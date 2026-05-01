# Summeap 🎙️→📄

**Summeap** converts audio and video recordings (MP4, MOV, MP3, WAV…) into structured Markdown summaries using local AI — no cloud, no subscriptions.

Built around [Whisper](https://github.com/openai/whisper) for transcription and [LM Studio](https://lmstudio.ai) as the local LLM backend. Includes OBS integration and a lightweight CLI recorder to auto-record Microsoft Teams calls.

---

## Features

- 🎙️ **Local transcription** via `mlx-whisper` (Apple Silicon GPU) or `openai-whisper` (CPU fallback)
- 🤖 **Local LLM summarisation** via LM Studio (OpenAI-compatible API)
- 👥 **Speaker diarization** via `pyannote.audio` on Apple MPS GPU
- 📄 **Multiple output formats**: Markdown, PDF (pandoc + xelatex), Word (.docx)
- 🧠 **Multiple models at once**: pass a comma-separated list and get one report per model
- 🎨 **Three summary styles**: `executive`, `normal`, `detailed`
- 🐳 **Docker support** for CPU and NVIDIA CUDA
- 🔴 **macOS status bar app**: native menubar icon, live recording counter, settings UI, global hotkey (`Cmd+Shift+R`)
- 🎬 **Two recording backends**: OBS Studio (full scene switching) or lightweight ffmpeg CLI recorder (no OBS required)

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
pip3 install rumps obsws-python
python3 src/statusbar/summeap_app.py
```

| Feature | Description |
|---------|-------------|
| 🔴 / ⚫ icon | Live recording state |
| Recording counter | Shows elapsed time and backend while recording (e.g. `🔴 OBS 4:32`) |
| Start / Stop | Toggle recording from the menu |
| Recent Summaries | Top 10 summaries from recordings folder, click to open |
| Settings | Configure recorder, OBS, paths, tokens and models |
| `Cmd+Shift+R` | Global hotkey via CGEventTap (no Hammerspoon needed) |
| Show Log | View media2md processing output |

Config is stored at `~/.config/summeap/config.json` and shared with `obs_teams_record.py`.

See [`src/statusbar/README.md`](src/statusbar/README.md) for full setup instructions.

---

## Recording Backends

The status bar app supports two recording backends, switchable from **Settings → Recorder → Backend**.

### OBS Studio (`obs`)
Full scene switching and Teams window auto-detection. Requires OBS Studio with the WebSocket server enabled.

1. Enable WebSocket server in OBS → *Tools → WebSocket Server Settings* (port 4455, set a password)
2. Create a scene named `Teams` with a *macOS Window Capture* source
3. Set the OBS password in **Settings → OBS Connection**

### CLI Recorder (`cli`)
Lightweight ffmpeg-based recorder — no OBS installation needed. Records audio (and optionally screen) directly using `avfoundation`.

1. `brew install ffmpeg`
2. In **Settings → Recorder**: set Backend to `cli`, set Audio Device (e.g. `:0` for default mic, or `:BlackHole 2ch` for loopback)
3. Leave Video Device as `none` for audio-only, or set `desktop` for screen capture

### Workflow (both backends)

```
Cmd+Shift+R (start)
  └── Backend starts recording
  └── Menubar shows 🔴 OBS 0:01 (or 🔴 CLI 0:01), counter increments every second

Cmd+Shift+R (stop)
  └── Recording stops, file saved to recordings folder
  └── media2md runs silently in the background
  └── Open "Show Log" to watch progress
  └── Output files appear in Recent Summaries when done
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
│   │   ├── hammerspoon_init.lua  # macOS global hotkey (optional, replaced by status bar app)
│   │   └── README.md
│   └── statusbar/
│       ├── summeap_app.py        # macOS status bar app (rumps)
│       ├── config.py             # Config R/W (~/.config/summeap/config.json)
│       ├── obs_client.py         # OBS WebSocket status polling + toggle
│       ├── cli_recorder.py       # Lightweight ffmpeg recording backend
│       ├── log_window.py         # Native AppKit log panel for media2md output
│       ├── settings_window.py    # Native AppKit settings panel
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

- [x] **Local transcription** — mlx-whisper (Apple Silicon) + openai-whisper (CPU fallback)
- [x] **Local LLM summarisation** — LM Studio / OpenAI-compatible API
- [x] **Speaker diarization** — pyannote.audio on Apple MPS
- [x] **Multiple output formats** — Markdown, PDF, Word (.docx)
- [x] **Multiple models at once** — one Whisper pass, N LLM reports
- [x] **Docker support** — CPU and NVIDIA CUDA images
- [x] **OBS + Teams integration** — scene switching, Teams window auto-detection, meeting title in filename
- [x] **Status bar app** — native macOS menubar app with live recording state, summaries list, settings UI and global hotkey (`Cmd+Shift+R` via CGEventTap)
- [x] **Recording counter** — elapsed time and backend shown in menubar while recording
- [x] **Settings UI** — full AppKit panel; configure all options without editing code
- [x] **Native log window** — AppKit panel streaming media2md output in the background; open on demand via "Show Log"
- [x] **Lightweight CLI recorder** — ffmpeg-based backend, no OBS required; audio-only or screen+audio, switchable from Settings
- [ ] **Auto-start on login** — LaunchAgent / Login Items integration
- [ ] **More conferencing platforms** — Zoom, Google Meet, Webex alongside Microsoft Teams
- [ ] **Automated start/stop** — detect call join/leave events to start and stop recording without a manual hotkey
- [ ] **Multi-platform support** — Linux and Windows (recording, hotkeys, notifications)

---

## License

MIT
