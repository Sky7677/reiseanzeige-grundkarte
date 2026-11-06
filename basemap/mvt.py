"""Namen der Ebenen einer Vektorkachel (Mapbox Vector Tile), ohne Protobuf-Bibliothek."""

from __future__ import annotations


class MVTError(ValueError):
    pass


def _varint(buf: bytes, pos: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if pos >= len(buf):
            raise MVTError("Kachel abgeschnitten")
        b = buf[pos]
        pos += 1
        value |= (b & 0x7F) << shift
        if b < 0x80:
            return value, pos
        shift += 7
        if shift > 63:
            raise MVTError("Zahl in der Kachel zu lang")


def _fields(buf: bytes):
    """(Feldnummer, Typ, Wert) – Wert ist bei Typ 2 das Bytestück."""
    pos = 0
    while pos < len(buf):
        key, pos = _varint(buf, pos)
        field, wire = key >> 3, key & 7
        if wire == 0:
            value, pos = _varint(buf, pos)
        elif wire == 1:
            value, pos = buf[pos:pos + 8], pos + 8
        elif wire == 2:
            size, pos = _varint(buf, pos)
            value, pos = buf[pos:pos + size], pos + size
            if pos > len(buf):
                raise MVTError("Kachel abgeschnitten")
        elif wire == 5:
            value, pos = buf[pos:pos + 4], pos + 4
        else:
            raise MVTError(f"Unbekannter Feldtyp {wire}")
        yield field, wire, value


def layer_names(tile: bytes) -> list[str]:
    """Ebenen (Feld 3 der Kachel), je mit ihrem Namen (Feld 1 der Ebene)."""
    names = []
    for field, wire, value in _fields(tile):
        if field == 3 and wire == 2:
            for f2, w2, v2 in _fields(value):
                if f2 == 1 and w2 == 2:
                    names.append(v2.decode("utf-8"))
                    break
    return names
