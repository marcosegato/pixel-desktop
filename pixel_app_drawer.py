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
import urllib.parse
import math
import shlex

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Gio', '2.0')
from gi.repository import Gtk, Gdk, Gio, GLib, Pango

import pixel_common

SOCKET_PATH = "/tmp/pixel_app_drawer.sock"
DRAWER_WIDTH = 792
DRAWER_HEIGHT = 570
USAGE_FILE = pixel_common.config_path("pixel-app-usage.json")

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
        os.makedirs(os.path.dirname(USAGE_FILE), exist_ok=True)
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
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_modal(True)
        self.stick()
        self.set_app_paintable(True)

        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()
        self.set_default_size(geom.width, geom.height)

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
        self.connect("button-press-event", self._on_button_press)
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
        is_dark = self._is_dark_mode()
        # 1. Clear window
        cr.save()
        cr.set_operator(cairo.Operator.CLEAR)
        cr.paint()
        cr.restore()

        # 2. Paint translucent scrim backdrop over full screen
        cr.save()
        if is_dark:
            cr.set_source_rgba(0, 0, 0, 0.45)
        else:
            cr.set_source_rgba(0, 0, 0, 0.22)
        cr.paint()
        cr.restore()

        # 3. Paint root_card surface 100% OPAQUE (zero wallpaper bleed)
        coords = self.root_card.translate_coordinates(self, 0, 0)
        if coords:
            cx, cy = coords
            alloc = self.root_card.get_allocation()
            cw, ch = alloc.width, alloc.height
            if cw > 50 and ch > 50:
                cr.save()
                cr.set_operator(cairo.Operator.SOURCE)
                if is_dark:
                    cr.set_source_rgb(0.118, 0.102, 0.094) # #1E1A18
                else:
                    cr.set_source_rgb(1.0, 1.0, 1.0) # #FFFFFF

                r = 28
                cr.new_sub_path()
                cr.arc(cx + cw - r, cy + r, r, -math.pi/2, 0)
                cr.arc(cx + cw - r, cy + ch - r, r, 0, math.pi/2)
                cr.arc(cx + r, cy + ch - r, r, math.pi/2, math.pi)
                cr.arc(cx + r, cy + r, r, math.pi, 3*math.pi/2)
                cr.close_path()
                cr.fill()
                cr.restore()

        return False

    def _load_css(self):
        is_dark = self._is_dark_mode()
        bg_color = "#1E1A18" if is_dark else "#FFFFFF"
        card_bg = "rgba(255, 255, 255, 0.08)" if is_dark else "rgba(0, 0, 0, 0.04)"
        text_primary = "#EDE0DC" if is_dark else "#181311"
        text_secondary = "#D0C3BE" if is_dark else "#4B3F3C"
        border_color = "rgba(255, 255, 255, 0.12)" if is_dark else "rgba(0, 0, 0, 0.10)"
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
            box-shadow: 0 16px 48px rgba(0, 0, 0, 0.40);
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
        .action-chips-box {{
            margin: 0px 20px 8px 20px;
        }}
        .action-chip {{
            background-color: {card_bg};
            border-radius: 999px;
            border: 1px solid {border_color};
            padding: 5px 14px;
            transition: all 120ms ease;
        }}
        .action-chip:hover, .action-chip:focus {{
            background-color: {hover_bg};
            border: 1px solid {accent_peach};
        }}
        .action-chip-label {{
            color: {text_primary};
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 12px;
            font-weight: 500;
        }}
        .action-chip-badge {{
            background-color: {accent_peach};
            color: {bg_color};
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 9.5px;
            font-weight: 700;
            border-radius: 999px;
            padding: 1px 7px;
            margin-left: 6px;
        }}
        .no-apps-card {{
            background-color: {card_bg};
            border-radius: 24px;
            border: 1px solid {border_color};
            padding: 24px;
            margin: 10px 20px 20px 20px;
        }}
        .no-apps-title {{
            color: {text_primary};
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 15px;
            font-weight: 700;
        }}
        .no-apps-desc {{
            color: {text_secondary};
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 12px;
            margin-top: 2px;
            margin-bottom: 18px;
        }}
        .prominent-btn {{
            background-color: {card_bg};
            border-radius: 16px;
            border: 1.5px solid {border_color};
            padding: 12px 18px;
            transition: all 140ms ease;
        }}
        .prominent-btn:hover, .prominent-btn:focus {{
            background-color: {hover_bg};
            border: 1.5px solid {accent_peach};
        }}
        .prominent-title {{
            color: {text_primary};
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 13.5px;
            font-weight: 700;
        }}
        .prominent-desc {{
            color: {text_secondary};
            font-family: 'Google Sans', 'Roboto', sans-serif;
            font-size: 11px;
            margin-top: 2px;
        }}
        .suggested-box {{
            margin: 4px 20px 12px 20px;
        }}
        button.app-item, .app-item {{
            background: transparent;
            background-color: transparent;
            border-radius: 18px;
            border: 1px solid transparent;
            padding: 6px 4px;
            box-shadow: none;
            transition: all 120ms ease-out;
        }}
        button.app-item:hover, button.app-item:focus, .app-item:hover, .app-item:focus {{
            background-color: {hover_bg};
            border: 1px solid {hover_border};
        }}
        button.app-item.keyboard-selected, .app-item.keyboard-selected {{
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
            background-color: {bg_color};
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
        self.backdrop_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.backdrop_box.set_hexpand(True)
        self.backdrop_box.set_vexpand(True)
        self.add(self.backdrop_box)

        self.backdrop_spacer = Gtk.Box()
        self.backdrop_spacer.set_vexpand(True)
        self.backdrop_box.pack_start(self.backdrop_spacer, True, True, 0)

        self.root_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.root_card.get_style_context().add_class("drawer-card")
        self.root_card.set_size_request(DRAWER_WIDTH, DRAWER_HEIGHT)
        self.root_card.set_halign(Gtk.Align.CENTER)
        self.root_card.set_valign(Gtk.Align.END)
        self.backdrop_box.pack_end(self.root_card, False, False, 0)

        # 1. Search Bar Container (Material 3 Pill)
        self.search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.search_box.get_style_context().add_class("search-container")

        search_icon = Gtk.Label()
        search_icon.set_markup('<span foreground="#4285F4" font_family="Google Sans" font_weight="bold" font_size="13pt">G</span>')
        search_icon.get_style_context().add_class("search-icon")
        self.search_box.pack_start(search_icon, False, False, 0)

        self.search_entry = Gtk.Entry()
        self.search_entry.get_style_context().add_class("search-entry")
        self.search_entry.set_placeholder_text("Search apps, Google, or ask Gemini (?)...")
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
        power_btn.set_tooltip_text("Power Menu (Shutdown / Restart / Lock)")
        power_btn.connect("clicked", lambda b: self._on_power_clicked())
        self.search_box.pack_end(power_btn, False, False, 2)

        self.root_card.pack_start(self.search_box, False, False, 0)

        # 1.5 Web & AI Action Chips (Compact row when apps match)
        self.action_chips_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.action_chips_box.get_style_context().add_class("action-chips-box")

        # Google Search Action Chip
        self.google_chip = Gtk.Button()
        self.google_chip.get_style_context().add_class("action-chip")
        self.google_chip.set_relief(Gtk.ReliefStyle.NONE)
        self.google_chip.set_can_focus(True)
        g_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.google_chip_icon = Gtk.Label(label="🌐")
        self.google_chip_label = Gtk.Label(label='Search Google')
        self.google_chip_label.get_style_context().add_class("action-chip-label")
        self.google_chip_badge = Gtk.Label(label="↵ Enter")
        self.google_chip_badge.get_style_context().add_class("action-chip-badge")
        g_box.pack_start(self.google_chip_icon, False, False, 0)
        g_box.pack_start(self.google_chip_label, False, False, 0)
        g_box.pack_start(self.google_chip_badge, False, False, 0)
        self.google_chip.add(g_box)
        self.google_chip.connect("clicked", lambda b: self._launch_google_search(self.search_entry.get_text()))
        self.google_chip.connect("key-press-event", lambda w, e: self._on_chip_key_press(w, e, "google"))
        self.action_chips_box.pack_start(self.google_chip, False, False, 0)

        # Gemini AI Action Chip
        self.gemini_chip = Gtk.Button()
        self.gemini_chip.get_style_context().add_class("action-chip")
        self.gemini_chip.set_relief(Gtk.ReliefStyle.NONE)
        self.gemini_chip.set_can_focus(True)
        gm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.gemini_chip_icon = Gtk.Label(label="✨")
        self.gemini_chip_label = Gtk.Label(label='Ask Gemini')
        self.gemini_chip_label.get_style_context().add_class("action-chip-label")
        self.gemini_chip_badge = Gtk.Label(label="AI")
        self.gemini_chip_badge.get_style_context().add_class("action-chip-badge")
        gm_box.pack_start(self.gemini_chip_icon, False, False, 0)
        gm_box.pack_start(self.gemini_chip_label, False, False, 0)
        gm_box.pack_start(self.gemini_chip_badge, False, False, 0)
        self.gemini_chip.add(gm_box)
        self.gemini_chip.connect("clicked", lambda b: self._launch_gemini(self.search_entry.get_text()))
        self.gemini_chip.connect("key-press-event", lambda w, e: self._on_chip_key_press(w, e, "gemini"))
        self.action_chips_box.pack_start(self.gemini_chip, False, False, 0)

        self.root_card.pack_start(self.action_chips_box, False, False, 0)
        self.action_chips_box.show_all()
        self.action_chips_box.set_no_show_all(True)
        self.action_chips_box.hide()

        # 2. Suggested Apps Section ("Suggested")
        self.suggested_header = Gtk.Label(label="FREQUENTLY USED")
        self.suggested_header.set_halign(Gtk.Align.START)
        self.suggested_header.get_style_context().add_class("section-header")
        self.root_card.pack_start(self.suggested_header, False, False, 0)

        self.suggested_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.suggested_box.set_halign(Gtk.Align.CENTER)
        self.suggested_box.set_can_focus(False)
        self.suggested_box.get_style_context().add_class("suggested-box")
        self.root_card.pack_start(self.suggested_box, False, False, 0)

        # 3. All Apps Section ("All Apps")
        self.all_apps_header = Gtk.Label(label="ALL APPS")
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
        self.flowbox.connect("child-activated", self._on_flowbox_child_activated)

        flow_pad_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        flow_pad_box.set_halign(Gtk.Align.CENTER)
        flow_pad_box.set_margin_start(0)
        flow_pad_box.set_margin_end(0)
        flow_pad_box.set_margin_bottom(12)
        flow_pad_box.pack_start(self.flowbox, True, True, 0)

        self.scrolled.add(flow_pad_box)
        self.root_card.pack_start(self.scrolled, True, True, 0)

        # 4. Universal Search Card (Shown when no local apps match)
        self.no_apps_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.no_apps_card.get_style_context().add_class("no-apps-card")
        self.no_apps_card.set_vexpand(True)

        no_apps_head = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
        self.no_apps_title = Gtk.Label(label="Universal Search (Web & AI)")
        self.no_apps_title.set_halign(Gtk.Align.START)
        self.no_apps_title.get_style_context().add_class("no-apps-title")
        self.no_apps_desc = Gtk.Label(label="No local apps found. Press Enter to search Google or ask Gemini AI directly.")
        self.no_apps_desc.set_halign(Gtk.Align.START)
        self.no_apps_desc.set_line_wrap(True)
        self.no_apps_desc.get_style_context().add_class("no-apps-desc")
        no_apps_head.pack_start(self.no_apps_title, False, False, 0)
        no_apps_head.pack_start(self.no_apps_desc, False, False, 0)
        self.no_apps_card.pack_start(no_apps_head, False, False, 0)

        # Prominent Google Search Button Card
        self.prominent_google_btn = Gtk.Button()
        self.prominent_google_btn.get_style_context().add_class("prominent-btn")
        self.prominent_google_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.prominent_google_btn.set_can_focus(True)
        pg_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        pg_icon = Gtk.Label(label="🌐")
        pg_icon.get_style_context().add_class("action-chip-icon")
        pg_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.prominent_google_title = Gtk.Label(label='Search with Google')
        self.prominent_google_title.set_halign(Gtk.Align.START)
        self.prominent_google_title.get_style_context().add_class("prominent-title")
        pg_desc = Gtk.Label(label='Open full web results with a Google Gemini AI Overview summary')
        pg_desc.set_halign(Gtk.Align.START)
        pg_desc.get_style_context().add_class("prominent-desc")
        pg_text_box.pack_start(self.prominent_google_title, False, False, 0)
        pg_text_box.pack_start(pg_desc, False, False, 0)
        self.prominent_google_badge = Gtk.Label(label="↵ Enter")
        self.prominent_google_badge.get_style_context().add_class("action-chip-badge")
        self.prominent_google_badge.set_valign(Gtk.Align.CENTER)
        pg_box.pack_start(pg_icon, False, False, 0)
        pg_box.pack_start(pg_text_box, True, True, 0)
        pg_box.pack_end(self.prominent_google_badge, False, False, 0)
        self.prominent_google_btn.add(pg_box)
        self.prominent_google_btn.connect("clicked", lambda b: self._launch_google_search(self.search_entry.get_text()))
        self.prominent_google_btn.connect("key-press-event", lambda w, e: self._on_prominent_key_press(w, e, "google"))
        self.no_apps_card.pack_start(self.prominent_google_btn, False, False, 0)

        # Prominent Gemini AI Button Card
        self.prominent_gemini_btn = Gtk.Button()
        self.prominent_gemini_btn.get_style_context().add_class("prominent-btn")
        self.prominent_gemini_btn.set_relief(Gtk.ReliefStyle.NONE)
        self.prominent_gemini_btn.set_can_focus(True)
        pgm_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        pgm_icon = Gtk.Label(label="✨")
        pgm_icon.get_style_context().add_class("action-chip-icon")
        pgm_text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        self.prominent_gemini_title = Gtk.Label(label='Ask Gemini AI')
        self.prominent_gemini_title.set_halign(Gtk.Align.START)
        self.prominent_gemini_title.get_style_context().add_class("prominent-title")
        pgm_desc = Gtk.Label(label='Open Google Gemini in browser (question automatically copied to clipboard)')
        pgm_desc.set_halign(Gtk.Align.START)
        pgm_desc.get_style_context().add_class("prominent-desc")
        pgm_text_box.pack_start(self.prominent_gemini_title, False, False, 0)
        pgm_text_box.pack_start(pgm_desc, False, False, 0)
        self.prominent_gemini_badge = Gtk.Label(label="AI")
        self.prominent_gemini_badge.get_style_context().add_class("action-chip-badge")
        self.prominent_gemini_badge.set_valign(Gtk.Align.CENTER)
        pgm_box.pack_start(pgm_icon, False, False, 0)
        pgm_box.pack_start(pgm_text_box, True, True, 0)
        pgm_box.pack_end(self.prominent_gemini_badge, False, False, 0)
        self.prominent_gemini_btn.add(pgm_box)
        self.prominent_gemini_btn.connect("clicked", lambda b: self._launch_gemini(self.search_entry.get_text()))
        self.prominent_gemini_btn.connect("key-press-event", lambda w, e: self._on_prominent_key_press(w, e, "gemini"))
        self.no_apps_card.pack_start(self.prominent_gemini_btn, False, False, 0)

        self.root_card.pack_start(self.no_apps_card, True, True, 0)
        self.no_apps_card.show_all()
        self.no_apps_card.set_no_show_all(True)
        self.no_apps_card.hide()

    def _create_app_tile(self, name, icon, app_info, width=108):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_size_request(width, 88)
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
        box.pack_start(img, False, False, 1)

        lbl = Gtk.Label(label=name)
        lbl.get_style_context().add_class("app-label")
        lbl.set_line_wrap(True)
        lbl.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        lbl.set_lines(3)
        lbl.set_max_width_chars(16)
        lbl.set_ellipsize(Pango.EllipsizeMode.END)
        lbl.set_justify(Gtk.Justification.CENTER)
        lbl.set_halign(Gtk.Align.CENTER)
        box.pack_start(lbl, False, False, 0)

        btn = Gtk.Button()
        btn.get_style_context().add_class("app-item")
        btn.set_relief(Gtk.ReliefStyle.NONE)
        btn.set_can_focus(True)
        btn.set_tooltip_text(name)
        btn.add(box)
        btn.app_box = box
        btn.app_info = app_info
        btn.connect("clicked", lambda b, info=app_info: self._launch_app(info))
        return btn

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

        self.root_card.show_all()

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
            default_keys = ["whatsapp", "chrome", "google-chrome", "nemo", "files", "youtube", "music", "drive", "terminal", "telegram"]
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
        for prefix in ["?", "gemini:", "gemini ", "ai:", "ai "]:
            if query.startswith(prefix):
                return False
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
        raw_text = entry.get_text()
        query = raw_text.strip()

        if query:
            if hasattr(self, "clear_btn"):
                self.clear_btn.show()

            # Check if user explicitly typed a Gemini prefix
            is_gemini_prefix = False
            for prefix in ["?", "gemini:", "gemini ", "ai:", "ai "]:
                if query.lower().startswith(prefix):
                    is_gemini_prefix = True
                    break

            # Find matching apps synchronously
            matching_apps = []
            if not is_gemini_prefix:
                q_lower = query.lower()
                for item in self.all_items:
                    if q_lower in item["name"].lower() or q_lower in item["exec"]:
                        matching_apps.append(item)

            # Update labels for action chips and prominent cards
            display_query = (query[:32] + "...") if len(query) > 32 else query
            gemini_query = query
            if is_gemini_prefix:
                for prefix in ["?", "gemini:", "gemini ", "ai:", "ai "]:
                    if gemini_query.lower().startswith(prefix):
                        gemini_query = gemini_query[len(prefix):].strip()
                        break
            disp_gemini = (gemini_query[:32] + "...") if len(gemini_query) > 32 else gemini_query

            self.google_chip_label.set_text(f'Search Google: "{display_query}"')
            self.gemini_chip_label.set_text(f'Ask Gemini: "{disp_gemini}"')
            self.prominent_google_title.set_text(f'Search with Google: "{display_query}"')
            self.prominent_gemini_title.set_text(f'Ask Gemini AI: "{disp_gemini}"')

            # Adjust badges depending on whether Gemini prefix was used
            if is_gemini_prefix:
                self.prominent_gemini_badge.set_text("↵ Enter")
                self.prominent_google_badge.set_text("Web")
                self.gemini_chip_badge.set_text("↵ Enter")
                self.google_chip_badge.set_text("Web")
            else:
                self.prominent_google_badge.set_text("↵ Enter")
                self.prominent_gemini_badge.set_text("AI")
                self.google_chip_badge.set_text("↵ Enter")
                self.gemini_chip_badge.set_text("AI")

            self.suggested_header.hide()
            self.suggested_box.hide()

            if matching_apps:
                self.first_visible_app = matching_apps[0]["app_info"]
                self.all_apps_header.show()
                self.all_apps_header.set_text(f"MATCHING APPS ({len(matching_apps)})")
                self.scrolled.show()
                self.no_apps_card.hide()
                self.action_chips_box.show()
            else:
                self.first_visible_app = None
                self.all_apps_header.hide()
                self.scrolled.hide()
                self.action_chips_box.hide()
                self.no_apps_card.show()
        else:
            if hasattr(self, "clear_btn"):
                self.clear_btn.hide()
            self.suggested_header.show()
            self.suggested_box.show()
            self.all_apps_header.show()
            self.all_apps_header.set_text("ALL APPS")
            self.scrolled.show()
            self.action_chips_box.hide()
            self.no_apps_card.hide()

        self.flowbox.invalidate_filter()

    def _on_search_activate(self, entry):
        query = entry.get_text().strip()
        if not query:
            return

        # Scenario C: Explicit Gemini prefix
        for prefix in ["?", "gemini:", "gemini ", "ai:", "ai "]:
            if query.lower().startswith(prefix):
                self._launch_gemini(query)
                return

        # Scenario A: Local app match found -> launch first matching app
        if self.first_visible_app:
            self._launch_app(self.first_visible_app)
            return

        # Scenario B: No local apps found -> Default Enter opens Google Search (Option A)
        self._launch_google_search(query)

    def _launch_google_search(self, query):
        self.hide_drawer()
        clean = query.lstrip("?").strip()
        if not clean:
            return
        url = f"https://www.google.com/search?q={urllib.parse.quote_plus(clean)}"
        try:
            subprocess.Popen(["google-chrome", url])
        except Exception:
            subprocess.Popen(["xdg-open", url])

    def _launch_gemini(self, query):
        self.hide_drawer()
        clean = query
        for prefix in ["?", "gemini:", "gemini ", "ai:", "ai "]:
            if clean.lower().startswith(prefix):
                clean = clean[len(prefix):].strip()
                break
        if not clean:
            clean = query.strip()
        if not clean:
            return

        # 1. Copy prompt to system clipboard for instant pasting
        try:
            clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
            clipboard.set_text(clean, -1)
            clipboard.store()
        except Exception as e:
            print(f"[Drawer] Clipboard error: {e}")

        # 2. Open Google Gemini in Chrome
        gemini_url = "https://gemini.google.com/app"
        try:
            subprocess.Popen(["google-chrome", gemini_url])
        except Exception:
            subprocess.Popen(["xdg-open", gemini_url])

        # 3. Native desktop notification with friendly confirmation
        try:
            preview = (clean[:45] + "...") if len(clean) > 45 else clean
            subprocess.Popen([
                "notify-send",
                "-a", "Google Gemini",
                "-i", "google-chrome",
                "Opening Google Gemini",
                f"Question copied to clipboard:\n\"{preview}\""
            ])
        except Exception:
            pass

    def _on_prominent_key_press(self, widget, event, target):
        val = event.keyval
        if val in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            if target == "google":
                self._launch_google_search(self.search_entry.get_text())
            else:
                self._launch_gemini(self.search_entry.get_text())
            return True
        elif val == Gdk.KEY_Down or val == Gdk.KEY_Tab:
            if target == "google":
                self.prominent_gemini_btn.grab_focus()
                return True
        elif val == Gdk.KEY_Up or (val == Gdk.KEY_Tab and (event.state & Gdk.ModifierType.SHIFT_MASK)):
            if target == "gemini":
                self.prominent_google_btn.grab_focus()
                return True
            elif target == "google":
                self.search_entry.grab_focus()
                return True
        elif val == Gdk.KEY_Escape:
            self.hide_drawer()
            return True
        return False

    def _on_chip_key_press(self, widget, event, target):
        val = event.keyval
        if val in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            if target == "google":
                self._launch_google_search(self.search_entry.get_text())
            else:
                self._launch_gemini(self.search_entry.get_text())
            return True
        elif val == Gdk.KEY_Right:
            if target == "google":
                self.gemini_chip.grab_focus()
                return True
        elif val == Gdk.KEY_Left:
            if target == "gemini":
                self.google_chip.grab_focus()
                return True
        elif val == Gdk.KEY_Up:
            self.search_entry.grab_focus()
            return True
        elif val == Gdk.KEY_Down:
            flow_tiles = self._get_visible_flowbox_tiles()
            if flow_tiles:
                self._set_keyboard_selection(flow_tiles[0], "flowbox", 0)
                return True
        elif val == Gdk.KEY_Escape:
            self.hide_drawer()
            return True
        return False

    def _on_power_clicked(self):
        self.hide_drawer()
        subprocess.Popen(pixel_common.session_quit_cmd())

    def _on_flowbox_child_activated(self, flowbox, child):
        tile = child.get_child()
        app_info = getattr(tile, "app_info", None)
        if not app_info and hasattr(child, "item_data"):
            app_info = child.item_data.get("app_info")
        if app_info:
            self._launch_app(app_info)

    def _launch_app(self, app_info):
        self.hide_drawer()
        try:
            record_app_usage(app_info.get_id())
        except Exception:
            pass
        try:
            context = Gdk.Display.get_default().get_app_launch_context()
            app_info.launch([], context)
        except Exception as e:
            cmd = app_info.get_commandline()
            print(f"[Drawer] Standard launch failed ({e}), falling back to cmd: {cmd}")
            if cmd:
                subprocess.Popen(shlex.split(cmd), start_new_session=True)

    def _position_window(self):
        display = Gdk.Display.get_default()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geom = monitor.get_geometry()

        self.set_default_size(geom.width, geom.height)
        self.resize(geom.width, geom.height)
        self.move(geom.x, geom.y)
        gdk_win = self.get_window()
        if gdk_win:
            gdk_win.move_resize(geom.x, geom.y, geom.width, geom.height)

        # Anchor drawer card 12px directly above the bottom dock (dock top is 1006)
        self.root_card.set_margin_bottom(86)

    def _force_focus_and_raise(self):
        try:
            gdk_win = self.get_window()
            if not gdk_win:
                return False
            xid = gdk_win.get_xid()
            from Xlib import X, display, protocol
            d = display.Display()
            d.set_error_handler(lambda *args: None)
            root = d.screen().root
            win = d.create_resource_object('window', xid)

            win.configure(stack_mode=X.Above)
            atom_net_active = d.intern_atom('_NET_ACTIVE_WINDOW')
            ev = protocol.event.ClientMessage(
                window=win,
                client_type=atom_net_active,
                data=(32, [2, int(time.time() * 1000) & 0xFFFFFFFF, 0, 0, 0])
            )
            root.send_event(ev, event_mask=X.SubstructureRedirectMask | X.SubstructureNotifyMask)
            try:
                d.set_input_focus(win, X.RevertToParent, X.CurrentTime)
            except Exception:
                pass
            d.sync()
        except Exception:
            pass
        return False

    def show_drawer(self, focus_search=True):
        self._clear_keyboard_selection()
        self._load_css()
        self._populate_suggested_apps()
        self.search_entry.set_text("")
        self._position_window()
        self.show_all()
        if hasattr(self, "clear_btn") and not self.search_entry.get_text().strip():
            self.clear_btn.hide()
        self.set_keep_above(True)
        self.present()

        self._force_focus_and_raise()
        GLib.timeout_add(35, self._force_focus_and_raise)

        if focus_search:
            self.search_entry.grab_focus()
        self.last_shown_time = time.time()

    def hide_drawer(self):
        self.hide()

    def toggle_drawer(self):
        now = time.time()
        # Debounce rapid double-trigger calls (< 250ms)
        if (now - getattr(self, "last_toggle_time", 0)) < 0.25:
            return
        self.last_toggle_time = now

        if self.is_visible():
            self.hide_drawer()
        else:
            self.show_drawer()

    def _on_button_press(self, widget, event):
        alloc = self.root_card.get_allocation()
        in_card = (alloc.x <= event.x <= alloc.x + alloc.width and 
                   alloc.y <= event.y <= alloc.y + alloc.height)
        if not in_card:
            self.hide_drawer()
            return True
        return False

    def _on_focus_out(self, widget, event):
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
        if val in (Gdk.KEY_Down, Gdk.KEY_Tab):
            if self.no_apps_card.is_visible():
                self.prominent_google_btn.grab_focus()
                return True
            if self.action_chips_box.is_visible() and not self.suggested_box.is_visible():
                self.google_chip.grab_focus()
                return True
            sug_tiles = self._get_suggested_tiles()
            if self.suggested_box.is_visible() and sug_tiles:
                idx = min(self.nav_suggested_idx, len(sug_tiles) - 1)
                self._set_keyboard_selection(sug_tiles[idx], "suggested", idx)
                return True
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
                elif data.startswith("query:"):
                    q = data[6:]
                    def do_set_query(query_text=q):
                        drawer.show_drawer(True)
                        drawer.search_entry.set_text(query_text)
                        drawer.search_entry.set_position(-1)
                    GLib.idle_add(do_set_query)
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

    if cmd != "daemon" and send_ipc_command(cmd):
        sys.exit(0)

    app = PixelAppDrawer()
    start_ipc_server(app)
    if cmd in ("toggle", "show", "search"):
        GLib.idle_add(app.show_drawer, True)
    Gtk.main()


if __name__ == "__main__":
    main()
