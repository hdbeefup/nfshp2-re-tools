"""Harvest vertex data from a .o file by pattern-scanning .data.

Usage:
    python tools/probe_geoprim.py <file.o> [--obj OUT.obj] [--min-run N]

Status: harvesting works; index/topology decoding is not yet implemented. The
emitted .obj contains all detected vertex positions as a point cloud (no
faces). Useful as a smoke test for the viewer.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfshp2.elf_o import ElfO
from nfshp2.geoprim import harvest_from_o


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--obj", type=Path, default=None, help="write a Wavefront .obj point cloud")
    ap.add_argument("--min-run", type=int, default=8, help="minimum run length to accept (default 8)")
    ap.add_argument("--top", type=int, default=12, help="show top N largest blobs")
    args = ap.parse_args()

    o = ElfO.open(args.path)
    blobs, stats = harvest_from_o(o, min_run=args.min_run)

    print(f"{args.path}")
    print(f"  .data size:        {len(o.data)} bytes")
    print(f"  vertex blobs:      {stats.blob_count}")
    print(f"  total vertices:    {stats.total_vertices}")
    if stats.total_vertices:
        amin = stats.overall_aabb_min
        amax = stats.overall_aabb_max
        print(f"  AABB:              ({amin[0]:.3f}, {amin[1]:.3f}, {amin[2]:.3f}) .. "
              f"({amax[0]:.3f}, {amax[1]:.3f}, {amax[2]:.3f})")
        extent = tuple(amax[i] - amin[i] for i in range(3))
        print(f"  extent:            ({extent[0]:.3f}, {extent[1]:.3f}, {extent[2]:.3f})")

    blobs_sorted = sorted(blobs, key=lambda b: -b.count)
    print(f"\nTop {args.top} blobs by vertex count:")
    for b in blobs_sorted[:args.top]:
        amin = b.positions.min(axis=0)
        amax = b.positions.max(axis=0)
        print(f"  off={b.offset:#08x}  count={b.count:>5}  "
              f"AABB=({amin[0]:.2f},{amin[1]:.2f},{amin[2]:.2f}) .. "
              f"({amax[0]:.2f},{amax[1]:.2f},{amax[2]:.2f})")

    if args.obj:
        with args.obj.open("w") as f:
            f.write(f"# point cloud harvested from {args.path}\n")
            for b in blobs:
                for p in b.positions:
                    f.write(f"v {p[0]} {p[1]} {p[2]}\n")
        print(f"\nWrote {args.obj} ({stats.total_vertices} vertices, no faces)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
