"""ELF .o parser for NFSHP2 EAGL asset containers.

These files use ELF as a container shell:
    e_ident:    7F 45 4C 46 01 01 01 ..    (ELFCLASS32, ELFDATA2LSB)
    e_type:     ET_REL (1)
    e_machine:  EM_MIPS (8)

Sections (consistent across the corpus):
    [0] (NULL)
    [1] .data       PROGBITS   ← geometry, render methods, models, all live here
    [2] .shstrtab   STRTAB
    [3] .strtab     STRTAB
    [4] .symtab     SYMTAB     ← named pointers into .data
    [5] .rel.data   REL        ← MIPS relocations within .data

Symbol names of interest (mangled C++):
    __geoprimdatabuffer_*       — the actual vertex/index buffers
    __Model::*                  — model/group nodes
    __BBOX::*                   — axis-aligned bounding boxes (6 floats)
    __RenderMethod:::*          — shader/render state
    __EAGL::TAR:::tar_*         — EA Asset Resource (TAR) entries
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path


ELF_MAGIC = b"\x7fELF"

# ELF header offsets / constants
EI_CLASS = 4   # 1=ELF32
EI_DATA = 5    # 1=little-endian

ET_REL = 1
EM_MIPS = 8

# Section types
SHT_NULL = 0
SHT_PROGBITS = 1
SHT_SYMTAB = 2
SHT_STRTAB = 3
SHT_REL = 9
SHT_NOBITS = 8


@dataclass
class Section:
    name: str
    type: int
    flags: int
    addr: int
    offset: int
    size: int
    link: int
    info: int
    addralign: int
    entsize: int
    raw: bytes  # bytes from file at [offset:offset+size] (or empty for SHT_NOBITS)


@dataclass
class Symbol:
    name: str
    value: int          # offset within target section (typically .data)
    size: int
    info: int           # bind << 4 | type
    other: int
    shndx: int          # section index this symbol belongs to


@dataclass
class Relocation:
    offset: int     # offset within target section where relocation is applied
    info: int       # high 24 bits = symbol index, low 8 bits = relocation type
    type: int
    sym: int


class ElfO:
    def __init__(self, path: Path, blob: bytes):
        self.path = path
        self.blob = blob
        self._parse()

    @classmethod
    def open(cls, path: str | Path) -> "ElfO":
        path = Path(path)
        return cls(path, path.read_bytes())

    def _parse(self) -> None:
        b = self.blob
        if b[:4] != ELF_MAGIC:
            raise ValueError(f"{self.path}: not ELF (got {b[:4]!r})")
        if b[EI_CLASS] != 1 or b[EI_DATA] != 1:
            raise ValueError(f"{self.path}: expected ELF32 LE")

        # 32-bit ELF header (52 bytes)
        (e_type, e_machine, e_version, e_entry, e_phoff, e_shoff,
         e_flags, e_ehsize, e_phentsize, e_phnum,
         e_shentsize, e_shnum, e_shstrndx) = struct.unpack("<HHIIIIIHHHHHH", b[16:52])

        if e_type != ET_REL or e_machine != EM_MIPS:
            # Not strictly required, but flag deviations from observed corpus.
            pass
        if e_shentsize != 40:
            raise ValueError(f"unexpected e_shentsize {e_shentsize}")

        # Read section headers
        raw_sections = []
        for i in range(e_shnum):
            o = e_shoff + i * e_shentsize
            (sh_name, sh_type, sh_flags, sh_addr, sh_offset,
             sh_size, sh_link, sh_info, sh_addralign, sh_entsize) = struct.unpack(
                "<IIIIIIIIII", b[o:o + 40])
            raw_sections.append({
                "name_idx": sh_name, "type": sh_type, "flags": sh_flags,
                "addr": sh_addr, "offset": sh_offset, "size": sh_size,
                "link": sh_link, "info": sh_info, "addralign": sh_addralign,
                "entsize": sh_entsize,
            })

        # Section name string table
        if e_shstrndx >= len(raw_sections):
            raise ValueError("invalid e_shstrndx")
        shstr_sec = raw_sections[e_shstrndx]
        shstr_blob = b[shstr_sec["offset"]:shstr_sec["offset"] + shstr_sec["size"]]

        def cstring(blob: bytes, off: int) -> str:
            end = blob.find(b"\x00", off)
            return blob[off:end].decode("ascii", errors="replace") if end >= 0 else ""

        self.sections: list[Section] = []
        for rs in raw_sections:
            name = cstring(shstr_blob, rs["name_idx"])
            raw = b[rs["offset"]:rs["offset"] + rs["size"]] if rs["type"] != SHT_NOBITS else b""
            self.sections.append(Section(
                name=name, type=rs["type"], flags=rs["flags"], addr=rs["addr"],
                offset=rs["offset"], size=rs["size"], link=rs["link"], info=rs["info"],
                addralign=rs["addralign"], entsize=rs["entsize"], raw=raw,
            ))

        self.section_by_name: dict[str, Section] = {s.name: s for s in self.sections}

        # Symbol table
        sym_sec = self.section_by_name.get(".symtab")
        if sym_sec is None:
            self.symbols = []
            self.data = b""
            self.relocations = []
            return

        str_sec = self.sections[sym_sec.link]
        str_blob = str_sec.raw

        symbols: list[Symbol] = []
        for o in range(0, sym_sec.size, 16):
            (st_name, st_value, st_size, st_info, st_other, st_shndx) = struct.unpack(
                "<IIIBBH", sym_sec.raw[o:o + 16])
            symbols.append(Symbol(
                name=cstring(str_blob, st_name),
                value=st_value, size=st_size, info=st_info, other=st_other,
                shndx=st_shndx,
            ))
        self.symbols = symbols

        # .data convenience handle
        data_sec = self.section_by_name.get(".data")
        self.data = data_sec.raw if data_sec else b""

        # Relocations
        self.relocations: list[Relocation] = []
        for sec in self.sections:
            if sec.type == SHT_REL and sec.size:
                for o in range(0, sec.size, 8):
                    r_offset, r_info = struct.unpack("<II", sec.raw[o:o + 8])
                    self.relocations.append(Relocation(
                        offset=r_offset, info=r_info,
                        type=r_info & 0xff, sym=r_info >> 8,
                    ))

    # Convenience queries
    def symbols_by_prefix(self, prefix: str) -> list[Symbol]:
        return [s for s in self.symbols if s.name.startswith(prefix)]

    def read(self, sym: Symbol) -> bytes:
        """Read the bytes a .data-resident symbol points at."""
        sec_idx = sym.shndx
        if sec_idx == 0 or sec_idx >= len(self.sections):
            return b""
        sec = self.sections[sec_idx]
        return sec.raw[sym.value:sym.value + sym.size]
