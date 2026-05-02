"""
LupaApp – Screen Magnifier
Entry point: run this file directly or as a compiled executable.
"""
import os
import sys
import ctypes
import ctypes.wintypes
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw

import pystray
from pystray import MenuItem as Item, Menu
from pynput import mouse
import threading

# Ensure the app directory is on the path when running frozen (PyInstaller)
_BASE = (
    sys._MEIPASS
    if getattr(sys, "frozen", False)
    else os.path.dirname(os.path.abspath(__file__))
)
sys.path.insert(0, _BASE)

from magnifier import MagnifierOverlay          # noqa: E402
from settings import load_config, save_config, SettingsDialog  # noqa: E402

class FloatingButton:
    def __init__(self, root, toggle_callback):
        self.root = root
        self.toggle_callback = toggle_callback
        
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.attributes('-alpha', 0.6)
        
        # Make the background fully transparent using a chroma key (magenta)
        self.win.attributes('-transparentcolor', 'magenta')
        
        size = 65
        self.win.geometry(f"{size}x{size}+0+0")
        
        self.canvas = tk.Canvas(self.win, width=size, height=size, bg="magenta", highlightthickness=0)
        self.canvas.pack()
        
        # Draw a sleek glass-like circle
        self.bg_oval = self.canvas.create_oval(5, 5, size-5, size-5, fill="#1a1a24", outline="#00ffcc", width=2)
        
        # Draw the magnifier icon
        self.canvas.create_oval(22, 22, 38, 38, outline="#00ffcc", width=3)
        self.canvas.create_line(36, 36, 48, 48, fill="#00ffcc", width=4, capstyle=tk.ROUND)
        
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Enter>", lambda e: self.win.attributes('-alpha', 1.0))
        self.canvas.bind("<Leave>", lambda e: self.win.attributes('-alpha', 0.6))
        
        self._drag_data = {"x": 0, "y": 0, "dragged": False}
        
        # Position at the right edge, vertically centered
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        self.win.geometry(f"+{screen_width - size - 20}+{screen_height//2 - size//2}")

    def _on_press(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self._drag_data["dragged"] = False

    def _on_drag(self, event):
        self._drag_data["dragged"] = True
        x = self.win.winfo_x() - self._drag_data["x"] + event.x
        y = self.win.winfo_y() - self._drag_data["y"] + event.y
        self.win.geometry(f"+{x}+{y}")

    def _on_release(self, event):
        if not self._drag_data["dragged"]:
            self.toggle_callback()

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

        # Create the magical infallible floating button
        self.floating_btn = FloatingButton(self.root, self.magnifier.toggle)

        self._start_mouse_listener()
        self._start_tray()

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
        menu = Menu(
            Item("Alternar lupa (Boton Flotante)", self._tray_toggle, default=True),
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
        self.magnifier.destroy()
        if hasattr(self, 'floating_btn'):
            self.floating_btn.win.destroy()
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
