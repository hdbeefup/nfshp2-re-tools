"""EAGL geoprimitive harvester.

Status: partial. The full EAGL geoprimdatabuffer struct layout (vertex count,
index count, primitive type, stride descriptor) is not yet fully decoded. What
we DO know after probing tracks/Alpine/level00/levelG.o:

    1. Vertex data is stored inline in the .data section, in regions following
       __RenderMethod:::__GPRenderMethod_* symbols.
    2. The vertex format observed is 24-byte stride:
            float[3]  position    (typically in [-1, +1] in local space)
            uint32    color       (RGBA8, often 0xFFFFFFFF)
            float[2]  uv
    3. Each RenderMethod block has a ~220-byte header of small ints, then
       the vertex blob, then trailing data (probably indices, stride and count
       not yet pinned down).
    4. Vertices are local-space; per-Model transforms (in __Model symbols) are
       expected to place them in world space — also not yet decoded.

For v1 we harvest vertex positions by pattern scanning so the viewer can draw a
point cloud. Triangle topology will be approximated by treating consecutive
triples as triangles (incorrect, but renders something).
"""
from __future__ import annotations

import math
import struct
from dataclasses import dataclass
from typing import Iterable

import numpy as np

from .elf_o import ElfO


VERTEX_STRIDE = 24
POS_RANGE = 50_000.0  # plausible world-coordinate magnitude


@dataclass
class VertexBlob:
    """One run of stride-24 vertices found in .data."""
    offset: int            # offset within .data
    count: int
    positions: np.ndarray  # (N, 3) float32
    colors: np.ndarray     # (N,) uint32
    uvs: np.ndarray        # (N, 2) float32


def _is_plausible_vertex(pos: tuple[float, float, float], uv: tuple[float, float]) -> bool:
    for v in pos:
        if math.isnan(v) or math.isinf(v):
            return False
        if abs(v) > POS_RANGE:
            return False
        # Reject denormals (often misalignment artifacts).
        if v != 0 and abs(v) < 1e-20:
            return False
    if all(v == 0 for v in pos):
        # All-zero position is suspicious; usually indicates we walked into padding.
        return False
    for v in uv:
        if math.isnan(v) or math.isinf(v):
            return False
        if abs(v) > 100.0:
            return False
    return True


def harvest_vertices(data: bytes, min_run: int = 4) -> list[VertexBlob]:
    """Scan .data for stride-24 vertex runs; return all blobs >= min_run vertices.

    The scanner walks every 4-byte alignment, attempts to read consecutive
    24-byte vertices that satisfy the plausibility test, and records the longest
    contiguous run starting at each candidate offset. Overlapping runs are
    deduplicated by keeping the longest one rooted at the lowest offset.
    """
    blobs: list[VertexBlob] = []
    i = 0
    n = len(data)
    while i + VERTEX_STRIDE <= n:
        # Try to read a vertex at i.
        pos = struct.unpack_from("<3f", data, i)
        uv = struct.unpack_from("<2f", data, i + 16)
        if _is_plausible_vertex(pos, uv):
            # Walk forward as far as we can.
            cur = i
            run_pos = []
            run_col = []
            run_uv = []
            while cur + VERTEX_STRIDE <= n:
                p = struct.unpack_from("<3f", data, cur)
                u = struct.unpack_from("<2f", data, cur + 16)
                if not _is_plausible_vertex(p, u):
                    break
                c = struct.unpack_from("<I", data, cur + 12)[0]
                run_pos.append(p)
                run_col.append(c)
                run_uv.append(u)
                cur += VERTEX_STRIDE
            run_len = len(run_pos)
            if run_len >= min_run:
                blobs.append(VertexBlob(
                    offset=i,
                    count=run_len,
                    positions=np.array(run_pos, dtype=np.float32),
                    colors=np.array(run_col, dtype=np.uint32),
                    uvs=np.array(run_uv, dtype=np.float32),
                ))
                i = cur  # skip past this run
                continue
        i += 4
    return blobs


@dataclass
class HarvestStats:
    blob_count: int
    total_vertices: int
    overall_aabb_min: tuple[float, float, float]
    overall_aabb_max: tuple[float, float, float]


def harvest_from_o(o: ElfO, min_run: int = 4) -> tuple[list[VertexBlob], HarvestStats]:
    blobs = harvest_vertices(o.data, min_run=min_run)
    if not blobs:
        return blobs, HarvestStats(0, 0, (0, 0, 0), (0, 0, 0))
    all_pos = np.concatenate([b.positions for b in blobs], axis=0)
    return blobs, HarvestStats(
        blob_count=len(blobs),
        total_vertices=int(all_pos.shape[0]),
        overall_aabb_min=tuple(map(float, all_pos.min(axis=0))),
        overall_aabb_max=tuple(map(float, all_pos.max(axis=0))),
    )
