#!/usr/bin/env bash
# =============================================================================
# GoogleBook / Pixel Desktop Environment Installer
# Material Design 3 (Android 15-17) Desktop Experience for Debian-based Linux
# (GTK/GNOME-based desktop environments)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUTO_YES=false

if [[ "$1" == "-y" || "$1" == "--yes" ]]; then
    AUTO_YES=true
fi

# Colors
C_RESET="\033[0m"
C_BOLD="\033[1m"
C_PEACH="\033[38;2;255;219;207m"
C_TERRACOTTA="\033[38;2;143;76;56m"
C_GREEN="\033[38;2;76;175;80m"
C_BLUE="\033[38;2;66;133;244m"
C_YELLOW="\033[38;2;251;188;4m"

ask_yes_no() {
    local question="$1"
    local answer=""
    if [ "$AUTO_YES" = true ]; then
        echo -e "${C_BLUE}${question} [Y/n]: yes (auto)${C_RESET}"
        return 0
    fi
    while true; do
        read -rp "$(echo -e "${C_BLUE}${question} [Y/n]: ${C_RESET}")" answer || true
        case "$answer" in
            ""|[Yy]|[Yy][Ee][Ss]) return 0 ;;
            [Nn]|[Nn][Oo]) return 1 ;;
            *) echo -e "${C_YELLOW}Please answer y or n.${C_RESET}" ;;
        esac
    done
}

clear_pixel_keybindings() {
    # Restore GNOME/GTK defaults and remove the suite's custom Alt+Tab entries.
    command -v gsettings >/dev/null 2>&1 || return 0
    gsettings set org.gnome.desktop.wm.keybindings switch-windows "['<Alt>Tab']" 2>/dev/null || true
    gsettings set org.gnome.desktop.wm.keybindings switch-windows-backward "['<Shift><Alt>Tab']" 2>/dev/null || true
    local media_keys="org.gnome.settings-daemon.plugins.media-keys"
    local current cleaned
    current=$(gsettings get "$media_keys" custom-keybindings 2>/dev/null || echo "")
    current="${current#@as }"
    if [[ -n "$current" && "$current" != "[]" ]]; then
        cleaned=$(echo "$current" | sed \
            -e "s|, */org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab/||g" \
            -e "s|, */org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab-reverse/||g" \
            -e "s|/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab/, ||g" \
            -e "s|/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab-reverse/, ||g" \
            -e "s|/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab/||g" \
            -e "s|/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab-reverse/||g")
        gsettings set "$media_keys" custom-keybindings "$cleaned" 2>/dev/null || true
    fi
}

echo -e "${C_BOLD}${C_TERRACOTTA}"
echo "  ╔══════════════════════════════════════════════════════════════════════╗"
echo "  ║         Google Pixel UI / Material Design 3 Desktop Suite            ║"
echo "  ║    ChromeOS Pixelbook Desktop Experience for Debian-based Linux      ║"
echo "  ╚══════════════════════════════════════════════════════════════════════╝"
echo -e "${C_RESET}"

# 1. Package Dependencies Check
echo -e "${C_BOLD}${C_BLUE}[1/6] Checking system dependencies...${C_RESET}"
REQUIRED_PKGS=(
    python3
    python3-gi
    python3-cairo
    gir1.2-gtk-3.0
    gir1.2-wnck-3.0
    gir1.2-rsvg-2.0
    python3-xlib
    wmctrl
    libglib2.0-bin
)

MISSING_PKGS=()
for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! dpkg -s "$pkg" >/dev/null 2>&1; then
        MISSING_PKGS+=("$pkg")
    fi
done

if [ ${#MISSING_PKGS[@]} -gt 0 ]; then
    echo -e "${C_YELLOW}Missing packages: ${MISSING_PKGS[*]}${C_RESET}"
    if [ "$AUTO_YES" = true ]; then
        DO_INSTALL="y"
    else
        read -rp "Install the packages above now via apt? [Y/n]: " DO_INSTALL
    fi
    if [[ "$DO_INSTALL" =~ ^[Yy]?$ ]]; then
        sudo apt update
        sudo apt install -y "${MISSING_PKGS[@]}"
    else
        echo -e "${C_YELLOW}Warning: Dependencies are incomplete, some components may fail to run.${C_RESET}"
    fi
else
    echo -e "${C_GREEN}✓ All system package dependencies are installed.${C_RESET}"
fi

# 2. Font Installation
echo -e "\n${C_BOLD}${C_BLUE}[2/6] Checking Google Sans fonts...${C_RESET}"
FONT_DIR="$HOME/.local/share/fonts/GoogleSans"
if ! fc-list : family | grep -qi "Google Sans"; then
    echo "Installing Google Sans fonts to $FONT_DIR..."
    mkdir -p "$FONT_DIR"
    if [ -d "$SCRIPT_DIR/assets/fonts" ]; then
        cp -r "$SCRIPT_DIR/assets/fonts/"*.ttf "$FONT_DIR/"
        fc-cache -f "$FONT_DIR"
        echo -e "${C_GREEN}✓ Google Sans fonts installed successfully.${C_RESET}"
    else
        echo -e "${C_YELLOW}assets/fonts directory not found, skipping font installation.${C_RESET}"
    fi
else
    echo -e "${C_GREEN}✓ Google Sans fonts are already available on the system.${C_RESET}"
fi

# 3. Default Configuration & Scratchpad
echo -e "\n${C_BOLD}${C_BLUE}[3/6] Checking initial configuration...${C_RESET}"
CONFIG_DIR="$HOME/.config/pixel-desktop"
mkdir -p "$CONFIG_DIR"

# Migrate configuration files from the old ~/.config/ location (one-time).
LEGACY_CONFIGS=(
    "pixel-launcher-apps.json"
    "pixel-widgets-pos.json"
    "pixel-desktop.json"
    "pixel-app-usage.json"
    "weather-config.json"
    "quick-notes.txt"
)
for cfg in "${LEGACY_CONFIGS[@]}"; do
    if [ -f "$HOME/.config/$cfg" ] && [ ! -e "$CONFIG_DIR/$cfg" ]; then
        mv "$HOME/.config/$cfg" "$CONFIG_DIR/$cfg"
        echo -e "${C_GREEN}✓ Migrated ~/.config/$cfg -> ~/.config/pixel-desktop/$cfg${C_RESET}"
    fi
done

# Migrate the weather cache as well (disposable, but keeps offline fallback).
CACHE_DIR="$HOME/.cache/pixel-desktop"
mkdir -p "$CACHE_DIR"
if [ -f "$HOME/.cache/weather-cache.json" ] && [ ! -e "$CACHE_DIR/weather-cache.json" ]; then
    mv "$HOME/.cache/weather-cache.json" "$CACHE_DIR/weather-cache.json"
    echo -e "${C_GREEN}✓ Migrated ~/.cache/weather-cache.json -> ~/.cache/pixel-desktop/weather-cache.json${C_RESET}"
fi

if [ ! -f "$CONFIG_DIR/quick-notes.txt" ]; then
    cat << 'EOF' > "$CONFIG_DIR/quick-notes.txt"
# Quick Notes (Pixel Quick Notes)
- Click on this widget to open the text editor.
- Supports live updates without reload.
- Write your to-do list or daily agenda here!
EOF
    echo -e "${C_GREEN}✓ Initial notes file ~/.config/pixel-desktop/quick-notes.txt created.${C_RESET}"
fi

# 4. Systemd User Services Installation
echo -e "\n${C_BOLD}${C_BLUE}[4/6] Installing systemd user background services...${C_RESET}"

DOCK_SERVICES=(
    "pixel-dock.service"
    "pixel-app-drawer.service"
    "pixel-recent-apps.service"
)
DESKTOP_SERVICES=(
    "pixel-desktop.service"
)

if ask_yes_no "Activate the dock (includes app drawer and recent apps)?"; then
    ACTIVATE_DOCK=true
else
    ACTIVATE_DOCK=false
fi
if ask_yes_no "Activate the desktop (widgets and canvas)?"; then
    ACTIVATE_DESKTOP=true
else
    ACTIVATE_DESKTOP=false
fi

ENABLE_SERVICES=()
DISABLE_SERVICES=()
if [ "$ACTIVATE_DOCK" = true ]; then
    ENABLE_SERVICES+=("${DOCK_SERVICES[@]}")
else
    DISABLE_SERVICES+=("${DOCK_SERVICES[@]}")
fi
if [ "$ACTIVATE_DESKTOP" = true ]; then
    ENABLE_SERVICES+=("${DESKTOP_SERVICES[@]}")
else
    DISABLE_SERVICES+=("${DESKTOP_SERVICES[@]}")
fi

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

# Stop, disable and remove the units of the components the user declined.
for svc in "${DISABLE_SERVICES[@]}"; do
    systemctl --user disable --now "$svc" >/dev/null 2>&1 || true
    rm -f "$SYSTEMD_USER_DIR/$svc"
    echo "  - Deactivated: $svc"
done

# Install the unit files of the selected components.
for svc in "${ENABLE_SERVICES[@]}"; do
    SRC_FILE="$SCRIPT_DIR/systemd/$svc"
    DST_FILE="$SYSTEMD_USER_DIR/$svc"
    if [ -f "$SRC_FILE" ]; then
        sed "s|@PIXEL_DESKTOP_DIR@|$SCRIPT_DIR|g" "$SRC_FILE" > "$DST_FILE"
        echo "  - Installed: $svc"
    fi
done

systemctl --user daemon-reload
if [ ${#ENABLE_SERVICES[@]} -gt 0 ]; then
    echo "Enabling and starting: ${ENABLE_SERVICES[*]}"
    systemctl --user enable --now "${ENABLE_SERVICES[@]}"
    echo -e "${C_GREEN}✓ Activated: ${ENABLE_SERVICES[*]}${C_RESET}"
else
    echo -e "${C_YELLOW}No Pixel Desktop component was activated.${C_RESET}"
fi

# 5. Alt+Tab Keybindings (GTK/GNOME-based desktops)
echo -e "\n${C_BOLD}${C_BLUE}[5/6] Configuring Alt+Tab shortcuts...${C_RESET}"
if [ "$ACTIVATE_DOCK" != true ]; then
    clear_pixel_keybindings
    echo -e "${C_YELLOW}Skipped: the Recent Apps Switcher is not activated (desktop defaults restored).${C_RESET}"
elif command -v gsettings >/dev/null 2>&1; then
    # GNOME / GTK path (settings-daemon media-keys custom keybindings)
    MEDIA_KEYS="org.gnome.settings-daemon.plugins.media-keys"
    KB_PATH1="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab/"
    KB_PATH2="/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab-reverse/"

    # Disable built-in window switching to avoid conflicts
    gsettings set org.gnome.desktop.wm.keybindings switch-windows "[]"
    gsettings set org.gnome.desktop.wm.keybindings switch-windows-backward "[]"

    # Append our keybindings to the custom list (handles "@as []" and "[]")
    CUSTOM_LIST=$(gsettings get "$MEDIA_KEYS" custom-keybindings 2>/dev/null || echo "@as []")
    CUSTOM_LIST="${CUSTOM_LIST#@as }"
    NEW_LIST="$CUSTOM_LIST"
    for KBP in "$KB_PATH1" "$KB_PATH2"; do
        if [[ "$NEW_LIST" != *"$KBP"* ]]; then
            if [[ -z "$NEW_LIST" || "$NEW_LIST" == "[]" ]]; then
                NEW_LIST="['$KBP']"
            else
                NEW_LIST="${NEW_LIST%]}, '$KBP']"
            fi
        fi
    done
    gsettings set "$MEDIA_KEYS" custom-keybindings "$NEW_LIST"

    gsettings set "$MEDIA_KEYS.custom-keybinding:$KB_PATH1" name "Pixel Recent Apps"
    gsettings set "$MEDIA_KEYS.custom-keybinding:$KB_PATH1" binding "['<Alt>Tab', '<Super>Tab']"
    gsettings set "$MEDIA_KEYS.custom-keybinding:$KB_PATH1" command "$SCRIPT_DIR/pixel_recent_apps.py alt-tab"

    gsettings set "$MEDIA_KEYS.custom-keybinding:$KB_PATH2" name "Pixel Recent Apps Reverse"
    gsettings set "$MEDIA_KEYS.custom-keybinding:$KB_PATH2" binding "['<Shift><Alt>Tab', '<Shift><Super>Tab']"
    gsettings set "$MEDIA_KEYS.custom-keybinding:$KB_PATH2" command "$SCRIPT_DIR/pixel_recent_apps.py prev"
    echo -e "${C_GREEN}✓ Alt+Tab and Super+Tab shortcuts wired to the Pixel Switcher (GNOME/GTK).${C_RESET}"
else
    echo -e "${C_YELLOW}gsettings not found, skipping Alt+Tab shortcut setup.${C_RESET}"
fi

# 6. Desktop Background
echo -e "\n${C_BOLD}${C_BLUE}[6/6] Setting desktop background...${C_RESET}"
BG_IMAGE="$SCRIPT_DIR/assets/pixel-peach-clay-discs-1080p.jpg"
if [ ! -f "$BG_IMAGE" ]; then
    echo -e "${C_YELLOW}assets/pixel-peach-clay-discs-1080p.jpg not found, skipping desktop background.${C_RESET}"
elif command -v gsettings >/dev/null 2>&1; then
    if gsettings set org.gnome.desktop.background picture-uri "file://$BG_IMAGE" 2>/dev/null; then
        # Dark-mode variant (GNOME 42+) and fill mode; ignore if unsupported
        gsettings set org.gnome.desktop.background picture-uri-dark "file://$BG_IMAGE" 2>/dev/null || true
        gsettings set org.gnome.desktop.background picture-options "zoom" 2>/dev/null || true
        echo -e "${C_GREEN}✓ Desktop background set to assets/pixel-peach-clay-discs-1080p.jpg.${C_RESET}"
    else
        echo -e "${C_YELLOW}Could not set the desktop background (schema not available), skipping.${C_RESET}"
    fi
else
    echo -e "${C_YELLOW}gsettings not found, skipping desktop background setup.${C_RESET}"
fi

echo -e "\n${C_BOLD}${C_GREEN}══════════════════════════════════════════════════════════════════════${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}  INSTALLATION COMPLETED SUCCESSFULLY! 🎉${C_RESET}"
echo -e "${C_BOLD}${C_GREEN}══════════════════════════════════════════════════════════════════════${C_RESET}"
echo "Active features:"
echo "  • Floating Shelf Dock : Auto-hides when a window is maximized / fullscreen"
echo "  • App Drawer (⸬)      : Press the drawer button on the dock for search & categories"
echo "  • Recent Apps (▢)     : Hold Alt then press Tab for smooth window switching"
echo "  • Desktop Widgets     : Clock, Open-Meteo Weather, Battery, MPRIS Music, Quick Notes"
echo ""
echo "To manage service status:"
echo "  systemctl --user status pixel-dock pixel-desktop pixel-recent-apps pixel-app-drawer"
echo ""
