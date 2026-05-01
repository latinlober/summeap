"""
settings_window.py — Single-window settings panel for Summeap
Built with AppKit (PyObjC, already installed with rumps).

Features:
- Single instance enforced (second call brings existing window to front)
- NSPopUpButton dropdowns for enum fields (Whisper Model, Default Style)
- Secure text fields for passwords/tokens
"""

import objc
from pathlib import Path
from typing import Optional
from AppKit import (
    NSPanel, NSView, NSTextField, NSSecureTextField, NSButton,
    NSScrollView, NSFont, NSMakeRect, NSPopUpButton,
    NSTextAlignmentRight, NSBezelStyleRounded,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSBackingStoreBuffered,
    NSApp, NSFloatingWindowLevel, NSObject,
    NSMenu, NSMenuItem, NSApplication,
)
from Foundation import NSPoint

import config as _config


def _ensure_edit_menu():
    """Add a standard Edit menu (Cut/Copy/Paste/Select All) if not present.
    This is required for keyboard shortcuts to work in NSTextField panels
    because rumps apps don't create an Edit menu by default.
    """
    main_menu = NSApp.mainMenu()
    if main_menu is None:
        return
    # Check if Edit menu already exists
    for i in range(main_menu.numberOfItems()):
        if main_menu.itemAtIndex_(i).title() == "Edit":
            return
    # Build Edit menu
    edit_menu = NSMenu.alloc().initWithTitle_("Edit")
    for title, action, key in [
        ("Cut",        "cut:",        "x"),
        ("Copy",       "copy:",       "c"),
        ("Paste",      "paste:",      "v"),
        ("Select All", "selectAll:",  "a"),
    ]:
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, action, key)
        edit_menu.addItem_(item)
    edit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_("Edit", "", "")
    edit_item.setSubmenu_(edit_menu)
    main_menu.addItem_(edit_item)

# ── Layout ────────────────────────────────────────────────────────────────────
WIN_W      = 540
LABEL_W    = 170
FIELD_W    = 320
ROW_H      = 24
ROW_GAP    = 7
SEC_GAP    = 16
MARGIN_X   = 20
MARGIN_TOP = 16
FONT       = NSFont.systemFontOfSize_(12)
FONT_BOLD  = NSFont.boldSystemFontOfSize_(12)
# ─────────────────────────────────────────────────────────────────────────────

# Field spec: (label, config_key, widget_type, placeholder_or_options)
# widget_type: "text" | "password" | "select"
SECTIONS = [
    ("OBS Connection", [
        ("Host",       "obs_host",     "text",     "localhost"),
        ("Port",       "obs_port",     "text",     "4455"),
        ("Password",   "obs_password", "password", "WebSocket server password"),
        ("Scene Name", "obs_scene",    "text",     "Teams"),
    ]),
    ("Paths", [
        ("Recordings Folder",   "recordings_dir",  "text", str(Path.home() / "Movies")),
        ("media2md.py",         "media2md_path",   "text", "~/bin/media2md.py"),
        ("obs_teams_record.py", "obs_script_path", "text", "~/bin/obs_teams_record.py"),
        ("Python",              "python_path",     "text", "/usr/bin/python3"),
        ("Extra PATH",          "extra_path",      "text", "/usr/local/bin:/opt/homebrew/bin"),
    ]),
    ("AI Models", [
        ("LLM Model",     "llm_model",     "text",   "google/gemma-4-26b-a4b"),
        ("Whisper Model", "whisper_model", "select", ["large-v3-turbo", "large-v3", "large",
                                                       "medium", "small", "base", "tiny"]),
        ("Default Style", "default_style", "select", ["detailed", "normal", "executive"]),
    ]),
    ("HuggingFace", [
        ("HF Token", "hf_token", "password", "hf_...  (only needed for diarization)"),
    ]),
    ("Export", [
        ("pandoc",          "pandoc_path",     "text", "/opt/homebrew/bin/pandoc"),
        ("xelatex",         "xelatex_path",    "text", "/usr/local/bin/xelatex"),
        ("Default Formats", "default_formats", "text", "pdf,docx  (comma-separated: pdf, docx)"),
    ]),
    ("Hotkeys", [
        ("Toggle Recording", "hotkey_toggle", "text", "<cmd>+<shift>+r"),
    ]),
]

# ── Singleton ─────────────────────────────────────────────────────────────────
_active_panel:    Optional[NSPanel]  = None
_active_delegate: Optional[NSObject] = None


def show_settings(on_save=None):
    global _active_panel, _active_delegate

    _ensure_edit_menu()

    # Enforce single instance
    if _active_panel is not None:
        _active_panel.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        return

    cfg       = _config.load()
    content_h = _content_height()
    visible_h = min(content_h, 560)
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

    # ── Content view ──────────────────────────────────────────────────────────
    content_view = NSView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, content_h))
    widgets: dict = {}

    y = content_h - MARGIN_TOP

    for section_title, section_fields in SECTIONS:
        # Section header
        y -= ROW_H
        hdr = _static(section_title, NSMakeRect(MARGIN_X, y, WIN_W - MARGIN_X * 2, ROW_H))
        hdr.setFont_(FONT_BOLD)
        content_view.addSubview_(hdr)
        y -= SEC_GAP

        for label_text, key, widget_type, options_or_ph in section_fields:
            y -= ROW_H

            lbl = _static(label_text + ":", NSMakeRect(MARGIN_X, y, LABEL_W, ROW_H))
            lbl.setAlignment_(NSTextAlignmentRight)
            content_view.addSubview_(lbl)

            fx = MARGIN_X + LABEL_W + 8

            if widget_type == "select":
                w = NSPopUpButton.alloc().initWithFrame_(
                    NSMakeRect(fx, y - 2, FIELD_W, ROW_H + 4)
                )
                for opt in options_or_ph:
                    w.addItemWithTitle_(opt)
                current = str(cfg.get(key, options_or_ph[0]))
                if current in options_or_ph:
                    w.selectItemWithTitle_(current)
                w.setFont_(FONT)
                content_view.addSubview_(w)

            elif widget_type == "password":
                w = NSSecureTextField.alloc().initWithFrame_(
                    NSMakeRect(fx, y, FIELD_W, ROW_H)
                )
                w.setStringValue_(str(cfg.get(key, "")))
                w.setPlaceholderString_(options_or_ph)
                w.setFont_(FONT)
                content_view.addSubview_(w)

            else:
                w = NSTextField.alloc().initWithFrame_(
                    NSMakeRect(fx, y, FIELD_W, ROW_H)
                )
                w.setStringValue_(str(cfg.get(key, "")))
                w.setPlaceholderString_(options_or_ph)
                w.setFont_(FONT)
                content_view.addSubview_(w)

            widgets[key] = w
            y -= ROW_GAP

    # ── Scroll view ───────────────────────────────────────────────────────────
    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(0, btn_area, WIN_W, visible_h)
    )
    scroll.setDocumentView_(content_view)
    scroll.setHasVerticalScroller_(True)
    scroll.setAutohidesScrollers_(True)
    scroll.setDrawsBackground_(False)
    content_view.scrollPoint_(NSPoint(0, content_h - visible_h))

    # ── Buttons ───────────────────────────────────────────────────────────────
    btn_cancel = _button("Cancel", NSMakeRect(WIN_W - 210, 12, 90, 28))
    btn_save   = _button("Save",   NSMakeRect(WIN_W - 110, 12, 90, 28))
    btn_save.setKeyEquivalent_("\r")

    root = panel.contentView()
    root.addSubview_(scroll)
    root.addSubview_(btn_cancel)
    root.addSubview_(btn_save)

    # ── Delegate ──────────────────────────────────────────────────────────────
    delegate = _Delegate.alloc().init()
    delegate.panel   = panel
    delegate.widgets = widgets
    delegate.on_save = on_save

    btn_cancel.setTarget_(delegate)
    btn_cancel.setAction_(objc.selector(delegate.cancel_, selector=b"cancel:"))
    btn_save.setTarget_(delegate)
    btn_save.setAction_(objc.selector(delegate.save_,    selector=b"save:"))

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


def _static(text: str, frame) -> NSTextField:
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
