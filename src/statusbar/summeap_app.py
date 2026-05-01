#!/usr/bin/env python3
"""
summeap_app.py — macOS status bar app for Summeap
Requires: pip3 install rumps pynput obsws-python

Run:
    python3 summeap_app.py

Add to Login Items for auto-start:
    System Settings → General → Login Items → add this script (via a .app wrapper)
"""

import subprocess
import sys
from pathlib import Path

# Ensure sibling modules are importable when run from any directory
sys.path.insert(0, str(Path(__file__).parent))

import rumps  # type: ignore
import config as _config
import obs_client as _obs
import settings_window as _settings
import log_window as _log_window

# ── Constants ─────────────────────────────────────────────────────────────────
MAX_SUMMARIES  = 10          # max items shown in Recent Summaries submenu
POLL_INTERVAL  = 3           # seconds between OBS status polls
ICON_RECORDING = "🔴"
ICON_IDLE      = "⚫"
# ─────────────────────────────────────────────────────────────────────────────


class SummeapApp(rumps.App):

    def __init__(self):
        super().__init__(ICON_IDLE, quit_button=None)
        self._recording = False
        self._build_menu()
        self._start_hotkey()

    # ── Menu construction ────────────────────────────────────────────────────

    def _build_menu(self):
        self._status_item   = rumps.MenuItem("○  Not recording", callback=None)
        self._status_item.set_callback(None)   # disabled / informational

        self._toggle_item   = rumps.MenuItem("Start Recording", callback=self.on_toggle)
        self._summaries_item = rumps.MenuItem("Recent Summaries")
        self._open_folder   = rumps.MenuItem("Open Recordings Folder…", callback=self.on_open_folder)
        self._settings_item = rumps.MenuItem("Settings…", callback=self.on_settings)
        self._log_item      = rumps.MenuItem("Show OBS Log…", callback=self.on_show_log)
        self._quit_item     = rumps.MenuItem("Quit", callback=rumps.quit_application)

        self.menu = [
            self._status_item,
            self._toggle_item,
            None,                        # separator
            self._summaries_item,
            self._open_folder,
            None,
            self._settings_item,
            self._log_item,
            self._quit_item,
        ]
        # Add a placeholder so rumps initialises the NSMenu backing object now;
        # the timer will replace it on the first tick.
        self._summaries_item.add(rumps.MenuItem("Loading…", callback=None))

    # ── OBS polling ──────────────────────────────────────────────────────────

    @rumps.timer(POLL_INTERVAL)
    def poll_obs(self, _):
        recording = _obs.is_recording()
        if recording != self._recording:
            self._recording = recording
            self._update_ui()
        # Refresh summaries on every tick (cheap glob, only updates menu items)
        self._refresh_summaries()
        # Pick up any pending media2md job written by obs_teams_record.py
        self._check_job_file()

    def _update_ui(self):
        if self._recording:
            self.title = ICON_RECORDING
            self._status_item.title = "●  Recording…"
            self._toggle_item.title = "Stop Recording"
        else:
            self.title = ICON_IDLE
            self._status_item.title = "○  Not recording"
            self._toggle_item.title = "Start Recording"

    # ── Toggle recording ─────────────────────────────────────────────────────

    def on_toggle(self, _):
        _obs.toggle()

    # ── Recent summaries submenu ─────────────────────────────────────────────

    def _refresh_summaries(self):
        cfg  = _config.load()
        folder = Path(cfg["recordings_dir"]).expanduser()

        # Prefer .docx, fall back to .md; group by stem
        files = {}
        for ext in ("*.docx", "*.md"):
            for f in folder.glob(ext):
                if f.stem not in files:
                    files[f.stem] = f

        recent = sorted(files.values(), key=lambda f: f.stat().st_mtime, reverse=True)
        recent = recent[:MAX_SUMMARIES]

        self._summaries_item.clear()
        if recent:
            for f in recent:
                label = f.stem[:60] + ("…" if len(f.stem) > 60 else "")
                item  = rumps.MenuItem(label, callback=self._make_open_cb(f))
                self._summaries_item.add(item)
        else:
            empty = rumps.MenuItem("No summaries yet", callback=None)
            self._summaries_item.add(empty)

    @staticmethod
    def _make_open_cb(path: Path):
        def _cb(_):
            subprocess.Popen(["open", str(path)])
        return _cb

    def on_open_folder(self, _):
        cfg = _config.load()
        folder = Path(cfg["recordings_dir"]).expanduser()
        subprocess.Popen(["open", str(folder)])

    # ── Settings ─────────────────────────────────────────────────────────────

    def on_settings(self, _):
        def _on_save(cfg):
            self._restart_hotkey()
            rumps.notification(
                title="Summeap",
                subtitle="Settings saved",
                message="Configuration updated successfully.",
            )
        _settings.show_settings(on_save=_on_save)

    # ── Job file polling ─────────────────────────────────────────────────────

    def _check_job_file(self):
        import json
        job_path = Path("/tmp/summeap_job.json")
        if job_path.exists():
            try:
                job = json.loads(job_path.read_text())
                job_path.unlink()
                _log_window.run_in_log_window(job)
            except Exception as e:
                print(f"Error reading job file: {e}")

    # ── OBS Log ──────────────────────────────────────────────────────────────

    def on_show_log(self, _):
        _log_window.show_log_window()

    # ── Global hotkey — Cocoa NSEvent monitor (no pynput / no thread issues) ──

    def _start_hotkey(self):
        self._hotkey_monitor = None
        self._restart_hotkey()

    def _restart_hotkey(self):
        try:
            from AppKit import NSEvent, NSKeyDownMask, NSEventModifierFlagCommand, \
                NSEventModifierFlagShift, NSEventModifierFlagControl, \
                NSEventModifierFlagOption
        except ImportError:
            print("AppKit not available — hotkey disabled")
            return

        # Remove existing monitor
        if getattr(self, "_hotkey_monitor", None) is not None:
            try:
                NSEvent.removeMonitor_(self._hotkey_monitor)
            except Exception:
                pass
            self._hotkey_monitor = None

        cfg = _config.load()
        key_combo = cfg.get("hotkey_toggle", "<cmd>+<shift>+r").strip().lower()
        if not key_combo:
            return

        # Parse key combo string like "<cmd>+<shift>+r"
        required_mods = 0
        key_char = ""
        for part in key_combo.split("+"):
            part = part.strip().strip("<>")
            if part in ("cmd", "command"):
                required_mods |= NSEventModifierFlagCommand
            elif part in ("shift",):
                required_mods |= NSEventModifierFlagShift
            elif part in ("ctrl", "control"):
                required_mods |= NSEventModifierFlagControl
            elif part in ("alt", "option"):
                required_mods |= NSEventModifierFlagOption
            else:
                key_char = part  # the actual key character

        if not key_char:
            print("hotkey: no key character found in combo, disabling")
            return

        _mask = 1 << 10  # NSEventMaskKeyDown

        def _handler(event):
            try:
                ch = event.charactersIgnoringModifiers()
                if ch is None:
                    return
                mods = event.modifierFlags() & (
                    NSEventModifierFlagCommand | NSEventModifierFlagShift |
                    NSEventModifierFlagControl | NSEventModifierFlagOption
                )
                if ch.lower() == key_char and mods == required_mods:
                    _obs.toggle()
            except Exception as e:
                print(f"hotkey handler error: {e}")

        monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            _mask, _handler
        )
        self._hotkey_monitor = monitor
        print(f"Global hotkey {key_combo!r} registered via NSEvent monitor")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    SummeapApp().run()
