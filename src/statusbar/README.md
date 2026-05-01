# statusbar

macOS status bar app for Summeap. Provides a persistent menubar icon to control
OBS recording, browse past summaries, and configure all settings — no Hammerspoon required.

## Features

- 🔴 / ⚫ menubar icon showing live recording state (polls OBS every 3s)
- **Start / Stop Recording** menu item
- **Recent Summaries** submenu — top 10 files from the recordings folder, click to open
- **Open Recordings Folder** — opens Finder at the recordings directory
- **Settings** — configure all options (OBS password, paths, tokens, models…) without editing code
- **Global hotkey** `Cmd+Shift+R` via `pynput` (replaces Hammerspoon if installed)

## Requirements

```bash
pip3 install rumps pynput obsws-python
```

> `rumps` requires macOS 10.10+.
> `pynput` requires Accessibility permission: **System Settings → Privacy & Security → Accessibility** → add your Terminal / Python.

## Setup

1. **Configure** — on first run, click *Settings…* and fill in:
   - OBS Password (from OBS → Tools → WebSocket Server Settings)
   - Recordings Folder (where OBS saves files, default `~/Movies`)
   - `media2md.py` and `obs_teams_record.py` paths
   - HuggingFace Token (only needed for `--diarize`)
   - LLM Model, Whisper Model, Default Style

   Settings are saved to `~/.config/summeap/config.json`.

2. **Run**:
   ```bash
   python3 src/statusbar/summeap_app.py
   ```

3. **Auto-start** — add to Login Items:
   - Wrap in a `.app` with [Platypus](https://sveinbjorn.org/platypus) or py2app
   - Or add a simple LaunchAgent plist in `~/Library/LaunchAgents/`

## Relation to Hammerspoon

| Feature | Hammerspoon | This app |
|---------|-------------|----------|
| Global hotkey | ✅ | ✅ (via pynput) |
| Menubar icon | ✅ (basic) | ✅ (richer menu) |
| Summaries list | ❌ | ✅ |
| Settings UI | ❌ | ✅ |

Both can coexist. If pynput is installed, the app registers `Cmd+Shift+R` and Hammerspoon can be removed. If not, Hammerspoon continues to handle the hotkey while this app provides the richer menu.

## Config file

`~/.config/summeap/config.json`:

```json
{
  "obs_host":        "localhost",
  "obs_port":        4455,
  "obs_password":    "your_password",
  "obs_scene":       "Teams",
  "recordings_dir":  "~/Movies",
  "media2md_path":   "~/bin/media2md.py",
  "obs_script_path": "~/bin/obs_teams_record.py",
  "hf_token":        "hf_...",
  "python_path":     "/usr/bin/python3",
  "extra_path":      "/usr/local/bin:/opt/homebrew/bin",
  "llm_model":       "google/gemma-4-26b-a4b",
  "whisper_model":   "large-v3-turbo",
  "default_style":   "detailed"
}
```
