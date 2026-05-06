"""Track loader: aggregate all visible geometry from a track folder.

Given a folder like tracks/Alpine, walks:
    persist.viv :: trackg.o   (persistent base track mesh)
    persist.viv :: skyg.o     (skybox)
    levelXX/levelG.o          (level-specific decorations)
    compNN.o                  (placed scenery / buildings, in world space)

Each .o is harvested for vertex positions via the geoprim probe. Until the
EAGL index format is fully decoded, the viewer treats vertices as a point cloud.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .bigf import Archive
from .elf_o import ElfO
from .geoprim import VertexBlob, harvest_from_o


@dataclass
class TrackPiece:
    """One named drawable: corresponds to a single .o file."""
    label: str           # e.g. "trackg", "comp01", "level00.levelG"
    source: str          # filesystem path or "<viv:persist.viv:trackg.o>"
    blobs: list[VertexBlob] = field(default_factory=list)

    @property
    def vertex_count(self) -> int:
        return sum(b.count for b in self.blobs)

    def all_positions(self) -> np.ndarray:
        if not self.blobs:
            return np.zeros((0, 3), dtype=np.float32)
        return np.concatenate([b.positions for b in self.blobs], axis=0)

    def all_colors(self) -> np.ndarray:
        if not self.blobs:
            return np.zeros((0,), dtype=np.uint32)
        return np.concatenate([b.colors for b in self.blobs], axis=0)


@dataclass
class Track:
    folder: Path
    pieces: list[TrackPiece] = field(default_factory=list)

    @property
    def total_vertices(self) -> int:
        return sum(p.vertex_count for p in self.pieces)

    def aabb(self) -> tuple[np.ndarray, np.ndarray]:
        all_pos = np.concatenate(
            [p.all_positions() for p in self.pieces if p.vertex_count],
            axis=0,
        ) if self.pieces else np.zeros((0, 3), dtype=np.float32)
        if all_pos.shape[0] == 0:
            return np.zeros(3, dtype=np.float32), np.zeros(3, dtype=np.float32)
        return all_pos.min(axis=0), all_pos.max(axis=0)


def load_track(folder: str | Path, level: str = "level00", min_run: int = 8) -> Track:
    folder = Path(folder)
    track = Track(folder=folder)

    persist = folder / "persist.viv"
    if persist.exists():
        with Archive.open(persist) as ar:
            for inner_name in ("trackg.o", "skyg.o"):
                if inner_name in ar:
                    blob = ar[inner_name]
                    o = ElfO(persist, blob)
                    pieces, _stats = harvest_from_o(o, min_run=min_run)
                    track.pieces.append(TrackPiece(
                        label=Path(inner_name).stem,
                        source=f"<viv:{persist.name}:{inner_name}>",
                        blobs=pieces,
                    ))

    level_dir = folder / level
    levelg = level_dir / "levelG.o"
    if levelg.exists():
        o = ElfO.open(levelg)
        pieces, _ = harvest_from_o(o, min_run=min_run)
        track.pieces.append(TrackPiece(
            label=f"{level}.levelG",
            source=str(levelg),
            blobs=pieces,
        ))

    for comp_path in sorted(folder.glob("comp*.o")):
        o = ElfO.open(comp_path)
        pieces, _ = harvest_from_o(o, min_run=min_run)
        track.pieces.append(TrackPiece(
            label=comp_path.stem,
            source=str(comp_path),
            blobs=pieces,
        ))

    return track
