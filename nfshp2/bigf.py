"""BIGF / VIV archive reader.

Layout (all big-endian unless noted):
    char[4]  magic     = "BIGF"
    uint32   total_size
    uint32   entry_count
    uint32   header_size       (offset to first file payload)
    Entry[entry_count]:
        uint32 offset
        uint32 size
        char[] name              NUL-terminated, NOT padded
"""
from __future__ import annotations

import mmap
import struct
from dataclasses import dataclass
from pathlib import Path


MAGIC = b"BIGF"


@dataclass(frozen=True)
class Entry:
    name: str
    offset: int
    size: int


class Archive:
    def __init__(self, path: Path, mm: mmap.mmap, entries: list[Entry]):
        self.path = path
        self._mm = mm
        self.entries = entries
        self._by_name = {e.name: e for e in entries}

    @classmethod
    def open(cls, path: str | Path) -> "Archive":
        path = Path(path)
        f = open(path, "rb")
        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
        if mm[:4] != MAGIC:
            raise ValueError(f"{path}: not a BIGF archive (got {mm[:4]!r})")
        total_size, entry_count, header_size = struct.unpack(">III", mm[4:16])
        if total_size != len(mm):
            # Some EA tools pack a header_size that omits trailing padding;
            # don't be strict about total_size matching exactly, but warn-worthy.
            pass
        entries: list[Entry] = []
        cursor = 16
        for _ in range(entry_count):
            offset, size = struct.unpack(">II", mm[cursor:cursor + 8])
            cursor += 8
            end = mm.find(b"\x00", cursor)
            if end < 0:
                raise ValueError(f"{path}: unterminated entry name at {cursor:#x}")
            name = mm[cursor:end].decode("ascii", errors="replace")
            cursor = end + 1
            entries.append(Entry(name=name, offset=offset, size=size))
        if cursor > header_size:
            raise ValueError(
                f"{path}: entry table overran header_size "
                f"(cursor={cursor:#x}, header_size={header_size:#x})"
            )
        return cls(path, mm, entries)

    def __getitem__(self, name: str) -> bytes:
        e = self._by_name[name]
        return bytes(self._mm[e.offset:e.offset + e.size])

    def __contains__(self, name: str) -> bool:
        return name in self._by_name

    def __iter__(self):
        return iter(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def close(self) -> None:
        self._mm.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
