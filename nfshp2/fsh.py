"""SHPI / FSH texture archive reader.

NFSHP2 uses 4 record types in practice (surveyed across 137 archives):
    0x60  DXT1  (BC1) — 748 occurrences
    0x61  DXT3  (BC2) — 511
    0x7B  8-bit palettized — 113 (palette comes as a sibling record, type 0x2A)
    0x7D  32-bit ARGB — 30

Layout:
    char[4]  magic   = "SHPI"
    uint32   total_size
    uint32   entry_count
    char[4]  tag                   (e.g. "G335")
    Entry[entry_count]:
        char[4]  name
        uint32   offset             (to first record in this entry's chain)

Record header (16 bytes, common):
    byte    record_type
    u24 LE  record_size             (total bytes for this record incl. header)
    u16 LE  width
    u16 LE  height
    u16 LE  center_x
    u16 LE  center_y
    u16 LE  x_pos
    u16 LE  y_pos
    [16 bytes type-specific metadata, often zero]
    [payload]

A directory entry points at the FIRST record. The chain continues at
offset+record_size and ends at the next directory offset (or EOF).
"""
from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image


MAGIC = b"SHPI"

TYPE_DXT1 = 0x60
TYPE_DXT3 = 0x61
TYPE_PAL8 = 0x7B
TYPE_ARGB32 = 0x7D
TYPE_PALETTE_24BIT = 0x24  # 24-bit RGB palette (768 bytes for 256 colors)
TYPE_PALETTE_32BIT = 0x2D  # 32-bit ARGB palette
TYPE_PALETTE_2A = 0x2A     # ARGB8888 palette (the variant we see in NFSHP2)


@dataclass
class Record:
    type: int
    size: int          # full record size (incl header)
    width: int
    height: int
    center_x: int
    center_y: int
    x_pos: int
    y_pos: int
    payload: bytes     # bytes after the 16-byte common header
    offset: int        # absolute offset in the archive


@dataclass
class FshEntry:
    name: str
    offset: int
    records: list[Record] = field(default_factory=list)

    @property
    def primary(self) -> Record:
        return self.records[0]


def _parse_record(blob: bytes, offset: int) -> Record:
    if offset + 16 > len(blob):
        raise ValueError(f"record at {offset:#x} truncated")
    head = blob[offset:offset + 16]
    rec_type = head[0]
    rec_size = head[1] | (head[2] << 8) | (head[3] << 16)
    if rec_size == 0:
        # Some chains have a zero-size sentinel; treat as "rest of buffer".
        rec_size = len(blob) - offset
    width, height, cx, cy, xo, yo = struct.unpack("<HHHHHH", head[4:16])
    payload = blob[offset + 16:offset + rec_size]
    return Record(rec_type, rec_size, width, height, cx, cy, xo, yo, payload, offset)


class FshFile:
    def __init__(self, path: Path, blob: bytes, tag: bytes, entries: list[FshEntry]):
        self.path = path
        self.blob = blob
        self.tag = tag
        self.entries = entries

    @classmethod
    def open(cls, path: str | Path) -> "FshFile":
        path = Path(path)
        blob = path.read_bytes()
        return cls.from_bytes(blob, path)

    @classmethod
    def from_bytes(cls, blob: bytes, path: Path | None = None) -> "FshFile":
        if blob[:4] != MAGIC:
            raise ValueError(f"not a SHPI archive (got {blob[:4]!r})")
        total_size, count, tag = struct.unpack("<II4s", blob[4:16])
        # entries
        dir_entries = []
        cursor = 16
        for _ in range(count):
            name = blob[cursor:cursor + 4].decode("ascii", errors="replace")
            off = struct.unpack("<I", blob[cursor + 4:cursor + 8])[0]
            dir_entries.append((name, off))
            cursor += 8
        # sort offsets to know where each chain ends
        offsets_sorted = sorted({off for _, off in dir_entries} | {len(blob)})
        entries: list[FshEntry] = []
        for name, off in dir_entries:
            # chain end = next-greater offset in the directory
            idx = offsets_sorted.index(off)
            chain_end = offsets_sorted[idx + 1] if idx + 1 < len(offsets_sorted) else len(blob)
            entry = FshEntry(name=name, offset=off)
            cur = off
            while cur < chain_end:
                rec = _parse_record(blob, cur)
                if rec.size <= 0 or cur + rec.size > chain_end:
                    break
                entry.records.append(rec)
                cur += rec.size
                if rec.size < 16:
                    break
            entries.append(entry)
        return cls(path or Path("<bytes>"), blob, tag, entries)

    def to_image(self, entry: FshEntry) -> Image.Image:
        return record_to_image(entry)


def _find_palette(entry: FshEntry) -> bytes | None:
    """Return RGBA palette bytes (256*4) for a palettized entry, or None."""
    for rec in entry.records[1:]:
        if rec.type in (TYPE_PALETTE_2A, TYPE_PALETTE_32BIT):
            # Each color = 4 bytes. NFSHP2 stores BGRA → RGBA on read.
            # Empirically (see particle.fsh): bytes are R,G,B,A with R first.
            # Take width × height of the palette record as color count if sane,
            # else fall back to len(payload)//4.
            n = rec.width * max(rec.height, 1) if rec.width else len(rec.payload) // 4
            if n <= 0 or n > 256:
                n = len(rec.payload) // 4
            n = min(n, 256)
            pal = rec.payload[:n * 4]
            # Pad to 256 colors with zeros so all index values are safe.
            if len(pal) < 256 * 4:
                pal = pal + b"\x00" * (256 * 4 - len(pal))
            return pal
        if rec.type == TYPE_PALETTE_24BIT:
            n = len(rec.payload) // 3
            n = min(n, 256)
            out = bytearray(256 * 4)
            for i in range(n):
                r, g, b = rec.payload[i*3:i*3+3]
                out[i*4:i*4+4] = bytes([r, g, b, 255])
            return bytes(out)
    return None


def record_to_image(entry: FshEntry) -> Image.Image:
    rec = entry.primary
    w, h = rec.width, rec.height
    if rec.type == TYPE_DXT1:
        # Pillow BC1 decoder: 8 bytes per 4x4 block.
        return Image.frombytes("RGBA", (w, h), rec.payload, "bcn", 1)
    if rec.type == TYPE_DXT3:
        # BC2 (DXT3): explicit alpha, 16 bytes per 4x4 block.
        return Image.frombytes("RGBA", (w, h), rec.payload, "bcn", 2)
    if rec.type == TYPE_ARGB32:
        # ARGB32 little-endian → BGRA on the wire. Verify by experiment if colors look swapped.
        n = w * h * 4
        return Image.frombytes("RGBA", (w, h), rec.payload[:n], "raw", "BGRA")
    if rec.type == TYPE_PAL8:
        pal = _find_palette(entry)
        n = w * h
        idx_bytes = rec.payload[:n]
        img = Image.frombytes("P", (w, h), idx_bytes)
        if pal is not None:
            # Pillow's "P" mode palette is RGB-only; convert via custom RGBA → RGBA blit.
            rgba = bytearray(n * 4)
            for i, idx in enumerate(idx_bytes):
                rgba[i*4:i*4+4] = pal[idx*4:idx*4+4]
            return Image.frombytes("RGBA", (w, h), bytes(rgba))
        # No palette found: return as greyscale-ish RGBA.
        return img.convert("RGBA")
    raise ValueError(f"unsupported FSH record type {rec.type:#04x} (entry {entry.name!r})")
