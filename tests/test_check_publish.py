import hashlib
import json

from pmtiles.tile import Compression, TileType

from basemap import check, config, publish
from fixtures import LAYERS, write_basemap


def test_gute_karte_besteht(tmp_path):
    cfg = config.load()
    path = str(tmp_path / "grundkarte-de.pmtiles")
    write_basemap(path, cfg, cfg["max_zoom"])
    report, errors = check.run(path, cfg)
    assert errors == [], report
    assert "Alle Prüfungen bestanden" in report
    assert f"| Augsburg | {cfg['max_zoom']} |" in report
    assert "Summe bis hier" in report


def test_fehlende_kachel_und_ebene_fallen_auf(tmp_path):
    cfg = config.load()
    path = str(tmp_path / "k.pmtiles")
    write_basemap(path, cfg, 12, skip=("Görlitz", 12), layers=[l for l in LAYERS if l != "ferries"])
    _, errors = check.run(path, cfg, max_zoom=12)
    assert any("Görlitz z12" in e and "fehlt" in e for e in errors)
    assert any("ferries" in e for e in errors)


def test_falsche_zoomstufe_kompression_und_groesse(tmp_path):
    cfg = config.load()
    path = str(tmp_path / "k.pmtiles")
    write_basemap(path, cfg, 10, compression=Compression.NONE, tile_type=TileType.PNG)
    _, errors = check.run(path, dict(cfg, max_size_bytes=10), max_zoom=12)
    text = " ".join(errors)
    assert "zu groß" in text and "png statt mvt" in text and "0–12" in text
    # Gleiche Datei, aber mit passender Erwartung: unkomprimierte Kacheln sind erlaubt
    _, errors = check.run(path, cfg, max_zoom=10)
    assert not any("Kompression" in e for e in errors)


def test_kaputte_datei(tmp_path):
    p = tmp_path / "k.pmtiles"
    p.write_bytes(b"nichts")
    _, errors = check.run(str(p), config.load())
    assert errors and "nicht lesbar" in errors[0]


def test_manifest(tmp_path):
    cfg = config.load()
    src = tmp_path / "grundkarte-de.pmtiles"
    write_basemap(str(src), cfg, cfg["max_zoom"])
    digest = hashlib.sha256(src.read_bytes()).hexdigest()
    out = tmp_path / "dist"
    assert publish.main([str(src), "--source-url", "https://download.versatiles.org/osm.20261027.versatiles",
                         "--source-date", "2026-10-27", "--out", str(out)]) == 0
    m = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert (out / cfg["file"]).exists() and not src.exists()
    assert m["format"] == 1 and m["kind"] == "basemap" and m["version"] == "2026-10-27"
    assert m["sha256"] == digest and m["size"] == (out / cfg["file"]).stat().st_size
    assert (m["min_zoom"], m["max_zoom"], m["tile_compression"], m["file_format"]) == (0, cfg["max_zoom"], "gzip", "pmtiles")
    assert m["online"]["tiles"].endswith("{z}/{x}/{y}") and "{fontstack}" in m["online"]["glyphs"]
    assert m["source"] == "VersaTiles osm.20261027.versatiles"
    assert "streets" in m["vector_layers"]
    assert m["bounds"] == cfg["bbox"]
