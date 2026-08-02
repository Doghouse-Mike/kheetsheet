# Flatpak port - status

Draft manifest + support files in this directory, now built and run
end-to-end once against a real Flatpak (`flatpak-builder` +
`org.kde.Sdk//6.11`, both installed locally). It builds clean and
installs, but the daemon crashes on launch - see "Current blocker" below.

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
- Autostart: drafted using the Background portal
  (`org.freedesktop.portal.Background.RequestBackground`), replacing
  the systemd user service. The request call itself runs without
  erroring; whether the consent dialog actually surfaced and how the
  response-signal wait behaves hasn't been conclusively observed yet
  (see below) because the daemon crashes shortly after in the same run.

## Current blocker

The daemon fails to start with:

    ModuleNotFoundError: No module named 'dbus.mainloop.pyqt6'

`daemon/__main__.py` imports `dbus.mainloop.pyqt6.DBusQtMainLoop` to
integrate dbus-python's event dispatching into Qt's event loop. On this
host that module is a compiled extension
(`dbus/mainloop/pyqt6.abi3.so`) shipped by Fedora's `python3-pyqt6-base`
RPM - confirmed via `rpm -qf` against the actual file. It is **not**
part of the PyPI `PyQt6` wheel the manifest currently installs. Fedora
builds it themselves as part of PyQt6 packaging; it only gets built when
PyQt6 is compiled from source with dbus-python (and its dev headers)
already present - not from a prebuilt wheel.

Two real paths forward, both bigger than what's been done so far:

1. **Build PyQt6 from source** (`sip-build`/`pip install --no-binary`)
   against `org.kde.Sdk//6.11`'s Qt6 dev headers, with dbus-python
   installed first so PyQt6's own build detects it and compiles the
   `dbus.mainloop.pyqt6` glue extension. This also resolves the
   already-known "bundles its own private Qt6" issue from the earlier
   draft, since a from-source build links the runtime's Qt6 instead of
   vendoring PyPI's. Packaging-only fix, no application code changes,
   but a meaningfully heavier module (license-acknowledgement flags,
   full qtbase/qtsvg/qtdeclarative etc. dev headers, longer build).
2. **Change the daemon's D-Bus/mainloop integration** to not depend on
   this Fedora-specific glue at all - e.g. a GLib mainloop (PyGObject is
   already a build dependency) bridged into Qt's event loop, or PyQt6's
   own native `QtDBus` API instead of dbus-python. This touches actual
   application source (`daemon/__main__.py`), not just packaging, and
   would need to work correctly for the existing non-Flatpak install
   path too - not something to decide unilaterally mid-packaging-spike.

Stopped here to ask which direction to take rather than guessing.

## Still open (unchanged from before)

- No icon file yet - `icon-placeholder.svg` is a stand-in.
- The `kheetsheet` app module's source is `type: dir, path: ..`, which
  only works because local builds were run *without* `--sandbox`.
  Flathub's real build pipeline requires `--sandbox`, which forbids
  `..` traversal outside the manifest's own directory - confirmed by
  hitting exactly that error locally. Before submission this needs to
  become a `type: git` source pointing at the pushed GitHub repo at a
  specific commit, once these flatpak/ files are actually on
  `origin/main`.
- The three pip build modules (`dbus-python`, `pycairo`, `pygobject`)
  currently build with `--share=network` (to let pip fetch their
  meson-python build backend), which Flathub review will reject.
  Before submission, replace with fully vendored build-backend sources
  (the normal job of `flatpak-pip-generator`, deliberately not used
  here - see the manifest's own comments for why) or confirm nothing
  else gets fetched and vendor just those.
- The wrapper's Background-portal response handling (`gdbus monitor` +
  grep with a timeout) is unverified in practice - the daemon crashed
  before that path could be observed end-to-end in this run.
