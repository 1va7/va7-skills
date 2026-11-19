#!/usr/bin/env python3
"""Install va7-skills onto an Antry bot with `antry skills push`.

Antry caps each pushed skill at roughly 93KB of raw file bytes. This script
stages every skill under skills/ into a temp dir, drops tests/ and caches, and
when a skill is still over the cap it gzips its largest Python scripts and
leaves a tiny stub with the same filename. The stub decompresses and executes
the original in its own module namespace, so `python3 x.py`, `import x` and
`Path(__file__)`-relative paths keep working unchanged.

Usage (run inside the Antry sandbox, as the bot's admin):
  python3 scripts/antry_install.py --bot <bot>            # push all skills
  python3 scripts/antry_install.py --bot <bot> --dry-run  # only show sizes
  python3 scripts/antry_install.py --bot <bot> --only va7-library va7-script
"""
from __future__ import annotations

import argparse
import gzip
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

LIMIT = 90 * 1024  # stay under the ~93KB cap measured on 2026-11-19
REPO = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"tests", "__pycache__", ".git"}

STUB = '''"""Stub: the real script is {gz} (gzipped to fit the Antry skill size cap)."""
import gzip as _gz
from pathlib import Path as _P
exec(compile(_gz.decompress((_P(__file__).parent / "{gz}").read_bytes()), __file__, "exec"))
'''


def size(d: Path) -> int:
    return sum(p.stat().st_size for p in d.rglob("*") if p.is_file())


def stage(src: Path, dst: Path) -> list[str]:
    shutil.copytree(src, dst, ignore=lambda _d, names: [n for n in names if n in SKIP_DIRS])
    packed = []
    for py in sorted(dst.rglob("*.py"), key=lambda p: p.stat().st_size, reverse=True):
        if size(dst) <= LIMIT:
            break
        gz = py.with_name(py.name + ".gz")
        gz.write_bytes(gzip.compress(py.read_bytes(), 9))
        py.write_text(STUB.format(gz=gz.name), encoding="utf-8")
        packed.append(str(py.relative_to(dst)))
    return packed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bot", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    skills = sorted(p for p in (REPO / "skills").iterdir() if (p / "SKILL.md").exists())
    if a.only:
        skills = [p for p in skills if p.name in a.only]
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        for src in skills:
            dst = Path(tmp) / src.name
            packed = stage(src, dst)
            kb = size(dst) / 1024
            note = f"（压缩 {len(packed)} 个脚本）" if packed else ""
            if size(dst) > LIMIT:
                print(f"✗ {src.name}: {kb:.0f}KB 仍超上限，跳过{note}")
                failed.append(src.name)
                continue
            if a.dry_run:
                print(f"· {src.name}: {kb:.0f}KB{note}")
                continue
            r = subprocess.run(["antry", "skills", "push", str(dst), "--bot", a.bot], capture_output=True, text=True)
            out = (r.stdout + r.stderr).strip().splitlines()
            ok = r.returncode == 0 and out and "已上架" in out[-1]
            print(f"{'✓' if ok else '✗'} {src.name}: {kb:.0f}KB{note} — {out[-1] if out else r.returncode}")
            if not ok:
                failed.append(src.name)
    if failed:
        print("未装上：" + "、".join(failed), file=sys.stderr)
        return 1
    print("（dry-run，未上架）" if a.dry_run else "全部上架。下一条消息起生效；用封面技能前先跑 va7-cover-tools/scripts/cover_assets.py ensure。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
