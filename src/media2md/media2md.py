#!/usr/bin/env python3
"""
media2md.py — Convierte MP4/MP3 a Markdown estructurado
Pipeline: ffmpeg → Whisper (transcripción local) → LM Studio API → .md

Uso:
  python3 ~/bin/media2md.py video.mp4
  python3 ~/bin/media2md.py audio.mp3
  python3 ~/bin/media2md.py video.mp4 --model qwen3.5-35b-a3b
  python3 ~/bin/media2md.py video.mp4 --output notas.md
  python3 ~/bin/media2md.py video.mp4 --whisper-model medium
  python3 ~/bin/media2md.py video.mp4 --context 32768
"""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


# ──────────────────────────────────────────────
# Configuración
# ──────────────────────────────────────────────
def _load_summeap_cfg() -> dict:
    cfg_path = Path.home() / ".config" / "summeap" / "config.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text())
        except Exception:
            pass
    return {}

_cfg = _load_summeap_cfg()

_LMSTUDIO_BASE = os.environ.get("LMSTUDIO_URL", "http://localhost:1234")
LMSTUDIO_BASE_URL = _LMSTUDIO_BASE + "/v1"
LMSTUDIO_API_BASE = _LMSTUDIO_BASE + "/api/v0"
DEFAULT_LLM_MODEL     = _cfg.get("llm_model",      "google/gemma-4-26b-a4b")
DEFAULT_WHISPER_MODEL = _cfg.get("whisper_model",   "large-v3-turbo")
DEFAULT_STYLE         = _cfg.get("default_style",   "normal")
DEFAULT_CONTEXT       = 32768
PANDOC_PATH           = _cfg.get("pandoc_path",     "pandoc")   or "pandoc"
XELATEX_PATH          = _cfg.get("xelatex_path",    "xelatex")  or "xelatex"
DEFAULT_FORMATS       = {f.strip().lower() for f in _cfg.get("default_formats", "pdf,docx").split(",") if f.strip()}
DEFAULT_DIARIZE       = bool(_cfg.get("default_diarize", "").strip())
# Margen de seguridad: usamos este % del contexto disponible para el texto
CONTEXT_USE_RATIO  = 0.75
# Aprox. chars por token (conservador para español/inglés mixto)
CHARS_PER_TOKEN    = 3.5
# ──────────────────────────────────────────────


SYSTEM_PROMPTS = {
    "executive": """Eres un asistente experto en crear resúmenes ejecutivos en Markdown.
Se te proporcionará la transcripción de un audio/video.
Tu tarea es generar un documento MUY BREVE y de alto nivel con:

1. Un título descriptivo (# Título)
2. Un párrafo de resumen ejecutivo (máximo 4 líneas)
3. Entre 3 y 5 conclusiones o puntos críticos como bullet points (## Puntos clave)
4. Una línea de "Acción recomendada" si aplica

Sé extremadamente conciso. Omite detalles, ejemplos y explicaciones largas.
Mantén el idioma original del contenido.
Devuelve ÚNICAMENTE el contenido Markdown, sin texto adicional ni bloques de código.""",

    "normal": """Eres un asistente experto en crear notas estructuradas en Markdown.
Se te proporcionará la transcripción de un audio/video.
Tu tarea es generar un documento Markdown bien estructurado con:

1. Un título descriptivo (# Título)
2. Un resumen ejecutivo de 2-3 líneas
3. Los puntos clave organizados en secciones temáticas con ## encabezados
4. Una sección de "Conclusiones o Acciones" al final si aplica
5. Bullet points claros y concisos
6. Mantén el idioma original del contenido

Devuelve ÚNICAMENTE el contenido Markdown, sin texto adicional ni bloques de código.""",

    "detailed": """Eres un asistente experto en crear documentación detallada en Markdown.
Se te proporcionará la transcripción de un audio/video.
Tu tarea es generar un documento Markdown exhaustivo con:

1. Un título descriptivo (# Título)
2. Un resumen ejecutivo de 3-5 líneas
3. Índice de secciones si el contenido lo justifica
4. Todas las secciones temáticas con ## encabezados y ### sub-secciones si aplica
5. Explicaciones completas, ejemplos mencionados y contexto relevante
6. Citas textuales relevantes en formato blockquote (> )
7. Una sección de "Conclusiones" con análisis
8. Una sección de "Próximos pasos o Acciones" si aplica

Sé exhaustivo y no omitas información relevante.
Mantén el idioma original del contenido.
Devuelve ÚNICAMENTE el contenido Markdown, sin texto adicional ni bloques de código.""",
}

# Prompt por defecto
SYSTEM_PROMPT = SYSTEM_PROMPTS["normal"]

CHUNK_SYSTEM_PROMPT = """Eres un asistente experto en resumir transcripciones.
Se te dará un fragmento de una transcripción de audio/video.
Extrae los puntos clave de ESE FRAGMENTO en formato de bullet points simples.
Sé conciso. No añadas introducción ni cierre, solo los puntos clave."""

CONSOLIDATE_SYSTEM_PROMPT = """Eres un asistente experto en crear notas estructuradas en Markdown.
Se te darán los puntos clave extraídos de varios fragmentos de una transcripción.
Tu tarea es consolidarlos en un único documento Markdown bien estructurado con:

1. Un título descriptivo (# Título)
2. Un resumen ejecutivo de 2-3 líneas
3. Los puntos clave organizados en secciones temáticas con ## encabezados (elimina duplicados)
4. Una sección de "Conclusiones o Acciones" al final si aplica

Devuelve ÚNICAMENTE el contenido Markdown, sin texto adicional ni bloques de código."""


def log(msg: str) -> None:
    print(f"  → {msg}", file=sys.stderr)


def warn(msg: str) -> None:
    print(f"  ⚠️  {msg}", file=sys.stderr)


# ──────────────────────────────────────────────
# LM Studio helpers
# ──────────────────────────────────────────────

def get_model_context(model_id: str) -> dict:
    """Consulta el contexto cargado y máximo del modelo vía API v0."""
    import urllib.request, json
    try:
        url = f"{LMSTUDIO_API_BASE}/models/{model_id}"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = json.loads(r.read())
        return {
            "loaded": data.get("loaded_context_length", 0),
            "max":    data.get("max_context_length", 0),
        }
    except Exception:
        return {"loaded": 0, "max": 0}


def reload_model_with_context(model_id: str, context: int) -> bool:
    """Recarga el modelo con más contexto usando la CLI de lms."""
    lms_paths = [
        "/Users/xavi/.lmstudio/bin/lms",
        "/usr/local/bin/lms",
        "lms",
    ]
    lms_bin = next((p for p in lms_paths if Path(p).exists() or p == "lms"), None)
    if not lms_bin:
        return False

    log(f"Recargando modelo con contexto={context} tokens...")
    try:
        # Primero descargamos el modelo actual
        subprocess.run([lms_bin, "unload", model_id, "-y"],
                       capture_output=True, timeout=30)
        # Lo cargamos con el contexto solicitado
        result = subprocess.run(
            [lms_bin, "load", model_id, "-c", str(context), "-y"],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            log(f"Modelo recargado con {context} tokens de contexto ✓")
            return True
        else:
            warn(f"lms load falló: {result.stderr.strip()}")
            return False
    except Exception as e:
        warn(f"No se pudo recargar el modelo: {e}")
        return False


# ──────────────────────────────────────────────
# Audio / transcripción
# ──────────────────────────────────────────────

def extract_audio(input_path: Path, tmp_dir: str) -> Path:
    """Extrae audio en WAV mono 16kHz (óptimo para Whisper)."""
    audio_path = Path(tmp_dir) / "audio.wav"
    log(f"Extrayendo audio de {input_path.name}...")
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", str(input_path),
         "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", str(audio_path)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(f"ERROR: ffmpeg falló al procesar {input_path}")
    log(f"Audio extraído → {audio_path.name}")
    return audio_path



# Mapeo de nombres de modelo a repositorios HuggingFace para mlx-whisper
MLX_MODEL_REPOS = {
    "tiny":             "mlx-community/whisper-tiny-mlx",
    "base":             "mlx-community/whisper-base-mlx",
    "small":            "mlx-community/whisper-small-mlx",
    "medium":           "mlx-community/whisper-medium-mlx",
    "large":            "mlx-community/whisper-large-v3-mlx",
    "large-v3":         "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo":   "mlx-community/whisper-large-v3-turbo",
}


def transcribe(audio_path: Path, whisper_model: str) -> str:
    """Transcribe el audio usando mlx-whisper (GPU Apple Silicon) con fallback a CPU."""
    log(f"Transcribiendo con Whisper ({whisper_model})...")

    # ── Intento 1: mlx-whisper (Apple GPU + Neural Engine) ──────────────────
    try:
        import mlx_whisper  # type: ignore
        hf_repo = MLX_MODEL_REPOS.get(whisper_model, f"mlx-community/whisper-{whisper_model}-mlx")
        log(f"Backend: mlx-whisper → {hf_repo} (Apple GPU)")
        result = mlx_whisper.transcribe(str(audio_path), path_or_hf_repo=hf_repo, verbose=False)
        text = result["text"].strip()
        log(f"Transcripción completada ({len(text):,} caracteres)")
        return text
    except ImportError:
        warn("mlx-whisper no disponible. Instálalo con: pip3 install mlx-whisper")
    except Exception as e:
        warn(f"mlx-whisper falló ({e}). Usando CPU como fallback...")

    # ── Fallback: openai-whisper en CPU ─────────────────────────────────────
    try:
        import whisper  # type: ignore
    except ImportError:
        sys.exit("ERROR: ni mlx-whisper ni openai-whisper están instalados.")

    log("Backend: openai-whisper (CPU)")
    model = whisper.load_model(whisper_model, device="cpu")
    result = model.transcribe(str(audio_path), verbose=False)
    text = result["text"].strip()
    log(f"Transcripción completada ({len(text):,} caracteres)")
    return text


def transcribe_with_speakers(audio_path: Path, whisper_model: str) -> str:
    """Transcribe el audio e identifica quién habla en cada fragmento."""
    import os, warnings
    warnings.filterwarnings("ignore")

    hf_token = os.environ.get("HF_TOKEN")
    if not hf_token:
        sys.exit("ERROR: variable HF_TOKEN no definida. Añade 'export HF_TOKEN=...' a ~/.zshrc")

    # ── Paso 1: Transcripción con timestamps por segmento (openai-whisper) ──
    log(f"Transcribiendo con Whisper ({whisper_model}) + timestamps...")
    try:
        import whisper  # type: ignore
    except ImportError:
        sys.exit("ERROR: openai-whisper no instalado. Ejecuta: pip3 install openai-whisper")

    log("Backend: openai-whisper (CPU) — requerido para diarización")
    wmodel = whisper.load_model(whisper_model, device="cpu")
    w_result = wmodel.transcribe(str(audio_path), verbose=False, word_timestamps=False)
    segments = w_result["segments"]  # lista de {start, end, text}
    log(f"Transcripción completada ({len(segments)} segmentos)")

    # ── Paso 2: Diarización con pyannote en GPU (MPS) ───────────────────────
    log("Cargando pipeline de diarización (pyannote)...")
    try:
        import torch
        # Parche necesario para compatibilidad con PyTorch ≥ 2.6
        _orig_load = torch.load
        torch.load = lambda *a, **kw: _orig_load(*a, **{**kw, "weights_only": False})

        from pyannote.audio import Pipeline  # type: ignore
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token,
        )
        torch.load = _orig_load  # restaurar

        # Usar GPU Apple Silicon si está disponible
        if torch.backends.mps.is_available():
            pipeline.to(torch.device("mps"))
            log("Diarización en GPU (MPS)")
        else:
            log("Diarización en CPU (MPS no disponible)")

    except ImportError:
        sys.exit("ERROR: pyannote.audio no instalado. Ejecuta: pip3 install pyannote.audio")
    except Exception as e:
        sys.exit(f"ERROR cargando pyannote: {e}")

    log("Ejecutando diarización...")
    diarization = pipeline(str(audio_path))

    # Construir lista de turnos: [(start, end, speaker), ...]
    turns = [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in diarization.itertracks(yield_label=True)
    ]

    # ── Paso 3: Calcular tiempo total y % por hablante ──────────────────────
    speaker_time: dict[str, float] = {}
    for t_start, t_end, speaker in turns:
        speaker_time[speaker] = speaker_time.get(speaker, 0.0) + (t_end - t_start)

    total_time = sum(speaker_time.values())
    speaker_stats = {
        sp: {"seconds": secs, "pct": round(secs / total_time * 100, 1)}
        for sp, secs in sorted(speaker_time.items(), key=lambda x: -x[1])
        if (secs / total_time * 100) >= 2.0  # filtrar artefactos de diarización
    }
    n_speakers = len(speaker_stats)
    log(f"Diarización completada ({n_speakers} hablante(s) detectado(s))")

    # ── Paso 4: Asignar cada segmento de Whisper al hablante correcto ────────
    def find_speaker(start: float, end: float) -> str:
        """Devuelve el hablante con mayor solapamiento temporal."""
        best_speaker, best_overlap = "Desconocido", 0.0
        for t_start, t_end, speaker in turns:
            overlap = max(0, min(end, t_end) - max(start, t_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = speaker
        return best_speaker

    # ── Paso 5: Construir texto con etiquetas de hablante ───────────────────
    lines = []
    current_speaker = None
    buffer = []

    for seg in segments:
        speaker = find_speaker(seg["start"], seg["end"])
        if speaker != current_speaker:
            if buffer and current_speaker:
                lines.append(f"**{current_speaker}:** {''.join(buffer).strip()}")
            current_speaker = speaker
            buffer = [seg["text"]]
        else:
            buffer.append(seg["text"])

    if buffer and current_speaker:
        lines.append(f"**{current_speaker}:** {''.join(buffer).strip()}")

    full_text = "\n\n".join(lines)
    log(f"Texto con hablantes generado ({len(full_text):,} caracteres)")

    # ── Paso 7: Resolver nombres reales vía LLM ─────────────────────────────
    import os
    llm_model_env = os.environ.get("DEFAULT_LLM_MODEL", DEFAULT_LLM_MODEL)
    speaker_ids   = list(speaker_stats.keys())
    log("Buscando presentaciones de hablantes en la transcripción...")
    name_map = resolve_speaker_names(full_text, speaker_ids, llm_model_env)

    if name_map:
        identified = ", ".join(f"{k} → {v}" for k, v in name_map.items())
        log(f"Nombres identificados: {identified}")
        # Reemplazar etiquetas en el texto: SPEAKER_00 → SPEAKER_00 (Juan)
        for spk, name in name_map.items():
            full_text = full_text.replace(f"**{spk}:**", f"**{spk} ({name}):**")
    else:
        log("No se detectaron presentaciones de hablantes")

    # ── Paso 8: Bloque Markdown con estadísticas de participación ───────────
    def fmt_time(secs: float) -> str:
        m, s = divmod(int(secs), 60)
        return f"{m}m {s:02d}s"

    stats_lines = ["## 👥 Participantes", ""]
    for sp, data in speaker_stats.items():
        label = f"{sp} ({name_map[sp]})" if sp in name_map else sp
        bar   = "█" * int(data["pct"] / 5)
        stats_lines.append(
            f"- **{label}** — {data['pct']}% · {fmt_time(data['seconds'])}  `{bar}`"
        )
    stats_lines += ["", f"> Duración total detectada: {fmt_time(total_time)}", ""]
    speaker_block = "\n".join(stats_lines)

    return full_text, speaker_block


# ──────────────────────────────────────────────
# Generación de Markdown
# ──────────────────────────────────────────────

def call_llm(client, model: str, system: str, user: str) -> str:
    """Llama al LLM y devuelve el texto generado."""
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": user},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content.strip()


def resolve_speaker_names(transcript: str, speakers: list[str], llm_model: str) -> dict[str, str]:
    """
    Usa el LLM para detectar nombres reales a partir de presentaciones en la
    transcripción. Devuelve un dict {SPEAKER_XX: "Nombre"} solo para los
    hablantes identificados; los no identificados no aparecen en el dict.
    """
    import json, os

    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        return {}

    client = OpenAI(
        base_url=os.environ.get("LMSTUDIO_URL", "http://localhost:1234") + "/v1",
        api_key="lm-studio",
    )

    speakers_list = ", ".join(speakers)
    system = (
        "Eres un asistente que analiza transcripciones para identificar el nombre real "
        "de cada hablante cuando este se presenta explícitamente. "
        "Responde ÚNICAMENTE con un objeto JSON válido sin texto adicional ni bloques de código."
    )
    user = f"""En esta transcripción los hablantes están etiquetados como: {speakers_list}

Analiza el texto y detecta si algún hablante dice su nombre (presentaciones del tipo
"Hola, soy Juan", "Me llamo Ana", "My name is Sarah", "I'm John", "Buenos días, soy el Dr. García", etc.)

Devuelve SOLO un JSON con el mapeo de etiqueta a nombre real, únicamente para los hablantes
que puedas identificar con seguridad. Ejemplo: {{"SPEAKER_00": "Juan", "SPEAKER_01": "Ana"}}
Si no identificas a ninguno, devuelve: {{}}

--- TRANSCRIPCIÓN ---
{transcript[:6000]}
--- FIN ---"""

    try:
        raw = call_llm(client, llm_model, system, user)
        # Extraer el JSON aunque venga con texto alrededor
        start = raw.find("{")
        end   = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return {}
        mapping = json.loads(raw[start:end])
        # Filtrar solo las claves que correspondan a speakers reales
        return {k: v for k, v in mapping.items() if k in speakers and isinstance(v, str) and v.strip()}
    except Exception as e:
        warn(f"No se pudo resolver nombres de hablantes: {e}")
        return {}


def split_into_chunks(text: str, max_chars: int) -> list[str]:
    """Divide el texto en chunks respetando párrafos/frases."""
    chunks, current = [], []
    current_len = 0

    for paragraph in text.split("\n"):
        para_len = len(paragraph) + 1
        if current_len + para_len > max_chars and current:
            chunks.append("\n".join(current).strip())
            current, current_len = [], 0
        current.append(paragraph)
        current_len += para_len

    if current:
        chunks.append("\n".join(current).strip())

    return [c for c in chunks if c]


def generate_markdown(transcript: str, llm_model: str, input_name: str,
                       requested_context: int, style: str = "normal") -> str:
    """
    Estrategia:
    1. Consulta el contexto cargado.
    2. Si el texto cabe → envía directo.
    3. Si no cabe → intenta recargar el modelo con más contexto.
    4. Si aún no cabe (o falla la recarga) → procesa por chunks y consolida.
    """
    try:
        from openai import OpenAI  # type: ignore
    except ImportError:
        sys.exit("ERROR: openai no instalado. Ejecuta: pip3 install openai")

    client = OpenAI(base_url=LMSTUDIO_BASE_URL, api_key="lm-studio")

    # ── 1. Ver contexto actual ──────────────────
    ctx = get_model_context(llm_model)
    system_prompt = SYSTEM_PROMPTS.get(style, SYSTEM_PROMPTS["normal"])
    log(f"Estilo de resumen: {style}")

    loaded_ctx = ctx["loaded"] or DEFAULT_CONTEXT
    log(f"Contexto del modelo: {loaded_ctx:,} tokens cargados / {ctx['max']:,} máximo")

    # Estimación de tokens necesarios (texto + system prompt + margen respuesta)
    overhead_chars = (len(system_prompt) + 500) * CHARS_PER_TOKEN
    text_chars     = len(transcript)
    needed_tokens  = int((text_chars + overhead_chars) / CHARS_PER_TOKEN)
    usable_tokens  = int(loaded_ctx * CONTEXT_USE_RATIO)

    log(f"Estimación necesaria: ~{needed_tokens:,} tokens | Disponible: ~{usable_tokens:,}")

    # ── 2. Intentar ampliar contexto si hace falta ─
    if needed_tokens > usable_tokens:
        target_ctx = min(max(needed_tokens * 2, requested_context), ctx["max"] or requested_context)
        warn(f"Transcripción demasiado larga para {loaded_ctx:,} tokens.")
        log(f"Intentando recargar con {target_ctx:,} tokens...")

        reloaded = reload_model_with_context(llm_model, target_ctx)
        if reloaded:
            ctx = get_model_context(llm_model)
            loaded_ctx = ctx["loaded"] or target_ctx
            usable_tokens = int(loaded_ctx * CONTEXT_USE_RATIO)
            log(f"Contexto actualizado: {loaded_ctx:,} tokens")

    # ── 3. Intento directo ──────────────────────
    max_chars_direct = int(usable_tokens * CHARS_PER_TOKEN)

    if text_chars <= max_chars_direct:
        log(f"Generando Markdown (modo directo) con {llm_model}...")
        user_msg = (f"Archivo original: {input_name}\n\n"
                    f"--- TRANSCRIPCIÓN ---\n{transcript}\n--- FIN TRANSCRIPCIÓN ---\n\n"
                    "Genera el documento Markdown estructurado.")
        try:
            return call_llm(client, llm_model, system_prompt, user_msg)
        except Exception as e:
            err_str = str(e)
            # Si el error es de contexto insuficiente, intentar recargar con más tokens
            if "n_ctx" in err_str or "context length" in err_str.lower() or "400" in err_str:
                warn(f"Contexto insuficiente en el modelo ({e}). Intentando recargar...")
                target_ctx = max(requested_context, needed_tokens * 2)
                reloaded = reload_model_with_context(llm_model, target_ctx)
                if reloaded:
                    ctx = get_model_context(llm_model)
                    loaded_ctx = ctx["loaded"] or target_ctx
                    usable_tokens = int(loaded_ctx * CONTEXT_USE_RATIO)
                    log(f"Reintentando modo directo con {loaded_ctx:,} tokens de contexto...")
                    try:
                        return call_llm(client, llm_model, system_prompt, user_msg)
                    except Exception as e2:
                        warn(f"Reintento fallido ({e2}). Cambiando a modo por chunks...")
                else:
                    warn("No se pudo recargar el modelo. Cambiando a modo por chunks...")
            else:
                warn(f"Modo directo falló ({e}). Cambiando a modo por chunks...")

    # ── 4. Modo por chunks ──────────────────────
    # Reservamos ~60% del contexto para el texto de cada chunk
    chunk_chars = int(usable_tokens * CHARS_PER_TOKEN * 0.60)
    chunks = split_into_chunks(transcript, chunk_chars)
    log(f"Procesando en {len(chunks)} fragmento(s) de ~{chunk_chars:,} chars cada uno...")

    summaries = []
    for i, chunk in enumerate(chunks, 1):
        log(f"  Fragmento {i}/{len(chunks)} ({len(chunk):,} chars)...")
        user_msg = (f"Fragmento {i} de {len(chunks)} — Archivo: {input_name}\n\n"
                    f"--- FRAGMENTO ---\n{chunk}\n--- FIN FRAGMENTO ---")
        try:
            summary = call_llm(client, llm_model, CHUNK_SYSTEM_PROMPT, user_msg)
            summaries.append(f"### Fragmento {i}\n{summary}")
        except Exception as e:
            warn(f"Error en fragmento {i}: {e}")
            summaries.append(f"### Fragmento {i}\n[Error al procesar este fragmento]")

    # ── 5. Consolidar resúmenes ─────────────────
    log("Consolidando fragmentos en documento final...")
    combined = "\n\n".join(summaries)
    user_msg = (f"Archivo original: {input_name}\n\n"
                f"A continuación los puntos clave de {len(chunks)} fragmentos:\n\n"
                f"{combined}\n\nGenera el documento Markdown final consolidado.")
    try:
        return call_llm(client, llm_model, system_prompt, user_msg)
    except Exception as e:
        # Último recurso: devolver los resúmenes tal cual
        warn(f"Consolidación falló ({e}). Devolviendo resúmenes sin consolidar.")
        return f"# Notas: {input_name}\n\n> ⚠️ Procesado en {len(chunks)} fragmentos\n\n" + combined


# ──────────────────────────────────────────────
# Exportación PDF
# ──────────────────────────────────────────────

def export_pdf(md_path: Path) -> None:
    """Convierte el fichero Markdown a PDF usando pandoc + xelatex."""
    pdf_path = md_path.with_suffix(".pdf")
    log("Exportando a PDF con pandoc + xelatex...")
    result = subprocess.run(
        [
            PANDOC_PATH, str(md_path),
            "-o", str(pdf_path),
            f"--pdf-engine={XELATEX_PATH}",
            "-V", "mainfont=Times New Roman",
            "-V", "sansfont=Helvetica Neue",
            "-V", "monofont=Menlo",
            "-V", "geometry:margin=2.5cm",
            "-V", "colorlinks=true",
            "-V", "linkcolor=NavyBlue",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log(f"PDF generado → {pdf_path.name}")
    else:
        warn(f"pandoc falló al generar el PDF:\n{result.stderr.strip()}")


def export_docx(md_path: Path) -> None:
    """Convierte el fichero Markdown a Word (.docx) usando pandoc."""
    docx_path = md_path.with_suffix(".docx")
    log("Exportando a Word (.docx) con pandoc...")
    result = subprocess.run(
        [PANDOC_PATH, str(md_path), "-o", str(docx_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        log(f"Word generado → {docx_path.name}")
    else:
        warn(f"pandoc falló al generar el Word:\n{result.stderr.strip()}")


# ──────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convierte MP4/MP3 a Markdown estructurado usando Whisper + LM Studio"
    )
    parser.add_argument("input", help="Fichero de entrada (.mp4, .mp3, .m4a, .wav, .mov, etc.)")
    parser.add_argument("--output", "-o", help="Fichero de salida .md (por defecto: mismo nombre que entrada)")
    parser.add_argument("--model", "-m", default=DEFAULT_LLM_MODEL,
                        help=f"Modelo(s) LM Studio, separados por coma (default: {DEFAULT_LLM_MODEL})")
    parser.add_argument("--whisper-model", "-w", default=DEFAULT_WHISPER_MODEL,
                        help=f"Tamaño del modelo Whisper: tiny/base/small/medium/large (default: {DEFAULT_WHISPER_MODEL})")
    parser.add_argument("--context", "-c", type=int, default=DEFAULT_CONTEXT,
                        help=f"Tokens de contexto a solicitar al recargar el modelo (default: {DEFAULT_CONTEXT})")
    parser.add_argument("--style", "-s", default=DEFAULT_STYLE,
                        choices=["executive", "normal", "detailed"],
                        help="Estilo del resumen: executive (alto nivel), normal (default), detailed (exhaustivo)")
    parser.add_argument("--diarize", "-d", action="store_true", default=DEFAULT_DIARIZE,
                        help="Identificar hablantes (requiere HF_TOKEN en el entorno)")
    parser.add_argument("--transcript-only", action="store_true",
                        help="Solo transcribir, sin pasar por LM Studio")
    parser.add_argument("--save-transcript", action="store_true",
                        help="Guardar también la transcripción en .txt")
    parser.add_argument("--no-pdf", action="store_true", default="pdf" not in DEFAULT_FORMATS,
                        help="No exportar a PDF")
    parser.add_argument("--docx", action="store_true", default="docx" in DEFAULT_FORMATS,
                        help="Exportar también a Word (.docx) usando pandoc")
    args = parser.parse_args()

    input_path = Path(args.input).resolve()
    if not input_path.exists():
        sys.exit(f"ERROR: No se encuentra el fichero: {input_path}")

    # Soporte de múltiples modelos separados por coma
    models = [m.strip() for m in args.model.split(",") if m.strip()]

    output_path = Path(args.output) if args.output else input_path.with_suffix(".md")

    print(f"\n🎬 media2md — {input_path.name}", file=sys.stderr)
    print("─" * 50, file=sys.stderr)
    _start_time = __import__("time").time()

    with tempfile.TemporaryDirectory() as tmp_dir:
        # 1. Extraer audio
        if input_path.suffix.lower() == ".wav":
            audio_path = input_path
        else:
            audio_path = extract_audio(input_path, tmp_dir)

        # 2. Transcribir (con o sin diarización)
        speaker_block = None
        if args.diarize:
            transcript, speaker_block = transcribe_with_speakers(audio_path, args.whisper_model)
        else:
            transcript = transcribe(audio_path, args.whisper_model)

        if args.save_transcript:
            transcript_path = input_path.with_suffix(".txt")
            transcript_path.write_text(transcript, encoding="utf-8")
            log(f"Transcripción guardada → {transcript_path}")

        if args.transcript_only:
            output_path.write_text(
                f"# Transcripción: {input_path.name}\n\n{transcript}\n",
                encoding="utf-8"
            )
            print(f"\n✅ Transcripción guardada en: {output_path}", file=sys.stderr)
            return

        # 3. Generar un informe por cada modelo
        for llm_model in models:
            # Determinar ruta de salida: si hay >1 modelo, añadir sufijo con nombre corto
            if len(models) == 1:
                md_path = output_path
            else:
                safe_model = re.sub(r'[\\/:*?"<>| ]', "_", llm_model)
                md_path = input_path.with_name(
                    input_path.stem + f"_{safe_model}.md"
                )

            log(f"Generando resumen con modelo: {llm_model}")
            markdown = generate_markdown(transcript, llm_model, input_path.name,
                                         args.context, args.style)

            # Insertar bloque de participantes tras el título si hay diarización
            if speaker_block:
                lines_md = markdown.split("\n", 1)
                markdown = (lines_md[0] + "\n\n" + speaker_block
                            + ("\n" + lines_md[1] if len(lines_md) > 1 else ""))

            # Añadir metadata del modelo al final del documento
            markdown += (
                f"\n\n---\n"
                f"> 🤖 Generado con **{llm_model}** · "
                f"Whisper `{args.whisper_model}` · "
                f"Estilo `{args.style}`  \n"
                f"> Fichero original: `{input_path.name}`\n"
            )

            md_path.write_text(markdown, encoding="utf-8")
            log(f"Markdown guardado → {md_path.name}")

            if not args.no_pdf:
                export_pdf(md_path)

            if args.docx:
                export_docx(md_path)

            print(f"\n✅ Markdown guardado en: {md_path}", file=sys.stderr)
            if not args.no_pdf:
                print(f"✅ PDF guardado en:      {md_path.with_suffix('.pdf')}", file=sys.stderr)
            if args.docx:
                print(f"✅ Word guardado en:     {md_path.with_suffix('.docx')}", file=sys.stderr)

    elapsed = __import__("time").time() - _start_time
    m, s = divmod(int(elapsed), 60)
    elapsed_str = f"{m}m {s:02d}s" if m else f"{s}s"
    print(f"\n   Modelos usados: {', '.join(models)}", file=sys.stderr)
    print(f"   Modelo Whisper: {args.whisper_model}", file=sys.stderr)
    print(f"   Tiempo total:   {elapsed_str}\n", file=sys.stderr)


if __name__ == "__main__":
    main()
