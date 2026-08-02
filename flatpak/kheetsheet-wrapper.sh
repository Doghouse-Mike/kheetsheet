#!/usr/bin/env bash
# Flatpak entry point. Runs inside the sandbox on every launch (and on
# every login, once autostarted via the Background portal below).
#
# DRAFT / UNTESTED - written from reading install.sh and the runtime's
# installed binaries, not yet run inside an actual built Flatpak. Two
# pieces in particular need verification against a real sandbox:
#   - The kpackagetool6/kwriteconfig6/qdbus sequence mirrors install.sh,
#     confirmed those three binaries exist in org.kde.Platform//6.11,
#     but not yet confirmed they succeed when *run from inside* the
#     sandbox against the --filesystem=xdg-data/kwin:create grant.
#   - RequestBackground's real response arrives async via a Response
#     signal on the returned request handle, not the initial method
#     return. gdbus has no clean "block until this signal fires"
#     primitive for an arbitrary object path (`gdbus wait` only waits
#     for a bus *name* to appear/disappear), so the `gdbus monitor`
#     below is a crude timeout-bounded grep, not a real wait. If that's
#     flaky in practice, redo this in Python with python-gi (PyGObject
#     is already a build dependency) using GLib's portal helpers
#     properly instead of hand-rolled D-Bus over bash.
set -euo pipefail

KWIN_SCRIPT_ID="kheetsheet-activewindow"
APP_LIB="/app/lib/kheetsheet"
QDBUS_BIN="qdbus"

echo "==> Installing/refreshing KWin active-window watcher script..."
rm -rf "$XDG_DATA_HOME/kwin/scripts/$KWIN_SCRIPT_ID"
kpackagetool6 --type KWin/Script -i "$APP_LIB/kwin-script"
kwriteconfig6 --file kwinrc --group Plugins --key "${KWIN_SCRIPT_ID}Enabled" true
"$QDBUS_BIN" org.kde.KWin /KWin reconfigure >/dev/null 2>&1 || true

SCRIPT_MAIN_JS="$XDG_DATA_HOME/kwin/scripts/$KWIN_SCRIPT_ID/contents/code/main.js"
"$QDBUS_BIN" org.kde.KWin /Scripting org.kde.kwin.Scripting.loadScript "$SCRIPT_MAIN_JS" "$KWIN_SCRIPT_ID" >/dev/null 2>&1 || true
"$QDBUS_BIN" org.kde.KWin /Scripting org.kde.kwin.Scripting.start >/dev/null 2>&1 || true

# Ask the Background portal for permission to run on login, replacing
# the systemd user service used in the non-Flatpak install. First run
# surfaces a one-time consent dialog (xdg-desktop-portal-kde) - this is
# a real, visible UX change from the old silent `systemctl enable`, not
# a bug.
echo "==> Requesting background/autostart permission..."
REQUEST_PATH=$(gdbus call --session \
  --dest org.freedesktop.portal.Desktop \
  --object-path /org/freedesktop/portal/desktop \
  --method org.freedesktop.portal.Background.RequestBackground \
  "" '{"reason": <"Run the shortcut-overlay daemon in the background">, "autostart": <true>, "commandline": <["kheetsheet"]>}' \
  2>/dev/null | grep -oP "(?<=objectpath ')[^']+" || true)

if [ -n "$REQUEST_PATH" ]; then
  timeout 30 gdbus monitor --session --dest org.freedesktop.portal.Desktop 2>/dev/null \
    | grep -m1 -F "$REQUEST_PATH: org.freedesktop.portal.Request.Response" || true
fi

echo "==> Starting daemon..."
export QT_QPA_PLATFORM=xcb
exec python3 "$APP_LIB/daemon/__main__.py"
