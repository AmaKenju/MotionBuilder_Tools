# -*- coding: utf-8 -*-
"""Shogun Subject Group Manager as a native MotionBuilder tool window.

A port of ShogunTools/ShogunSubjectGroups.py (tkinter) to a dockable pyfbsdk
FBTool. Same behaviour: list the subjects loaded in Shogun Live, group them,
and enable/disable a whole group in one click.

Group definitions live in 'subject_groups.json' next to this file - separate
from the standalone tool's copy in the ShogunTools repo.

Run this file in the MotionBuilder Python Editor to open the tool. It is
registered by name, so re-running it replaces the existing window rather than
opening a second one.

Requires Shogun Live to be running and reachable; the connection itself is
handled by shogun_live_connect.py in this folder.

MotionBuilder 2024 (Python 3.10).
"""
import json
import os
import sys
import traceback

from pyfbsdk import (
    FBAddRegionParam,
    FBAttachType,
    FBButton,
    FBEdit,
    FBLabel,
    FBList,
    FBListStyle,
    FBMessageBox,
    FBTextJustify,
    ShowTool,
)
from pyfbsdk_additions import FBCreateUniqueTool, FBHBoxLayout, FBVBoxLayout

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
TOOL_NAME = "Shogun Subject Groups"
DEFAULT_HOST = "localhost"

TOOL_START_WIDTH = 900
TOOL_START_HEIGHT = 620
TOOL_MIN_WIDTH = 640
TOOL_MIN_HEIGHT = 480

try:
    _THIS_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # __file__ is undefined if the code was pasted straight into the editor.
    _THIS_DIR = os.getcwd()

if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import shogun_live_connect as shogun  # noqa: E402  (needs _THIS_DIR on sys.path)

# Keyed off the imported module rather than _THIS_DIR: a module always has a
# real __file__, so the groups file stays next to the tools even when this
# script is launched from the Crescent menu.
SUBJECT_GROUPS_FILE = os.path.join(shogun.TOOLS_DIR, "subject_groups.json")


# ---------------------------------------------------------------------------
# Group persistence
# ---------------------------------------------------------------------------
def load_subject_groups():
    """Read the groups file. Returns [] if it is missing or unreadable."""
    try:
        with open(SUBJECT_GROUPS_FILE, encoding="utf-8") as handle:
            data = json.load(handle)
        raw = data.get("groups", []) if isinstance(data, dict) else data
        groups = []
        for group in raw:
            if isinstance(group, dict) and group.get("name"):
                groups.append({
                    "name": str(group["name"]),
                    "subjects": [str(s) for s in group.get("subjects", [])],
                })
        return groups
    except (OSError, ValueError):
        return []


def save_subject_groups(groups):
    try:
        with open(SUBJECT_GROUPS_FILE, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "groups": groups}, handle,
                      ensure_ascii=False, indent=2)
        return True
    except OSError as exc:
        print("Failed to save subject groups: {0}".format(exc))
        return False


# ---------------------------------------------------------------------------
# Tool
# ---------------------------------------------------------------------------
class SubjectGroupTool(object):
    """Builds the tool layout and holds all its state."""

    TYPE_LABELS = {
        "ERigidObject": "Prop",
        "ELabelingCluster": "Cluster",
        "EGeneral": "Subject",
    }

    def __init__(self):
        self.live = None
        self.groups = load_subject_groups()
        # Parallel to the subject list widget: (name, type_label, enabled).
        self.subjects = []
        self.selected_group_index = None

    # -- layout ------------------------------------------------------------
    def populate(self, tool):
        x = FBAddRegionParam(6, FBAttachType.kFBAttachLeft, "")
        y = FBAddRegionParam(6, FBAttachType.kFBAttachTop, "")
        w = FBAddRegionParam(-6, FBAttachType.kFBAttachRight, "")
        h = FBAddRegionParam(-6, FBAttachType.kFBAttachBottom, "")
        tool.AddRegion("main", "main", x, y, w, h)

        main = FBVBoxLayout()
        tool.SetControl("main", main)

        main.Add(self._build_header(), 26)

        body = FBHBoxLayout()
        body.AddRelative(self._build_subject_column(), 1.0)
        body.AddRelative(self._build_group_column(), 1.0)
        main.AddRelative(body, 1.0)

        self.status_label = FBLabel()
        self.status_label.Caption = "Not connected."
        main.Add(self.status_label, 20)

        self.refresh_group_list()
        self._update_connection_label()

    def _build_header(self):
        row = FBHBoxLayout()

        label = FBLabel()
        label.Caption = "Host:"
        label.Justify = FBTextJustify.kFBTextJustifyRight
        row.Add(label, 38)

        self.host_edit = FBEdit()
        self.host_edit.Text = DEFAULT_HOST
        row.Add(self.host_edit, 170)

        connect_btn = FBButton()
        connect_btn.Caption = "Connect"
        connect_btn.Justify = FBTextJustify.kFBTextJustifyCenter
        connect_btn.OnClick.Add(self.on_connect)
        row.Add(connect_btn, 80)

        self.conn_label = FBLabel()
        self.conn_label.Caption = "Not connected"
        row.AddRelative(self.conn_label, 1.0)

        return row

    def _build_subject_column(self):
        col = FBVBoxLayout()

        head = FBHBoxLayout()
        title = FBLabel()
        title.Caption = "Subjects in Shogun"
        head.AddRelative(title, 1.0)
        refresh_btn = FBButton()
        refresh_btn.Caption = "Refresh"
        refresh_btn.Justify = FBTextJustify.kFBTextJustifyCenter
        refresh_btn.OnClick.Add(self.on_refresh)
        head.Add(refresh_btn, 80)
        col.Add(head, 24)

        self.subject_list = FBList()
        self.subject_list.Style = FBListStyle.kFBVerticalList
        self.subject_list.MultiSelect = True
        self.subject_list.ExtendedSelect = True
        col.AddRelative(self.subject_list, 1.0)

        hint = FBLabel()
        hint.Caption = "* enabled / - disabled   |   multi-select with Ctrl / Shift"
        col.Add(hint, 18)

        buttons = FBHBoxLayout()
        enable_btn = FBButton()
        enable_btn.Caption = "Enable Selected"
        enable_btn.Justify = FBTextJustify.kFBTextJustifyCenter
        enable_btn.OnClick.Add(self.on_enable_selected)
        buttons.AddRelative(enable_btn, 1.0)
        disable_btn = FBButton()
        disable_btn.Caption = "Disable Selected"
        disable_btn.Justify = FBTextJustify.kFBTextJustifyCenter
        disable_btn.OnClick.Add(self.on_disable_selected)
        buttons.AddRelative(disable_btn, 1.0)
        col.Add(buttons, 28)

        return col

    def _build_group_column(self):
        col = FBVBoxLayout()

        title = FBLabel()
        title.Caption = "Groups"
        col.Add(title, 20)

        self.group_list = FBList()
        self.group_list.Style = FBListStyle.kFBVerticalList
        self.group_list.MultiSelect = False
        self.group_list.OnChange.Add(self.on_group_changed)
        col.AddRelative(self.group_list, 0.8)

        create = FBHBoxLayout()
        self.new_group_edit = FBEdit()
        self.new_group_edit.Text = ""
        create.AddRelative(self.new_group_edit, 1.0)
        new_btn = FBButton()
        new_btn.Caption = "New"
        new_btn.Justify = FBTextJustify.kFBTextJustifyCenter
        new_btn.OnClick.Add(self.on_create_group)
        create.Add(new_btn, 70)
        col.Add(create, 26)

        ops = FBHBoxLayout()
        for caption, callback in (("Add Selected", self.on_add_to_group),
                                  ("Replace", self.on_replace_group),
                                  ("Delete", self.on_delete_group)):
            button = FBButton()
            button.Caption = caption
            button.Justify = FBTextJustify.kFBTextJustifyCenter
            button.OnClick.Add(callback)
            ops.AddRelative(button, 1.0)
        col.Add(ops, 26)

        contents_title = FBLabel()
        contents_title.Caption = "Group Contents"
        col.Add(contents_title, 20)

        self.member_list = FBList()
        self.member_list.Style = FBListStyle.kFBVerticalList
        self.member_list.MultiSelect = True
        self.member_list.ExtendedSelect = True
        col.AddRelative(self.member_list, 1.0)

        member_hint = FBLabel()
        member_hint.Caption = "x = not loaded in Shogun"
        col.Add(member_hint, 18)

        member_ops = FBHBoxLayout()
        remove_btn = FBButton()
        remove_btn.Caption = "Remove Members"
        remove_btn.Justify = FBTextJustify.kFBTextJustifyCenter
        remove_btn.OnClick.Add(self.on_remove_members)
        member_ops.Add(remove_btn, 140)
        col.Add(member_ops, 26)

        toggle = FBHBoxLayout()
        group_enable = FBButton()
        group_enable.Caption = "Enable Group"
        group_enable.Justify = FBTextJustify.kFBTextJustifyCenter
        group_enable.OnClick.Add(self.on_enable_group)
        toggle.AddRelative(group_enable, 1.0)
        group_disable = FBButton()
        group_disable.Caption = "Disable Group"
        group_disable.Justify = FBTextJustify.kFBTextJustifyCenter
        group_disable.OnClick.Add(self.on_disable_group)
        toggle.AddRelative(group_disable, 1.0)
        col.Add(toggle, 30)

        return col

    # -- connection --------------------------------------------------------
    def _status(self, message, kind="info"):
        self.status_label.Caption = message
        print("[{0}] {1}".format(kind, message))

    def _update_connection_label(self):
        if self.live is not None and self.live.connected:
            self.conn_label.Caption = "Connected to {0}".format(self.live.endpoint)
        else:
            self.conn_label.Caption = "Not connected"

    def _require_connection(self):
        if self.live is not None and self.live.connected:
            return True
        self._status("Not connected to Shogun Live. Press Connect.", "error")
        self._update_connection_label()
        return False

    def on_connect(self, control=None, event=None):
        host = (self.host_edit.Text or "").strip() or DEFAULT_HOST
        self.host_edit.Text = host
        self._status("Connecting to {0}...".format(host))
        try:
            self.live = shogun.connect(host=host, reconnect=True, verbose=True)
        except Exception as exc:
            traceback.print_exc()
            self.live = None
            self._update_connection_label()
            self._status("Connection failed: {0}".format(exc), "error")
            FBMessageBox("Connection Error",
                         "Could not connect to Shogun Live at {0}.\n"
                         "Make sure Shogun Live is running.\n\n{1}".format(host, exc),
                         "OK", None, None)
            return
        self._update_connection_label()
        self.refresh_subjects()

    # -- subjects ----------------------------------------------------------
    def _subject_type_label(self, name):
        try:
            result, subject_type = self.live.subjects.subject_type(name)
        except Exception:
            return "Subject"
        if not result:
            return "Subject"
        key = getattr(subject_type, "name", str(subject_type))
        return self.TYPE_LABELS.get(key, str(key))

    def refresh_subjects(self, control=None, event=None):
        if not self._require_connection():
            return
        try:
            result, names = self.live.subjects.subjects()
            if not result:
                self._status("Failed to get subjects: {0}".format(result), "error")
                names = []

            enabled = []
            try:
                enabled_result, enabled = self.live.subjects.enabled_subjects()
                if not enabled_result:
                    enabled = []
            except Exception:
                enabled = []
            enabled_set = set(enabled)

            self.subjects = [
                (name, self._subject_type_label(name), name in enabled_set)
                for name in names
            ]

            self.subject_list.Items.removeAll()
            for name, type_label, is_enabled in self.subjects:
                marker = "*" if is_enabled else "-"
                self.subject_list.Items.append(
                    "{0}  {1}   [{2}]".format(marker, name, type_label))

            self.refresh_member_list()
            self._status("Loaded {0} subject(s), {1} enabled.".format(
                len(self.subjects), len(enabled_set)), "success")
        except Exception as exc:
            traceback.print_exc()
            self._update_connection_label()
            self._status("Refresh failed: {0}".format(exc), "error")

    def on_refresh(self, control=None, event=None):
        self.refresh_subjects()

    def _selected_subject_names(self):
        return [self.subjects[i][0]
                for i in range(len(self.subjects))
                if self.subject_list.IsSelected(i)]

    def _apply_enabled(self, names, enable):
        """Set the enabled state on each subject. Returns (ok_count, failed_names)."""
        succeeded, failed = 0, []
        for name in names:
            try:
                if self.live.subjects.set_subject_enabled(name, enable):
                    succeeded += 1
                else:
                    failed.append(name)
            except Exception:
                failed.append(name)
        return succeeded, failed

    def _toggle_selected(self, enable):
        if not self._require_connection():
            return
        names = self._selected_subject_names()
        if not names:
            self._status("Select one or more subjects first.")
            return
        succeeded, failed = self._apply_enabled(names, enable)
        word = "enabled" if enable else "disabled"
        self.refresh_subjects()
        if failed:
            self._status("{0} subject(s) {1}, {2} failed.".format(
                succeeded, word, len(failed)), "error")
        else:
            self._status("{0} subject(s) {1}.".format(succeeded, word), "success")

    def on_enable_selected(self, control=None, event=None):
        self._toggle_selected(True)

    def on_disable_selected(self, control=None, event=None):
        self._toggle_selected(False)

    # -- groups ------------------------------------------------------------
    def refresh_group_list(self):
        self.group_list.Items.removeAll()
        for group in self.groups:
            self.group_list.Items.append("{0}   ({1})".format(
                group["name"], len(group["subjects"])))
        if self.selected_group_index is not None and \
                self.selected_group_index < len(self.groups):
            self.group_list.ItemIndex = self.selected_group_index
        self.refresh_member_list()

    def _selected_group(self):
        # Tracked explicitly rather than read from group_list.ItemIndex: an
        # untouched FBList can report index 0, which would silently act on the
        # first group when the user has not picked one.
        index = self.selected_group_index
        if index is None or index < 0 or index >= len(self.groups):
            return None
        return self.groups[index]

    def on_group_changed(self, control=None, event=None):
        index = self.group_list.ItemIndex
        self.selected_group_index = index if index is not None and index >= 0 else None
        self.refresh_member_list()

    def refresh_member_list(self):
        self.member_list.Items.removeAll()
        group = self._selected_group()
        if group is None:
            return
        loaded = {name: is_enabled for name, _type, is_enabled in self.subjects}
        for name in group["subjects"]:
            if name in loaded:
                marker = "*" if loaded[name] else "-"
            else:
                marker = "x"
            self.member_list.Items.append("{0}  {1}".format(marker, name))

    def _persist(self, message, kind="success"):
        if save_subject_groups(self.groups):
            self._status(message, kind)
        else:
            self._status("Saved in memory but writing {0} failed.".format(
                SUBJECT_GROUPS_FILE), "error")

    def _select_group_by_name(self, name):
        for index, group in enumerate(self.groups):
            if group["name"] == name:
                self.selected_group_index = index
                self.group_list.ItemIndex = index
                return

    def on_create_group(self, control=None, event=None):
        name = (self.new_group_edit.Text or "").strip()
        if not name:
            self._status("Enter a group name first.")
            return
        names = self._selected_subject_names()
        if not names:
            self._status("Select the subjects to put in the group.")
            return

        for group in self.groups:
            if group["name"] == name:
                answer = FBMessageBox(
                    "Confirm",
                    'Group "{0}" already exists. Overwrite it?'.format(name),
                    "Yes", "No", None)
                if answer != 1:
                    return
                group["subjects"] = list(names)
                self.refresh_group_list()
                self._select_group_by_name(name)
                self.refresh_member_list()
                self._persist('Group "{0}" overwritten ({1} subject(s)).'.format(
                    name, len(names)))
                return

        self.groups.append({"name": name, "subjects": list(names)})
        self.refresh_group_list()
        self._select_group_by_name(name)
        self.refresh_member_list()
        self.new_group_edit.Text = ""
        self._persist('Group "{0}" created ({1} subject(s)).'.format(name, len(names)))

    def on_add_to_group(self, control=None, event=None):
        group = self._selected_group()
        if group is None:
            self._status("Select a target group first.")
            return
        names = self._selected_subject_names()
        if not names:
            self._status("Select the subjects to add.")
            return
        added = 0
        for name in names:
            if name not in group["subjects"]:
                group["subjects"].append(name)
                added += 1
        self.refresh_group_list()
        self._select_group_by_name(group["name"])
        self.refresh_member_list()
        self._persist('Added {0} subject(s) to "{1}".'.format(added, group["name"]))

    def on_replace_group(self, control=None, event=None):
        group = self._selected_group()
        if group is None:
            self._status("Select the group to replace.")
            return
        names = self._selected_subject_names()
        if not names:
            self._status("Select the subjects to use.")
            return
        group["subjects"] = list(names)
        self.refresh_group_list()
        self._select_group_by_name(group["name"])
        self.refresh_member_list()
        self._persist('"{0}" replaced with {1} subject(s).'.format(
            group["name"], len(names)))

    def on_remove_members(self, control=None, event=None):
        group = self._selected_group()
        if group is None:
            self._status("Select a group first.")
            return
        to_remove = {group["subjects"][i]
                     for i in range(len(group["subjects"]))
                     if self.member_list.IsSelected(i)}
        if not to_remove:
            self._status("Select the members to remove.")
            return
        group["subjects"] = [s for s in group["subjects"] if s not in to_remove]
        self.refresh_group_list()
        self._select_group_by_name(group["name"])
        self.refresh_member_list()
        self._persist('Removed {0} member(s) from "{1}".'.format(
            len(to_remove), group["name"]))

    def on_delete_group(self, control=None, event=None):
        group = self._selected_group()
        if group is None:
            self._status("Select the group to delete.")
            return
        answer = FBMessageBox("Confirm",
                              'Delete group "{0}"?'.format(group["name"]),
                              "Yes", "No", None)
        if answer != 1:
            return
        name = group["name"]
        self.groups = [g for g in self.groups if g is not group]
        self.selected_group_index = None
        self.refresh_group_list()
        self.member_list.Items.removeAll()
        self._persist('Group "{0}" deleted.'.format(name))

    def _toggle_group(self, enable):
        if not self._require_connection():
            return
        group = self._selected_group()
        if group is None:
            self._status("Select a group first.")
            return
        names = group["subjects"]
        if not names:
            self._status("This group has no subjects.")
            return

        succeeded, failed = self._apply_enabled(names, enable)
        word = "enabled" if enable else "disabled"
        self.refresh_subjects()
        if failed:
            FBMessageBox("Some subjects not found",
                         'Group "{0}" {1}.\n\nNot loaded / not found:\n  {2}'.format(
                             group["name"], word, "\n  ".join(failed)),
                         "OK", None, None)
            self._status('"{0}" {1}: {2} ok, {3} failed.'.format(
                group["name"], word, succeeded, len(failed)), "error")
        else:
            self._status('"{0}" {1} ({2} subject(s)).'.format(
                group["name"], word, succeeded), "success")

    def on_enable_group(self, control=None, event=None):
        self._toggle_group(True)

    def on_disable_group(self, control=None, event=None):
        self._toggle_group(False)


def create_tool():
    tool = FBCreateUniqueTool(TOOL_NAME)
    tool.StartSizeX = TOOL_START_WIDTH
    tool.StartSizeY = TOOL_START_HEIGHT
    tool.MinSizeX = TOOL_MIN_WIDTH
    tool.MinSizeY = TOOL_MIN_HEIGHT

    SubjectGroupTool().populate(tool)
    ShowTool(tool)
    return tool


create_tool()
