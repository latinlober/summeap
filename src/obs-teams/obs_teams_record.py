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
import subprocess
from datetime import datetime
from pathlib import Path

# ── Configuración ─────────────────────────────────────────────────────────────
OBS_HOST       = "localhost"
OBS_PORT       = 4455
OBS_PASSWORD   = "your_obs_websocket_password"   # OBS → Tools → WebSocket Server Settings
OBS_SCENE      = "Teams"
RECORDINGS_DIR = Path.home() / "Movies"           # folder where OBS saves recordings
MEDIA2MD       = str(Path.home() / "bin" / "media2md.py")
HF_TOKEN       = "your_huggingface_token"         # only needed for --diarize
PYTHON         = "/usr/bin/python3"
EXTRA_PATH     = "/usr/local/bin:/opt/homebrew/bin"
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


def _prompt_transcribe(video_path: Path) -> None:
    """Pregunta via diálogo si quiere transcribir y lanza media2md en Terminal."""
    import stat, tempfile

    script = f"""tell application "System Events"
    set opts to {{"Solo MD", "MD + PDF", "MD + Word", "MD + PDF + Word", "MD + Diarización", "MD + Diarización + PDF", "MD + Diarización + Word", "Cancelar"}}
    set resp to choose from list opts ¬
        with title "OBS Teams · {video_path.name}" ¬
        with prompt "¿Generar resumen con media2md?" ¬
        default items {{"MD + Word"}}
    if resp is false then return "Cancelar"
    return item 1 of resp
end tell"""
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    choice = result.stdout.strip()

    if choice in ("Cancelar", ""):
        print("   Transcripción omitida")
        return

    diarize_flag  = "--diarize"  if "Diarización" in choice else ""
    pdf_flag      = ""           if "PDF"         in choice else "--no-pdf"
    docx_flag     = "--docx"     if "Word"        in choice else ""
    log_path      = video_path.with_suffix(".log")

    # Escribir el comando en un script temporal para evitar problemas de quoting.
    # Al terminar, el script se cierra usando el ID de tab que AppleScript nos
    # devuelve al lanzarlo — guardado en /tmp para que el bash lo use.
    close_cmd = (
        'osascript -e "tell application \\"Terminal\\" to close tab'
        ' (tab 1 of (every window whose frontmost is true))" 2>/dev/null || true'
    )
    lines = [
        "#!/bin/bash",
        f"export HF_TOKEN={HF_TOKEN!r}",
        f"export PATH={EXTRA_PATH!r}:$PATH",
        (f"{PYTHON} {MEDIA2MD} {diarize_flag} {pdf_flag} {docx_flag} --style detailed --save-transcript {str(video_path)!r}"
         f" 2>&1 | tee {str(log_path)!r}"),
        "echo '--- Proceso completado. Cerrando ventana en 3s ---'",
        "sleep 3",
        close_cmd,
    ]
    tmp = Path(tempfile.mktemp(suffix=".sh"))
    tmp.write_text("\n".join(lines) + "\n")
    tmp.chmod(tmp.stat().st_mode | stat.S_IEXEC | stat.S_IRUSR)

    # Lanzar en Terminal y obtener el ID del tab para que el script se cierre
    # exactamente a sí mismo, independientemente de qué ventana esté activa.
    applescript = f"""tell application "Terminal"
    activate
    set t to do script "bash {tmp}"
    set tab_id to tab_id of t
    set win_id to id of (window 1 where (exists (tabs whose tab_id is tab_id)))
    return (win_id as string) & ":" & (tab_id as string)
end tell"""
    id_result = subprocess.run(["osascript", "-e", applescript],
                               capture_output=True, text=True).stdout.strip()

    # Reescribir el script añadiendo el comando de cierre con IDs exactos
    if ":" in id_result:
        win_id, tab_id = id_result.split(":", 1)
        close_exact = (
            f'osascript -e "tell application \\"Terminal\\" to close'
            f' (tab {tab_id} of window id {win_id})" 2>/dev/null || true'
        )
        updated_lines = [l for l in lines if "close tab" not in l] + [
            "echo '--- Proceso completado. Cerrando ventana en 3s ---'",
            "sleep 3",
            close_exact,
        ]
        # Eliminar el echo/sleep/close originales y reemplazar
        core_lines = [l for l in lines
                      if not l.startswith("echo '---") and "sleep 3" not in l
                      and "close tab" not in l]
        final_lines = core_lines + [
            "echo '--- Proceso completado. Cerrando ventana en 3s ---'",
            "sleep 3",
            close_exact,
        ]
        tmp.write_text("\n".join(final_lines) + "\n")

    print(f"   Lanzando media2md en Terminal ({choice})...")


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
