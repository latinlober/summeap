"""
log_window.py — Native floating log window for media2md output.

run_in_log_window() runs silently in the background — no window pops up.
show_log_window()   is user-triggered (via "Show Log" menu item).
"""

import threading
import subprocess
import os
from pathlib import Path
from typing import Optional

from AppKit import (
    NSPanel, NSScrollView, NSTextView, NSFont, NSMakeRect, NSColor,
    NSWindowStyleMaskTitled, NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable, NSWindowStyleMaskMiniaturizable,
    NSBackingStoreBuffered, NSApp, NSFloatingWindowLevel, NSObject,
    NSForegroundColorAttributeName, NSFontAttributeName,
)
from Foundation import NSThread, NSOperationQueue, NSMutableAttributedString, NSRange

WIN_W = 700
WIN_H = 460

_ATTRS = {
    NSFontAttributeName:            NSFont.fontWithName_size_("Menlo", 12),
    NSForegroundColorAttributeName: NSColor.greenColor(),
}

# ── Singleton ─────────────────────────────────────────────────────────────────
_panel:    Optional[NSPanel]    = None
_textview: Optional[NSTextView] = None
_delegate: Optional[NSObject]   = None
# ─────────────────────────────────────────────────────────────────────────────


def _on_main(fn):
    if NSThread.isMainThread():
        fn()
    else:
        NSOperationQueue.mainQueue().addOperationWithBlock_(fn)


def _build_panel(title: str) -> None:
    """Create panel + text view. Must run on main thread. Panel stays hidden."""
    global _panel, _textview, _delegate

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

    tv = NSTextView.alloc().initWithFrame_(NSMakeRect(0, 0, WIN_W, WIN_H))
    tv.setEditable_(False)
    tv.setSelectable_(True)
    tv.setRichText_(False)
    tv.setBackgroundColor_(NSColor.blackColor())
    tv.setTextColor_(NSColor.greenColor())
    tv.setFont_(NSFont.fontWithName_size_("Menlo", 12))
    tv.setAutomaticLinkDetectionEnabled_(False)
    tv.setAutomaticQuoteSubstitutionEnabled_(False)
    tv.setAutomaticSpellingCorrectionEnabled_(False)
    tv.textContainer().setWidthTracksTextView_(True)
    tv.setHorizontallyResizable_(False)
    tv.setVerticallyResizable_(True)
    tv.setMaxSize_((1e7, 1e7))

    scroll = NSScrollView.alloc().initWithFrame_(
        NSMakeRect(0, 0, WIN_W, WIN_H)
    )
    scroll.setHasVerticalScroller_(True)
    scroll.setHasHorizontalScroller_(False)
    scroll.setAutohidesScrollers_(True)
    scroll.setAutoresizingMask_(18)   # width + height
    scroll.setDocumentView_(tv)
    scroll.setDrawsBackground_(False)

    panel.contentView().addSubview_(scroll)
    panel.contentView().setAutoresizesSubviews_(True)

    delegate = _PanelDelegate.alloc().init()
    panel.setDelegate_(delegate)

    _panel    = panel
    _textview = tv
    _delegate = delegate


# ── Public API ────────────────────────────────────────────────────────────────

def show_log_window():
    """Bring the log window to front. Creates it (empty) if needed."""
    def _show():
        if _panel is None:
            _build_panel("Summeap — Log")
        _panel.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)
    _on_main(_show)


def run_in_log_window(job: dict):
    """Prepare the log buffer for this job and stream media2md output into it.
    The window stays hidden until the user opens it via 'Show Log'."""
    video_path = job["video_path"]
    python     = job["python"]
    media2md   = job["media2md"]
    hf_token   = job.get("hf_token", "")
    extra_path = job.get("extra_path", "")
    title      = f"Summeap — {Path(video_path).name}"

    cmd = [x for x in [
        python, media2md,
        job.get("diarize_flag", ""),
        job.get("pdf_flag", ""),
        job.get("docx_flag", ""),
        "--style", "detailed", "--save-transcript",
        video_path,
    ] if x]

    env = os.environ.copy()
    env["HF_TOKEN"] = hf_token
    env["PATH"]     = extra_path + ":" + env.get("PATH", "")

    def _prepare():
        global _panel, _textview
        if _panel is None:
            _build_panel(title)
        else:
            # Clear text storage directly — do NOT call setString_ (resets color)
            storage = _textview.textStorage()
            storage.beginEditing()
            storage.deleteCharactersInRange_((0, storage.length()))
            storage.endEditing()
            _panel.setTitle_(title)
        threading.Thread(target=_stream, args=(_textview, cmd, env), daemon=True).start()

    _on_main(_prepare)


def _stream(tv: NSTextView, cmd: list, env: dict):
    _append(tv, "$ " + " ".join(cmd) + "\n\n")
    try:
        proc = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1,
        )
        for line in proc.stdout:
            _append(tv, line)
        proc.wait()
        _append(tv, f"\n--- Done (exit {proc.returncode}) ---\n")
    except Exception as e:
        _append(tv, f"\nERROR: {e}\n")


def _append(tv: NSTextView, text: str):
    def _do():
        astr = NSMutableAttributedString.alloc().initWithString_(text)
        rng = (0, astr.length())
        astr.addAttribute_value_range_(
            NSForegroundColorAttributeName, NSColor.greenColor(), rng)
        astr.addAttribute_value_range_(
            NSFontAttributeName, NSFont.fontWithName_size_("Menlo", 12), rng)
        storage = tv.textStorage()
        storage.beginEditing()
        storage.appendAttributedString_(astr)
        storage.endEditing()
        tv.scrollRangeToVisible_((storage.length(), 0))
    _on_main(_do)


# ── Delegate ──────────────────────────────────────────────────────────────────

class _PanelDelegate(NSObject):
    def windowWillClose_(self, notification):
        global _panel, _textview, _delegate
        _panel = _textview = _delegate = None
