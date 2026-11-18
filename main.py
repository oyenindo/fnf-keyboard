"""
OsuKeys - keyboard osu!mania di Android (Kivy) dengan hitbox ala FNF.

Mode koneksi ke laptop:
  1. UDP  : HP -> kabel OTG (USB Tethering) / WiFi -> receiver_laptop.py. Tanpa root.
  2. HID  : HP jadi keyboard USB asli lewat OTG (/dev/hidg0). Butuh root + kernel support
            (jalankan setup_hid.sh dulu).
"""
import colorsys
import json
import os
import socket
import subprocess

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle, Triangle
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import NoTransition, Screen, ScreenManager
from kivy.uix.scrollview import ScrollView
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.utils import platform

# --------------------------------------------------------------------------
# Tabel tombol (nama -> HID usage ID)
# --------------------------------------------------------------------------
HID = {}
for _i, _c in enumerate("abcdefghijklmnopqrstuvwxyz"):
    HID[_c] = 0x04 + _i
for _i, _c in enumerate("1234567890"):
    HID[_c] = 0x1E + _i
HID.update({
    "space": 0x2C, "enter": 0x28, "esc": 0x29, "backspace": 0x2A, "tab": 0x2B,
    "-": 0x2D, "=": 0x2E, "[": 0x2F, "]": 0x30, "\\": 0x31, ";": 0x33,
    "'": 0x34, "`": 0x35, ",": 0x36, ".": 0x37, "/": 0x38,
    "right": 0x4F, "left": 0x50, "down": 0x51, "up": 0x52,
    "lctrl": 0xE0, "lshift": 0xE1, "lalt": 0xE2,
    "rctrl": 0xE4, "rshift": 0xE5, "ralt": 0xE6,
})
for _i in range(12):
    HID["f%d" % (_i + 1)] = 0x3A + _i
KEYNAMES = list(HID.keys())

DEFAULT_BINDS = {
    1: ["space"],
    2: ["f", "j"],
    3: ["f", "space", "j"],
    4: ["d", "f", "j", "k"],
    5: ["d", "f", "space", "j", "k"],
    6: ["s", "d", "f", "j", "k", "l"],
    7: ["s", "d", "f", "space", "j", "k", "l"],
    8: ["a", "s", "d", "f", "j", "k", "l", ";"],
    9: ["a", "s", "d", "f", "space", "j", "k", "l", ";"],
    10: ["a", "s", "d", "f", "v", "n", "j", "k", "l", ";"],
    11: ["a", "s", "d", "f", "v", "space", "n", "j", "k", "l", ";"],
    12: ["q", "w", "e", "r", "a", "s", "d", "f", "j", "k", "l", ";"],
}

MODE_LABELS = {
    "udp": "UDP (USB tethering / WiFi)",
    "hid": "HID root (/dev/hidg0)",
}
LABEL_TO_MODE = {v: k for k, v in MODE_LABELS.items()}


# --------------------------------------------------------------------------
# Output ke laptop
# --------------------------------------------------------------------------
class Output:
    def __init__(self):
        self.mode = "udp"
        self.sock = None
        self.target = ("192.168.42.100", 5005)
        self.hid = None
        self.proc = None
        self.state = set()
        self.error = ""

    def configure(self, cfg):
        self.close()
        self.mode = cfg["mode"]
        self.state = set()
        self.error = ""
        if self.mode == "udp":
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self.sock.setblocking(False)
                self.target = (cfg["ip"], int(cfg["port"]))
            except Exception as e:
                self.error = str(e)
        else:
            self._open_hid()

    def close(self):
        for obj in (self.sock, self.hid):
            try:
                if obj:
                    obj.close()
            except Exception:
                pass
        if self.proc:
            try:
                self.proc.stdin.close()
                self.proc.terminate()
            except Exception:
                pass
        self.sock = self.hid = self.proc = None

    def _open_hid(self):
        try:
            self.hid = open("/dev/hidg0", "wb", buffering=0)
            return
        except Exception:
            self.hid = None
        try:
            # fallback: tulis lewat shell root
            self.proc = subprocess.Popen(
                ["su", "-c", "dd of=/dev/hidg0 bs=16 2>/dev/null"],
                stdin=subprocess.PIPE,
            )
        except Exception as e:
            self.error = "HID gagal: %s" % e

    def send(self, keys):
        self.state = set(keys)
        self._emit()
        if not self.state:
            self._emit()  # kirim 2x saat lepas, jaga-jaga paket UDP hilang

    def heartbeat(self, dt):
        if self.mode == "udp" and self.state:
            self._emit()

    def _emit(self):
        try:
            if self.mode == "udp":
                if self.sock:
                    data = ",".join(sorted(self.state)) or "-"
                    self.sock.sendto(data.encode(), self.target)
            else:
                report = bytearray(16)  # 1 byte modifier + 15 byte bitmap (NKRO)
                for name in self.state:
                    u = HID.get(name)
                    if u is None:
                        continue
                    if 0xE0 <= u <= 0xE7:
                        report[0] |= 1 << (u - 0xE0)
                    elif u < 120:
                        report[1 + u // 8] |= 1 << (u % 8)
                if self.hid:
                    self.hid.write(bytes(report))
                elif self.proc:
                    self.proc.stdin.write(bytes(report))
                    self.proc.stdin.flush()
        except Exception as e:
            self.error = str(e)


# --------------------------------------------------------------------------
# Hitbox ala FNF: kolom penuh layar, multi-touch, geser antar kolom
# --------------------------------------------------------------------------
FNF_COLORS = [(0.80, 0.20, 0.85), (0.20, 0.85, 0.90), (0.35, 0.95, 0.20), (0.95, 0.20, 0.20)]


def column_color(i, n):
    if n == 4:
        return FNF_COLORS[i]
    return colorsys.hsv_to_rgb((0.83 - 0.83 * i / max(1, n - 1)) % 1.0, 0.75, 0.95)


class Hitbox(FloatLayout):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        self.n = 4
        self.binds = []
        self.col_count = []
        self.touch_col = {}
        self.labels = []
        self.bind(pos=self.redraw, size=self.redraw)

    def setup(self, n, binds):
        self.n = n
        self.binds = list(binds)
        self.col_count = [0] * n
        self.touch_col = {}
        self.clear_widgets()
        self.labels = []
        for b in self.binds:
            lb = Label(text=b.upper(), bold=True, color=(1, 1, 1, 1),
                       halign="center", valign="middle")
            self.labels.append(lb)
            self.add_widget(lb)
        self.app.out.send(set())
        self.redraw()

    def redraw(self, *a):
        if not self.col_count:
            return
        n = self.n
        w = self.width / n
        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.05, 0.05, 0.07, 1)
            Rectangle(pos=self.pos, size=self.size)
            for i in range(n):
                r, g, b = column_color(i, n)
                pressed = self.col_count[i] > 0
                x = self.x + i * w
                Color(r, g, b, 0.50 if pressed else 0.13)
                Rectangle(pos=(x, self.y), size=(w, self.height))
                Color(r, g, b, 1)
                Line(rectangle=(x, self.y, w, self.height), width=dp(1.5))
                # penanda segitiga di bawah (seperti panah FNF)
                s = min(w * 0.55, dp(70))
                cx, cy = x + w / 2, self.y + self.height * 0.17
                pts = [cx - s / 2, cy - s / 2, cx + s / 2, cy - s / 2, cx, cy + s / 2]
                if pressed:
                    Color(r, g, b, 0.9)
                    Triangle(points=pts)
                else:
                    Color(r, g, b, 1)
                    Line(points=pts, close=True, width=dp(2))
        for i, lb in enumerate(self.labels):
            lb.size = (w, dp(36))
            lb.text_size = lb.size
            lb.font_size = min(sp(22), w * 0.32)
            lb.pos = (self.x + i * w, self.y + self.height * 0.17 - dp(26))

    def col_at(self, x):
        i = int((x - self.x) / self.width * self.n)
        return max(0, min(self.n - 1, i))

    def on_touch_down(self, t):
        if not self.collide_point(*t.pos):
            return False
        t.grab(self)
        self._assign(t, self.col_at(t.x))
        return True

    def on_touch_move(self, t):
        if t.grab_current is self:
            c = self.col_at(t.x)
            if self.touch_col.get(t.uid) != c:
                self._assign(t, c)
            return True
        return False

    def on_touch_up(self, t):
        if t.grab_current is self:
            self._assign(t, None)
            t.ungrab(self)
            return True
        return False

    def _assign(self, t, c):
        old = self.touch_col.pop(t.uid, None)
        if old is not None:
            self.col_count[old] -= 1
        if c is not None:
            self.touch_col[t.uid] = c
            self.col_count[c] += 1
        keys = {self.binds[i] for i in range(self.n) if self.col_count[i] > 0}
        self.app.out.send(keys)
        self.redraw()


class MenuButton(Button):
    """Tahan 0.7 detik untuk buka pengaturan (biar tidak kepencet saat main)."""
    _ev = None

    def on_press(self):
        self._ev = Clock.schedule_once(lambda dt: App.get_running_app().open_settings(), 0.7)

    def on_release(self):
        if self._ev:
            self._ev.cancel()
            self._ev = None


class PlayScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        root = FloatLayout()
        self.hitbox = Hitbox(app)
        root.add_widget(self.hitbox)
        btn = MenuButton(text="tahan: menu", size_hint=(None, None), size=(dp(120), dp(30)),
                         pos_hint={"center_x": 0.5, "top": 1}, font_size=sp(11),
                         background_color=(1, 1, 1, 0.25))
        root.add_widget(btn)
        self.status = Label(text="", size_hint=(None, None), size=(dp(300), dp(24)),
                            pos_hint={"x": 0.01, "top": 1}, font_size=sp(11),
                            halign="left", color=(1, 0.5, 0.5, 1))
        root.add_widget(self.status)
        self.add_widget(root)

    def on_enter(self):
        cfg = self.app.cfg
        n = cfg["keys"]
        self.hitbox.setup(n, self.app.get_binds(n))
        self.status.text = self.app.out.error

    def on_leave(self):
        self.app.out.send(set())


# --------------------------------------------------------------------------
# Pengaturan
# --------------------------------------------------------------------------
class SettingsScreen(Screen):
    def __init__(self, app, **kw):
        super().__init__(**kw)
        self.app = app
        root = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        sv = ScrollView()
        self.box = GridLayout(cols=1, size_hint_y=None, spacing=dp(8))
        self.box.bind(minimum_height=self.box.setter("height"))
        sv.add_widget(self.box)
        root.add_widget(sv)
        btn = Button(text="SIMPAN & MAIN", size_hint_y=None, height=dp(54))
        btn.bind(on_release=self.save)
        root.add_widget(btn)
        self.add_widget(root)

    def on_pre_enter(self):
        self.build()

    def _row(self, text, widget, h=46):
        row = BoxLayout(size_hint_y=None, height=dp(h), spacing=dp(8))
        row.add_widget(Label(text=text, size_hint_x=0.4, halign="left", valign="middle"))
        widget.size_hint_x = 0.6
        row.add_widget(widget)
        self.box.add_widget(row)
        return row

    def build(self):
        cfg = self.app.cfg
        self.box.clear_widgets()
        self.n = cfg["keys"]
        self.tmp_binds = {str(k): list(self.app.get_binds(k)) for k in range(1, 13)}

        self.mode_sp = Spinner(text=MODE_LABELS[cfg["mode"]], values=list(MODE_LABELS.values()))
        self._row("Mode koneksi", self.mode_sp)
        self.ip_in = TextInput(text=cfg["ip"], multiline=False, input_filter=None)
        self._row("IP laptop (UDP)", self.ip_in)
        self.port_in = TextInput(text=str(cfg["port"]), multiline=False, input_filter="int")
        self._row("Port (UDP)", self.port_in)

        self.n_label = Label(text="Jumlah key: %d" % self.n, size_hint_y=None, height=dp(30))
        self.box.add_widget(self.n_label)
        sl = Slider(min=1, max=12, step=1, value=self.n, size_hint_y=None, height=dp(44))
        sl.bind(value=self.on_n)
        self.box.add_widget(sl)

        self.rows = GridLayout(cols=1, size_hint_y=None, spacing=dp(6))
        self.rows.bind(minimum_height=self.rows.setter("height"))
        self.box.add_widget(self.rows)
        self.build_rows()

    def on_n(self, inst, val):
        self.n = int(val)
        self.n_label.text = "Jumlah key: %d" % self.n
        self.build_rows()

    def build_rows(self):
        self.rows.clear_widgets()
        binds = self.tmp_binds[str(self.n)]
        for i in range(self.n):
            row = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
            row.add_widget(Label(text="Key %d" % (i + 1), size_hint_x=0.4))
            sp_ = Spinner(text=binds[i], values=KEYNAMES, size_hint_x=0.6)
            try:
                sp_._dropdown.max_height = Window.height * 0.6
            except Exception:
                pass
            sp_.bind(text=lambda inst, val, idx=i: self.set_bind(idx, val))
            row.add_widget(sp_)
            self.rows.add_widget(row)

    def set_bind(self, idx, val):
        self.tmp_binds[str(self.n)][idx] = val

    def save(self, *a):
        cfg = self.app.cfg
        cfg["keys"] = self.n
        cfg["mode"] = LABEL_TO_MODE[self.mode_sp.text]
        cfg["ip"] = self.ip_in.text.strip()
        try:
            cfg["port"] = int(self.port_in.text)
        except ValueError:
            cfg["port"] = 5005
        cfg["binds"] = self.tmp_binds
        self.app.save_cfg()
        self.app.out.configure(cfg)
        self.app.sm.current = "play"


# --------------------------------------------------------------------------
# App
# --------------------------------------------------------------------------
def keep_awake():
    if platform != "android":
        return
    try:
        from android.runnable import run_on_ui_thread
        from jnius import autoclass
        Activity = autoclass("org.kivy.android.PythonActivity")

        @run_on_ui_thread
        def f():
            Activity.mActivity.getWindow().addFlags(128)  # FLAG_KEEP_SCREEN_ON
        f()
    except Exception:
        pass


class OsuKeysApp(App):
    title = "OsuKeys"

    def build(self):
        self.cfg_path = os.path.join(self.user_data_dir, "config.json")
        self.cfg = self.load_cfg()
        self.out = Output()
        self.out.configure(self.cfg)
        Window.clearcolor = (0.05, 0.05, 0.07, 1)

        self.sm = ScreenManager(transition=NoTransition())
        self.sm.add_widget(PlayScreen(self, name="play"))
        self.sm.add_widget(SettingsScreen(self, name="settings"))
        self.sm.current = "play"
        Clock.schedule_interval(self.out.heartbeat, 0.2)
        keep_awake()
        return self.sm

    def open_settings(self, *a):
        self.sm.current = "settings"

    def get_binds(self, n):
        binds = list(self.cfg["binds"].get(str(n), []))
        default = DEFAULT_BINDS[n]
        while len(binds) < n:
            binds.append(default[len(binds)])
        return binds[:n]

    def load_cfg(self):
        cfg = {"keys": 4, "mode": "udp", "ip": "192.168.42.100", "port": 5005, "binds": {}}
        try:
            with open(self.cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            cfg.update(data)
        except Exception:
            pass
        cfg["keys"] = max(1, min(12, int(cfg["keys"])))
        if cfg["mode"] not in MODE_LABELS:
            cfg["mode"] = "udp"
        return cfg

    def save_cfg(self):
        try:
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump(self.cfg, f, indent=2)
        except Exception:
            pass

    def on_pause(self):
        return True

    def on_stop(self):
        self.out.close()


if __name__ == "__main__":
    OsuKeysApp().run()
