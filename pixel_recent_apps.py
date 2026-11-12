#!/usr/bin/env python3
"""
Google Pixel UI / Material Design 3 (Android 15 / 16 / 17) Recent Apps Switcher
Fast, native GTK+3 & Cairo multitasking overview with overlapping card deck,
live window previews, Monet Peach Clay theming, RAM telemetry, and instant socket IPC.
"""

import os
import sys
import math
import socket
import threading
import subprocess
import time
import cairo

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
gi.require_version('Wnck', '3.0')
gi.require_version('PangoCairo', '1.0')
from gi.repository import Gtk, Gdk, GdkX11, Wnck, GLib, Pango, PangoCairo, GdkPixbuf

SOCKET_PATH = "/tmp/pixel_recent_apps.sock"

# Card & Geometry Constants (Optimized for 16:9 & 16:10 Desktop Windows)
CARD_W = 460
CARD_H = 370
CARD_RADIUS = 24
CARD_STRIDE = 330  # 130px overlap between adjacent cards
HEADER_H = 46
PREVIEW_PAD = 8
BOTTOM_BTN_SIZE = 54


def get_ram_info():
    try:
        with open('/proc/meminfo', 'r') as f:
            lines = f.readlines()
        info = {}
        for l in lines:
            parts = l.split(':')
            if len(parts) == 2:
                info[parts[0].strip()] = int(parts[1].split()[0])
        total_gb = info['MemTotal'] / (1024 * 1024)
        avail_gb = info['MemAvailable'] / (1024 * 1024)
        used_gb = total_gb - avail_gb
        return used_gb, total_gb, avail_gb
    except Exception:
        return 0.0, 0.0, 0.0


def is_dark_mode():
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


class WindowItem:
    def __init__(self, wnck_win, gdk_disp):
        self.wnck_win = wnck_win
        self.xid = wnck_win.get_xid()
        self.title = wnck_win.get_name() or "Aplikasi"
        self.app_name = wnck_win.get_class_group_name() or wnck_win.get_class_instance_name() or "Aplikasi"
        self.icon_pixbuf = None
        self.preview_pixbuf = None
        self.is_active = wnck_win.is_active()

        # Extract app icon
        try:
            raw_icon = wnck_win.get_icon()
            if raw_icon:
                self.icon_pixbuf = raw_icon.scale_simple(26, 26, GdkPixbuf.InterpType.BILINEAR)
            else:
                icon_theme = Gtk.IconTheme.get_default()
                for name in [self.app_name.lower(), self.app_name, "application-x-executable"]:
                    if icon_theme.has_icon(name):
                        self.icon_pixbuf = icon_theme.load_icon(name, 26, 0)
                        break
        except Exception:
            pass

        # Capture window preview
        try:
            gdk_win = GdkX11.X11Window.foreign_new_for_display(gdk_disp, self.xid)
            if gdk_win:
                geom = gdk_win.get_geometry()
                if geom.width > 30 and geom.height > 30:
                    raw_pb = Gdk.pixbuf_get_from_window(gdk_win, 0, 0, geom.width, geom.height)
                    if raw_pb:
                        target_w = CARD_W - (PREVIEW_PAD * 2)
                        target_h = CARD_H - HEADER_H - (PREVIEW_PAD * 2)
                        # Aspect cover scaling (fills preview area cleanly like Android Recent Apps)
                        scale = max(target_w / raw_pb.get_width(), target_h / raw_pb.get_height())
                        sw = max(1, int(raw_pb.get_width() * scale))
                        sh = max(1, int(raw_pb.get_height() * scale))
                        self.preview_pixbuf = raw_pb.scale_simple(sw, sh, GdkPixbuf.InterpType.BILINEAR)
        except Exception:
            self.preview_pixbuf = None


class PixelRecentApps(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.set_title("Pixel Recent Apps")
        self.set_role("recent-apps")
        self.set_decorated(False)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_app_paintable(True)

        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual and screen.is_composited():
            self.set_visual(visual)

        self.screen_w = screen.get_width()
        self.screen_h = screen.get_height()
        self.set_default_size(self.screen_w, self.screen_h)

        self.wnck_screen = Wnck.Screen.get_default()
        self.gdk_disp = GdkX11.X11Display.get_default()

        self.windows = []
        self.current_idx = 0
        self.scroll_x = 0.0
        self.target_scroll_x = 0.0
        self.anim_timer_id = 0

        self.mouse_x = -1
        self.mouse_y = -1
        self.hovered_close_idx = -1
        self.hovered_card_idx = -1
        self.hovered_clear_all = False

        self.drag_active = False
        self.drag_start_x = 0
        self.drag_start_scroll = 0

        self.connect("draw", self._on_draw)
        self.connect("key-press-event", self._on_key_press)
        self.connect("button-press-event", self._on_button_press)
        self.connect("button-release-event", self._on_button_release)
        self.connect("motion-notify-event", self._on_motion_notify)
        self.connect("scroll-event", self._on_scroll)
        self.connect("destroy", Gtk.main_quit)

        self.add_events(Gdk.EventMask.POINTER_MOTION_MASK |
                        Gdk.EventMask.BUTTON_PRESS_MASK |
                        Gdk.EventMask.BUTTON_RELEASE_MASK |
                        Gdk.EventMask.SCROLL_MASK |
                        Gdk.EventMask.KEY_PRESS_MASK)

    def refresh_windows(self):
        self.wnck_screen.force_update()
        raw_windows = self.wnck_screen.get_windows_stacked()
        valid = []

        # Filter out desktop, docks, lyrics, and our own window
        for w in reversed(raw_windows):
            w_type = w.get_window_type()
            if w_type in [Wnck.WindowType.NORMAL, Wnck.WindowType.DIALOG]:
                if not w.is_skip_tasklist() and not w.is_skip_pager():
                    name = w.get_name() or ""
                    if "Pixel Recent Apps" in name or "MaterialYouDesktop" in name or "DesktopLyrics" in name:
                        continue
                    item = WindowItem(w, self.gdk_disp)
                    valid.append(item)

        self.windows = valid
        if self.windows:
            # If 2 or more windows exist, pre-select the 2nd window (index 1 / previous active)
            # so the user can immediately switch with Enter or cycle with Super+Tab
            if len(self.windows) > 1:
                self.current_idx = 1
            else:
                self.current_idx = 0
        else:
            self.current_idx = 0

        self.target_scroll_x = - (self.current_idx * CARD_STRIDE)
        self.scroll_x = self.target_scroll_x
        self.queue_draw()

    def _update_target_scroll(self):
        if not self.windows:
            self.target_scroll_x = 0.0
            return
        self.target_scroll_x = - (self.current_idx * CARD_STRIDE)
        self._start_animation()

    def _start_animation(self):
        if self.anim_timer_id == 0:
            self.anim_timer_id = GLib.timeout_add(16, self._anim_tick)

    def _anim_tick(self):
        diff = self.target_scroll_x - self.scroll_x
        if abs(diff) < 0.5:
            self.scroll_x = self.target_scroll_x
            self.anim_timer_id = 0
            self.queue_draw()
            return False
        self.scroll_x += diff * 0.28
        self.queue_draw()
        return True

    def show_switcher(self):
        self.refresh_windows()
        self.show_all()
        self.present()
        self.grab_focus()

    def hide_switcher(self):
        self.hide()
        self.windows = []
        if self.anim_timer_id != 0:
            GLib.source_remove(self.anim_timer_id)
            self.anim_timer_id = 0

    def toggle_switcher(self):
        if self.is_visible():
            if self.windows and len(self.windows) > 1:
                self.current_idx = (self.current_idx + 1) % len(self.windows)
                self._update_target_scroll()
            else:
                self.hide_switcher()
        else:
            self.show_switcher()

    def activate_window(self, idx):
        if 0 <= idx < len(self.windows):
            item = self.windows[idx]
            self.hide_switcher()
            GLib.timeout_add(20, lambda: self._do_activate(item))

    def _do_activate(self, item):
        try:
            item.wnck_win.activate(int(time.time()))
        except Exception:
            subprocess.run(["wmctrl", "-i", "-a", hex(item.xid)])
        return False

    def close_window(self, idx):
        if 0 <= idx < len(self.windows):
            item = self.windows[idx]
            try:
                item.wnck_win.close(int(time.time()))
            except Exception:
                subprocess.run(["wmctrl", "-i", "-c", hex(item.xid)])

            self.windows.pop(idx)
            if self.current_idx >= len(self.windows):
                self.current_idx = max(0, len(self.windows) - 1)
            self._update_target_scroll()
            self.queue_draw()

            if not self.windows:
                GLib.timeout_add(300, self.hide_switcher)

    def close_all_windows(self):
        for item in list(self.windows):
            try:
                item.wnck_win.close(int(time.time()))
            except Exception:
                subprocess.run(["wmctrl", "-i", "-c", hex(item.xid)])
        self.windows = []
        self.hide_switcher()

    # =========================================================================
    # Cairo Drawing Routine
    # =========================================================================
    def _draw_rounded_rect(self, cr, x, y, w, h, r):
        cr.new_sub_path()
        cr.arc(x + w - r, y + r, r, -math.pi / 2, 0)
        cr.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
        cr.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
        cr.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
        cr.close_path()

    def _draw_shadow(self, cr, x, y, w, h, r, elevation=16):
        steps = 6
        max_blur = elevation * 1.5
        for i in range(steps, 0, -1):
            offset = (i / steps) * max_blur
            alpha = (0.05 / steps) * (steps - i + 1)
            cr.save()
            self._draw_rounded_rect(cr, x - offset / 2, y + (elevation * 0.4) - offset / 2, w + offset, h + offset, r + offset / 2)
            cr.set_source_rgba(0, 0, 0, alpha)
            cr.fill()
            cr.restore()

    def _on_draw(self, widget, cr):
        is_dark = is_dark_mode()
        sw = self.screen_w
        sh = self.screen_h

        # 1. Dimmed Wallpaper Scrim (Material You Frosted Backdrop)
        if is_dark:
            cr.set_source_rgba(0.08, 0.07, 0.06, 0.82) # Warm Dark Frosted Glass
        else:
            cr.set_source_rgba(0.98, 0.96, 0.95, 0.82) # Peach Clay Frosted Glass
        cr.paint()

        # 2. Top Header Telemetry & Status Bar
        self._draw_top_bar(cr, is_dark)

        # 3. Card Carousel (Overlapping Deck)
        if not self.windows:
            self._draw_empty_state(cr, is_dark)
        else:
            self._draw_cards(cr, is_dark)

        # 4. Bottom Floating Action Pill ("Clear All / Tutup Semua")
        self._draw_bottom_bar(cr, is_dark)

        return False

    def _draw_top_bar(self, cr, is_dark):
        sw = self.screen_w
        y = 28

        # Left Badge: "Aplikasi Terbuka"
        title_x = 48
        layout_t = self.create_pango_layout("Aplikasi Terbuka")
        layout_t.set_font_description(Pango.FontDescription("Google Sans Bold 16"))
        if is_dark:
            cr.set_source_rgba(0.93, 0.88, 0.86, 0.95)
        else:
            cr.set_source_rgba(0.14, 0.10, 0.09, 0.95)
        cr.move_to(title_x, y + 6)
        PangoCairo.show_layout(cr, layout_t)

        # Right Telemetry Pill: RAM Usage
        used_gb, total_gb, avail_gb = get_ram_info()
        ram_text = f"Memori: {used_gb:.1f} GB / {total_gb:.1f} GB ({avail_gb:.1f} GB Kosong)"

        layout_r = self.create_pango_layout(ram_text)
        layout_r.set_font_description(Pango.FontDescription("Google Sans Medium 11.5"))
        _, r_rect = layout_r.get_pixel_extents()

        pill_w = r_rect.width + 36
        pill_h = 36
        pill_x = sw - pill_w - 48
        pill_y = y

        self._draw_rounded_rect(cr, pill_x, pill_y, pill_w, pill_h, pill_h / 2)
        if is_dark:
            cr.set_source_rgba(0.17, 0.14, 0.13, 0.92) # Surface Container High #2B2422
        else:
            cr.set_source_rgba(0.96, 0.93, 0.91, 0.92) # Surface Container High #F5EDE8
        cr.fill()

        # Pill text
        cr.move_to(pill_x + 18, pill_y + 8)
        if is_dark:
            cr.set_source_rgba(1.0, 0.86, 0.81, 0.95) # Warm Peach
        else:
            cr.set_source_rgba(0.56, 0.30, 0.22, 0.95) # Deep Terracotta
        PangoCairo.show_layout(cr, layout_r)

    def _draw_empty_state(self, cr, is_dark):
        cx = self.screen_w / 2
        cy = self.screen_h / 2 - 30

        cr.new_sub_path()
        cr.arc(cx, cy - 20, 48, 0, 2 * math.pi)
        if is_dark:
            cr.set_source_rgba(0.22, 0.18, 0.17, 0.95)
        else:
            cr.set_source_rgba(0.96, 0.93, 0.91, 0.95)
        cr.fill()

        l1 = self.create_pango_layout("Tidak Ada Aplikasi Terbuka")
        l1.set_font_description(Pango.FontDescription("Google Sans Bold 17"))
        _, r1 = l1.get_pixel_extents()

        l2 = self.create_pango_layout("Semua jendela aplikasi sedang ditutup • Tekan Esc untuk kembali")
        l2.set_font_description(Pango.FontDescription("Google Sans Medium 12"))
        _, r2 = l2.get_pixel_extents()

        if is_dark:
            cr.set_source_rgba(0.93, 0.88, 0.86, 0.95)
            cr.move_to(cx - r1.width / 2, cy + 45)
            PangoCairo.show_layout(cr, l1)

            cr.set_source_rgba(0.82, 0.76, 0.75, 0.80)
            cr.move_to(cx - r2.width / 2, cy + 75)
            PangoCairo.show_layout(cr, l2)
        else:
            cr.set_source_rgba(0.14, 0.10, 0.09, 0.95)
            cr.move_to(cx - r1.width / 2, cy + 45)
            PangoCairo.show_layout(cr, l1)

            cr.set_source_rgba(0.33, 0.26, 0.25, 0.80)
            cr.move_to(cx - r2.width / 2, cy + 75)
            PangoCairo.show_layout(cr, l2)

    def _get_card_geometry(self, idx):
        cx = self.screen_w / 2
        cy = (self.screen_h - CARD_H) / 2 - 10
        card_x = cx - CARD_W / 2 + (idx * CARD_STRIDE) + self.scroll_x
        return card_x, cy, CARD_W, CARD_H

    def _draw_cards(self, cr, is_dark):
        n = len(self.windows)
        k = self.current_idx

        # Draw outside inward so focused card (k) is always drawn LAST (on top)
        draw_order = []
        for i in range(0, k):
            draw_order.append(i)
        for i in range(n - 1, k, -1):
            draw_order.append(i)
        if 0 <= k < n:
            draw_order.append(k)

        for idx in draw_order:
            is_focused = (idx == k)
            card_x, card_y, cw, ch = self._get_card_geometry(idx)

            if card_x + cw < -50 or card_x > self.screen_w + 50:
                continue

            item = self.windows[idx]
            self._draw_single_card(cr, idx, item, card_x, card_y, cw, ch, is_focused, is_dark)

    def _draw_single_card(self, cr, idx, item, x, y, w, h, is_focused, is_dark):
        r = CARD_RADIUS

        # Focused card slight elevation scale
        scale_factor = 1.02 if is_focused else 0.96
        if scale_factor != 1.0:
            cr.save()
            cx = x + w / 2
            cy = y + h / 2
            cr.translate(cx, cy)
            cr.scale(scale_factor, scale_factor)
            cr.translate(-cx, -cy)

        # 1. Elevation Drop Shadow
        shadow_elev = 24 if is_focused else 10
        self._draw_shadow(cr, x, y, w, h, r, shadow_elev)

        # 2. Card Surface Container
        self._draw_rounded_rect(cr, x, y, w, h, r)
        if is_dark:
            cr.set_source_rgba(0.12, 0.10, 0.09, 0.98) # Dark Surface #1E1A18
        else:
            cr.set_source_rgba(1.0, 0.98, 0.97, 0.98) # Light Surface #FFF8F6
        cr.fill()

        # 3. Card Header Bar
        hx = x + 12
        hy = y + 10
        hw = w - 24
        hh = HEADER_H - 12

        # Header Pill Background
        self._draw_rounded_rect(cr, hx, hy, hw, hh, hh / 2)
        if is_focused:
            if is_dark:
                cr.set_source_rgba(0.56, 0.30, 0.22, 0.95) # Dark Primary Container #8F4C38
            else:
                cr.set_source_rgba(1.0, 0.86, 0.81, 0.95) # Light Primary Container #FFDBCF
        else:
            if is_dark:
                cr.set_source_rgba(0.17, 0.14, 0.13, 0.90) # Surface Container High #2B2422
            else:
                cr.set_source_rgba(0.96, 0.93, 0.91, 0.90) # Surface Container High #F5EDE8
        cr.fill()

        # App Icon
        if item.icon_pixbuf:
            Gdk.cairo_set_source_pixbuf(cr, item.icon_pixbuf, hx + 6, hy + (hh - 26) / 2)
            cr.paint()

        # App Title & Window Name
        display_title = item.title.strip()
        if len(display_title) > 34:
            display_title = display_title[:32] + "…"

        layout = self.create_pango_layout(display_title)
        layout.set_font_description(Pango.FontDescription("Google Sans Bold 11.5"))

        if is_focused:
            if is_dark:
                cr.set_source_rgba(1.0, 0.86, 0.81, 0.98) # Warm Peach
            else:
                cr.set_source_rgba(0.24, 0.12, 0.08, 0.98) # Deep Espresso
        else:
            if is_dark:
                cr.set_source_rgba(0.93, 0.88, 0.86, 0.90)
            else:
                cr.set_source_rgba(0.14, 0.10, 0.09, 0.90)

        cr.move_to(hx + 38, hy + 9)
        PangoCairo.show_layout(cr, layout)

        # Header Close Button ('✕')
        cb_size = 26
        cb_x = hx + hw - cb_size - 5
        cb_y = hy + (hh - cb_size) / 2

        is_close_hovered = (self.hovered_close_idx == idx)
        cr.new_sub_path()
        cr.arc(cb_x + cb_size / 2, cb_y + cb_size / 2, cb_size / 2, 0, 2 * math.pi)
        if is_close_hovered:
            if is_dark:
                cr.set_source_rgba(1.0, 0.71, 0.63, 0.35)
            else:
                cr.set_source_rgba(0.56, 0.30, 0.22, 0.25)
            cr.fill()
        else:
            cr.set_source_rgba(0, 0, 0, 0.06)
            cr.fill()

        # '✕' icon inside button
        cr.save()
        cr.set_line_width(1.8)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        if is_focused:
            if is_dark:
                cr.set_source_rgba(1.0, 0.86, 0.81, 0.95)
            else:
                cr.set_source_rgba(0.24, 0.12, 0.08, 0.95)
        else:
            if is_dark:
                cr.set_source_rgba(0.93, 0.88, 0.86, 0.85)
            else:
                cr.set_source_rgba(0.14, 0.10, 0.09, 0.85)

        cross_pad = 7
        cr.move_to(cb_x + cross_pad, cb_y + cross_pad)
        cr.line_to(cb_x + cb_size - cross_pad, cb_y + cb_size - cross_pad)
        cr.move_to(cb_x + cb_size - cross_pad, cb_y + cross_pad)
        cr.line_to(cb_x + cross_pad, cb_y + cb_size - cross_pad)
        cr.stroke()
        cr.restore()

        # 4. Window Preview Canvas
        px = x + PREVIEW_PAD
        py = y + HEADER_H + 2
        pw = w - (PREVIEW_PAD * 2)
        ph = h - HEADER_H - PREVIEW_PAD - 4
        pr = 18

        cr.save()
        self._draw_rounded_rect(cr, px, py, pw, ph, pr)
        if is_dark:
            cr.set_source_rgba(0.06, 0.05, 0.05, 0.98)
        else:
            cr.set_source_rgba(0.94, 0.91, 0.89, 0.98)
        cr.fill_preserve()
        cr.clip()

        if item.preview_pixbuf:
            pb_w = item.preview_pixbuf.get_width()
            pb_h = item.preview_pixbuf.get_height()
            off_x = px + (pw - pb_w) / 2
            off_y = py + (ph - pb_h) / 2
            Gdk.cairo_set_source_pixbuf(cr, item.preview_pixbuf, off_x, off_y)
            cr.paint()
        else:
            cx = px + pw / 2
            cy = py + ph / 2
            if item.icon_pixbuf:
                big_icon = item.icon_pixbuf.scale_simple(64, 64, GdkPixbuf.InterpType.BILINEAR)
                if big_icon:
                    Gdk.cairo_set_source_pixbuf(cr, big_icon, cx - 32, cy - 40)
                    cr.paint()

            lbl = self.create_pango_layout(item.app_name)
            lbl.set_font_description(Pango.FontDescription("Google Sans Medium 13"))
            _, l_rect = lbl.get_pixel_extents()
            if is_dark:
                cr.set_source_rgba(0.82, 0.76, 0.75, 0.80)
            else:
                cr.set_source_rgba(0.33, 0.26, 0.25, 0.80)
            cr.move_to(cx - l_rect.width / 2, cy + 34)
            PangoCairo.show_layout(cr, lbl)

        cr.restore()

        # 5. Non-focused Dimming Scrim
        if not is_focused:
            cr.save()
            self._draw_rounded_rect(cr, x, y, w, h, r)
            if is_dark:
                cr.set_source_rgba(0.0, 0.0, 0.0, 0.22)
            else:
                cr.set_source_rgba(1.0, 1.0, 1.0, 0.22)
            cr.fill()
            cr.restore()
        else:
            # 6. Focused Card Accent Ring
            cr.save()
            self._draw_rounded_rect(cr, x + 0.5, y + 0.5, w - 1, h - 1, r)
            if is_dark:
                cr.set_source_rgba(1.0, 0.71, 0.63, 0.55) # Monet Light Peach
            else:
                cr.set_source_rgba(0.56, 0.30, 0.22, 0.45) # Monet Terracotta
            cr.set_line_width(1.5)
            cr.stroke()
            cr.restore()

        if scale_factor != 1.0:
            cr.restore()

    def _draw_bottom_bar(self, cr, is_dark):
        sw = self.screen_w
        sh = self.screen_h
        btn_s = BOTTOM_BTN_SIZE
        bx = (sw - btn_s) / 2
        by = sh - btn_s - 32

        # Button Shadow
        self._draw_shadow(cr, bx, by, btn_s, btn_s, btn_s / 2, 14)

        # Button Circle
        cr.new_sub_path()
        cr.arc(bx + btn_s / 2, by + btn_s / 2, btn_s / 2, 0, 2 * math.pi)

        if self.hovered_clear_all:
            if is_dark:
                cr.set_source_rgba(1.0, 0.71, 0.63, 0.98) # Bright Peach
                fg_color = (0.34, 0.12, 0.05, 0.98)
            else:
                cr.set_source_rgba(0.56, 0.30, 0.22, 0.98) # Rich Terracotta
                fg_color = (1.0, 1.0, 1.0, 0.98)
        else:
            if is_dark:
                cr.set_source_rgba(0.56, 0.30, 0.22, 0.95) # Dark Primary Container
                fg_color = (1.0, 0.86, 0.81, 0.98)
            else:
                cr.set_source_rgba(1.0, 0.86, 0.81, 0.95) # Light Primary Container
                fg_color = (0.24, 0.12, 0.08, 0.98)
        cr.fill()

        # '✕' / Clear All Icon in Center
        cr.save()
        cr.set_line_width(2.4)
        cr.set_line_cap(cairo.LINE_CAP_ROUND)
        cr.set_source_rgba(*fg_color)
        c_pad = 17
        cr.move_to(bx + c_pad, by + c_pad)
        cr.line_to(bx + btn_s - c_pad, by + btn_s - c_pad)
        cr.move_to(bx + btn_s - c_pad, by + c_pad)
        cr.line_to(bx + c_pad, by + btn_s - c_pad)
        cr.stroke()
        cr.restore()

        # Subtitle below button
        lbl = self.create_pango_layout("Tutup Semua")
        lbl.set_font_description(Pango.FontDescription("Google Sans Medium 10.5"))
        _, l_rect = lbl.get_pixel_extents()
        if is_dark:
            cr.set_source_rgba(0.82, 0.76, 0.75, 0.75)
        else:
            cr.set_source_rgba(0.33, 0.26, 0.25, 0.75)
        cr.move_to((sw - l_rect.width) / 2, by + btn_s + 6)
        PangoCairo.show_layout(cr, lbl)

    # =========================================================================
    # Event Handlers (Mouse, Drag, Scroll, Keyboard)
    # =========================================================================
    def _on_key_press(self, widget, event):
        keyval = event.keyval

        if keyval == Gdk.KEY_Escape:
            self.hide_switcher()
            return True
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Up):
            if self.windows:
                self.current_idx = (self.current_idx - 1) % len(self.windows)
                self._update_target_scroll()
            return True
        elif keyval in (Gdk.KEY_Right, Gdk.KEY_Down):
            if self.windows:
                self.current_idx = (self.current_idx + 1) % len(self.windows)
                self._update_target_scroll()
            return True
        elif keyval == Gdk.KEY_Tab:
            if event.state & Gdk.ModifierType.SHIFT_MASK:
                if self.windows:
                    self.current_idx = (self.current_idx - 1) % len(self.windows)
                    self._update_target_scroll()
            else:
                if self.windows:
                    self.current_idx = (self.current_idx + 1) % len(self.windows)
                    self._update_target_scroll()
            return True
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            self.activate_window(self.current_idx)
            return True
        elif keyval in (Gdk.KEY_Delete, Gdk.KEY_BackSpace):
            self.close_window(self.current_idx)
            return True
        elif keyval == Gdk.KEY_Home:
            if self.windows:
                self.current_idx = 0
                self._update_target_scroll()
            return True
        elif keyval == Gdk.KEY_End:
            if self.windows:
                self.current_idx = len(self.windows) - 1
                self._update_target_scroll()
            return True

        return False

    def _on_scroll(self, widget, event):
        if not self.windows:
            return False

        if event.direction == Gdk.ScrollDirection.UP or event.delta_y < 0 or event.direction == Gdk.ScrollDirection.LEFT:
            self.current_idx = max(0, self.current_idx - 1)
            self._update_target_scroll()
            return True
        elif event.direction == Gdk.ScrollDirection.DOWN or event.delta_y > 0 or event.direction == Gdk.ScrollDirection.RIGHT:
            self.current_idx = min(len(self.windows) - 1, self.current_idx + 1)
            self._update_target_scroll()
            return True
        return False

    def _on_motion_notify(self, widget, event):
        self.mouse_x = event.x
        self.mouse_y = event.y

        if self.drag_active:
            dx = event.x - self.drag_start_x
            self.scroll_x = self.drag_start_scroll + dx
            self.target_scroll_x = self.scroll_x
            self.queue_draw()
            return True

        # Check Clear All Button Hover
        sw = self.screen_w
        sh = self.screen_h
        btn_s = BOTTOM_BTN_SIZE
        bx = (sw - btn_s) / 2
        by = sh - btn_s - 32
        prev_clear_hover = self.hovered_clear_all
        self.hovered_clear_all = (bx <= event.x <= bx + btn_s and by <= event.y <= by + btn_s)

        # Check Close Button Hover on cards
        prev_close_hover = self.hovered_close_idx
        self.hovered_close_idx = -1

        k = self.current_idx
        n = len(self.windows)
        hit_order = [k] if 0 <= k < n else []
        for i in range(n - 1, -1, -1):
            if i != k:
                hit_order.append(i)

        for idx in hit_order:
            card_x, card_y, cw, ch = self._get_card_geometry(idx)
            if card_x <= event.x <= card_x + cw and card_y <= event.y <= card_y + ch:
                hx = card_x + 12
                hy = card_y + 10
                hw = cw - 24
                hh = HEADER_H - 12
                cb_size = 26
                cb_x = hx + hw - cb_size - 5
                cb_y = hy + (hh - cb_size) / 2

                if cb_x <= event.x <= cb_x + cb_size and cb_y <= event.y <= cb_y + cb_size:
                    self.hovered_close_idx = idx
                break

        if prev_clear_hover != self.hovered_clear_all or prev_close_hover != self.hovered_close_idx:
            self.queue_draw()

        return False

    def _on_button_press(self, widget, event):
        if event.button != 1:
            return False

        # 1. Clear All Button
        if self.hovered_clear_all:
            self.close_all_windows()
            return True

        # 2. Card Close Button
        if self.hovered_close_idx != -1:
            self.close_window(self.hovered_close_idx)
            return True

        # 3. Card Hit Testing
        k = self.current_idx
        n = len(self.windows)
        hit_order = [k] if 0 <= k < n else []
        for i in range(n - 1, -1, -1):
            if i != k:
                hit_order.append(i)

        for idx in hit_order:
            card_x, card_y, cw, ch = self._get_card_geometry(idx)
            if card_x <= event.x <= card_x + cw and card_y <= event.y <= card_y + ch:
                if idx == self.current_idx:
                    self.activate_window(idx)
                    return True
                else:
                    self.current_idx = idx
                    self._update_target_scroll()
                    return True

        # 4. Drag / Swipe gesture start
        self.drag_active = True
        self.drag_start_x = event.x
        self.drag_start_scroll = self.scroll_x

        return True

    def _on_button_release(self, widget, event):
        if event.button != 1:
            return False

        if self.drag_active:
            self.drag_active = False
            drag_dist = abs(event.x - self.drag_start_x)
            if drag_dist > 15:
                if self.windows:
                    nearest_idx = round(- self.scroll_x / CARD_STRIDE)
                    nearest_idx = max(0, min(len(self.windows) - 1, nearest_idx))
                    self.current_idx = nearest_idx
                    self._update_target_scroll()
                return True
            else:
                sw = self.screen_w
                sh = self.screen_h
                btn_s = BOTTOM_BTN_SIZE
                bx = (sw - btn_s) / 2
                by = sh - btn_s - 32
                if not (bx <= event.x <= bx + btn_s and by <= event.y <= by + btn_s):
                    is_on_card = False
                    for idx in range(len(self.windows)):
                        card_x, card_y, cw, ch = self._get_card_geometry(idx)
                        if card_x <= event.x <= card_x + cw and card_y <= event.y <= card_y + ch:
                            is_on_card = True
                            break
                    if not is_on_card:
                        self.hide_switcher()
                        return True

        return False


# =============================================================================
# IPC Server & Client
# =============================================================================
def start_ipc_server(app):
    if os.path.exists(SOCKET_PATH):
        try:
            os.remove(SOCKET_PATH)
        except Exception:
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
                    GLib.idle_add(app.toggle_switcher)
                elif data == "show":
                    GLib.idle_add(app.show_switcher)
                elif data == "hide":
                    GLib.idle_add(app.hide_switcher)
                elif data == "next":
                    def do_next():
                        if app.windows:
                            app.current_idx = (app.current_idx + 1) % len(app.windows)
                            app._update_target_scroll()
                    GLib.idle_add(do_next)
                elif data == "prev":
                    def do_prev():
                        if app.windows:
                            app.current_idx = (app.current_idx - 1) % len(app.windows)
                            app._update_target_scroll()
                    GLib.idle_add(do_prev)
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

    app = PixelRecentApps()
    start_ipc_server(app)

    if cmd in ("toggle", "show"):
        GLib.idle_add(app.show_switcher)

    Gtk.main()


if __name__ == "__main__":
    main()
