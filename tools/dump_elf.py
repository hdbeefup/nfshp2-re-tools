"""Print sections, symbols, and relocations of an NFSHP2 .o file.

Usage:
    python tools/dump_elf.py <file.o> [--filter PREFIX] [--max N]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nfshp2.elf_o import ElfO


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("path", type=Path)
    ap.add_argument("--filter", default="", help="only print symbols whose name starts with this")
    ap.add_argument("--max", type=int, default=80, help="max symbols to print")
    args = ap.parse_args()

    o = ElfO.open(args.path)
    print(f"{args.path}: {len(o.sections)} sections, {len(o.symbols)} symbols, {len(o.relocations)} relocations")
    print()
    print("Sections:")
    for i, s in enumerate(o.sections):
        print(f"  [{i}] {s.name:<12} type={s.type:<3} size={s.size:>9} offset={s.offset:#010x}")
    print()
    print(f"Symbols (filter={args.filter!r}, showing up to {args.max}):")
    syms = [s for s in o.symbols if s.name.startswith(args.filter)]
    print(f"  total matching: {len(syms)}")
    for s in syms[:args.max]:
        print(f"  {s.value:#010x}  size={s.size:>7}  shndx={s.shndx}  {s.name}")

    # Summary buckets
    buckets: dict[str, int] = {}
    for s in o.symbols:
        if s.name.startswith("__"):
            head = s.name.split("::", 1)[0].split(":", 1)[0]
            buckets[head] = buckets.get(head, 0) + 1
    print()
    print("Symbol prefix buckets:")
    for k, v in sorted(buckets.items(), key=lambda kv: -kv[1]):
        print(f"  {v:>5}  {k}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
