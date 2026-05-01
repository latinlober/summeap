"""
settings_window.py — Single-window settings panel for Summeap
Built with AppKit (PyObjC, already installed with rumps).

Features:
- Single instance enforced (second call brings existing window to front)
- Select (NSPopUpButton) for enum fields
- Help (?) button per row showing a tooltip alert
"""

import objc
from pathlib import Path
from typing import Optional
from AppKit import (
    NSPanel, NSView, NSTextField, NSSecureTextField, NSButton,
    NSScrollView, NSFont, NSMakeRect, NSPopUpButton,
    NSTextAlignmentRight, NSBezelStyleRounded, NSBezelStyleHelpButton,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSApp, NSFloatingWindowLevel, NSObject, NSAlert,
    NSMomentaryLightButton, NSButtonTypeToggle,
)
from Foundation import NSPoint

import config as _config

# ── Layout ────────────────────────────────────────────────────────────────────
WIN_W      = 600
LABEL_W    = 175
FIELD_W    = 300
HELP_W     = 22
ROW_H      = 24
ROW_GAP    = 7
SEC_GAP    = 16
MARGIN_X   = 20
MARGIN_TOP = 16
FONT       = NSFont.systemFontOfSize_(12)
FONT_BOLD  = NSFont.boldSystemFontOfSize_(12)
FONT_SMALL = NSFont.systemFontOfSize_(10)
# ─────────────────────────────────────────────────────────────────────────────

# Field spec: (label, config_key, widget, placeholder_or_options, help_text)
# widget: "text" | "password" | "select"
SECTIONS = [
    ("OBS Connection", [
        ("Host",        "obs_host",     "text",     "localhost",
         "Hostname or IP where OBS is running. Use 'localhost' if OBS is on the same machine."),
        ("Port",        "obs_port",     "text",     "4455",
         "OBS WebSocket server port. Default is 4455.\nChange in OBS → Tools → WebSocket Server Settings."),
        ("Password",    "obs_password", "password", "WebSocket server password",
         "Password set in OBS → Tools → WebSocket Server Settings.\nLeave empty if authentication is disabled."),
        ("Scene Name",  "obs_scene",    "text",     "Teams",
         "Name of the OBS scene used for recording.\nThe scene must contain a source named 'macOS Window Capture'."),
    ]),
    ("Paths", [
        ("Recordings Folder",   "recordings_dir",  "text", str(Path.home() / "Movies"),
         "Folder where OBS saves recording files.\nSet in OBS → Settings → Output → Recording Path."),
        ("media2md.py",         "media2md_path",   "text", "~/bin/media2md.py",
         "Full path to the media2md.py script that generates summaries."),
        ("obs_teams_record.py", "obs_script_path", "text", "~/bin/obs_teams_record.py",
         "Full path to obs_teams_record.py, which controls OBS recording."),
        ("Python",              "python_path",     "text", "/usr/bin/python3",
         "Python interpreter used to run the scripts.\nRun 'which python3' in Terminal to find the correct path."),
        ("Extra PATH",          "extra_path",      "text", "/usr/local/bin:/opt/homebrew/bin",
         "Additional directories prepended to PATH when running scripts.\nAdd Homebrew's bin if tools like ffmpeg are installed there."),
    ]),
    ("AI Models", [
        ("LLM Model",     "llm_model",     "text",   "google/gemma-4-26b-a4b",
         "Model ID as shown in LM Studio. Must be loaded and running on the local server.\nExample: google/gemma-4-26b-a4b"),
        ("Whisper Model", "whisper_model", "select", ["large-v3-turbo", "large-v3", "large",
                                                       "medium", "small", "base", "tiny"],
         "Whisper model size for transcription.\nLarger = more accurate but slower.\n'large-v3-turbo' is the best balance for Apple Silicon."),
        ("Default Style", "default_style", "select", ["detailed", "normal", "executive"],
         "Summary verbosity:\n• detailed — exhaustive notes, quotes, action items\n• normal — balanced summary with key points\n• executive — brief high-level overview only"),
    ]),
    ("HuggingFace", [
        ("HF Token", "hf_token", "password", "hf_...",
         "HuggingFace access token — only required when using speaker diarization (--diarize).\nGet yours at huggingface.co/settings/tokens\nYou also need to accept the pyannote model terms on HuggingFace."),
    ]),
]

# ── Singleton panel ───────────────────────────────────────────────────────────
_active_panel:    Optional[NSPanel]   = None
_active_delegate: Optional[NSObject]  = None


def show_settings(on_save=None):
    global _active_panel, _active_delegate

    # Enforce single instance
    if _active_panel is not None:
        _active_panel.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        return

    cfg       = _config.load()
    content_h = _content_height()
    visible_h = min(content_h, 580)
    btn_area  = 50

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, WIN_W, visible_h + btn_area),
        (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
         | NSWindowStyleMaskResizable),
        NSBackingStoreBuffered,
        False,
    )
    panel.setTitle_("Summeap — Settings")
    panel.setLevel_(NSFloatingWindowLevel)
    panel.center()

    # Content view
    content_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, content_h))
    widgets: dict[str, object] = {}   # key → NSTextField | NSPopUpButton
    help_texts: dict[str, str] = {}   # key → help string

    y = content_h - MARGIN_TOP

    for section_title, section_fields in SECTIONS:
        y -= ROW_H
        hdr = _label(section_title, NSMakeRect(MARGIN_X, y, WIN_W - MARGIN_X * 2, ROW_H))
        hdr.setFont_(FONT_BOLD)
        content_view.addSubview_(hdr)
        y -= SEC_GAP

        for label_text, key, widget_type, options_or_ph, help_text in section_fields:
            y -= ROW_H
            help_texts[key] = help_text

            # Label
            lbl = _label(label_text + ":", NSMakeRect(MARGIN_X, y, LABEL_W, ROW_H))
            lbl.setAlignment_(NSTextAlignmentRight)
            content_view.addSubview_(lbl)

            fx = MARGIN_X + LABEL_W + 8

            if widget_type == "select":
                popup = NSPopUpButton.alloc().initWithFrame_(
                    NSMakeRect(fx, y - 2, FIELD_W, ROW_H + 4)
                )
                for opt in options_or_ph:
                    popup.addItemWithTitle_(opt)
                current = str(cfg.get(key, options_or_ph[0]))
                if current in options_or_ph:
                    popup.selectItemWithTitle_(current)
                popup.setFont_(FONT)
                content_view.addSubview_(popup)
                widgets[key] = popup

            elif widget_type == "password":
                fld = NSSecureTextField.alloc().initWithFrame_(
                    NSMakeRect(fx, y, FIELD_W, ROW_H)
                )
                fld.setStringValue_(str(cfg.get(key, "")))
                fld.setPlaceholderString_(options_or_ph)
                fld.setFont_(FONT)
                content_view.addSubview_(fld)
                widgets[key] = fld

            else:  # "text"
                fld = NSTextField.alloc().initWithFrame_(
                    NSMakeRect(fx, y, FIELD_W, ROW_H)
                )
                fld.setStringValue_(str(cfg.get(key, "")))
                fld.setPlaceholderString_(options_or_ph)
                fld.setFont_(FONT)
                content_view.addSubview_(fld)
                widgets[key] = fld

            # Help (?) button
            hx = fx + FIELD_W + 6
            hbtn = NSButton.alloc().initWithFrame_(NSMakeRect(hx, y, HELP_W, HELP_W))
            hbtn.setBezelStyle_(NSBezelStyleHelpButton)
            hbtn.setTitle_("")
            hbtn.setToolTip_(help_text)
            # Store key as tag via a closure-safe approach
            _attach_help(hbtn, label_text, help_text, content_view)
            content_view.addSubview_(hbtn)

            y -= ROW_GAP

    # Scroll view
    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(0, btn_area, WIN_W, visible_h)
    )
    scroll.setDocumentView_(content_view)
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    scroll.setDrawsBackground_(False)
    content_view.scrollPoint_(NSPoint(0, content_h - visible_h))

    # Buttons
    btn_cancel = _button("Cancel", NSMakeRect(WIN_W - 220, 12, 90, 28))
    btn_save   = _button("Save",   NSMakeRect(WIN_W - 120, 12, 90, 28))
    btn_save.setKeyEquivalent_("\r")

    root = panel.contentView()
    root.addSubview_(scroll)
    root.addSubview_(btn_cancel)
    root.addSubview_(btn_save)

    # Delegate
    delegate = _Delegate.alloc().init()
    delegate.panel    = panel
    delegate.widgets  = widgets
    delegate.on_save  = on_save

    btn_cancel.setTarget_(delegate)
    btn_cancel.setAction_(objc.selector(delegate.cancel_, selector=b"cancel:"))
    btn_save.setTarget_(delegate)
    btn_save.setAction_(objc.selector(delegate.save_,   selector=b"save:"))

    _active_panel    = panel
    _active_delegate = delegate

    panel.makeKeyAndOrderFront_(None)
    NSApp.activateIgnoringOtherApps_(True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _content_height() -> int:
    n_rows = sum(len(f) for _, f in SECTIONS)
    n_secs = len(SECTIONS)
    return (MARGIN_TOP
            + n_secs * (ROW_H + SEC_GAP)
            + n_rows * (ROW_H + ROW_GAP)
            + MARGIN_TOP)


def _label(text: str, frame) -> NSTextField:
    f = NSTextField.alloc().initWithFrame_(frame)
    f.setStringValue_(text)
    f.setBezeled_(False)
    f.setDrawsBackground_(False)
    f.setEditable_(False)
    f.setSelectable_(False)
    f.setFont_(FONT)
    return f


def _button(title: str, frame) -> NSButton:
    b = NSButton.alloc().initWithFrame_(frame)
    b.setTitle_(title)
    b.setBezelStyle_(NSBezelStyleRounded)
    return b


def _attach_help(btn: NSButton, field_name: str, help_text: str, parent: NSView):
    """Create a one-shot helper object that shows an alert when the ? is clicked."""
    helper = _HelpButtonHelper.alloc().init()
    helper.field_name = field_name
    helper.help_text  = help_text
    # Store on parent view to keep alive
    if not hasattr(parent, "_help_helpers"):
        parent._help_helpers = []
    parent._help_helpers.append(helper)
    btn.setTarget_(helper)
    btn.setAction_(objc.selector(helper.showHelp_, selector=b"showHelp:"))


# ── Help button helper ────────────────────────────────────────────────────────

class _HelpButtonHelper(NSObject):
    def showHelp_(self, sender):
        alert = NSAlert.alloc().init()
        alert.setMessageText_(self.field_name)
        alert.setInformativeText_(self.help_text)
        alert.addButtonWithTitle_("OK")
        alert.runModal()


# ── Delegate ──────────────────────────────────────────────────────────────────

class _Delegate(NSObject):

    def cancel_(self, sender):
        global _active_panel, _active_delegate
        self.panel.close()
        _active_panel = _active_delegate = None

    def save_(self, sender):
        global _active_panel, _active_delegate
        cfg = _config.load()
        for key, widget in self.widgets.items():
            if isinstance(widget, NSPopUpButton):
                val = widget.titleOfSelectedItem()
            else:
                val = widget.stringValue().strip()
            if val:
                cfg[key] = int(val) if key == "obs_port" else val
        _config.save(cfg)
        self.panel.close()
        _active_panel = _active_delegate = None
        if self.on_save:
            self.on_save(cfg)
