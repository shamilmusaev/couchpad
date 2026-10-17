import os
import signal
import tempfile
import unittest

from couchpad import procs

UID = 1000


def P(ppid, comm, cmd=None, uid=UID):
    return {"ppid": ppid, "comm": comm, "cmdline": cmd or [comm], "uid": uid}


def steam_tree():
    return {
        1: P(0, "systemd", uid=0),
        100: P(1, "systemd"),
        200: P(100, "steam", ["/home/u/.steam/ubuntu12_32/steam"]),
        300: P(200, "reaper", ["/home/u/.steam/ubuntu12_32/reaper",
                                "SteamLaunch", "AppId=1091500", "--", "proton"]),
        301: P(300, "python3", ["python3", "proton", "waitforexitandrun"]),
        302: P(301, "wine64-preloader", ["wine64", "Game.exe"]),
        303: P(302, "Game.exe"),
        304: P(300, "wineserver"),
        400: P(100, "plasmashell"),
        500: P(100, "kwin_wayland"),
        600: P(100, "firefox"),
        601: P(600, "Isolated Web Co"),
        700: P(100, "ghostty"),
        701: P(700, "bash"),
        800: P(1, "Xorg", uid=0),
        900: P(200, "reaper", ["/x/reaper", "SteamLaunch", "AppId=0", "--", "x"]),
    }


class FindTarget(unittest.TestCase):
    def test_game_window_kills_reaper_tree(self):
        self.assertEqual(procs.find_target(steam_tree(), 303, UID),
                         (300, "steam", "Steam AppId 1091500"))

    def test_any_process_inside_game(self):
        self.assertEqual(procs.find_target(steam_tree(), 302, UID)[0], 300)

    def test_shell_is_protected(self):
        t = steam_tree()
        for pid in (400, 500, 200, 700, 1):
            self.assertIsNone(procs.find_target(t, pid, UID), pid)

    def test_other_users_process(self):
        self.assertIsNone(procs.find_target(steam_tree(), 800, UID))

    def test_plain_app(self):
        self.assertEqual(procs.find_target(steam_tree(), 600, UID),
                         (600, "process", "firefox"))

    def test_unknown_pid(self):
        self.assertIsNone(procs.find_target(steam_tree(), 12345, UID))
        self.assertIsNone(procs.find_target(steam_tree(), 0, UID))

    def test_parent_loop_does_not_hang(self):
        t = {10: P(11, "a"), 11: P(10, "b")}
        self.assertEqual(procs.find_target(t, 10, UID), (10, "process", "a"))


class Fallback(unittest.TestCase):
    def test_latest_game(self):
        t = steam_tree()
        t[1000] = P(200, "reaper", ["/x/reaper", "SteamLaunch", "AppId=42", "--", "g"])
        t[1001] = P(1000, "game")
        self.assertEqual(procs.latest_steam_game(t, UID)[0], 1000)

    def test_ignores_appid_zero_and_empty(self):
        t = steam_tree()
        del t[301], t[302], t[303], t[304]
        self.assertIsNone(procs.latest_steam_game(t, UID))


class KillTree(unittest.TestCase):
    def run_kill(self, table, root, kind):
        sent = []
        n = procs.kill_tree(root, kind, table_fn=lambda: table,
                            kill=lambda p, s: sent.append((p, s)),
                            sleep=lambda s: None)
        return sent, n

    def test_steam_game(self):
        sent, n = self.run_kill(steam_tree(), 300, "steam")
        killed = {p for p, s in sent if s == signal.SIGKILL}
        self.assertEqual(killed, {301, 302, 303, 304})
        self.assertEqual(sent[-1], (300, signal.SIGTERM))
        for p in (200, 400, 500, 1):
            self.assertNotIn(p, {x for x, _ in sent})

    def test_plain_process_spares_protected_children(self):
        t = steam_tree()
        t[602] = P(600, "bash")
        sent, n = self.run_kill(t, 600, "process")
        pids = [p for p, _ in sent]
        self.assertIn(601, pids)
        self.assertNotIn(602, pids)
        self.assertEqual(sent[-1], (600, signal.SIGKILL))

    def test_process_already_gone(self):
        def gone(p, s):
            raise ProcessLookupError
        n = procs.kill_tree(300, "steam", table_fn=steam_tree, kill=gone,
                            sleep=lambda s: None)
        self.assertEqual(n, 0)

    def test_never_kills_itself(self):
        t = steam_tree()
        t[os.getpid()] = P(303, "python3")
        sent, _ = self.run_kill(t, 300, "steam")
        self.assertNotIn(os.getpid(), [p for p, _ in sent])

    def test_real_process_tree(self):
        """Spawn a real parent/child pair and kill it for real."""
        import subprocess
        import time
        parent = subprocess.Popen(["sh", "-c", "sleep 60 & sleep 60 & wait"])
        time.sleep(0.2)
        table = procs.read_table()
        kids = procs.descendants(table, parent.pid)
        self.assertEqual(len(kids), 2)
        procs.kill_tree(parent.pid, "process")
        parent.wait(timeout=5)
        time.sleep(0.2)
        table = procs.read_table()
        for k in kids:
            self.assertTrue(k not in table or table[k]["comm"] != "sleep")


class ReadTable(unittest.TestCase):
    def test_parses_odd_comm(self):
        with tempfile.TemporaryDirectory() as d:
            os.makedirs(f"{d}/42")
            with open(f"{d}/42/stat", "w") as f:
                f.write("42 (Web Content (x)) S 7 42 42 0 -1 4194560 0 0")
            with open(f"{d}/42/cmdline", "wb") as f:
                f.write(b"/usr/bin/a\0--flag\0")
            os.makedirs(f"{d}/self")
            t = procs.read_table(d)
            self.assertEqual(t[42]["comm"], "Web Content (x)")
            self.assertEqual(t[42]["ppid"], 7)
            self.assertEqual(t[42]["state"], "S")
            self.assertEqual(t[42]["cmdline"], ["/usr/bin/a", "--flag"])

    def test_real_proc_contains_me(self):
        t = procs.read_table()
        self.assertIn(os.getpid(), t)
        self.assertEqual(t[os.getpid()]["ppid"], os.getppid())


if __name__ == "__main__":
    unittest.main()


class SteamRunning(unittest.TestCase):
    def test_zombie_steam_is_not_running(self):
        from unittest import mock
        from couchpad import system
        uid = os.getuid()
        zombie = {1: {"comm": "steam", "uid": uid, "state": "Z", "ppid": 0, "cmdline": []}}
        alive = {1: {"comm": "steam", "uid": uid, "state": "S", "ppid": 0, "cmdline": []}}
        with mock.patch.object(procs, "read_table", return_value=zombie):
            self.assertFalse(system.steam_running())
        with mock.patch.object(procs, "read_table", return_value=alive):
            self.assertTrue(system.steam_running())
