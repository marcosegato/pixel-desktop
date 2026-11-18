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

echo -e "${C_BOLD}${C_TERRACOTTA}"
echo "  ╔══════════════════════════════════════════════════════════════════════╗"
echo "  ║         Google Pixel UI / Material Design 3 Desktop Suite            ║"
echo "  ║    ChromeOS Pixelbook Desktop Experience for Debian-based Linux      ║"
echo "  ╚══════════════════════════════════════════════════════════════════════╝"
echo -e "${C_RESET}"

# 1. Package Dependencies Check
echo -e "${C_BOLD}${C_BLUE}[1/5] Checking system dependencies...${C_RESET}"
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
echo -e "\n${C_BOLD}${C_BLUE}[2/5] Checking Google Sans fonts...${C_RESET}"
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
echo -e "\n${C_BOLD}${C_BLUE}[3/5] Checking initial configuration...${C_RESET}"
mkdir -p "$HOME/.config"
if [ ! -f "$HOME/.config/quick-notes.txt" ]; then
    cat << 'EOF' > "$HOME/.config/quick-notes.txt"
# Quick Notes (Pixel Quick Notes)
- Click on this widget to open the text editor.
- Supports live updates without reload.
- Write your to-do list or daily agenda here!
EOF
    echo -e "${C_GREEN}✓ Initial notes file ~/.config/quick-notes.txt created.${C_RESET}"
fi

# 4. Systemd User Services Installation
echo -e "\n${C_BOLD}${C_BLUE}[4/5] Installing systemd user background services...${C_RESET}"
SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
mkdir -p "$SYSTEMD_USER_DIR"

SERVICES=(
    "pixel-dock.service"
    "pixel-desktop.service"
    "pixel-app-drawer.service"
    "pixel-recent-apps.service"
)

for svc in "${SERVICES[@]}"; do
    SRC_FILE="$SCRIPT_DIR/systemd/$svc"
    DST_FILE="$SYSTEMD_USER_DIR/$svc"
    if [ -f "$SRC_FILE" ]; then
        sed "s|@PIXEL_DESKTOP_DIR@|$SCRIPT_DIR|g" "$SRC_FILE" > "$DST_FILE"
        echo "  - Installed: $svc"
    fi
done

systemctl --user daemon-reload
echo "Enabling and starting services..."
systemctl --user enable --now "${SERVICES[@]}"
echo -e "${C_GREEN}✓ All 4 Pixel Desktop services are active and running.${C_RESET}"

# 5. Alt+Tab Keybindings (GTK/GNOME-based desktops)
echo -e "\n${C_BOLD}${C_BLUE}[5/5] Configuring Alt+Tab shortcuts...${C_RESET}"
if command -v gsettings >/dev/null 2>&1; then
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
