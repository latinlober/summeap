"""
cli_recorder.py — Lightweight ffmpeg-based recording backend for Summeap.

Provides the same interface as obs_client.py:
    is_recording() -> bool
    toggle()       -> None
    start()        -> None
    stop()         -> None

State is persisted in /tmp so it survives between toggle() calls:
    /tmp/summeap_cli_rec.pid   — PID of the ffmpeg process
    /tmp/summeap_cli_rec.path  — absolute path of the output file
"""

import json
import logging
import os
import signal
import subprocess
import time
import threading
from datetime import datetime
from pathlib import Path

import config as _config

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_PATH = Path.home() / ".config" / "summeap" / "cli_recorder.log"
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

_log = logging.getLogger("cli_recorder")
_log.setLevel(logging.DEBUG)
if not _log.handlers:
    _fh = logging.FileHandler(LOG_PATH, encoding="utf-8")
    _fh.setFormatter(logging.Formatter("%(asctime)s  %(levelname)-7s  %(message)s",
                                        datefmt="%Y-%m-%d %H:%M:%S"))
    _log.addHandler(_fh)
# ─────────────────────────────────────────────────────────────────────────────

_PID_FILE  = Path("/tmp/summeap_cli_rec.pid")
_PATH_FILE = Path("/tmp/summeap_cli_rec.path")

# Quality presets → audio bitrate
_QUALITY = {
    "low":    "64k",
    "medium": "128k",
    "high":   "192k",
}


# ── Public API ────────────────────────────────────────────────────────────────

def is_recording() -> bool:
    """Return True if our ffmpeg process is alive."""
    if not _PID_FILE.exists():
        return False
    try:
        pid = int(_PID_FILE.read_text().strip())
        os.kill(pid, 0)   # signal 0 = check existence
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        _PID_FILE.unlink(missing_ok=True)
        return False


def toggle() -> None:
    if is_recording():
        stop()
    else:
        start()


def start() -> None:
    """Launch ffmpeg and persist its PID and output path."""
    if is_recording():
        _log.info("start() called but already recording — ignored")
        return

    cfg         = _config.load()
    ffmpeg      = cfg.get("ffmpeg_path") or "ffmpeg"
    recordings  = Path(cfg.get("recordings_dir", str(Path.home() / "Movies"))).expanduser()
    recordings.mkdir(parents=True, exist_ok=True)

    audio_dev   = cfg.get("cli_audio_device", "").strip()
    video_dev   = cfg.get("cli_video_device", "none").strip().lower()
    quality     = cfg.get("cli_quality", "medium").strip().lower()
    bitrate     = _QUALITY.get(quality, "128k")

    ts          = datetime.now().strftime("%Y-%m-%d %H-%M-%S")

    if video_dev and video_dev != "none":
        # Video + audio
        device_str  = f"{video_dev}:{audio_dev}" if audio_dev else video_dev
        output_path = recordings / f"Recording {ts}.mov"
        cmd = [
            ffmpeg, "-y",
            "-f", "avfoundation",
            "-framerate", "30",
            "-i", device_str,
            "-c:v", "libx264", "-preset", "ultrafast",
            "-c:a", "aac", "-b:a", bitrate,
            str(output_path),
        ]
    else:
        # Audio only
        device_str  = f":{audio_dev}" if audio_dev and not audio_dev.startswith(":") else (audio_dev or ":0")
        output_path = recordings / f"Recording {ts}.m4a"
        cmd = [
            ffmpeg, "-y",
            "-f", "avfoundation",
            "-i", device_str,
            "-c:a", "aac", "-b:a", bitrate,
            str(output_path),
        ]

    _log.info("start() cmd: %s", " ".join(cmd))

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError:
        _log.error("ffmpeg not found at: %s", ffmpeg)
        _notify("⚠️ Summeap", f"ffmpeg not found: {ffmpeg}")
        return
    except Exception as e:
        _log.error("start() Popen failed: %s", e)
        _notify("⚠️ Summeap", f"Failed to start recording: {e}")
        return

    _PID_FILE.write_text(str(proc.pid))
    _PATH_FILE.write_text(str(output_path))
    _log.info("Recording started — pid=%d  path=%s", proc.pid, output_path)
    _notify("🔴 Summeap", f"Recording started · {datetime.now().strftime('%Y-%m-%d %H:%M')}")

    # Drain stderr in background so pipe doesn't block ffmpeg
    def _drain(p):
        for line in p.stderr:
            _log.debug("[ffmpeg] %s", line.rstrip())
        _log.info("[ffmpeg] process exited with code %d", p.wait())
    threading.Thread(target=_drain, args=(proc,), daemon=True).start()


def stop() -> None:
    """Terminate ffmpeg gracefully, wait for file, then write job file."""
    if not _PID_FILE.exists():
        _log.info("stop() called but no pid file — ignored")
        return

    try:
        pid = int(_PID_FILE.read_text().strip())
    except ValueError:
        _log.error("stop(): invalid pid file")
        _PID_FILE.unlink(missing_ok=True)
        return

    output_path = Path(_PATH_FILE.read_text().strip()) if _PATH_FILE.exists() else None

    _log.info("stop() sending SIGTERM to pid=%d", pid)
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait up to 10s for graceful shutdown
        for _ in range(100):
            time.sleep(0.1)
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
        else:
            _log.warning("stop(): ffmpeg still running after 10s, sending SIGKILL")
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
    except ProcessLookupError:
        _log.info("stop(): process already gone")
    except Exception as e:
        _log.error("stop(): kill failed: %s", e)
    finally:
        _PID_FILE.unlink(missing_ok=True)

    _notify("⏹️ Summeap", f"Recording stopped{': ' + output_path.name if output_path else ''}")

    if output_path:
        # Hand off to media2md via the same job-file mechanism as obs_teams_record.py
        threading.Thread(
            target=_post_process,
            args=(output_path,),
            daemon=True,
        ).start()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _post_process(output_path: Path) -> None:
    """Wait for file to be fully written, then submit media2md job."""
    if not _wait_for_file_ready(output_path):
        _notify("⚠️ Summeap", f"File not ready: {output_path.name}")
        return

    cfg = _config.load()
    fmt = {f.strip().lower() for f in cfg.get("default_formats", "pdf,docx").split(",") if f.strip()}
    diarize = bool(cfg.get("default_diarize", "").strip())

    diarize_flag = "--diarize" if diarize else ""
    pdf_flag     = "" if "pdf" in fmt else "--no-pdf"
    docx_flag    = "--docx" if "docx" in fmt else ""

    job = {
        "video_path":   str(output_path),
        "python":       cfg.get("python_path", "/usr/bin/python3"),
        "media2md":     cfg.get("media2md_path", str(Path.home() / "bin" / "media2md.py")),
        "hf_token":     cfg.get("hf_token", ""),
        "extra_path":   cfg.get("extra_path", ""),
        "diarize_flag": diarize_flag,
        "pdf_flag":     pdf_flag,
        "docx_flag":    docx_flag,
    }
    job_path = Path("/tmp/summeap_job.json")
    job_path.write_text(json.dumps(job))
    _log.info("Job written to %s", job_path)


def _wait_for_file_ready(path: Path, timeout: int = 60, stable_secs: int = 3) -> bool:
    """Wait until the file exists and its size is stable (same as obs_teams_record.py)."""
    _log.info("Waiting for file to be ready: %s", path)
    deadline   = time.time() + timeout
    last_size  = -1
    stable_since = None
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            size = path.stat().st_size
            if size == last_size:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= stable_secs:
                    _log.info("File ready (%d KB): %s", size // 1024, path.name)
                    return True
            else:
                last_size = size
                stable_since = None
        time.sleep(1)
    _log.warning("Timeout waiting for file: %s", path.name)
    return False


def _notify(title: str, message: str) -> None:
    subprocess.run(
        ["osascript", "-e",
         f'display notification "{message}" with title "{title}" sound name "Glass"'],
        capture_output=True,
    )
