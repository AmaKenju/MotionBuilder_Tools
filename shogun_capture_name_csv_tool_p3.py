# -*- coding: utf-8 -*-
"""Pick a Shogun Live capture name from a CSV shot list, in MotionBuilder.

A port of ShogunTools/CaptureNameShogun.py. That script read a hard-coded CSV,
stepped through it with up/down buttons and pushed the current row into
Shogun's capture name. This keeps that workflow but lets you browse for the
CSV, shows the whole list, and flags rows Shogun cannot use as a file name
instead of refusing to build the window.

Run this file in the MotionBuilder Python Editor to open the tool.

MotionBuilder 2024 (Python 3.10).
"""
import csv
import os
import sys
import unicodedata

from pyfbsdk import FBFilePopup, FBFilePopupStyle, FBTextJustify, ShowTool
from pyfbsdk_additions import FBCreateUniqueTool, FBHBoxLayout, FBVBoxLayout

try:
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _THIS_DIR = os.getcwd()
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from shogun_mobu_ui import (  # noqa: E402
    ShogunToolBase,
    alert,
    fill_main_region,
    make_button,
    make_edit,
    make_label,
    make_list,
)

TOOL_NAME = "Shogun Capture Name (CSV)"
TOOL_START_WIDTH = 520
TOOL_START_HEIGHT = 470
TOOL_MIN_WIDTH = 420
TOOL_MIN_HEIGHT = 340

# Which CSV column holds the name. The original script always read column 0.
NAME_COLUMN = 0


def is_usable_capture_name(text):
    """False if the name has characters Shogun will not accept in a file name.

    Same rule as the original script: reject full-width, wide and ambiguous
    East Asian characters, and spaces.
    """
    if not text:
        return False
    for char in text:
        if char == " ":
            return False
        if unicodedata.east_asian_width(char) in ("F", "A", "W"):
            return False
    return True


def read_names_from_csv(path):
    """Return the name column of every non-empty row. Raises on read errors."""
    names = []
    with open(path, newline="", encoding="utf-8-sig") as handle:
        for row in csv.reader(handle):
            if not row:
                continue
            value = row[NAME_COLUMN].strip() if len(row) > NAME_COLUMN else ""
            if value:
                names.append(value)
    return names


class CaptureNameCsvTool(ShogunToolBase):

    def __init__(self):
        super(CaptureNameCsvTool, self).__init__()
        self.names = []

    # -- layout ------------------------------------------------------------
    def populate(self, tool):
        main = FBVBoxLayout()
        fill_main_region(tool, main)

        main.Add(self.build_header(), 26)

        csv_row = FBHBoxLayout()
        csv_row.Add(make_label("CSV:", FBTextJustify.kFBTextJustifyRight), 40)
        self.csv_edit = make_edit("")
        csv_row.AddRelative(self.csv_edit, 1.0)
        csv_row.Add(make_button("Browse", self.on_browse), 70)
        csv_row.Add(make_button("Load", self.on_load), 60)
        main.Add(csv_row, 26)

        main.Add(make_label("Shot list  (x = cannot be used as a capture name)"), 22)

        self.name_list = make_list(multi_select=False)
        main.AddRelative(self.name_list, 1.0)

        step = FBHBoxLayout()
        step.AddRelative(make_button("< Prev", self.on_prev), 1.0)
        step.AddRelative(make_button("Next >", self.on_next), 1.0)
        main.Add(step, 28)

        main.Add(make_button("Set as Capture Name", self.on_set_name), 34)

        current_row = FBHBoxLayout()
        current_row.Add(make_label("In Shogun:", FBTextJustify.kFBTextJustifyRight), 80)
        self.current_label = make_label("-")
        current_row.AddRelative(self.current_label, 1.0)
        current_row.Add(make_button("Refresh", self.on_refresh_current), 80)
        main.Add(current_row, 24)

        main.Add(self.build_status_label(), 20)

    # -- CSV ---------------------------------------------------------------
    def on_browse(self, control=None, event=None):
        popup = FBFilePopup()
        popup.Caption = "Select the shot list CSV"
        popup.Style = FBFilePopupStyle.kFBFilePopupOpen
        # FBFilePopup raises if no filter is set.
        popup.Filter = "*.csv"
        current = (self.csv_edit.Text or "").strip()
        if current and os.path.isdir(os.path.dirname(current)):
            popup.Path = os.path.dirname(current)
        if not popup.Execute():
            return
        self.csv_edit.Text = popup.FullFilename
        self.load_csv()

    def on_load(self, control=None, event=None):
        self.load_csv()

    def load_csv(self):
        path = (self.csv_edit.Text or "").strip()
        if not path:
            self.status("Choose a CSV file first.")
            return
        if not os.path.isfile(path):
            self.status("File not found: {0}".format(path), "error")
            return

        try:
            names = read_names_from_csv(path)
        except (OSError, UnicodeDecodeError, csv.Error) as exc:
            self.status("Could not read the CSV: {0}".format(exc), "error")
            alert("CSV error", "Could not read:\n{0}\n\n{1}".format(path, exc))
            return

        self.names = names
        self.name_list.Items.removeAll()
        unusable = 0
        for name in names:
            if is_usable_capture_name(name):
                marker = " "
            else:
                marker = "x"
                unusable += 1
            self.name_list.Items.append("{0}  {1}".format(marker, name))

        if not names:
            self.status("No names found in column {0} of {1}.".format(
                NAME_COLUMN, os.path.basename(path)), "error")
            return

        if unusable:
            self.status("Loaded {0} name(s); {1} cannot be used as capture names.".format(
                len(names), unusable), "error")
        else:
            self.status("Loaded {0} name(s).".format(len(names)), "success")

    # -- list navigation ---------------------------------------------------
    def _selected_index(self):
        for index in range(len(self.names)):
            if self.name_list.IsSelected(index):
                return index
        return None

    def _select(self, index):
        for i in range(len(self.names)):
            self.name_list.Selected(i, i == index)
        self.name_list.ItemIndex = index

    def _step(self, delta):
        if not self.names:
            self.status("Load a CSV first.")
            return
        current = self._selected_index()
        if current is None:
            # Nothing picked yet: start at whichever end the user moved toward.
            index = 0 if delta > 0 else len(self.names) - 1
        else:
            index = current + delta
            if index < 0 or index >= len(self.names):
                self.status("Already at the {0} of the list.".format(
                    "start" if index < 0 else "end"))
                return
        self._select(index)
        self.status("{0} / {1}: {2}".format(index + 1, len(self.names),
                                            self.names[index]))

    def on_prev(self, control=None, event=None):
        self._step(-1)

    def on_next(self, control=None, event=None):
        self._step(1)

    # -- Shogun ------------------------------------------------------------
    def on_connected(self):
        self.refresh_current()

    def on_refresh_current(self, control=None, event=None):
        self.refresh_current()

    def refresh_current(self):
        if not self.require_connection():
            return
        ok, name = self.call(self.live.capture.capture_name(), "Get capture name")
        self.current_label.Caption = name if ok else "-"

    def on_set_name(self, control=None, event=None):
        if not self.require_connection():
            return
        index = self._selected_index()
        if index is None:
            self.status("Select a name in the list first.")
            return

        name = self.names[index]
        if not is_usable_capture_name(name):
            self.status("'{0}' cannot be used as a capture name.".format(name), "error")
            alert("Unusable name",
                  "'{0}' contains characters Shogun cannot use in a file name\n"
                  "(full-width / wide characters or spaces).".format(name))
            return

        ok, _ = self.call(self.live.capture.set_capture_name(name), "Set capture name")
        if ok:
            self.status("Capture name set to '{0}'.".format(name), "success")
            self.refresh_current()


def create_tool():
    tool = FBCreateUniqueTool(TOOL_NAME)
    tool.StartSizeX = TOOL_START_WIDTH
    tool.StartSizeY = TOOL_START_HEIGHT
    tool.MinSizeX = TOOL_MIN_WIDTH
    tool.MinSizeY = TOOL_MIN_HEIGHT

    CaptureNameCsvTool().populate(tool)
    ShowTool(tool)
    return tool


create_tool()
