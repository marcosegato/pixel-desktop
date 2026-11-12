#!/usr/bin/env python3
"""
Google Pixel UI / Material Design 3 (Android 15 / 16 / 17) App Drawer
Fast, native GTK+3 application drawer with pure Material You surface, instant real-time search,
zero-artifact transparent corners, passive Super key listener, and socket-based instant toggle.
"""

import os
import sys
import socket
import threading
import subprocess
import cairo
import json
import time

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Gio', '2.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango

SOCKET_PATH = "/tmp/pixel_app_drawer.sock"
DRAWER_WIDTH = 792
DRAWER_HEIGHT = 540
USAGE_FILE = os.path.expanduser("~/.config/pixel-app-usage.json")

def record_app_usage(app_id):
    if not app_id:
        return
    try:
        data = {}
        if os.path.exists(USAGE_FILE):
            with open(USAGE_FILE, "r") as f:
                data = json.load(f)
        key = str(app_id).strip()
        entry = data.get(key, {"count": 0, "last_used": 0})
        entry["count"] = entry.get("count", 0) + 1
        entry["last_used"] = int(time.time())
        data[key] = entry
        with open(USAGE_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[Usage] Error recording usage: {e}")

def get_top_used_app_ids(limit=6):
    try:
        if os.path.exists(USAGE_FILE):
            with open(USAGE_FILE, "r") as f:
                data = json.load(f)
            now = time.time()
            scored = []
            for k, v in data.items():
                count = v.get("count", 0)
                last_used = v.get("last_used", 0)
                # Recency bonus: last 24h +10, last 7 days +4
                recency = 10.0 if (now - last_used < 86400) else (4.0 if (now - last_used < 604800) else 0.0)
                score = count * 2.0 + recency
                scored.append((score, k))
            scored.sort(key=lambda x: x[0], reverse=True)
            return [k for _, k in scored[:limit]]
    except Exception:
        pass
    return []

class PixelAppDrawer(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("Pixel App Drawer")
        self.set_role("app-drawer")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_default_size(DRAWER_WIDTH, DRAWER_HEIGHT)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_app_paintable(True)

        # Transparency support
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)

        self._can_close_on_unfocus = False
        self.all_items = []
        self.first_visible_app = None

        self.selected_tile = None
        self.nav_area = "search"
        self.nav_suggested_idx = 0
        self.nav_flowbox_idx = 0

        self._load_css()
        self._build_ui()
        self._load_apps()

        self.connect("draw", self._on_draw)
        self.connect("realize", lambda w: self._position_window())
        self.connect("key-press-event", self._on_key_press)
        self.connect("focus-out-event", self._on_focus_out)

        self._start_super_key_listener()

    def _is_dark_mode(self):
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
            return True

    def _on_draw(self, widget, cr):
        # Clear root window to 100% transparent to eliminate rectangular corner artifacts
        cr.set_source_rgba(0, 0, 0, 0)
        cr.set_operator(cairo.Operator.CLEAR)
        cr.paint()
        cr.set_operator(cairo.Operator.OVER)
        return False

    def _load_css(self):
        is_dark = self._is_dark_mode()
        bg_color = "rgba(30, 26, 24, 0.96)" if is_dark else "rgba(255, 248, 246, 0.97)"
        card_bg = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.04)"
        text_primary = "#EDE0DC" if is_dark else "#231917"
        text_secondary = "#D0C3BE" if is_dark else "#53433F"
        border_color = "rgba(255, 255, 255, 0.10)" if is_dark else "rgba(0, 0, 0, 0.08)"
        accent_peach = "#E0876A" if is_dark else "#8F4C38"
        hover_bg = "rgba(224, 135, 106, 0.18)" if is_dark else "rgba(143, 76, 56, 0.12)"
        hover_border = "rgba(224, 135, 106, 0.35)" if is_dark else "rgba(143, 76, 56, 0.25)"

        css = f"""
        * {{
            outline: none;
            outline-style: none;
            outline-width: 0;
            -gtk-outline-radius: 0;
            box-shadow: none;
        }}
        window {{
            background: transparent;
            background-color: transparent;
            border: none;
            box-shadow: none;
        }}
        .drawer-card {{
            background-color: {bg_color};
            border-radius: 28px;
            border: 1.5px solid {border_color};
            box-shadow: none;
        }}
        .search-container {{
            background-color: {card_bg};
            border-radius: 24px;
            border: 1px solid {border_color};
            padding: 4px 16px;
            margin: 16px 20px 10px 20px;
        }}
        .search-container:focus-within {{
            border: 1.5px solid {accent_peach};
        }}
        .search-icon {{
            color: {accent_peach};
            font-size: 16px;
            margin-right: 8px;
        }}
        .search-entry {{
            background: transparent;
            border: none;
            color: {text_primary};
            font-family: 'Google Sans', 'Product Sans', 'Roboto', sans-serif;
            font-size: 14px;
            font-weight: 500;
            padding: 8px 4px;
        }}
        .search-entry:focus {{
            outline: none;
            border: none;
            box-shadow: none;
        }}
        .power-btn {{
            background: transparent;
            border: none;
            color: {accent_peach};
            font-size: 15px;
            padding: 2px 8px;
            border-radius: 999px;
            transition: all 120ms ease;
        }}
        .power-btn:hover {{
            background-color: {hover_bg};
        }}
        .section-header {{
            color: {accent_peach};
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 11px;
            font-weight: 700;
            letter-spacing: 1.5px;
            margin: 10px 24px 6px 24px;
        }}
        .suggested-box {{
            margin: 4px 20px 12px 20px;
        }}
        .app-item {{
            background: transparent;
            border-radius: 18px;
            border: 1px solid transparent;
            padding: 8px 6px;
            transition: all 120ms ease-out;
        }}
        .app-item:hover, .app-item:focus {{
            background-color: {hover_bg};
            border: 1px solid {hover_border};
        }}
        .app-item.keyboard-selected {{
            background-color: {hover_bg};
            border: 1px solid {accent_peach};
        }}
        .app-label {{
            color: {text_primary};
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 11px;
            font-weight: 500;
            margin-top: 4px;
        }}
        .drawer-card scrolledwindow,
        .drawer-card scrolledwindow viewport,
        .drawer-card scrolledwindow viewport.frame,
        .drawer-card flowbox,
        .drawer-card flowboxchild,
        .drawer-card eventbox {{
            border: none;
            background: transparent;
            background-color: transparent;
            box-shadow: none;
            outline: none;
            outline-style: none;
            outline-width: 0;
        }}
        .drawer-card undershoot,
        .drawer-card undershoot.top,
        .drawer-card undershoot.bottom,
        .drawer-card undershoot.left,
        .drawer-card undershoot.right,
        .drawer-card overshoot,
        .drawer-card overshoot.top,
        .drawer-card overshoot.bottom,
        .drawer-card overshoot.left,
        .drawer-card overshoot.right {{
            background-image: none;
            background: none;
            border: none;
            box-shadow: none;
        }}
        scrollbar {{
            opacity: 0.3;
        }}
        scrollbar:hover {{
            opacity: 0.8;
        }}
        scrollbar slider:hover {{
            background-color: {accent_peach};
        }}
        """
        if not hasattr(self, "_css_provider"):
            self._css_provider = Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_screen(
                Gdk.Screen.get_default(),
                self._css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_USER + 10
            )
        self._css_provider.load_from_data(css.encode('utf-8'))

    def _build_ui(self):
        self.root_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.root_card.get_style_context().add_class("drawer-card")
        self.add(self.root_card)

        # 1. Search Bar Container (Material 3 Pill)
        self.search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search_box.get_style_context().add_class("search-container")

        search_icon = Gtk.Label(label="🔍")
        search_icon.get_style_context().add_class("search-icon")
        self.search_box.pack_start(search_icon, False, False, 0)

        self.search_entry = Gtk.Entry()
        self.search_entry.get_style_context().add_class("search-entry")
        self.search_entry.set_placeholder_text("Telusuri aplikasi, setelan, atau berkas...")
        self.search_entry.set_hexpand(True)
        self.search_entry.connect("changed", self._on_search_changed)
        self.search_entry.connect("activate", self._on_search_activate)
        self.search_entry.connect("key-press-event", self._on_search_key_press)
        self.search_box.pack_start(self.search_entry, True, True, 0)

        self.clear_btn = Gtk.Button(label="✕")
        self.clear_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.clear_btn.connect("clicked", lambda b: self.search_entry.set_text(""))
        self.clear_btn.set_no_show_all(True)
        self.clear_btn.hide()
        self.search_box.pack_end(self.clear_btn, False, False, 0)

        # Power / Session Button (Shutdown, Restart, Suspend)
        power_btn = Gtk.Button(label="⏻")
        power_btn.set_relief(Gtk.ReliefStyle.NONE)
        power_btn.get_style_context().add_class("power-btn")
        power_btn.set_tooltip_text("Menu Daya (Matikan / Mulai Ulang / Kunci)")
        power_btn.connect("clicked", lambda b: self._on_power_clicked())
        self.search_box.pack_end(power_btn, False, False, 2)

        self.root_card.pack_start(self.search_box, False, False, 0)

        # 2. Suggested Apps Section ("Disarankan")
        self.suggested_header = Gtk.Label(label="SERING DIGUNAKAN")
        self.suggested_header.set_halign(Gtk.Align.START)
        self.suggested_header.get_style_context().add_class("section-header")
        self.root_card.pack_start(self.suggested_header, False, False, 0)

        self.suggested_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.suggested_box.set_halign(Gtk.Align.CENTER)
        self.suggested_box.set_can_focus(False)
        self.suggested_box.get_style_context().add_class("suggested-box")
        self.root_card.pack_start(self.suggested_box, False, False, 0)

        # 3. All Apps Section ("Semua Aplikasi")
        self.all_apps_header = Gtk.Label(label="SEMUA APLIKASI")
        self.all_apps_header.set_halign(Gtk.Align.START)
        self.all_apps_header.get_style_context().add_class("section-header")
        self.root_card.pack_start(self.all_apps_header, False, False, 0)

        self.scrolled = Gtk.ScrolledWindow()
        self.scrolled.set_can_focus(False)
        self.scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.scrolled.set_vexpand(True)
        self.scrolled.set_hexpand(True)
        self.scrolled.set_margin_start(16)
        self.scrolled.set_margin_end(16)
        self.scrolled.set_margin_bottom(20)

        self.flowbox = Gtk.FlowBox()
        self.flowbox.set_valign(Gtk.Align.START)
        self.flowbox.set_halign(Gtk.Align.CENTER)
        self.flowbox.set_max_children_per_line(6)
        self.flowbox.set_min_children_per_line(6)
        self.flowbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.flowbox.set_homogeneous(True)
        self.flowbox.set_row_spacing(8)
        self.flowbox.set_column_spacing(10)
        self.flowbox.set_filter_func(self._filter_apps)
        self.flowbox.set_can_focus(False)

        flow_pad_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        flow_pad_box.set_halign(Gtk.Align.CENTER)
        flow_pad_box.set_margin_start(0)
        flow_pad_box.set_margin_end(0)
        flow_pad_box.set_margin_bottom(12)
        flow_pad_box.pack_start(self.flowbox, True, True, 0)

        self.scrolled.add(flow_pad_box)
        self.root_card.pack_start(self.scrolled, True, True, 0)

    def _create_app_tile(self, name, icon, app_info, width=108):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        box.set_size_request(width, 72)
        box.get_style_context().add_class("app-item")

        img = None
        # Explicit Google Chrome icon fix
        if "chrome" in name.lower() or (app_info and "chrome" in (app_info.get_id() or "").lower()):
            icon = Gio.ThemedIcon.new("google-chrome")

        if icon:
            try:
                img = Gtk.Image.new_from_gicon(icon, Gtk.IconSize.LARGE_TOOLBAR)
                img.set_pixel_size(38)
            except Exception:
                pass
        if not img:
            img = Gtk.Image.new_from_icon_name("application-x-executable", Gtk.IconSize.LARGE_TOOLBAR)
            img.set_pixel_size(38)

        img.set_halign(Gtk.Align.CENTER)
        box.pack_start(img, False, False, 2)

        lbl = Gtk.Label(label=name)
        lbl.get_style_context().add_class("app-label")
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_max_width_chars(11)
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_halign(Gtk.Align.CENTER)
        box.pack_start(lbl, False, False, 0)

        event_box = Gtk.EventBox()
        event_box.set_visible_window(False)
        event_box.set_can_focus(False)
        event_box.add(box)
        event_box.app_box = box
        event_box.app_info = app_info
        event_box.connect("button-press-event", lambda w, e: self._launch_app(app_info))
        return event_box

    def _load_apps(self):
        apps = Gio.AppInfo.get_all()
        seen = set()
        valid = []

        for app in apps:
            if not app.should_show():
                continue
            name = app.get_display_name()
            if not name or name in seen:
                continue
            seen.add(name)

            icon = app.get_icon()
            if "chrome" in name.lower() or "chrome" in (app.get_id() or "").lower():
                icon = Gio.ThemedIcon.new("google-chrome")

            valid.append({
                "name": name,
                "icon": icon,
                "app_info": app,
                "exec": (app.get_executable() or "").lower()
            })

        valid.sort(key=lambda x: x["name"].lower())
        self.all_items = valid

        # 1. Populate Suggested Apps dynamically
        self._populate_suggested_apps()

        # 2. Populate All Apps FlowBox
        for item in valid:
            tile = self._create_app_tile(item["name"], item["icon"], item["app_info"], width=108)
            tile.item_data = item
            self.flowbox.add(tile)

        self.show_all()
        self.hide()

    def _populate_suggested_apps(self):
        # Clear existing suggested tiles
        for child in self.suggested_box.get_children():
            self.suggested_box.remove(child)

        top_ids = get_top_used_app_ids(limit=6)
        suggested_found = []

        # Match against recorded usage history
        for tid in top_ids:
            for item in self.all_items:
                app = item["app_info"]
                aid = (app.get_id() or "").lower()
                exec_cmd = item["exec"]
                name = item["name"].lower()
                tid_clean = tid.lower().replace(".desktop", "")
                if (tid.lower() == aid or tid_clean in aid or tid_clean in exec_cmd or tid_clean in name) and item not in suggested_found:
                    suggested_found.append(item)
                    break
            if len(suggested_found) >= 6:
                break

        # Fallback to smart defaults if fewer than 6 apps tracked
        if len(suggested_found) < 6:
            default_keys = ["whatsmulti", "whatsapp", "chrome", "google-chrome", "nemo", "files", "youtube", "music", "drive", "terminal", "telegram"]
            for dk in default_keys:
                for item in self.all_items:
                    if (dk in item["name"].lower() or dk in item["exec"]) and item not in suggested_found:
                        suggested_found.append(item)
                        break
                if len(suggested_found) >= 6:
                    break

        for item in suggested_found:
            tile = self._create_app_tile(item["name"], item["icon"], item["app_info"], width=108)
            tile.item_data = item
            self.suggested_box.pack_start(tile, False, False, 0)

        self.suggested_box.show_all()

    def _filter_apps(self, child):
        query = self.search_entry.get_text().strip().lower()
        if not query:
            return True
        tile = child.get_child()
        data = getattr(tile, "item_data", None) or getattr(child, "item_data", None)
        if not data:
            return True
        name = data.get("name", "").lower()
        exec_cmd = data.get("exec", "").lower()
        match = query in name or query in exec_cmd
        if match and self.first_visible_app is None:
            self.first_visible_app = data["app_info"]
        return match

    def _on_search_changed(self, entry):
        self._clear_keyboard_selection()
        self.first_visible_app = None
        query = entry.get_text().strip()
        if query:
            if hasattr(self, "clear_btn"):
                self.clear_btn.show()
            self.suggested_header.hide()
            self.suggested_box.hide()
        else:
            if hasattr(self, "clear_btn"):
                self.clear_btn.hide()
            self.suggested_header.show()
            self.suggested_box.show()
        self.flowbox.invalidate_filter()

    def _on_search_activate(self, entry):
        if self.first_visible_app:
            self._launch_app(self.first_visible_app)
        else:
            cmd = entry.get_text().strip()
            if cmd:
                try:
                    subprocess.Popen(cmd, shell=True)
                except Exception as e:
                    print(f"[Drawer] Exec error: {e}")
                self.hide_drawer()

    def _on_power_clicked(self):
        self.hide_drawer()
        subprocess.Popen(["cinnamon-session-quit", "--power-off"])

    def _launch_app(self, app_info):
        self.hide_drawer()
        try:
            context = Gdk.Display.get_default().get_app_launch_context()
            app_info.launch([], context)
        except Exception as e:
            cmd = app_info.get_commandline()
            print(f"[Drawer] Standard launch failed ({e}), falling back to cmd: {cmd}")
            if cmd:
                subprocess.Popen(cmd.split()[0])

    def _position_window(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()

        dock_y = 995
        try:
            pos_file = os.path.expanduser("~/.config/pixel-widgets-pos.json")
            if os.path.exists(pos_file):
                with open(pos_file, "r") as f:
                    pos_data = json.load(f)
                    if "dock" in pos_data and pos_data["dock"][1] is not None:
                        dock_y = pos_data["dock"][1]
        except Exception:
            pass

        min_s, nat_s = self.get_preferred_size()
        actual_w = max(DRAWER_WIDTH, nat_s.width)
        actual_h = max(DRAWER_HEIGHT, nat_s.height)

        gap = 16
        x = geom.x + (geom.width - actual_w) // 2
        y = geom.y + dock_y - actual_h - gap
        self.move(x, y)
        gdk_win = self.get_window()
        if gdk_win:
            gdk_win.move(x, y)

    def show_drawer(self, focus_search=True):
        self._clear_keyboard_selection()
        self._load_css()
        self._populate_suggested_apps()
        self.show_all()
        if hasattr(self, "clear_btn") and not self.search_entry.get_text().strip():
            self.clear_btn.hide()
        self._position_window()
        self.set_keep_above(True)
        self.present()
        self.search_entry.set_text("")
        if focus_search:
            self.search_entry.grab_focus()
        self.last_shown_time = time.time()
        self._can_close_on_unfocus = False
        GLib.timeout_add(800, self._enable_unfocus_close)

    def hide_drawer(self):
        self.hide()
        self._can_close_on_unfocus = False

    def toggle_drawer(self):
        now = time.time()
        # Debounce rapid double-trigger calls (< 400ms)
        if (now - getattr(self, "last_toggle_time", 0)) < 0.40:
            return
        self.last_toggle_time = now

        if self.is_visible():
            self.hide_drawer()
        else:
            self.show_drawer()

    def _enable_unfocus_close(self):
        self._can_close_on_unfocus = True
        return False

    def _on_focus_out(self, widget, event):
        if (time.time() - getattr(self, "last_shown_time", 0)) < 0.8:
            return False
        if self._can_close_on_unfocus and self.is_visible():
            self.hide_drawer()
        return False

    def _clear_keyboard_selection(self):
        if hasattr(self, "selected_tile") and self.selected_tile:
            if hasattr(self.selected_tile, "app_box"):
                self.selected_tile.app_box.get_style_context().remove_class("keyboard-selected")
            self.selected_tile = None
        self.nav_area = "search"

    def _set_keyboard_selection(self, tile, area, idx):
        if not tile:
            return
        self._clear_keyboard_selection()
        self.selected_tile = tile
        self.nav_area = area
        if area == "suggested":
            self.nav_suggested_idx = idx
        elif area == "flowbox":
            self.nav_flowbox_idx = idx
            GLib.idle_add(self._ensure_tile_visible, tile)
        if hasattr(tile, "app_box"):
            tile.app_box.get_style_context().add_class("keyboard-selected")

    def _ensure_tile_visible(self, tile):
        try:
            parent = tile.get_parent()
            if not parent:
                return
            alloc = parent.get_allocation()
            adj = self.scrolled.get_vadjustment()
            if alloc.y < adj.get_value():
                adj.set_value(max(0, alloc.y - 10))
            elif alloc.y + alloc.height > adj.get_value() + adj.get_page_size():
                adj.set_value(alloc.y + alloc.height - adj.get_page_size() + 10)
        except Exception:
            pass

    def _get_suggested_tiles(self):
        return [c for c in self.suggested_box.get_children() if c.is_visible()]

    def _get_visible_flowbox_tiles(self):
        tiles = []
        for child in self.flowbox.get_children():
            if child.get_child_visible():
                tile = child.get_child()
                if tile:
                    tiles.append(tile)
        return tiles

    def _on_search_key_press(self, entry, event):
        val = event.keyval
        if val == Gdk.KEY_Down:
            sug_tiles = self._get_suggested_tiles()
            if self.suggested_box.is_visible() and sug_tiles:
                idx = min(self.nav_suggested_idx, len(sug_tiles) - 1)
                self._set_keyboard_selection(sug_tiles[idx], "suggested", idx)
            else:
                flow_tiles = self._get_visible_flowbox_tiles()
                if flow_tiles:
                    self._set_keyboard_selection(flow_tiles[0], "flowbox", 0)
            return True
        elif val == Gdk.KEY_Escape:
            self.hide_drawer()
            return True
        return False

    def _on_key_press(self, widget, event):
        val = event.keyval

        if val == Gdk.KEY_Escape:
            self.hide_drawer()
            return True

        if val == Gdk.KEY_Down:
            if self.nav_area == "search":
                sug_tiles = self._get_suggested_tiles()
                if self.suggested_box.is_visible() and sug_tiles:
                    idx = min(self.nav_suggested_idx, len(sug_tiles) - 1)
                    self._set_keyboard_selection(sug_tiles[idx], "suggested", idx)
                else:
                    flow_tiles = self._get_visible_flowbox_tiles()
                    if flow_tiles:
                        self._set_keyboard_selection(flow_tiles[0], "flowbox", 0)
                return True
            elif self.nav_area == "suggested":
                flow_tiles = self._get_visible_flowbox_tiles()
                if flow_tiles:
                    idx = min(self.nav_suggested_idx, len(flow_tiles) - 1)
                    self._set_keyboard_selection(flow_tiles[idx], "flowbox", idx)
                return True
            elif self.nav_area == "flowbox":
                flow_tiles = self._get_visible_flowbox_tiles()
                new_idx = self.nav_flowbox_idx + 6
                if new_idx < len(flow_tiles):
                    self._set_keyboard_selection(flow_tiles[new_idx], "flowbox", new_idx)
                return True

        elif val == Gdk.KEY_Up:
            if self.nav_area == "flowbox":
                if self.nav_flowbox_idx >= 6:
                    flow_tiles = self._get_visible_flowbox_tiles()
                    self._set_keyboard_selection(flow_tiles[self.nav_flowbox_idx - 6], "flowbox", self.nav_flowbox_idx - 6)
                    return True
                else:
                    sug_tiles = self._get_suggested_tiles()
                    if self.suggested_box.is_visible() and sug_tiles:
                        col = self.nav_flowbox_idx % 6
                        idx = min(col, len(sug_tiles) - 1)
                        self._set_keyboard_selection(sug_tiles[idx], "suggested", idx)
                    else:
                        self._clear_keyboard_selection()
                        self.search_entry.grab_focus()
                    return True
            elif self.nav_area == "suggested":
                self._clear_keyboard_selection()
                self.search_entry.grab_focus()
                return True

        elif val == Gdk.KEY_Left:
            if self.nav_area == "suggested":
                if self.nav_suggested_idx > 0:
                    sug_tiles = self._get_suggested_tiles()
                    self._set_keyboard_selection(sug_tiles[self.nav_suggested_idx - 1], "suggested", self.nav_suggested_idx - 1)
                    return True
            elif self.nav_area == "flowbox":
                if self.nav_flowbox_idx > 0:
                    flow_tiles = self._get_visible_flowbox_tiles()
                    self._set_keyboard_selection(flow_tiles[self.nav_flowbox_idx - 1], "flowbox", self.nav_flowbox_idx - 1)
                    return True

        elif val == Gdk.KEY_Right:
            if self.nav_area == "suggested":
                sug_tiles = self._get_suggested_tiles()
                if self.nav_suggested_idx < len(sug_tiles) - 1:
                    self._set_keyboard_selection(sug_tiles[self.nav_suggested_idx + 1], "suggested", self.nav_suggested_idx + 1)
                    return True
            elif self.nav_area == "flowbox":
                flow_tiles = self._get_visible_flowbox_tiles()
                if self.nav_flowbox_idx < len(flow_tiles) - 1:
                    self._set_keyboard_selection(flow_tiles[self.nav_flowbox_idx + 1], "flowbox", self.nav_flowbox_idx + 1)
                    return True

        elif val in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            if self.selected_tile:
                app_info = getattr(self.selected_tile, "app_info", None)
                if app_info:
                    self._launch_app(app_info)
                    return True

        elif self.selected_tile and not (event.state & (Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.MOD1_MASK)):
            if val == Gdk.KEY_BackSpace or (32 <= val <= 126):
                self._clear_keyboard_selection()
                self.search_entry.grab_focus()
                return False

        return False

    def _start_super_key_listener(self):
        def listener():
            try:
                from Xlib import X, display
                from Xlib.ext import record
                from Xlib.protocol import rq
                
                rec_d = display.Display()
                super_pressed = False
                super_combo = False

                def callback(reply):
                    nonlocal super_pressed, super_combo
                    if reply.category != record.FromServer:
                        return
                    if reply.client_swapped:
                        return
                    data = reply.data
                    while len(data):
                        event, data = rq.EventField(None).parse_binary_value(data, rec_d.display, None, None)
                        if event.type == X.KeyPress:
                            if event.detail == 133:  # Super_L
                                super_pressed = True
                                super_combo = False
                            elif super_pressed:
                                super_combo = True
                        elif event.type == X.KeyRelease:
                            if event.detail == 133:
                                if super_pressed and not super_combo:
                                    GLib.idle_add(self.toggle_drawer)
                                super_pressed = False
                                super_combo = False

                ctx = rec_d.record_create_context(
                    0,
                    [record.AllClients],
                    [{
                        'core_requests': (0, 0),
                        'core_replies': (0, 0),
                        'ext_requests': (0, 0, 0, 0),
                        'ext_replies': (0, 0, 0, 0),
                        'delivered_events': (0, 0),
                        'device_events': (X.KeyPress, X.KeyRelease),
                        'errors': (0, 0),
                        'client_started': False,
                        'client_died': False,
                    }]
                )
                rec_d.record_enable_context(ctx, callback)
            except Exception as e:
                print(f"[Drawer] Super key passive listener warning: {e}")

        t = threading.Thread(target=listener, daemon=True)
        t.start()


def start_ipc_server(drawer):
    if os.path.exists(SOCKET_PATH):
        try:
            os.remove(SOCKET_PATH)
        except OSError:
            pass

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(SOCKET_PATH)
    server.listen(5)

    def loop():
        while True:
            try:
                conn, _ = server.accept()
                data = conn.recv(1024).decode('utf-8').strip()
                if data == "toggle":
                    GLib.idle_add(drawer.toggle_drawer)
                elif data == "show":
                    GLib.idle_add(drawer.show_drawer)
                elif data == "hide":
                    GLib.idle_add(drawer.hide_drawer)
                elif data == "search":
                    GLib.idle_add(drawer.show_drawer, True)
                elif data == "nav_down":
                    def do_nav():
                        sug_tiles = drawer._get_suggested_tiles()
                        if drawer.suggested_box.is_visible() and sug_tiles:
                            drawer._set_keyboard_selection(sug_tiles[0], "suggested", 0)
                        else:
                            flow_tiles = drawer._get_visible_flowbox_tiles()
                            if flow_tiles:
                                drawer._set_keyboard_selection(flow_tiles[0], "flowbox", 0)
                    GLib.idle_add(do_nav)
                conn.sendall(b"OK\n")
                conn.close()
            except Exception:
                pass

    t = threading.Thread(target=loop, daemon=True)
    t.start()


def send_ipc_command(cmd):
    if not os.path.exists(SOCKET_PATH):
        return False
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(SOCKET_PATH)
        s.sendall(cmd.encode('utf-8'))
        resp = s.recv(1024)
        s.close()
        return True
    except Exception:
        return False


def main():
    cmd = "toggle"
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()

    if send_ipc_command(cmd):
        sys.exit(0)

    app = PixelAppDrawer()
    start_ipc_server(app)
    if cmd in ("toggle", "show", "search"):
        GLib.idle_add(app.show_drawer, True)
    Gtk.main()


if __name__ == "__main__":
    main()
