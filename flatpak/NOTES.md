# Flatpak port - status

**It works end-to-end now.** `flatpak-builder` builds the manifest clean,
`flatpak run io.github.DoghouseMike.KheetSheet` starts the daemon with no
crash, the KWin script lands in the real host
`~/.local/share/kwin/scripts/` (not the sandboxed one), and the running
app answers `com.kheetsheet.Daemon.Toggle` over D-Bus exactly like the
native systemd install does - confirmed by actually calling it twice via
`gdbus call` against the running flatpak instance, not just checking that
the process stayed alive.

## Resolved so far

- **kpackagetool6, kwriteconfig6, qdbus are present in
  `org.kde.Platform//6.11`** - but see the kpackagetool6 finding below;
  presence of the binary wasn't the whole story.
- **The KWin/Script kpackagetool6 install doesn't work inside the
  sandbox**, even though the binary is there: `kpackagetool6`'s
  "KWin/Script" package-structure *plugin* ships as part of KWin itself
  (the host compositor package), not the generic `org.kde.Platform`
  runtime. Fix: skip kpackagetool6 entirely and `cp -r` the script
  directory directly into `$HOME/.local/share/kwin/scripts/<id>` -  a
  KWin script is just files, no compile/validate step needed. Also
  dropped the kwriteconfig6 `kwinrc` persistence step (would need a
  third non-default permission for an edge case the per-launch
  loadScript+start D-Bus calls already cover - see the wrapper script's
  own comments for the reasoning).
- **The runtime bundles Python 3.13** and the AT-SPI GObject typelib
  already. dbus-python, pycairo, and PyGObject build fine as source
  modules against `org.kde.Sdk//6.11`'s bundled meson/ninja/gcc and
  pkg-config files for dbus-1/glib-2.0/cairo/gobject-introspection -
  confirmed by an actual successful build, not just header presence.
  Real pinned sources (fetched from PyPI's JSON API directly, sha256
  included) are in the manifest now, replacing the placeholder hashes.
- **App ID had to change**: `io.github.Doghouse-Mike.KheetSheet` is
  invalid - Flatpak only allows hyphens in an app ID's *last* segment.
  Renamed throughout to `io.github.DoghouseMike.KheetSheet`.
- **Fixed: `dbus.mainloop.pyqt6` missing from the PyPI `PyQt6` wheel.**
  That module (bridges dbus-python's event dispatching into Qt's event
  loop, imported by `daemon/__main__.py`) is a compiled extension Fedora
  builds themselves as part of PyQt6 packaging - not part of the plain
  PyPI wheel. Fixed by building PyQt6 from source against
  `org.kde.Sdk//6.11`'s own Qt6 instead of installing the prebuilt wheel:
    - `sip` + `PyQt-builder` (the build-time tools, unrelated to the
      `PyQt6-sip` runtime module which stays a binary wheel) get
      installed to a throwaway prefix so their console scripts are on
      PATH only for this module's build.
    - `sip-build --dbus=<dir>` points at dbus-python's header (installed
      to a non-standard path by its own PyPI wheel - not found by the
      default pkg-config search PyQt6's own build does for libdbus).
    - Turns out `org.kde.Sdk` carries dev headers for nearly all of
      Qt6's addon modules, not just qtbase - PyQt-builder auto-skips any
      submodule whose headers are missing, so this ended up building
      most of PyQt6 rather than just Core/Gui/Widgets/DBus, confirmed by
      an actual build rather than assumed.
    - Building from source also resolved the earlier "bundles its own
      private Qt6" concern for free - it now links the runtime's Qt6
      instead of vendoring PyPI's.
    - Two more real bugs found along the way, both the same shape: the
      Designer/qmlscene plugins and the pyuic6/pylupdate6 tool scripts
      each tried installing into paths under Qt's own prefix (`/usr`'s
      plugin dir, then `/usr/bin`) rather than `$FLATPAK_DEST` - and
      `/usr` is the read-only `org.kde.Sdk` mount in the build sandbox.
      Fixed with `--no-designer-plugin --no-qml-plugin --no-tools`
      (none of those apply to a headless daemon anyway).
    - One more: `make install`'s last step shells out to `sip-distinfo`
      internally, which needs the same PATH/PYTHONPATH override as the
      `sip-build` invocation itself - each `build-commands` list entry
      runs as its own separate shell, so setting env vars in one entry
      doesn't carry to the next.
- Autostart: drafted using the Background portal
  (`org.freedesktop.portal.Background.RequestBackground`). The request
  call runs without erroring on every observed run, but whether a
  consent dialog actually surfaced on screen, and whether the
  `gdbus monitor`-based response wait behaves correctly, still hasn't
  been conclusively confirmed - the runs so far all moved past that step
  within its timeout without visible incident, but that's not the same
  as having watched the dialog appear and clicked it.

## Still open

- No icon file yet - `icon-placeholder.svg` is a stand-in.
- The `kheetsheet` app module's source is `type: dir, path: ..`, which
  only works because local builds were run *without* `--sandbox`.
  Flathub's real build pipeline requires `--sandbox`, which forbids
  `..` traversal outside the manifest's own directory - confirmed by
  hitting exactly that error locally. Before submission this needs to
  become a `type: git` source pointing at the pushed GitHub repo at a
  specific commit, once these flatpak/ files are actually on
  `origin/main`.
- The four pip/sip build modules (`dbus-python`, `pycairo`, `pygobject`,
  `python3-pyqt6`) build with `--share=network` (to let pip/sip-build
  fetch their meson-python/PyQt-builder build backends), which Flathub
  review will reject. Before submission, replace with fully vendored
  build-backend sources (the normal job of `flatpak-pip-generator`,
  deliberately not used here - see the manifest's own comments for why)
  or confirm nothing else gets fetched and vendor just those.
- PyQt6 built from source pulls in a lot of Qt6 addon modules
  (QtMultimedia, QtBluetooth, QtNfc, etc.) that KheetSheet doesn't use,
  because `org.kde.Sdk` has dev headers for most of them and
  PyQt-builder builds whatever it can find headers for. Not wrong, just
  bigger than strictly necessary - worth an explicit `--enable=` allowlist
  (Core/Gui/Widgets/DBus only) if final package size matters.
- No appstream data warning during export
  (`No appstream data for app/... /files/share/app-info`) - cosmetic for
  local testing, but Flathub requires valid appstream; the
  `metainfo.xml` drafted here hasn't been validated with
  `appstream-util` or run through `appstreamcli compose`.
- The kwin-script filesystem grant, KWin D-Bus talk-name, and Background
  portal permission are the three things a Flathub reviewer will ask to
  be justified - all three now demonstrably necessary (not just assumed
  necessary), which makes that conversation easier.

## Next concrete step

Decide whether to keep iterating toward a Flathub-submittable manifest
(vendor the build-time network fetches, switch to a `type: git` source,
validate appstream, maybe trim the PyQt6 module list) or consider this
spike's goal - proving the whole thing can actually run - met, and treat
the rest as follow-up work.
