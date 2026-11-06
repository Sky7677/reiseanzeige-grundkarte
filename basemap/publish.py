"""Manifest zur geprüften Grundkarte schreiben.

Die App liest zuerst nur das kleine Manifest (Version, Größe, Prüfsumme) und
lädt die Datei nur bei neuer Version. Die Adressen der Online-Kacheln und
Schriften stehen hier statt in der App: Fällt ein Dienst weg, genügt eine
neue Fassung des Manifests.

Aufruf: python -m basemap.publish DATEI --source-url URL --source-date JJJJ-MM-TT
            [--out dist] [--manifest manifest.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from . import config as cfgmod
from .pmtiles import COMPRESSION, Reader

MANIFEST_FORMAT = 1


def sha256_of(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(path: str, cfg: dict, source_url: str, source_date: str, created: str | None = None) -> dict:
    with Reader.open(path) as r:
        h = r.header
        meta = r.metadata()
    return {
        "format": MANIFEST_FORMAT,
        "kind": "basemap",
        "version": source_date,
        "file": os.path.basename(path),
        "file_format": "pmtiles",
        "size": os.path.getsize(path),
        "sha256": sha256_of(path),
        "created": created or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": f"VersaTiles {source_url.rsplit('/', 1)[-1]}",
        "source_url": source_url,
        "schema": "shortbread-v1",
        "min_zoom": h.min_zoom,
        "max_zoom": h.max_zoom,
        # Gebiet, das bis max_zoom vollständig enthalten ist. Der Kopf der Datei nennt ein
        # viel größeres, weil die groben Stufen ganze Kacheln (bis zur Welt) enthalten.
        "bounds": list(cfg["bbox"]),
        "tile_compression": COMPRESSION.get(h.tile_compression, "unknown"),
        "tiles": h.addressed_tiles,
        "vector_layers": sorted(l["id"] for l in meta.get("vector_layers", []) if isinstance(l, dict) and "id" in l),
        "online": cfg["online"],
        "attribution": cfg["attribution"],
        "license": cfg["license"],
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Manifest der Grundkarte schreiben")
    p.add_argument("file")
    p.add_argument("--config")
    p.add_argument("--source-url", required=True)
    p.add_argument("--source-date", required=True)
    p.add_argument("--out", default="dist")
    a = p.parse_args(argv)
    cfg = cfgmod.load(a.config)
    os.makedirs(a.out, exist_ok=True)
    target = os.path.join(a.out, cfg["file"])
    if os.path.abspath(a.file) != os.path.abspath(target):
        os.replace(a.file, target)
    manifest = build_manifest(target, cfg, a.source_url, a.source_date)
    with open(os.path.join(a.out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
