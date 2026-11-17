#!/usr/bin/env python3
"""
pixel_common - Shared helpers for the Pixel Desktop suite.

Location-independent resolution of paths, so the suite works no matter
where the repository is cloned and no matter where companion projects
(WhatsApp PWA, YouTube Music, prayer-applet) live on the user's machine.

Resolution order for companion projects:
  1. Explicit user override in ~/.config/pixel-desktop.json
     -> {"companion_apps": {"whatsapp": "/some/other/dir", ...}}
  2. Well-known default location (~/Applications/<dir>)
  3. None (callers fall back to desktop entries or web URLs)

Desktop-entry discovery:
  Installed apps (deb / flatpak / AppImage wrapper) are found via XDG
  desktop entries (Gio), so launchers work with any standard installation
  of an application, not only the bespoke ~/Applications layout.
"""

import os
import json

# The suite's own installation directory (works wherever the repo is cloned).
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Optional user overrides for companion project locations.
CONFIG_FILE = os.path.expanduser("~/.config/pixel-desktop.json")

# Well-known default locations of companion projects.
DEFAULT_COMPANIONS = {
    "whatsapp": "~/Applications/whatsapp-pwa",
    "youtube_music": "~/Applications/youtube-music",
    "prayer_applet": "~/Applications/prayer-applet",
}

_companion_cache = {}


def load_config():
    """Load the optional user override config, or {} if missing/invalid."""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def companion_dir(key):
    """Return the base directory of a companion project, or None if not found."""
    if key in _companion_cache:
        return _companion_cache[key]

    result = None
    override = load_config().get("companion_apps", {}).get(key)
    candidates = []
    if override:
        candidates.append(override)
    default = DEFAULT_COMPANIONS.get(key)
    if default:
        candidates.append(default)

    for cand in candidates:
        path = os.path.expanduser(str(cand))
        if os.path.isdir(path):
            result = path
            break

    _companion_cache[key] = result
    return result


def companion_file(key, relpath):
    """Return an absolute path to a file inside a companion project, or None."""
    base = companion_dir(key)
    if not base or not relpath:
        return None
    path = os.path.join(base, relpath)
    return path if os.path.exists(path) else None


def find_desktop_app(tokens):
    """Find an installed application via XDG desktop entries.

    Matches any of the given lowercase tokens against the desktop entry ID,
    executable name, or command line. Returns a Gio.DesktopAppInfo or None.
    """
    try:
        import gi
        gi.require_version('Gio', '2.0')
        from gi.repository import Gio

        for app in Gio.AppInfo.get_all():
            if not isinstance(app, Gio.DesktopAppInfo):
                continue
            app_id = (app.get_id() or "").lower()
            exe = (app.get_executable() or "").lower()
            cmd = (app.get_commandline() or "").lower()
            if any(t in app_id or t in exe or t in cmd for t in tokens):
                return app
    except Exception:
        pass
    return None


def desktop_app_launch_cmd(app):
    """Return a shell command string that launches a Gio desktop app, or None."""
    if not app:
        return None
    try:
        filename = app.get_filename()
        if filename:
            # 'gio' ships with libglib2.0-bin (a hard dependency of this suite).
            return f'gio launch "{filename}"'
    except Exception:
        pass
    return None


def desktop_app_icon_spec(app):
    """Return an icon spec (theme name or file path) for a desktop app, or None."""
    if not app:
        return None
    try:
        icon = app.get_icon()
        return icon.to_string() if icon else None
    except Exception:
        pass
    return None
