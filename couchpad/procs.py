"""Process-tree helpers for force-closing a game safely."""

import os
import signal
import time

# Never kill these, whatever window/process the user points at.
PROTECTED_COMM = {
    "systemd", "kwin_wayland", "kwin_x11", "kwin_wayland_wr", "plasmashell",
    "Xwayland", "Xorg", "krunner", "ksmserver", "kded6", "kded5",
    "dbus-daemon", "dbus-broker", "pipewire", "wireplumber", "pipewire-pulse",
    "sddm", "gamescope", "gamescope-wl", "steam", "steamwebhelper",
    "steam-runtime-l", "srt-logger", "python3", "bash", "zsh", "fish",
    "konsole", "ghostty", "dolphin", "plasma-keyboard", "xdg-desktop-por",
    "steamos-manager", "inputplumber",
}


def read_table(proc="/proc"):
    """pid -> {"ppid", "comm", "cmdline", "uid"} for every readable process."""
    table = {}
    for name in os.listdir(proc):
        if not name.isdigit():
            continue
        pid = int(name)
        try:
            with open(f"{proc}/{name}/stat", "rb") as f:
                stat = f.read().decode(errors="replace")
            with open(f"{proc}/{name}/cmdline", "rb") as f:
                cmdline = f.read().split(b"\0")
            uid = os.stat(f"{proc}/{name}").st_uid
        except OSError:
            continue
        # comm may contain spaces/parens: it is between the first "(" and
        # the last ")".
        lp, rp = stat.find("("), stat.rfind(")")
        comm = stat[lp + 1:rp]
        rest = stat[rp + 2:].split()
        table[pid] = {
            "state": rest[0],
            "ppid": int(rest[1]),
            "comm": comm,
            "cmdline": [c.decode(errors="replace") for c in cmdline if c],
            "uid": uid,
        }
    return table


def is_reaper(info):
    cmd = info["cmdline"]
    return bool(cmd) and os.path.basename(cmd[0]) == "reaper" and "SteamLaunch" in cmd


def steam_app_id(info):
    for arg in info["cmdline"]:
        if arg.startswith("AppId="):
            return arg[len("AppId="):]
    return None


def ancestors(table, pid):
    seen = set()
    while pid in table and pid not in seen and pid > 1:
        seen.add(pid)
        yield pid
        pid = table[pid]["ppid"]


def descendants(table, root):
    children = {}
    for pid, info in table.items():
        children.setdefault(info["ppid"], []).append(pid)
    out, stack = [], [root]
    while stack:
        for child in children.get(stack.pop(), []):
            out.append(child)
            stack.append(child)
    return out


def is_protected(info):
    return info["comm"] in PROTECTED_COMM


def find_target(table, pid, my_uid=None):
    """Decide what to kill for a window owned by `pid`.

    Returns (root_pid, kind, label) or None. kind is "steam" when the game
    runs under Steam's reaper (then the whole reaper tree goes), else
    "process".
    """
    if my_uid is None:
        my_uid = os.getuid()
    if pid not in table or pid <= 1:
        return None
    info = table[pid]
    if info["uid"] != my_uid:
        return None
    for anc in ancestors(table, pid):
        if is_reaper(table[anc]):
            return anc, "steam", f"Steam AppId {steam_app_id(table[anc])}"
    if is_protected(info):
        return None
    return pid, "process", info["comm"]


def latest_steam_game(table, my_uid=None):
    """Fallback without a window manager: newest running Steam game."""
    if my_uid is None:
        my_uid = os.getuid()
    reapers = [pid for pid, info in table.items()
               if info["uid"] == my_uid and is_reaper(info)
               and steam_app_id(info) not in (None, "0")
               and descendants(table, pid)]
    if not reapers:
        return None
    pid = max(reapers)
    return pid, "steam", f"Steam AppId {steam_app_id(table[pid])}"


def kill_tree(root, kind, table_fn=read_table, kill=os.kill, sleep=time.sleep):
    """SIGKILL everything below root (twice, to catch fresh spawns), then
    the root itself. Steam's reaper is only TERM'ed so Steam notices the
    game ended cleanly. Returns the number of processes signalled."""
    me = os.getpid()
    count = 0
    for attempt in range(2):
        table = table_fn()
        if root not in table:
            break
        # Under Steam's reaper everything belongs to the game (proton's
        # python script, wrapper shells...). Elsewhere be conservative.
        victims = [p for p in descendants(table, root)
                   if p != me and (kind == "steam" or not is_protected(table[p]))]
        for p in victims:
            try:
                kill(p, signal.SIGKILL)
                count += 1
            except (ProcessLookupError, PermissionError):
                pass
        if attempt == 0:
            sleep(0.3)
    try:
        kill(root, signal.SIGTERM if kind == "steam" else signal.SIGKILL)
        count += 1
    except (ProcessLookupError, PermissionError):
        pass
    return count
