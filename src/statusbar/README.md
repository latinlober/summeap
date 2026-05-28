# statusbar

Native macOS menubar app for Summeap. Provides a persistent menubar icon to control recording, browse past summaries, and configure all settings — no Hammerspoon required.

## Features

- 🔴 / ⚫ menubar icon showing live recording state
- **Recording counter** — elapsed time and backend in the title while recording (e.g. `🔴 OBS 4:32` or `🔴 CLI 1:07`)
- **Start / Stop Recording** menu item and global hotkey `Cmd+Shift+R` (via CGEventTap — no Hammerspoon needed)
- **Two recording backends** — OBS Studio or lightweight ffmpeg CLI recorder, switchable from Settings
- **Recent Summaries** submenu — top 10 files from the recordings folder, click to open
- **Open Recordings Folder** — opens Finder at the recordings directory
- **Settings** — full AppKit panel to configure all options without editing code
- **Show Log** — native AppKit log panel that streams media2md output in the background; open on demand

## Requirements

```bash
pip3 install rumps obsws-python   # obsws-python only needed for OBS backend
brew install ffmpeg               # only needed for CLI backend
```

> Requires macOS 10.10+.
> `Cmd+Shift+R` hotkey requires **Accessibility permission**: System Settings → Privacy & Security → Accessibility → add your Terminal app.

## Setup

1. **Run**:
   ```bash
   python3 src/statusbar/summeap_app.py
   ```

2. **Configure** — click *Settings…* in the menubar and fill in:

   | Section | Key settings |
   |---------|-------------|
   | Recorder | Backend (`obs` or `cli`), ffmpeg path, audio/video device, quality |
   | OBS Connection | Host, port, password, scene name |
   | Paths | Recordings folder, media2md.py path, Python path |
   | AI Models | LLM model, Whisper model, summary style |
   | HuggingFace | HF token (only for diarization) |
   | Export | pandoc/xelatex paths, output formats (PDF, Word), diarization default |
   | Hotkeys | Toggle recording hotkey (default `<cmd>+<shift>+r`) |

   Settings are saved to `~/.config/summeap/config.json`.

3. **Auto-start** — create a LaunchAgent so the app starts automatically at login:

   ```bash
   cat > ~/Library/LaunchAgents/com.summeap.statusbar.plist << 'EOF'
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.summeap.statusbar</string>
       <key>ProgramArguments</key>
       <array>
           <string>/usr/bin/python3</string>
           <string>/Users/YOUR_USER/summeap-repo/src/statusbar/summeap_app.py</string>
       </array>
       <key>RunAtLoad</key>
       <true/>
       <key>KeepAlive</key>
       <false/>
       <key>StandardOutPath</key>
       <string>/tmp/summeap-statusbar.log</string>
       <key>StandardErrorPath</key>
       <string>/tmp/summeap-statusbar.error.log</string>
   </dict>
   </plist>
   EOF

   launchctl load ~/Library/LaunchAgents/com.summeap.statusbar.plist
   ```

   > Replace `YOUR_USER` with your macOS username, or use the absolute path to the repo.

   To disable auto-start:
   ```bash
   launchctl unload ~/Library/LaunchAgents/com.summeap.statusbar.plist
   ```

   Logs are written to `/tmp/summeap-statusbar.log` and `/tmp/summeap-statusbar.error.log`.

## Recording Backends

### OBS (`obs`)
Full scene switching and Teams window auto-detection. Requires OBS Studio with WebSocket server enabled (port 4455).

### CLI (`cli`)
Uses ffmpeg `avfoundation` — no OBS needed.

- **Audio-only** (default): set Video Device to `none`, Audio Device to `:0` (default mic) or `:BlackHole 2ch` (loopback)
- **Screen + audio**: set Video Device to `desktop` and Audio Device to your mic/loopback index

Quality presets: `low` = 64 kbps · `medium` = 128 kbps · `high` = 192 kbps

## Config file

`~/.config/summeap/config.json` (shared with `obs_teams_record.py`):

```json
{
  "recorder_backend":  "obs",
  "ffmpeg_path":       "/opt/homebrew/bin/ffmpeg",
  "cli_audio_device":  ":0",
  "cli_video_device":  "none",
  "cli_quality":       "medium",

  "obs_host":          "localhost",
  "obs_port":          4455,
  "obs_password":      "your_password",
  "obs_scene":         "Teams",

  "recordings_dir":    "~/Movies",
  "media2md_path":     "~/bin/media2md.py",
  "obs_script_path":   "~/bin/obs_teams_record.py",
  "python_path":       "/usr/bin/python3",
  "extra_path":        "/usr/local/bin:/opt/homebrew/bin",

  "llm_model":         "google/gemma-4-26b-a4b",
  "whisper_model":     "large-v3-turbo",
  "default_style":     "detailed",
  "default_formats":   "pdf,docx",
  "default_diarize":   "",

  "hf_token":          "hf_...",
  "pandoc_path":       "/opt/homebrew/bin/pandoc",
  "xelatex_path":      "/usr/local/bin/xelatex",

  "hotkey_toggle":     "<cmd>+<shift>+r"
}
```

## Module overview

| File | Purpose |
|------|---------|
| `summeap_app.py` | Main rumps app — menubar, timers, hotkey |
| `config.py` | Read/write `~/.config/summeap/config.json` |
| `obs_client.py` | OBS WebSocket polling and toggle via `obs_teams_record.py` |
| `cli_recorder.py` | ffmpeg avfoundation recording backend |
| `log_window.py` | AppKit NSPanel streaming subprocess output |
| `settings_window.py` | AppKit NSPanel settings form |
