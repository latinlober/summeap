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
import threading
from pathlib import Path

# Ensure sibling modules are importable when run from any directory
sys.path.insert(0, str(Path(__file__).parent))

import rumps  # type: ignore
import config as _config
import obs_client as _obs

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
        self._quit_item     = rumps.MenuItem("Quit", callback=rumps.quit_application)

        self.menu = [
            self._status_item,
            self._toggle_item,
            None,                        # separator
            self._summaries_item,
            self._open_folder,
            None,
            self._settings_item,
            self._quit_item,
        ]
        self._refresh_summaries()

    # ── OBS polling ──────────────────────────────────────────────────────────

    @rumps.timer(POLL_INTERVAL)
    def poll_obs(self, _):
        recording = _obs.is_recording()
        if recording != self._recording:
            self._recording = recording
            self._update_ui()

    def _update_ui(self):
        if self._recording:
            self.title = ICON_RECORDING
            self._status_item.title = "●  Recording…"
            self._toggle_item.title = "Stop Recording"
        else:
            self.title = ICON_IDLE
            self._status_item.title = "○  Not recording"
            self._toggle_item.title = "Start Recording"
            self._refresh_summaries()

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
        cfg = _config.load()
        fields = [
            ("OBS Password",         "obs_password"),
            ("OBS Host",             "obs_host"),
            ("OBS Port",             "obs_port"),
            ("OBS Scene",            "obs_scene"),
            ("Recordings Folder",    "recordings_dir"),
            ("media2md.py Path",     "media2md_path"),
            ("obs_teams_record.py",  "obs_script_path"),
            ("HuggingFace Token",    "hf_token"),
            ("Python Path",          "python_path"),
            ("Extra PATH",           "extra_path"),
            ("LLM Model",            "llm_model"),
            ("Whisper Model",        "whisper_model"),
            ("Default Style",        "default_style"),
        ]
        changed = False
        for label, key in fields:
            current = str(cfg.get(key, ""))
            win = rumps.Window(
                title=f"Summeap Settings — {label}",
                message=f"{label}:",
                default_text=current,
                ok="Save",
                cancel="Skip",
                dimensions=(400, 24),
            )
            response = win.run()
            if response.clicked == 1 and response.text.strip() != current:
                val = response.text.strip()
                cfg[key] = int(val) if key == "obs_port" else val
                changed = True

        if changed:
            _config.save(cfg)
            rumps.notification(
                title="Summeap",
                subtitle="Settings saved",
                message="Configuration updated successfully.",
            )

    # ── Global hotkey (optional — requires pynput) ───────────────────────────

    def _start_hotkey(self):
        try:
            from pynput import keyboard  # type: ignore

            def on_activate():
                _obs.toggle()

            hotkeys = keyboard.GlobalHotKeys({"<cmd>+<shift>+r": on_activate})
            t = threading.Thread(target=hotkeys.start, daemon=True)
            t.start()
            print("Global hotkey Cmd+Shift+R registered via pynput")
        except ImportError:
            print("pynput not installed — global hotkey disabled (Hammerspoon still works)")
        except Exception as e:
            print(f"Could not register global hotkey: {e}")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    SummeapApp().run()
