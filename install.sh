#!/usr/bin/env bash
# Install Couchpad for the current user (no root needed). Safe to run again.
#   ./install.sh               install / update
#   ./install.sh --no-steam    don't touch Steam's desktop controller layout
#   ./install.sh --test        run the unit tests first
#   ./install.sh uninstall     remove (restores Steam's desktop layout)
set -euo pipefail

SRC="$(cd "$(dirname "$0")" && pwd)"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CONF="${XDG_CONFIG_HOME:-$HOME/.config}"
DEST="$DATA/couchpad"
UNIT="$CONF/systemd/user/couchpad.service"
BIN="$HOME/.local/bin/couchpad"
APPS="$DATA/applications"
ICON="$DATA/icons/hicolor/scalable/apps/couchpad.svg"
AUTOSTART="$CONF/autostart/couchpad-tray.desktop"
RULE=/etc/udev/rules.d/72-couchpad-dualsense.rules

bold() { printf '\033[1m%s\033[0m\n' "$*"; }
say() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m!!\033[0m %s\n' "$*"; }

steam_running() { pgrep -u "$USER" -x steam >/dev/null; }

APP_RE='^([^ ]*/)?python3( [^ ]+)* -m couchpad app( |$)'
app_running() { pgrep -u "$USER" -f "$APP_RE" >/dev/null; }

stop_app() {   # control center / tray of the installed version; SIGTERM saves and quits
    app_running || return 1
    pkill -TERM -u "$USER" -f "$APP_RE" || true
    for _ in $(seq 50); do app_running || return 0; sleep 0.1; done
    pkill -KILL -u "$USER" -f "$APP_RE" || true
    return 0
}
game_running() { pgrep -u "$USER" -f 'reaper SteamLaunch AppId=[1-9]' >/dev/null; }

with_steam_closed() {
    local was_running=0
    if steam_running; then
        if game_running; then
            warn "A game is running - skipping the Steam layout step (run ./install.sh again later)"
            return 0
        fi
        was_running=1
        say "Closing Steam for a moment"
        steam -shutdown >/dev/null 2>&1 || true
        for _ in $(seq 60); do steam_running || break; sleep 0.5; done
        if steam_running; then
            warn "Steam did not quit - skipping the Steam layout step"
            return 0
        fi
    fi
    "$@" || true
    if [ "$was_running" = 1 ]; then
        say "Starting Steam again"
        if systemctl --user cat app-steam@autostart.service >/dev/null 2>&1; then
            systemctl --user start app-steam@autostart.service
        else
            (setsid steam -silent >/dev/null 2>&1 &)
        fi
    fi
}

if [ "${1:-}" = uninstall ]; then
    systemctl --user disable --now couchpad.service 2>/dev/null || true
    stop_app || true
    if [ -d "$DEST/couchpad" ]; then
        with_steam_closed env PYTHONPATH="$DEST" python3 -m couchpad steam-layout restore
    fi
    rm -rf "$DEST"
    rm -f "$UNIT" "$BIN" "$APPS/couchpad.desktop" "$APPS/couchpad-wheel.desktop" "$ICON" "$AUTOSTART"
    systemctl --user daemon-reload
    say "Removed. Settings stay in $CONF/couchpad (delete by hand if you like)."
    [ -f "$RULE" ] && say "Optional udev rule left in place: sudo rm $RULE"
    exit 0
fi

STEAM_STEP=1
RUN_TESTS=0
for arg in "$@"; do
    case "$arg" in
        --no-steam) STEAM_STEP=0 ;;
        --test) RUN_TESTS=1 ;;
        *) warn "unknown option $arg"; exit 2 ;;
    esac
done

bold "Couchpad $(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$SRC/couchpad/__init__.py")"

say "Checking dependencies"
missing=()
for mod in evdev pyudev gi PySide6.QtQuick; do
    python3 -c "import $mod" 2>/dev/null || missing+=("$mod")
done
if [ ${#missing[@]} -gt 0 ]; then
    warn "Missing Python modules: ${missing[*]}"
    echo "    Fedora/Bazzite: rpm-ostree install python3-evdev python3-pyudev python3-gobject python3-pyside6"
    echo "    Arch:           sudo pacman -S python-evdev python-pyudev python-gobject pyside6"
    echo "    Debian/Ubuntu:  sudo apt install python3-evdev python3-pyudev python3-gi python3-pyside6.qtquick"
    exit 1
fi

if [ "$RUN_TESTS" = 1 ] && [ -d "$SRC/tests" ]; then
    say "Running tests"
    (cd "$SRC" && PYTHONPATH="$SRC:$SRC/tests" python3 -m unittest discover -s tests -q)
fi

APP_WAS_RUNNING=0
if stop_app; then APP_WAS_RUNNING=1; fi

say "Copying files to $DEST"
mkdir -p "$DEST"
if [ "$SRC" != "$DEST" ]; then
    rm -rf "$DEST/couchpad.new"
    cp -r "$SRC/couchpad" "$DEST/couchpad.new"
    find "$DEST/couchpad.new" -name __pycache__ -prune -exec rm -rf {} +
    rm -rf "$DEST/couchpad"
    mv "$DEST/couchpad.new" "$DEST/couchpad"
    cp "$SRC/README.md" "$DEST/" 2>/dev/null || true
    cp -r "$SRC/system" "$DEST/"
    cp "$SRC/install.sh" "$DEST/"
fi

mkdir -p "$(dirname "$UNIT")" "$(dirname "$BIN")" "$APPS" "$(dirname "$ICON")"
sed "s|%h/couchpad|$DEST|g" "$SRC/system/couchpad.service" > "$UNIT"
cat > "$BIN" <<EOF
#!/bin/sh
PYTHONPATH="$DEST" exec python3 -W ignore -m couchpad "\$@"
EOF
chmod +x "$BIN"
install -m644 "$SRC/couchpad/data/couchpad.svg" "$ICON"
install -m644 "$SRC/system/couchpad.desktop" "$APPS/couchpad.desktop"
sed -i "s|^Exec=.*|Exec=$BIN app|" "$APPS/couchpad.desktop"
install -m644 "$SRC/system/couchpad-wheel.desktop" "$APPS/couchpad-wheel.desktop"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS" 2>/dev/null || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q "$DATA/icons/hicolor" 2>/dev/null || true

PYTHONPATH="$DEST" python3 -m couchpad --write-config >/dev/null

# Tray icon at login (can be switched off in the app)
if PYTHONPATH="$DEST" python3 -c "import sys; from couchpad import config; sys.exit(0 if config.load().tray else 1)"; then
    mkdir -p "$(dirname "$AUTOSTART")"
    cat > "$AUTOSTART" <<EOF
[Desktop Entry]
Type=Application
Name=Couchpad
Comment=Значок Couchpad в трее
Icon=couchpad
Exec=$BIN app --tray
X-KDE-autostart-phase=2
NoDisplay=true
EOF
fi

if [ "$STEAM_STEP" = 1 ]; then
    with_steam_closed env PYTHONPATH="$DEST" python3 -m couchpad steam-layout neutral
fi

systemctl --user daemon-reload
systemctl --user enable couchpad.service >/dev/null 2>&1
systemctl --user restart couchpad.service
sleep 1
if systemctl --user is-active --quiet couchpad.service; then
    say "Service is running"
else
    warn "Service did not start: journalctl --user -u couchpad -n 30"
fi
# Bring the tray back (or start it the first time) when there is a desktop.
if [ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] && { [ "$APP_WAS_RUNNING" = 1 ] || [ -f "$AUTOSTART" ]; }; then
    (setsid "$BIN" app --tray >/dev/null 2>&1 &)
fi
bold "Done. Open «Couchpad» from the app menu, or double-tap Share on the DualSense."
