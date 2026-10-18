"""Configuration: defaults plus an optional TOML override file."""

import json
import os
import re
import tomllib
from dataclasses import dataclass, field, fields

CONFIG_PATH = os.path.join(
    os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
    "couchpad", "config.toml")


@dataclass
class Config:
    # --- Share-button gestures (seconds) ---
    tap_max: float = 0.35            # a press longer than this is not a "tap"
    double_tap_window: float = 0.45  # max gap between the two taps' releases
    long_press: float = 1.5          # hold time for Share+O / Share+Triangle
    alt_tab_timeout: float = 10.0    # auto-confirm the switcher after idling

    # --- touchpad ---
    grab_touchpad: bool = True       # stop KDE from using the pad on its own
    pointer_speed: float = 1.0
    pointer_accel: float = 1.0       # 0 = linear
    pointer_smoothing: float = 0.35  # 0 = off, <1; light EMA against jitter
    natural_scroll: bool = True      # phone-like two-finger scrolling
    scroll_speed: float = 1.0
    tap_to_click: bool = True
    tap_time: float = 0.20
    tap_move: float = 70.0           # touchpad units (~2 mm)

    # --- sticks in mouse mode ---
    stick_mouse: str = "off"         # both (left = cursor, right = scroll) | scroll | off
    stick_deadzone: float = 0.12
    stick_pointer_speed: float = 1400.0  # px/s at full deflection
    stick_scroll_speed: float = 1800.0   # hi-res units/s (120 = 1 notch)

    # --- behaviour ---
    rumble: bool = True              # haptic feedback on the controller
    haptic_strength: float = 1.0     # 0 = off .. 3 = strongest
    haptics: str = "auto"            # auto (HD over Bluetooth) | hd | rumble
    notifications: bool = True
    osd: bool = True                 # own on-screen messages instead of KDE popups
    hold_osd: bool = True            # progress ring while holding Share + ○/△
    mouse_on_after_minimize: bool = False
    keyboard: str = "auto"           # auto | steam | plasma
    idle_off: float = 0.0            # switch the pad off after N idle minutes (0 = never)
    tray: bool = True                # control center icon in the system tray
    language: str = "auto"           # auto | ru | en

    # --- lights ---
    light_mode: str = "static"       # off | static | breathe | rainbow | battery | steam
    light_color: str = "#1e6bff"
    light_brightness: float = 0.8    # 0..1
    light_speed: float = 1.0         # breathe / rainbow speed
    light_mouse_color: str = ""   # lightbar while mouse mode is on ("" = keep)
    light_flash: bool = True         # short flashes on actions
    player_leds: str = "auto"        # auto | off | battery | mouse
    mic_led: str = "auto"            # auto | mouse

    # Quick-launch wheel items: [{app = "hydra"}, {name, icon, open|exec}]
    wheel: list = field(default_factory=list)

    # Share + button -> action (see actions.py); missing = default
    chords: dict = field(default_factory=dict)

    extra: dict = field(default_factory=dict)


def load(path: str = None) -> Config:
    path = path or CONFIG_PATH
    cfg = Config()
    if not os.path.exists(path):
        return cfg
    with open(path, "rb") as f:
        data = tomllib.load(f)
    known = {f.name for f in fields(Config) if f.name != "extra"}
    for key, value in data.items():
        if key not in known:
            cfg.extra[key] = value
            continue
        default = getattr(cfg, key)
        if isinstance(default, (list, dict)):
            if isinstance(value, type(default)):
                setattr(cfg, key, value)
            continue
        if isinstance(value, (list, dict)) or (
                isinstance(default, (int, float)) and isinstance(value, str)):
            continue
        try:
            value = type(default)(value)
        except (TypeError, ValueError):
            continue
        setattr(cfg, key, value)
    validate(cfg)
    return cfg


CHOICES = {
    "haptics": ("auto", "hd", "rumble"),
    "keyboard": ("auto", "steam", "plasma"),
    "light_mode": ("off", "static", "breathe", "rainbow", "battery", "steam"),
    "player_leds": ("auto", "off", "battery", "mouse"),
    "mic_led": ("auto", "mouse"),
    "language": ("auto", "ru", "en"),
    "stick_mouse": ("both", "scroll", "off"),
}
COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def validate(cfg):
    defaults = Config()
    for key, allowed in CHOICES.items():
        if getattr(cfg, key) not in allowed:
            setattr(cfg, key, getattr(defaults, key))
    if not COLOR_RE.match(cfg.light_color):
        cfg.light_color = defaults.light_color
    if cfg.light_mouse_color and not COLOR_RE.match(cfg.light_mouse_color):
        cfg.light_mouse_color = defaults.light_mouse_color
    cfg.light_brightness = min(max(cfg.light_brightness, 0.0), 1.0)
    cfg.light_speed = min(max(cfg.light_speed, 0.1), 5.0)
    cfg.idle_off = max(cfg.idle_off, 0.0)
    cfg.haptic_strength = min(max(cfg.haptic_strength, 0.0), 3.0)
    cfg.wheel = [w for w in cfg.wheel if isinstance(w, dict)]
    cfg.chords = {str(k): str(v) for k, v in cfg.chords.items()}


# --------------------------------------------------------------------------
# Writing (the control center saves through this)

SECTIONS = [
    ("Share-button gestures (seconds)",
     ["tap_max", "double_tap_window", "long_press", "alt_tab_timeout"]),
    ("Touchpad", ["grab_touchpad", "pointer_speed", "pointer_accel", "pointer_smoothing",
                  "natural_scroll", "scroll_speed", "tap_to_click", "tap_time", "tap_move"]),
    ("Sticks in mouse mode", ["stick_mouse", "stick_deadzone", "stick_pointer_speed",
                              "stick_scroll_speed"]),
    ("Feedback", ["rumble", "haptic_strength", "haptics"]),
    ("Messages", ["notifications", "osd", "hold_osd"]),
    ("Behaviour", ["mouse_on_after_minimize", "keyboard", "idle_off", "tray", "language"]),
    ("Lights", ["light_mode", "light_color", "light_brightness", "light_speed",
                "light_mouse_color", "light_flash", "player_leds", "mic_led"]),
]


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(float(v)) if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    raise TypeError(f"cannot write {type(v).__name__}")


def _key(k):
    return k if re.match(r"^[A-Za-z0-9_-]+$", k) else json.dumps(k, ensure_ascii=False)


def dumps(cfg):
    out = ["# couchpad settings (written by the control center; hand edits are fine).",
           "# Delete a line to get the default back.", ""]
    for title, keys in SECTIONS:
        out.append(f"# {title}")
        out += [f"{k} = {_value(getattr(cfg, k))}" for k in keys]
        out.append("")
    for k, v in cfg.extra.items():
        if not isinstance(v, (dict, list)):
            out.append(f"{_key(k)} = {_value(v)}")
    if cfg.chords:
        out += ["", "# Share + button -> action", "[chords]"]
        out += [f"{_key(k)} = {_value(v)}" for k, v in sorted(cfg.chords.items())]
    for item in cfg.wheel:
        out += ["", "[[wheel]]"]
        out += [f"{_key(k)} = {_value(v)}" for k, v in item.items()
                if isinstance(v, (str, int, float, bool))]
    return "\n".join(out).rstrip() + "\n"


def save(cfg, path=None):
    """Atomic write, so the daemon never reads half a file."""
    path = path or CONFIG_PATH
    text = dumps(cfg)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "w") as f:
        f.write(text)
    os.replace(tmp, path)


WHEEL_HELP = """
# Quick-launch wheel (Share + R1), up to 8 items, top = first, clockwise.
# app = .desktop id, or open = URL, or exec = shell command; name/icon optional.
# Without any [[wheel]] entries a default set of installed apps is used.
# [[wheel]]
# app = "hydra"
# [[wheel]]
# name = "Big Picture"
# icon = "steam"
# open = "steam://open/bigpicture"
"""

DEFAULT_FILE = dumps(Config()) + WHEEL_HELP
