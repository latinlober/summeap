# Docker

CPU and NVIDIA CUDA images for running `media2md` in a container.

## Build

```bash
# CPU image
docker build -t media2md:latest .

# CUDA image (Linux + NVIDIA)
docker build -f Dockerfile.cuda -t media2md:cuda .
```

## Run

```bash
# CPU (macOS / Linux)
docker run --rm \
  -v "$PWD":/data \
  -e HF_TOKEN \
  -e LMSTUDIO_URL=http://host.docker.internal:1234 \
  media2md:latest meeting.mp4 --style detailed

# NVIDIA GPU
docker run --rm --gpus all \
  -v "$PWD":/data \
  -e HF_TOKEN \
  -e LMSTUDIO_URL=http://host.docker.internal:1234 \
  media2md:cuda meeting.mp4 --diarize
```

## Docker Compose

```bash
# CPU
HF_TOKEN=hf_xxx docker compose run --rm media2md meeting.mp4

# CUDA
HF_TOKEN=hf_xxx docker compose run --rm media2md-cuda meeting.mp4 --diarize
```

Model caches (Whisper + HuggingFace) are stored in named volumes and reused across runs.
