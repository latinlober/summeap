#!/usr/bin/env python3
"""
obs_teams_record.py — Controla la grabación de OBS para Teams
Llamado desde Hammerspoon al pulsar la hotkey.

Uso:
  python3 obs_teams_record.py start    → cambia a escena Teams y empieza a grabar
  python3 obs_teams_record.py stop     → para la grabación
  python3 obs_teams_record.py toggle   → alterna start/stop
  python3 obs_teams_record.py status   → devuelve 'recording' o 'stopped'
"""

import re
import sys
import os
import json
import subprocess
from datetime import datetime
from pathlib import Path

# ── Configuración ─────────────────────────────────────────────────────────────
# Values are loaded from ~/.config/summeap/config.json when available.
# The hardcoded values below serve as fallback defaults.

def _load_cfg() -> dict:
    cfg_path = Path.home() / ".config" / "summeap" / "config.json"
    if cfg_path.exists():
        try:
            return json.loads(cfg_path.read_text())
        except Exception:
            pass
    return {}

_cfg = _load_cfg()

OBS_HOST       = _cfg.get("obs_host",        "localhost")
OBS_PORT       = int(_cfg.get("obs_port",    4455))
OBS_PASSWORD   = _cfg.get("obs_password",    "your_obs_websocket_password")
OBS_SCENE      = _cfg.get("obs_scene",       "Teams")
RECORDINGS_DIR = Path(_cfg.get("recordings_dir", str(Path.home() / "Movies")))
MEDIA2MD       = _cfg.get("media2md_path",   str(Path.home() / "bin" / "media2md.py"))
HF_TOKEN       = _cfg.get("hf_token",        "")
PYTHON         = _cfg.get("python_path",     "/usr/bin/python3")
EXTRA_PATH     = _cfg.get("extra_path",      "/usr/local/bin:/opt/homebrew/bin:/Users/xavi/Library/Python/3.9/bin")
# ─────────────────────────────────────────────────────────────────────────────

# Fichero temporal donde se persiste el título entre invocaciones separadas
_TITLE_FILE = Path("/tmp/obs_meeting_title.txt")

# Título de la reunión capturado en start_recording, usado al renombrar en stop
_meeting_title: str = ""


def get_client():
    try:
        import obsws_python as obs  # type: ignore
        return obs.ReqClient(host=OBS_HOST, port=OBS_PORT, password=OBS_PASSWORD, timeout=10)
    except ImportError:
        sys.exit("ERROR: obsws-python no instalado. Ejecuta: pip3 install obsws-python")
    except Exception as e:
        sys.exit(f"ERROR conectando con OBS: {e}\n¿Está OBS abierto con el WebSocket activo?")


def notify(title: str, message: str) -> None:
    """Muestra una notificación macOS."""
    subprocess.run([
        "osascript", "-e",
        f'display notification "{message}" with title "{title}" sound name "Glass"'
    ], capture_output=True)


def _fit_to_canvas(client, scene_name: str, source_name: str) -> None:
    """Ajusta el transform del source para ocupar todo el canvas (fit to screen)."""
    try:
        video    = client.get_video_settings()
        canvas_w = video.base_width
        canvas_h = video.base_height

        # Obtener el sceneItemId del source
        items   = client.get_scene_item_list(scene_name)
        item_id = next(
            (i["sceneItemId"] for i in items.scene_items if i["sourceName"] == source_name),
            None,
        )
        if item_id is None:
            print(f"⚠️  Source '{source_name}' no encontrado en escena '{scene_name}'")
            return

        client.set_scene_item_transform(scene_name, item_id, {
            "positionX":      0.0,
            "positionY":      0.0,
            "boundsType":     "OBS_BOUNDS_STRETCH",
            "boundsWidth":    float(canvas_w),
            "boundsHeight":   float(canvas_h),
            "boundsAlignment": 0,
            "alignment":      5,
            "rotation":       0.0,
        })
        print(f"Fit to screen → {canvas_w}x{canvas_h}")
    except Exception as e:
        print(f"⚠️  No se pudo aplicar fit to screen: {e}")


def start_recording() -> None:
    global _meeting_title
    client = get_client()

    # Cambiar a la escena Teams si existe
    scenes = [s["sceneName"] for s in client.get_scene_list().scenes]
    if OBS_SCENE in scenes:
        client.set_current_program_scene(OBS_SCENE)
        print(f"Escena cambiada a: {OBS_SCENE}")
    else:
        print(f"⚠️  Escena '{OBS_SCENE}' no encontrada. Usando escena activa.")
        print(f"   Escenas disponibles: {', '.join(scenes)}")

    # Reapuntar el Window Capture a la ventana de llamada de Teams
    # La ventana de llamada sigue el patrón: "[Microsoft Teams] Título | Microsoft Teams"
    # Las ventanas de chat empiezan por: "[Microsoft Teams] Chat|..."
    try:
        props = client.get_input_properties_list_property_items("macOS Window Capture", "window")
        call_window = next(
            (item for item in props.property_items
             if "| Microsoft Teams" in item["itemName"]
             and not item["itemName"].startswith("[Microsoft Teams] Chat")),
            None,
        )
        if call_window:
            client.set_input_settings(
                "macOS Window Capture",
                {"type": 1, "window": call_window["itemValue"]},
                overlay=True,
            )
            print(f"Window Capture → {call_window['itemName']}")
            # Extraer el título de la reunión del nombre de ventana:
            # "[Microsoft Teams] Título de la reunión | Microsoft Teams"
            m = re.match(r"^\[Microsoft Teams\]\s+(.+?)\s+\|\s+Microsoft Teams$",
                         call_window["itemName"])
            _meeting_title = m.group(1) if m else ""
            if _meeting_title:
                print(f"Título reunión: {_meeting_title}")
                _TITLE_FILE.write_text(_meeting_title)
            # Fit to screen: ajustar transform para ocupar todo el canvas
            _fit_to_canvas(client, OBS_SCENE, "macOS Window Capture")
        else:
            print("⚠️  No se encontró ventana de llamada Teams activa")
            print("   Ventanas Teams disponibles:")
            for item in props.property_items:
                if "teams" in item["itemName"].lower() or "Microsoft Teams" in item["itemName"]:
                    print(f"     · {item['itemName']}")
    except Exception as e:
        print(f"⚠️  No se pudo actualizar Window Capture: {e}")

    # Verificar que no esté ya grabando
    if client.get_record_status().output_active:
        print("OBS ya está grabando")
        notify("OBS Teams", "Ya está grabando")
        return

    client.start_record()
    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"✅ Grabación iniciada — {ts}")
    notify("🔴 OBS Teams", f"Grabación iniciada · {ts}")


def _rename_with_title(video_path: Path) -> Path:
    """Renombra el fichero añadiendo el título de la reunión como prefijo.

    Resultado: "<título> - 2026-04-28 16-16-21.mov"
    Carga el título desde disco para sobrevivir entre invocaciones de proceso.
    Caracteres no válidos en nombres de fichero son reemplazados por '_'.
    """
    title = _meeting_title
    if not title and _TITLE_FILE.exists():
        title = _TITLE_FILE.read_text().strip()
        _TITLE_FILE.unlink(missing_ok=True)
    if not title:
        return video_path
    safe_title = re.sub(r'[\\/:*?"<>|]', "_", title).strip()
    new_name = f"{safe_title} - {video_path.name}"
    new_path = video_path.parent / new_name
    try:
        video_path.rename(new_path)
        print(f"   Renombrado → {new_path.name}")
        return new_path
    except Exception as e:
        print(f"⚠️  No se pudo renombrar: {e}")
        return video_path


def stop_recording() -> None:
    client = get_client()

    if not client.get_record_status().output_active:
        print("OBS no está grabando")
        notify("OBS Teams", "No hay grabación activa")
        return

    result = client.stop_record()

    # output_path puede estar en la clase o en la instancia según versión de obsws-python
    raw_path = getattr(result, "output_path", None)
    output_path = Path(raw_path) if raw_path else None

    print("⏹️  Grabación detenida")

    if output_path and output_path.exists():
        output_path = _rename_with_title(output_path)
        print(f"   Fichero: {output_path}")
        notify("⏹️ OBS Teams", f"Grabación guardada: {output_path.name}")
        _prompt_transcribe(output_path)
    else:
        # Fallback: buscar el fichero más reciente en el directorio de grabaciones
        candidates = sorted(
            list(RECORDINGS_DIR.glob("*.mp4")) +
            list(RECORDINGS_DIR.glob("*.mkv")) +
            list(RECORDINGS_DIR.glob("*.mov")),
            key=lambda f: f.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            latest = _rename_with_title(candidates[0])
            print(f"   Fichero más reciente: {latest}")
            notify("⏹️ OBS Teams", f"Grabación guardada: {latest.name}")
            _prompt_transcribe(latest)
        else:
            notify("⏹️ OBS Teams", "Grabación detenida")


def _wait_for_file_ready(path: Path, timeout: int = 60, stable_secs: int = 3) -> bool:
    """Wait until the file exists and its size has been stable for stable_secs seconds.
    Returns True if ready, False if timed out."""
    import time
    print(f"   Esperando a que OBS finalice la escritura de {path.name}…")
    deadline = time.time() + timeout
    last_size = -1
    stable_since = None
    while time.time() < deadline:
        if path.exists() and path.stat().st_size > 0:
            size = path.stat().st_size
            if size == last_size:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= stable_secs:
                    print(f"   Fichero listo ({size // 1024} KB)")
                    return True
            else:
                last_size = size
                stable_since = None
        time.sleep(1)
    print(f"   ⚠️  Timeout esperando fichero: {path.name}")
    return False


def _prompt_transcribe(video_path: Path) -> None:
    """Lanza media2md usando la configuración de settings, sin diálogo."""
    import stat, tempfile

    # Wait for OBS to finish writing the file before processing
    if not _wait_for_file_ready(video_path):
        notify("⚠️ Summeap", f"Fichero no disponible: {video_path.name}")
        return

    # Read flags directly from config — no dialog shown
    _fmt     = {f.strip().lower() for f in _cfg.get("default_formats", "pdf,docx").split(",") if f.strip()}
    _diarize = bool(_cfg.get("default_diarize", "").strip())

    diarize_flag = "--diarize" if _diarize  else ""
    pdf_flag     = ""          if "pdf"  in _fmt else "--no-pdf"
    docx_flag    = "--docx"    if "docx" in _fmt else ""
    log_path     = video_path.with_suffix(".log")

    print(f"   Iniciando media2md: diarize={_diarize} pdf={'pdf' in _fmt} docx={'docx' in _fmt}")

    # Write a job file for the statusbar app to pick up and run with live output
    import json as _json
    job = {
        "video_path":   str(video_path),
        "python":       PYTHON,
        "media2md":     MEDIA2MD,
        "hf_token":     HF_TOKEN,
        "extra_path":   EXTRA_PATH,
        "diarize_flag": diarize_flag,
        "pdf_flag":     pdf_flag,
        "docx_flag":    docx_flag,
    }
    job_path = Path("/tmp/summeap_job.json")
    job_path.write_text(_json.dumps(job))
    print(f"   Job escrito en {job_path}")


def toggle_recording() -> None:
    client = get_client()
    if client.get_record_status().output_active:
        stop_recording()
    else:
        start_recording()


def status() -> None:
    client = get_client()
    active = client.get_record_status().output_active
    print("recording" if active else "stopped")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "toggle"
    actions = {"start": start_recording, "stop": stop_recording,
                "toggle": toggle_recording, "status": status}
    if cmd not in actions:
        sys.exit(f"Uso: {sys.argv[0]} start|stop|toggle|status")
    actions[cmd]()
