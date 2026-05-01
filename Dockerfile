# ─────────────────────────────────────────────────────────────────────────────
# media2md — Dockerfile multi-plataforma
#
# GPU support:
#   macOS (Apple Silicon) : CPU fallback (MPS no accesible desde VM Docker)
#   Linux + NVIDIA        : CUDA vía nvidia-container-toolkit
#   Linux sin GPU         : CPU fallback automático
#
# Build:
#   docker build -t media2md .
#
# Run (macOS / Linux CPU):
#   docker run --rm -v "$PWD":/data -e HF_TOKEN media2md video.mp4
#
# Run (Linux + NVIDIA GPU):
#   docker run --rm --gpus all -v "$PWD":/data -e HF_TOKEN media2md video.mp4
# ─────────────────────────────────────────────────────────────────────────────

# Base con CUDA 12.4 + cuDNN — en CPU/macOS se ignoran las libs CUDA
FROM python:3.11-slim

# ── Sistema ──────────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        curl \
        # soundfile deps
        libsndfile1 \
        # torchaudio deps
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# ── Usuario no-root ───────────────────────────────────────────────────────────
RUN useradd -m -u 1000 media2md
USER media2md
WORKDIR /home/media2md

ENV PATH="/home/media2md/.local/bin:$PATH"
# Cache de modelos dentro del contenedor (se puede montar como volumen)
ENV WHISPER_CACHE="/home/media2md/.cache/whisper"
ENV HF_HOME="/home/media2md/.cache/huggingface"

# ── Python deps ──────────────────────────────────────────────────────────────
# Instalamos primero torch CPU-only por defecto; si hay CUDA disponible
# en runtime el script lo detecta igualmente vía torch.cuda.is_available()
RUN pip install --no-cache-dir --upgrade pip

# PyTorch: versión CPU que funciona en ARM64 y x86_64
# En Linux+NVIDIA se puede hacer override con la imagen CUDA (ver abajo)
RUN pip install --no-cache-dir \
        torch \
        torchaudio \
        --index-url https://download.pytorch.org/whl/cpu

# Resto de dependencias
RUN pip install --no-cache-dir \
        openai-whisper \
        openai \
        "speechbrain==1.0.0" \
        "pyannote.audio==3.4.0" \
        soundfile \
        numpy

# ── Script ───────────────────────────────────────────────────────────────────
COPY --chown=media2md:media2md media2md.py /home/media2md/media2md.py

# Directorio de trabajo para los archivos del usuario
VOLUME ["/data"]
WORKDIR /data

ENTRYPOINT ["python3", "/home/media2md/media2md.py"]
CMD ["--help"]
