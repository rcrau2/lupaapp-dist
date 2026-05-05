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

class FloatingDashboard:
    def __init__(self, app, toggle_callback):
        self.app = app
        self.root = app.root
        self.toggle_callback = toggle_callback
        
        self.win = tk.Toplevel(self.root)
        self.win.overrideredirect(True)
        self.win.attributes('-topmost', True)
        self.win.attributes('-alpha', 0.5)
        self.win.configure(bg="#1a1a24")
        
        # Dimensions
        self.w = 65
        self.h = 470
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        self.win.geometry(f"{self.w}x{self.h}+{screen_width - self.w - 20}+{screen_height//2 - self.h//2}")
        
        self.canvas = tk.Canvas(self.win, width=self.w, height=self.h, bg="#1a1a24", highlightthickness=2, highlightbackground="#00ffcc")
        self.canvas.pack(fill="both", expand=True)
        
        # Draw Magnifier icon at top (toggle button)
        self.canvas.create_oval(15, 15, 50, 50, fill="#2a2a35", outline="#00ffcc", width=2)
        self.canvas.create_oval(25, 25, 37, 37, outline="#00ffcc", width=2)
        self.canvas.create_line(35, 35, 43, 43, fill="#00ffcc", width=3, capstyle=tk.ROUND)
        self.canvas.create_text(32, 65, text="ON/OFF", fill="#00ffcc", font=("Segoe UI", 7, "bold"))

        # Sliders properties
        self.sliders = []
        self._add_slider(85, "ZOOM", 8.0, 1.5, self.app.config.get("zoom", 2.0), self._on_zoom)
        self._add_slider(195, "BRILLO", 3.0, 0.2, self.app.config.get("brightness", 1.0), self._on_bri)
        self._add_slider(305, "CONTRASTE", 3.0, 0.2, self.app.config.get("contrast", 1.0), self._on_con)
        
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<Enter>", lambda e: self.win.attributes('-alpha', 0.85))
        self.canvas.bind("<Leave>", lambda e: self.win.attributes('-alpha', 0.5))
        
        # Draw Close App button (Professional Rounded Design)
        self._draw_round_rect(self.canvas, 10, 415, 55, 445, radius=12, fill="", outline="#cba6f7", width=2)
        self.close_btn_txt = self.canvas.create_text(32, 430, text="Cerrar", fill="#cba6f7", font=("Segoe UI", 9, "bold"), justify="center")
        
        self._drag_data = {"x": 0, "y": 0, "active_slider": None, "moved": False}
        
    def _draw_round_rect(self, canvas, x1, y1, x2, y2, radius=10, **kwargs):
        points = [x1+radius, y1, x1+radius, y1, x2-radius, y1, x2-radius, y1,
                  x2, y1, x2, y1+radius, x2, y1+radius, x2, y2-radius, x2, y2-radius,
                  x2, y2, x2-radius, y2, x2-radius, y2, x1+radius, y2, x1+radius, y2,
                  x1, y2, x1, y2-radius, x1, y2-radius, x1, y1+radius, x1, y1+radius, x1, y1]
        return canvas.create_polygon(points, smooth=True, **kwargs)
        
    def _add_slider(self, y, label, max_val, min_val, current_val, callback):
        # Draw rail
        self.canvas.create_text(32, y, text=label, fill="#89dceb", font=("Segoe UI", 7, "bold"))
        rail = self.canvas.create_rectangle(28, y+15, 36, y+95, fill="#333", outline="")
        fill = self.canvas.create_rectangle(28, y+15, 36, y+95, fill="#00ffcc", outline="")
        
        slider = {
            "y": y+15,
            "h": 80,
            "min": min_val,
            "max": max_val,
            "val": current_val,
            "cb": callback,
            "fill": fill
        }
        self.sliders.append(slider)
        self._update_slider_visual(slider)

    def _update_slider_visual(self, slider):
        pct = (slider["val"] - slider["min"]) / (slider["max"] - slider["min"])
        fill_h = slider["h"] * pct
        # Invert so max is at top
        self.canvas.coords(slider["fill"], 28, slider["y"] + slider["h"] - fill_h, 36, slider["y"] + slider["h"])

    def _on_zoom(self, val):
        self.app.magnifier.set_zoom(val)
    def _on_bri(self, val):
        self.app.magnifier.set_brightness(val)
    def _on_con(self, val):
        self.app.magnifier.set_contrast(val)

    def _on_press(self, event):
        self._drag_data["x"] = event.x
        self._drag_data["y"] = event.y
        self._drag_data["moved"] = False
        self._drag_data["active_slider"] = None
        
        if event.y < 70:
            # Clicked power button area
            self.toggle_callback()
            return
            
        if event.y > 400:
            # Clicked close button area
            self.app.hide_to_tray()
            return
            
        # Check sliders
        for s in self.sliders:
            if s["y"] - 10 <= event.y <= s["y"] + s["h"] + 10:
                self._drag_data["active_slider"] = s
                self._handle_slider_drag(s, event.y)
                return

    def _on_drag(self, event):
        s = self._drag_data["active_slider"]
        if s:
            self._handle_slider_drag(s, event.y)
        else:
            self._drag_data["moved"] = True
            # Move window
            x = self.win.winfo_x() - self._drag_data["x"] + event.x
            y = self.win.winfo_y() - self._drag_data["y"] + event.y
            self.win.geometry(f"+{x}+{y}")

    def _handle_slider_drag(self, s, my):
        # Clamp to slider bounds
        my = max(s["y"], min(my, s["y"] + s["h"]))
        # Calculate percentage (inverted because Y increases downwards)
        pct = 1.0 - ((my - s["y"]) / s["h"])
        s["val"] = s["min"] + pct * (s["max"] - s["min"])
        self._update_slider_visual(s)
        s["cb"](s["val"])
        
    def is_hovered(self, mx, my):
        x = self.win.winfo_x()
        y = self.win.winfo_y()
        return x <= mx <= x + self.w and y <= my <= y + self.h

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

        self.magnifier = MagnifierOverlay(self.root, self.config, self)

        # Create the magical infallible floating dashboard
        self.floating_dashboard = FloatingDashboard(self, self.magnifier.toggle)

        self._start_mouse_listener()
        self._start_tray()

    # ── mouse listener ────────────────────────────────────────────

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
            Item("Salir Completamente",       self._tray_quit),
        )
        self._tray = pystray.Icon("LupaApp", self._make_tray_icon(),
                                  "Lupa de Pantalla", menu)
        threading.Thread(target=self._tray.run, daemon=True).start()

    def hide_to_tray(self):
        self.magnifier.hide()
        self.floating_dashboard.win.withdraw()

    def toggle_dashboard(self):
        if self.floating_dashboard.win.state() == "withdrawn":
            self.floating_dashboard.win.deiconify()
        else:
            self.hide_to_tray()

    def _tray_toggle(self, icon, item):
        self.root.after(0, self.toggle_dashboard)

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
        if hasattr(self, 'floating_dashboard'):
            self.floating_dashboard.win.destroy()
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
