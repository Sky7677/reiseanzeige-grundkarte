import pytest

from basemap import config, source

URLLIST = """TsvHttp-1.0
https://download.versatiles.org/osm.versatiles\t66681318912\tAbCd==
https://download.versatiles.org/osm.20260608.versatiles\t66581318912\tAbCd==
https://download.versatiles.org/osm.20261027.versatiles\t66681318912\tAbCd==
https://download.versatiles.org/osm.20260105.versatiles\t62381318912\tAbCd==
https://download.versatiles.org/osm.20261027.versatiles.md5\t60\tx==
"""

FEED = """<?xml version="1.0"?><rss><channel>
<item><title>osm.20260413.versatiles</title><link>https://download.versatiles.org/osm.20260413.versatiles</link></item>
<item><title>osm.20251006.versatiles</title></item>
</channel></rss>"""


def test_neueste_fassung_aus_der_liste():
    cfg = config.load()
    s = source.newest(URLLIST, cfg["source"]["base"], cfg["source"]["pattern"])
    assert s.name == "osm.20261027.versatiles"
    assert s.url == "https://download.versatiles.org/osm.20261027.versatiles"
    assert s.date == "2026-10-27" and s.tag == "grundkarte-2026-10-27"


def test_ersatzweise_aus_dem_feed():
    cfg = config.load()
    calls = []

    def fetch(url):
        calls.append(url)
        if url.endswith(".tsv"):
            raise OSError("nicht erreichbar")
        return FEED

    s = source.discover(cfg, fetch)
    assert s.date == "2026-04-13" and len(calls) == 2


def test_ohne_datierte_fassung():
    cfg = config.load()
    with pytest.raises(RuntimeError, match="keine datierte Fassung"):
        source.discover(cfg, lambda url: "osm.versatiles osm.20261399.versatiles")
