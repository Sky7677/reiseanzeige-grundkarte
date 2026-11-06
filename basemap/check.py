"""Geschnittene Grundkarte prüfen und vermessen.

Geprüft wird, was die App braucht: Vektorkacheln (MVT) mit gzip oder ohne
Kompression, Zoomstufen ab 0 bis zur eingestellten Stufe, ein Gebiet, das
Deutschland ganz abdeckt, die Ebenen, die die Kartenstile nutzen, und Kacheln
an bekannten Orten. Dazu die Größe – unter der Grenze für Release-Dateien –
und die Größe je Zoomstufe, damit sich 11 und 12 vergleichen lassen.

Aufruf: python -m basemap.check DATEI [--max-zoom N] [--report bericht.md]
Endet mit Fehler, wenn eine Prüfung scheitert; dann wird nichts veröffentlicht.
"""

from __future__ import annotations

import argparse
import os
import sys
import time

from . import config as cfgmod
from . import mvt
from .pmtiles import COMPRESSION, TILE_TYPE, PMTilesError, Reader, lonlat_to_tile, zoom_stats

SAMPLE_ZOOMS = (5, 8)        # zusätzlich zur höchsten Stufe
CITY_LAYERS = {"streets"}    # in Städten auf der höchsten Stufe unbedingt vorhanden


def mb(n: int) -> str:
    return f"{n / 1_000_000:,.1f} MB".replace(",", ".")


def run(path: str, cfg: dict, max_zoom: int | None = None) -> tuple[str, list[str]]:
    """Bericht (Markdown) und Liste der Fehler."""
    max_zoom = int(cfg["max_zoom"] if max_zoom is None else max_zoom)
    errors: list[str] = []
    size = os.path.getsize(path)
    lines = [f"Datei `{os.path.basename(path)}`: {mb(size)} ({size:,} Byte)".replace(",", "."), ""]
    if size > int(cfg["max_size_bytes"]):
        errors.append(f"Datei zu groß: {mb(size)} > {mb(int(cfg['max_size_bytes']))}")

    t0 = time.time()
    try:
        reader = Reader.open(path)
    except (PMTilesError, OSError) as err:
        return "\n".join(lines + [f"Nicht lesbar: {err}"]), [f"Datei nicht lesbar: {err}"]
    with reader:
        h = reader.header
        lines += [
            f"Kacheln: {h.addressed_tiles:,} adressiert, {h.tile_contents:,} verschieden".replace(",", "."),
            f"Typ {TILE_TYPE.get(h.tile_type, h.tile_type)}, Kompression {COMPRESSION.get(h.tile_compression, h.tile_compression)}, "
            f"Zoom {h.min_zoom} bis {h.max_zoom}",
            f"Gebiet: {h.min_lon:.3f}, {h.min_lat:.3f} bis {h.max_lon:.3f}, {h.max_lat:.3f}",
            "",
        ]
        if TILE_TYPE.get(h.tile_type) != "mvt":
            errors.append(f"Kacheltyp {TILE_TYPE.get(h.tile_type, h.tile_type)} statt mvt")
        if COMPRESSION.get(h.tile_compression) not in ("gzip", "none"):
            errors.append(f"Kompression {COMPRESSION.get(h.tile_compression, h.tile_compression)} – die App liest nur gzip oder unkomprimiert")
        if h.min_zoom != 0 or h.max_zoom != max_zoom:
            errors.append(f"Zoom {h.min_zoom}–{h.max_zoom} statt 0–{max_zoom}")
        west, south, east, north = cfg["bbox"]
        if h.min_lon > west + 0.01 or h.min_lat > south + 0.01 or h.max_lon < east - 0.01 or h.max_lat < north - 0.01:
            errors.append("Gebiet deckt die eingestellte bbox nicht ab")

        try:
            meta = reader.metadata()
        except (PMTilesError, ValueError) as err:
            meta = {}
            errors.append(f"Metadaten nicht lesbar: {err}")
        layers = {l.get("id") for l in meta.get("vector_layers", []) if isinstance(l, dict)}
        missing = [l for l in cfg["required_layers"] if l not in layers]
        lines.append(f"Ebenen laut Metadaten: {len(layers)}" + (f", es fehlen: {', '.join(missing)}" if missing else ", alle benötigten vorhanden"))
        if missing:
            errors.append("Ebenen fehlen in den Metadaten: " + ", ".join(missing))
        for key in ("attribution", "name", "description"):
            if key in meta:
                lines.append(f"Metadaten {key}: {str(meta[key])[:160]}")
        lines.append("")

        if reader.tile(0, 0, 0) is None:
            errors.append("Kachel 0/0/0 fehlt")
        lines += ["| Ort | Zoom | Kachel | Größe | Ebenen | Ergebnis |", "|---|---|---|---|---|---|"]
        for s in cfg["samples"]:
            for z in (max_zoom, *[z for z in SAMPLE_ZOOMS if z < max_zoom]):
                x, y = lonlat_to_tile(s["lon"], s["lat"], z)
                label = f"| {s['name']} | {z} | {x}/{y} |"
                try:
                    data = reader.tile_data(z, x, y)
                except (PMTilesError, OSError, EOFError) as err:
                    errors.append(f"{s['name']} z{z}: nicht lesbar ({err})")
                    lines.append(f"{label} – | – | nicht lesbar |")
                    continue
                if data is None:
                    errors.append(f"{s['name']} z{z}: Kachel {x}/{y} fehlt")
                    lines.append(f"{label} – | – | fehlt |")
                    continue
                try:
                    names = mvt.layer_names(data)
                except mvt.MVTError as err:
                    errors.append(f"{s['name']} z{z}: keine gültige Vektorkachel ({err})")
                    lines.append(f"{label} {len(data):,} B | – | ungültig |".replace(",", "."))
                    continue
                problems = []
                if not names:
                    problems.append("leer")
                unknown = [n for n in names if layers and n not in layers]
                if unknown:
                    problems.append("unbekannte Ebenen " + ", ".join(unknown))
                if z == max_zoom and not CITY_LAYERS <= set(names):
                    problems.append("ohne Straßen")
                if problems:
                    errors.append(f"{s['name']} z{z}: " + "; ".join(problems))
                lines.append(f"{label} {len(data):,} B | {len(names)} | {'ok' if not problems else '; '.join(problems)} |".replace(",", "."))

        stats = zoom_stats(reader)
    lines += ["", "Größe je Zoomstufe (gleiche Kacheln einmal gezählt):", "",
              "| Zoom | Kacheln | Daten | Summe bis hier |", "|---|---|---|---|"]
    total = 0
    for z, s in stats.items():
        total += s["bytes"]
        lines.append(f"| {z} | {s['tiles']:,} | {mb(s['bytes'])} | {mb(total)} |".replace(",", "."))
    lines += ["", f"Geprüft in {time.time() - t0:.1f} s."]
    if errors:
        lines += ["", "**Fehler:**", *[f"- {e}" for e in errors]]
    else:
        lines += ["", "Alle Prüfungen bestanden."]
    return "\n".join(lines), errors


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Grundkarte prüfen")
    p.add_argument("file")
    p.add_argument("--config")
    p.add_argument("--max-zoom", type=int)
    p.add_argument("--report")
    a = p.parse_args(argv)
    text, errors = run(a.file, cfgmod.load(a.config), a.max_zoom)
    print(text)
    if a.report:
        with open(a.report, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
