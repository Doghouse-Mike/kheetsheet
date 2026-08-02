# Flatpak port - status

**Works end-to-end, verified functionally, not just "process didn't
crash."** `flatpak-builder` builds the manifest with no build-time network
access, `flatpak run io.github.DoghouseMike.KheetSheet` starts the daemon
cleanly, and the running app correctly tracks real window-focus changes
and renders the right app's shortcuts in the overlay - confirmed with
screenshots against real focus changes (Konsole, Dolphin, Kate), not just
D-Bus return values.

## The real bug (found after a long investigation)

Early Flatpak builds had the daemon start fine and answer D-Bus calls,
but the overlay would eventually show stale or wrong info - stuck on
whatever app was focused at some earlier point, not updating on real
focus changes. `org.kde.kwin.Scripting.isScriptLoaded("kheetsheet-activewindow")`
would report `false` sometime after every launch, with no error anywhere
in any log.

Seven separate hypotheses were tested and ruled out empirically before
finding the real cause: stacked/overlapping test instances left running
from earlier tests, a race between the daemon starting and the KWin
script's immediate self-report firing before the daemon existed, a
missing `kwinrc` `Enabled` flag, a plain KWin scripting-API quirk
(disproven - the identical load sequence run standalone on the host
stayed stable for a full 2 minutes), a double-load race between the
wrapper's own script-loading and the daemon's own independent
script-loading, deferring the daemon's load past `app.exec()` via
`QTimer.singleShot`, and using one-shot `qdbus` subprocess calls instead
of the daemon's persistent dbus-python connection.

**Actual cause**: `daemon/service.py`'s `ensure_kwin_script_loaded()`
computed the KWin script's file path from `os.environ["XDG_DATA_HOME"]`.
Inside the Flatpak sandbox, that env var is redirected to this app's
private `~/.var/app/<id>/data` - not the real host path the
`--filesystem=xdg-data/kwin:create` grant exposes, which is where the
wrapper actually copies the script files. `loadScript()` on that
nonexistent path returned a valid-looking id, and `start()` didn't error
either - it just silently loaded nothing. That's what looked like the
script "mysteriously" going unloaded sometime after every launch: the
daemon's own startup call was never loading real code in the first
place, on Flatpak specifically, every single time.

Confirmed by adding temporary diagnostic prints to see the actual
computed path (`/home/mike/.var/app/io.github.DoghouseMike.KheetSheet/data/kwin/scripts/...`)
before the daemon's own D-Bus calls - not inferred, directly observed.

**Fix** in `daemon/service.py`: detect `/.flatpak-info` (the standard way
to detect running inside a Flatpak sandbox) and use `$HOME/.local/share`
directly in that case, exactly like the wrapper script already does for
its own file-copy step. Verified stable over repeated launches, extended
idle periods (60s+), and multiple real window-focus changes with
screenshot confirmation.

Also simplified while investigating: the wrapper no longer calls
`loadScript`/`start`/`reconfigure` itself at all - `ensure_kwin_script_loaded()`
in `service.py` already does that once, reliably, at the daemon's own
startup (that's its whole reason for existing - KWin doesn't reliably
auto-load an enabled script on its own). Having both the wrapper and the
daemon each independently do it was pure duplication; this wasn't
actually the bug, but there's no reason to keep it once the real fix
landed. The wrapper still copies the script files (kpackagetool6 doesn't
work in-sandbox - see below) and persists `kwinrc`'s `Enabled` flag for
KWin's own benefit if it ever restarts independently.

## Other resolved issues

- **kpackagetool6, kwriteconfig6, qdbus are present in
  `org.kde.Platform//6.11`**, but `kpackagetool6`'s "KWin/Script"
  package-structure *plugin* is not - that ships as part of KWin itself
  (the host compositor package), not the generic runtime. Fixed by
  skipping kpackagetool6 entirely and `cp -r`-ing the script directory
  directly - a KWin script is just files, no validate/compile step.
- **App ID had to change**: `io.github.Doghouse-Mike.KheetSheet` is
  invalid - Flatpak only allows hyphens in an app ID's *last* segment.
  Renamed throughout to `io.github.DoghouseMike.KheetSheet`.
- **`dbus.mainloop.pyqt6` missing from the PyPI `PyQt6` wheel.** That
  module (bridges dbus-python's event dispatching into Qt's event loop)
  is a compiled extension Fedora builds themselves as part of PyQt6
  packaging, not part of the plain PyPI wheel. Fixed by building PyQt6
  from source against `org.kde.Sdk//6.11`'s own Qt6 (with dbus-python
  present so PyQt6's own build compiles the glue extension), which also
  resolved the earlier "bundles its own private Qt6" concern for free.
  `--no-designer-plugin --no-qml-plugin --no-tools` avoid those pieces
  trying to install into the read-only SDK mount under `/usr`.
- **No build-time network access needed.** dbus-python, pycairo,
  pygobject, and PyQt6's own build tools (`sip`, `PyQt-builder`) all
  declare PEP517/setuptools_scm build backends that aren't present in
  `org.kde.Sdk` by default (`meson-python`, `pyproject-metadata`,
  `setuptools_scm`, `vcs-versioning`) plus `patchelf` (meson-python's
  wheel-building step unconditionally shells out to it to fix RPATHs -
  confirmed by hitting `FileNotFoundError: patchelf` directly, not
  guessed). All vendored as explicit pinned sources (fetched from PyPI's
  JSON API, not `flatpak-pip-generator`) rather than using
  `--share=network`.

## Still open

- No icon file yet - `icon-placeholder.svg` is a stand-in.
- The `kheetsheet` app module's source is `type: dir, path: ..`, which
  only works because local builds were run *without* `--sandbox`.
  Flathub's real build pipeline requires `--sandbox`, which forbids `..`
  traversal outside the manifest's own directory - confirmed by hitting
  exactly that error locally. Before submission this needs to become a
  `type: git` source pointing at the pushed GitHub repo at a specific
  commit, once these flatpak/ files are actually on `origin/main`.
- PyQt6 built from source pulls in a lot of Qt6 addon modules
  (QtMultimedia, QtBluetooth, QtNfc, etc.) that KheetSheet doesn't use,
  because `org.kde.Sdk` has dev headers for most of them and
  PyQt-builder builds whatever it can find headers for. Not wrong, just
  bigger than strictly necessary.
- No appstream data warning during export (cosmetic for local testing,
  but Flathub requires valid appstream) - `metainfo.xml` hasn't been
  validated with `appstream-util`/`appstreamcli compose`.
- The kwin-script filesystem grant, kwinrc filesystem grant, KWin D-Bus
  talk-name, and Background portal permission are what a Flathub
  reviewer will ask to be justified - all now demonstrably necessary
  (not just assumed necessary), which makes that conversation easier.

## Next concrete step

Switch the app module to a `type: git` source and test with `--sandbox`
(Flathub's actual build mode), then validate appstream metadata.
