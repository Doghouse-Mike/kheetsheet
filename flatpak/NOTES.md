
# Flatpak Port - Status

**Works end-to-end, verified functionally, not just "process didn't crash."** `flatpak-builder` builds the manifest with no build-time network access, `flatpak run io.github.DoghouseMike.KheetSheet` starts the daemon cleanly, and the running app correctly tracks real window-focus changes and renders the right app's shortcuts in the overlay - confirmed with screenshots against real focus changes (Konsole, Dolphin, Kate), not just D-Bus return values.

## The Real Bug (Found after a lOng iNvestigation)

Early Flatpak builds had the daemon start fine and answer D-Bus calls, but the overlay would eventually show stale or wrong info - stuck on whatever app was focused at some earlier point, not updating on real focus changes. `org.kde.kwin.Scripting.isScriptLoaded("kheetsheet-activewindow")` would report `false` sometime after every launch, with no error anywhere in any log.

Seven separate hypotheses were tested and ruled out before finding the real cause: stacked/overlapping test instances left running from earlier tests, a race between the daemon starting and the KWin script's immediate self-report firing before the daemon existed, a missing `kwinrc` `Enabled` flag, a plain KWin scripting-API quirk (disproven - the identical load sequence run standalone on the host stayed stable for a full 2 minutes), a double-load race between the wrapper's own script-loading and the daemon's own independent script-loading, deferring the daemon's load past `app.exec()` via `QTimer.singleShot`, and using one-shot `qdbus` subprocess calls instead of the daemon's persistent dbus-python connection.

**Actual cause**: `daemon/service.py`'s `ensure_kwin_script_loaded()` computed the KWin script's file path from `os.environ["XDG_DATA_HOME"]`. Inside the Flatpak sandbox, that env var is redirected to this app's private `~/.var/app/<id>/data` - not the real host path the --filesystem=xdg-data/kwin:create` grant exposes, which is where the wrapper actually copies the script files. `loadScript()` on that nonexistent path returned a valid-looking id, and `start()` didn't error either - it just silently loaded nothing. That's what looked like the script "mysteriously" going unloaded sometime after every launch: the daemon's own startup call was never loading real code in the first place, on Flatpak specifically, every single time.

Confirmed by adding temporary diagnostic prints to see the actual computed path (`/home/mike/.var/app/io.github.DoghouseMike.KheetSheet/data/kwin/scripts/...`) before the daemon's own D-Bus calls - not inferred, directly observed.

**Fix** in `daemon/service.py`: detect `/.flatpak-info` (the standard way to detect running inside a Flatpak sandbox) and use `$HOME/.local/share` directly in that case, exactly like the wrapper script already does for its own file-copy step. Verified stable over repeated launches, extended idle periods (60s+), and multiple real window-focus changes with screenshot confirmation.

Also simplified while investigating: the wrapper no longer calls `loadScript`/`start`/`reconfigure` itself at all - `ensure_kwin_script_loaded()` in `service.py` already does that once, reliably, at the daemon's own startup (that's its whole reason for existing - KWin doesn't reliably auto-load an enabled script on its own). Having both the wrapper and the daemon each independently do it was pure duplication; this wasn't actually the bug, but there's no reason to keep it once the real fix landed. The wrapper still copies the script files (kpackagetool6 doesn't work in-sandbox - see below) and persists `kwinrc`'s `Enabled` flag for KWin's own benefit if it ever restarts independently.

## Other Resolved Issues

- **kpackagetool6, kwriteconfig6, qdbus are present in
  `org.kde.Platform//6.11`**, but `kpackagetool6`'s "KWin/Script"
  package-structure *plugin* is not - that ships as part of KWin itself
  (the host compositor package), not the generic runtime. Fixed by
  skipping kpackagetool6 entirely and `cp -r`-ing the script directory
  directly - a KWin script is just files, no validate/compile step.
- **App ID had to change**: `io.github.Doghouse-Mike.KheetSheet` is
  invalid - Flatpak only allows hyphens in an app ID's *last* segment.
  Renamed throughout to `io.github.DoghouseMike.KheetSheet`.
- **`dbus.mainloop.pyqt6` missing from the PyPI `PyQt6` wheel.** That module (bridges dbus-python's event dispatching into Qt's event loop) is a compiled extension Fedora builds themselves as part of PyQt6 packaging, not part of the plain PyPI wheel. Fixed by building PyQt6 from source against `org.kde.Sdk//6.11`'s own Qt6 (with dbus-python present so PyQt6's own build compiles the glue extension), which also resolved the earlier "bundles its own private Qt6" concern for free. `--no-designer-plugin --no-qml-plugin --no-tools` avoid those pieces trying to install into the read-only SDK mount under `/usr`.
- **No build-time network access needed.** dbus-python, pycairo,
  pygobject, and PyQt6's own build tools (`sip`, `PyQt-builder`) all
  declare PEP517/setuptools_scm build backends that aren't present in
  `org.kde.Sdk` by default (`meson-python`, `pyproject-metadata`,
  `setuptools_scm`, `vcs-versioning`) plus `patchelf` (meson-python's
  wheel-building step unconditionally shells out to it to fix RPATHs -
  confirmed by hitting `FileNotFoundError: patchelf` directly, not
  guessed). All vendored as explicit pinned sources (fetched from PyPI's JSON API, not `flatpak-pip-generator`) rather than using
  `--share=network`.

## Also Resolved

- **Switched the app module's source to `type: git`.** The previous
  `type: dir, path: ..` only worked for local builds run *without*
  `--sandbox` - Flathub's real build pipeline always uses `--sandbox`,
  which forbids `..` traversal outside the manifest's own directory,
  confirmed by hitting exactly that error locally. `url` is a local
  `file://` path for now since nothing here is pushed to `origin/main`
  yet - swap for the real `https://github.com/Doghouse-Mike/kheetsheet.git` URL once it is. Verified the full manifest builds, installs, and runs correctly under `--sandbox`.
- **Validated `metainfo.xml`** with `appstreamcli validate` - passed
  clean after adding a `<developer>` element (was flagged as
  `developer-info-missing`, an info-level note but one Flathub review
  does check for). The separate "No appstream data for app/... -
  /files/share/app-info" warning that appears during local
  `flatpak-builder --install` runs is unrelated to metainfo.xml
  validity - it's about a composed AppStream catalog cache that
  Flathub's own CI generates at the repo level, not something an
  individual app build needs to embed itself.

## Also Resolved

- **Real icon added.** `io.github.DoghouseMike.KheetSheet.svg` (a
  monogram merging the K and the ⌘-style shortcut glyph) replaces
  `icon-placeholder.svg`, installed to the same
  `hicolor/scalable/apps/` path. Rendered clean with ImageMagick
  (`convert -background none ... -resize 256x256`) as a sanity check -
  no XML/rendering errors.

## Still Open

- PyQt6 built from source pulls in a lot of Qt6 addon modules
  (QtMultimedia, QtBluetooth, QtNfc, etc.) that KheetSheet doesn't use, because `org.kde.Sdk` has dev headers for most of them and
  PyQt-builder builds whatever it can find headers for. Not wrong, just
  bigger than strictly necessary.
- The kwin-script filesystem grant, kwinrc filesystem grant, KWin D-Bus talk-name, and Background portal permission are what a Flathub reviewer will ask to be justified - all now demonstrably necessary (not just assumed necessary), which makes that conversation easier.

## Two More Real Bugs Found and Fixed (2026-08-03)

- **Stale commit pin.** The `kheetsheet` module's git source was still
  pinned to `15b4b98`, from before the real icon was added - a build
  against that commit checked out a tree missing
  `io.github.DoghouseMike.KheetSheet.svg` entirely and failed on the
  icon install step with `install: cannot stat ...`.
- **Desktop/metainfo/icon silently never installed, in every prior
  build.** The three `install -Dm644 ... \` build-commands used a YAML multi-line plain scalar with a trailing shell-style `\` continuation. YAML block-scalar folding already joins those lines with a single space - it doesn't treat `\` as a continuation character at all, so the shell actually received `... .desktop \ /app/share/...`. Bash's `\ ` (backslash-space) escapes the space *into* the argument instead of splitting on it, so the destination argument became
  `" /app/share/applications/..."` - a relative path starting with a
  literal space character, not an absolute `/app/...` path. Every build
  to date silently created a bogus `" /app/share/..."` directory tree
  instead of installing to the real app tree. No error was ever
  surfaced - `install -D` happily creates whatever destination path
  it's given. Confirmed directly by inspecting `.flatpak-builder/build/kheetsheet-*/` and finding a literal space-named directory containing `app/share/applications/...` etc. Fixed by collapsing each command onto one line (no continuation
  needed - YAML already folds the two source lines with a space).

  Practical effect: the desktop entry, AppStream metainfo, and icon had never actually worked in any Flatpak build of this app, despite the earlier "real icon added" and "metainfo.xml validated" notes above - those were true of the *source files*, not of what actually landed in the built app. Verified the fix with a full rebuild: `appstreamcli compose` now finds and composes the component (previously logged "No appstream data" and silently skipped it), and the desktop file, metainfo, and generated PNG icons (48/64/128px + @2x) all appear under the installed app's `files/share/`.

- **`url` swapped to the real GitHub URL.** Now
  `https://github.com/Doghouse-Mike/kheetsheet.git`, still pinned to
  `e0887868fbf033da1af579dc6384cd6cb83a2250` (the icon commit - the tw bug-fix commits above only touch the manifest file itself, which
  `flatpak-builder` reads directly off disk, not through the git
  source, so the pin didn't need to move again). Verified with a full
  `--sandbox` build that actually clones over HTTPS from GitHub.

## App ID Rename, Metainfo Screenshots, and a Real Tagged Release (2026-08-03)

Three more Flathub-readiness gaps closed, everything below is pushed to origin/main` and verified with a full `--sandbox` build against the real GitHub source:

- **App ID renamed to `coffee._28mm.KheetSheet`.**
  `io.github.DoghouseMike.KheetSheet` relied on `io.github`'s ownership
  verification, which checks the ID's last-but-one segment against the
  GitHub username - but the real username is `Doghouse-Mike` (with a
  hyphen), which Flatpak IDs don't allow outside the last segment, so
  that verification path can never succeed as-is. Rooted the ID at
  `28mm.coffee` instead, a domain actually owned. Flathub's own naming rules (their own example: `7-zip.org` -> `org._7_zip`) prefix a
  component starting with a digit with an underscore, so the reverse-DNS `coffee.28mm` becomes `coffee._28mm`. To be verified later via
  Flathub's website method (a token file at
  `https://28mm.coffee/.well-known/org.flathub.VerifiedApps.txt`) once the app is actually submitted and a token is issued - that step can't happen before submission.

  Renamed the manifest, desktop file, metainfo, and icon accordingly (all four files renamed, not just their `id:`/`<id>` fields), and updated the AppStream `<developer id>` to match. Verified with a full rebuild + local install + confirmed the daemon still loads its KWin script correctly under the new ID.

  Hit two unrelated environment issues while re-verifying this (not manifest bugs): PyQt6 has to rebuild fully from source whenever the manifest's own filename changes (it's part of the module cache key), which takes over 30 minutes - don't `--force-clean` away a build that's mid-way through it, and give it a long enough timeout to actually finish. Separately, `rofiles-fuse` started intermittently failing with `Permission denied` on its own mountpoint partway through a run (looked like a race with a systemd-managed transient automount unit reusing the same path) - `--disable-rofiles-fuse` sidesteps it by falling back to plain copying instead of FUSE, no functional downside for this build.

- **Added `<screenshots>` to the metainfo.** There were none before -
  Flathub's store listing reads screenshots from the metainfo itself,
  separate from the README's images. Added the three per-app stills
  (Konsole/Dolphin/Kate), pointed at stable `raw.githubusercontent.com` URLs pinned to the `v0.1.0` tag (below) rather than `main`, so they can't silently change or disappear later.

- **Cut a real tagged release, `v0.1.0`.** The `<release>` entry was a
  literal `PLACEHOLDER` comment before, with no matching git tag at all
  (`git tag -l` was empty). Tagged and pushed `v0.1.0` at the tip of
  `main` (the app-ID rename + GitHub-source-URL commits), updated the metainfo `<release>` to match, and confirmed via the GitHub API that the tag's tree actually contains the screenshot files referenced above (the `raw.githubusercontent.com` URLs may take a few minutes to reflect a brand-new tag even after the API confirms it - a CDN propagation delay, not a real problem).

## Next Concrete Step

Submission itself (forking `flathub/flathub`, requesting the app ID, and the website ownership-verification step that depends on it) is the one remaining piece, and has to be done by hand - not something to script. Optional, size-only cleanup that isn't a blocker: trim the PyQt6 module's `--enable=` allowlist (see "Still open" above).
