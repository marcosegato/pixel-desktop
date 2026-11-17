# Google Pixel UI / GoogleBook Desktop Suite for Linux

> **Material Design 3 (Android 15 / 16 / 17 & ChromeOS Pixelbook) Desktop Environment for Linux Mint (Cinnamon / X11)**  
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
* **Overlapping Card Deck Carousel**: Fully replaces the built-in Cinnamon window switcher.
* **Natural Alt+Tab Cycling**: Hold `Alt`, press `Tab` to select an app, and the moment `Alt` is released, the selected window is immediately activated and brought to front.
* **Real-Time Window Previews**: Live window preview screenshots via `GdkX11` & `libwnck`.
* **Header Telemetry & Clear All**: Displays real-time RAM usage in the top bar and a round *"Close All"* button at the bottom.

### 4. Interactive Desktop Canvas (`pixel_desktop.py`)
* **Native Google Pixel Widgets**:
  * Large Digital Clock & Calendar with *Google Sans* typography.
  * Real-Time Open-Meteo Weather with automatic location detection via IP geolocation.
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
* **Distro**: Linux Mint (Cinnamon) 21.x / 22.x, Ubuntu, or any Debian-based distro with an X11 session.
* **Python**: Python 3.10 or above.

### 1-Click Installation via Script

1. Clone this repository:
   ```bash
   git clone https://github.com/<username>/pixel-desktop.git ~/Applications/pixel-desktop
   cd ~/Applications/pixel-desktop
   ```

2. Run the installer script:
   ```bash
   ./install.sh
   ```
   *(Use `./install.sh -y` to skip the automatic package confirmation prompt).*

The installer script will automatically:
* Check and install system dependency packages (`python3-gi`, `gir1.2-wnck-3.0`, `python3-xlib`, `wmctrl`, etc.).
* Install the official *Google Sans* fonts to `~/.local/share/fonts/`.
* Register and enable 4 `systemd --user` background services.
* Configure the Cinnamon `Alt+Tab` shortcut to the Pixel Recent Apps Switcher.

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
| **`~/.config/weather-config.json`** | Manual weather coordinate settings (city, latitude, longitude) when not using IP auto-detect. |

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

## 🗑️ Uninstallation

To remove this suite and restore the Cinnamon desktop shortcuts to their default settings:
```bash
cd ~/Applications/pixel-desktop
./uninstall.sh
```

---

## 📄 License
Distributed under the MIT license. Feel free to use, modify, and share it!
