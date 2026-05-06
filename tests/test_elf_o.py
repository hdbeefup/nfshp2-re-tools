"""Tests for ELF .o parser."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfshp2.elf_o import ElfO

GAME_ROOT = Path(__file__).resolve().parents[2]
LEVELG_O = GAME_ROOT / "tracks" / "Alpine" / "level00" / "levelG.o"
COMP01_O = GAME_ROOT / "tracks" / "Alpine" / "comp01.o"
UPLOAD_O = GAME_ROOT / "tracks" / "Alpine" / "upload.o"


def test_levelg_sections_and_symbols():
    o = ElfO.open(LEVELG_O)
    names = [s.name for s in o.sections]
    assert ".data" in names
    assert ".symtab" in names
    assert ".strtab" in names

    geo = o.symbols_by_prefix("__geoprimdatabuffer_")
    assert len(geo) >= 1, "expected at least one __geoprimdatabuffer_* symbol"
    models = o.symbols_by_prefix("__Model")
    assert len(models) >= 1, "expected at least one __Model* symbol"

    # All geoprim symbols must point inside .data
    data_size = len(o.data)
    for s in geo:
        assert 0 <= s.value < data_size, f"{s.name}: value {s.value:#x} outside .data ({data_size:#x})"
        assert s.value + s.size <= data_size, f"{s.name}: range overruns .data"


def test_comp01_o_loads():
    o = ElfO.open(COMP01_O)
    assert len(o.symbols) > 10
    assert len(o.data) > 1000


def test_upload_o_loads():
    o = ElfO.open(UPLOAD_O)
    assert len(o.symbols) >= 1


if __name__ == "__main__":
    test_levelg_sections_and_symbols()
    test_comp01_o_loads()
    test_upload_o_loads()
    print("OK")
