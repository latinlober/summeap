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
import time
from pathlib import Path

# Ensure sibling modules are importable when run from any directory
sys.path.insert(0, str(Path(__file__).parent))

import rumps  # type: ignore
import config as _config
import obs_client as _obs
import settings_window as _settings
import log_window as _log_window


def _get_backend():
    """Return the active recording backend module (obs_client or cli_recorder)."""
    cfg = _config.load()
    if cfg.get("recorder_backend", "obs") == "cli":
        import cli_recorder as _cli
        return _cli
    return _obs

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
        self._rec_start: float = 0.0   # time.time() when recording started
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
        self._log_item      = rumps.MenuItem("Show Log…", callback=self.on_show_log)
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
        recording = _get_backend().is_recording()
        if recording != self._recording:
            self._recording = recording
            if recording:
                self._rec_start = time.time()
            self._update_ui()
        # Refresh summaries on every tick (cheap glob, only updates menu items)
        self._refresh_summaries()
        # Pick up any pending media2md job written by obs_teams_record.py
        self._check_job_file()

    def _update_ui(self):
        if self._recording:
            self._update_title_counter()
            self._status_item.title = "●  Recording…"
            self._toggle_item.title = "Stop Recording"
        else:
            self.title = ICON_IDLE
            self._status_item.title = "○  Not recording"
            self._toggle_item.title = "Start Recording"

    def _update_title_counter(self):
        """Update menubar title with backend name and elapsed time."""
        cfg     = _config.load()
        backend = cfg.get("recorder_backend", "obs").upper()
        elapsed = int(time.time() - self._rec_start)
        hours, rem = divmod(elapsed, 3600)
        mins, secs = divmod(rem, 60)
        if hours:
            counter = f"{hours}:{mins:02d}:{secs:02d}"
        else:
            counter = f"{mins}:{secs:02d}"
        self.title = f"{ICON_RECORDING} {backend} {counter}"

    @rumps.timer(1)
    def tick_counter(self, _):
        """Update the recording counter in the title every second."""
        if self._recording:
            self._update_title_counter()

    # ── Toggle recording ─────────────────────────────────────────────────────

    def on_toggle(self, _):
        _get_backend().toggle()

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

    # ── Global hotkey — CGEventTap (requires Accessibility permission) ────────

    def _start_hotkey(self):
        self._hotkey_tap = None
        self._hotkey_run_loop_source = None
        self._restart_hotkey()

    def _restart_hotkey(self):
        import Quartz

        # Remove existing tap
        if getattr(self, "_hotkey_tap", None) is not None:
            try:
                Quartz.CGEventTapEnable(self._hotkey_tap, False)
            except Exception:
                pass
            self._hotkey_tap = None

        cfg = _config.load()
        key_combo = cfg.get("hotkey_toggle", "<cmd>+<shift>+r").strip().lower()
        if not key_combo:
            return

        # Parse modifiers and key char
        required_mods = 0
        key_char = ""
        for part in key_combo.split("+"):
            part = part.strip().strip("<>")
            if part in ("cmd", "command"):
                required_mods |= Quartz.kCGEventFlagMaskCommand
            elif part == "shift":
                required_mods |= Quartz.kCGEventFlagMaskShift
            elif part in ("ctrl", "control"):
                required_mods |= Quartz.kCGEventFlagMaskControl
            elif part in ("alt", "option"):
                required_mods |= Quartz.kCGEventFlagMaskAlternate
            else:
                key_char = part

        if not key_char:
            print("hotkey: no key character found, disabling")
            return

        key_code = _char_to_keycode(key_char)
        if key_code is None:
            print(f"hotkey: unknown key '{key_char}', disabling")
            return

        def _tap_cb(proxy, event_type, event, refcon):
            try:
                if event_type == Quartz.kCGEventKeyDown:
                    code  = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                    flags = Quartz.CGEventGetFlags(event) & (
                        Quartz.kCGEventFlagMaskCommand | Quartz.kCGEventFlagMaskShift |
                        Quartz.kCGEventFlagMaskControl | Quartz.kCGEventFlagMaskAlternate
                    )
                    if code == key_code and flags == required_mods:
                        _get_backend().toggle()
            except Exception as e:
                print(f"hotkey tap error: {e}")
            return event

        tap = Quartz.CGEventTapCreate(
            Quartz.kCGSessionEventTap,
            Quartz.kCGHeadInsertEventTap,
            Quartz.kCGEventTapOptionDefault,
            Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
            _tap_cb,
            None,
        )
        if tap is None:
            print("hotkey: CGEventTapCreate failed — Accessibility permission required")
            print("  → System Settings → Privacy & Security → Accessibility")
            print(f"  → Add: /Library/Developer/CommandLineTools/Library/Frameworks/"
                  f"Python3.framework/Versions/3.9/Resources/Python.app")
            return

        run_loop_source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
        Quartz.CFRunLoopAddSource(
            Quartz.CFRunLoopGetMain(),
            run_loop_source,
            Quartz.kCFRunLoopCommonModes,
        )
        Quartz.CGEventTapEnable(tap, True)
        self._hotkey_tap = tap
        self._hotkey_run_loop_source = run_loop_source
        print(f"Global hotkey {key_combo!r} registered via CGEventTap")


def _char_to_keycode(char: str) -> int:
    """Map a single character to its macOS virtual key code."""
    _map = {
        'a': 0,  's': 1,  'd': 2,  'f': 3,  'h': 4,  'g': 5,  'z': 6,
        'x': 7,  'c': 8,  'v': 9,  'b': 11, 'q': 12, 'w': 13, 'e': 14,
        'r': 15, 'y': 16, 't': 17, '1': 18, '2': 19, '3': 20, '4': 21,
        '6': 22, '5': 23, '=': 24, '9': 25, '7': 26, '-': 27, '8': 28,
        '0': 29, ']': 30, 'o': 31, 'u': 32, '[': 33, 'i': 34, 'p': 35,
        'l': 37, 'j': 38, "'": 39, 'k': 40, ';': 41, '\\': 42, ',': 43,
        '/': 44, 'n': 45, 'm': 46, '.': 47, '`': 50,
    }
    return _map.get(char.lower())


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    SummeapApp().run()
