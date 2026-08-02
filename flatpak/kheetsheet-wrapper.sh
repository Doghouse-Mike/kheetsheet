#!/usr/bin/env bash
# Flatpak entry point. Runs inside the sandbox on every launch (and on
# every login, once autostarted via the Background portal below).
#
# Built and run once against a real Flatpak (org.kde.Platform//6.11).
# What that run found and fixed:
#   - kpackagetool6 IS present in the runtime, but its "KWin/Script"
#     package-structure plugin is NOT - that plugin ships as part of
#     KWin itself (the host compositor package), not the generic app
#     runtime, so `kpackagetool6 --type KWin/Script -i ...` fails inside
#     the sandbox with "Package type 'KWin/Script' not found" even
#     though the binary runs fine. A KWin script is just plain files
#     (metadata.json + contents/code/main.js) with no compile step, so
#     the fix below is a plain `cp -r` instead of going through
#     kpackagetool6 at all.
#   - Inside the sandbox $XDG_DATA_HOME is redirected to the app's
#     private ~/.var/app/<id>/data, not the real host path the
#     --filesystem=xdg-data/kwin:create grant exposes - so, like
#     install.sh does on the host side, this script uses
#     $HOME/.local/share directly for the one path that needs to land
#     in the real, granted location.
#   - Deliberately does NOT also run install.sh's kwriteconfig6 step to
#     persist Enabled=true into kwinrc: that would need a third
#     non-default permission (kwinrc lives under xdg-config, not the
#     xdg-data/kwin path already granted) just to cover the edge case of
#     KWin restarting independently mid-session without the app also
#     restarting. The loadScript+start D-Bus calls below already run on
#     every app launch, which happens on every login via the Background
#     portal autostart - that covers the common case without asking for
#     more than the KWin D-Bus/filesystem access already justified.
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
REAL_XDG_DATA_HOME="$HOME/.local/share"

echo "==> Installing/refreshing KWin active-window watcher script..."
KWIN_SCRIPT_DEST="$REAL_XDG_DATA_HOME/kwin/scripts/$KWIN_SCRIPT_ID"
rm -rf "$KWIN_SCRIPT_DEST"
mkdir -p "$(dirname "$KWIN_SCRIPT_DEST")"
cp -r "$APP_LIB/kwin-script" "$KWIN_SCRIPT_DEST"

SCRIPT_MAIN_JS="$KWIN_SCRIPT_DEST/contents/code/main.js"
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
