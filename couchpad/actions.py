"""Catalogue of actions a Share + button chord can run.

Shared by the input engine (which chords exist), the daemon (how to run
them) and the control center (labels, icons, the remapping UI).
"""

# name -> (label, theme icon)
ACTIONS = {
    "none":             ("Ничего", "ph:prohibit"),
    "mouse_toggle":     ("Мышь с тачпада вкл/выкл", "ph:hand-pointing"),
    "keyboard":         ("Экранная клавиатура", "ph:keyboard"),
    "volume_up":        ("Громкость +", "ph:speaker-high"),
    "volume_down":      ("Громкость −", "ph:speaker-low"),
    "mute":             ("Звук вкл/выкл", "ph:speaker-slash"),
    "mic_mute":         ("Микрофон вкл/выкл", "ph:microphone-slash"),
    "media_play_pause": ("Пауза / воспроизведение", "ph:play"),
    "media_next":       ("Следующий трек", "ph:skip-forward"),
    "media_previous":   ("Предыдущий трек", "ph:skip-back"),
    "screenshot":       ("Скриншот", "ph:camera"),
    "battery":          ("Показать заряд", "ph:battery-high"),
    "overview":         ("Обзор окон", "ph:squares-four"),
    "show_desktop":     ("Показать рабочий стол", "ph:desktop"),
    "close_window":     ("Закрыть окно (мягко)", "ph:x-square"),
    "fullscreen":       ("Окно на весь экран", "ph:arrows-out"),
    "display_monitor":  ("Только монитор", "ph:monitor"),
    "display_tv":       ("Только телевизор", "ph:television"),
    "big_picture":      ("Steam Big Picture", "ph:steam-logo"),
    "control_center":   ("Панель Couchpad", "ph:sliders-horizontal"),
    "power_off":        ("Выключить геймпад", "ph:power"),
}

# Buttons whose Share chord can be remapped. ○, △ and R1 are fixed:
# switcher / minimize, force close and the quick-launch wheel.
CHORD_BUTTONS = ("square", "cross", "up", "down", "left", "right",
                 "l1", "l2", "r2", "l3", "r3", "options")

FIXED_CHORDS = {
    "circle": ("Окна (Alt+Tab) · удерживать — свернуть игру", "ph:stack"),
    "triangle": ("Удерживать — закрыть игру", "ph:x-circle"),
    "r1": ("Колесо быстрого запуска", "ph:circles-three-plus"),
}

DEFAULT_CHORDS = {
    "square": "keyboard",
    "up": "volume_up",
    "down": "volume_down",
    "left": "display_monitor",
    "right": "display_tv",
    "cross": "media_play_pause",
    "l1": "battery",
    "l2": "screenshot",
    "r2": "mute",
    "l3": "control_center",
    "r3": "show_desktop",
    "options": "overview",
}

REPEATING = {"volume_up", "volume_down"}

BUTTON_LABELS = {
    "cross": "✕", "circle": "○", "triangle": "△", "square": "□",
    "up": "↑", "down": "↓", "left": "←", "right": "→",
    "l1": "L1", "r1": "R1", "l2": "L2", "r2": "R2", "l3": "L3", "r3": "R3",
    "options": "Options", "share": "Share", "ps": "PS",
}


def chords(overrides):
    """Effective chord map: defaults + valid user overrides."""
    out = dict(DEFAULT_CHORDS)
    for button, action in (overrides or {}).items():
        if button in CHORD_BUTTONS and action in ACTIONS:
            out[button] = action
    return out
