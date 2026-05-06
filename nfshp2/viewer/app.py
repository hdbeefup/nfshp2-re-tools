"""moderngl + glfw freecam viewer for an NFSHP2 track.

Controls:
    Mouse drag (right button) ─ look around
    W/A/S/D                    ─ move (XZ)
    Space / Ctrl               ─ up / down
    Shift                      ─ sprint (10x)
    Mouse wheel                ─ adjust speed
    P                          ─ toggle point size (1 / 3 / 5 px)
    R                          ─ recenter on track AABB
    Esc                        ─ quit

Renders harvested vertex blobs as a coloured point cloud. Each TrackPiece gets
a different hue so you can distinguish trackg / skyg / levelG / comp01..32 at a
glance. The per-vertex color from the .o file is *also* available but currently
ignored — track world geometry is mostly white (0xFFFFFFFF) and would render as
solid white with no shape distinction.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import glfw
import moderngl
import numpy as np
from pyrr import Matrix44

from ..track import Track


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
void main() {
    frag = vec4(v_color, 1.0);
}
"""


# Distinct hue palette (HSV → RGB, evenly spaced) used to colour-code pieces.
def _palette(n: int) -> np.ndarray:
    import colorsys
    out = np.zeros((n, 3), dtype=np.float32)
    for i in range(n):
        h = (i * 0.61803398875) % 1.0  # golden-ratio for good spread
        r, g, b = colorsys.hsv_to_rgb(h, 0.55, 0.95)
        out[i] = (r, g, b)
    return out


class Viewer:
    def __init__(self, track: Track, width: int = 1280, height: int = 800):
        self.track = track
        if not glfw.init():
            raise RuntimeError("glfw init failed")
        glfw.window_hint(glfw.CONTEXT_VERSION_MAJOR, 3)
        glfw.window_hint(glfw.CONTEXT_VERSION_MINOR, 3)
        glfw.window_hint(glfw.OPENGL_PROFILE, glfw.OPENGL_CORE_PROFILE)
        glfw.window_hint(glfw.OPENGL_FORWARD_COMPAT, True)
        title = f"NFSHP2 Map Viewer — {track.folder.name} ({track.total_vertices} verts)"
        self.win = glfw.create_window(width, height, title, None, None)
        if not self.win:
            glfw.terminate()
            raise RuntimeError("could not create glfw window")
        glfw.make_context_current(self.win)
        glfw.swap_interval(1)
        self.ctx = moderngl.create_context()
        self.ctx.enable(moderngl.PROGRAM_POINT_SIZE | moderngl.DEPTH_TEST)

        self.prog = self.ctx.program(vertex_shader=VERT_SHADER, fragment_shader=FRAG_SHADER)
        self.u_mvp = self.prog["mvp"]
        self.u_point_size = self.prog["point_size"]

        self._build_buffers()

        # Camera state — fit to AABB
        amin, amax = track.aabb()
        self.center = (amin + amax) * 0.5
        size = float(np.linalg.norm(amax - amin))
        self.cam_pos = self.center + np.array([0.0, size * 0.4, size * 0.7], dtype=np.float32)
        self.yaw = -np.pi / 2  # facing -z
        self.pitch = -0.4
        self.speed = max(size * 0.05, 5.0)
        self.point_size = 3.0

        # Input state
        self._last_mouse = None
        self._dragging = False
        self._keys: set[int] = set()
        self._point_size_idx = 1
        self._point_sizes = (1.0, 3.0, 5.0, 8.0)

        glfw.set_key_callback(self.win, self._on_key)
        glfw.set_mouse_button_callback(self.win, self._on_button)
        glfw.set_cursor_pos_callback(self.win, self._on_cursor)
        glfw.set_scroll_callback(self.win, self._on_scroll)
        glfw.set_framebuffer_size_callback(self.win, self._on_resize)

    def _build_buffers(self):
        palette = _palette(len(self.track.pieces))
        positions: list[np.ndarray] = []
        colors: list[np.ndarray] = []
        for i, piece in enumerate(self.track.pieces):
            pos = piece.all_positions()
            if pos.shape[0] == 0:
                continue
            positions.append(pos)
            col = np.tile(palette[i], (pos.shape[0], 1))
            colors.append(col.astype(np.float32))

        if positions:
            all_pos = np.concatenate(positions, axis=0)
            all_col = np.concatenate(colors, axis=0)
        else:
            all_pos = np.zeros((1, 3), dtype=np.float32)
            all_col = np.zeros((1, 3), dtype=np.float32)

        self.vbo_pos = self.ctx.buffer(all_pos.tobytes())
        self.vbo_col = self.ctx.buffer(all_col.tobytes())
        self.vao = self.ctx.vertex_array(
            self.prog,
            [(self.vbo_pos, "3f", "in_pos"),
             (self.vbo_col, "3f", "in_color")],
        )
        self.vertex_count = all_pos.shape[0]

    def _on_resize(self, win, w, h):
        self.ctx.viewport = (0, 0, w, h)

    def _on_key(self, win, key, scancode, action, mods):
        if action == glfw.PRESS:
            if key == glfw.KEY_ESCAPE:
                glfw.set_window_should_close(win, True)
            elif key == glfw.KEY_P:
                self._point_size_idx = (self._point_size_idx + 1) % len(self._point_sizes)
                self.point_size = self._point_sizes[self._point_size_idx]
            elif key == glfw.KEY_R:
                amin, amax = self.track.aabb()
                self.center = (amin + amax) * 0.5
                size = float(np.linalg.norm(amax - amin))
                self.cam_pos = self.center + np.array([0.0, size * 0.4, size * 0.7], dtype=np.float32)
                self.yaw = -np.pi / 2
                self.pitch = -0.4
                self.speed = max(size * 0.05, 5.0)
            self._keys.add(key)
        elif action == glfw.RELEASE:
            self._keys.discard(key)

    def _on_button(self, win, button, action, mods):
        if button == glfw.MOUSE_BUTTON_RIGHT:
            self._dragging = (action == glfw.PRESS)
            self._last_mouse = None

    def _on_cursor(self, win, x, y):
        if not self._dragging:
            self._last_mouse = (x, y)
            return
        if self._last_mouse is None:
            self._last_mouse = (x, y)
            return
        dx = x - self._last_mouse[0]
        dy = y - self._last_mouse[1]
        self._last_mouse = (x, y)
        self.yaw += dx * 0.005
        self.pitch -= dy * 0.005
        # Clamp pitch
        lim = np.pi * 0.49
        self.pitch = max(-lim, min(lim, self.pitch))

    def _on_scroll(self, win, xoff, yoff):
        factor = 1.2 if yoff > 0 else (1.0 / 1.2)
        self.speed = max(0.1, self.speed * factor)

    def _forward(self) -> np.ndarray:
        return np.array([
            np.cos(self.pitch) * np.cos(self.yaw),
            np.sin(self.pitch),
            np.cos(self.pitch) * np.sin(self.yaw),
        ], dtype=np.float32)

    def _right(self) -> np.ndarray:
        f = self._forward()
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        r = np.cross(f, up)
        n = np.linalg.norm(r)
        return r / n if n > 1e-6 else np.array([1.0, 0.0, 0.0], dtype=np.float32)

    def _step(self, dt: float):
        speed = self.speed
        if glfw.KEY_LEFT_SHIFT in self._keys or glfw.KEY_RIGHT_SHIFT in self._keys:
            speed *= 10.0
        f = self._forward()
        r = self._right()
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        if glfw.KEY_W in self._keys: self.cam_pos += f * speed * dt
        if glfw.KEY_S in self._keys: self.cam_pos -= f * speed * dt
        if glfw.KEY_D in self._keys: self.cam_pos += r * speed * dt
        if glfw.KEY_A in self._keys: self.cam_pos -= r * speed * dt
        if glfw.KEY_SPACE in self._keys: self.cam_pos += up * speed * dt
        if glfw.KEY_LEFT_CONTROL in self._keys or glfw.KEY_RIGHT_CONTROL in self._keys:
            self.cam_pos -= up * speed * dt

    def _mvp(self, w: int, h: int) -> np.ndarray:
        f = self._forward()
        eye = self.cam_pos
        target = eye + f
        up = np.array([0.0, 1.0, 0.0], dtype=np.float32)
        view = Matrix44.look_at(eye, target, up, dtype=np.float32)
        amin, amax = self.track.aabb()
        diag = float(np.linalg.norm(amax - amin))
        far = max(diag * 4.0, 50000.0)
        proj = Matrix44.perspective_projection(60.0, w / max(h, 1), 0.5, far, dtype=np.float32)
        return (proj * view).astype(np.float32)

    def run(self):
        last = time.time()
        while not glfw.window_should_close(self.win):
            now = time.time()
            dt = now - last
            last = now
            self._step(dt)
            w, h = glfw.get_framebuffer_size(self.win)
            self.ctx.viewport = (0, 0, w, h)
            self.ctx.clear(0.05, 0.06, 0.08, 1.0, depth=1.0)
            mvp = self._mvp(w, h)
            self.u_mvp.write(mvp.tobytes())
            self.u_point_size.value = self.point_size
            self.vao.render(mode=moderngl.POINTS, vertices=self.vertex_count)
            glfw.swap_buffers(self.win)
            glfw.poll_events()
        glfw.terminate()


def run(track: Track):
    Viewer(track).run()
