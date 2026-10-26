BG = '@RAM_BG@'
PANEL = '@RAM_PANEL@'
INPUT = '@RAM_INPUT@'
TEXT = '@RAM_TEXT@'
MUTED = '@RAM_MUTED@'
LINE = '@RAM_LINE@'
SELECT = '@RAM_SELECT@'
NOTE = '@RAM_NOTE@'
FG_ACCENT = '@RAM_ACCENT@'
HOVER = '@RAM_HOVER@'
PRESSED = '@RAM_PRESSED@'
RAISED = '@RAM_RAISED@'
ACCENT_HOVER = '@RAM_ACCENT_HOVER@'
ACCENT_PRESSED = '@RAM_ACCENT_PRESSED@'
ACCENT_BRIGHT = '@RAM_ACCENT_BRIGHT@'
ACCENT_SOFT = '@RAM_ACCENT_SOFT@'
ACCENT_TEXT = '@RAM_ACCENT_TEXT@'
ACCENT_DEEP = '@RAM_ACCENT_DEEP@'
ON_ACCENT = '@RAM_ON_ACCENT@'
SUCCESS = '@RAM_SUCCESS@'
WARNING = '@RAM_WARNING@'
ERROR = '@RAM_ERROR@'
DANGER_SURFACE = '@RAM_DANGER_SURFACE@'
ON_DANGER = '@RAM_ON_DANGER@'

ARROW = '@RAM_ARROW@'
SUCCESS_SURFACE = '@RAM_SUCCESS_SURFACE@'
SUCCESS_BORDER = '@RAM_SUCCESS_BORDER@'
OPAQUE_PANEL = '@RAM_OPAQUE_PANEL@'
OPAQUE_SELECT = '@RAM_OPAQUE_SELECT@'


MAIN = f"""
            QMainWindow {{ background: {BG}; }}
            QWidget {{ color: {TEXT}; font-family: 'Segoe UI'; }}

            QFrame#navPanel, QFrame#rightPanel {{ background: {PANEL}; border: 0; }}
            QFrame#centerPanel {{ background: {BG};    border: 0; }}
            QFrame#titleBar {{ background: {PANEL}; border-bottom: 1px solid {LINE}; }}

            QLabel#sectionTitle {{ font-size: 13px; font-weight: 700; }}
            QLabel#titleText {{ font-size: 12px; font-weight: 700; color: {TEXT}; }}

            QPushButton#titleButton {{
                background: transparent; border: 0;
                min-height: 24px; min-width: 30px; padding: 0;
                text-align: center; color: {MUTED}; font-size: 12px;
            }}
            QPushButton#titleButton:hover {{ background: {SELECT}; color: {TEXT}; }}

            QPushButton#closeButton {{
                background: transparent; border: 0;
                min-height: 24px; min-width: 30px; padding: 0;
                text-align: center; color: {MUTED}; font-size: 12px;
            }}
            QPushButton#closeButton:hover {{ background: @RAM_DANGER_SURFACE@; color: @RAM_ON_DANGER@; }}

            QPushButton#navTab {{
                background: transparent; border: 1px solid transparent;
                border-radius: 0; text-align: left; min-height: 28px;
                padding: 2px 8px; color: {MUTED}; font-size: 12px;
            }}
            QPushButton#navTab:checked {{
                background: {RAISED}; border: 1px solid {HOVER};
                color: {TEXT}; font-weight: 700;
            }}

            QListWidget {{
                background: {INPUT}; border: 1px solid {LINE};
                outline: none; padding: 2px; font-size: 11px;
            }}
            QListWidget::item {{ height: 22px; padding-left: 6px; }}
            QListWidget::item:selected {{ background: {SELECT}; color: {TEXT}; }}

            QLabel#accountName {{ color: {TEXT};  font-size: 11px; }}
            QLabel#noteSep {{ color: @RAM_MUTED@; font-size: 11px; }}
            QLabel#noteText {{ color: {NOTE};  font-size: 11px; font-weight: 600; }}
            QLabel#performanceSep {{ color: @RAM_MUTED@; font-size: 11px; }}
            QLabel#ramUsage {{ color: {ACCENT_TEXT}; font-size: 10px; }}
            QLabel#cpuUsage {{ color: @RAM_SUCCESS@; font-size: 10px; }}

            QLineEdit {{
                background: {INPUT}; border: 1px solid {LINE};
                padding: 4px 6px; min-height: 24px; color: {TEXT};
            }}

            QPushButton {{
                background: {INPUT}; border: 1px solid {LINE};
                min-height: 26px; padding: 2px 8px;
                text-align: left; font-size: 11px; color: {TEXT};
            }}
            QPushButton:hover {{ background: {SELECT}; }}
            QPushButton:pressed {{ background: {SELECT}; }}

            QToolButton#splitArrow {{
                background: {INPUT}; border: 1px solid {LINE};
                min-width: 26px; max-width: 26px; min-height: 26px;
                padding: 0; color: {TEXT};
            }}
            QToolButton#splitArrow:hover {{ background: {SELECT}; }}
            QToolButton#splitArrow:pressed {{ background: {SELECT}; }}
            QToolButton#splitArrow::menu-indicator {{ image: none; }}

            QMenu {{
                background: {OPAQUE_PANEL}; border: 1px solid {LINE};
                color: {TEXT}; font-size: 11px;
                border-radius: 0px;
                padding: 2px 0px;
            }}
            QMenu::item {{
                padding: 4px 20px 4px 12px;
                border-radius: 0px;
            }}
            QMenu::item:selected {{ background: {OPAQUE_SELECT}; border-radius: 0px; }}
            QMenu::separator {{ height: 1px; background: {LINE}; margin: 2px 0px; }}

            QToolTip {{
                background: {OPAQUE_PANEL}; border: 1px solid {LINE};
                color: {TEXT}; padding: 4px 6px;
            }}

            QScrollArea#groupScroll {{
                background: transparent; border: 0;
                max-height: 30px;
            }}
            QScrollArea#groupScroll > QWidget > QWidget {{
                background: transparent;
            }}
            QPushButton#groupTab {{
                background: transparent; border: 1px solid transparent;
                border-radius: 3px; min-height: 20px; max-height: 20px;
                padding: 0px 8px; font-size: 10px; color: {MUTED};
            }}
            QPushButton#groupTab:checked {{
                background: {RAISED}; border: 1px solid {HOVER}; color: {TEXT};
            }}
            QPushButton#groupTab:hover {{ background: @RAM_RAISED@; border-color: @RAM_HOVER@; }}

            QDialog {{ background: {BG}; }}
            QTextEdit {{ background: {INPUT}; border: 1px solid {LINE}; color: {TEXT}; font-size: 11px; }}

            QCheckBox {{ color: {TEXT}; font-size: 11px; spacing: 6px; }}
            QCheckBox::indicator {{
                width: 13px; height: 13px;
                border: 1px solid {LINE}; background: {INPUT};
            }}
            QCheckBox::indicator:checked {{
                background: {ACCENT_BRIGHT}; border: 1px solid {ACCENT_BRIGHT};
                image: url(none);
            }}
            QCheckBox::indicator:disabled {{
                background: {SELECT}; border: 1px solid {LINE};
                opacity: 0.5;
            }}
            QCheckBox:disabled {{ color: {MUTED}; }}

            QRadioButton {{ color: {TEXT}; font-size: 11px; spacing: 6px; }}
            QRadioButton::indicator {{
                width: 13px; height: 13px; border-radius: 7px;
                border: 1px solid {LINE}; background: {INPUT};
            }}
            QRadioButton::indicator:checked {{
                background: {ACCENT_BRIGHT}; border: 2px solid {INPUT};
                outline: 1px solid {ACCENT_BRIGHT};
            }}
            QRadioButton:disabled {{ color: {MUTED}; }}

            QGroupBox {{
                border: 1px solid {LINE}; border-radius: 3px;
                margin-top: 10px; padding-top: 4px;
                font-size: 10px; font-weight: 700; color: {MUTED};
            }}
            QGroupBox::title {{
                subcontrol-origin: margin; subcontrol-position: top left;
                padding: 0 6px 0 6px; left: 8px;
            }}
        """


DIALOG = f"""
    QDialog   {{ background: {BG}; }}
    QLabel    {{ color: {TEXT}; font-size: 11px; }}
    QLineEdit {{ background: {INPUT}; border: 1px solid {LINE};
                color: {TEXT}; padding: 4px 6px; min-height: 24px; }}
    QTextEdit {{ background: {INPUT}; border: 1px solid {LINE};
                color: {TEXT}; font-family: Consolas, monospace; font-size: 11px; }}
    QPushButton {{
        background: {INPUT}; border: 1px solid {LINE};
        color: {TEXT}; min-height: 26px; padding: 2px 12px; font-size: 11px;
    }}
    QPushButton:hover   {{ background: {SELECT}; }}
    QPushButton:pressed {{ background: {SELECT}; }}
"""


COMMON = (
    'QPushButton:disabled, QToolButton:disabled { color: @RAM_MUTED@; }'
    'QPushButton:focus, QToolButton:focus, QLineEdit:focus, QComboBox:focus,'
    'QTextEdit:focus { border: 1px solid @RAM_ACCENT@; }'
    'QComboBox { background: @RAM_INPUT@; color: @RAM_TEXT@;'
    ' border: 1px solid @RAM_LINE@; padding: 3px 6px; min-height: 24px; }'
    # Native frames keep buttonless spin box editors from collapsing.
    'QAbstractSpinBox { background: @RAM_INPUT@; color: @RAM_TEXT@; min-height: 24px; }'
    'QComboBox QLineEdit, QAbstractSpinBox QLineEdit { background: transparent;'
    ' border: 0; padding: 0; margin: 0; min-height: 0; min-width: 0; }'
    'QComboBox QAbstractItemView { background: @RAM_OPAQUE_PANEL@; color: @RAM_TEXT@;'
    ' selection-background-color: @RAM_OPAQUE_SELECT@; selection-color: @RAM_TEXT@; }'
    'QSlider::groove:horizontal { height: 4px; background: @RAM_LINE@; }'
    'QSlider::handle:horizontal { width: 12px; margin: -4px 0; background: @RAM_ACCENT@; }'
    'QScrollArea { background: transparent; border: 0; }'
)
