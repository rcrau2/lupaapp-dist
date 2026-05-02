import json
import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path

CONFIG_FILE = Path.home() / ".magnifier_lupa" / "config.json"

DEFAULT = {
    "hotkey": ["q", "w", "e"],
    "zoom": 2.0,
    "brightness": 1.0,
    "contrast": 1.0,
    "lens_size": 220,
}

MODIFIERS = ["ctrl", "shift", "alt"]
KEYS = list("abcdefghijklmnopqrstuvwxyz") + [str(i) for i in range(10)]
ALL_KEYS = MODIFIERS + KEYS


def load_config():
    if CONFIG_FILE.exists():
        try:
            return {**DEFAULT, **json.loads(CONFIG_FILE.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return DEFAULT.copy()


def save_config(cfg):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


# ── colour palette ────────────────────────────────────────────────
BG = "#1e1e2e"
FG = "#cdd6f4"
ACCENT = "#89b4fa"
MUTED = "#6c7086"
SURFACE = "#313244"


class SettingsDialog:
    def __init__(self, parent, config):
        self.result = None
        self._cfg = config.copy()

        self.win = tk.Toplevel(parent)
        self.win.title("Configuración – Lupa de Pantalla")
        self.win.geometry("460x540")
        self.win.resizable(False, False)
        self.win.configure(bg=BG)
        self.win.grab_set()
        self.win.focus_force()

        self._build()

    # ── UI construction ───────────────────────────────────────────

    def _build(self):
        self._apply_style()

        tk.Label(
            self.win,
            text="⚙  Configuración de Lupa",
            font=("Segoe UI", 14, "bold"),
            bg=BG,
            fg=ACCENT,
        ).pack(pady=(20, 10))

        self._build_hotkey_section()
        self._build_sliders_section()
        self._build_controls_hint()
        self._build_buttons()

    def _apply_style(self):
        s = ttk.Style(self.win)
        s.theme_use("clam")
        s.configure("TCombobox", fieldbackground=SURFACE, background=SURFACE, foreground=FG)
        s.map("TCombobox", fieldbackground=[("readonly", SURFACE)])

    def _lframe(self, text):
        f = tk.LabelFrame(
            self.win,
            text=f"  {text}  ",
            font=("Segoe UI", 9),
            bg=BG,
            fg=MUTED,
            bd=1,
            relief="groove",
        )
        f.pack(fill="x", padx=20, pady=6)
        return f

    def _build_hotkey_section(self):
        frame = self._lframe("Atajo de teclado  (3 teclas)")
        row = tk.Frame(frame, bg=BG)
        row.pack(padx=12, pady=10)

        hk = self._cfg.get("hotkey", ["q", "w", "e"])

        def combo(values, default, col):
            tk.Label(row, text=f"Tecla {col+1}:", bg=BG, fg=FG,
                     font=("Segoe UI", 9)).grid(row=0, column=col * 2, padx=(0, 4))
            cb = ttk.Combobox(row, values=values, width=6, state="readonly")
            cb.set(default)
            cb.grid(row=0, column=col * 2 + 1, padx=(0, 10))
            return cb

        self._key1 = combo(ALL_KEYS, hk[0] if len(hk) > 0 else "q", 0)
        self._key2 = combo(ALL_KEYS, hk[1] if len(hk) > 1 else "w", 1)
        self._key3 = combo(ALL_KEYS, hk[2] if len(hk) > 2 else "e", 2)

        tk.Label(
            frame,
            text="Puede ser cualquier combinación de teclas y modificadores.",
            font=("Segoe UI", 8),
            bg=BG,
            fg=MUTED,
        ).pack(pady=(0, 8))

    def _build_sliders_section(self):
        frame = self._lframe("Valores por defecto")

        self._zoom_var = tk.DoubleVar(value=self._cfg.get("zoom", 2.0))
        self._bri_var = tk.DoubleVar(value=self._cfg.get("brightness", 1.0))
        self._con_var = tk.DoubleVar(value=self._cfg.get("contrast", 1.0))
        self._size_var = tk.IntVar(value=self._cfg.get("lens_size", 220))

        self._slider(frame, "Zoom inicial:", self._zoom_var, 1.5, 8.0, 0.1)
        self._slider(frame, "Brillo inicial:", self._bri_var, 0.2, 3.0, 0.05)
        self._slider(frame, "Contraste inicial:", self._con_var, 0.2, 3.0, 0.05)
        self._slider(frame, "Tamaño de lupa (px):", self._size_var, 120, 400, 10)

    def _slider(self, parent, label, var, from_, to, res):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill="x", padx=12, pady=3)
        tk.Label(row, text=label, bg=BG, fg=FG, font=("Segoe UI", 9),
                 width=24, anchor="w").pack(side="left")
        tk.Scale(
            row, variable=var, from_=from_, to=to, resolution=res,
            orient="horizontal", length=170, showvalue=True,
            bg=BG, fg=FG, troughcolor=SURFACE, highlightthickness=0,
            activebackground=ACCENT,
        ).pack(side="left")

    def _build_controls_hint(self):
        frame = self._lframe("Controles mientras la lupa está activa")
        lines = (
            "Rueda del ratón          →  Zoom  (+/-)\n"
            "Ctrl  +  Rueda           →  Brillo  (+/-)\n"
            "Shift  +  Rueda          →  Contraste  (+/-)"
        )
        tk.Label(frame, text=lines, font=("Consolas", 9), bg=BG, fg="#89dceb",
                 justify="left").pack(padx=12, pady=8)

    def _build_buttons(self):
        f = tk.Frame(self.win, bg=BG)
        f.pack(pady=14)
        tk.Button(f, text="  Guardar  ", command=self._save,
                  bg=ACCENT, fg=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", cursor="hand2", pady=6).pack(side="left", padx=10)
        tk.Button(f, text="  Cancelar  ", command=self.win.destroy,
                  bg=SURFACE, fg=FG, font=("Segoe UI", 10),
                  relief="flat", cursor="hand2", pady=6).pack(side="left", padx=10)

    # ── save ──────────────────────────────────────────────────────

    def _save(self):
        k1, k2, k3 = self._key1.get(), self._key2.get(), self._key3.get()
        if len(set([k1, k2, k3])) < 3:
            messagebox.showerror(
                "Error de configuración",
                "Las tres teclas deben ser distintas.",
                parent=self.win,
            )
            return
        self.result = {
            "hotkey": [k1, k2, k3],
            "zoom": round(float(self._zoom_var.get()), 2),
            "brightness": round(float(self._bri_var.get()), 2),
            "contrast": round(float(self._con_var.get()), 2),
            "lens_size": int(self._size_var.get()),
        }
        self.win.destroy()
