
# KheetSheet

A KDE Plasma clone of the ([discontinued](https://www.mediaatelier.com/en/LandingCheatSheet/)) Mac app Cheatsheet.

The idea is that you press a hotkey, and see the focused app's keyboard shortcuts in an overlay, grouped by menu. Shortcut data comes entirely from AT-SPI (the accessibility tree) which has some limitations. If an app *doesn't* expose its menu via AT-SPI (many GTK4/Electron apps), you'll get a simple "no shortcuts found". I've not been able to find a workaround that wasn't super creepy or likely to serve stale data. Or both. Yet?

> I have an idea for Obsidian, but it'd mean accessing the vault to read custom & plugin keybinds and might not get anywhere.

Many GTK4 apps *do* institute their own version though, `CTRL+?` (Or `CTRL+SHIFT+/`) will bring up *their* native overlay.

A bit more on reasoning/thoughts without clogging this up any more than it already is can be found [here](https://28mm.coffee/kheetsheet)

## AI Disclosure

I, the human writing *this*, barely touched the actual code, that's all Clanker. If that grinds your gears, this may not be for you, but hopefully we can all move on with our lives.

## Screenshots

| Real shortcuts (Dolphin) | App with no AT-SPI menu (VS Code) |
| --- | --- |
| ![Overlay showing Dolphin's File and Edit shortcuts](screenshots/example-dolphin.png) | ![Overlay showing the honest "no shortcuts" message](screenshots/example-no-shortcuts.png) |

## Supported Systems

Any(?) KDE Plasma 6 desktop. I've only tested Kubuntu and Bazzite, installation may differ slightly for not those.

Distro-specific install steps:

- **Kubuntu / Debian / Ubuntu-based** — this page, you're here.
- **Bazzite / Fedora Atomic** — see [BAZZITE-README.md](BAZZITE-README.md). (*slightly* different steps)

## Install (Kubuntu/Debian/Ubuntu-based Plasma 6)

