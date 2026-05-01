-- ─────────────────────────────────────────────────────────────────────────────
-- Hammerspoon config — OBS Teams Recorder
-- Hotkey: Cmd+Shift+R → toggle OBS recording (Teams scene)
-- Copy this file to ~/.hammerspoon/init.lua and reload Hammerspoon.
-- ─────────────────────────────────────────────────────────────────────────────

local OBS_SCRIPT = os.getenv("HOME") .. "/bin/obs_teams_record.py"
local PYTHON     = "/usr/bin/python3"

-- Indicador visual en la menubar
local menubar = hs.menubar.new()

local function updateMenubar(recording)
    if recording then
        menubar:setTitle("🔴 REC")
        menubar:setTooltip("OBS grabando Teams — Cmd+Shift+R para parar")
    else
        menubar:setTitle("⚫ REC")
        menubar:setTooltip("OBS en espera — Cmd+Shift+R para grabar Teams")
    end
end

-- Estado inicial
local function checkStatus()
    local out, ok, _, rc = hs.execute(PYTHON .. " " .. OBS_SCRIPT .. " status 2>/dev/null")
    updateMenubar(type(out) == "string" and out:match("recording") ~= nil)
end

-- Toggle grabación
local function toggleRecording()
    hs.notify.new({title="OBS Teams", informativeText="Procesando..."}):send()
    hs.task.new(PYTHON, function(code, stdout, stderr)
        local recording = stdout and stdout:match("recording") ~= nil
        updateMenubar(recording)
    end, {OBS_SCRIPT, "toggle"}):start()
end

-- Hotkey global: Cmd + Shift + Ctrl + R
hs.hotkey.bind({"cmd", "shift"}, "R", toggleRecording)

-- Actualizar estado del menubar al arrancar
checkStatus()

hs.alert.show("⌨️  Hammerspoon cargado · Cmd+Shift+R = grabar Teams")
