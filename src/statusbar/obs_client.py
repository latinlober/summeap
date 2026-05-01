"""
obs_client.py — Thin wrapper around obsws_python for status polling.
All OBS control logic (scene switching, window detection, etc.) stays
in obs_teams_record.py — this module only reads status and delegates
start/stop via subprocess.
"""

import subprocess
import logging
from datetime import datetime
from pathlib import Path

import config as _config

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_PATH = Path.home() / ".config" / "summeap" / "obs.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_log = logging.getLogger("obs_client")
_log.setLevel(logging.DEBUG)
if not _log.handlers:
    _fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                        datefmt="%Y-%m-%d %H:%M:%S"))
    _log.addHandler(_fh)
# ─────────────────────────────────────────────────────────────────────────────


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
        active = bool(client.get_record_status().output_active)
        return active
    except Exception as e:
        _log.debug("is_recording poll error: %s", e)
        return False


def toggle() -> None:
    """Start or stop recording by delegating to obs_teams_record.py."""
    cfg = _config.load()
    script = cfg["obs_script_path"]
    python = cfg["python_path"]
    _log.info("toggle() → %s %s toggle", python, script)
    try:
        proc = subprocess.Popen(
            [python, script, "toggle"],
            env=_build_env(cfg),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        # Stream output to log in a background thread so we don't block
        import threading
        def _drain(p):
            for line in p.stdout:
                _log.info("[obs_script] %s", line.rstrip())
            rc = p.wait()
            _log.info("[obs_script] exited with code %d", rc)
        threading.Thread(target=_drain, args=(proc,), daemon=True).start()
    except Exception as e:
        _log.error("toggle() failed to launch script: %s", e)


def _build_env(cfg: dict) -> dict:
    """Build environment dict for subprocess calls."""
    import os
    env = os.environ.copy()
    env["HF_TOKEN"]  = cfg.get("hf_token", "")
    env["PATH"]      = cfg.get("extra_path", "") + ":" + env.get("PATH", "")
    return env
