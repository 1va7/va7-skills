#!/usr/bin/env python3
"""Fetch the large, non-text assets of va7-video-cover-maker into a local cache.

The skill itself only ships text (SKILL.md, references, scripts) because skill
upload has a size cap. Binary assets are downloaded on first use and checked by
sha256:

- fonts/NotoSansSC-Bold.otf — official notofonts/noto-cjk release (OFL)
- cover-case-library/{published,local-previews}/ — VA7 historical covers,
  a release asset of 1va7/va7-skills (tag cover-assets-v1)

Also installs Pillow for the current user when missing.

Cache dir: $VA7_COVER_ASSETS, else ~/.cache/va7-cover-assets.

Usage:
  python3 cover_assets.py ensure     # idempotent; prints resolved paths as JSON
  python3 cover_assets.py path       # print paths without downloading
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ASSETS = Path(os.environ.get("VA7_COVER_ASSETS", "~/.cache/va7-cover-assets")).expanduser()
FONT = ASSETS / "fonts" / "NotoSansSC-Bold.otf"
CASES = ASSETS / "cover-case-library"

FONT_URL = "https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/SubsetOTF/SC/NotoSansSC-Bold.otf"
FONT_SHA256 = "c6cb5a93abaa9edc8ee7463b7ebb7f42d618d40e6ed2f7a5371c97b0b64767c0"
CASES_URL = "https://github.com/1va7/va7-skills/releases/download/cover-assets-v1/cover-case-library-v1.zip"
CASES_SHA256 = "3f69e16a1b949630e12bc7fae09d4e13970311afe9854940b70a3eba8165c473"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _download(url: str, dest: Path, sha_prefix: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url, timeout=300) as r, tmp.open("wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    if not _sha256(tmp).startswith(sha_prefix):
        tmp.unlink()
        raise SystemExit(f"下载校验失败：{url}")
    tmp.replace(dest)


def ensure_pillow() -> None:
    try:
        import PIL  # noqa: F401
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "--user", "-q", "--break-system-packages", "pillow"],
                       check=True)
        import site
        sys.path.insert(0, site.getusersitepackages())


def ensure_font() -> Path:
    if not (FONT.exists() and _sha256(FONT).startswith(FONT_SHA256)):
        _download(FONT_URL, FONT, FONT_SHA256)
    return FONT


def ensure_cases() -> Path:
    marker = CASES / ".sha256"
    if not (marker.exists() and marker.read_text().strip() == CASES_SHA256):
        z = ASSETS / "cover-case-library.zip"
        _download(CASES_URL, z, CASES_SHA256)
        with zipfile.ZipFile(z) as zf:
            zf.extractall(ASSETS)
        z.unlink()
        marker.write_text(CASES_SHA256)
    return CASES


def font_path() -> str | None:
    """Font for rendering: cached asset, else system Noto CJK; None if neither."""
    if FONT.exists():
        return str(FONT)
    for p in ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
              "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc"):
        if Path(p).exists():
            return p
    return None


def paths() -> dict:
    return {"assets": str(ASSETS), "font": str(FONT), "font_ready": FONT.exists(),
            "cover_case_library": str(CASES), "cases_ready": (CASES / ".sha256").exists()}


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "ensure"
    if cmd == "ensure":
        ensure_pillow()
        ensure_font()
        ensure_cases()
    elif cmd != "path":
        print(__doc__)
        return 2
    print(json.dumps(paths(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
