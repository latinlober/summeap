"""
config.py — Summeap configuration manager
Reads/writes ~/.config/summeap/config.json
"""

import json
import shutil
from pathlib import Path

CONFIG_PATH = Path.home() / ".config" / "summeap" / "config.json"


def _find(cmd: str) -> str:
    """Return the path of a command if found on PATH, else empty string."""
    found = shutil.which(cmd)
    return found or ""


DEFAULTS = {
    "obs_host":        "localhost",
    "obs_port":        4455,
    "obs_password":    "",
    "obs_scene":       "Teams",
    "recordings_dir":  str(Path.home() / "Movies"),
    "media2md_path":   str(Path.home() / "bin" / "media2md.py"),
    "obs_script_path": str(Path.home() / "bin" / "obs_teams_record.py"),
    "hf_token":        "",
    "python_path":     "/usr/bin/python3",
    "extra_path":      "/usr/local/bin:/opt/homebrew/bin",
    "llm_model":       "google/gemma-4-26b-a4b",
    "whisper_model":   "large-v3-turbo",
    "default_style":   "detailed",
    "hotkey_toggle":   "<cmd>+<shift>+r",
    "pandoc_path":     "",   # auto-detected at first load if empty
    "xelatex_path":    "",   # auto-detected at first load if empty
    "default_formats": "pdf,docx",  # comma-separated: pdf, docx
}


def load() -> dict:
    """Load config from disk, filling missing keys with defaults."""
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            on_disk = json.loads(CONFIG_PATH.read_text())
            cfg.update(on_disk)
        except Exception:
            pass
    # Auto-detect pandoc / xelatex if not yet configured
    changed = False
    if not cfg.get("pandoc_path"):
        cfg["pandoc_path"] = _find("pandoc")
        changed = True
    if not cfg.get("xelatex_path"):
        cfg["xelatex_path"] = _find("xelatex")
        changed = True
    if changed:
        save(cfg)
    return cfg


def save(cfg: dict) -> None:
    """Persist config to disk."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))
