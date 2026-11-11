#!/usr/bin/env python3
"""
Google Pixel Desktop UI / Material Design 3 (MD3) for Linux Mint Cinnamon.
Designed for ThinkPad X1 Carbon Gen 6.
- 0.0% CPU when idle (Event-driven DBus & minute-boundary timers)
- Clean, modular, hyper-efficient GTK3 & Cairo native renderer
- Authentic Google Pixel 'At a Glance', MD3 Clock, Google Search Pill, and Media Widget
"""

import os
import sys
import time
import json
import signal
import datetime
import urllib.request
import subprocess
import threading

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('Rsvg', '2.0')
gi.require_version('Pango', '1.0')
gi.require_version('PangoCairo', '1.0')

from gi.repository import Gtk, Gdk, GLib, Gio, Rsvg, Pango, PangoCairo
import cairo

# Asset paths
ASSETS_DIR = "/home/teddy/Applications/pixel-desktop/assets"
WEATHER_CACHE_PATH = os.path.expanduser("~/.cache/weather-cache.json")
WEATHER_CONFIG_PATH = os.path.expanduser("~/.config/weather-config.json")

# Screen Dimensions
SCREEN_WIDTH = 1920
SCREEN_HEIGHT = 1080

# UI Dimensions & Layout Coordinates
AT_A_GLANCE_X = 80
AT_A_GLANCE_Y = 65
AT_A_GLANCE_W = 420
AT_A_GLANCE_H = 100

CLOCK_W = 380
CLOCK_H = 120
CLOCK_X = int((SCREEN_WIDTH - CLOCK_W) / 2)
CLOCK_Y = 160

SEARCH_W = 580
SEARCH_H = 54
SEARCH_X = int((SCREEN_WIDTH - SEARCH_W) / 2)
SEARCH_Y = CLOCK_Y + CLOCK_H + 28

MEDIA_W = 480
MEDIA_H = 72
MEDIA_X = int((SCREEN_WIDTH - MEDIA_W) / 2)
MEDIA_Y = SEARCH_Y + SEARCH_H + 25

class PixelDesktopWindow(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)

        # Basic Window Configuration
        self.set_title("PixelDesktop")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_below(True)
        self.stick()
        self.set_type_hint(Gdk.WindowTypeHint.DOCK)
        self.set_app_paintable(True)

        # Transparent RGBA Visual
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        self.set_size_request(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.set_default_size(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.move(0, 0)

        # State Variables
        self.current_time_str = datetime.datetime.now().strftime("%H:%M")
        self.current_date_str = datetime.datetime.now().strftime("%A, %b %-d")
        self.battery_pct = 100
        self.battery_state = 5  # UPower full/charging/discharging
        self.cpu_temp = 50
        self.fan_rpm = 0

        # Weather Data
        self.weather_info = {
            "city": "Malang",
            "temp": 25,
            "code": 3,
            "condition": "Partly Cloudy"
        }
        self.load_weather_cache()

        # MPRIS Media Data
        self.media_playing = False
        self.media_title = ""
        self.media_artist = ""
        self.media_player_name = ""

        # Search Bar State
        self.search_active = False

        # Load SVG Icons
        self.icon_g = self.load_svg("google-g.svg")
        self.icon_mic = self.load_svg("google-mic.svg")
        self.icon_lens = self.load_svg("google-lens.svg")

        # Container for interactive widgets
        self.fixed = Gtk.Fixed()
        self.add(self.fixed)

        # Search Entry Widget (initially hidden/unmapped inside the pill)
        self.search_entry = Gtk.Entry()
        self.search_entry.set_size_request(SEARCH_W - 130, SEARCH_H - 14)
        self.search_entry.set_has_frame(False)
        self.search_entry.set_placeholder_text("Search Google or type a command...")
        self.search_entry.connect("activate", self.on_search_submit)
        self.search_entry.connect("key-press-event", self.on_search_key)
        self.search_entry.connect("focus-out-event", self.on_search_focus_out)

        # Custom CSS styling for the entry
        css_provider = Gtk.CssProvider()
        css_provider.load_from_data(b"""
            entry {
                background: transparent;
                color: #ffffff;
                font-family: 'Google Sans', sans-serif;
                font-size: 15px;
                caret-color: #a8c7fa;
                border: none;
                padding-left: 8px;
            }
            entry selection {
                background-color: #a8c7fa;
                color: #041e49;
            }
        """)
        self.search_entry.get_style_context().add_provider(
            css_provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self.fixed.put(self.search_entry, SEARCH_X + 56, SEARCH_Y + 7)

        # Events
        self.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK |
            Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.connect("draw", self.on_draw)
        self.connect("button-press-event", self.on_button_press)
        self.connect("realize", self.on_realize)

        # Setup Event Watchdogs
        self.init_dbus_watchers()
        self.update_hardware_stats()
        self.schedule_next_minute_tick()

        # Weather background refresh thread
        self.fetch_weather_async()
        GLib.timeout_add_seconds(900, self.fetch_weather_async)  # Every 15 min

    def load_svg(self, filename):
        path = os.path.join(ASSETS_DIR, filename)
        if os.path.exists(path):
            try:
                return Rsvg.Handle.new_from_file(path)
            except Exception as e:
                print(f"[PixelDesktop] Error loading SVG {filename}: {e}")
        return None

    def on_realize(self, widget):
        self.update_input_regions()

    def update_input_regions(self):
        """Configure X11 input regions so empty desktop is 100% click-through."""
        window = self.get_window()
        if not window:
            return

        region = cairo.Region()
        # 1. At a Glance rectangle
        region.union(cairo.RectangleInt(AT_A_GLANCE_X, AT_A_GLANCE_Y, AT_A_GLANCE_W, AT_A_GLANCE_H))
        # 2. Clock rectangle
        region.union(cairo.RectangleInt(CLOCK_X, CLOCK_Y, CLOCK_W, CLOCK_H))
        # 3. Search Bar rectangle
        region.union(cairo.RectangleInt(SEARCH_X, SEARCH_Y, SEARCH_W, SEARCH_H))
        # 4. Media Player rectangle (if playing)
        if self.media_playing:
            region.union(cairo.RectangleInt(MEDIA_X, MEDIA_Y, MEDIA_W, MEDIA_H))

        window.input_shape_combine_region(region, 0, 0)

    # -------------------------------------------------------------
    # DBus Watchers (Pure Event-Driven, 0% CPU Idle)
    # -------------------------------------------------------------
    def init_dbus_watchers(self):
        try:
            # UPower Device Watcher
            sys_bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
            sys_bus.signal_subscribe(
                "org.freedesktop.UPower",
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                "/org/freedesktop/UPower/devices/battery_BAT0",
                None,
                Gio.DBusSignalFlags.NONE,
                self.on_upower_changed,
                None
            )
            # Read initial battery state
            upower = Gio.DBusProxy.new_sync(
                sys_bus, Gio.DBusProxyFlags.NONE, None,
                "org.freedesktop.UPower",
                "/org/freedesktop/UPower/devices/battery_BAT0",
                "org.freedesktop.UPower.Device",
                None
            )
            pct = upower.get_cached_property("Percentage")
            if pct:
                self.battery_pct = round(pct.unpack())
            state = upower.get_cached_property("State")
            if state:
                self.battery_state = state.unpack()
        except Exception as e:
            print(f"[PixelDesktop] UPower watcher error: {e}")

        try:
            # MPRIS Media Watcher
            sess_bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            sess_bus.signal_subscribe(
                None,
                "org.freedesktop.DBus.Properties",
                "PropertiesChanged",
                "/org/mpris/MediaPlayer2",
                None,
                Gio.DBusSignalFlags.NONE,
                self.on_mpris_properties_changed,
                None
            )
            sess_bus.signal_subscribe(
                "org.freedesktop.DBus",
                "org.freedesktop.DBus",
                "NameOwnerChanged",
                "/org/freedesktop/DBus",
                None,
                Gio.DBusSignalFlags.NONE,
                self.on_mpris_name_owner_changed,
                None
            )
            self.refresh_mpris_state()
        except Exception as e:
            print(f"[PixelDesktop] MPRIS watcher error: {e}")

    def on_upower_changed(self, connection, sender, path, iface, signal, params, user_data):
        try:
            props = params.unpack()[1]
            if "Percentage" in props:
                self.battery_pct = round(props["Percentage"])
            if "State" in props:
                self.battery_state = props["State"]
            self.queue_draw_area(AT_A_GLANCE_X, AT_A_GLANCE_Y, AT_A_GLANCE_W, AT_A_GLANCE_H)
        except Exception:
            pass

    def on_mpris_properties_changed(self, conn, sender, path, iface, signal, params, user_data):
        GLib.idle_add(self.refresh_mpris_state)

    def on_mpris_name_owner_changed(self, conn, sender, path, iface, signal, params, user_data):
        name = params.unpack()[0]
        if name.startswith("org.mpris.MediaPlayer2"):
            GLib.idle_add(self.refresh_mpris_state)

    def refresh_mpris_state(self):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            proxy = Gio.DBusProxy.new_sync(
                bus, Gio.DBusProxyFlags.NONE, None,
                "org.freedesktop.DBus",
                "/org/freedesktop/DBus",
                "org.freedesktop.DBus",
                None
            )
            names = proxy.call_sync("ListNames", None, Gio.DBusCallFlags.NONE, -1, None).unpack()[0]
            mpris_names = [n for n in names if n.startswith("org.mpris.MediaPlayer2.")]

            found_active = False
            for player_bus_name in mpris_names:
                player = Gio.DBusProxy.new_sync(
                    bus, Gio.DBusProxyFlags.NONE, None,
                    player_bus_name,
                    "/org/mpris/MediaPlayer2",
                    "org.mpris.MediaPlayer2.Player",
                    None
                )
                status_prop = player.get_cached_property("PlaybackStatus")
                status = status_prop.unpack() if status_prop else ""
                if status == "Playing":
                    meta_prop = player.get_cached_property("Metadata")
                    meta = meta_prop.unpack() if meta_prop else {}
                    title = meta.get("xesam:title", "")
                    artist = meta.get("xesam:artist", [""])
                    if isinstance(artist, list) and len(artist) > 0:
                        artist = artist[0]

                    self.media_playing = True
                    self.media_title = str(title) if title else "Now Playing"
                    self.media_artist = str(artist) if artist else "Unknown Artist"
                    self.media_player_name = player_bus_name
                    found_active = True
                    break

            if not found_active and self.media_playing:
                self.media_playing = False
                self.media_title = ""
                self.media_artist = ""
                self.media_player_name = ""

            self.update_input_regions()
            self.queue_draw_area(MEDIA_X - 10, MEDIA_Y - 10, MEDIA_W + 20, MEDIA_H + 20)
        except Exception:
            pass

    # -------------------------------------------------------------
    # Hardware & Timer Watchdogs (Minute Boundaries)
    # -------------------------------------------------------------
    def schedule_next_minute_tick(self):
        now = datetime.datetime.now()
        seconds_to_next_minute = 60 - now.second
        if seconds_to_next_minute <= 0:
            seconds_to_next_minute = 60
        GLib.timeout_add_seconds(seconds_to_next_minute, self.on_minute_tick)

    def on_minute_tick(self):
        now = datetime.datetime.now()
        self.current_time_str = now.strftime("%H:%M")
        self.current_date_str = now.strftime("%A, %b %-d")
        self.update_hardware_stats()

        # Redraw Clock and At a Glance
        self.queue_draw_area(CLOCK_X - 10, CLOCK_Y - 10, CLOCK_W + 20, CLOCK_H + 20)
        self.queue_draw_area(AT_A_GLANCE_X, AT_A_GLANCE_Y, AT_A_GLANCE_W, AT_A_GLANCE_H)

        # Schedule next tick at next minute boundary
        self.schedule_next_minute_tick()
        return False

    def update_hardware_stats(self):
        # Read temperature
        try:
            with open("/proc/acpi/ibm/thermal", "r") as f:
                line = f.readline()
                temps = line.split()[1:]
                self.cpu_temp = int(temps[0])
        except Exception:
            self.cpu_temp = 50

        # Read fan speed
        try:
            with open("/proc/acpi/ibm/fan", "r") as f:
                for line in f:
                    if line.startswith("speed:"):
                        self.fan_rpm = int(line.split()[1])
                        break
        except Exception:
            self.fan_rpm = 0

    # -------------------------------------------------------------
    # Weather Functions (Cached + Async)
    # -------------------------------------------------------------
    def load_weather_cache(self):
        if os.path.exists(WEATHER_CACHE_PATH):
            try:
                with open(WEATHER_CACHE_PATH, "r") as f:
                    data = json.load(f)
                    w = data.get("last_weather", {})
                    if w:
                        self.weather_info = {
                            "city": w.get("city", "Malang"),
                            "temp": w.get("temp", 25),
                            "code": w.get("code", 3),
                            "condition": self.code_to_condition(w.get("code", 3))
                        }
            except Exception:
                pass

    def code_to_condition(self, code):
        mapping = {
            0: "Clear Sky",
            1: "Mainly Clear",
            2: "Partly Cloudy",
            3: "Overcast",
            45: "Foggy",
            48: "Depositing Rime Fog",
            51: "Light Drizzle",
            53: "Moderate Drizzle",
            55: "Dense Drizzle",
            61: "Slight Rain",
            63: "Moderate Rain",
            65: "Heavy Rain",
            71: "Slight Snow",
            73: "Moderate Snow",
            75: "Heavy Snow",
            80: "Rain Showers",
            81: "Moderate Showers",
            82: "Violent Showers",
            95: "Thunderstorm"
        }
        return mapping.get(code, "Partly Cloudy")

    def fetch_weather_async(self):
        def worker():
            try:
                cmd = ["/usr/bin/python3", "/home/teddy/.local/share/cinnamon/desklets/weather-widget@teddy/fetch_weather.py"]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    if "temp" in data:
                        self.weather_info = {
                            "city": data.get("city", "Malang"),
                            "temp": data.get("temp", 25),
                            "code": data.get("code", 3),
                            "condition": self.code_to_condition(data.get("code", 3))
                        }
                        GLib.idle_add(self.queue_draw_area, AT_A_GLANCE_X, AT_A_GLANCE_Y, AT_A_GLANCE_W, AT_A_GLANCE_H)
            except Exception as e:
                print(f"[PixelDesktop] Weather fetch worker error: {e}")
        threading.Thread(target=worker, daemon=True).start()
        return True

    # -------------------------------------------------------------
    # Cairo Drawing Engine (Material Design 3 / Google Pixel)
    # -------------------------------------------------------------
    def draw_rounded_pill(self, cr, x, y, w, h, radius):
        """Draws a pill/rounded rectangle path."""
        cr.new_sub_path()
        cr.arc(x + w - radius, y + radius, radius, -1.5707963, 0)
        cr.arc(x + w - radius, y + h - radius, radius, 0, 1.5707963)
        cr.arc(x + radius, y + h - radius, radius, 1.5707963, 3.1415926)
        cr.arc(x + radius, y + radius, radius, 3.1415926, 4.7123889)
        cr.close_path()

    def on_draw(self, widget, cr):
        # 1. Clear with total transparency
        cr.set_operator(cairo.OPERATOR_SOURCE)
        cr.set_source_rgba(0, 0, 0, 0)
        cr.paint()
        cr.set_operator(cairo.OPERATOR_OVER)

        # 2. Draw Google Pixel "At a Glance" Widget
        self.draw_at_a_glance(cr)

        # 3. Draw Material You Clock Pill
        self.draw_pixel_clock(cr)

        # 4. Draw Google Pixel Search Bar Pill
        self.draw_search_bar(cr)

        # 5. Draw Material You Media Player (if active)
        if self.media_playing:
            self.draw_media_player(cr)

        return False

    def draw_at_a_glance(self, cr):
        """Google Pixel 'At a Glance' (Date, Weather, Battery & Thermal status)."""
        x = AT_A_GLANCE_X
        y = AT_A_GLANCE_Y

        # Soft drop shadow for legibility over any wallpaper
        cr.save()

        # Date Line
        layout = self.create_pango_layout(self.current_date_str)
        desc = Pango.FontDescription("Google Sans Medium 22")
        layout.set_font_description(desc)

        # Shadow
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.move_to(x + 1.5, y + 1.5)
        PangoCairo.show_layout(cr, layout)

        # Text
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.98)
        cr.move_to(x, y)
        PangoCairo.show_layout(cr, layout)

        # Sub-Line: Weather & Battery Pill
        weather_text = f"⛅ {self.weather_info['temp']}°C  {self.weather_info['condition']}"
        bat_icon = "⚡" if self.battery_state in [1, 4] else "🔋"
        status_text = f"{weather_text}   •   {bat_icon} {self.battery_pct}%   •   {self.cpu_temp}°C"

        sub_layout = self.create_pango_layout(status_text)
        sub_desc = Pango.FontDescription("Google Sans 13")
        sub_layout.set_font_description(sub_desc)

        # Shadow
        cr.set_source_rgba(0, 0, 0, 0.45)
        cr.move_to(x + 1.5, y + 36.5)
        PangoCairo.show_layout(cr, sub_layout)

        # Text
        cr.set_source_rgba(0.90, 0.92, 0.95, 0.88)
        cr.move_to(x, y + 35)
        PangoCairo.show_layout(cr, sub_layout)

        cr.restore()

    def draw_pixel_clock(self, cr):
        """Material Design 3 Frosted Glass Pill Clock."""
        x = CLOCK_X
        y = CLOCK_Y
        w = CLOCK_W
        h = CLOCK_H
        radius = h / 2

        cr.save()

        # Pill Background (Material You Surface Container High)
        self.draw_rounded_pill(cr, x, y, w, h, radius)
        # Frosted glass fill
        cr.set_source_rgba(0.11, 0.13, 0.16, 0.68)
        cr.fill_preserve()

        # Glass Rim Stroke
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.14)
        cr.set_line_width(1.0)
        cr.stroke()

        # Inner subtle gradient
        self.draw_rounded_pill(cr, x + 1, y + 1, w - 2, h - 2, radius - 1)
        pat = cairo.LinearGradient(x, y, x, y + h)
        pat.add_color_stop_rgba(0.0, 1.0, 1.0, 1.0, 0.08)
        pat.add_color_stop_rgba(1.0, 1.0, 1.0, 1.0, 0.00)
        cr.set_source(pat)
        cr.fill()

        # Clock Text: Google Sans Bold
        layout = self.create_pango_layout(self.current_time_str)
        desc = Pango.FontDescription("Google Sans Bold 56")
        layout.set_font_description(desc)

        ink_rect, log_rect = layout.get_pixel_extents()
        text_w = log_rect.width
        text_h = log_rect.height

        text_x = x + (w - text_w) / 2
        text_y = y + (h - text_h) / 2 - 2

        # Soft text shadow
        cr.set_source_rgba(0, 0, 0, 0.35)
        cr.move_to(text_x + 2, text_y + 2)
        PangoCairo.show_layout(cr, layout)

        # Pastel Accent Color (Android 15 M3 Primary Accent #c2e7ff)
        cr.set_source_rgba(0.76, 0.90, 1.0, 0.98)
        cr.move_to(text_x, text_y)
        PangoCairo.show_layout(cr, layout)

        cr.restore()

    def render_svg_icon(self, handle, cr, x, y, width, height):
        if not handle:
            return
        cr.save()
        if hasattr(handle, "render_document"):
            rect = Rsvg.Rectangle()
            rect.x = x
            rect.y = y
            rect.width = width
            rect.height = height
            handle.render_document(cr, rect)
        else:
            cr.translate(x, y)
            dims = handle.get_dimensions()
            cr.scale(width / dims.width, height / dims.height)
            handle.render_cairo(cr)
        cr.restore()

    def draw_search_bar(self, cr):
        """Google Pixel Pill Search Bar with 4-color 'G', Mic, and Lens."""
        x = SEARCH_X
        y = SEARCH_Y
        w = SEARCH_W
        h = SEARCH_H
        radius = h / 2

        cr.save()

        # Pill Background
        self.draw_rounded_pill(cr, x, y, w, h, radius)
        # Glow / Active highlight if search is active
        if self.search_active:
            cr.set_source_rgba(0.14, 0.17, 0.22, 0.88)
        else:
            cr.set_source_rgba(0.10, 0.12, 0.16, 0.72)
        cr.fill_preserve()

        # Border Stroke
        if self.search_active:
            cr.set_source_rgba(0.66, 0.78, 0.98, 0.75)  # M3 Primary Accent border
            cr.set_line_width(1.5)
        else:
            cr.set_source_rgba(1.0, 1.0, 1.0, 0.16)
            cr.set_line_width(1.0)
        cr.stroke()

        # 1. Draw 4-color Google 'G' Logo on Left
        if self.icon_g:
            self.render_svg_icon(self.icon_g, cr, x + 16, y + 13, 28, 28)

        # 2. Draw Placeholder Text if NOT searching
        if not self.search_active:
            layout = self.create_pango_layout("Search device or Google...")
            desc = Pango.FontDescription("Google Sans 14")
            layout.set_font_description(desc)

            cr.set_source_rgba(0.85, 0.88, 0.92, 0.65)
            cr.move_to(x + 58, y + 17)
            PangoCairo.show_layout(cr, layout)

        # 3. Draw Google Assistant Mic Icon
        if self.icon_mic:
            self.render_svg_icon(self.icon_mic, cr, x + w - 74, y + 15, 24, 24)

        # 4. Draw Google Lens Icon
        if self.icon_lens:
            self.render_svg_icon(self.icon_lens, cr, x + w - 40, y + 15, 24, 24)

        cr.restore()

    def draw_media_player(self, cr):
        """Material You Floating Media Player Pill."""
        x = MEDIA_X
        y = MEDIA_Y
        w = MEDIA_W
        h = MEDIA_H
        radius = 24

        cr.save()

        # Rounded Container
        self.draw_rounded_pill(cr, x, y, w, h, radius)
        cr.set_source_rgba(0.12, 0.15, 0.19, 0.82)
        cr.fill_preserve()

        cr.set_source_rgba(1.0, 1.0, 1.0, 0.14)
        cr.set_line_width(1.0)
        cr.stroke()

        # Music Note / Album Art Thumbnail Pill
        thumb_x = x + 12
        thumb_y = y + 12
        thumb_size = h - 24
        self.draw_rounded_pill(cr, thumb_x, thumb_y, thumb_size, thumb_size, 14)
        cr.set_source_rgba(0.66, 0.78, 0.98, 0.35)
        cr.fill()

        # Music Icon
        layout_icon = self.create_pango_layout("🎵")
        layout_icon.set_font_description(Pango.FontDescription("18"))
        cr.move_to(thumb_x + 13, thumb_y + 11)
        PangoCairo.show_layout(cr, layout_icon)

        # Title Text (truncated)
        title = self.media_title
        if len(title) > 28:
            title = title[:27] + "…"
        layout_t = self.create_pango_layout(title)
        layout_t.set_font_description(Pango.FontDescription("Google Sans Medium 14"))
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.95)
        cr.move_to(x + thumb_size + 24, y + 16)
        PangoCairo.show_layout(cr, layout_t)

        # Artist Text
        artist = self.media_artist
        if len(artist) > 34:
            artist = artist[:33] + "…"
        layout_a = self.create_pango_layout(artist)
        layout_a.set_font_description(Pango.FontDescription("Google Sans 12"))
        cr.set_source_rgba(0.80, 0.84, 0.88, 0.70)
        cr.move_to(x + thumb_size + 24, y + 38)
        PangoCairo.show_layout(cr, layout_a)

        # Play/Pause indicator
        btn_layout = self.create_pango_layout("⏸")
        btn_layout.set_font_description(Pango.FontDescription("16"))
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.85)
        cr.move_to(x + w - 38, y + 25)
        PangoCairo.show_layout(cr, btn_layout)

        cr.restore()

    # -------------------------------------------------------------
    # Mouse & Keyboard Event Handlers
    # -------------------------------------------------------------
    def on_button_press(self, widget, event):
        x = event.x
        y = event.y

        # 1. Search Bar Clicks
        if SEARCH_X <= x <= SEARCH_X + SEARCH_W and SEARCH_Y <= y <= SEARCH_Y + SEARCH_H:
            # Check if clicked on Mic
            if x >= SEARCH_X + SEARCH_W - 80 and x < SEARCH_X + SEARCH_W - 46:
                subprocess.Popen(["google-chrome", "https://www.google.com"])
                return True
            # Check if clicked on Lens
            if x >= SEARCH_X + SEARCH_W - 46:
                subprocess.Popen(["google-chrome", "https://lens.google.com"])
                return True

            # Clicked on Search Input area -> Activate Entry
            self.activate_search()
            return True

        # 2. Media Player Clicks
        if self.media_playing and MEDIA_X <= x <= MEDIA_X + MEDIA_W and MEDIA_Y <= y <= MEDIA_Y + MEDIA_H:
            if self.media_player_name:
                self.mpris_toggle_play_pause(self.media_player_name)
            return True

        # 3. At a Glance Click -> Open Weather / Calendar
        if AT_A_GLANCE_X <= x <= AT_A_GLANCE_X + AT_A_GLANCE_W and AT_A_GLANCE_Y <= y <= AT_A_GLANCE_Y + AT_A_GLANCE_H:
            self.fetch_weather_async()
            return True

        # Clicked outside active search -> Deactivate
        if self.search_active:
            self.deactivate_search()

        return False

    def activate_search(self):
        self.search_active = True
        self.search_entry.show()
        self.search_entry.grab_focus()
        self.queue_draw_area(SEARCH_X - 10, SEARCH_Y - 10, SEARCH_W + 20, SEARCH_H + 20)

    def deactivate_search(self):
        self.search_active = False
        self.search_entry.set_text("")
        self.search_entry.hide()
        self.queue_draw_area(SEARCH_X - 10, SEARCH_Y - 10, SEARCH_W + 20, SEARCH_H + 20)

    def on_search_focus_out(self, widget, event):
        if self.search_active:
            self.deactivate_search()
        return False

    def on_search_key(self, widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.deactivate_search()
            return True
        return False

    def on_search_submit(self, widget):
        query = self.search_entry.get_text().strip()
        self.deactivate_search()
        if not query:
            return

        # App Launcher keywords
        apps_map = {
            "whatsmulti": ["/home/teddy/Applications/whatsmulti/whatsmulti"],
            "whatsapp": ["/home/teddy/Applications/whatsmulti/whatsmulti"],
            "terminal": ["gnome-terminal"],
            "files": ["nemo"],
            "nemo": ["nemo"],
            "chrome": ["google-chrome"],
            "settings": ["cinnamon-settings"],
            "calculator": ["gnome-calculator"],
            "music": ["youtube-music"],
            "code": ["code"]
        }

        q_lower = query.lower()
        if q_lower in apps_map:
            try:
                subprocess.Popen(apps_map[q_lower])
                return
            except Exception:
                pass

        # Otherwise launch Google Search in Chrome
        encoded = urllib.request.quote(query)
        url = f"https://www.google.com/search?q={encoded}"
        subprocess.Popen(["google-chrome", url])

    def mpris_toggle_play_pause(self, bus_name):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            player = Gio.DBusProxy.new_sync(
                bus, Gio.DBusProxyFlags.NONE, None,
                bus_name,
                "/org/mpris/MediaPlayer2",
                "org.mpris.MediaPlayer2.Player",
                None
            )
            player.call_sync("PlayPause", None, Gio.DBusCallFlags.NONE, -1, None)
        except Exception as e:
            print(f"[PixelDesktop] MPRIS toggle error: {e}")


def main():
    # Make executable react to SIGINT / SIGTERM cleanly
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    signal.signal(signal.SIGTERM, lambda s, f: Gtk.main_quit())

    win = PixelDesktopWindow()
    win.show_all()
    win.search_entry.hide()  # Entry starts hidden
    Gtk.main()

if __name__ == '__main__':
    main()
