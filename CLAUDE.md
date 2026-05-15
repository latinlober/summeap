# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

**Summeap** converts audio/video recordings into structured Markdown summaries using local AI. The pipeline: media file → Whisper transcription → LM Studio LLM summarisation → Markdown/PDF/Word output. No cloud services required.

## Running the Tools

```bash
# Core pipeline
python3 src/media2md/media2md.py meeting.mp4
python3 src/media2md/media2md.py meeting.mp4 --style detailed --save-transcript --docx
python3 src/media2md/media2md.py meeting.mp4 --diarize  # requires HF_TOKEN env var
python3 src/media2md/media2md.py meeting.mp4 --model gemma-4-26b,qwen3-35b  # multiple models

# Status bar app (macOS)
pip3 install rumps obsws-python
python3 src/statusbar/summeap_app.py

# OBS+Teams recorder (standalone)
python3 src/obs-teams/obs_teams_record.py

# Docker
docker build -t media2md:latest docker/
docker build -f docker/Dockerfile.cuda -t media2md:cuda docker/
docker run --rm -v "$PWD":/data -e HF_TOKEN -e LMSTUDIO_URL=http://host.docker.internal:1234 media2md:latest meeting.mp4
```

## Architecture

The project has four independent components under `src/`:

### `src/media2md/media2md.py`
Single-file CLI pipeline. Key flow:
1. Extract audio from video via ffmpeg
2. Transcribe with `mlx-whisper` (Apple Silicon GPU) or `openai-whisper` (CPU fallback)
3. Optionally diarize with `pyannote.audio` (MPS GPU), merging speaker labels into transcript
4. Send transcript to LM Studio (OpenAI-compatible API at `localhost:1234`) for summarisation
5. Export to Markdown, then optionally PDF (pandoc+xelatex) and/or Word (pandoc)
6. When multiple `--model` values given, Whisper runs once and each model generates its own output file

### `src/statusbar/` — macOS menubar app
- `summeap_app.py` — `rumps`-based app; orchestrates all components; registers `Cmd+Shift+R` global hotkey via CGEventTap
- `config.py` — reads/writes `~/.config/summeap/config.json` (shared with `obs_teams_record.py`)
- `obs_client.py` — polls OBS WebSocket for recording state; toggle start/stop
- `cli_recorder.py` — ffmpeg `avfoundation` backend; no OBS needed
- `log_window.py` — AppKit `NSPanel` that streams `media2md` subprocess output
- `settings_window.py` — AppKit `NSPanel` for all configuration

The app supports two recording backends (switchable in Settings): `obs` (full OBS scene switching) and `cli` (lightweight ffmpeg). On stop, it spawns `media2md.py` in a background subprocess and shows output via the log window.

### `src/obs-teams/obs_teams_record.py`
Standalone OBS controller. Uses `obsws-python` to switch scenes and detects active Microsoft Teams window for auto-naming recordings.

### `src/hammerspoon/hammerspoon_init.lua`
Legacy Lua script for global hotkey via Hammerspoon. Superseded by the CGEventTap approach in the status bar app — kept for users who prefer Hammerspoon.

## Key Dependencies

| Purpose | Package |
|---------|---------|
| Transcription (Apple Silicon) | `mlx-whisper` |
| Transcription (CPU) | `openai-whisper` |
| Diarization | `pyannote.audio==3.4.0`, `speechbrain==1.0.0` |
| LLM API client | `openai` (pointed at LM Studio) |
| Status bar UI | `rumps` |
| OBS control | `obsws-python` |
| Doc export | `pandoc`, `xelatex` (system), `python-docx` |

## Environment Variables

- `HF_TOKEN` — HuggingFace token; required only for diarization
- `LMSTUDIO_URL` — override LM Studio base URL (default: `http://localhost:1234`); used in Docker
