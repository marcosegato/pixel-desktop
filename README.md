# Google Pixel UI / GoogleBook Desktop Suite for Linux

> **Material Design 3 (Android 15 / 16 / 17 & ChromeOS Pixelbook) Desktop Environment for Debian-based Linux distributions (GTK/GNOME-based desktop environments / X11)**  
> Fast, native vector-rendered desktop suite written in Python 3, GTK+ 3, and Cairo with pure event-driven architecture (0.0% CPU when idle).

---

## 🌟 Key Features

### 1. Floating Shelf Dock (`pixel_dock.py`)
* **Material 3 Squircle Design**: A floating pill with subtle elevation shadows and curved corners characteristic of Google Pixel.
* **Launcher & Control Integration**:
  * The **App Drawer (`⸬`)** button on the left side to open the app drawer.
  * The **Multitasking Overview (`▢`)** button to see currently open apps.
  * **Google Search Bar**: A centered capsule design with the colorful Google 'G' logo.
* **Pinned & Running Apps**:
  * Includes a running dot indicator (*active dot*).
  * Free icon position arrangement via **Drag & Drop** (saved automatically).
  * **Smart Left Click**: Minimizes the active window, restores (*unminimizes*) minimized windows, and cycles between them when there are multiple windows of the same app.
  * **Right-Click App Profile Menu**: An isolated profile menu (WhatsApp Work/Admin/Personal, Google Chrome New Window & Incognito, Nemo Home/Downloads folders, Terminal, MPRIS music controls, etc.), plus *"Pin to Dock"* / *"Close Window"* toggles.
* **Smart Auto-Hide / Auto-Dodge**: The dock automatically slides down to hide when an active window is *Fullscreen*, *Maximized*, or covers the bottom dock area, and instantly reappears when the cursor touches the bottom edge of the screen.

### 2. Fullscreen App Drawer (`pixel_app_drawer.py`)
* **Modern App Drawer**: Solid Material 3 cards over a softly frosted background (*frosted glass backdrop*).
* **Instant Search**: Fast fuzzy-matching app search with a Google Web Search fallback.
* **Category Tab Chips**: App filtering by category (*All, Work & Productivity, Communication, Multimedia, Utilities*).
* **System Power Button (`⏻`)**: Quick access to shutdown, restart, or sleep dialogs (*shutdown / restart / suspend*).

### 3. Recent Apps Switcher / Alt+Tab Replacement (`pixel_recent_apps.py`)
* **Overlapping Card Deck Carousel**: Fully replaces the desktop environment's built-in window switcher.
* **Natural Alt+Tab Cycling**: Hold `Alt`, press `Tab` to select an app, and the moment `Alt` is released, the selected window is immediately activated and brought to front.
* **Real-Time Window Previews**: Live window preview screenshots via `GdkX11` & `libwnck`.
* **Header Telemetry & Clear All**: Displays real-time RAM usage in the top bar and a round *"Close All"* button at the bottom.

### 4. Interactive Desktop Canvas (`pixel_desktop.py`)
* **Native Google Pixel Widgets**:
  * Large Digital Clock & Calendar with *Google Sans* typography.
  * Real-Time Open-Meteo Weather with automatic location detection via IP geolocation (falls back to Rome, Italy).
  * ThinkPad Temperature & Battery Telemetry.
  * MPRIS Music Player with a moving audio wave bar (*squiggly progress wave*).
  * Quick Folder Launchers (*Downloads, Documents, Pictures, Music*).
  * Interactive Control Center with a live volume slider and shortcut buttons (Dark Mode, Wi-Fi, Bluetooth).
  * Quick Notes with an automatic file watcher (*live watcher* on `~/.config/quick-notes.txt`).
* **Input Shape Click-Through**: Transparent click-through areas to the wallpaper without blocking the desktop.
* **0.0% Idle CPU**: No active polling loops. Uses DBus UPower, DBus MPRIS, and a minute-boundary tick.

---

## 🚀 Installation Guide (Quick Start)

### System Requirements (Prerequisites)
* **Distro**: any Debian-based distribution (Ubuntu, Debian, etc.) with a GTK/GNOME-based desktop environment (GNOME, ...), on an X11 session or a Wayland session providing XWayland — the services run with `GDK_BACKEND=x11`, and the dock/desktop windows are marked `SKIP_TASKBAR` + `DOCK` so they never appear in the dash or the Alt+Tab switcher.
* **Python**: Python 3.10 or above.

### 1-Click Installation via Script

1. Clone this repository — any location works (e.g. `~/src/pixel-desktop`, `~/Documents/pixel-desktop`):
   ```bash
   git clone https://github.com/<username>/pixel-desktop.git
   cd pixel-desktop
   ```

2. Run the installer script from that directory:
   ```bash
   ./install.sh
   ```
   *(Use `./install.sh -y` to skip the automatic package confirmation prompt).*

The installer script will automatically:
* Check and install system dependency packages (`python3-gi`, `gir1.2-wnck-3.0`, `python3-xlib`, `wmctrl`, etc.).
* Install the official *Google Sans* fonts to `~/.local/share/fonts/`.
* Set `assets/pixel-peach-clay-discs-1080p.jpg` as the desktop background.
* Register and enable 4 `systemd --user` background services, pointing at the directory you cloned to.
* Configure the desktop environment's `Alt+Tab` shortcut to the Pixel Recent Apps Switcher (GNOME/GTK-based desktops).

---

## ⌨️ Keyboard Shortcuts (Keybindings)

| Keyboard Shortcut | Action / Function |
| :--- | :--- |
| **`Alt + Tab`** / **`Super + Tab`** | Opens the Recent Apps Switcher (Hold Alt, press Tab to navigate, release Alt to select). |
| **`Shift + Alt + Tab`** | Navigates the Recent Apps Switcher backward (*reverse*). |
| **`Enter`** / **`Space`** | Activates the currently selected window in Recent Apps. |
| **`Esc`** | Closes the App Drawer or Recent Apps overlay without selecting. |
| **`Delete`** / **`Backspace`** | Closes the currently selected window in Recent Apps. |

---

## 🛠️ Customization & Configuration Files

All configuration files are stored neatly in standard JSON / text format in `~/.config/`:

| Configuration File | Description |
| :--- | :--- |
| **`~/.config/pixel-launcher-apps.json`** | List of apps pinned to the Dock (`name`, `icon`, `cmd`, `bg`, `shape`). Changes are updated on screen instantly without a restart. |
| **`~/.config/pixel-widgets-pos.json`** | Desktop widget position coordinates (saved automatically when widgets are moved with a mouse drag). |
| **`~/.config/quick-notes.txt`** | Text content of the quick notes desktop widget. |
| **`~/.config/weather-config.json`** | Weather location settings. With `"auto_location": true` (default) the city is detected via IP geolocation; if detection fails, Rome (Italy) is used. Set `"auto_location": false` plus `manual_city`, `manual_lat`, `manual_lon` to pin a location. |
| **`~/.config/pixel-desktop.json`** | Optional overrides for companion-app locations (see below). |

Companion apps (WhatsApp PWA, YouTube Music, prayer-applet) are discovered automatically in this order: the path set in `~/.config/pixel-desktop.json`, then the well-known `~/Applications/<name>` location, then any standard installed application (deb/flatpak) via its desktop entry, then a web fallback. To point a companion at a custom directory:

```json
{
  "companion_apps": {
    "whatsapp": "~/opt/whatsapp-pwa",
    "youtube_music": "~/apps/youtube-music",
    "prayer_applet": "~/dev/prayer-applet"
  }
}
```

---

## ⚙️ Service Management (Systemd Services)

All desktop components run independently in the background under `systemd --user` control:

```bash
# Check the status of all components
systemctl --user status pixel-dock pixel-desktop pixel-recent-apps pixel-app-drawer

# Restart the dock after changing settings
systemctl --user restart pixel-dock.service

# Temporarily stop
systemctl --user stop pixel-dock pixel-desktop pixel-recent-apps pixel-app-drawer
```

---

## 🔄 Applying Changes & Updates

Services run the scripts **directly from the cloned directory**, so edits to a script are picked up as soon as the corresponding service is restarted. Use this table to know what to restart:

| Changed file | Action required |
| :--- | :--- |
| `pixel_dock.py` | `systemctl --user restart pixel-dock.service` |
| `pixel_desktop.py` | `systemctl --user restart pixel-desktop.service` |
| `pixel_app_drawer.py` | `systemctl --user restart pixel-app-drawer.service` |
| `pixel_recent_apps.py` | `systemctl --user restart pixel-recent-apps.service` |
| `pixel_common.py` | Restart **all four** services (it is imported by every component) |
| `fetch_weather.py` | Nothing — it is executed on demand by the desktop widget |
| `install.sh` / `systemd/*.service` | Re-run `./install.sh` (re-renders the unit files and reloads systemd) — required after environment changes such as `GDK_BACKEND` or `XAUTHORITY` |
| `~/.config/pixel-launcher-apps.json` | Nothing — the dock watches the file and reloads instantly |
| `~/.config/quick-notes.txt` | Nothing — the notes widget watches the file live |
| `~/.config/weather-config.json` | Nothing — the next weather fetch uses the new settings |
| Moved the repository directory | Re-run `./install.sh` from the new location (the unit files embed the absolute path) |

### Pulling upstream updates

If you modified files locally, `git pull` may refuse to overwrite them. To take the upstream version of a script and reinstall cleanly:

```bash
cd /path/to/pixel-desktop
git stash            # or: git checkout -- <file> to discard local changes in one file
git pull
git stash pop        # re-apply your local changes (skip if you discarded them)

# Re-render the systemd units and restart everything
./install.sh -y
systemctl --user daemon-reload
systemctl --user restart pixel-dock pixel-desktop pixel-recent-apps pixel-app-drawer
```

If a change still does not appear after restarting:

1. Check the service logs: `journalctl --user -u pixel-dock.service -n 50 --no-pager` (repeat for the other units).
2. Verify the unit points at the right directory: `systemctl --user cat pixel-dock.service | grep ExecStart`.
3. If the repository moved, re-run `./install.sh` so the units are regenerated with the new path.
4. Log out and back in (or `systemctl --user daemon-reload`) if a unit file was edited manually — systemd caches unit definitions.

---

## 🗑️ Uninstallation

To remove this suite and restore the desktop environment's shortcuts and background to their default settings:
```bash
cd /path/to/pixel-desktop   # the directory you cloned to
./uninstall.sh
```

---

## 📄 License
Distributed under the MIT license. Feel free to use, modify, and share it!
