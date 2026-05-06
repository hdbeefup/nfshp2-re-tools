"""Tests for BIGF/VIV parser against tracks/Alpine/comp01.viv."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfshp2.bigf import Archive

GAME_ROOT = Path(__file__).resolve().parents[2]
COMP01_VIV = GAME_ROOT / "tracks" / "Alpine" / "comp01.viv"


def test_comp01_viv_entries():
    with Archive.open(COMP01_VIV) as ar:
        names = [e.name for e in ar]
        assert names == ["mesh.sim", "lightglow.dat", "particle.mpb", "particle.fsh"], names
        offsets = {e.name: e.offset for e in ar}
        assert offsets["mesh.sim"] == 0x70
        assert offsets["lightglow.dat"] == 0x104c0
        assert offsets["particle.mpb"] == 0x104d0
        assert offsets["particle.fsh"] == 0x104e0


def test_comp01_viv_payload_extraction():
    with Archive.open(COMP01_VIV) as ar:
        mesh = ar["mesh.sim"]
        assert len(mesh) == ar._by_name["mesh.sim"].size
        assert len(mesh) > 0
        fsh = ar["particle.fsh"]
        assert fsh[:4] == b"SHPI", fsh[:4]


if __name__ == "__main__":
    test_comp01_viv_entries()
    test_comp01_viv_payload_extraction()
    print("OK")
