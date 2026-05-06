"""Extract FSH/SHPI textures to PNG.

Usage:
    python tools/dump_fsh.py <file.fsh> [-o <out_dir>] [--list]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfshp2.fsh import FshFile


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("fsh", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    fsh = FshFile.open(args.fsh)
    if args.list:
        print(f"{args.fsh}: tag={fsh.tag!r}, {len(fsh.entries)} entries")
        for e in fsh.entries:
            r = e.primary
            chain = ",".join(f"{rec.type:#04x}" for rec in e.records)
            print(f"  {e.name}  off={e.offset:#x}  type={r.type:#04x}  {r.width}x{r.height}  chain=[{chain}]")
        return 0

    out = args.out or args.fsh.with_suffix(".png_dir")
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for e in fsh.entries:
        try:
            img = fsh.to_image(e)
            png = out / f"{e.name}.png"
            img.save(png)
            print(f"  wrote {png.name}  ({e.primary.width}x{e.primary.height}, type={e.primary.type:#04x})")
        except Exception as ex:
            failed += 1
            print(f"  ! {e.name}: {ex}")
    print(f"Done: {len(fsh.entries) - failed}/{len(fsh.entries)} written to {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
