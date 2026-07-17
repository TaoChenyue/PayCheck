"""Theme management — Fusion-based dark/light mode with system detection.

Provides auto-detect for Windows (registry), macOS (defaults), and Linux (gsettings).
Persists user preference via the database settings table.
"""

import logging
import platform
import subprocess
from enum import Enum

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

log = logging.getLogger("paycheck.gui.theme")

_SETTING_KEY = "theme_mode"


class ThemeMode(Enum):
    LIGHT = "light"
    DARK = "dark"
    SYSTEM = "system"


# ── Dark palette built on Fusion defaults ─────────────────────────

def _build_dark_palette() -> QPalette:
    """Return a QPalette tuned for dark backgrounds with readable text."""
    p = QPalette()

    # Base colours — dark grey foundation
    p.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.WindowText, QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.Text, QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(240, 240, 240))
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.ColorRole.Link, QColor(100, 160, 255))
    p.setColor(QPalette.ColorRole.Highlight, QColor(100, 160, 255))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(240, 240, 240))

    # Disabled state
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText,
               QColor(128, 128, 128))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,
               QColor(128, 128, 128))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText,
               QColor(128, 128, 128))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText,
               QColor(128, 128, 128))

    return p


DARK_PALETTE: QPalette = _build_dark_palette()
"""Pre-built dark palette for Fusion style."""


def _fresh_light_palette() -> QPalette:
    """Return a clean Fusion-default palette (no overrides).

    Each call creates a new QPalette so that switching back from dark
    to light properly resets all color roles.
    """
    return QPalette()


# ── System detection ───────────────────────────────────────────────

def _detect_windows() -> str:
    """Read HKCU registry for Windows 10/11 dark-mode preference."""
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        )
        value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
        winreg.CloseKey(key)
        return "light" if value == 1 else "dark"
    except Exception:
        log.debug("Failed to read Windows theme registry", exc_info=True)
        return "light"


def _detect_macos() -> str:
    """Read macOS appearance via `defaults read`."""
    try:
        result = subprocess.run(
            ["defaults", "read", "-g", "AppleInterfaceStyle"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0 and "Dark" in result.stdout:
            return "dark"
        return "light"
    except Exception:
        log.debug("Failed to detect macOS theme", exc_info=True)
        return "light"


def _detect_linux() -> str:
    """Read GNOME / XFCE / KDE dark preference via gsettings."""
    try:
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
            capture_output=True, text=True, timeout=3,
        )
        if result.returncode == 0:
            theme_name = result.stdout.strip().strip("'").lower()
            return "dark" if "dark" in theme_name else "light"
    except Exception:
        log.debug("Failed to detect Linux theme", exc_info=True)
    return "light"


def detect_system_theme() -> str:
    """Return 'light' or 'dark' based on the OS-level setting."""
    system = platform.system()
    if system == "Windows":
        return _detect_windows()
    elif system == "Darwin":
        return _detect_macos()
    else:
        return _detect_linux()


# ── Theme manager ──────────────────────────────────────────────────

class ThemeManager:
    """Central theme controller for the PayCheck application.

    Usage::

        mgr = ThemeManager()
        mgr.apply(app)           # apply saved or system-default theme
        mgr.set_mode(app, ThemeMode.DARK)  # switch manually
    """

    def __init__(self) -> None:
        self._mode: ThemeMode = ThemeMode.SYSTEM

    # -- persistence -------------------------------------------------

    def save_preference(self, mode: ThemeMode) -> None:
        """Write the user's theme choice to the database."""
        from paycheck.storage.database import set_setting
        set_setting(_SETTING_KEY, mode.value)
        self._mode = mode

    def load_preference(self) -> ThemeMode:
        """Read the persisted theme choice (defaults to SYSTEM)."""
        from paycheck.storage.database import get_setting
        raw = get_setting(_SETTING_KEY, ThemeMode.SYSTEM.value)
        try:
            self._mode = ThemeMode(raw)
        except ValueError:
            self._mode = ThemeMode.SYSTEM
        return self._mode

    # -- apply -------------------------------------------------------

    def _resolve_mode(self, mode: ThemeMode | None = None) -> ThemeMode:
        """Resolve *mode* through SYSTEM → OS detection."""
        m = mode if mode is not None else self._mode
        if m == ThemeMode.SYSTEM:
            os_theme = detect_system_theme()
            return ThemeMode.DARK if os_theme == "dark" else ThemeMode.LIGHT
        return m

    def apply(self, app: QApplication, mode: ThemeMode | None = None) -> ThemeMode:
        """Apply the given (or saved) theme and return the *effective* mode.

        Must be called *after* ``QApplication`` is created but *before*
        the main window is shown.
        """
        effective = self._resolve_mode(mode)

        app.setStyle("Fusion")
        if effective == ThemeMode.DARK:
            app.setPalette(DARK_PALETTE)
        else:
            app.setPalette(_fresh_light_palette())

        log.info("Theme applied: %s (resolved=%s)", self._mode.value, effective.value)
        return effective

    def set_mode(self, app: QApplication, mode: ThemeMode) -> ThemeMode:
        """Switch to *mode*, persist it, and apply immediately.

        Returns the effective theme after resolving SYSTEM.
        """
        self.save_preference(mode)
        return self.apply(app, mode)

    @property
    def current_mode(self) -> ThemeMode:
        return self._mode
