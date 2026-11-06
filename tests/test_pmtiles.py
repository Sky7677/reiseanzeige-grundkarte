import gzip
import random

import pytest
from pmtiles.tile import tileid_to_zxy
from pmtiles.tile import zxy_to_tileid as reference_id

from basemap import config, mvt
from basemap.pmtiles import PMTilesError, Reader, lonlat_to_tile, zoom_of, zoom_stats, zxy_to_tile_id
from fixtures import write_basemap


def test_kachelnummer_wie_referenz():
    rnd = random.Random(7)
    for z in range(0, 16):
        for _ in range(50):
            x, y = rnd.randrange(1 << z), rnd.randrange(1 << z)
            tid = zxy_to_tile_id(z, x, y)
            assert tid == reference_id(z, x, y)
            assert zoom_of(tid) == z == tileid_to_zxy(tid)[0]


def test_kachel_ausserhalb():
    with pytest.raises(ValueError):
        zxy_to_tile_id(3, 8, 0)


def test_lage_einer_kachel():
    # Augsburg Hbf liegt auf Stufe 12 in Kachel 2171/1417 (Web-Mercator, y von Norden)
    assert lonlat_to_tile(10.8856, 48.3655, 12) == (2171, 1417)
    assert lonlat_to_tile(0.0, 0.0, 1) == (1, 1)


def test_lesen_mit_unterverzeichnissen(tmp_path):
    cfg = config.load()
    path = str(tmp_path / "karte.pmtiles")
    tiles = write_basemap(path, cfg, 12, filler=12000)
    with Reader.open(path) as r:
        assert r.header.leaf_length > 0, "genug Kacheln für Unterverzeichnisse"
        assert (r.header.min_zoom, r.header.max_zoom) == (0, 12)
        for (z, x, y), raw in tiles.items():
            assert r.tile_data(z, x, y) == raw
        assert r.tile(12, 0, 0) is None
        assert r.tile(12, 1, 1) is None
        assert sum(e.run_length for e in r.entries()) == r.header.addressed_tiles == len(tiles)
        stats = zoom_stats(r)
    assert stats[12]["tiles"] >= 12000
    assert sum(s["tiles"] for s in stats.values()) == len(tiles)


def test_metadaten_und_ebenen(tmp_path):
    cfg = config.load()
    path = str(tmp_path / "karte.pmtiles")
    write_basemap(path, cfg, 8)
    with Reader.open(path) as r:
        assert "streets" in {l["id"] for l in r.metadata()["vector_layers"]}
        x, y = lonlat_to_tile(13.3694, 52.5251, 8)
        assert mvt.layer_names(r.tile_data(8, x, y)) == ["land", "streets", "place_labels"]
        assert gzip.decompress(r.tile(8, x, y)) == r.tile_data(8, x, y)


def test_keine_pmtiles_datei(tmp_path):
    p = tmp_path / "x.pmtiles"
    p.write_bytes(b"SQLite format 3\x00" + b"\x00" * 200)
    with pytest.raises(PMTilesError):
        Reader.open(str(p))


def test_ungueltige_kachel():
    with pytest.raises(mvt.MVTError):
        mvt.layer_names(b"\x1a\x7f\x0a")
