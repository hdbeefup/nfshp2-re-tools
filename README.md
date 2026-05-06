# NFS Hot Pursuit 2 — Map Viewer (v1)

Standalone Python toolkit for inspecting Need For Speed: Hot Pursuit 2 (PC, 2002,
EA Black Box) track files: `tracks/<TrackName>/...`. Ships an interactive freecam
viewer that renders the track as a colour-coded point cloud, plus a set of CLI
extractors for the underlying file formats.

## Status

| Area                                | State    | Notes |
|-------------------------------------|----------|-------|
| BIGF / `.viv` archive               | working  | Round-trip read; tested against `comp01.viv` |
| SHPI / `.fsh` textures              | working  | DXT1, DXT3, ARGB32 decoded; palettised (0x7B) tested only on small placeholders |
| ELF / `.o` container                | working  | Sections, symbols, relocations all parsed |
| EAGL geoprim vertex extraction      | partial  | Vertex positions/colors/UVs harvested by stride-24 pattern scan |
| EAGL geoprim **index** extraction   | unsolved | Triangle topology not yet decoded — viewer shows points, not surfaces |
| Per-Model transforms                | unsolved | World coords come straight from `.data`; comp/track meshes happen to already be world-space |
| Texture binding to geometry         | unsolved | FSH parser ships separately; nothing applies textures yet |

## Quickstart

```powershell
# install deps (one-time)
python -m pip install moderngl glfw pyrr numpy pillow

# extract a VIV archive
python tools/extract_viv.py ../tracks/Alpine/comp01.viv

# dump an FSH archive to PNGs
python tools/dump_fsh.py ../tracks/Alpine/level00/level.fsh

# inspect a .o symbol table
python tools/dump_elf.py ../tracks/Alpine/level00/levelG.o --filter __geoprim

# harvest vertices from a .o
python tools/probe_geoprim.py ../tracks/Alpine/comp01.o

# render a top-down PNG of a whole track (headless)
python tools/snapshot_track.py ../tracks/Alpine -o alpine_top.png --view top --exclude skyg

# open the interactive viewer
python tools/view_track.py ../tracks/Alpine
```

Viewer controls: right-drag to look, WASD/space/ctrl to fly, shift = sprint,
mouse wheel adjusts speed, P toggles point size, R recenters, Esc quits.

## What's in a track folder

```
tracks/<Name>/
  persist.viv              ← BIGF archive: trackg.o + skyg.o + persistent FSH
  level00/                 ← variant 0 of the level
    levelG.o               ← level-specific extra geometry (small)
    level.fsh              ← level-specific textures
    aipaths.dat, drvpath.ini, lighting.ini   (not consumed yet)
  level01/ … level05/      ← additional level variants (career mode etc.)
  comp01.o … comp32.o      ← placed scenery / road segments (world-space)
  comp01.viv … compNN.viv  ← per-comp particles + textures
  *.bnk, *.fsh             ← audio + ambient textures (not consumed yet)
```

`tracks.ini` and `surface.ini` (one level up) describe per-track gameplay tuning.

## File-format notes

### BIGF / VIV (trivial)

Big-endian header `BIGF` + uint32 size + uint32 entry count + uint32 header size,
then a packed table of `(uint32 offset, uint32 size, NUL-terminated name)`.
NFSHP2 doesn't compress, doesn't pad — names are immediately concatenated.

### SHPI / FSH (mostly trivial)

Little-endian header `SHPI` + uint32 size + uint32 count + 4-char tag (always
`G335` in this corpus). Directory entries are `(4-char name, uint32 offset)`.
Each entry points at a chain of 16-byte-headed records that ends at the next
directory offset. NFSHP2 uses four record types only (surveyed across 137
archives):

| Code | Meaning                | Count | Decode |
|------|------------------------|-------|--------|
| 0x60 | DXT1 (BC1)             | 748   | Pillow's BCn decoder, mode=1 |
| 0x61 | DXT3 (BC2)             | 511   | Pillow's BCn decoder, mode=2 |
| 0x7B | 8-bit palettised       | 113   | Index payload + sibling 0x2A palette |
| 0x7D | 32-bit ARGB (BGRA wire)| 30    | Raw `BGRA` reorder |

After each main record, the chain typically continues with a 0x69 metadata
block we ignore.

### ELF .o (used as a container, not code)

Standard ELF32 little-endian, but with `e_machine = EM_MIPS` even though the
PC executable is x86. The ELF format is being repurposed as a labelled binary
container — the runtime parser walks the symbol table, not the program headers.
Every file in this corpus has exactly six sections: `(NULL)`, `.data`,
`.shstrtab`, `.strtab`, `.symtab`, `.rel.data`. All assets live in `.data`.

Symbol prefixes that matter:

| Prefix                                 | Role |
|----------------------------------------|------|
| `__geoprimdatabuffer_<i>_<n>`          | Geoprim descriptor (header + render state) |
| `__RenderMethod:::__GPRenderMethod_*`  | Shader/render-state block, with vertex blob inline |
| `__Model::*`                           | Model node — transform + child geoprim refs |
| `__BBOX::*`                            | Axis-aligned bounding box (6 floats) |
| `__EAGL::TAR:::tar_*`                  | EA Asset Resource (texture/material binding) |

All defined symbols have `st_size = 4` (not the actual struct size — the linker
recorded only the first slot). To bound a struct's extent we use the next
defined symbol's address.

### EAGL geoprim (partially decoded)

Each `__RenderMethod` block contains, in order:

1. ~220 bytes of small-int header. The vertex count appears at `+0x88` of the
   block (verified for one buffer where this was 192 = the actual run length).
2. A vertex blob with **24-byte stride**: `float3 position` + `uint32 color (RGBA8)`
   + `float2 uv`.
3. Trailing data that should be index buffer + topology info, but its encoding
   is unsolved — the values don't bound to the vertex count for any obvious
   stride/format combination.

The viewer's geoprim harvester (`nfshp2/geoprim.py`) walks `.data` looking for
runs of plausible 24-byte vertices (position magnitude bounded, UVs bounded,
no NaN). This recovers the world-space vertices of `comp*.o` correctly without
needing to interpret the descriptor at all. It misses any geometry stored under
a different stride or with positions that look like garbage to the heuristic.

### What we don't decode yet

- Triangle indices / strip topology (`.o` trailing data after each vertex blob).
- Per-Model transforms — `__Model::*` symbols hold what looks like a 4×3 matrix
  + child pointers, but the schema isn't pinned down. Not needed for `comp*.o`
  (already world-space), critical for sub-meshes inside `levelG.o` that live in
  local space.
- The link from `__EAGL::TAR` to a specific FSH entry name (so meshes can be
  textured).
- `aipaths.dat`, `drvpath.ini` (AI/driving paths).
- Audio (`.bnk`).

If you want to push topology decoding further: the practical next step is
to load `nfshp2.exe` into Ghidra, find the parser by string-cross-ref on
`__geoprimdatabuffer`, and walk the call site that consumes the `RenderMethod`
descriptor. Alternatively, `EAGL/eaglrm.o` is itself an asset .o — its
`__RenderMethod` definitions might describe the canonical shader-input layout
for every vertex format the engine supports.

## Layout

```
re-tools/
  nfshp2/
    bigf.py        # BIGF/VIV archive
    fsh.py         # SHPI/FSH textures
    elf_o.py       # ELF .o container
    geoprim.py     # EAGL vertex harvester (partial)
    track.py       # Aggregates a whole track's drawables
    viewer/app.py  # moderngl + glfw freecam window
  tools/
    extract_viv.py
    dump_fsh.py
    dump_elf.py
    probe_geoprim.py
    snapshot_track.py    # headless top/iso PNG
    view_track.py        # interactive
  tests/
    test_bigf.py
    test_fsh.py
    test_elf_o.py
```

Tests run as plain scripts (`python tests/test_bigf.py`); they assume the game
folder lives at `..` relative to `re-tools/`.

## Future work

1. **Decode index format.** Likely 1 day of Ghidra on `nfshp2.exe`.
2. **Texture meshes.** Once topology is solved and `__EAGL::TAR` ↔ FSH mapping
   is figured out, switch to triangle rendering with sampled FSH textures.
3. **Blender importer.** The parser core is intentionally `bpy`-free; an add-on
   can `import nfshp2.track` and emit Blender meshes once topology lands.
