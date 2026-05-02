"""
LupaApp – Screen Magnifier
Entry point: run this file directly or as a compiled executable.
"""
import os
import sys
import ctypes
import ctypes.wintypes
import threading
import tkinter as tk
from PIL import Image, ImageDraw

import pystray
from pystray import MenuItem as Item, Menu
from pynput import keyboard, mouse

# Ensure the app directory is on the path when running frozen (PyInstaller)
_BASE = (
    sys._MEIPASS
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
sys.path.insert(0, _BASE)

from magnifier import MagnifierOverlay          # noqa: E402
from settings import load_config, save_config, SettingsDialog  # noqa: E402


# ── Windows RegisterHotKey helper ─────────────────────────────────────────────
# Removed _WinHotkey because RegisterHotKey doesn't support combinations like q+w+e



# ── Main application ──────────────────────────────────────────────────────────

class LupaApp:
    def __init__(self):
        self.config = load_config()
        # Migrate old default hotkey to new default
        hk = self.config.get("hotkey", [])
        if hk == ["ctrl", "shift", "m"] or "alt" in hk:
            self.config["hotkey"] = ["q", "w", "e"]
            save_config(self.config)

        # Tkinter root (hidden – only used as event-loop host)
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("LupaApp")

        self.magnifier = MagnifierOverlay(self.root, self.config)

        # Modifier-key state tracked for scroll-event routing
        self._ctrl_held  = False
        self._shift_held = False
        self._kb         = None   # pynput Listener

        self._start_kb_listener()
        self._start_mouse_listener()
        self._start_tray()
        self._keep_alive()

    def _keep_alive(self):
        # Wakes up the Tkinter event loop periodically to process events 
        # queued from background threads (like hotkey triggers).
        self.root.after(50, self._keep_alive)

    # ── keyboard / hotkey ─────────────────────────────────────────

    def _start_kb_listener(self):
        def on_activate():
            print("Hotkey triggered! Toggling magnifier...", flush=True)
            # Called from background thread – schedule on tk main loop
            self.root.after(0, self.magnifier.toggle)

        _CTRL  = {keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r}
        _SHIFT = {keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r}
        _ALT   = {keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r, keyboard.Key.alt_gr}

        self._pressed_keys = set()
        self._hotkey_triggered = False

        def get_key_name(key):
            if key in _CTRL: return "ctrl"
            if key in _SHIFT: return "shift"
            if key in _ALT: return "alt"
            if hasattr(key, 'char') and key.char:
                return key.char.lower()
            if hasattr(key, 'vk') and key.vk:
                if 32 <= key.vk <= 126:
                    return chr(key.vk).lower()
            return None

        def on_press(key):
            if key in _CTRL: self._ctrl_held = True
            elif key in _SHIFT: self._shift_held = True
            
            k_name = get_key_name(key)
            if k_name:
                self._pressed_keys.add(k_name)
                
            hk = set(self.config.get("hotkey", ["q", "w", "e"]))
            if hk.issubset(self._pressed_keys):
                if not self._hotkey_triggered:
                    self._hotkey_triggered = True
                    on_activate()

        def on_release(key):
            if key in _CTRL: self._ctrl_held = False
            elif key in _SHIFT: self._shift_held = False
            
            k_name = get_key_name(key)
            if k_name and k_name in self._pressed_keys:
                self._pressed_keys.remove(k_name)
                
            hk = set(self.config.get("hotkey", ["q", "w", "e"]))
            if not hk.issubset(self._pressed_keys):
                self._hotkey_triggered = False

        self._kb = keyboard.Listener(
            on_press=on_press, on_release=on_release, daemon=True)
        self._kb.start()

    # ── mouse scroll listener ─────────────────────────────────────

    def _start_mouse_listener(self):
        def on_scroll(x, y, dx, dy):
            if not self.magnifier.active:
                return
            direction = 1 if dy > 0 else -1
            if self._ctrl_held:
                delta = direction * 0.08
                self.root.after(0, lambda d=delta: self.magnifier.brightness_delta(d))
            elif self._shift_held:
                delta = direction * 0.08
                self.root.after(0, lambda d=delta: self.magnifier.contrast_delta(d))
            else:
                delta = direction * 0.25
                self.root.after(0, lambda d=delta: self.magnifier.zoom_delta(d))

        self._mouse = mouse.Listener(on_scroll=on_scroll, daemon=True)
        self._mouse.start()

    # ── system tray ───────────────────────────────────────────────

    @staticmethod
    def _make_tray_icon() -> Image.Image:
        img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        d.ellipse([4, 4, 44, 44], fill=(33, 150, 243, 255),
                  outline=(255, 255, 255, 200), width=3)
        d.line([37, 37, 60, 60], fill=(255, 255, 255, 220), width=6)
        d.line([14, 24, 34, 24], fill=(255, 255, 255, 160), width=2)
        d.line([24, 14, 24, 34], fill=(255, 255, 255, 160), width=2)
        return img

    def _start_tray(self):
        combo = "+".join(k.upper() for k in self.config.get("hotkey", ["q", "w", "e"]))

        menu = Menu(
            Item(f"Alternar lupa  ({combo})", self._tray_toggle, default=True),
            Item("Configuración…",            self._tray_settings),
            Menu.SEPARATOR,
            Item("Salir",                     self._tray_quit),
        )
        self._tray = pystray.Icon("LupaApp", self._make_tray_icon(),
                                  "Lupa de Pantalla", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def _tray_toggle(self, icon, item):
        self.root.after(0, self.magnifier.toggle)

    def _tray_settings(self, icon, item):
        self.root.after(0, self._open_settings)

    def _tray_quit(self, icon, item):
        self.root.after(0, self._quit)

    # ── settings dialog ───────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(self.root, self.config)
        self.root.wait_window(dlg.win)
        if dlg.result:
            self.config.update(dlg.result)
            save_config(self.config)
            self.magnifier.update_config(self.config)
            # Restart hotkey listeners with the new combo
            try:
                self._kb.stop()
            except Exception:
                pass
            self._start_kb_listener()

    # ── quit ──────────────────────────────────────────────────────

    def _quit(self):
        self.magnifier.destroy()
        try:
            self._tray.stop()
        except Exception:
            pass
        self.root.quit()

    # ── entry ─────────────────────────────────────────────────────

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    LupaApp().run()
