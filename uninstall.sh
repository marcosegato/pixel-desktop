#!/usr/bin/env bash
# =============================================================================
# GoogleBook / Pixel Desktop Environment Uninstaller
# =============================================================================

set -e

SYSTEMD_USER_DIR="$HOME/.config/systemd/user"
SERVICES=(
    "pixel-dock.service"
    "pixel-desktop.service"
    "pixel-app-drawer.service"
    "pixel-recent-apps.service"
)

echo "Menghentikan dan menonaktifkan layanan Pixel Desktop..."
for svc in "${SERVICES[@]}"; do
    systemctl --user stop "$svc" 2>/dev/null || true
    systemctl --user disable "$svc" 2>/dev/null || true
    rm -f "$SYSTEMD_USER_DIR/$svc"
done

systemctl --user daemon-reload
rm -f /tmp/pixel_*.sock

echo "Mengembalikan pintasan Alt+Tab bawaan Cinnamon..."
if command -v gsettings >/dev/null 2>&1; then
    gsettings set org.cinnamon.desktop.keybindings.wm switch-windows "['<Alt>Tab']"
    gsettings set org.cinnamon.desktop.keybindings.wm switch-windows-backward "['<Shift><Alt>Tab']"
fi

echo "✓ Penghapusan selesai. Desktop telah kembali ke pengaturan default."
