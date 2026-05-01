"""
log_window.py — Native floating log window for media2md output.
Shows a scrollable text view that streams subprocess output in real time.
"""

import threading
import subprocess
import os
from pathlib import Path
from typing import Optional

import objc
from AppKit import (
    NSPanel, NSScrollView, NSTextView, NSFont, NSMakeRect, NSColor,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSWindowStyleMaskMiniaturizable,
    NSBackingStoreBuffered, NSApp, NSFloatingWindowLevel, NSObject,
    NSString, NSAttributedString,
)
from Foundation import NSTimer, NSRunLoop, NSDefaultRunLoopMode

# ── Singleton ─────────────────────────────────────────────────────────────────
_active_panel: Optional[NSPanel] = None
_active_text_view: Optional[NSTextView] = None
_active_delegate: Optional[NSObject] = None
# ─────────────────────────────────────────────────────────────────────────────

WIN_W = 700
WIN_H = 460


def show_log_window(title: str = "Summeap — Processing") -> NSTextView:
    """Open (or reuse) the log window and return the NSTextView to write to."""
    global _active_panel, _active_text_view, _active_delegate

    if _active_panel is not None:
        _active_panel.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
        # Clear previous content
        _active_text_view.setString_("")
        _active_panel.setTitle_(title)
        return _active_text_view

    panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
        NSMakeRect(0, 0, WIN_W, WIN_H),
        (NSWindowStyleMaskTitled | NSWindowStyleMaskClosable |
         NSWindowStyleMaskResizable | NSWindowStyleMaskMiniaturizable),
        NSBackingStoreBuffered,
        False,
    )
    panel.setTitle_(title)
    panel.setLevel_(NSFloatingWindowLevel)
    panel.center()

    # Scroll + text view
    scroll = NSScrollView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, WIN_H))
    scroll.setHasVerticalScroller_(True)
    scroll.setHasHorizontalScroller_(False)
    scroll.setAutohidesScrollers_(True)

    tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, WIN_H))
    tv.setEditable_(False)
    tv.setSelectable_(True)
    tv.setFont_(NSFont.fontWithName_size_("Menlo", 11))
    tv.setBackgroundColor_(NSColor.blackColor())
    tv.setTextColor_(NSColor.greenColor())
    tv.setAutomaticLinkDetectionEnabled_(False)
    tv.setAutomaticQuoteSubstitutionEnabled_(False)
    tv.setAutomaticSpellingCorrectionEnabled_(False)
    tv.textContainer().setWidthTracksTextView_(True)

    scroll.setDocumentView_(tv)
    scroll.setAutoresizingMask_(18)  # width + height

    panel.contentView().addSubview_(scroll)

    # Delegate to clear singleton on close
    delegate = _PanelDelegate.alloc().init()
    panel.setDelegate_(delegate)

    _active_panel    = panel
    _active_text_view = tv
    _active_delegate = delegate

    panel.makeKeyAndOrderFront_(None)
    NSApp.activateIgnoringOtherApps_(True)
    return tv


def append_text(text_view: NSTextView, text: str):
    """Append text to the log window on the main thread."""
    def _append():
        storage = text_view.textStorage()
        end = storage.length()
        attr_str = NSAttributedString.alloc().initWithString_attributes_(
            text,
            {
                "NSFont": NSFont.fontWithName_size_("Menlo", 11),
                "NSForegroundColor": NSColor.greenColor(),
            }
        )
        storage.insertAttributedString_atIndex_(attr_str, end)
        # Scroll to bottom
        text_view.scrollRangeToVisible_((storage.length(), 0))
    # Must run on main thread
    objc.callAfter(_append)


def run_in_log_window(job: dict):
    """Run media2md from a job dict, streaming output to the log window."""
    video_path  = job["video_path"]
    python      = job["python"]
    media2md    = job["media2md"]
    hf_token    = job.get("hf_token", "")
    extra_path  = job.get("extra_path", "")
    diarize     = job.get("diarize_flag", "")
    pdf_flag    = job.get("pdf_flag", "")
    docx_flag   = job.get("docx_flag", "")

    title = f"Summeap — {Path(video_path).name}"
    tv = show_log_window(title)

    cmd = [x for x in [
        python, media2md,
        diarize, pdf_flag, docx_flag,
        "--style", "detailed", "--save-transcript",
        video_path,
    ] if x]

    env = os.environ.copy()
    env["HF_TOKEN"] = hf_token
    env["PATH"]     = extra_path + ":" + env.get("PATH", "")

    def _stream():
        append_text(tv, f"$ {' '.join(cmd)}\n\n")
        try:
            proc = subprocess.Popen(
                cmd, env=env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, bufsize=1,
            )
            for line in proc.stdout:
                append_text(tv, line)
            proc.wait()
            append_text(tv, f"\n--- Proceso completado (exit {proc.returncode}) ---\n")
        except Exception as e:
            append_text(tv, f"\nERROR: {e}\n")

    threading.Thread(target=_stream, daemon=True).start()


# ── Delegate ──────────────────────────────────────────────────────────────────

class _PanelDelegate(NSObject):
    def windowWillClose_(self, notification):
        global _active_panel, _active_text_view, _active_delegate
        _active_panel = _active_text_view = _active_delegate = None
