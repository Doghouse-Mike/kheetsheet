# Installing KheetSheet on Bazzite

**Status: unverified.** This was written without access to an actual Bazzite
machine — it's a best-effort translation of the Kubuntu install steps to
Fedora/rpm-ostree conventions, not something that's been run. Treat the
package names below as a starting guess, not a fact; verify each one before
trusting it, and update this doc (or ask for it to be updated) once tested on
the real machine.

## Why this needs a separate guide

Bazzite is built on Fedora Atomic (rpm-ostree) — the base OS image is
immutable, so `dnf install` doesn't work the way `apt install` does on
Kubuntu. Persistent system packages have to be *layered* onto the image with
`rpm-ostree install`, which requires a reboot to take effect. Fedora's package
names also don't all match Debian/Ubuntu's — same underlying software,
different names.

Everything else about KheetSheet (the daemon, the KWin script, `install.sh`,
the manual shortcut-binding step) is standard KDE Plasma machinery, not
Kubuntu-specific — none of that should need to change for Bazzite.

## 1. Install dependencies (layered, requires reboot)

Best-guess Fedora package names for the same dependencies documented in
`README.md`:

```
rpm-ostree install python3-pyqt6 python3-dbus python3-gobject \
    at-spi2-core kf6-kpackage kf6-kconfig qt6-qttools
```

Then reboot for the layered packages to take effect:

```
systemctl reboot
```

Notes on individual packages, ranked by how confident this guess is:

- `python3-pyqt6`, `python3-dbus` — fairly confident; Fedora tends to keep
  these names close to upstream.
- `python3-gobject` — this is the one place Fedora's naming is known to
  diverge from Debian: Debian calls it `python3-gi`, Fedora calls the same
  thing `python3-gobject`.
- `at-spi2-core` — should provide the AT-SPI GObject-introspection typelib
  that Debian ships separately as `gir1.2-atspi-2.0`; on most Fedora desktop
  spins this is already installed as a base accessibility component, so this
  may turn out to be a no-op.
- `kf6-kpackage`, `kf6-kconfig` — guesses at the packages providing
  `kpackagetool6` and `kwriteconfig6`/`kreadconfig6` respectively, following
  Fedora's `kf6-*` naming convention for KDE Frameworks 6 packages. Not
  verified.
- `qt6-qttools` — guess at the package providing `qdbus6`.
- **`python3-dbus.mainloop.pyqt6` has no listed equivalent** — this Debian
  package provides the Qt/D-Bus mainloop glue the daemon imports
  (`dbus.mainloop.pyqt6`, used in `daemon/__main__.py`). Whether Fedora ships
  this as part of `python3-dbus` or `python3-pyqt6`, as a separate package, or
  not at all (in which case it'd need to come from `pip`) is unknown from
  here — this is the dependency most likely to cause `install.sh` to still
  report something missing after the `rpm-ostree install` above.

## 2. Run the installer

Same as Kubuntu — nothing distro-specific in the script itself:

```
./install.sh
```

If it reports a missing dependency, that means the guess above was wrong for
that one. Find the real package with:

```
dnf provides '*/<missing-binary-or-file>'
```

e.g. `dnf provides '*/kwriteconfig6'` to find whatever package actually ships
that binary on Bazzite, then `rpm-ostree install` it and reboot again.

## 3. Bind the global shortcut

Identical manual step to the Kubuntu install — System Settings → Shortcuts →
Add New → Command or Script. See `README.md`'s Install section for the exact
command to bind. This part of `kglobalaccel` is Plasma-level, not
distro-specific, so it should behave the same here.

## Things worth checking specifically on Bazzite

- **SELinux vs AppArmor.** The Kubuntu install found that AppArmor blocked one
  snap-confined app (VS Code) from querying another snap's (Vivaldi's)
  AT-SPI tree — this didn't affect KheetSheet's own use case, but SELinux
  (enabled by default on Fedora/Bazzite) enforces differently and hasn't been
  checked against this daemon's AT-SPI queries at all.
- **Flatpak sandboxing.** Bazzite leans heavily on Flatpak for user apps
  (browsers, etc., often not available any other way). Flatpak's sandboxing
  of the accessibility bus is a real open question — it may behave like the
  snap confinement case (some apps blocked from exposing/querying AT-SPI
  data), or it may be stricter, or looser. Worth testing against a few
  representative Flatpak apps early rather than assuming parity with the
  Kubuntu findings.
- **`QT_QPA_PLATFORM=xcb` requirement.** The daemon's systemd unit forces this
  because native Qt-Wayland windows didn't honor always-on-top/positioning
  under KWin on Kubuntu. Bazzite also runs Plasma on Wayland by default, so
  this should still apply — but worth confirming XWayland is available and
  working out of the box (it should be, but hasn't been checked here).
