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
#   - Originally skipped install.sh's kwriteconfig6 step (persisting
#     Enabled=true into kwinrc), on the theory that per-launch
#     loadScript+start already covered the common case and the flag was
#     only needed for the rare case of KWin restarting independently
#     mid-session. Added it back partway through investigating the real
#     bug below, suspecting it might be the cause - it wasn't (the
#     tests that seemed to implicate it were actually just hitting the
#     real bug regardless of this flag), but it's low-cost correct
#     coverage for that narrow restart case regardless, so left it in.
#     Needs its own --filesystem=xdg-config/kwinrc:create grant (kwinrc
#     isn't under the xdg-data/kwin path already granted) and, like the
#     KWin script path itself, $XDG_CONFIG_HOME is redirected inside the
#     sandbox to the app's private ~/.var/app/<id>/config - so this
#     overrides it to the real $HOME/.config for this one call, same
#     pattern as XDG_DATA_HOME below.
#   - RequestBackground's real response arrives async via a Response
#     signal on the returned request handle, not the initial method
#     return. gdbus has no clean "block until this signal fires"
#     primitive for an arbitrary object path (`gdbus wait` only waits
#     for a bus *name* to appear/disappear), so the `gdbus monitor`
#     below is a crude timeout-bounded grep, not a real wait. If that's
#     flaky in practice, redo this in Python with python-gi (PyGObject
#     is already a build dependency) using GLib's portal helpers
#     properly instead of hand-rolled D-Bus over bash.
#   - Stopped calling loadScript/start/reconfigure here at all - the
#     daemon's own service.py already does unloadScript+loadScript+start
#     once at its own startup (ensure_kwin_script_loaded(), by design -
#     see its comment - because KWin doesn't reliably auto-load an
#     enabled script on its own), so this wrapper doing the same thing
#     too was pure duplication. This turned out NOT to be the cause of
#     the real bug described below, but having exactly one place own
#     script loading is simpler regardless, so left it removed.
#   - THE ACTUAL BUG, found after a long investigation (isScriptLoaded
#     kept reporting false sometime after every launch, with no error
#     anywhere): service.py's ensure_kwin_script_loaded() computed the
#     script's path from os.environ["XDG_DATA_HOME"] - which inside the
#     sandbox is redirected to this app's private
#     ~/.var/app/<id>/data, not the real host path this wrapper actually
#     copies the script files to (via the --filesystem grant). loadScript
#     on that nonexistent path returned a valid-looking id and "start()"
#     didn't error either - it just silently loaded nothing, which is
#     what looked like the script mysteriously going unloaded after the
#     fact. Fixed in service.py by detecting /.flatpak-info and using
#     $HOME/.local/share directly in that case, same as this wrapper
#     already does for its own file copy below.
set -euo pipefail

KWIN_SCRIPT_ID="kheetsheet-activewindow"
APP_LIB="/app/lib/kheetsheet"
REAL_XDG_DATA_HOME="$HOME/.local/share"
REAL_XDG_CONFIG_HOME="$HOME/.config"

# Ask the Background portal for permission to run on login, replacing
# the systemd user service used in the non-Flatpak install. First run
# surfaces a one-time consent dialog (xdg-desktop-portal-kde) - this is
# a real, visible UX change from the old silent `systemctl enable`, not
# a bug. Deliberately runs before the KWin script load below - see the
# race-condition note above.
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

echo "==> Installing/refreshing KWin active-window watcher script..."
KWIN_SCRIPT_DEST="$REAL_XDG_DATA_HOME/kwin/scripts/$KWIN_SCRIPT_ID"
rm -rf "$KWIN_SCRIPT_DEST"
mkdir -p "$(dirname "$KWIN_SCRIPT_DEST")"
cp -r "$APP_LIB/kwin-script" "$KWIN_SCRIPT_DEST"

# Persist Enabled=true into kwinrc for KWin's own benefit if it ever
# restarts independently - actual (re)loading is left entirely to the
# daemon's own startup logic, see the note above.
XDG_CONFIG_HOME="$REAL_XDG_CONFIG_HOME" kwriteconfig6 --file kwinrc --group Plugins --key "${KWIN_SCRIPT_ID}Enabled" true

echo "==> Starting daemon..."
export QT_QPA_PLATFORM=xcb
exec python3 "$APP_LIB/daemon/__main__.py"
