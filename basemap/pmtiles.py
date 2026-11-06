"""PMTiles (Version 3) lesen, nur mit der Standardbibliothek.

Genügt für die Prüfung der Grundkarte: Kopf, Metadaten und einzelne Kacheln.
Spezifikation: https://github.com/protomaps/PMTiles/blob/main/spec/v3/spec.md
"""

from __future__ import annotations

import gzip
import json
import math
import struct
from dataclasses import dataclass
from typing import BinaryIO

MAGIC = b"PMTiles"
HEADER_LEN = 127

COMPRESSION = {0: "unknown", 1: "none", 2: "gzip", 3: "brotli", 4: "zstd"}
TILE_TYPE = {0: "unknown", 1: "mvt", 2: "png", 3: "jpeg", 4: "webp", 5: "avif", 6: "mlt"}


class PMTilesError(ValueError):
    pass


@dataclass(frozen=True)
class Header:
    root_offset: int
    root_length: int
    metadata_offset: int
    metadata_length: int
    leaf_offset: int
    leaf_length: int
    data_offset: int
    data_length: int
    addressed_tiles: int
    tile_entries: int
    tile_contents: int
    clustered: bool
    internal_compression: int
    tile_compression: int
    tile_type: int
    min_zoom: int
    max_zoom: int
    min_lon: float
    min_lat: float
    max_lon: float
    max_lat: float
    center_zoom: int
    center_lon: float
    center_lat: float


@dataclass(frozen=True)
class Entry:
    tile_id: int
    offset: int
    length: int
    run_length: int


def parse_header(raw: bytes) -> Header:
    if len(raw) < HEADER_LEN or raw[:7] != MAGIC:
        raise PMTilesError("Keine PMTiles-Datei (Kennung fehlt)")
    if raw[7] != 3:
        raise PMTilesError(f"PMTiles-Version {raw[7]} wird nicht unterstützt")
    u64 = struct.unpack_from("<11Q", raw, 8)
    clustered, ic, tc, tt, minz, maxz = struct.unpack_from("<6B", raw, 96)
    min_lon, min_lat, max_lon, max_lat = struct.unpack_from("<4i", raw, 102)
    cz = raw[118]
    c_lon, c_lat = struct.unpack_from("<2i", raw, 119)
    return Header(*u64, bool(clustered), ic, tc, tt, minz, maxz,
                  min_lon / 1e7, min_lat / 1e7, max_lon / 1e7, max_lat / 1e7, cz, c_lon / 1e7, c_lat / 1e7)


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(buf):
            raise PMTilesError("Verzeichnis abgeschnitten")
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if b < 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise PMTilesError("Zahl im Verzeichnis zu lang")


def decompress(data: bytes, compression: int) -> bytes:
    if compression in (0, 1):
        return data
    if compression == 2:
        return gzip.decompress(data)
    raise PMTilesError(f"Kompression {COMPRESSION.get(compression, compression)} wird hier nicht unterstützt")


def parse_directory(raw: bytes) -> list[Entry]:
    n, pos = _varint(raw, 0)
    ids, runs, lengths, offsets = [], [], [], []
    last = 0
    for _ in range(n):
        d, pos = _varint(raw, pos)
        last += d
        ids.append(last)
    for _ in range(n):
        v, pos = _varint(raw, pos)
        runs.append(v)
    for _ in range(n):
        v, pos = _varint(raw, pos)
        lengths.append(v)
    for i in range(n):
        v, pos = _varint(raw, pos)
        if v == 0 and i > 0:
            offsets.append(offsets[i - 1] + lengths[i - 1])
        else:
            offsets.append(v - 1)
    return [Entry(ids[i], offsets[i], lengths[i], runs[i]) for i in range(n)]


def zxy_to_tile_id(z: int, x: int, y: int) -> int:
    """Kachelnummer entlang der Hilbert-Kurve, wie in der Spezifikation."""
    if not 0 <= z <= 31 or not (0 <= x < (1 << z) and 0 <= y < (1 << z)):
        raise ValueError("Kachel außerhalb der Zoomstufe")
    acc = ((1 << (z * 2)) - 1) // 3
    a = z - 1
    while a >= 0:
        s = 1 << a
        rx = s & x
        ry = s & y
        acc += ((3 * rx) ^ ry) << a
        if ry == 0:
            if rx != 0:
                x, y = s - 1 - x, s - 1 - y
            x, y = y, x
        a -= 1
    return acc


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 1 << z
    x = int((lon + 180.0) / 360.0 * n)
    r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def find(entries: list[Entry], tile_id: int) -> Entry | None:
    lo, hi = 0, len(entries) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        c = entries[mid].tile_id
        if tile_id > c:
            lo = mid + 1
        elif tile_id < c:
            hi = mid - 1
        else:
            return entries[mid]
    if hi >= 0:
        e = entries[hi]
        if e.run_length == 0:
            return e   # Verweis auf ein Unterverzeichnis
        if tile_id - e.tile_id < e.run_length:
            return e
    return None


class Reader:
    def __init__(self, f: BinaryIO) -> None:
        self.f = f
        self.header = parse_header(self._read(0, HEADER_LEN))
        self._root = self._directory(self.header.root_offset, self.header.root_length)
        self._leaves: dict[int, list[Entry]] = {}

    @classmethod
    def open(cls, path: str) -> "Reader":
        return cls(open(path, "rb"))

    def close(self) -> None:
        self.f.close()

    def __enter__(self) -> "Reader":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _read(self, offset: int, length: int) -> bytes:
        self.f.seek(offset)
        data = self.f.read(length)
        if len(data) != length:
            raise PMTilesError("Datei kürzer als im Kopf angegeben")
        return data

    def _directory(self, offset: int, length: int) -> list[Entry]:
        return parse_directory(decompress(self._read(offset, length), self.header.internal_compression))

    def metadata(self) -> dict:
        h = self.header
        if h.metadata_length == 0:
            return {}
        raw = decompress(self._read(h.metadata_offset, h.metadata_length), h.internal_compression)
        return json.loads(raw.decode("utf-8"))

    def tile(self, z: int, x: int, y: int) -> bytes | None:
        """Kachel wie gespeichert (also ggf. noch komprimiert), oder None."""
        tile_id = zxy_to_tile_id(z, x, y)
        entries = self._root
        for _depth in range(4):
            e = find(entries, tile_id)
            if e is None:
                return None
            if e.run_length > 0:
                return self._read(self.header.data_offset + e.offset, e.length)
            entries = self._leaves.get(e.offset)
            if entries is None:
                if len(self._leaves) >= 64:
                    self._leaves.pop(next(iter(self._leaves)))
                entries = self._leaves[e.offset] = self._directory(self.header.leaf_offset + e.offset, e.length)
        raise PMTilesError("Verzeichnis zu tief verschachtelt")

    def tile_data(self, z: int, x: int, y: int) -> bytes | None:
        """Kachel entpackt."""
        raw = self.tile(z, x, y)
        return None if raw is None else decompress(raw, self.header.tile_compression)

    def entries(self):
        """Alle Kacheleinträge (ohne Verweise auf Unterverzeichnisse), in Verzeichnisreihenfolge."""
        stack = [iter(self._root)]
        while stack:
            e = next(stack[-1], None)
            if e is None:
                stack.pop()
            elif e.run_length > 0:
                yield e
            else:
                stack.append(iter(self._directory(self.header.leaf_offset + e.offset, e.length)))


def zoom_of(tile_id: int) -> int:
    """Zoomstufe einer Kachelnummer."""
    z = 0
    while ((1 << (2 * (z + 1))) - 1) // 3 <= tile_id:
        z += 1
    return z


def zoom_stats(reader: Reader) -> dict[int, dict[str, int]]:
    """Je Zoomstufe: Zahl der Kacheln und Bytes. Gleiche Kacheln (z. B. Meer) liegen
    nur einmal in der Datei und zählen bei der niedrigsten Stufe, in der sie vorkommen."""
    stats: dict[int, dict[str, int]] = {}
    seen: set[int] = set()
    for e in reader.entries():
        z = zoom_of(e.tile_id)
        # Ein Lauf kann über das Ende einer Zoomstufe hinausreichen; das betrifft
        # nur einfarbige Kacheln (Meer) und ist für die Größe vernachlässigbar.
        s = stats.setdefault(z, {"tiles": 0, "bytes": 0})
        s["tiles"] += e.run_length
        if e.offset not in seen:
            seen.add(e.offset)
            s["bytes"] += e.length
    return dict(sorted(stats.items()))
