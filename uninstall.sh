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

echo "Stopping and disabling Pixel Desktop services..."
for svc in "${SERVICES[@]}"; do
    systemctl --user stop "$svc" 2>/dev/null || true
    systemctl --user disable "$svc" 2>/dev/null || true
    rm -f "$SYSTEMD_USER_DIR/$svc"
done

systemctl --user daemon-reload
rm -f /tmp/pixel_*.sock

echo "Restoring the default desktop Alt+Tab shortcuts..."
if command -v gsettings >/dev/null 2>&1; then
    DE="${XDG_CURRENT_DESKTOP,,}"
    if [[ "$DE" == *cinnamon* ]] || command -v cinnamon-session >/dev/null 2>&1; then
        gsettings set org.cinnamon.desktop.keybindings.wm switch-windows "['<Alt>Tab']"
        gsettings set org.cinnamon.desktop.keybindings.wm switch-windows-backward "['<Shift><Alt>Tab']"
        # Remove the suite's custom keybindings (custom12 / custom13)
        CUSTOM_LIST=$(gsettings get org.cinnamon.desktop.keybindings custom-list 2>/dev/null || echo "[]")
        CLEANED=$(echo "$CUSTOM_LIST" | sed "s/, 'custom12'//g; s/, 'custom13'//g")
        if [[ "$CLEANED" != "$CUSTOM_LIST" ]]; then
            gsettings set org.cinnamon.desktop.keybindings custom-list "$CLEANED"
        fi
    else
        # GNOME / generic GTK path: remove the suite's custom keybindings
        MEDIA_KEYS="org.gnome.settings-daemon.plugins.media-keys"
        CURRENT=$(gsettings get "$MEDIA_KEYS" custom-keybindings 2>/dev/null || echo "")
        CURRENT="${CURRENT#@as }"
        if [[ -n "$CURRENT" && "$CURRENT" != "[]" ]]; then
            CLEANED=$(echo "$CURRENT" | sed \
                -e "s|, */org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab/||g" \
                -e "s|, */org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab-reverse/||g" \
                -e "s|/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab/, ||g" \
                -e "s|/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab-reverse/, ||g" \
                -e "s|/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab/||g" \
                -e "s|/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/pixel-alttab-reverse/||g")
            gsettings set "$MEDIA_KEYS" custom-keybindings "$CLEANED"
        fi
    fi
fi

echo "✓ Uninstallation complete. The desktop has been restored to its default settings."
