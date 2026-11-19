"""Locate the va7 user config (config.json written by va7-onboarding).

Lookup order (first hit wins):
1. env VA7_USER_CONFIG
2. <skills_root>/va7-config/default.json — deployment default, shipped as a
   private skill next to the others so every chat/sandbox sees the same config.
3. <skills_root>/va7-pipeline/config/default.json — same, for setups that keep
   it inside the pipeline. Neither is in the public repo; see
   config/default.example.json.

Relative paths inside the config (e.g. voice_profile.path) resolve against
the config file's own directory.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

SKILLS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIGS = (
    SKILLS_ROOT / "va7-config" / "default.json",
    SKILLS_ROOT / "va7-pipeline" / "config" / "default.json",
)


def config_path() -> Path | None:
    env = os.environ.get("VA7_USER_CONFIG")
    if env:
        return Path(env).expanduser()
    return next((p for p in DEFAULT_CONFIGS if p.exists()), None)


def load_config(path: str | Path | None = None) -> tuple[dict, Path | None]:
    p = Path(path).expanduser() if path else config_path()
    if not p or not p.exists():
        return {}, None
    return json.loads(p.read_text(encoding="utf-8")), p


def resolve(cfg_file: Path | None, value: str | None) -> Path | None:
    if not value:
        return None
    p = Path(value).expanduser()
    if not p.is_absolute() and cfg_file:
        p = (cfg_file.parent / p).resolve()
    return p


def style_rules_path(path: str | Path | None = None) -> Path | None:
    """Voice style rules: config voice_profile.style_rules, else va7-script's local copy."""
    cfg, cfg_file = load_config(path)
    p = resolve(cfg_file, (cfg.get("voice_profile") or {}).get("style_rules"))
    if p and p.exists():
        return p
    local = SKILLS_ROOT / "va7-script" / "references" / "voice" / "style_rules.json"
    return local if local.exists() else None


def base_config(path: str | Path | None = None) -> tuple[str | None, dict[str, str]]:
    cfg, _ = load_config(path)
    base = cfg.get("base", {})
    return base.get("base_token"), dict(base.get("tables", {}))


if __name__ == "__main__":
    cfg, p = load_config()
    print(json.dumps({"config": str(p) if p else None, "base_token": (cfg.get("base") or {}).get("base_token"),
                      "tables": (cfg.get("base") or {}).get("tables"),
                      "voice_profile": str(resolve(p, (cfg.get("voice_profile") or {}).get("path"))),
                      "style_rules": str(style_rules_path())},
                     ensure_ascii=False, indent=2))
