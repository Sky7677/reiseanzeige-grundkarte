"""Kleine Grundkarten für die Tests, geschrieben mit dem PMTiles-Paket von Protomaps
(unabhängig vom eigenen Leser in basemap/pmtiles.py)."""

from __future__ import annotations

import gzip
import random

from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

from basemap.pmtiles import lonlat_to_tile


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _field(num: int, payload: bytes) -> bytes:
    return _varint((num << 3) | 2) + _varint(len(payload)) + payload


def mvt(*layers: str, extra: bytes = b"") -> bytes:
    """Vektorkachel mit leeren Ebenen der angegebenen Namen."""
    out = b""
    for name in layers:
        layer = _varint((15 << 3) | 0) + _varint(2) + _field(1, name.encode()) + _varint((5 << 3) | 0) + _varint(4096) + extra
        out += _field(3, layer)
    return out


LAYERS = ["aerialways", "boundaries", "boundary_labels", "bridges", "buildings", "dam_lines", "dam_polygons",
          "ferries", "land", "ocean", "pier_lines", "pier_polygons", "place_labels", "sites", "street_polygons",
          "streets", "water_lines", "water_polygons", "water_polygons_labels", "pois"]


def write_basemap(path: str, cfg: dict, max_zoom: int, *, compression: int = Compression.GZIP,
                  tile_type: int = TileType.MVT, skip: tuple[str, int] | None = None,
                  layers: list[str] | None = None, filler: int = 0) -> dict[tuple[int, int, int], bytes]:
    """Grundkarte mit Kacheln an den Stichproben-Orten (alle Zoomstufen), Kachel 0/0/0
    und `filler` zusätzlichen Kacheln auf Stufe 10 (für Unterverzeichnisse)."""
    tiles: dict[tuple[int, int, int], bytes] = {}
    for z in range(0, max_zoom + 1):
        for s in cfg["samples"]:
            if skip and skip == (s["name"], z):
                continue
            x, y = lonlat_to_tile(s["lon"], s["lat"], z)
            names = ["land", "streets", "place_labels"] if z >= 8 else ["land", "boundaries"]
            tiles[(z, x, y)] = mvt(*names, extra=f"{s['name']}/{z}".encode())
    tiles.setdefault((0, 0, 0), mvt("ocean", "land"))
    rnd = random.Random(1)
    for i in range(filler):
        x, y = 2000 + i % 200, 1250 + i // 200
        tiles.setdefault((12, x, y), mvt("land", extra=bytes(rnd.randrange(256) for _ in range(rnd.randrange(1, 300)))))
    data = {k: (gzip.compress(v, mtime=0) if compression == Compression.GZIP else v) for k, v in tiles.items()}
    west, south, east, north = cfg["bbox"]
    with open(path, "wb") as f:
        w = Writer(f)
        for (z, x, y) in sorted(data, key=lambda k: zxy_to_tileid(*k)):
            w.write_tile(zxy_to_tileid(z, x, y), data[(z, x, y)])
        w.finalize(
            {
                "tile_type": tile_type,
                "tile_compression": compression,
                "min_lon_e7": int((west - 0.5) * 1e7), "min_lat_e7": int((south - 0.5) * 1e7),
                "max_lon_e7": int((east + 0.5) * 1e7), "max_lat_e7": int((north + 0.5) * 1e7),
                "center_zoom": 6, "center_lon_e7": int(10.4 * 1e7), "center_lat_e7": int(51.1 * 1e7),
            },
            {"name": "Test", "attribution": "© OpenStreetMap-Mitwirkende",
             "vector_layers": [{"id": n, "fields": {}} for n in (layers or LAYERS)]},
        )
    return tiles
