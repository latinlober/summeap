# Summeap 🎙️→📄

**Summeap** converts audio and video recordings (MP4, MOV, MP3, WAV…) into structured Markdown summaries using local AI — no cloud, no subscriptions.

Built around [Whisper](https://github.com/openai/whisper) for transcription and [LM Studio](https://lmstudio.ai) as the local LLM backend. Includes optional OBS integration to auto-record Microsoft Teams calls.

---

## Features

- 🎙️ **Local transcription** via `mlx-whisper` (Apple Silicon GPU) or `openai-whisper` (CPU fallback)
- 🤖 **Local LLM summarisation** via LM Studio (OpenAI-compatible API)
- 👥 **Speaker diarization** via `pyannote.audio` on Apple MPS GPU
- 📄 **Multiple output formats**: Markdown, PDF (pandoc + xelatex), Word (.docx)
- 🧠 **Multiple models at once**: pass a comma-separated list and get one report per model
- 🎨 **Three summary styles**: `executive`, `normal`, `detailed`
- 🐳 **Docker support** for CPU and NVIDIA CUDA
- 🔴 **OBS integration**: one hotkey (`Cmd+Shift+R`) to start/stop recording Teams calls

---

## Requirements

### macOS (native)

| Tool | Install |
|------|---------|
| Python 3.9+ | `brew install python` |
| ffmpeg | `brew install ffmpeg` |
| pandoc + xelatex | `brew install pandoc` + MacTeX |
| LM Studio | [lmstudio.ai](https://lmstudio.ai) |
| mlx-whisper | `pip3 install mlx-whisper` |
| openai | `pip3 install openai` |

For diarization only:
```bash
pip3 install "pyannote.audio==3.4.0" "speechbrain==1.0.0" openai-whisper
```

### Docker
- Docker Desktop
- `HF_TOKEN` env var (only needed for diarization)

---

## Quick Start

### Native (macOS)

```bash
# Basic summary
python3 media2md.py meeting.mp4

# Detailed summary, save transcript, export to Word
python3 media2md.py meeting.mp4 --style detailed --save-transcript --docx

# With speaker diarization
export HF_TOKEN=your_token_here
python3 media2md.py meeting.mp4 --diarize --style detailed

# Multiple models (one report per model)
python3 media2md.py meeting.mp4 --model gemma-4-26b,qwen3-35b --docx
```

### Docker (CPU)

```bash
cd /path/to/video
docker run --rm \
  -v "$PWD":/data \
  -e HF_TOKEN \
  -e LMSTUDIO_URL=http://host.docker.internal:1234 \
  media2md:latest meeting.mp4 --style detailed
```

### Docker Compose

```bash
# CPU
HF_TOKEN=your_token LMSTUDIO_URL=http://host.docker.internal:1234 \
  docker compose run --rm media2md meeting.mp4

# NVIDIA GPU
docker compose run --rm media2md-cuda meeting.mp4 --diarize
```

---

## CLI Reference

```
usage: media2md.py [-h] [--output OUTPUT] [--model MODEL]
                   [--whisper-model WHISPER_MODEL] [--context CONTEXT]
                   [--style {executive,normal,detailed}]
                   [--diarize] [--transcript-only] [--save-transcript]
                   [--no-pdf] [--docx]
                   input

positional arguments:
  input                         Audio/video file (.mp4, .mov, .mp3, .wav, …)

options:
  --model, -m MODEL             LLM model(s), comma-separated (default: google/gemma-4-26b-a4b)
  --whisper-model, -w MODEL     Whisper size: tiny/base/small/medium/large/large-v3-turbo (default: large-v3-turbo)
  --context, -c TOKENS          Context tokens to request on model reload (default: 32768)
  --style, -s STYLE             Summary style: executive | normal | detailed (default: normal)
  --output, -o FILE             Output .md path (default: same name as input)
  --diarize, -d                 Enable speaker diarization (requires HF_TOKEN)
  --transcript-only             Save only the raw transcript, skip LLM
  --save-transcript             Also save the transcript as .txt
  --no-pdf                      Skip PDF export
  --docx                        Also export to Word (.docx)
```

**Multiple models**: when `--model` receives a comma-separated list, Whisper runs once and each model generates its own report file:
```
meeting_gemma-4-26b.md / .docx
meeting_qwen3-35b.md   / .docx
```

---

## Status Bar App

A native macOS menubar app built with Python + `rumps`:

```bash
pip3 install rumps pynput obsws-python
python3 src/statusbar/summeap_app.py
```

| Feature | Description |
|---------|-------------|
| 🔴 / ⚫ icon | Live recording state, polls OBS every 3s |
| Start / Stop | Toggle recording from the menu |
| Recent Summaries | Top 10 summaries from recordings folder, click to open |
| Settings | Configure OBS, paths, tokens and models without editing code |
| `Cmd+Shift+R` | Global hotkey via `pynput` (replaces Hammerspoon) |

Config is stored at `~/.config/summeap/config.json` and shared with `obs_teams_record.py`.

See [`src/statusbar/README.md`](src/statusbar/README.md) for full setup instructions.

---

## OBS + Teams Integration

Automatically records Microsoft Teams calls and triggers summarisation when you stop recording.

### Components

| File | Purpose |
|------|---------|
| `obs_teams_record.py` | OBS WebSocket controller |
| `hammerspoon_init.lua` | Global hotkey + menubar indicator |

### Setup

1. **OBS**: enable WebSocket server in *Tools → WebSocket Server Settings* (port 4455, set a password). Create a scene named `Teams` with a *macOS Window Capture* source named `macOS Window Capture`.

2. **Hammerspoon**: install from [hammerspoon.org](https://hammerspoon.org), copy `hammerspoon_init.lua` to `~/.hammerspoon/init.lua`, reload config.

3. **Edit constants** in `obs_teams_record.py`:
   ```python
   OBS_PASSWORD   = "your_obs_password"
   RECORDINGS_DIR = Path("/your/recordings/folder")
   MEDIA2MD       = "/path/to/media2md.py"
   HF_TOKEN       = "your_hf_token"  # only needed for diarization
   PYTHON         = "/usr/bin/python3"
   EXTRA_PATH     = "/usr/local/bin:/opt/homebrew/bin"
   ```

4. **Usage**: press `Cmd+Shift+R` to start recording. The script:
   - Switches OBS to the Teams scene
   - Auto-detects the active Teams call window
   - Fits it to full canvas
   - Renames the recording with the meeting title as prefix
   - Shows a dialog to choose the summary format when you stop

### Workflow

```
Cmd+Shift+R (start)
  └── OBS switches to Teams scene
  └── Finds Teams call window, fits to screen
  └── Starts recording
  └── Menubar shows 🔴 REC

Cmd+Shift+R (stop)
  └── OBS stops recording
  └── File renamed: "Meeting Title - 2026-04-28 16-16-21.mov"
  └── Dialog: choose summary format
  └── Terminal opens, runs media2md, closes automatically
```

---

## LM Studio Setup

1. Download and install [LM Studio](https://lmstudio.ai)
2. Load a model (recommended: `google/gemma-4-26b-a4b` or `qwen/qwen3-35b`)
3. Start the local server on port `1234`
4. For large transcripts, load the model with at least 32K context tokens

`media2md` will automatically attempt to reload the model with more context if the transcript doesn't fit.

---

## Speaker Diarization

Requires a [HuggingFace](https://huggingface.co) account with access to:
- [`pyannote/speaker-diarization-3.1`](https://huggingface.co/pyannote/speaker-diarization-3.1)
- [`pyannote/segmentation-3.0`](https://huggingface.co/pyannote/segmentation-3.0)

Accept the model terms on HuggingFace, then:
```bash
export HF_TOKEN=hf_your_token_here
python3 media2md.py meeting.mp4 --diarize
```

The output includes a participants section:
```markdown
## 👥 Participants

- **SPEAKER_00 (Alice)** — 45.2% · 18m 05s  `█████████`
- **SPEAKER_01 (Bob)**   — 32.1% · 12m 50s  `██████`
- **SPEAKER_02**         — 22.7% · 9m 05s   `████`
```

---

## Project Structure

```
summeap/
├── src/
│   ├── media2md/
│   │   ├── media2md.py           # Main pipeline: transcription + LLM summarisation
│   │   └── README.md
│   ├── obs-teams/
│   │   ├── obs_teams_record.py   # OBS controller + Teams call integration
│   │   └── README.md
│   ├── hammerspoon/
│   │   ├── hammerspoon_init.lua  # macOS global hotkey (Cmd+Shift+R) — optional
│   │   └── README.md
│   └── statusbar/
│       ├── summeap_app.py        # macOS status bar app (rumps)
│       ├── config.py             # Config R/W (~/.config/summeap/config.json)
│       ├── obs_client.py         # OBS status polling
│       └── README.md
├── docker/
│   ├── Dockerfile                # CPU image (macOS / Linux)
│   ├── Dockerfile.cuda           # NVIDIA CUDA image
│   ├── docker-compose.yml        # Compose with volume caching
│   └── README.md
├── docs/                         # Additional documentation
├── .gitignore
└── README.md
```

---

## Roadmap

Contributions and ideas are welcome! Here's what we'd like to tackle next:

- [x] **Status bar app** — native macOS menubar app with summaries list, settings UI and global hotkey (`src/statusbar/`)
- [ ] **Multi-platform support** — Linux and Windows in addition to macOS (recording integration, hotkeys, system notifications)
- [ ] **More conferencing platforms** — Zoom, Google Meet, Webex, and others alongside Microsoft Teams
- [ ] **Lightweight CLI recorder** — replace OBS with a minimal command-line audio/screen capture utility, removing the need for a full OBS installation
- [ ] **Status bar app** — a native menubar application to browse past summaries, open reports, and configure settings without editing code
- [ ] **Automated start/stop** — detect call events directly from the conferencing client (join/leave hooks, window focus events) to start and stop recording without any manual hotkey

---

## License

MIT
