"""Extract a BIGF/VIV archive to a directory.

Usage:
    python tools/extract_viv.py <archive.viv> [-o <out_dir>] [--list]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfshp2.bigf import Archive


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("archive", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None,
                    help="output directory (default: <archive>.extracted/)")
    ap.add_argument("--list", action="store_true", help="list entries, don't extract")
    args = ap.parse_args()

    with Archive.open(args.archive) as ar:
        if args.list:
            print(f"{args.archive}: {len(ar)} entries")
            for e in ar:
                print(f"  {e.offset:#010x}  {e.size:>10}  {e.name}")
            return 0

        out = args.out or args.archive.with_suffix(args.archive.suffix + ".extracted")
        out.mkdir(parents=True, exist_ok=True)
        for e in ar:
            (out / e.name).write_bytes(ar[e.name])
            print(f"  wrote {e.name}  ({e.size} bytes)")
        print(f"Extracted {len(ar)} entries to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
