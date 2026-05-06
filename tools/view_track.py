"""Open the moderngl viewer on a track folder.

Usage:
    python tools/view_track.py <track_folder> [--level level00]

Status: renders harvested vertex positions as a colour-coded point cloud.
Triangle topology is not yet decoded from the EAGL geoprim format; expect to
see the track silhouette and prop placement, not solid surfaces.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfshp2.track import load_track
from nfshp2.viewer.app import run as run_viewer


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("track", type=Path)
    ap.add_argument("--level", default="level00")
    ap.add_argument("--min-run", type=int, default=8)
    args = ap.parse_args()

    print(f"loading {args.track} ...")
    t0 = time.time()
    track = load_track(args.track, level=args.level, min_run=args.min_run)
    elapsed = time.time() - t0
    amin, amax = track.aabb()
    print(f"  loaded {len(track.pieces)} pieces, {track.total_vertices} vertices in {elapsed:.1f}s")
    print(f"  AABB ({amin[0]:.1f}, {amin[1]:.1f}, {amin[2]:.1f}) "
          f".. ({amax[0]:.1f}, {amax[1]:.1f}, {amax[2]:.1f})")
    for p in track.pieces:
        print(f"    {p.label:<20} {p.vertex_count:>7} verts")
    print()
    print("Controls: right-drag to look, WASD/space/ctrl to fly, shift = sprint, P = point size, R = recenter, Esc = quit")

    run_viewer(track)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
