import time
import tkinter as tk
from PIL import Image, ImageTk, ImageEnhance, ImageDraw, ImageFont

import mss

try:
    import win32gui
    import win32con
    WIN32 = True
except ImportError:
    WIN32 = False

# This colour is used as the transparent key on Windows.
# Pixels that end up exactly (1,1,1) become see-through.
_TRANSPARENT_RGB = (1, 1, 1)
_TRANSPARENT_HEX = "#010101"

_HUD_DURATION = 1.5   # seconds to show the HUD label


class MagnifierOverlay:
    def __init__(self, root, config, app=None):
        self.root = root
        self.config = config
        self.app = app
        
        self.active = False
        self._sct = mss.mss()
        self._win = None
        self._canvas = None
        self._photo = None        # must stay alive (ImageTk GC)
        self._sct = mss.mss()

        self._hud_text = ""
        self._hud_until = 0.0
        self._frozen_screen = None
        self._screen_width = 0
        self._screen_height = 0

    # ── public API ────────────────────────────────────────────────

    def show(self):
        # 1. Capture the ENTIRE SCREEN before showing the window
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        raw = self._sct.grab({"left": 0, "top": 0, "width": sw, "height": sh})
        self._frozen_screen = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
        self._screen_width = sw
        self._screen_height = sh

        if not self._win:
            self._build_window()
        self.active = True
        self._win.deiconify()
        
        # Start keyboard listener for Escape key
        from pynput import keyboard
        def on_release(key):
            if key == keyboard.Key.esc:
                self.root.after(0, self.app.floating_dashboard.toggle_callback)
        self._esc_listener = keyboard.Listener(on_release=on_release)
        self._esc_listener.start()
        
        self._loop()

    def hide(self):
        self.active = False
        self._frozen_screen = None
        if hasattr(self, '_esc_listener') and self._esc_listener:
            self._esc_listener.stop()
            self._esc_listener = None
        if self._after_id:
            self.root.after_cancel(self._after_id)
            self._after_id = None
        if self._win:
            self._win.withdraw()

    def toggle(self):
        print(f"Magnifier toggle called. Current active state: {self.active}", flush=True)
        if self.active:
            self.hide()
        else:
            self.show()

    def destroy(self):
        self.hide()
        if self._win:
            self._win.destroy()
            self._win = None

    def update_config(self, config):
        """Called after settings change; rebuilds the window next show()."""
        self.config = config
        if self._win:
            self._win.destroy()
            self._win = None

    # ── control deltas (called from scroll events) ────────────────

    def zoom_delta(self, delta):
        val = max(1.5, min(10.0, self.config.get("zoom", 2.0) + delta))
        self.config["zoom"] = round(val, 2)
        self._show_hud(f"Zoom  {self.config['zoom']:.1f}×")

    def brightness_delta(self, delta):
        val = max(0.1, min(3.0, self.config.get("brightness", 1.0) + delta))
        self.config["brightness"] = round(val, 2)
        self._show_hud(f"Brillo  {self.config['brightness']:.2f}")

    def contrast_delta(self, delta):
        val = max(0.1, min(3.0, self.config.get("contrast", 1.0) + delta))
        self.config["contrast"] = round(val, 2)
        self._show_hud(f"Contraste  {self.config['contrast']:.2f}")

    # ── internal helpers ──────────────────────────────────────────

    def _show_hud(self, text):
        self._hud_text = text
        self._hud_until = time.monotonic() + _HUD_DURATION

    def _build_window(self):
        size = self.config.get("lens_size", 220)
        w = tk.Toplevel(self.root)
        w.withdraw()
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.configure(bg=_TRANSPARENT_HEX)
        w.attributes("-transparentcolor", _TRANSPARENT_HEX)
        c = tk.Canvas(w, width=size, height=size,
                      bg=_TRANSPARENT_HEX, highlightthickness=0)
        c.pack()
        self._win = w
        self._canvas = c
        w.update_idletasks()
        self._apply_clickthrough()

    def _apply_clickthrough(self):
        """Make the overlay transparent to mouse events (Windows only)."""
        if not WIN32:
            return
        try:
            hwnd = self._win.winfo_id()
            ex = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE)
            win32gui.SetWindowLong(
                hwnd,
                win32con.GWL_EXSTYLE,
                ex
                | win32con.WS_EX_LAYERED
                | win32con.WS_EX_TRANSPARENT
                | win32con.WS_EX_NOACTIVATE,
            )
            try:
                import win32api
                win32gui.SetLayeredWindowAttributes(hwnd, win32api.RGB(*_TRANSPARENT_RGB), 0, win32con.LWA_COLORKEY)
            except Exception:
                pass
        except Exception:
            pass

    # ── render loop ───────────────────────────────────────────────

    def _loop(self):
        if not self.active:
            return
        self._frame()
        self._after_id = self.root.after(30, self._loop)   # ~33 fps

    def _frame(self):
        if not self._win:
            return
        try:
            size = self.config.get("lens_size", 220)
            zoom = self.config.get("zoom", 2.0)
            bri = self.config.get("brightness", 1.0)
            con = self.config.get("contrast", 1.0)

            mx = self._win.winfo_pointerx()
            my = self._win.winfo_pointery()
            sw = self._win.winfo_screenwidth()
            sh = self._win.winfo_screenheight()
            
            # Smart hide if hovering over the dashboard
            if self.app and hasattr(self.app, 'floating_dashboard'):
                if self.app.floating_dashboard.is_hovered(mx, my):
                    self._win.attributes('-alpha', 0.0)
                    return
                else:
                    self._win.attributes('-alpha', 1.0)

            # Region to capture (clamp to screen bounds)
            cap = max(4, int(size / zoom))
            x1 = max(0, min(sw - cap, mx - cap // 2))
            y1 = max(0, min(sh - cap, my - cap // 2))

            if self._frozen_screen:
                img = self._frozen_screen.crop((x1, y1, x1 + cap, y1 + cap))
            else:
                img = Image.new("RGB", (cap, cap), "black")
                
            img = img.resize((size, size), Image.LANCZOS)

            if bri != 1.0:
                img = ImageEnhance.Brightness(img).enhance(bri)
            if con != 1.0:
                img = ImageEnhance.Contrast(img).enhance(con)

            img = self._make_circular(img, size)

            if self._hud_text and time.monotonic() < self._hud_until:
                img = self._draw_hud(img, size)

            # Compose onto a flat RGB image using the transparent colour as bg
            flat = Image.new("RGB", (size, size), _TRANSPARENT_RGB)
            flat.paste(img, mask=img.split()[3])

            # Center the window exactly on the cursor
            wx = mx - size // 2
            wy = my - size // 2
            
            # Keep within screen bounds slightly so it doesn't clip out completely if not needed, 
            # actually it's better to let it perfectly center even if it goes off-screen edge.
            
            self._win.geometry(f"{size}x{size}+{wx}+{wy}")
            self._photo = ImageTk.PhotoImage(flat)
            self._canvas.configure(width=size, height=size)
            self._canvas.delete("all")
            self._canvas.create_image(0, 0, anchor="nw", image=self._photo)

        except Exception as e:
            import traceback
            traceback.print_exc()
            pass   # silently skip bad frames (e.g. during resize)

    # ── image compositing ─────────────────────────────────────────

    def _make_circular(self, img: Image.Image, size: int) -> Image.Image:
        """Clip img to a circle, add a white border ring, return RGBA."""
        # Alpha mask: circle
        mask = Image.new("L", (size, size), 0)
        ImageDraw.Draw(mask).ellipse([2, 2, size - 2, size - 2], fill=255)

        rgba = img.convert("RGBA")
        rgba.putalpha(mask)

        # White border
        border = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        bd = ImageDraw.Draw(border)
        bd.ellipse([1, 1, size - 1, size - 1], outline=(255, 255, 255, 220), width=3)
        # Drop shadow (soft dark ring)
        bd.ellipse([0, 0, size, size], outline=(0, 0, 0, 80), width=1)

        return Image.alpha_composite(rgba, border)

    def _draw_hud(self, img: Image.Image, size: int) -> Image.Image:
        """Overlay a semi-transparent pill with the HUD text."""
        overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        d = ImageDraw.Draw(overlay)

        text = self._hud_text
        pill_w, pill_h = 170, 30
        px = (size - pill_w) // 2
        py = size - 50

        d.rounded_rectangle([px, py, px + pill_w, py + pill_h],
                             radius=12, fill=(0, 0, 0, 170))

        # Try a system font; fall back gracefully
        font = None
        try:
            font = ImageFont.truetype("C:/Windows/Fonts/segoeui.ttf", 14)
        except Exception:
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            except Exception:
                font = ImageFont.load_default()

        d.text(
            (size // 2, py + pill_h // 2),
            text,
            fill=(255, 255, 255, 230),
            anchor="mm",
            font=font,
        )
        return Image.alpha_composite(img, overlay)
