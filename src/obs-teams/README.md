# obs-teams

OBS WebSocket controller that auto-records Microsoft Teams calls and triggers
the media2md summarisation pipeline when recording stops.

## Setup

1. Edit the constants at the top of `obs_teams_record.py`:
   ```python
   OBS_PASSWORD   = "your_obs_websocket_password"
   RECORDINGS_DIR = Path.home() / "Movies"
   MEDIA2MD       = str(Path.home() / "bin" / "media2md.py")
   HF_TOKEN       = "your_huggingface_token"   # only for --diarize
   PYTHON         = "/usr/bin/python3"
   EXTRA_PATH     = "/usr/local/bin:/opt/homebrew/bin"
   ```

2. In OBS: enable WebSocket server (*Tools → WebSocket Server Settings*, port 4455).
   Create a scene named `Teams` with a source named `macOS Window Capture`.

3. Copy `obs_teams_record.py` to `~/bin/` and pair it with the Hammerspoon hotkey.

## Dependencies

```bash
pip3 install obsws-python
```

See the [main README](../../README.md) for the full workflow description.
