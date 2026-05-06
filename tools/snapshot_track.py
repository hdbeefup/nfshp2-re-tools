"""Render a top-down PNG snapshot of a loaded track. Headless smoke test.

Usage:
    python tools/snapshot_track.py <track_folder> -o snap.png [--level level00]
"""
from __future__ import annotations

import argparse
import colorsys
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np
import moderngl
from PIL import Image
from pyrr import Matrix44

from nfshp2.track import load_track


VERT_SHADER = """
#version 330
in vec3 in_pos;
in vec3 in_color;
uniform mat4 mvp;
uniform float point_size;
out vec3 v_color;
void main() {
    gl_Position = mvp * vec4(in_pos, 1.0);
    gl_PointSize = point_size;
    v_color = in_color;
}
"""

FRAG_SHADER = """
#version 330
in vec3 v_color;
out vec4 frag;
void main() { frag = vec4(v_color, 1.0); }
"""


def palette(n: int) -> np.ndarray:
    out = np.zeros((n, 3), dtype=np.float32)
    for i in range(n):
        h = (i * 0.61803398875) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.55, 0.95)
        out[i] = (r, g, b)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("track", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=Path("snap.png"))
    ap.add_argument("--level", default="level00")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1200)
    ap.add_argument("--view", choices=("top", "iso"), default="top")
    ap.add_argument("--exclude", nargs="*", default=[],
                    help="piece labels to skip (e.g. --exclude skyg)")
    args = ap.parse_args()

    track = load_track(args.track, level=args.level)
    print(f"loaded {len(track.pieces)} pieces, {track.total_vertices} verts")

    pieces = [p for p in track.pieces if p.label not in args.exclude]
    excluded = track.total_vertices - sum(p.vertex_count for p in pieces)
    if excluded:
        print(f"  excluded {excluded} verts ({args.exclude})")

    # Build vertex buffer
    pal = palette(len(pieces))
    pos_chunks = []
    col_chunks = []
    for i, p in enumerate(pieces):
        pos = p.all_positions()
        if pos.shape[0] == 0:
            continue
        pos_chunks.append(pos)
        col_chunks.append(np.tile(pal[i], (pos.shape[0], 1)).astype(np.float32))
    all_pos = np.concatenate(pos_chunks, axis=0)
    all_col = np.concatenate(col_chunks, axis=0)

    # Headless context
    ctx = moderngl.create_standalone_context(require=330)
    ctx.enable(moderngl.DEPTH_TEST | moderngl.PROGRAM_POINT_SIZE)
    prog = ctx.program(vertex_shader=VERT_SHADER, fragment_shader=FRAG_SHADER)
    vbo_pos = ctx.buffer(all_pos.tobytes())
    vbo_col = ctx.buffer(all_col.tobytes())
    vao = ctx.vertex_array(
        prog,
        [(vbo_pos, "3f", "in_pos"), (vbo_col, "3f", "in_color")],
    )

    # Camera fits AABB of the visible pieces only.
    amin = all_pos.min(axis=0)
    amax = all_pos.max(axis=0)
    center = (amin + amax) * 0.5
    extent = float(np.linalg.norm(amax - amin))
    if args.view == "top":
        eye = center + np.array([0.0, max(amax[1], 1) + extent * 0.4, 0.001], dtype=np.float32)
        up = np.array([0.0, 0.0, -1.0], dtype=np.float32)
    else:
        eye = center + np.array([extent * 0.5, extent * 0.4, extent * 0.5], dtype=np.float32)
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    view = Matrix44.look_at(eye, center, up, dtype=np.float32)
    proj = Matrix44.perspective_projection(50.0, args.width / args.height, 1.0, extent * 4.0, dtype=np.float32)
    mvp = (proj * view).astype(np.float32)
    prog["mvp"].write(mvp.tobytes())
    prog["point_size"].value = 2.0

    # Framebuffer
    color = ctx.texture((args.width, args.height), 4)
    depth = ctx.depth_renderbuffer((args.width, args.height))
    fbo = ctx.framebuffer(color_attachments=[color], depth_attachment=depth)
    fbo.use()
    ctx.viewport = (0, 0, args.width, args.height)
    ctx.clear(0.05, 0.06, 0.08, 1.0, depth=1.0)
    vao.render(mode=moderngl.POINTS, vertices=all_pos.shape[0])

    # Read back
    raw = fbo.read(components=4)
    img = Image.frombytes("RGBA", (args.width, args.height), raw).transpose(Image.FLIP_TOP_BOTTOM)
    img.save(args.out)
    print(f"wrote {args.out}  {img.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
