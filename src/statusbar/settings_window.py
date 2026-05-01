"""
settings_window.py — Single-window settings panel for Summeap
Built with AppKit (PyObjC, already installed with rumps).
"""

import objc
from AppKit import (
    NSPanel, NSView, NSTextField, NSSecureTextField, NSButton,
    NSScrollView, NSColor, NSFont, NSMakeRect, NSMakeSize,
    NSTextAlignmentRight, NSTextAlignmentLeft,
    NSBezelStyleRounded, NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable, NSWindowStyleMaskResizable,
    NSBackingStoreBuffered, NSApp, NSFloatingWindowLevel,
    NSObject,
)
from Foundation import NSMakeRange
import config as _config

# ── Layout constants ───────────────────────────────────────────────────────────
WIN_W       = 560
LABEL_W     = 180
FIELD_W     = 340
ROW_H       = 28
ROW_GAP     = 8
SECTION_GAP = 20
MARGIN_X    = 20
MARGIN_Y    = 20
FONT_LABEL  = NSFont.systemFontOfSize_(12)
FONT_HEADER = NSFont.boldSystemFontOfSize_(12)
# ─────────────────────────────────────────────────────────────────────────────

# Field definitions: (label, config_key, is_secure, placeholder)
SECTIONS = [
    ("OBS Connection", [
        ("Host",          "obs_host",      False, "localhost"),
        ("Port",          "obs_port",      False, "4455"),
        ("Password",      "obs_password",  True,  "WebSocket server password"),
        ("Scene Name",    "obs_scene",     False, "Teams"),
    ]),
    ("Paths", [
        ("Recordings Folder", "recordings_dir",  False, "~/Movies"),
        ("media2md.py",       "media2md_path",   False, "~/bin/media2md.py"),
        ("obs_teams_record",  "obs_script_path", False, "~/bin/obs_teams_record.py"),
        ("Python",            "python_path",     False, "/usr/bin/python3"),
        ("Extra PATH",        "extra_path",      False, "/usr/local/bin:/opt/homebrew/bin"),
    ]),
    ("AI Models", [
        ("LLM Model",      "llm_model",      False, "google/gemma-4-26b-a4b"),
        ("Whisper Model",  "whisper_model",  False, "large-v3-turbo"),
        ("Default Style",  "default_style",  False, "executive / normal / detailed"),
    ]),
    ("HuggingFace", [
        ("HF Token",  "hf_token",  True,  "hf_... (only needed for diarization)"),
    ]),
]


def _count_rows() -> int:
    return sum(len(fields) for _, fields in SECTIONS)


def _total_height() -> int:
    n_rows     = _count_rows()
    n_sections = len(SECTIONS)
    return (MARGIN_Y * 2
            + n_rows * (ROW_H + ROW_GAP)
            + n_sections * (ROW_H + SECTION_GAP)
            + 50)   # buttons area


def show_settings(on_save=None):
    """Open the settings panel. on_save(cfg) is called when the user saves."""
    cfg = _config.load()
    height = min(_total_height(), 620)   # cap height, scroll if needed

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, WIN_W, height),
        NSWindowStyleMaskTitled | NSWindowStyleMaskClosable | NSWindowStyleMaskResizable,
        NSBackingStoreBuffered,
        False,
    )
    panel.setTitle_("Summeap — Settings")
    panel.setLevel_(NSFloatingWindowLevel)
    panel.center()

    # ── Scrollable content view ───────────────────────────────────────────────
    content_h = _total_height() - 50
    content_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, content_h))

    fields: dict[str, NSTextField] = {}   # key → input widget
    y = content_h - MARGIN_Y

    for section_title, section_fields in SECTIONS:
        # Section header
        y -= ROW_H
        header = _make_label(section_title, NSMakeRect(MARGIN_X, y, WIN_W - MARGIN_X * 2, ROW_H))
        header.setFont_(FONT_HEADER)
        content_view.addSubview_(header)

        for label_text, key, secure, placeholder in section_fields:
            y -= ROW_H + ROW_GAP

            # Label (right-aligned)
            lbl = _make_label(label_text + ":", NSMakeRect(MARGIN_X, y, LABEL_W, ROW_H))
            lbl.setAlignment_(NSTextAlignmentRight)
            content_view.addSubview_(lbl)

            # Input field
            fx = MARGIN_X + LABEL_W + 8
            if secure:
                field = NSSecureTextField.alloc().initWithFrame_(
                    NSMakeRect(fx, y, FIELD_W, ROW_H)
                )
            else:
                field = NSTextField.alloc().initWithFrame_(
                    NSMakeRect(fx, y, FIELD_W, ROW_H)
                )
            field.setStringValue_(str(cfg.get(key, "")))
            field.setPlaceholderString_(placeholder)
            field.setFont_(FONT_LABEL)
            field.setBezeled_(True)
            content_view.addSubview_(field)
            fields[key] = field

        y -= SECTION_GAP

    # ── Scroll view wrapper ───────────────────────────────────────────────────
    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(0, 50, WIN_W, height - 50)
    )
    scroll.setDocumentView_(content_view)
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    # Scroll to top
    content_view.scrollPoint_(
        content_view.frame().origin.__class__(0, content_h - height + 50)
    )

    # ── Buttons ───────────────────────────────────────────────────────────────
    btn_cancel = _make_button("Cancel", NSMakeRect(WIN_W - 210, 12, 90, 28))
    btn_save   = _make_button("Save",   NSMakeRect(WIN_W - 110, 12, 90, 28))
    btn_save.setKeyEquivalent_("\r")

    container = panel.contentView()
    container.addSubview_(scroll)
    container.addSubview_(btn_cancel)
    container.addSubview_(btn_save)

    # ── Delegate to handle button clicks ─────────────────────────────────────
    delegate = _SettingsDelegate.alloc().init()
    delegate.panel   = panel
    delegate.fields  = fields
    delegate.on_save = on_save
    # Keep a strong reference so ARC doesn't deallocate it
    panel._delegate_ref = delegate

    btn_cancel.setTarget_(delegate)
    btn_cancel.setAction_(objc.selector(delegate.cancel_, selector=b"cancel:"))
    btn_save.setTarget_(delegate)
    btn_save.setAction_(objc.selector(delegate.save_, selector=b"save:"))

    panel.makeKeyAndOrderFront_(None)
    NSApp.activateIgnoringOtherApps_(True)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_label(text: str, frame) -> NSTextField:
    lbl = NSTextField.alloc().initWithFrame_(frame)
    lbl.setStringValue_(text)
    lbl.setBezeled_(False)
    lbl.setDrawsBackground_(False)
    lbl.setEditable_(False)
    lbl.setSelectable_(False)
    lbl.setFont_(FONT_LABEL)
    return lbl


def _make_button(title: str, frame) -> NSButton:
    btn = NSButton.alloc().initWithFrame_(frame)
    btn.setTitle_(title)
    btn.setBezelStyle_(NSBezelStyleRounded)
    return btn


# ── Delegate ──────────────────────────────────────────────────────────────────

class _SettingsDelegate(NSObject):

    def cancel_(self, sender):
        self.panel.close()

    def save_(self, sender):
        cfg = _config.load()
        for key, field in self.fields.items():
            val = field.stringValue()
            if val.strip():
                cfg[key] = int(val) if key == "obs_port" else val
        _config.save(cfg)
        self.panel.close()
        if self.on_save:
            self.on_save(cfg)
