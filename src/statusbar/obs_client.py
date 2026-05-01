"""
obs_client.py — Thin wrapper around obsws_python for status polling.
All OBS control logic (scene switching, window detection, etc.) stays
in obs_teams_record.py — this module only reads status and delegates
start/stop via subprocess.
"""

import subprocess
from pathlib import Path

import config as _config


def is_recording() -> bool:
    """Return True if OBS is currently recording. Returns False on any error."""
    cfg = _config.load()
    try:
        import obsws_python as obs  # type: ignore
        client = obs.ReqClient(
            host=cfg["obs_host"],
            port=int(cfg["obs_port"]),
            password=cfg["obs_password"],
            timeout=3,
        )
        return bool(client.get_record_status().output_active)
    except Exception:
        return False


def toggle() -> None:
    """Start or stop recording by delegating to obs_teams_record.py."""
    cfg = _config.load()
    subprocess.Popen(
        [cfg["python_path"], cfg["obs_script_path"], "toggle"],
        env=_build_env(cfg),
    )


def _build_env(cfg: dict) -> dict:
    """Build environment dict for subprocess calls."""
    import os
    env = os.environ.copy()
    env["HF_TOKEN"]  = cfg.get("hf_token", "")
    env["PATH"]      = cfg.get("extra_path", "") + ":" + env.get("PATH", "")
    return env
