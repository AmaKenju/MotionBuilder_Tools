# -*- coding: utf-8 -*-
"""Shared Shogun Live API connection helper for MotionBuilder tools.

This is the base layer for every Shogun Live tool in this repo. It:
  * locates the Shogun Live Python SDK on disk and puts it on sys.path
    (MotionBuilder's embedded Python has no pip-installed copy of it),
  * opens a vicon_core_api.Client to the Shogun Live terminal server,
  * keeps that connection alive as a module-level singleton so several tools
    can share one socket,
  * exposes every shogun_live_api service through one object.

Usage from another MotionBuilder script:

    import sys
    sys.path.append(r"C:\\Users\\Owner\\Documents\\GitHub\\MotionBuilder_Tools")

    import shogun_live_connect as shogun
    live = shogun.get(host="192.168.0.10")          # connects once, then reused
    result, name = live.capture.capture_name()
    print(name)

    # Or let errors raise instead of checking every Result:
    name = shogun.check(live.capture.capture_name())

Run this file directly in the Python Editor to connect and print a status
report (SDK path, server version, capture folder/name, subjects).

Requires Shogun Live to be running, with its terminal server reachable on
port 52800 (Shogun Live > the app is started normally; the port can be changed
with the --terminal-port command line argument).

Compatible with both Python 2.7 (MotionBuilder <=2020) and Python 3.7+ (MotionBuilder 2022+).
Note: on Python 2.7 the SDK needs the 'enum34' backport installed.
"""
from __future__ import print_function

import os
import re
import sys

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
# Default machine running Shogun Live. "localhost" if it is this machine.
DEFAULT_HOST = "localhost"
# Default terminal server port. Shogun Live uses 52800 unless started with
# --terminal-port=<n>.
DEFAULT_PORT = 52800

# Seconds to wait for the TCP connection, and for a command to answer.
CONNECT_TIMEOUT_SECONDS = 5.0
SEND_TIMEOUT_SECONDS = 30.0

# Set this to a folder containing 'vicon_core_api' and 'shogun_live_api'
# to skip auto-discovery, e.g.
#   r"C:\\Program Files\\Vicon\\ShogunLive1.19\\SDK\\Python"
SDK_PATH_OVERRIDE = ""

# Where to look for installed Shogun Live versions when auto-discovering.
SDK_SEARCH_ROOTS = [
    r"C:\Program Files\Vicon",
    r"C:\Program Files (x86)\Vicon",
]

# Sub-path from a ShogunLive install folder to the SDK Python folder.
SDK_SUB_PATH = os.path.join("SDK", "Python")

# The two packages shipped in the SDK. Each lives in its own sub-folder.
SDK_PACKAGES = ["vicon_core_api", "shogun_live_api"]


# ---------------------------------------------------------------------------
# SDK discovery
# ---------------------------------------------------------------------------
def _version_key(folder_name):
    """Sort key so 'ShogunLive1.19' beats 'ShogunLive1.9'."""
    match = re.search(r"(\d+)\.(\d+)", folder_name)
    if match:
        return (int(match.group(1)), int(match.group(2)))
    return (0, 0)


def find_sdk_roots():
    """Return candidate SDK 'Python' folders, newest Shogun Live version first."""
    if SDK_PATH_OVERRIDE:
        return [SDK_PATH_OVERRIDE]

    installs = []
    for root in SDK_SEARCH_ROOTS:
        if not os.path.isdir(root):
            continue
        for entry in os.listdir(root):
            if not entry.lower().startswith("shogunlive"):
                continue
            sdk_python = os.path.join(root, entry, SDK_SUB_PATH)
            if os.path.isdir(sdk_python):
                installs.append((_version_key(entry), sdk_python))

    installs.sort(key=lambda item: item[0], reverse=True)
    return [path for _key, path in installs]


def sdk_package_dirs(sdk_python_root):
    """Return the per-package folders to add to sys.path, or None if incomplete.

    The SDK ships as 'SDK/Python/<package>/<package>/__init__.py', so the
    importable directory is one level below the package folder.
    """
    dirs = []
    for package in SDK_PACKAGES:
        outer = os.path.join(sdk_python_root, package)
        if os.path.isdir(os.path.join(outer, package)):
            dirs.append(outer)
        elif os.path.isfile(os.path.join(outer, "__init__.py")):
            # Flat layout: SDK/Python/<package>/__init__.py
            dirs.append(sdk_python_root)
        else:
            return None
    return dirs


def ensure_sdk_on_path(verbose=True):
    """Make 'vicon_core_api' and 'shogun_live_api' importable. Return the path used."""
    try:
        import vicon_core_api  # noqa: F401
        import shogun_live_api  # noqa: F401
        return os.path.dirname(os.path.dirname(vicon_core_api.__file__))
    except ImportError:
        pass

    tried = []
    for sdk_root in find_sdk_roots():
        tried.append(sdk_root)
        dirs = sdk_package_dirs(sdk_root)
        if not dirs:
            continue
        for path in dirs:
            if path not in sys.path:
                sys.path.insert(0, path)
        try:
            import vicon_core_api  # noqa: F401
            import shogun_live_api  # noqa: F401
        except ImportError as exc:
            if "enum" in str(exc):
                raise ImportError(
                    "The Shogun Live SDK needs the 'enum34' backport on Python 2.7 "
                    "(MotionBuilder <=2020). Either run this on MotionBuilder 2022+ "
                    "or install enum34 into MotionBuilder's Python. ({0})".format(exc))
            continue
        if verbose:
            print("Shogun Live SDK: {0}".format(sdk_root))
        return sdk_root

    raise ImportError(
        "Could not find the Shogun Live Python SDK. Looked under: {0}\n"
        "Set SDK_PATH_OVERRIDE at the top of shogun_live_connect.py to the folder "
        "containing 'vicon_core_api' and 'shogun_live_api'.".format(tried or SDK_SEARCH_ROOTS))


# ---------------------------------------------------------------------------
# Result handling
# ---------------------------------------------------------------------------
def check(api_return):
    """Raise on a failed API call, otherwise return the call's output value(s).

    Every SDK call returns either a Result, or a tuple whose first element is a
    Result. This mirrors check_api_call() in the SDK's sample_scripts/utils.py.
    """
    from vicon_core_api import Result, RPCError

    if isinstance(api_return, (Result, bool)):
        if api_return:
            return None
        raise RPCError(str(api_return))
    if not api_return[0]:
        raise RPCError(str(api_return[0]))
    if len(api_return) > 2:
        return api_return[1:]
    return api_return[1]


def ok(api_return):
    """True if the API call succeeded. Never raises."""
    from vicon_core_api import Result

    if isinstance(api_return, (Result, bool)):
        return bool(api_return)
    return bool(api_return[0])


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
class ShogunLive(object):
    """A live connection to Shogun Live, with every service exposed lazily.

    Services (see the SDK docs for each one's methods):
        .capture       CaptureServices             start/stop capture, take info
        .subjects      SubjectServices             subject list, import/export
        .application   ApplicationServices         system config, license, shutdown
        .playback      PlaybackServices            playback transport
        .cameras       CameraDeviceServices        camera devices
        .calibration   CameraCalibrationServices   camera calibration
        .subject_cal   SubjectCalibrationServices  subject calibration
        .selection     SelectionServices           selection in the GUI
        .view          ViewServices                view layouts
        .log           LogServices                 application log
    """

    _SERVICE_MAP = {
        "capture": "CaptureServices",
        "subjects": "SubjectServices",
        "application": "ApplicationServices",
        "playback": "PlaybackServices",
        "cameras": "CameraDeviceServices",
        "calibration": "CameraCalibrationServices",
        "subject_cal": "SubjectCalibrationServices",
        "selection": "SelectionServices",
        "view": "ViewServices",
        "log": "LogServices",
    }

    def __init__(self, host, port, connect_timeout, send_timeout):
        from vicon_core_api import Client

        self.host = host
        self.port = port
        self._services = {}
        self._failure_message = None
        self.client = Client(
            host,
            port,
            connect_timeout_seconds=connect_timeout,
            send_timeout_seconds=send_timeout,
            client_failed_callback=self._on_client_failed)

    def _on_client_failed(self, message):
        self._failure_message = message
        print("Shogun Live client: {0}".format(message))

    @property
    def connected(self):
        return bool(self.client) and self.client.connected

    @property
    def endpoint(self):
        return "{0}:{1}".format(self.host, self.port)

    @property
    def failure_message(self):
        return self._failure_message

    def server_version(self):
        return self.client.server_version()

    def __getattr__(self, name):
        """Create service objects on first use, e.g. live.capture."""
        class_name = ShogunLive._SERVICE_MAP.get(name)
        if class_name is None:
            raise AttributeError(name)
        if name not in self._services:
            import shogun_live_api
            self._services[name] = getattr(shogun_live_api, class_name)(self.client)
        return self._services[name]

    def stop(self):
        if self.client:
            self.client.stop()
        self._services = {}

    def __enter__(self):
        return self

    def __exit__(self, _type, _value, _traceback):
        self.stop()

    def __repr__(self):
        return "<ShogunLive {0} {1}>".format(
            self.endpoint, "connected" if self.connected else "disconnected")


# Module-level singleton, so several tools share one socket.
_CONNECTION = [None]


def connect(host=None, port=None, reconnect=False, verbose=True):
    """Connect to Shogun Live and return a ShogunLive object.

    Reuses the existing connection unless it dropped, the endpoint changed, or
    reconnect=True. Raises RuntimeError if the connection could not be made.
    """
    host = DEFAULT_HOST if host is None else host
    port = DEFAULT_PORT if port is None else port

    current = _CONNECTION[0]
    if current is not None:
        same_endpoint = (current.host == host and current.port == port)
        if current.connected and same_endpoint and not reconnect:
            return current
        current.stop()
        _CONNECTION[0] = None

    ensure_sdk_on_path(verbose=verbose)

    live = ShogunLive(host, port, CONNECT_TIMEOUT_SECONDS, SEND_TIMEOUT_SECONDS)
    if not live.connected:
        live.stop()
        raise RuntimeError(
            "Could not connect to Shogun Live at {0}:{1}.\n"
            "  - Is Shogun Live running on that machine?\n"
            "  - Is port {1} open through the firewall?\n"
            "  - If Shogun Live was started with --terminal-port, pass that port here.\n"
            "  ({2})".format(host, port, live.failure_message or "no further detail"))

    _CONNECTION[0] = live
    if verbose:
        version = live.server_version()
        print("Connected to Shogun Live at {0} (terminal protocol {1}).".format(
            live.endpoint, "{0}.{1}".format(*version) if version else "unknown"))
    return live


def get(host=None, port=None, verbose=False):
    """Return the shared connection, connecting on first use. Use this from tools."""
    return connect(host=host, port=port, verbose=verbose)


def current():
    """Return the shared connection if there is a live one, else None. Never connects."""
    live = _CONNECTION[0]
    if live is not None and live.connected:
        return live
    return None


def disconnect():
    """Close the shared connection, if any."""
    live = _CONNECTION[0]
    if live is not None:
        live.stop()
        _CONNECTION[0] = None
        print("Disconnected from Shogun Live.")


# ---------------------------------------------------------------------------
# Status report (what runs when this file is executed directly)
# ---------------------------------------------------------------------------
def _report_line(label, api_return):
    if ok(api_return):
        value = api_return if not isinstance(api_return, tuple) else api_return[1]
        print("  {0}: {1}".format(label, value))
    else:
        result = api_return if not isinstance(api_return, tuple) else api_return[0]
        print("  {0}: <{1}>".format(label, result))


def status(host=None, port=None):
    """Connect (if needed) and print what Shogun Live currently reports."""
    live = connect(host=host, port=port, verbose=True)

    print("Capture:")
    _report_line("folder", live.capture.capture_folder())
    _report_line("name", live.capture.capture_name())
    _report_line("description", live.capture.capture_description())

    state_return = live.capture.latest_capture_state()
    if ok(state_return):
        _result, capture_id, state = state_return
        print("  latest capture: id={0} state={1}".format(capture_id, state.name))
    else:
        print("  latest capture: <{0}>".format(state_return[0]))

    subjects_return = live.subjects.subjects()
    enabled_return = live.subjects.enabled_subjects()
    if ok(subjects_return):
        subjects = subjects_return[1]
        enabled = enabled_return[1] if ok(enabled_return) else []
        print("Subjects ({0}):".format(len(subjects)))
        for name in subjects:
            print("  - {0}{1}".format(name, "" if name in enabled else "  (disabled)"))
    else:
        print("Subjects: <{0}>".format(subjects_return[0]))

    return live


if __name__ == "__main__":
    status()
