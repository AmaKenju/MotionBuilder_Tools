# -*- coding: utf-8 -*-
"""Shared UI pieces for the Shogun Live tools in this repo.

Every Shogun tool window needs the same things: a host field, a Connect
button, a connection indicator and a status line at the bottom. This module
provides that as a base class so each tool file only contains its own logic.

Subclass ShogunToolBase, build your layout in populate(), and call
build_header() / build_status_label() for the common rows. Override
on_connected() to refresh your widgets once a connection is established.

MotionBuilder 2024 (Python 3.10).
"""
import os
import sys
import traceback

from pyfbsdk import (
    FBAddRegionParam,
    FBAttachType,
    FBButton,
    FBButtonStyle,
    FBEdit,
    FBLabel,
    FBList,
    FBListStyle,
    FBMessageBox,
    FBTextJustify,
)
from pyfbsdk_additions import FBHBoxLayout, FBVBoxLayout

try:
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _THIS_DIR = os.getcwd()

if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import shogun_live_connect as shogun  # noqa: E402  (needs _THIS_DIR on sys.path)

DEFAULT_HOST = "localhost"


# ---------------------------------------------------------------------------
# Widget helpers
# ---------------------------------------------------------------------------
def make_label(caption="", justify=None):
    label = FBLabel()
    label.Caption = caption
    if justify is not None:
        label.Justify = justify
    return label


def make_button(caption, callback=None, hint=""):
    button = FBButton()
    button.Caption = caption
    button.Justify = FBTextJustify.kFBTextJustifyCenter
    if hint:
        button.Hint = hint
    if callback is not None:
        button.OnClick.Add(callback)
    return button


def make_checkbox(caption, callback=None, state=False):
    button = FBButton()
    button.Caption = caption
    button.Style = FBButtonStyle.kFBCheckbox
    button.State = 1 if state else 0
    if callback is not None:
        button.OnClick.Add(callback)
    return button


def make_edit(text=""):
    edit = FBEdit()
    edit.Text = text
    return edit


def make_list(multi_select=False, on_change=None):
    widget = FBList()
    widget.Style = FBListStyle.kFBVerticalList
    widget.MultiSelect = multi_select
    if multi_select:
        widget.ExtendedSelect = True
    if on_change is not None:
        widget.OnChange.Add(on_change)
    return widget


def fill_main_region(tool, layout, margin=6):
    """Give the tool a single full-size region and put 'layout' in it."""
    x = FBAddRegionParam(margin, FBAttachType.kFBAttachLeft, "")
    y = FBAddRegionParam(margin, FBAttachType.kFBAttachTop, "")
    w = FBAddRegionParam(-margin, FBAttachType.kFBAttachRight, "")
    h = FBAddRegionParam(-margin, FBAttachType.kFBAttachBottom, "")
    tool.AddRegion("main", "main", x, y, w, h)
    tool.SetControl("main", layout)


# ---------------------------------------------------------------------------
# Base tool
# ---------------------------------------------------------------------------
class ShogunToolBase(object):
    """Connection header, status line and Shogun error handling."""

    def __init__(self):
        self.live = None
        self.host_edit = None
        self.conn_label = None
        self.status_label = None

    # -- common rows -------------------------------------------------------
    def build_header(self):
        """Host field + Connect button + connection indicator, as one HBox."""
        row = FBHBoxLayout()
        row.Add(make_label("Host:", FBTextJustify.kFBTextJustifyRight), 38)

        self.host_edit = make_edit(DEFAULT_HOST)
        row.Add(self.host_edit, 170)

        row.Add(make_button("Connect", self.on_connect), 80)

        self.conn_label = make_label("Not connected")
        row.AddRelative(self.conn_label, 1.0)
        return row

    def build_status_label(self):
        self.status_label = make_label("Not connected.")
        return self.status_label

    # -- status ------------------------------------------------------------
    def status(self, message, kind="info"):
        if self.status_label is not None:
            self.status_label.Caption = message
        print("[{0}] {1}".format(kind, message))

    def update_connection_label(self):
        if self.conn_label is None:
            return
        if self.connected:
            self.conn_label.Caption = "Connected to {0}".format(self.live.endpoint)
        else:
            self.conn_label.Caption = "Not connected"

    # -- connection --------------------------------------------------------
    @property
    def connected(self):
        return self.live is not None and self.live.connected

    def require_connection(self):
        if self.connected:
            return True
        self.status("Not connected to Shogun Live. Press Connect.", "error")
        self.update_connection_label()
        return False

    def on_connect(self, control=None, event=None):
        host = (self.host_edit.Text or "").strip() or DEFAULT_HOST
        self.host_edit.Text = host
        self.status("Connecting to {0}...".format(host))
        try:
            self.live = shogun.connect(host=host, reconnect=True, verbose=True)
        except Exception as exc:
            traceback.print_exc()
            self.live = None
            self.update_connection_label()
            self.status("Connection failed: {0}".format(exc), "error")
            FBMessageBox("Connection Error",
                         "Could not connect to Shogun Live at {0}.\n"
                         "Make sure Shogun Live is running.\n\n{1}".format(host, exc),
                         "OK", None, None)
            return
        self.update_connection_label()
        self.on_connected()

    def on_connected(self):
        """Called after a successful connect. Override to refresh widgets."""

    # -- API call helper ---------------------------------------------------
    def call(self, api_return, what, quiet=False):
        """Unpack an SDK return, reporting failures on the status line.

        Returns (True, value_or_tuple) on success, (False, None) on failure.
        Pass quiet=True where a failure is expected or where an earlier, more
        specific message must stay on the status line.
        """
        try:
            if not shogun.ok(api_return):
                result = api_return if not isinstance(api_return, tuple) else api_return[0]
                if not quiet:
                    self.status("{0} failed: {1}".format(what, result), "error")
                return False, None
        except Exception as exc:
            if not quiet:
                self.status("{0} failed: {1}".format(what, exc), "error")
            return False, None

        if not isinstance(api_return, tuple):
            return True, None
        if len(api_return) == 1:
            return True, None
        if len(api_return) == 2:
            return True, api_return[1]
        return True, api_return[1:]


def confirm(title, message):
    """Yes/No dialog. True when the user picked Yes."""
    return FBMessageBox(title, message, "Yes", "No", None) == 1


def alert(title, message):
    FBMessageBox(title, message, "OK", None, None)
