"""Einstellungen aus grundkarte.json."""

from __future__ import annotations

import json
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parent.parent / "grundkarte.json"


def load(path: str | Path | None = None) -> dict:
    with open(path or DEFAULT_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    west, south, east, north = cfg["bbox"]
    if not (west < east and south < north):
        raise ValueError("bbox muss West, Süd, Ost, Nord sein")
    if not 0 <= int(cfg["max_zoom"]) <= 14:
        raise ValueError("max_zoom muss zwischen 0 und 14 liegen")
    return cfg


def bbox_arg(cfg: dict) -> str:
    """bbox für versatiles convert: "West,Süd,Ost,Nord"."""
    return ",".join(f"{v:g}" for v in cfg["bbox"])
