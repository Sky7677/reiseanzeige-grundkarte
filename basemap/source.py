"""Neueste datierte VersaTiles-Fassung von OpenStreetMap finden.

VersaTiles veröffentlicht den Planeten unregelmäßig als datierte Dateien
(osm.JJJJMMTT.versatiles). Gelesen wird die URL-Liste, ersatzweise der RSS-Feed;
geschnitten wird immer aus der datierten Datei, nicht aus osm.versatiles,
damit Version und Inhalt zusammenpassen.

Aufruf: python -m basemap.source [--github-output DATEI]
Schreibt url, date (JJJJ-MM-TT), name und tag als Zeilen key=value.
"""

from __future__ import annotations

import argparse
import re
import sys
import urllib.request
from dataclasses import dataclass

from . import USER_AGENT
from . import config as cfgmod


@dataclass(frozen=True)
class Source:
    name: str      # osm.20261027.versatiles
    url: str
    date: str      # 2026-10-27

    @property
    def tag(self) -> str:
        return f"grundkarte-{self.date}"


def newest(text: str, base: str, pattern: str) -> Source | None:
    """Neueste Fassung aus beliebigem Text (TSV-Liste, RSS, HTML)."""
    found: dict[str, str] = {}
    for m in re.finditer(pattern, text):
        stamp = m.group(1)
        if not _valid_date(stamp):
            continue
        found[stamp] = m.group(0)
    if not found:
        return None
    stamp = max(found)
    name = found[stamp]
    return Source(name=name, url=base.rstrip("/") + "/" + name, date=f"{stamp[:4]}-{stamp[4:6]}-{stamp[6:]}")


def _valid_date(stamp: str) -> bool:
    y, m, d = int(stamp[:4]), int(stamp[4:6]), int(stamp[6:])
    return 2020 <= y <= 2100 and 1 <= m <= 12 and 1 <= d <= 31


def _get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as res:
        return res.read(4 * 1024 * 1024).decode("utf-8", "replace")


def discover(cfg: dict, fetch=_get) -> Source:
    src = cfg["source"]
    errors = []
    for url in (src["urllist"], src["feed"]):
        try:
            hit = newest(fetch(url), src["base"], src["pattern"])
        except Exception as err:  # noqa: BLE001 – nächste Quelle versuchen
            errors.append(f"{url}: {err}")
            continue
        if hit:
            return hit
        errors.append(f"{url}: keine datierte Fassung gefunden")
    raise RuntimeError("VersaTiles-Fassung nicht ermittelbar – " + "; ".join(errors))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Neueste VersaTiles-Fassung ermitteln")
    p.add_argument("--config")
    p.add_argument("--github-output", help="Ergebnis zusätzlich an diese Datei anhängen ($GITHUB_OUTPUT)")
    a = p.parse_args(argv)
    s = discover(cfgmod.load(a.config))
    lines = [f"url={s.url}", f"name={s.name}", f"date={s.date}", f"tag={s.tag}"]
    print("\n".join(lines))
    if a.github_output:
        with open(a.github_output, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
