"""Python side of the control center: settings, daemon link, system tasks."""

import json
import logging
import os
import shutil
import subprocess
import threading
import time

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot

from .. import __version__, config as config_mod, i18n, procs, steamcfg, system, wheel as wheel_mod
from ..actions import (ACTIONS, BUTTON_LABELS, CHORD_BUTTONS, DEFAULT_CHORDS, FIXED_CHORDS,
                       chords as chord_map)
from ..daemon import HAPTICS
from ..i18n import _

log = logging.getLogger("couchpad")

UNIT = "couchpad.service"
AUTOSTART = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                         "autostart", "couchpad-tray.desktop")
REPO_URL = "https://github.com/shamilmusaev/couchpad"
CHORD_ORDER = ("circle", "triangle", "r1", "square", "cross", "up", "down", "left", "right",
               "l1", "l2", "r2", "l3", "r3", "options")


def daemon_call(cmd, timeout=2500):
    """Send a ctl command to the running daemon. None if it isn't running."""
    from gi.repository import Gio, GLib
    try:
        bus = Gio.bus_get_sync(Gio.BusType.SESSION)
        res = bus.call_sync(system.BUS_NAME, system.OBJ_PATH, system.BUS_NAME, "Command",
                            GLib.Variant("(s)", (cmd,)), None, 0, timeout, None)
        return res.unpack()[0]
    except Exception:
        return None


def systemctl(*args):
    try:
        r = subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True,
                           timeout=15)
        return r.returncode, r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)


def installed_apps():
    """Every visible .desktop application: [{id, name, icon}], sorted."""
    seen, out = set(), []
    for d in wheel_mod.app_dirs():
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            if not n.endswith(".desktop") or n in seen:
                continue
            seen.add(n)
            try:
                info = wheel_mod.read_desktop(os.path.join(d, n))
            except OSError:
                continue
            if info["hidden"]:
                continue
            out.append({"id": n[:-len(".desktop")], "name": info["name"], "icon": info["icon"]})
    out.sort(key=lambda a: a["name"].lower())
    return out


class Backend(QObject):
    statusChanged = Signal()
    langChanged = Signal()
    settingsChanged = Signal()
    chordsChanged = Signal()
    wheelChanged = Signal()
    appsChanged = Signal()
    serviceChanged = Signal()
    steamChanged = Signal()
    toast = Signal(str, str, str)          # title, body, kind (ok|warn|error|info)
    _statusFromThread = Signal(str)
    _toastFromThread = Signal(str, str, str)
    _serviceFromThread = Signal(bool, bool)
    _steamFromThread = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.cfg = config_mod.load()
        i18n.set_lang(self.cfg.language)
        self._status = {}
        self._running = False
        self._apps = []
        self._service_active = False
        self._autostart = False
        self._steam = "unknown"
        self._busy = False
        self.save_timer = QTimer(self, singleShot=True, interval=250, timeout=self._save)
        self._statusFromThread.connect(self._apply_status)
        self._toastFromThread.connect(self.toast)
        self._serviceFromThread.connect(self._apply_service)
        self._steamFromThread.connect(self._apply_steam)
        self.alive = True
        threading.Thread(target=self._poll, daemon=True, name="status").start()
        self.refreshService()
        self.refreshSteam()

    # ------------------------------------------------------------------ status
    def _poll(self):
        while self.alive:
            res = daemon_call("status", 1500)
            self._statusFromThread.emit(res or "")
            time.sleep(1.0)

    def _apply_status(self, text):
        try:
            st = json.loads(text) if text else {}
        except ValueError:
            st = {}
        running = bool(text)
        st.pop("events", None)
        if st != self._status or running != self._running:
            self._status = st
            self._running = running
            self.statusChanged.emit()

    @Property("QVariantMap", notify=statusChanged)
    def status(self):
        return self._status

    @Property(bool, notify=statusChanged)
    def daemonRunning(self):
        return self._running

    @Property("QVariantMap", notify=statusChanged)
    def pad(self):
        pads = self._status.get("controllers") or []
        return pads[0] if pads else {}

    @Property(bool, notify=statusChanged)
    def mouse(self):
        return bool(self._status.get("mouse"))

    @Slot(bool)
    def setMouse(self, on):
        self._call_async("mouse " + ("on" if on else "off"))

    @Slot(str)
    def runAction(self, name):
        if not self._running:
            self.toast.emit(_("Служба не запущена"), _("Запустите её на вкладке «Система»"), "warn")
            return
        self._call_async("action " + name)

    @Slot(str)
    def testHaptic(self, name):
        self._call_async("haptic " + name)

    @Slot()
    def warmHaptics(self):
        self._call_async("haptic-warm")

    @Slot(str)
    def previewLight(self, color):
        self._call_async("light-preview " + color)

    @Slot()
    def testOsd(self):
        self._call_async(_("osd Сообщение Couchpad"))

    def _call_async(self, cmd):
        threading.Thread(target=daemon_call, args=(cmd,), daemon=True).start()

    # ---------------------------------------------------------------- settings
    @Property("QVariantMap", notify=settingsChanged)
    def settings(self):
        out = {}
        for k, v in vars(self.cfg).items():
            if isinstance(v, (bool, int, float, str)):
                out[k] = v
        return out

    @Slot(str, "QVariant")
    def set(self, key, value):
        if not hasattr(self.cfg, key) or key in ("wheel", "chords", "extra"):
            return
        default = getattr(config_mod.Config(), key)
        try:
            value = type(default)(value)
        except (TypeError, ValueError):
            return
        if getattr(self.cfg, key) == value:
            return
        setattr(self.cfg, key, value)
        config_mod.validate(self.cfg)
        if key == "language":
            i18n.set_lang(self.cfg.language)
            self.langChanged.emit()
            self.chordsChanged.emit()
            self.wheelChanged.emit()
        self.settingsChanged.emit()
        self.save_timer.start()

    @Slot(str)
    def resetSetting(self, key):
        if hasattr(self.cfg, key):
            self.set(key, getattr(config_mod.Config(), key))

    def _save(self):
        try:
            config_mod.save(self.cfg)
        except OSError as exc:
            self.toast.emit(_("Не удалось сохранить"), str(exc), "error")
            return
        self._call_async("reload")
        if self.cfg.tray != os.path.exists(AUTOSTART):
            self._write_autostart(self.cfg.tray)

    @Slot()
    def reloadFromDisk(self):
        self.cfg = config_mod.load()
        self.settingsChanged.emit()
        self.chordsChanged.emit()
        self.wheelChanged.emit()

    # ------------------------------------------------------------------ chords
    @Property(str, notify=langChanged)
    def lang(self):
        return i18n.lang()

    @Property("QVariantMap", constant=True)
    def translations(self):
        from ..i18n_en import EN
        return EN

    @Property("QVariantList", notify=langChanged)
    def actions(self):
        return [{"name": k, "label": _(v[0]), "icon": v[1]} for k, v in ACTIONS.items()]

    @Property("QVariantList", notify=chordsChanged)
    def chords(self):
        eff = chord_map(self.cfg.chords)
        out = []
        for b in CHORD_ORDER:
            if b in FIXED_CHORDS:
                label, icon = FIXED_CHORDS[b]
                out.append({"button": b, "glyph": BUTTON_LABELS[b], "fixed": True,
                            "action": "", "label": _(label), "icon": icon, "custom": False})
            else:
                a = eff.get(b, "none")
                out.append({"button": b, "glyph": BUTTON_LABELS[b], "fixed": False,
                            "action": a, "label": _(ACTIONS[a][0]), "icon": ACTIONS[a][1],
                            "custom": a != DEFAULT_CHORDS.get(b)})
        return out

    @Slot(str, str)
    def setChord(self, button, action):
        if button not in CHORD_BUTTONS or action not in ACTIONS:
            return
        if action == DEFAULT_CHORDS.get(button):
            self.cfg.chords.pop(button, None)
        else:
            self.cfg.chords[button] = action
        self.chordsChanged.emit()
        self.save_timer.start()

    @Slot()
    def resetChords(self):
        self.cfg.chords = {}
        self.chordsChanged.emit()
        self.save_timer.start()

    # ------------------------------------------------------------------- wheel
    @Property("QVariantList", notify=wheelChanged)
    def wheelItems(self):
        raw = self.cfg.wheel or wheel_mod.DEFAULT_ITEMS
        out = []
        for item in wheel_mod.resolve(raw):
            kind = "app" if item.get("app") else "open" if item.get("open") else "exec"
            out.append({"name": item["name"], "icon": item.get("icon", ""), "kind": kind,
                        "value": item.get(kind, "")})
        return out

    @Property(bool, notify=wheelChanged)
    def wheelIsDefault(self):
        return not self.cfg.wheel

    def _wheel_raw(self):
        """Config entries in the order shown (uninstalled apps dropped), so
        indices match wheelItems."""
        raw = self.cfg.wheel or wheel_mod.DEFAULT_ITEMS
        return [dict(w) for w in raw if isinstance(w, dict) and wheel_mod.resolve([w])]

    def _store_wheel(self, items):
        keep = ("app", "open", "exec", "name", "icon")
        self.cfg.wheel = [{k: it[k] for k in keep if it.get(k)}
                          for it in items[:wheel_mod.MAX_ITEMS]]
        self.wheelChanged.emit()
        self.save_timer.start()

    @Slot(str)
    def wheelAddApp(self, app_id):
        items = self._wheel_raw()
        if len(items) >= wheel_mod.MAX_ITEMS:
            self.toast.emit(_("В колесе уже 8 приложений"), _("Удалите одно, чтобы добавить новое"), "warn")
            return
        if any(i.get("app") == app_id for i in items):
            self.toast.emit(_("Уже в колесе"), "", "info")
            return
        items.append({"app": app_id})
        self._store_wheel(items)

    @Slot(str, str, str)
    def wheelAddCustom(self, name, target, icon):
        target = target.strip()
        if not target:
            return
        items = self._wheel_raw()
        if len(items) >= wheel_mod.MAX_ITEMS:
            self.toast.emit(_("В колесе уже 8 приложений"), _("Удалите одно, чтобы добавить новое"), "warn")
            return
        kind = "open" if "://" in target else "exec"
        items.append({"name": name.strip() or target, kind: target, "icon": icon.strip()})
        self._store_wheel(items)

    @Slot(int)
    def wheelRemove(self, i):
        items = self._wheel_raw()
        if 0 <= i < len(items):
            del items[i]
            self._store_wheel(items)

    @Slot(int, int)
    def wheelMove(self, i, d):
        items = self._wheel_raw()
        j = i + d
        if 0 <= i < len(items) and 0 <= j < len(items):
            items[i], items[j] = items[j], items[i]
            self._store_wheel(items)

    @Slot()
    def wheelReset(self):
        self.cfg.wheel = []
        self.wheelChanged.emit()
        self.save_timer.start()

    @Property("QVariantList", notify=appsChanged)
    def apps(self):
        return self._apps

    @Slot()
    def loadApps(self):
        if self._apps:
            return

        def work():
            apps = installed_apps()
            self._apps = apps
            self.appsChanged.emit()
        threading.Thread(target=work, daemon=True).start()

    # ---------------------------------------------------------------- haptics
    @Property("QVariantList", notify=langChanged)
    def hapticPatterns(self):
        names = {"tick": _("Тик"), "progress1": _("Удержание 1"), "progress2": _("Удержание 2"),
                 "progress3": _("Удержание 3"), "fire": _("Сработало"), "cancel": _("Отмена"),
                 "on": _("Включено"), "off": _("Выключено"), "open": _("Открытие"), "detent": _("Щелчок"),
                 "launch": _("Запуск"), "step": _("Шаг"), "confirm": _("Выбор")}
        return [{"name": k, "label": names.get(k, k)} for k in HAPTICS]

    # ---------------------------------------------------------------- service
    @Property(bool, notify=serviceChanged)
    def serviceActive(self):
        return self._service_active

    @Property(bool, notify=serviceChanged)
    def autostart(self):
        return self._autostart

    @Property(bool, notify=serviceChanged)
    def busy(self):
        return self._busy

    def _apply_service(self, active, enabled):
        self._service_active, self._autostart = active, enabled
        self.serviceChanged.emit()

    @Slot()
    def refreshService(self):
        def work():
            a = systemctl("is-active", UNIT)[1] == "active"
            e = systemctl("is-enabled", UNIT)[1] == "enabled"
            self._serviceFromThread.emit(a, e)
        threading.Thread(target=work, daemon=True).start()

    @Slot(str)
    def service(self, verb):
        if verb not in ("start", "stop", "restart", "enable", "disable"):
            return

        def work():
            code, out = systemctl(verb, UNIT)
            if code:
                self._toastFromThread.emit(_("Не получилось"), out or verb, "error")
            else:
                self._toastFromThread.emit({"start": _("Служба запущена"), "stop": _("Служба остановлена"),
                                            "restart": _("Служба перезапущена"),
                                            "enable": _("Автозапуск включён"),
                                            "disable": _("Автозапуск выключен")}[verb], "", "ok")
            time.sleep(0.5)
            a = systemctl("is-active", UNIT)[1] == "active"
            e = systemctl("is-enabled", UNIT)[1] == "enabled"
            self._serviceFromThread.emit(a, e)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ steam layout
    @Property(str, notify=steamChanged)
    def steamLayout(self):
        return self._steam

    def _apply_steam(self, state):
        self._steam = state
        self.steamChanged.emit()

    @Slot()
    def refreshSteam(self):
        def work():
            st = steamcfg.status()
            if not st:
                self._steamFromThread.emit("none")
            else:
                self._steamFromThread.emit("neutral" if all(st.values()) else "steam")
        threading.Thread(target=work, daemon=True).start()

    @Slot(bool)
    def setSteamLayout(self, neutral):
        """Quit Steam, change its desktop layout, start it again."""
        if self._busy:
            return
        self._busy = True
        self.serviceChanged.emit()

        def work():
            try:
                self._steam_layout(neutral)
            finally:
                self._busy = False
                self._serviceFromThread.emit(self._service_active, self._autostart)
                self.refreshSteam()
        threading.Thread(target=work, daemon=True).start()

    def _steam_layout(self, neutral):
        was_running = system.steam_running()
        if was_running:
            if any(procs.is_reaper(i) for i in procs.read_table().values()):
                self._toastFromThread.emit(_("Сначала закройте игру"),
                                           _("Steam нельзя перезапускать во время игры"), "warn")
                return
            self._toastFromThread.emit(_("Steam закрывается…"), _("Это займёт несколько секунд"), "info")
            subprocess.run(["steam", "-shutdown"], capture_output=True, timeout=20)
            for _i in range(60):
                if not system.steam_running():
                    break
                time.sleep(0.5)
            if system.steam_running():
                self._toastFromThread.emit(_("Steam не закрылся"), _("Попробуйте ещё раз"), "error")
                return
        changed = steamcfg.neutralize() if neutral else steamcfg.restore()
        self._toastFromThread.emit(
            _("Раскладка Steam: ") + (_("нейтральная") if neutral else _("как была")),
            _("Изменено файлов: {n}").format(n=len(changed)) if changed
            else _("Изменения не понадобились"), "ok")
        if was_running:
            if systemctl("cat", "app-steam@autostart.service")[0] == 0:
                systemctl("start", "app-steam@autostart.service")
            else:
                subprocess.Popen(["steam", "-silent"], start_new_session=True,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ------------------------------------------------------------------- misc
    @Property(str, constant=True)
    def version(self):
        return __version__

    @Property(str, constant=True)
    def repoUrl(self):
        return REPO_URL

    @Property(str, constant=True)
    def configPath(self):
        return config_mod.CONFIG_PATH

    @Property(bool, constant=True)
    def displaySwitcher(self):
        return bool(shutil.which("display-switcher")
                    or os.path.exists(os.path.expanduser("~/.local/bin/display-switcher")))

    @Slot(result=str)
    def logText(self):
        try:
            r = subprocess.run(["journalctl", "--user", "-u", UNIT, "-n", "200", "-o", "short",
                                "--no-pager"], capture_output=True, text=True, timeout=5)
            return r.stdout
        except (OSError, subprocess.TimeoutExpired) as exc:
            return str(exc)

    @Slot(str)
    def openUrl(self, url):
        subprocess.Popen(["xdg-open", url], start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    @Slot()
    def openConfig(self):
        if not os.path.exists(config_mod.CONFIG_PATH):
            config_mod.save(self.cfg)
        self.openUrl(config_mod.CONFIG_PATH)

    def _write_autostart(self, on):
        try:
            if on:
                os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
                with open(AUTOSTART, "w") as f:
                    f.write("[Desktop Entry]\nType=Application\nName=Couchpad\n"
                            "Comment=Значок Couchpad в трее\nIcon=couchpad\n"
                            "Exec=couchpad app --tray\nX-KDE-autostart-phase=2\n"
                            "NoDisplay=true\n")
            elif os.path.exists(AUTOSTART):
                os.unlink(AUTOSTART)
        except OSError as exc:
            log.warning("autostart: %s", exc)

    def shutdown(self):
        self.alive = False
        if self.save_timer.isActive():
            self.save_timer.stop()
            self._save()
