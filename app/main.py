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

        # Start background polling
        self._polling_active = True
        self._start_kb_listener()

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
        # We replace pynput with a rock-solid background polling loop using GetAsyncKeyState.
        # This completely bypasses hook timeouts and guarantees arbitrary key combinations.
        threading.Thread(target=self._poll_hotkey, daemon=True).start()

    def _poll_hotkey(self):
        import time
        import ctypes
        
        VK_MAP = {
            "ctrl": 0x11,
            "shift": 0x10,
            "alt": 0x12,
        }
        
        def get_vk(key_str):
            k = str(key_str).lower()
            if k in VK_MAP:
                return VK_MAP[k]
            if len(k) == 1:
                return ord(k.upper())
            return None

        triggered = False
        while getattr(self, '_polling_active', True):
            time.sleep(0.05)  # 50ms polling loop (20 checks per sec)
            
            hk = self.config.get("hotkey", ["q", "w", "e"])
            vks = [get_vk(k) for k in hk if k]
            vks = [vk for vk in vks if vk is not None]
            
            if not vks:
                continue
                
            all_pressed = True
            for vk in vks:
                state = ctypes.windll.user32.GetAsyncKeyState(vk)
                if not (state & 0x8000):
                    all_pressed = False
                    break
                    
            if all_pressed:
                if not triggered:
                    triggered = True
                    self.root.after(0, self.magnifier.toggle)
            else:
                triggered = False

    # ── mouse scroll listener ─────────────────────────────────────

    def _start_mouse_listener(self):
        def on_scroll(x, y, dx, dy):
            if not self.magnifier.active:
                return
            direction = 1 if dy > 0 else -1
            import ctypes
            ctrl_held = bool(ctypes.windll.user32.GetAsyncKeyState(0x11) & 0x8000)
            shift_held = bool(ctypes.windll.user32.GetAsyncKeyState(0x10) & 0x8000)
            
            if ctrl_held:
                delta = direction * 0.08
                self.root.after(0, lambda d=delta: self.magnifier.brightness_delta(d))
            elif shift_held:
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
            # Polling loop automatically picks up new config without restart

    # ── quit ──────────────────────────────────────────────────────

    def _quit(self):
        self._polling_active = False
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
