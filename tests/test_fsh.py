"""Tests for FSH/SHPI parser."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfshp2.fsh import FshFile, TYPE_DXT1, TYPE_DXT3

GAME_ROOT = Path(__file__).resolve().parents[2]
LEVEL_FSH = GAME_ROOT / "tracks" / "Alpine" / "level00" / "level.fsh"


def test_level_fsh_directory():
    fsh = FshFile.open(LEVEL_FSH)
    assert fsh.tag == b"G335"
    assert len(fsh.entries) == 20
    e0 = fsh.entries[0]
    assert e0.name == "0000"
    assert e0.primary.width == 32
    assert e0.primary.height == 64
    assert e0.primary.type == TYPE_DXT1


def test_level_fsh_decode_first():
    fsh = FshFile.open(LEVEL_FSH)
    img = fsh.to_image(fsh.entries[0])
    assert img.size == (32, 64)
    assert img.mode == "RGBA"


def test_level_fsh_decode_all():
    fsh = FshFile.open(LEVEL_FSH)
    failed = []
    for e in fsh.entries:
        try:
            img = fsh.to_image(e)
            assert img.size == (e.primary.width, e.primary.height)
        except Exception as ex:
            failed.append((e.name, str(ex)))
    assert not failed, failed


if __name__ == "__main__":
    test_level_fsh_directory()
    test_level_fsh_decode_first()
    test_level_fsh_decode_all()
    print("OK")
