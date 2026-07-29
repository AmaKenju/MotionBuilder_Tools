# -*- coding: utf-8 -*-
"""Play back Shogun Live captures from a MotionBuilder tool window.

A port of ShogunTools/ShogunReviewPlay.py. That script played the most recent
capture; this adds the capture list so any take in the review folder can be
picked, plus pause and exit-review controls.

Run this file in the MotionBuilder Python Editor to open the tool.

MotionBuilder 2024 (Python 3.10).
"""
import os
import sys
import time

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
    fill_main_region,
    make_button,
    make_checkbox,
    make_label,
    make_list,
)

TOOL_NAME = "Shogun Review Play"
TOOL_START_WIDTH = 520
TOOL_START_HEIGHT = 460
TOOL_MIN_WIDTH = 420
TOOL_MIN_HEIGHT = 360


class ReviewPlayTool(ShogunToolBase):

    def __init__(self):
        super(ReviewPlayTool, self).__init__()
        # Capture names in the order shown in the list widget (newest first).
        self.capture_names = []

    # -- layout ------------------------------------------------------------
    def populate(self, tool):
        main = FBVBoxLayout()
        fill_main_region(tool, main)

        main.Add(self.build_header(), 26)

        folder_row = FBHBoxLayout()
        folder_row.Add(make_label("Review folder:", FBTextJustify.kFBTextJustifyRight), 100)
        self.folder_label = make_label("-")
        folder_row.AddRelative(self.folder_label, 1.0)
        main.Add(folder_row, 22)

        list_head = FBHBoxLayout()
        list_head.AddRelative(make_label("Captures (newest first)"), 1.0)
        list_head.Add(make_button("Refresh", self.on_refresh), 80)
        main.Add(list_head, 24)

        self.capture_list = make_list(multi_select=False)
        main.AddRelative(self.capture_list, 1.0)

        play_row = FBHBoxLayout()
        play_row.AddRelative(make_button("Play Selected", self.on_play_selected), 1.2)
        play_row.AddRelative(make_button("Play Latest", self.on_play_latest,
                                         "Same behaviour as ShogunReviewPlay.py"), 1.0)
        main.Add(play_row, 30)

        transport = FBHBoxLayout()
        transport.AddRelative(make_button("Pause", self.on_pause), 1.0)
        transport.AddRelative(make_button("Resume", self.on_resume), 1.0)
        transport.AddRelative(make_button("Exit Review", self.on_exit_review), 1.0)
        main.Add(transport, 28)

        options = FBHBoxLayout()
        self.loop_check = make_checkbox("Loop", self.on_toggle_loop)
        options.Add(self.loop_check, 80)
        self.state_label = make_label("-")
        options.AddRelative(self.state_label, 1.0)
        main.Add(options, 24)

        main.Add(self.build_status_label(), 20)

    # -- refresh -----------------------------------------------------------
    def on_connected(self):
        self.refresh()

    def on_refresh(self, control=None, event=None):
        self.refresh()

    def refresh(self):
        if not self.require_connection():
            return

        ok, folder = self.call(self.live.playback.review_folder(), "Get review folder")
        self.folder_label.Caption = folder if ok else "-"

        ok, loop_enabled = self.call(self.live.playback.loop_enabled(), "Get loop state")
        if ok:
            self.loop_check.State = 1 if loop_enabled else 0

        self.refresh_capture_list()
        self.refresh_state()

    def refresh_capture_list(self):
        ok, captures = self.call(self.live.playback.capture_list(), "Get capture list")
        self.capture_list.Items.removeAll()
        self.capture_names = []
        if not ok:
            return

        # Newest first, matching the max(epoch_time) pick in the original script.
        for capture in sorted(captures, key=lambda c: c.epoch_time, reverse=True):
            stamp = time.strftime("%Y-%m-%d %H:%M:%S",
                                  time.localtime(capture.epoch_time))
            self.capture_names.append(capture.capture_name)
            self.capture_list.Items.append("{0}    {1}".format(
                capture.capture_name, stamp))

        if not self.capture_names:
            self.status("No captures in the review folder: {0}".format(
                self.folder_label.Caption))
        else:
            self.status("{0} capture(s) available.".format(len(self.capture_names)),
                        "success")

    def refresh_state(self):
        # Quiet: this runs after playback actions whose own error message
        # must stay on the status line.
        ok, state = self.call(self.live.playback.state(), "Get playback state",
                              quiet=True)
        if not ok:
            self.state_label.Caption = "-"
            return
        mode = getattr(state.mode, "name", str(state.mode))
        name = state.capture_name or "<live buffer>"
        self.state_label.Caption = "{0}  -  {1}".format(mode, name)

    # -- capture selection -------------------------------------------------
    def _selected_capture_name(self):
        for index in range(len(self.capture_names)):
            if self.capture_list.IsSelected(index):
                return self.capture_names[index]
        return None

    def _latest_capture_name(self):
        """The name ShogunReviewPlay.py would have chosen."""
        result, _capture_id, name = self.live.capture.latest_capture_name()
        if result and name:
            return name
        # Nothing captured this session - fall back to the newest on disk,
        # which refresh_capture_list() already sorted to the top.
        if self.capture_names:
            return self.capture_names[0]
        return None

    # -- playback ----------------------------------------------------------
    def _enter_review_and_play(self, capture_name):
        """Enter review for this capture and start playing.

        Retries once after exit_review(), as the original script did: entering
        review fails if a review session is already open.
        """
        result = self.live.playback.enter_capture_review(capture_name)
        if not result:
            self.live.playback.exit_review()
            result = self.live.playback.enter_capture_review(capture_name)
            if not result:
                self.status("Could not enter review for '{0}': {1}".format(
                    capture_name, result), "error")
                self.refresh_state()
                return False

        ok, _ = self.call(self.live.playback.play(), "Play")
        self.refresh_state()
        if not ok:
            return False
        self.status("Playing '{0}'.".format(capture_name), "success")
        return True

    def on_play_selected(self, control=None, event=None):
        if not self.require_connection():
            return
        name = self._selected_capture_name()
        if name is None:
            self.status("Select a capture in the list first.")
            return
        self._enter_review_and_play(name)

    def on_play_latest(self, control=None, event=None):
        if not self.require_connection():
            return
        if not self.capture_names:
            self.refresh_capture_list()
        name = self._latest_capture_name()
        if name is None:
            self.status("No capture available to review in {0}".format(
                self.folder_label.Caption), "error")
            return
        self._enter_review_and_play(name)

    def on_pause(self, control=None, event=None):
        if not self.require_connection():
            return
        ok, _ = self.call(self.live.playback.pause(), "Pause")
        self.refresh_state()
        if ok:
            self.status("Paused.", "success")

    def on_resume(self, control=None, event=None):
        if not self.require_connection():
            return
        ok, _ = self.call(self.live.playback.play(), "Play")
        self.refresh_state()
        if ok:
            self.status("Playing.", "success")

    def on_exit_review(self, control=None, event=None):
        if not self.require_connection():
            return
        ok, _ = self.call(self.live.playback.exit_review(), "Exit review")
        self.refresh_state()
        if ok:
            self.status("Left review; back to live.", "success")

    def on_toggle_loop(self, control=None, event=None):
        if not self.require_connection():
            return
        enabled = bool(self.loop_check.State)
        ok, _ = self.call(self.live.playback.set_loop_enabled(enabled), "Set loop")
        if ok:
            self.status("Loop {0}.".format("on" if enabled else "off"), "success")


def create_tool():
    tool = FBCreateUniqueTool(TOOL_NAME)
    tool.StartSizeX = TOOL_START_WIDTH
    tool.StartSizeY = TOOL_START_HEIGHT
    tool.MinSizeX = TOOL_MIN_WIDTH
    tool.MinSizeY = TOOL_MIN_HEIGHT

    ReviewPlayTool().populate(tool)
    ShowTool(tool)
    return tool


create_tool()
