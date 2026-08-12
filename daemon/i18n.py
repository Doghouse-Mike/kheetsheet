import gettext
import os

# locale/ is a sibling of daemon/ in both deployments this app ships as:
# the native install runs daemon/ in place from the git checkout, and the
# Flatpak build installs daemon/ under /app/lib/kheetsheet/daemon - so a
# path relative to this file resolves correctly either way.
_LOCALE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "locale")

_ = gettext.translation("kheetsheet", localedir=_LOCALE_DIR, fallback=True).gettext
