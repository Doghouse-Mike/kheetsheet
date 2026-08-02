# Flatpak port - status

Draft manifest + support files in this directory. Written on the Bazzite
box by inspecting the installed `org.kde.Platform//6.11` runtime directly
(via `find`/`bwrap`, not a full `flatpak-builder` build - that's not
installed here yet, only bare `flatpak`).

## Resolved since the last handoff

- **kpackagetool6, kwriteconfig6, qdbus are all present in
  `org.kde.Platform//6.11`** (confirmed by listing the runtime's `/bin`
  directly). `install.sh`'s KWin-script-install logic can run close to
  as-is inside the sandbox - no need to reimplement it in Python. Note
  the binary is named `qdbus`, not `qdbus6`/`qdbus-qt6` as install.sh's
  host-side dependency check looks for.
- **The runtime bundles Python 3.13** and the AT-SPI GObject typelib
  (`Atspi-2.0.typelib` + `libatspi.so.0`) already. PyQt6, dbus-python,
  and PyGObject still need to be added as build modules - draft module
  stanzas are in the manifest but use placeholder source hashes.
- Autostart: drafted using the Background portal
  (`org.freedesktop.portal.Background.RequestBackground`) from the
  wrapper script, replacing the systemd user service. This surfaces a
  one-time visible consent dialog on first run - a real UX change from
  the silent `systemctl enable`, not a bug to fix.

## Still open

1. No icon file yet - `icon-placeholder.svg` is a stand-in.
2. Pip module source hashes in the manifest are placeholders. Run
   `flatpak-pip-generator` (from the flatpak-builder tools repo) against
   `dbus-python`, `pygobject`, and `PyQt6` to get real, pinned entries.
3. PyQt6 module currently installs the PyPI binary wheel, which bundles
   its own private Qt6 rather than linking the runtime's - works, but
   duplicates what `org.kde.Platform` already ships and is the kind of
   thing Flathub reviewers ask about. Building from source with
   `sip-build` against the runtime's Qt6 avoids that at the cost of a
   much heavier module.
4. None of this has been run through actual `flatpak-builder` yet - only
   `flatpak` itself is installed, not `flatpak-builder` or `org.kde.Sdk`.
   Doing so is a multi-GB download, so it wasn't started without asking
   first.
5. The wrapper's Background-portal response handling
   (`gdbus monitor` + grep with a timeout) is a crude stand-in for
   properly waiting on the async `Request.Response` signal. Worth
   redoing in Python with `python-gi` once that's a confirmed-working
   build dependency anyway.

## Next concrete step

Install `flatpak-builder` + `org.kde.Sdk//6.11`, run
`flatpak-pip-generator` for the three Python deps, drop the real hashes
into the manifest, then `flatpak-builder --user --install` and iterate on
whatever actually fails.
