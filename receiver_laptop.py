"""
Receiver OsuKeys untuk laptop Windows (mode UDP).
Jalankan:  python receiver_laptop.py [port]
Kalau osu! dijalankan sebagai Administrator, jalankan script ini juga sebagai Administrator.
"""
import ctypes
import socket
import sys
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5005

# nama -> (scancode set 1, extended)
SC = {}
for c, s in zip("qwertyuiop", range(0x10, 0x1A)):
    SC[c] = (s, False)
for c, s in zip("asdfghjkl", range(0x1E, 0x27)):
    SC[c] = (s, False)
for c, s in zip("zxcvbnm", range(0x2C, 0x33)):
    SC[c] = (s, False)
for c, s in zip("1234567890", range(0x02, 0x0C)):
    SC[c] = (s, False)
SC.update({
    "esc": (0x01, False), "-": (0x0C, False), "=": (0x0D, False), "backspace": (0x0E, False),
    "tab": (0x0F, False), "[": (0x1A, False), "]": (0x1B, False), "enter": (0x1C, False),
    "lctrl": (0x1D, False), ";": (0x27, False), "'": (0x28, False), "`": (0x29, False),
    "lshift": (0x2A, False), "\\": (0x2B, False), ",": (0x33, False), ".": (0x34, False),
    "/": (0x35, False), "rshift": (0x36, False), "lalt": (0x38, False), "space": (0x39, False),
    "rctrl": (0x1D, True), "ralt": (0x38, True),
    "up": (0x48, True), "left": (0x4B, True), "right": (0x4D, True), "down": (0x50, True),
})
for i in range(10):
    SC["f%d" % (i + 1)] = (0x3B + i, False)
SC["f11"] = (0x57, False)
SC["f12"] = (0x58, False)

# --- SendInput (scancode) ---
PUL = ctypes.POINTER(ctypes.c_ulong)


class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]


class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong), ("wParamL", ctypes.c_short), ("wParamH", ctypes.c_ushort)]


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long), ("dy", ctypes.c_long), ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong), ("dwExtraInfo", PUL)]


class InputUnion(ctypes.Union):
    _fields_ = [("ki", KeyBdInput), ("mi", MouseInput), ("hi", HardwareInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong), ("ii", InputUnion)]


def press(name, up):
    if name not in SC:
        return
    scan, ext = SC[name]
    flags = 0x0008 | (0x0001 if ext else 0) | (0x0002 if up else 0)
    extra = ctypes.c_ulong(0)
    ii = InputUnion()
    ii.ki = KeyBdInput(0, scan, flags, 0, ctypes.pointer(extra))
    x = Input(ctypes.c_ulong(1), ii)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("0.0.0.0", PORT))
    sock.settimeout(0.05)
    try:
        ips = socket.gethostbyname_ex(socket.gethostname())[2]
    except Exception:
        ips = []
    print("Receiver aktif di port %d" % PORT)
    print("Isi salah satu IP ini di aplikasi HP:", ", ".join(ips))
    print("Ctrl+C untuk berhenti.")

    state = set()
    last = time.time()
    try:
        while True:
            try:
                data, _ = sock.recvfrom(1024)
                last = time.time()
                new = {k for k in data.decode(errors="ignore").split(",") if k and k != "-"}
                for k in new - state:
                    press(k, False)
                for k in state - new:
                    press(k, True)
                state = new
            except socket.timeout:
                # pengaman: kalau HP berhenti kirim heartbeat, lepas semua tombol
                if state and time.time() - last > 1.0:
                    for k in state:
                        press(k, True)
                    state = set()
    except KeyboardInterrupt:
        pass
    finally:
        for k in state:
            press(k, True)


if __name__ == "__main__":
    main()
