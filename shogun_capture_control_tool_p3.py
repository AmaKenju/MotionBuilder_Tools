# -*- coding: utf-8 -*-
"""Start / stop Shogun Live recording from a MotionBuilder tool window.

Wraps shogun_live_api CaptureServices: set the capture name, start a capture,
stop or cancel it, and watch the state of the latest capture.

Run this file in the MotionBuilder Python Editor to open the tool.

MotionBuilder 2024 (Python 3.10).
"""
import os
import sys

from pyfbsdk import FBTextJustify, ShowTool
from pyfbsdk_additions import FBCreateUniqueTool, FBHBoxLayout, FBVBoxLayout

try:
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _THIS_DIR = os.getcwd()
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from shogun_mobu_ui import (  # noqa: E402
    ShogunToolBase,
    confirm,
    fill_main_region,
    make_button,
    make_edit,
    make_label,
)

TOOL_NAME = "Shogun Capture Control"
TOOL_START_WIDTH = 460
TOOL_START_HEIGHT = 300
TOOL_MIN_WIDTH = 400
TOOL_MIN_HEIGHT = 260

# States in which a capture is still running, so Stop / Cancel make sense.
ACTIVE_STATE_NAMES = ("EArmed", "EStarted", "EPartStopped")


class CaptureControlTool(ShogunToolBase):

    def __init__(self):
        super(CaptureControlTool, self).__init__()
        # Id of the capture this tool started; 0 means "whatever is running".
        self.capture_id = 0

    # -- layout ------------------------------------------------------------
    def populate(self, tool):
        main = FBVBoxLayout()
        fill_main_region(tool, main)

        main.Add(self.build_header(), 26)

        name_row = FBHBoxLayout()
        name_row.Add(make_label("Capture name:", FBTextJustify.kFBTextJustifyRight), 100)
        self.name_edit = make_edit("")
        name_row.AddRelative(self.name_edit, 1.0)
        name_row.Add(make_button("Set", self.on_set_name), 60)
        main.Add(name_row, 26)

        folder_row = FBHBoxLayout()
        folder_row.Add(make_label("Folder:", FBTextJustify.kFBTextJustifyRight), 100)
        self.folder_label = make_label("-")
        folder_row.AddRelative(self.folder_label, 1.0)
        main.Add(folder_row, 22)

        state_row = FBHBoxLayout()
        state_row.Add(make_label("State:", FBTextJustify.kFBTextJustifyRight), 100)
        self.state_label = make_label("-")
        state_row.AddRelative(self.state_label, 1.0)
        state_row.Add(make_button("Refresh", self.on_refresh), 80)
        main.Add(state_row, 26)

        main.Add(make_label(""), 6)

        transport = FBHBoxLayout()
        transport.AddRelative(make_button("START", self.on_start,
                                          "Start (or arm) a capture"), 1.4)
        transport.AddRelative(make_button("STOP", self.on_stop,
                                          "Stop the capture in progress"), 1.0)
        transport.AddRelative(make_button("CANCEL", self.on_cancel,
                                          "Cancel and discard the capture"), 1.0)
        main.Add(transport, 42)

        main.AddRelative(make_label(""), 1.0)
        main.Add(self.build_status_label(), 20)

    # -- refresh -----------------------------------------------------------
    def on_connected(self):
        self.refresh()

    def on_refresh(self, control=None, event=None):
        self.refresh()

    def refresh(self):
        if not self.require_connection():
            return

        ok, name = self.call(self.live.capture.capture_name(), "Get capture name")
        if ok:
            self.name_edit.Text = name

        ok, folder = self.call(self.live.capture.capture_folder(), "Get capture folder")
        self.folder_label.Caption = folder if ok else "-"

        self.refresh_state()

    def refresh_state(self):
        """Update the state line. Returns the state name, or '' if unavailable."""
        # Quiet: NotAvailable just means nothing has been captured yet, and
        # this runs right after actions whose own error message must survive.
        ok, values = self.call(self.live.capture.latest_capture_state(),
                               "Get capture state", quiet=True)
        if not ok:
            self.state_label.Caption = "no capture yet"
            return ""

        capture_id, state = values
        state_name = getattr(state, "name", str(state))
        self.state_label.Caption = "id={0}  {1}".format(capture_id, state_name)
        return state_name

    def _is_capturing(self):
        if not self.connected:
            return False
        return self.refresh_state() in ACTIVE_STATE_NAMES

    # -- actions -----------------------------------------------------------
    def on_set_name(self, control=None, event=None):
        if not self.require_connection():
            return
        name = (self.name_edit.Text or "").strip()
        if not name:
            self.status("Enter a capture name first.")
            return
        ok, _ = self.call(self.live.capture.set_capture_name(name), "Set capture name")
        if ok:
            self.status("Capture name set to '{0}'.".format(name), "success")

    def on_start(self, control=None, event=None):
        if not self.require_connection():
            return

        # Apply whatever is in the name field before recording.
        name = (self.name_edit.Text or "").strip()
        if name:
            self.call(self.live.capture.set_capture_name(name), "Set capture name")

        ok, capture_id = self.call(self.live.capture.start_capture(), "Start capture")
        if not ok:
            # start_capture reports NotPermitted when a capture is already
            # running or the system is not ready, InvalidSettings for bad
            # capture settings - self.call already put the reason on the line.
            self.refresh_state()
            return

        self.capture_id = capture_id
        self.refresh_state()
        self.status("Capture started (id={0}, name='{1}').".format(
            capture_id, name or "<unchanged>"), "success")

    def on_stop(self, control=None, event=None):
        if not self.require_connection():
            return
        ok, _ = self.call(self.live.capture.stop_capture(self.capture_id), "Stop capture")
        if not ok:
            self.refresh_state()
            return
        self.status("Capture stopped (id={0}).".format(self.capture_id or "any"),
                    "success")
        self.capture_id = 0
        self.refresh_state()

    def on_cancel(self, control=None, event=None):
        if not self.require_connection():
            return
        if not confirm("Cancel capture",
                       "Cancel the capture in progress?\nThe recorded data is discarded."):
            return
        ok, _ = self.call(self.live.capture.cancel_capture(self.capture_id),
                          "Cancel capture")
        if not ok:
            self.refresh_state()
            return
        self.status("Capture canceled.", "success")
        self.capture_id = 0
        self.refresh_state()


def create_tool():
    tool = FBCreateUniqueTool(TOOL_NAME)
    tool.StartSizeX = TOOL_START_WIDTH
    tool.StartSizeY = TOOL_START_HEIGHT
    tool.MinSizeX = TOOL_MIN_WIDTH
    tool.MinSizeY = TOOL_MIN_HEIGHT

    CaptureControlTool().populate(tool)
    ShowTool(tool)
    return tool


create_tool()
