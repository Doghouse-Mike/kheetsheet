#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KWIN_SCRIPT_ID="kheetsheet-activewindow"
SERVICE_NAME="kheetsheet-daemon.service"

echo "==> Checking dependencies..."
missing=()
python3 -c "import PyQt6.QtWidgets, PyQt6.QtDBus" 2>/dev/null || missing+=("python3-pyqt6")
python3 -c "import dbus" 2>/dev/null || missing+=("python3-dbus")
python3 -c "import dbus.mainloop.pyqt6" 2>/dev/null || missing+=("python3-dbus.mainloop.pyqt6")
python3 -c "import gi" 2>/dev/null || missing+=("python3-gi")
python3 -c "import gi; gi.require_version('Atspi','2.0'); from gi.repository import Atspi" 2>/dev/null || missing+=("gir1.2-atspi-2.0")
command -v kpackagetool6 >/dev/null 2>&1 || missing+=("kpackagetool6")
command -v kwriteconfig6 >/dev/null 2>&1 || missing+=("libkf6config-bin")
QDBUS_BIN="$(command -v qdbus6 || command -v qdbus-qt6 || true)"
[ -n "$QDBUS_BIN" ] || missing+=("qdbus-qt6")

if [ ${#missing[@]} -ne 0 ]; then
    echo "Missing dependencies, install these and re-run (see README.md for the full install command):"
    printf '  - %s\n' "${missing[@]}"
    exit 1
fi

# Detect a previous install pointing at a different copy of this project
# (e.g. an older download/extraction) before we overwrite its service file
# below - the daemon only ever runs from one path at a time, so once this
# run finishes, that old copy is dead weight rather than a working install.
# We only report it; deleting an arbitrary directory automatically isn't
# something this script does.
OLD_SERVICE_FILE="$HOME/.config/systemd/user/$SERVICE_NAME"
OLD_PROJECT_DIR=""
if [ -f "$OLD_SERVICE_FILE" ]; then
    OLD_PROJECT_DIR="$(sed -n 's|^ExecStart=/usr/bin/python3 \(.*\)/daemon/__main__\.py$|\1|p' "$OLD_SERVICE_FILE")"
fi

# A terminal launched from a sandboxed app (e.g. a snap-packaged IDE) may have
# XDG_DATA_HOME redirected to that app's private sandbox directory, which
# would silently install the KWin script somewhere KWin never reads from.
REAL_XDG_DATA_HOME="${XDG_DATA_HOME:-$HOME/.local/share}"
case "$REAL_XDG_DATA_HOME" in
    "$HOME"/snap/*)
        echo "Note: sandboxed XDG_DATA_HOME detected ($REAL_XDG_DATA_HOME), using \$HOME/.local/share instead."
        REAL_XDG_DATA_HOME="$HOME/.local/share"
        ;;
esac

echo "==> Installing KWin active-window watcher script..."
# Always reinstall clean rather than relying on `-u` (upgrade): kpackagetool6's
# upgrade path re-validates the *already-installed* metadata.json against
# --type, so an older install lacking a field kpackagetool6 later started
# requiring (e.g. KPackageStructure) makes -u fail even when the new source
# metadata.json is fine. Removing first sidesteps that comparison entirely.
rm -rf "$REAL_XDG_DATA_HOME/kwin/scripts/$KWIN_SCRIPT_ID"
XDG_DATA_HOME="$REAL_XDG_DATA_HOME" kpackagetool6 --type KWin/Script -i "$PROJECT_DIR/kwin-script"
kwriteconfig6 --file kwinrc --group Plugins --key "${KWIN_SCRIPT_ID}Enabled" true
"$QDBUS_BIN" org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true

SCRIPT_MAIN_JS="$REAL_XDG_DATA_HOME/kwin/scripts/$KWIN_SCRIPT_ID/contents/code/main.js"
# Unload any already-loaded instance under this same ID first (e.g. from a
# previous run of this script) - confirmed the hard way that calling
# loadScript while an instance with the same ID is already loaded can leave
# KWin's script unloaded with no error surfaced, silently killing active-
# window tracking until something happens to reload it. unloadScript
# returning false just means nothing was loaded yet, which is fine.
"$QDBUS_BIN" org.kde.KWin /Scripting org.kde.kwin.Scripting.unloadScript "$KWIN_SCRIPT_ID" >/dev/null 2>&1 || true
"$QDBUS_BIN" org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript "$SCRIPT_MAIN_JS" "$KWIN_SCRIPT_ID" >/dev/null 2>&1 || true
"$QDBUS_BIN" org.kde.KWin /Scripting org.kde.kwin.Scripting.start >/dev/null 2>&1 || true

echo "==> Installing systemd user service..."
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/$SERVICE_NAME" <<EOF
[Unit]
Description=KheetSheet daemon (AT-SPI shortcut overlay)
After=graphical-session.target
PartOf=graphical-session.target

[Service]
Environment=QT_QPA_PLATFORM=xcb
ExecStart=/usr/bin/python3 $PROJECT_DIR/daemon/__main__.py
Restart=on-failure
RestartSec=2

# Hardening. Deliberately does NOT include PrivateTmp/ProtectHome/
# ProtectSystem: those sandbox via mount namespaces and would hide either
# /tmp/.X11-unix (the XWayland socket QT_QPA_PLATFORM=xcb connects to) or
# /run/user/<uid> (the D-Bus session bus socket) or both, breaking the
# daemon outright. Everything below only removes capabilities this daemon
# has no legitimate use for, so it can't affect D-Bus, AT-SPI, or X11.
NoNewPrivileges=true
RestrictSUIDSGID=true
RestrictRealtime=true
RestrictNamespaces=true
LockPersonality=true
ProtectHostname=true
ProtectClock=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectKernelLogs=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_UNIX

[Install]
WantedBy=graphical-session.target
EOF
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
# `enable --now` only *starts* the unit, which is a no-op if it's already
# running from a previous install - it would silently keep running the old
# code instead of picking up whatever changed in this run. `restart` starts
# it if stopped and restarts it if already active, so an upgrade always
# takes effect immediately rather than waiting for the next login/reboot.
systemctl --user restart "$SERVICE_NAME"

cat <<'EOF'

==> Install complete.

One manual step remains -- kglobalaccel only registers command shortcuts
through its real registration protocol, not by reading config files off disk
(a plain .desktop file + kglobalshortcutsrc entry gets silently discarded on
next login, confirmed the hard way). So:

  1. Open System Settings -> Shortcuts.
  2. Click "Add New" (top right) -> "Command or Script".
  3. Name it "KheetSheet", set your preferred trigger key, and set the command to:
       gdbus call --session --dest com.kheetsheet.Daemon --object-path /KheetSheet --method com.kheetsheet.Daemon.Toggle
  4. Click Apply.

Double-check the key that actually lands in the trigger field before saving --
it can end up different from what you pressed (e.g. picking up extra held
modifiers) if the recording widget catches a stray keypress.
EOF

if [ -n "$OLD_PROJECT_DIR" ] && [ "$OLD_PROJECT_DIR" != "$PROJECT_DIR" ]; then
    cat <<EOF

==> Note: a previous install pointed at:
      $OLD_PROJECT_DIR
    The daemon now runs from this copy instead:
      $PROJECT_DIR
    That old directory is no longer used for anything -- safe to delete it
    once you've confirmed this one works.
EOF
fi
