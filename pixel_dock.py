#!/usr/bin/env python3
"""
Pixel Dock - Native Google Pixel Material You Floating Auto-Hide Dock (Plank Replacement)
Generic GTK/GNOME desktop environments (laptops and desktops)

Features:
- Material Design 3 Floating Dock Surface with Monet tonal container elevation
- Full Plank Replacement: Auto-Hide / Window-Dodge behavior
- 100% Invisible when hidden: Slides completely offscreen (y = 1095), 0 pixels visible
- Global Bottom-Edge Hover Reveal: Reveals instantly when cursor hits screen bottom (y >= 1078) even with fullscreen apps
- Leftmost Pixel App Drawer button (⸬) -> opens full-screen Pixel App Drawer overlay
- Android Recent Apps button (▢) -> opens Recent Apps multitasking overview
- Google Pixel Search Pill -> opens App Drawer search
- Dynamic App Badges: Pinned apps + Running Unpinned Apps with running dot indicators (•)
- Single-Click Restore/Unminimize: If an app is running/minimized, left-clicking restores and focuses its window (never opens duplicate windows)
- Right-Click Material 3 Context Menu:
  * Application Profiles / Desktop Actions (e.g. WhatsApp Work/Admin/Personal/All, Chrome New Window/Incognito)
  * "📌 Keep in Dock" / "📌 Remove from Dock"
  * "✕ Close Window"
- Dynamic Width Expansion/Contraction as apps open and close
- Smooth 60fps spring/ease animations, 0.0% CPU when stationary
"""

import sys, os, time, math, json, shlex, subprocess, signal, glob
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkPixbuf', '2.0')
gi.require_version('PangoCairo', '1.0')
gi.require_version('Gio', '2.0')
from gi.repository import Gtk, Gdk, GdkPixbuf, GLib, Gio, Pango, PangoCairo
import cairo

import pixel_common

try:
    from Xlib import X, display, protocol
except ImportError:
    pass

try:
    signal.signal(signal.SIGCHLD, signal.SIG_IGN)
except Exception:
    pass

SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080
DOCK_H = 64
GAP = 14
WINDOW_H = DOCK_H + GAP             # 78
SHOWN_Y = SCREEN_HEIGHT - WINDOW_H  # 1002
HIDDEN_Y = SCREEN_HEIGHT + 15       # 1095 (completely offscreen below screen bottom)
LAUNCHER_CONFIG_FILE = pixel_common.config_path("pixel-launcher-apps.json")

# WhatsApp Multi profile identifiers.
WHATSAPP_WORK_SCRIPT     = "launch-work.sh"
WHATSAPP_ADMIN_SCRIPT    = "launch-admintech.sh"
WHATSAPP_PERSONAL_SCRIPT = "launch-personal.sh"
WHATSAPP_MATCH_KEYS      = ["whatsapp", "whatsapp-work", "whatsapp-admintech", "whatsapp-personal"]


def hex_to_rgb(hex_str):
    hex_str = hex_str.lstrip('#')
    if len(hex_str) == 6:
        return tuple(int(hex_str[i:i+2], 16) / 255.0 for i in (0, 2, 4))
    return (0.5, 0.5, 0.5)


class PixelDock(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        self.set_title("PixelDock")
        self.set_role("pixel-dock")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_accept_focus(False)
        self.set_focus_on_map(False)
        self.set_keep_above(True)
        self.stick()
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_app_paintable(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)

        self.icon_theme = Gtk.IconTheme.get_default()
        self.icon_cache = {}

        # Pre-index desktop files for dynamic running apps
        self.desktop_index = {}
        self._index_desktop_files()

        # State Variables
        self.is_dark_mode = self.check_dark_mode()
        self.launcher_apps = []
        self.unpinned_apps = {}
        self.all_dock_items = []
        self.load_launcher_apps()

        # Geometry
        self.current_y = SHOWN_Y
        self.target_y = SHOWN_Y
        self.anim_timer = None
        self.hide_timer = None
        self._recalculate_geometry()

        self.mouse_inside = False
        self.hover_candidate = None  # "drawer", "recent", "search", or index 0..N
        self.hover_title = ""

        # Drag and Drop Reordering State
        self.drag_index = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_current_x = 0
        self.is_dragging = False

        # Window-Dodge Obscuration Detection
        self.is_obscured = False
        self.x_display = None
        self.atom_net_active = None
        self.atom_net_state = None
        self.atom_fullscreen = None
        self.atom_max_vert = None
        self.atom_max_horz = None
        self.atom_client_list = None
        self.atom_wm_class = None
        self.atom_close_window = None

        self._init_xlib()
        self._init_menu_css()

        self.set_size_request(SCREEN_WIDTH, WINDOW_H)
        self.set_default_size(SCREEN_WIDTH, WINDOW_H)
        self.move(0, self.current_y)

        self.add_events(
            Gdk.EventMask.ENTER_NOTIFY_MASK |
            Gdk.EventMask.LEAVE_NOTIFY_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK |
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.BUTTON_RELEASE_MASK
        )

        self.connect("draw", self.on_draw)
        self.connect("enter-notify-event", self.on_enter)
        self.connect("leave-notify-event", self.on_leave)
        self.connect("motion-notify-event", self.on_motion)
        self.connect("button-press-event", self.on_button_press)
        self.connect("button-release-event", self.on_button_release)
        self.connect("realize", self.on_realize)

        # Polling timers
        GLib.timeout_add(300, self._periodic_check)
        GLib.timeout_add(40, self._global_pointer_check)

    def on_realize(self, widget):
        self._update_input_shape()
        self.set_keep_above(True)

    def _init_xlib(self):
        try:
            self.x_display = display.Display()
            self.atom_net_active = self.x_display.intern_atom('_NET_ACTIVE_WINDOW')
            self.atom_net_state = self.x_display.intern_atom('_NET_WM_STATE')
            self.atom_fullscreen = self.x_display.intern_atom('_NET_WM_STATE_FULLSCREEN')
            self.atom_max_vert = self.x_display.intern_atom('_NET_WM_STATE_MAXIMIZED_VERT')
            self.atom_max_horz = self.x_display.intern_atom('_NET_WM_STATE_MAXIMIZED_HORZ')
            self.atom_client_list = self.x_display.intern_atom('_NET_CLIENT_LIST')
            self.atom_wm_class = self.x_display.intern_atom('WM_CLASS')
            self.atom_close_window = self.x_display.intern_atom('_NET_CLOSE_WINDOW')
        except Exception as e:
            print(f"[PixelDock] Xlib init warning: {e}")

    def _init_menu_css(self):
        css = """
        menu {
            background-color: #FFFFFF;
            border-radius: 16px;
            border: 1px solid rgba(0, 0, 0, 0.12);
            padding: 8px 6px;
            box-shadow: 0 12px 36px rgba(0, 0, 0, 0.22);
        }
        menuitem {
            border-radius: 10px;
            padding: 7px 14px;
            color: #111827;
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 12.5px;
            font-weight: 500;
        }
        menuitem:hover {
            background-color: rgba(224, 135, 106, 0.18);
            color: #8F4C38;
        }
        separator {
            background-color: rgba(0, 0, 0, 0.08);
            margin: 5px 8px;
        }
        """
        if self.is_dark_mode:
            css = """
            menu {
                background-color: #1E1A18;
                border-radius: 16px;
                border: 1px solid rgba(255, 255, 255, 0.14);
                padding: 8px 6px;
                box-shadow: 0 12px 36px rgba(0, 0, 0, 0.50);
            }
            menuitem {
                border-radius: 10px;
                padding: 7px 14px;
                color: #EDE0DC;
                font-family: 'Google Sans', 'Roboto', sans-serif;
                font-size: 12.5px;
                font-weight: 500;
            }
            menuitem:hover {
                background-color: rgba(224, 135, 106, 0.22);
                color: #E0876A;
            }
            separator {
                background-color: rgba(255, 255, 255, 0.10);
                margin: 5px 8px;
            }
            """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode('utf-8'))
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION + 30
        )

    def _index_desktop_files(self):
        index = {}
        dirs = [os.path.expanduser('~/.local/share/applications/*.desktop'), '/usr/share/applications/*.desktop']
        for p in dirs:
            for f in glob.glob(p):
                try:
                    info = Gio.DesktopAppInfo.new_from_filename(f)
                    if info:
                        base = os.path.basename(f)
                        name = info.get_display_name()
                        icon = info.get_string('Icon') or ''
                        cmd = info.get_commandline() or ''
                        wm = (info.get_startup_wm_class() or '').lower()
                        exec_bin = cmd.split()[0].split('/')[-1].lower() if cmd else ''

                        entry = {
                            'file': f,
                            'name': name,
                            'icon': icon,
                            'cmd': cmd,
                            'desktop_id': base,
                            'info': info
                        }
                        if wm:
                            index[wm] = entry
                        if exec_bin:
                            index[exec_bin] = entry
                        index[base.replace('.desktop', '').lower()] = entry
                except Exception:
                    pass
        self.desktop_index = index

    def check_dark_mode(self):
        try:
            state_file = os.path.expanduser("~/.cache/auto_theme_current.state")
            if os.path.exists(state_file):
                with open(state_file, 'r') as f:
                    c = f.read().strip().lower()
                    if c == "dark":
                        return True
                    elif c == "light":
                        return False
            settings = Gtk.Settings.get_default()
            return bool(settings.get_property("gtk-application-prefer-dark-theme"))
        except Exception:
            return False

    def load_launcher_apps(self):
        self.icon_cache.clear()
        raw = []
        if os.path.exists(LAUNCHER_CONFIG_FILE):
            try:
                with open(LAUNCHER_CONFIG_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            except Exception as e:
                print(f"[PixelDock] Error loading launcher apps: {e}")

        if not raw:
            notes_path = pixel_common.config_path("quick-notes.txt")

            # WhatsApp & YouTube Music: bespoke companion script -> installed
            # desktop entry -> web fallback. Icons: companion asset -> desktop
            # entry icon -> theme icon.
            wh_launch = pixel_common.companion_file("whatsapp", "launch.sh")
            if not wh_launch:
                wh_app = pixel_common.find_desktop_app(["whatsapp"])
                wh_launch = pixel_common.desktop_app_launch_cmd(wh_app)
            wh_icon = (pixel_common.companion_file("whatsapp", "icons/whatsapp.svg")
                       or pixel_common.desktop_app_icon_spec(pixel_common.find_desktop_app(["whatsapp"])))

            ytm_launch = pixel_common.companion_file("youtube_music", "launch.sh")
            if not ytm_launch:
                ytm_app = pixel_common.find_desktop_app(["youtube music", "youtube-music", "youtubemusic"])
                ytm_launch = pixel_common.desktop_app_launch_cmd(ytm_app)
            ytm_icon = (pixel_common.companion_file("youtube_music", "youtube-music.svg")
                        or pixel_common.desktop_app_icon_spec(pixel_common.find_desktop_app(["youtube music", "youtube-music", "youtubemusic"])))

            raw = [
                {"name": "WhatsApp", "icon": wh_icon or "whatsapp", "cmd": wh_launch or "google-chrome https://web.whatsapp.com", "bg": "#E8F5E9"},
                {"name": "Chrome", "icon": "google-chrome", "cmd": "google-chrome", "bg": "#FFFFFF"},
                {"name": "Files", "icon": "system-file-manager", "cmd": f"nemo {home}", "bg": "#E8EAED"},
                {"name": "Settings", "icon": "preferences-system", "cmd": pixel_common.settings_cmd(), "bg": "#E8EAED"},
                {"name": "YouTube Music", "icon": ytm_icon or "multimedia-audio-player", "cmd": ytm_launch or "google-chrome https://music.youtube.com", "bg": "#FFFFFF"},
                {"name": "Telegram", "icon": "org.telegram.desktop", "cmd": "flatpak run org.telegram.desktop", "bg": "#E1F5FE"},
                {"name": "Terminal", "icon": "utilities-terminal", "cmd": "gnome-terminal", "bg": "#ECEFF1"},
                {"name": "Notes", "icon": "accessories-text-editor", "cmd": f"xed {notes_path}", "bg": "#FEF7E0"}
            ]

        # Add pinned flag and running_xids container
        self.launcher_apps = []
        for item in raw:
            item_copy = dict(item)
            item_copy["pinned"] = True
            item_copy["running_xids"] = []
            self.launcher_apps.append(item_copy)

        self._combine_dock_items()

    def _combine_dock_items(self):
        self.all_dock_items = list(self.launcher_apps) + list(self.unpinned_apps.values())
        self._recalculate_geometry()

    def _recalculate_geometry(self):
        self.dock_w = 309 + (len(self.all_dock_items) * 52) + 36
        self.dock_x = (SCREEN_WIDTH - self.dock_w) // 2
        self._update_input_shape()

    def _update_input_shape(self):
        try:
            win = self.get_window()
            if not win:
                return
            region = cairo.Region()
            if self.current_y <= SHOWN_Y + 5:
                # Dock is visible: sensitive only over dock pill
                region.union(cairo.RectangleInt(self.dock_x, 0, self.dock_w, WINDOW_H))
            win.input_shape_combine_region(region, 0, 0)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Global Pointer & Window-Dodge Engine
    # ------------------------------------------------------------------
    def _global_pointer_check(self):
        try:
            display_dev = Gdk.Display.get_default()
            if not display_dev:
                return True
            seat = display_dev.get_default_seat()
            if not seat:
                return True
            pointer = seat.get_pointer()
            if not pointer:
                return True
            _, px, py = pointer.get_position()

            # 1. Edge reveal trigger: mouse hits screen bottom
            if py >= SCREEN_HEIGHT - 2:
                if self.target_y != SHOWN_Y:
                    self.show_dock(animated=True)
            elif self.current_y == SHOWN_Y and self.target_y == SHOWN_Y:
                # 2. If mouse is outside dock boundaries when obscured
                is_over_dock = (self.dock_x <= px <= self.dock_x + self.dock_w and py >= SHOWN_Y)
                if not is_over_dock and self.is_obscured:
                    if not self.hide_timer:
                        self.hide_timer = GLib.timeout_add(220, self._on_hide_timer)
                elif is_over_dock:
                    if self.hide_timer:
                        GLib.source_remove(self.hide_timer)
                        self.hide_timer = None
        except Exception:
            pass
        return True

    def check_obscuration(self):
        if not self.x_display:
            return False
        try:
            root = self.x_display.screen().root

            # Current workspace check
            atom_current_desktop = self.x_display.intern_atom('_NET_CURRENT_DESKTOP')
            curr_desk_prop = root.get_full_property(atom_current_desktop, X.AnyPropertyType)
            curr_desk = curr_desk_prop.value[0] if (curr_desk_prop and curr_desk_prop.value) else 0

            atom_wm_desktop = self.x_display.intern_atom('_NET_WM_DESKTOP')
            atom_client_list = self.x_display.intern_atom('_NET_CLIENT_LIST')
            atom_hidden = self.x_display.intern_atom('_NET_WM_STATE_HIDDEN')

            prop = root.get_full_property(atom_client_list, X.AnyPropertyType)
            if not prop or not prop.value:
                return False

            for xid in prop.value:
                try:
                    win = self.x_display.create_resource_object('window', xid)

                    # 1. Desktop check
                    desk_prop = win.get_full_property(atom_wm_desktop, X.AnyPropertyType)
                    if desk_prop and desk_prop.value:
                        desk = desk_prop.value[0]
                        if desk != 0xFFFFFFFF and desk != curr_desk:
                            continue

                    # 2. Skip minimized windows
                    state_prop = win.get_full_property(self.atom_net_state, X.AnyPropertyType)
                    states = list(state_prop.value) if (state_prop and state_prop.value) else []
                    if atom_hidden in states:
                        continue

                    # 3. Skip dock and desktop widgets
                    cls_prop = win.get_full_property(self.atom_wm_class, X.AnyPropertyType)
                    if cls_prop and cls_prop.value:
                        cls_str = cls_prop.value.decode('utf-8', errors='ignore').lower()
                        if any(k in cls_str for k in ['pixel_dock', 'pixel_desktop', 'desktop-lyrics', 'pixel_app_drawer']):
                            continue

                    # 4. If window is Fullscreen or Maximized -> Obscured!
                    if self.atom_fullscreen in states:
                        return True
                    if self.atom_max_vert in states and self.atom_max_horz in states:
                        return True

                    # 5. Overlap check with dock rectangle
                    coords = root.translate_coords(win, 0, 0)
                    geom = win.get_geometry()
                    win_root_x = coords.x
                    win_root_y = coords.y
                    win_w = geom.width
                    win_h = geom.height

                    if win_root_y + win_h >= SHOWN_Y - 5:
                        if not (win_root_x + win_w < self.dock_x or win_root_x > self.dock_x + self.dock_w):
                            return True
                except Exception:
                    pass

            return False
        except Exception:
            return False

    def update_running_apps(self):
        if not self.x_display or not self.atom_client_list:
            return

        # Clear running XIDs on pinned apps
        for app in self.launcher_apps:
            app["running_xids"] = []

        unpinned_map = {}
        old_unpinned_keys = set(self.unpinned_apps.keys())

        try:
            root = self.x_display.screen().root
            prop = root.get_full_property(self.atom_client_list, X.AnyPropertyType)
            atom_type = self.x_display.intern_atom('_NET_WM_WINDOW_TYPE')
            atom_type_normal = self.x_display.intern_atom('_NET_WM_WINDOW_TYPE_NORMAL')
            atom_type_dialog = self.x_display.intern_atom('_NET_WM_WINDOW_TYPE_DIALOG')
            atom_skip_taskbar = self.x_display.intern_atom('_NET_WM_STATE_SKIP_TASKBAR')

            if prop and prop.value:
                for xid in prop.value:
                    try:
                        win = self.x_display.create_resource_object('window', xid)

                        # Check window type
                        type_prop = win.get_full_property(atom_type, X.AnyPropertyType)
                        if type_prop and type_prop.value:
                            types = list(type_prop.value)
                            if atom_type_normal not in types and atom_type_dialog not in types:
                                continue

                        # Check state (skip taskbar)
                        state_prop = win.get_full_property(self.atom_net_state, X.AnyPropertyType)
                        if state_prop and state_prop.value and atom_skip_taskbar in state_prop.value:
                            continue

                        # Check class
                        cls_prop = win.get_full_property(self.atom_wm_class, X.AnyPropertyType)
                        if not cls_prop or not cls_prop.value:
                            continue
                        parts = [p.lower() for p in cls_prop.value.decode('utf-8', errors='ignore').split('\x00') if p]
                        if not parts:
                            continue

                        # Ignore internal desktop widgets
                        cls_str = " ".join(parts)
                        if any(k in cls_str for k in ["pixel_desktop", "pixel_dock", "pixel_app_drawer", "desktop-lyrics"]):
                            continue

                        # 1. Match against pinned apps
                        matched_pinned = False
                        for p_app in self.launcher_apps:
                            p_name = p_app.get("name", "").lower()
                            p_cmd = p_app.get("cmd", "").lower()
                            p_keys = []
                            if "whatsapp" in p_name or "whatsapp" in p_cmd:
                                p_keys = list(WHATSAPP_MATCH_KEYS)
                            elif "youtube" in p_name or "music" in p_name:
                                p_keys = ["cinhimbnkkaeohfgghhklpknlkffjgod", "crx_cinhimbnkkaeohfgghhklpknlkffjgod", "youtube-music", "youtube music"]
                            elif "chrome" in p_name or "chrome" in p_cmd:
                                if any(p.startswith("crx_") or "cinhimb" in p or "whatsapp" in p for p in parts):
                                    continue
                                p_keys = ["google-chrome", "chrome"]
                            elif "terminal" in p_name or "terminal" in p_cmd:
                                p_keys = ["gnome-terminal-server", "gnome-terminal", "terminal"]
                            elif "files" in p_name or "nemo" in p_cmd:
                                p_keys = ["nemo", "files"]
                            elif "telegram" in p_name:
                                p_keys = ["telegram", "telegramdesktop", "org.telegram.desktop"]
                            elif "settings" in p_name:
                                p_keys = ["gnome-control-center"]
                            elif "notes" in p_name or "xed" in p_cmd:
                                p_keys = ["xed"]
                            else:
                                p_keys = [p_name]
                                if p_cmd:
                                    p_keys.append(p_cmd.split()[0].split('/')[-1])

                            if any(k in cls_str for k in p_keys):
                                p_app["running_xids"].append(xid)
                                matched_pinned = True
                                break

                        if matched_pinned:
                            continue

                        # 2. Window is an unpinned running app: match via desktop index
                        match_info = None
                        for p in parts:
                            if p in self.desktop_index:
                                match_info = self.desktop_index[p]
                                break

                        app_id = parts[0]
                        app_name = match_info['name'] if match_info else parts[-1].capitalize()
                        app_icon = match_info['icon'] if match_info else parts[0]
                        app_cmd = match_info['cmd'] if match_info else parts[0]

                        if app_id not in unpinned_map:
                            unpinned_map[app_id] = {
                                "name": app_name,
                                "icon": app_icon,
                                "cmd": app_cmd,
                                "bg": "#FFFFFF",
                                "pinned": False,
                                "desktop_id": match_info.get("desktop_id") if match_info else None,
                                "running_xids": [xid]
                            }
                        else:
                            unpinned_map[app_id]["running_xids"].append(xid)

                    except Exception:
                        pass
        except Exception as e:
            print(f"[PixelDock] update_running_apps error: {e}")

        # Check if dock items changed
        new_unpinned_keys = set(unpinned_map.keys())
        self.unpinned_apps = unpinned_map

        if new_unpinned_keys != old_unpinned_keys:
            self._combine_dock_items()
            self.queue_draw()
        else:
            self.all_dock_items = list(self.launcher_apps) + list(self.unpinned_apps.values())
            self.queue_draw()

    def _periodic_check(self):
        cur_dark = self.check_dark_mode()
        if cur_dark != self.is_dark_mode:
            self.is_dark_mode = cur_dark
            self._init_menu_css()
            self.queue_draw()

        self.update_running_apps()

        obscured = self.check_obscuration()
        if obscured != self.is_obscured:
            self.is_obscured = obscured
            display_dev = Gdk.Display.get_default()
            seat = display_dev.get_default_seat() if display_dev else None
            pointer = seat.get_pointer() if seat else None
            is_over = False
            if pointer:
                _, px, py = pointer.get_position()
                is_over = (self.dock_x <= px <= self.dock_x + self.dock_w and py >= SHOWN_Y)
            if not is_over:
                if self.is_obscured:
                    self.hide_dock(animated=True)
                else:
                    self.show_dock(animated=True)

        return True

    # ------------------------------------------------------------------
    # Animation & Show/Hide Transitions
    # ------------------------------------------------------------------
    def show_dock(self, animated=True):
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None

        self.target_y = SHOWN_Y
        self.set_keep_above(True)
        if animated:
            self._start_anim()
        else:
            self.current_y = SHOWN_Y
            self.move(0, self.current_y)
            self._update_input_shape()

    def hide_dock(self, animated=True):
        self.target_y = HIDDEN_Y
        if animated:
            self._start_anim()
        else:
            self.current_y = HIDDEN_Y
            self.move(0, self.current_y)
            self._update_input_shape()

    def _start_anim(self):
        if self.anim_timer:
            return
        self.anim_timer = GLib.timeout_add(16, self._anim_step)

    def _anim_step(self):
        diff = self.target_y - self.current_y
        if abs(diff) <= 2:
            self.current_y = self.target_y
            self.move(0, self.current_y)
            self._update_input_shape()
            self.anim_timer = None
            return False

        step = int(diff * 0.40)
        if step == 0:
            step = -2 if diff < 0 else 2
        self.current_y += step
        self.move(0, self.current_y)
        return True

    # ------------------------------------------------------------------
    # Mouse Events
    # ------------------------------------------------------------------
    def on_enter(self, widget, event):
        self.mouse_inside = True
        if self.hide_timer:
            GLib.source_remove(self.hide_timer)
            self.hide_timer = None

        if self.target_y != SHOWN_Y:
            self.show_dock(animated=True)
        return False

    def on_leave(self, widget, event):
        display_dev = Gdk.Display.get_default()
        seat = display_dev.get_default_seat() if display_dev else None
        pointer = seat.get_pointer() if seat else None
        if not pointer:
            return False
        _, px, py = pointer.get_position()

        if self.dock_x <= px <= self.dock_x + self.dock_w and SHOWN_Y <= py <= SCREEN_HEIGHT:
            return False

        self.mouse_inside = False
        self.hover_candidate = None
        self.hover_title = ""
        self.queue_draw()

        if self.is_obscured:
            if self.hide_timer:
                GLib.source_remove(self.hide_timer)
            self.hide_timer = GLib.timeout_add(220, self._on_hide_timer)
        return False

    def _on_hide_timer(self):
        self.hide_timer = None
        display_dev = Gdk.Display.get_default()
        seat = display_dev.get_default_seat() if display_dev else None
        pointer = seat.get_pointer() if seat else None
        if pointer:
            _, px, py = pointer.get_position()
            if self.dock_x <= px <= self.dock_x + self.dock_w and py >= SHOWN_Y:
                return False
        if self.is_obscured:
            self.hide_dock(animated=True)
        return False

    def on_motion(self, widget, event):
        x = event.x
        y = event.y

        # Handle Drag-and-Drop Reordering
        if self.drag_index is not None and (event.state & Gdk.ModifierType.BUTTON1_MASK):
            if not self.is_dragging:
                if abs(x - self.drag_start_x) > 6:
                    self.is_dragging = True
            if self.is_dragging:
                self.drag_current_x = x
                num_pinned = len(self.launcher_apps)
                if num_pinned > 1 and self.drag_index < num_pinned:
                    start_x = self.dock_x + 309
                    target_idx = int((x - start_x + 26) // 52)
                    target_idx = max(0, min(num_pinned - 1, target_idx))
                    if target_idx != self.drag_index:
                        item = self.launcher_apps.pop(self.drag_index)
                        self.launcher_apps.insert(target_idx, item)
                        self.drag_index = target_idx
                        self._combine_dock_items()
                self.queue_draw()
                win = self.get_window()
                if win:
                    win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "grabbing"))
                return True

        old_cand = self.hover_candidate
        self.hover_candidate = None
        self.hover_title = ""

        rx = x - self.dock_x
        if 0 <= y <= DOCK_H and 0 <= rx <= self.dock_w:
            if 12 <= rx <= 52:
                self.hover_candidate = "drawer"
                self.hover_title = "Pixel App Drawer"
            elif 60 <= rx <= 100:
                self.hover_candidate = "recent"
                self.hover_title = "Recent Apps"
            elif 110 <= rx <= 295:
                self.hover_candidate = "search"
                self.hover_title = "Search Google or Gemini"
            elif rx >= 309:
                idx = int((rx - 309) // 52)
                if 0 <= idx < len(self.all_dock_items):
                    offset = (rx - 309) % 52
                    if offset <= 44:
                        self.hover_candidate = idx
                        self.hover_title = self.all_dock_items[idx].get("name", "")

        if self.hover_candidate != old_cand:
            self.queue_draw()

        win = self.get_window()
        if win:
            if self.hover_candidate is not None:
                win.set_cursor(Gdk.Cursor.new_from_name(self.get_display(), "pointer"))
            else:
                win.set_cursor(None)
        return False

    def on_button_press(self, widget, event):
        x = event.x
        y = event.y
        rx = x - self.dock_x

        if 0 <= y <= DOCK_H and 0 <= rx <= self.dock_w:
            # Immediate window state refresh so clicks have 0-latency tracking
            self.update_running_apps()
            if event.button == 1:
                # Left Click
                if 12 <= rx <= 52:
                    self.toggle_app_drawer()
                    return True
                elif 60 <= rx <= 100:
                    self.toggle_recent_apps()
                    return True
                elif 110 <= rx <= 295:
                    self.activate_search()
                    return True
                elif rx >= 309:
                    idx = int((rx - 309) // 52)
                    if 0 <= idx < len(self.all_dock_items):
                        offset = (rx - 309) % 52
                        if offset <= 44:
                            self.drag_index = idx
                            self.drag_start_x = x
                            self.drag_start_y = y
                            self.drag_current_x = x
                            self.is_dragging = False
                    return True

            elif event.button == 3:
                # Right Click Context Menu
                if rx >= 309:
                    idx = int((rx - 309) // 52)
                    if 0 <= idx < len(self.all_dock_items):
                        offset = (rx - 309) % 52
                        if offset <= 44:
                            self.show_context_menu(self.all_dock_items[idx], event)
                    return True
                elif 12 <= rx <= 52:
                    self.toggle_app_drawer()
                    return True

        return False

    def on_button_release(self, widget, event):
        if event.button == 1:
            if self.is_dragging:
                self._save_launcher_apps()
                self.is_dragging = False
                self.drag_index = None
                self.queue_draw()
                win = self.get_window()
                if win:
                    win.set_cursor(None)
                return True
            elif self.drag_index is not None:
                idx = self.drag_index
                self.drag_index = None
                if 0 <= idx < len(self.all_dock_items):
                    self.on_app_left_click(self.all_dock_items[idx])
                return True
        self.is_dragging = False
        self.drag_index = None
        return False

    def _save_launcher_apps(self):
        to_save = []
        for app in self.launcher_apps:
            to_save.append({
                "name": app.get("name", "App"),
                "icon": app.get("icon", ""),
                "cmd": app.get("cmd", ""),
                "bg": app.get("bg", "#FFFFFF"),
                "shape": app.get("shape", "circle")
            })
        try:
            os.makedirs(os.path.dirname(LAUNCHER_CONFIG_FILE), exist_ok=True)
            with open(LAUNCHER_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(to_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[PixelDock] Error saving reordered apps: {e}")

    # ------------------------------------------------------------------
    # App Activation / Unminimize Engine (Single-Click Focus)
    # ------------------------------------------------------------------
    def on_app_left_click(self, app):
        running_xids = app.get("running_xids", [])
        if running_xids:
            # Window is already running: Restore, unminimize and focus!
            self.focus_or_unminimize(running_xids)
        else:
            # Window is not running: Launch new instance!
            self.launch_app(app)

    def focus_or_unminimize(self, running_xids):
        if not self.x_display or not running_xids:
            return
        try:
            root = self.x_display.screen().root
            prop = root.get_full_property(self.atom_net_active, X.AnyPropertyType)
            active_xid = prop.value[0] if (prop and prop.value) else 0

            # Cycle windows if multiple instances exist and current is already active
            target_xid = running_xids[0]
            if len(running_xids) > 1 and active_xid in running_xids:
                idx = running_xids.index(active_xid)
                target_xid = running_xids[(idx + 1) % len(running_xids)]

            win = self.x_display.create_resource_object('window', target_xid)
            atom_hidden = self.x_display.intern_atom('_NET_WM_STATE_HIDDEN')
            state_prop = win.get_full_property(self.atom_net_state, X.AnyPropertyType)
            is_hidden = False
            if state_prop and state_prop.value:
                is_hidden = (atom_hidden in state_prop.value)

            # 1. If single window, it is active in foreground AND not hidden: MINIMIZE IT!
            if len(running_xids) == 1 and active_xid == target_xid and not is_hidden:
                atom_change_state = self.x_display.intern_atom('WM_CHANGE_STATE')
                ev = protocol.event.ClientMessage(
                    window=win,
                    client_type=atom_change_state,
                    data=(32, [3, 0, 0, 0, 0])  # IconicState = 3
                )
                root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
                self.x_display.sync()
                return

            # 2. Window is minimized or inactive: Unminimize, raise and focus!
            ev_state = protocol.event.ClientMessage(
                window=win,
                client_type=self.atom_net_state,
                data=(32, [0, atom_hidden, 0, 1, 0])  # 0 = REMOVE
            )
            root.send_event(ev_state, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)

            # 3. Map & raise above
            win.map()
            win.configure(stack_mode=X.Above)

            # 4. Send _NET_ACTIVE_WINDOW
            ev_active = protocol.event.ClientMessage(
                window=win,
                client_type=self.atom_net_active,
                data=(32, [2, int(time.time() * 1000) & 0xFFFFFFFF, 0, 0, 0])
            )
            root.send_event(ev_active, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)

            # 5. Set direct X11 input focus
            try:
                self.x_display.set_input_focus(win, X.RevertToParent, X.CurrentTime)
            except Exception:
                pass
            self.x_display.sync()
        except Exception as e:
            # 6. Fallback if direct X11 message failed
            try:
                subprocess.run(["wmctrl", "-i", "-a", hex(target_xid)], capture_output=True)
            except Exception:
                pass

    def launch_app(self, app):
        cmd = app.get("cmd", "")
        name = app.get("name", "")

        if "whatsapp" in name.lower() or "whatsapp" in cmd.lower():
            wh_launch = pixel_common.companion_file("whatsapp", "launch.sh")
            if not wh_launch:
                wh_cmd = pixel_common.desktop_app_launch_cmd(
                    pixel_common.find_desktop_app(["whatsapp"]))
                if wh_cmd:
                    try:
                        subprocess.Popen(shlex.split(wh_cmd), start_new_session=True)
                    except Exception as e:
                        print(f"[PixelDock] WhatsApp launch error: {e}")
                    return
            elif wh_launch:
                try:
                    subprocess.Popen([wh_launch], start_new_session=True)
                except Exception as e:
                    print(f"[PixelDock] WhatsApp launch error: {e}")
                return
            elif cmd:
                try:
                    subprocess.Popen(shlex.split(cmd), start_new_session=True)
                except Exception:
                    pass
                return

        if not cmd:
            return

        try:
            subprocess.Popen(shlex.split(cmd), start_new_session=True)
        except Exception as e:
            print(f"[PixelDock] Launch error ({cmd}): {e}")

    def _send_mpris(self, method):
        # 1. Try D-Bus MPRIS
        try:
            import dbus
            bus = dbus.SessionBus()
            for name in bus.list_names():
                if name.startswith("org.mpris.MediaPlayer2."):
                    try:
                        obj = bus.get_object(name, '/org/mpris/MediaPlayer2')
                        player = dbus.Interface(obj, 'org.mpris.MediaPlayer2.Player')
                        getattr(player, method)()
                        return True
                    except Exception:
                        pass
        except Exception:
            pass

        # 2. Fallback to hardware multimedia key simulation (standard XF86 keycodes)
        key_codes = {
            "PlayPause": 172,  # XF86AudioPlay
            "Next": 171,       # XF86AudioNext
            "Previous": 173,   # XF86AudioPrev
            "Stop": 174        # XF86AudioStop
        }
        kc = key_codes.get(method)
        if kc and self.x_display:
            try:
                from Xlib.ext import xtest
                xtest.fake_input(self.x_display, X.KeyPress, kc)
                xtest.fake_input(self.x_display, X.KeyRelease, kc)
                self.x_display.sync()
                return True
            except Exception:
                pass
        return False

    # ------------------------------------------------------------------
    # Material 3 Right-Click Context Menu & "Keep in Dock"
    # ------------------------------------------------------------------
    def show_context_menu(self, app, event):
        menu = Gtk.Menu()
        name = app.get("name", "")
        cmd = app.get("cmd", "")
        is_pinned = app.get("pinned", False)
        running_xids = app.get("running_xids", [])

        # 1. Custom Actions / Profiles
        wh_work = pixel_common.companion_file("whatsapp", WHATSAPP_WORK_SCRIPT)
        if ("whatsapp" in name.lower() or "whatsapp" in cmd.lower()) and wh_work:
            # WhatsApp 3-Profile Menu
            item_k = Gtk.MenuItem(label="🟢  WhatsApp - Work")
            item_k.connect("activate", lambda w: subprocess.Popen([wh_work], start_new_session=True))
            menu.append(item_k)

            wh_admin = pixel_common.companion_file("whatsapp", WHATSAPP_ADMIN_SCRIPT)
            item_a = Gtk.MenuItem(label="🟠  WhatsApp - AdminTech")
            item_a.connect("activate", lambda w: subprocess.Popen([wh_admin], start_new_session=True))
            menu.append(item_a)

            wh_personal = pixel_common.companion_file("whatsapp", WHATSAPP_PERSONAL_SCRIPT)
            item_p = Gtk.MenuItem(label="🟣  WhatsApp - Personal")
            item_p.connect("activate", lambda w: subprocess.Popen([wh_personal], start_new_session=True))
            menu.append(item_p)

            item_all = Gtk.MenuItem(label="🚀  Open All 3 Profiles at Once")
            item_all.connect("activate", lambda w: subprocess.Popen([os.path.join(wh_base, "launch-all.sh")], start_new_session=True))
            menu.append(item_all)

        elif "youtube" in name.lower() or "music" in name.lower():
            item_play = Gtk.MenuItem(label="⏯️  Play / Pause")
            item_play.connect("activate", lambda w: self._send_mpris("PlayPause"))
            menu.append(item_play)

            item_next = Gtk.MenuItem(label="⏭️  Next Song")
            item_next.connect("activate", lambda w: self._send_mpris("Next"))
            menu.append(item_next)

            item_prev = Gtk.MenuItem(label="⏮️  Previous Song")
            item_prev.connect("activate", lambda w: self._send_mpris("Previous"))
            menu.append(item_prev)

            if not running_xids:
                item_open = Gtk.MenuItem(label="🔴  Open YouTube Music")
                item_open.connect("activate", lambda w, a=app: self.launch_app(a))
                menu.append(item_open)

        elif "chrome" in name.lower() or "chrome" in cmd.lower():
            item_nw = Gtk.MenuItem(label="🌐  New Window")
            item_nw.connect("activate", lambda w: subprocess.Popen(["google-chrome", "--new-window"], start_new_session=True))
            menu.append(item_nw)

            item_incog = Gtk.MenuItem(label="🕶️  New Incognito Window")
            item_incog.connect("activate", lambda w: subprocess.Popen(["google-chrome", "--incognito"], start_new_session=True))
            menu.append(item_incog)

        elif "nemo" in cmd.lower() or "files" in name.lower():
            item_nw = Gtk.MenuItem(label="📁  New File Window")
            item_nw.connect("activate", lambda w: subprocess.Popen(["nemo"], start_new_session=True))
            menu.append(item_nw)

            item_home = Gtk.MenuItem(label="🏠  Home Folder")
            item_home.connect("activate", lambda w: subprocess.Popen(["nemo", os.path.expanduser("~")], start_new_session=True))
            menu.append(item_home)

            item_dl = Gtk.MenuItem(label="📥  Downloads Folder")
            item_dl.connect("activate", lambda w: subprocess.Popen(["nemo", os.path.expanduser("~/Downloads")], start_new_session=True))
            menu.append(item_dl)

        elif "terminal" in name.lower() or "terminal" in cmd.lower():
            item_t = Gtk.MenuItem(label="💻  Open New Terminal")
            item_t.connect("activate", lambda w: subprocess.Popen(["gnome-terminal"], start_new_session=True))
            menu.append(item_t)

        elif "settings" in name.lower():
            item_s = Gtk.MenuItem(label="⚙️  System Settings")
            item_s.connect("activate", lambda w: pixel_common.open_settings())
            menu.append(item_s)

        elif "telegram" in name.lower():
            item_t = Gtk.MenuItem(label="✈️  Open Telegram")
            item_t.connect("activate", lambda w, a=app: self.launch_app(a))
            menu.append(item_t)

        elif "notes" in name.lower() or "xed" in cmd.lower():
            item_n = Gtk.MenuItem(label="📝  Open Quick Notes")
            item_n.connect("activate", lambda w: subprocess.Popen(["xed", pixel_common.config_path("quick-notes.txt")], start_new_session=True))
            menu.append(item_n)

        else:
            # Check desktop actions from .desktop file
            desktop_id = app.get("desktop_id")
            if not desktop_id:
                for key in [name.lower(), cmd.split()[0].split('/')[-1].lower() if cmd else '']:
                    if key in self.desktop_index:
                        desktop_id = self.desktop_index[key].get('desktop_id')
                        break
            if desktop_id:
                try:
                    d_info = Gio.DesktopAppInfo.new(desktop_id)
                    if d_info and d_info.list_actions():
                        for act in d_info.list_actions():
                            act_name = d_info.get_action_name(act) or act
                            act_item = Gtk.MenuItem(label=f"▶  {act_name}")
                            act_item.connect("activate", lambda w, a=act, info=d_info: info.launch_action(a, None))
                            menu.append(act_item)
                except Exception:
                    pass

        # Separator
        if len(menu.get_children()) > 0:
            menu.append(Gtk.SeparatorMenuItem())

        # 2. Pin / Unpin Action ("Keep in Dock")
        if is_pinned:
            item_pin = Gtk.MenuItem(label="📌  Remove from Dock")
            item_pin.connect("activate", lambda w, a=app: self.unpin_app(a))
            menu.append(item_pin)
        else:
            item_pin = Gtk.MenuItem(label="📌  Keep in Dock")
            item_pin.connect("activate", lambda w, a=app: self.pin_app(a))
            menu.append(item_pin)

        # 3. Close Window Action (if running)
        if running_xids:
            item_close = Gtk.MenuItem(label="✕  Close Window")
            item_close.connect("activate", lambda w, xids=running_xids: self.close_app_windows(xids))
            menu.append(item_close)

        menu.show_all()
        try:
            menu.popup_at_pointer(event)
        except Exception:
            menu.popup(None, None, None, None, event.button, event.time)

    def pin_app(self, app):
        apps = []
        if os.path.exists(LAUNCHER_CONFIG_FILE):
            try:
                with open(LAUNCHER_CONFIG_FILE, "r", encoding="utf-8") as f:
                    apps = json.load(f)
            except Exception:
                pass

        exists = any(a.get("name", "").lower() == app.get("name", "").lower() for a in apps)
        if not exists:
            new_entry = {
                "name": app.get("name", "App"),
                "icon": app.get("icon", "application-x-executable"),
                "cmd": app.get("cmd", ""),
                "bg": app.get("bg", "#FFFFFF"),
                "shape": "circle"
            }
            apps.append(new_entry)
            try:
                os.makedirs(os.path.dirname(LAUNCHER_CONFIG_FILE), exist_ok=True)
                with open(LAUNCHER_CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(apps, f, indent=2, ensure_ascii=False)
            except Exception as e:
                print(f"[PixelDock] Error saving pinned apps: {e}")

        self.load_launcher_apps()
        self.update_running_apps()

    def unpin_app(self, app):
        apps = []
        if os.path.exists(LAUNCHER_CONFIG_FILE):
            try:
                with open(LAUNCHER_CONFIG_FILE, "r", encoding="utf-8") as f:
                    apps = json.load(f)
            except Exception:
                pass

        apps = [a for a in apps if a.get("name", "").lower() != app.get("name", "").lower() and a.get("cmd", "").lower() != app.get("cmd", "").lower()]
        try:
            os.makedirs(os.path.dirname(LAUNCHER_CONFIG_FILE), exist_ok=True)
            with open(LAUNCHER_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(apps, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[PixelDock] Error saving pinned apps: {e}")

        self.load_launcher_apps()
        self.update_running_apps()

    def close_app_windows(self, running_xids):
        if not self.x_display:
            return
        root = self.x_display.screen().root
        for xid in running_xids:
            try:
                win = self.x_display.create_resource_object('window', xid)
                ev = protocol.event.ClientMessage(
                    window=win,
                    client_type=self.atom_close_window,
                    data=(32, [int(time.time() * 1000) & 0xFFFFFFFF, 2, 0, 0, 0])
                )
                root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
                self.x_display.sync()
            except Exception:
                pass
            subprocess.run(["wmctrl", "-i", "-c", hex(xid)], capture_output=True)

    # ------------------------------------------------------------------
    # Actions & App Launching
    # ------------------------------------------------------------------
    def toggle_app_drawer(self):
        try:
            import socket
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect("/tmp/pixel_app_drawer.sock")
            s.sendall(b"toggle\n")
            s.close()
        except Exception:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            subprocess.Popen([sys.executable, os.path.join(script_dir, "pixel_app_drawer.py"), "toggle"], start_new_session=True)

    def toggle_recent_apps(self):
        try:
            import socket
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect("/tmp/pixel_recent_apps.sock")
            s.sendall(b"toggle\n")
            s.close()
        except Exception:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            subprocess.Popen([sys.executable, os.path.join(script_dir, "pixel_recent_apps.py"), "toggle"], start_new_session=True)

    def activate_search(self):
        try:
            import socket
            s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            s.settimeout(0.3)
            s.connect("/tmp/pixel_app_drawer.sock")
            s.sendall(b"search\n")
            s.close()
        except Exception:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            subprocess.Popen([sys.executable, os.path.join(script_dir, "pixel_app_drawer.py"), "search"], start_new_session=True)

    # ------------------------------------------------------------------
    # Cairo Drawing Engine
    # ------------------------------------------------------------------
    def on_draw(self, widget, cr):
        cr.save()
        cr.set_operator(cairo.Operator.CLEAR)
        cr.paint()
        cr.restore()

        x = self.dock_x
        y = 0
        w = self.dock_w
        h = DOCK_H

        # Theme Colors
        if self.is_dark_mode:
            bg_rgba = (0.12, 0.11, 0.13, 0.96)
            border_rgba = (1.0, 1.0, 1.0, 0.12)
            btn_bg_rgba = (1.0, 1.0, 1.0, 0.08)
            btn_hover_rgba = (0.88, 0.53, 0.42, 0.22)
            pill_bg_rgba = (1.0, 1.0, 1.0, 0.06)
            pill_border_rgba = (1.0, 1.0, 1.0, 0.10)
            text_color = (0.93, 0.88, 0.86)
            dot_color = (0.88, 0.53, 0.42)
        else:
            bg_rgba = (1.0, 1.0, 1.0, 0.96)
            border_rgba = (0.0, 0.0, 0.0, 0.09)
            btn_bg_rgba = (0.0, 0.0, 0.0, 0.05)
            btn_hover_rgba = (0.56, 0.30, 0.22, 0.14)
            pill_bg_rgba = (0.0, 0.0, 0.0, 0.04)
            pill_border_rgba = (0.0, 0.0, 0.0, 0.08)
            text_color = (0.14, 0.10, 0.09)
            dot_color = (0.56, 0.30, 0.22)

        # 1. Dock Container Shadow
        cr.save()
        for i in range(1, 4):
            cr.set_source_rgba(0, 0, 0, 0.04 * (4 - i))
            self._rounded_rect(cr, x - i, y - i + 2, w + (i * 2), h + (i * 2), 30)
            cr.fill()
        cr.restore()

        # 2. Dock Container Background Pill
        cr.save()
        self._rounded_rect(cr, x, y, w, h, 30)
        cr.set_source_rgba(*bg_rgba)
        cr.fill_preserve()
        cr.set_source_rgba(*border_rgba)
        cr.set_line_width(1.2)
        cr.stroke()
        cr.restore()

        # 3. Drawer Button (⸬)
        is_hover_drawer = (self.hover_candidate == "drawer")
        cr.save()
        self._rounded_rect(cr, x + 12, y + 12, 40, 40, 20)
        if is_hover_drawer:
            cr.set_source_rgba(*btn_hover_rgba)
            cr.fill_preserve()
            cr.set_source_rgba(*dot_color)
            cr.set_line_width(1.5)
            cr.stroke()
        else:
            cr.set_source_rgba(*btn_bg_rgba)
            cr.fill()

        # Draw ⸬ icon dots
        cr.set_source_rgb(*text_color)
        cx, cy = x + 32, y + 32
        dot_r = 2.4
        offset = 5.5
        for dx, dy in [(0, -offset), (0, offset), (-offset, 0), (offset, 0), (0, 0)]:
            cr.new_sub_path()
            cr.arc(cx + dx, cy + dy, dot_r, 0, 2 * math.pi)
            cr.fill()
        cr.restore()

        # 4. Recent Apps Button (▢)
        is_hover_recent = (self.hover_candidate == "recent")
        cr.save()
        self._rounded_rect(cr, x + 60, y + 12, 40, 40, 20)
        if is_hover_recent:
            cr.set_source_rgba(*btn_hover_rgba)
            cr.fill_preserve()
            cr.set_source_rgba(*dot_color)
            cr.set_line_width(1.5)
            cr.stroke()
        else:
            cr.set_source_rgba(*btn_bg_rgba)
            cr.fill()

        # Draw square icon
        cr.set_source_rgb(*text_color)
        self._rounded_rect(cr, x + 73, y + 25, 14, 14, 3)
        cr.set_line_width(1.8)
        cr.stroke()
        cr.restore()

        # 5. Google Search Pill
        is_hover_search = (self.hover_candidate == "search")
        cr.save()
        pill_x = x + 110
        pill_y = y + 12
        pill_w = 185
        pill_h = 40
        self._rounded_rect(cr, pill_x, pill_y, pill_w, pill_h, 20)
        if is_hover_search:
            cr.set_source_rgba(*btn_hover_rgba)
            cr.fill_preserve()
            cr.set_source_rgba(*dot_color)
            cr.set_line_width(1.4)
            cr.stroke()
        else:
            cr.set_source_rgba(*pill_bg_rgba)
            cr.fill_preserve()
            cr.set_source_rgba(*pill_border_rgba)
            cr.set_line_width(1.0)
            cr.stroke()

        # Google "G" Logo
        layout_g = PangoCairo.create_layout(cr)
        layout_g.set_markup('<span foreground="#4285F4" font_family="Google Sans" font_weight="bold" font_size="13pt">G</span>')
        cr.move_to(pill_x + 14, pill_y + 8)
        PangoCairo.show_layout(cr, layout_g)

        # Search placeholder text
        layout_txt = PangoCairo.create_layout(cr)
        txt_col = "#EDE0DC" if self.is_dark_mode else "#53433F"
        layout_txt.set_markup(f'<span foreground="{txt_col}" font_family="Google Sans" font_size="9.5pt">Search...</span>')
        cr.move_to(pill_x + 36, pill_y + 11)
        PangoCairo.show_layout(cr, layout_txt)

        # Mic Icon
        layout_mic = PangoCairo.create_layout(cr)
        layout_mic.set_markup('<span font_size="11pt">🎙️</span>')
        cr.move_to(pill_x + pill_w - 28, pill_y + 10)
        PangoCairo.show_layout(cr, layout_mic)
        cr.restore()
        cr.new_path()

        # 6. Pinned & Running Application Badges
        start_x = x + 309
        for idx, app in enumerate(self.all_dock_items):
            ax = start_x + (idx * 52)
            ay = y + 7
            is_hover = (self.hover_candidate == idx)
            is_being_dragged = (self.is_dragging and idx == self.drag_index)
            draw_ay = ay - 3 if is_being_dragged else ay

            # Badge Circle
            cr.save()
            cr.new_sub_path()
            bg_col = app.get("bg", "#FFFFFF")
            rgb = hex_to_rgb(bg_col)
            cr.arc(ax + 22, draw_ay + 21, 21, 0, 2 * math.pi)
            cr.set_source_rgb(*rgb)
            cr.fill_preserve()

            if is_being_dragged:
                cr.set_source_rgba(*dot_color)
                cr.set_line_width(2.6)
                cr.stroke()
            elif is_hover:
                cr.set_source_rgba(*dot_color)
                cr.set_line_width(2.0)
                cr.stroke()
            else:
                cr.set_source_rgba(0, 0, 0, 0.08)
                cr.set_line_width(1.0)
                cr.stroke()
            cr.restore()

            # App Icon
            icon_name = app.get("icon", "")
            pixbuf = self._get_cached_icon(icon_name, 28)
            if pixbuf:
                cr.save()
                Gdk.cairo_set_source_pixbuf(cr, pixbuf, ax + 8, draw_ay + 7)
                cr.paint()
                cr.restore()

            # Running Dot Indicator
            if app.get("running_xids"):
                cr.save()
                cr.new_sub_path()
                cr.set_source_rgb(*dot_color)
                cr.arc(ax + 22, ay + 47, 2.2, 0, 2 * math.pi)
                cr.fill()
                cr.restore()

        # 7. Hover Tooltip
        if self.hover_title and self.hover_candidate is not None:
            self._draw_tooltip(cr, x, y, w, h)

        return False

    def _draw_tooltip(self, cr, dock_x, dock_y, dock_w, dock_h):
        cr.save()
        layout = PangoCairo.create_layout(cr)
        layout.set_text(self.hover_title, -1)
        desc = Pango.FontDescription("Google Sans Medium 9")
        layout.set_font_description(desc)
        ink, logical = layout.get_pixel_extents()

        tt_w = logical.width + 18
        tt_h = 26

        if self.hover_candidate == "drawer":
            anchor_x = dock_x + 32
        elif self.hover_candidate == "recent":
            anchor_x = dock_x + 80
        elif self.hover_candidate == "search":
            anchor_x = dock_x + 202
        elif isinstance(self.hover_candidate, int):
            anchor_x = dock_x + 309 + (self.hover_candidate * 52) + 22
        else:
            anchor_x = dock_x + (dock_w // 2)

        tt_x = anchor_x - (tt_w // 2)
        tt_y = dock_y - 34

        # Background
        self._rounded_rect(cr, tt_x, tt_y, tt_w, tt_h, 8)
        if self.is_dark_mode:
            cr.set_source_rgba(0.18, 0.16, 0.20, 0.95)
        else:
            cr.set_source_rgba(0.15, 0.15, 0.17, 0.92)
        cr.fill_preserve()
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.15)
        cr.set_line_width(1.0)
        cr.stroke()

        # Text
        cr.set_source_rgb(1.0, 1.0, 1.0)
        cr.move_to(tt_x + 9, tt_y + 4)
        PangoCairo.show_layout(cr, layout)
        cr.restore()

    def _get_cached_icon(self, icon_name, size):
        if not icon_name:
            return None
        cache_key = f"{icon_name}_{size}"
        if cache_key in self.icon_cache:
            return self.icon_cache[cache_key]

        pixbuf = None
        if os.path.exists(icon_name):
            try:
                pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_scale(icon_name, size, size, True)
            except Exception:
                pass
        else:
            try:
                theme = Gtk.IconTheme.get_default()
                pixbuf = theme.load_icon(icon_name, size, Gtk.IconLookupFlags.FORCE_SIZE)
            except Exception:
                pass

        if not pixbuf:
            try:
                theme = Gtk.IconTheme.get_default()
                pixbuf = theme.load_icon("application-x-executable", size, Gtk.IconLookupFlags.FORCE_SIZE)
            except Exception:
                pass

        self.icon_cache[cache_key] = pixbuf
        return pixbuf

    def _rounded_rect(self, cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi/2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi/2)
        cr.arc(x + r, y + h - r, r, math.pi/2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3*math.pi/2)
        cr.close_path()


def main():
    global SCREEN_WIDTH, SCREEN_HEIGHT, SHOWN_Y, HIDDEN_Y

    # Use the real screen size instead of the 1920x1080 fallback
    screen = Gdk.Screen.get_default()
    if screen:
        SCREEN_WIDTH = screen.get_width()
        SCREEN_HEIGHT = screen.get_height()
        SHOWN_Y = SCREEN_HEIGHT - WINDOW_H
        HIDDEN_Y = SCREEN_HEIGHT + 15

    dock = PixelDock()
    dock.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
