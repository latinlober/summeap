# media2md

Converts audio/video files to structured Markdown using local AI.

## Usage

```bash
python3 media2md.py meeting.mp4
python3 media2md.py meeting.mp4 --style detailed --save-transcript --docx
python3 media2md.py meeting.mp4 --diarize
python3 media2md.py meeting.mp4 --model gemma-4-26b,qwen3-35b --docx
```

## Dependencies

```bash
pip3 install mlx-whisper openai
# optional diarization:
pip3 install "pyannote.audio==3.4.0" "speechbrain==1.0.0" openai-whisper
```

Requires: `ffmpeg`, `pandoc` + xelatex (for PDF), LM Studio running on port 1234.

See the [main README](../../README.md) for full CLI reference.
