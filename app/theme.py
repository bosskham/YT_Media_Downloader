from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

# ── Catppuccin Mocha (dark) ──────────────────────────────────────────────────
DARK: dict[str, str] = {
    "bg":          "#1e1e2e",
    "bg2":         "#181825",
    "surface":     "#313244",
    "surface2":    "#45475a",
    "border":      "#585b70",
    "text":        "#cdd6f4",
    "text2":       "#a6adc8",
    "text_muted":  "#6c7086",
    "accent":      "#89b4fa",
    "accent_hover":"#b4befe",
    "success":     "#a6e3a1",
    "warning":     "#f9e2af",
    "error":       "#f38ba8",
    "peach":       "#fab387",
    "mauve":       "#cba6f7",
}

# ── Clean Light ──────────────────────────────────────────────────────────────
LIGHT: dict[str, str] = {
    "bg":          "#eff1f5",
    "bg2":         "#e6e9ef",
    "surface":     "#ffffff",
    "surface2":    "#dce0e8",
    "border":      "#ccd0da",
    "text":        "#4c4f69",
    "text2":       "#5c5f77",
    "text_muted":  "#9ca0b0",
    "accent":      "#1e66f5",
    "accent_hover":"#04a5e5",
    "success":     "#40a02b",
    "warning":     "#df8e1d",
    "error":       "#d20f39",
    "peach":       "#fe640b",
    "mauve":       "#8839ef",
}


def build_stylesheet(c: dict) -> str:
    return f"""
/* ── Base ───────────────────────────────────────────── */
QMainWindow, QDialog {{
    background-color: {c['bg']};
}}
QWidget {{
    background-color: transparent;
    color: {c['text']};
    font-family: "Segoe UI", "SF Pro Display", Arial, sans-serif;
    font-size: 13px;
}}
QScrollArea, QScrollArea > QWidget > QWidget {{
    background-color: transparent;
    border: none;
}}

/* ── Buttons ────────────────────────────────────────── */
QPushButton {{
    background-color: {c['accent']};
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 600;
    font-size: 13px;
    min-height: 36px;
}}
QPushButton:hover    {{ background-color: {c['accent_hover']}; }}
QPushButton:pressed  {{ background-color: {c['accent']}; }}
QPushButton:disabled {{ background-color: {c['surface2']}; color: {c['text_muted']}; }}

QPushButton[role="secondary"] {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
}}
QPushButton[role="secondary"]:hover  {{ background-color: {c['surface2']}; }}
QPushButton[role="secondary"]:checked {{
    background-color: {c['accent']};
    color: #ffffff;
    border: 1px solid {c['accent']};
}}

QPushButton[role="danger"] {{
    background-color: {c['error']};
    color: #ffffff;
}}
QPushButton[role="danger"]:hover {{ opacity: 0.85; }}

QPushButton[role="icon"] {{
    background-color: transparent;
    color: {c['text2']};
    border: none;
    border-radius: 8px;
    padding: 6px 8px;
    min-height: 32px;
    min-width: 32px;
    font-size: 16px;
}}
QPushButton[role="icon"]:hover {{
    background-color: {c['surface2']};
    color: {c['text']};
}}

QPushButton[role="nav"] {{
    background-color: transparent;
    color: {c['text_muted']};
    border: none;
    border-radius: 20px;
    padding: 6px 20px;
    font-weight: 600;
    font-size: 13px;
    min-height: 34px;
}}
QPushButton[role="nav"]:hover   {{ background-color: {c['surface']}; color: {c['text']}; }}
QPushButton[role="nav"]:checked {{
    background-color: {c['accent']};
    color: #ffffff;
}}

/* ── Inputs ─────────────────────────────────────────── */
QLineEdit {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 2px solid {c['border']};
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
    min-height: 36px;
}}
QLineEdit:focus   {{ border: 2px solid {c['accent']}; }}
QLineEdit:disabled {{ background-color: {c['surface2']}; color: {c['text_muted']}; }}
QLineEdit::placeholder {{ color: {c['text_muted']}; }}

QTextEdit {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 2px solid {c['border']};
    border-radius: 8px;
    padding: 8px 12px;
}}
QTextEdit:focus {{ border: 2px solid {c['accent']}; }}

/* ── ComboBox ───────────────────────────────────────── */
QComboBox {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 2px solid {c['border']};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 36px;
    min-width: 120px;
}}
QComboBox:focus {{ border: 2px solid {c['accent']}; }}
QComboBox::drop-down {{ border: none; width: 30px; }}
QComboBox::down-arrow {{
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {c['text2']};
    width: 0; height: 0;
    margin-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    selection-background-color: {c['accent']};
    selection-color: #ffffff;
    padding: 4px;
    outline: none;
}}

/* ── Tab Widget ─────────────────────────────────────── */
QTabWidget {{ background-color: {c['bg']}; }}
QTabWidget::pane {{ border: none; background-color: {c['bg']}; }}
QTabBar {{ background-color: {c['bg']}; }}
QTabBar::tab {{
    background-color: {c['bg']};
    color: {c['text_muted']};
    padding: 12px 28px;
    border: none;
    border-bottom: 3px solid transparent;
    font-size: 14px;
    font-weight: 600;
    margin-right: 4px;
}}
QTabBar::tab:selected {{
    color: {c['accent']};
    border-bottom: 3px solid {c['accent']};
}}
QTabBar::tab:hover:!selected {{
    color: {c['text']};
}}

/* ── Progress Bar ───────────────────────────────────── */
QProgressBar {{
    border: none;
    border-radius: 4px;
    background-color: {c['surface2']};
    min-height: 8px;
    max-height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {c['accent']};
    border-radius: 4px;
}}
QProgressBar[role="success"]::chunk {{ background-color: {c['success']}; }}
QProgressBar[role="error"]::chunk   {{ background-color: {c['error']}; }}

/* ── Scrollbars ─────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent; width: 8px; border-radius: 4px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {c['surface2']}; border-radius: 4px; min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{ background: {c['text_muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: transparent; height: 8px; border-radius: 4px; margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {c['surface2']}; border-radius: 4px; min-width: 20px;
}}
QScrollBar::handle:horizontal:hover {{ background: {c['text_muted']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}

/* ── CheckBox ───────────────────────────────────────── */
QCheckBox {{
    color: {c['text']};
    spacing: 8px;
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 18px; height: 18px;
    border-radius: 4px;
    border: 2px solid {c['border']};
    background-color: {c['surface']};
}}
QCheckBox::indicator:checked {{
    background-color: {c['accent']};
    border: 2px solid {c['accent']};
}}
QCheckBox::indicator:hover {{ border: 2px solid {c['accent']}; }}

/* ── Labels ─────────────────────────────────────────── */
QLabel {{ color: {c['text']}; background-color: transparent; }}
QLabel[role="heading"]    {{ font-size: 22px; font-weight: 700; }}
QLabel[role="subheading"] {{ font-size: 15px; font-weight: 600; color: {c['text2']}; }}
QLabel[role="muted"]      {{ color: {c['text_muted']}; font-size: 12px; }}
QLabel[role="header-icon"] {{ font-size: 22px; color: {c['accent']}; background-color: transparent; }}
QLabel[role="about-icon"]  {{ font-size: 40px; color: {c['accent']}; background-color: transparent; }}
QLabel[role="thumb-placeholder"] {{
    background-color: {c['surface2']};
    border-radius: 6px;
    color: {c['text_muted']};
    font-size: 11px;
}}
QLabel[role="badge-queued"]      {{
    background-color: {c['surface2']}; color: {c['text2']};
    border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
QLabel[role="badge-downloading"] {{
    background-color: {c['accent']}; color: #ffffff;
    border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
QLabel[role="badge-processing"]  {{
    background-color: {c['peach']}; color: #ffffff;
    border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
QLabel[role="badge-lyrics"]      {{
    background-color: {c['mauve']}; color: #ffffff;
    border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
QLabel[role="badge-done"]        {{
    background-color: {c['success']}; color: {c['bg']};
    border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
QLabel[role="badge-error"]       {{
    background-color: {c['error']}; color: #ffffff;
    border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}
QLabel[role="badge-cancelled"]   {{
    background-color: {c['surface2']}; color: {c['text_muted']};
    border-radius: 4px; padding: 2px 8px; font-size: 11px; font-weight: 600;
}}

/* ── Frame / Card ───────────────────────────────────── */
QFrame[role="card"] {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}
QFrame[role="header"] {{
    background-color: {c['bg2']};
    border-bottom: 1px solid {c['border']};
    border-radius: 0;
}}
QFrame[role="panel"] {{
    background-color: {c['bg']};
    border-top: 1px solid {c['border']};
}}

/* ── List Widget ────────────────────────────────────── */
QListWidget {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 4px;
    color: {c['text']};
    outline: none;
}}
QListWidget::item {{
    padding: 8px 12px;
    border-radius: 6px;
}}
QListWidget::item:selected {{
    background-color: {c['accent']};
    color: #ffffff;
}}
QListWidget::item:hover:!selected {{ background-color: {c['surface2']}; }}

/* ── SpinBox ────────────────────────────────────────── */
QSpinBox {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 2px solid {c['border']};
    border-radius: 8px;
    padding: 6px 12px;
    font-size: 13px;
    min-height: 36px;
}}
QSpinBox:focus {{ border: 2px solid {c['accent']}; }}
QSpinBox::up-button, QSpinBox::down-button {{
    border: none;
    background-color: transparent;
    width: 20px;
}}

/* ── GroupBox ───────────────────────────────────────── */
QGroupBox {{
    background-color: {c['surface']};
    border: 1px solid {c['border']};
    border-radius: 10px;
    margin-top: 14px;
    padding: 16px 12px 12px 12px;
    font-weight: 600;
    color: {c['text']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    padding: 0 8px;
    color: {c['accent']};
    font-weight: 600;
    font-size: 13px;
}}

/* ── Splitter ───────────────────────────────────────── */
QSplitter {{ background-color: {c['bg']}; }}
QSplitter::handle:vertical {{ background-color: {c['border']}; height: 1px; }}
QSplitter::handle:horizontal {{ background-color: {c['border']}; width: 1px; }}

/* ── Status Bar ─────────────────────────────────────── */
QStatusBar {{
    background-color: {c['bg2']};
    color: {c['text2']};
    border-top: 1px solid {c['border']};
    font-size: 12px;
}}

/* ── Tooltip ────────────────────────────────────────── */
QToolTip {{
    background-color: {c['surface']};
    color: {c['text']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 4px 8px;
    font-size: 12px;
}}

/* ── Separator ──────────────────────────────────────── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {c['border']};
    background-color: {c['border']};
    max-height: 1px;
    min-height: 1px;
    border: none;
}}
"""


def _build_palette(c: dict) -> QPalette:
    """Map theme color dict onto a QPalette so Fusion fills widget backgrounds correctly."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(c["bg"]))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(c["text"]))
    p.setColor(QPalette.ColorRole.Base,            QColor(c["surface"]))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(c["surface2"]))
    p.setColor(QPalette.ColorRole.Text,            QColor(c["text"]))
    p.setColor(QPalette.ColorRole.BrightText,      QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Button,          QColor(c["surface"]))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(c["text"]))
    p.setColor(QPalette.ColorRole.Highlight,       QColor(c["accent"]))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    p.setColor(QPalette.ColorRole.Link,            QColor(c["accent"]))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(c["surface"]))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(c["text"]))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(c["text_muted"]))
    # Disabled state
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(c["text_muted"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(c["text_muted"]))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(c["text_muted"]))
    return p


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, app: QApplication) -> None:
        super().__init__()
        self._app = app
        self._current = "dark"
        self._apply(self._current)

    # ── public ───────────────────────────────────────────
    @property
    def current(self) -> str:
        return self._current

    @property
    def colors(self) -> dict:
        return DARK if self._current == "dark" else LIGHT

    def toggle(self) -> None:
        self._apply("light" if self._current == "dark" else "dark")

    # ── private ──────────────────────────────────────────
    def _apply(self, theme: str) -> None:
        self._current = theme
        colors = DARK if theme == "dark" else LIGHT
        # Palette must be set BEFORE the stylesheet so Fusion uses correct
        # base colors for areas not explicitly covered by QSS.
        self._app.setPalette(_build_palette(colors))
        self._app.setStyleSheet(build_stylesheet(colors))
        self.theme_changed.emit(theme)
