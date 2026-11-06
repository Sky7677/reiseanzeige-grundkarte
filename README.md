# reiseanzeige-grundkarte

Deutschland-Grundkarte für die [Android-Reiseanzeige](https://github.com/Sky7677/android-reiseanzeige): ein Ausschnitt aus der VersaTiles-Fassung von OpenStreetMap (Shortbread-Schema), als eine PMTiles-Datei. Die App lädt sie einmal und zeigt die Karte damit auch im Funkloch; Details über der Grundkarte holt sie online vom VersaTiles-Kachelserver. Beide stammen aus derselben VersaTiles-Fassung und passen deshalb zu denselben Kartenstilen.

## Lauf

Der Workflow [`Grundkarte bauen`](.github/workflows/grundkarte.yml) läuft am 7. jedes Monats und von Hand über „Run workflow“:

1. Neueste datierte Fassung `osm.JJJJMMTT.versatiles` ermitteln (URL-Liste von download.versatiles.org, ersatzweise der RSS-Feed). Ist das Release `grundkarte-JJJJ-MM-TT` dieser Fassung schon da, endet der Lauf.
2. Mit dem [`versatiles`](https://github.com/versatiles-org/versatiles-rs)-Werkzeug Deutschland samt Rand bis zur eingestellten Zoomstufe ausschneiden, Kacheln gzip-komprimiert. Gelesen wird direkt vom Server, nur die nötigen Teile.
3. Prüfen: Größe unter 1,9 GB (Grenze für Release-Dateien 2 GB), Vektorkacheln, Zoom ab 0, Gebiet, alle Ebenen der Kartenstile in den Metadaten, Stichproben-Kacheln an zehn Orten von Flensburg bis Konstanz. Der Bericht steht in der Zusammenfassung des Laufs, mit der Größe je Zoomstufe.
4. Nur bei Erfolg als Release `grundkarte-JJJJ-MM-TT` mit `manifest.json` veröffentlichen, als „latest“ markiert. Die letzten zwei Fassungen bleiben erhalten.
5. Statusdatei `status/letzter-lauf.json` committen. Das zeigt, wie der letzte Lauf ausging, und hält den Zeitplan am Leben (GitHub schaltet ihn nach 60 Tagen ohne Aktivität ab).

Bei Pull Requests läuft ein Messlauf ohne Veröffentlichung: Ausschnitt bis Zoom 12, daraus Zoom 11, beide geprüft und vermessen.

Einstellungen (Gebiet, Rand, Zoomstufe, Größengrenze, Online-Adressen, Stichproben) stehen in [`grundkarte.json`](grundkarte.json).

## Manifest

Die App liest `https://github.com/Sky7677/reiseanzeige-grundkarte/releases/latest/download/manifest.json` und lädt die Datei nur bei neuer Version:

```json
{
  "format": 1,
  "kind": "basemap",
  "version": "2026-10-27",
  "file": "grundkarte-de.pmtiles",
  "file_format": "pmtiles",
  "size": 512345678,
  "sha256": "…",
  "source": "VersaTiles osm.20261027.versatiles",
  "schema": "shortbread-v1",
  "min_zoom": 0,
  "max_zoom": 12,
  "bounds": [5.43, 46.95, 15.6, 55.33],
  "tile_compression": "gzip",
  "online": {
    "tiles": "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}",
    "glyphs": "https://tiles.versatiles.org/assets/glyphs/{fontstack}/{range}.pbf",
    "max_zoom": 14
  },
  "attribution": "© OpenStreetMap-Mitwirkende · VersaTiles",
  "license": "ODbL 1.0 – © OpenStreetMap-Mitwirkende (https://www.openstreetmap.org/copyright)"
}
```

Die Online-Adressen stehen hier statt in der App: Fällt ein Dienst weg, genügt eine neue Fassung des Manifests, kein App-Update.

## Entwicklung

```sh
pip install -e ".[test]"
pytest -q
python -m basemap.source                       # neueste Fassung anzeigen
python -m basemap.check grundkarte-de.pmtiles  # eine Datei prüfen
```

Die Tests schreiben kleine Grundkarten mit dem PMTiles-Paket von Protomaps und lesen sie mit dem eigenen, abhängigkeitsfreien Leser in `basemap/pmtiles.py`.

## Lizenzen

- Code: MIT (siehe `LICENSE`).
- Daten in den Releases: © OpenStreetMap-Mitwirkende, [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/); Kacheln aufbereitet von [VersaTiles](https://versatiles.org).
