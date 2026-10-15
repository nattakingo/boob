"""
overlay.py - Overlay grafico trasparente e click-through sopra il gioco.

Disegna i riquadri degli slot rilevati *direttamente sopra* la finestra di
Albion, alle coordinate reali, cosi' vedi in tempo reale cosa il bot "pensa".

Caratteristiche:
  - trasparente: vedi il gioco sotto (trucco del colore chiave "magenta");
  - click-through: i click passano attraverso l'overlay (WS_EX_TRANSPARENT);
  - topmost: resta sopra la finestra di gioco.

Gira su un thread separato con il suo mainloop Tkinter; il thread principale
chiama `update(...)` per aggiornare il disegno.
"""

from __future__ import annotations

import sys
import threading
import tkinter as tk

TRANSPARENT_COLOR = "#ff00ff"  # magenta = colore che diventa invisibile

# Costanti Win32
_GWL_EXSTYLE = -20
_WS_EX_LAYERED = 0x00080000
_WS_EX_TRANSPARENT = 0x00000020
_WS_EX_TOOLWINDOW = 0x00000080


class Overlay:
    def __init__(self) -> None:
        self._items: list[tuple[int, int, int, int, str, str]] = []
        self._status: str = ""
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._root: tk.Tk | None = None
        self._canvas: tk.Canvas | None = None
        self._started = False

    # ---- API pubblica (thread-safe) ----
    def start(self) -> None:
        if self._started:
            return
        self._started = True
        self._thread = threading.Thread(target=self._run, name="overlay", daemon=True)
        self._thread.start()

    def update(self, items: list[tuple[int, int, int, int, str, str]], status: str = "") -> None:
        """items: lista di (x1, y1, x2, y2, colore_hex, etichetta)."""
        with self._lock:
            self._items = items
            self._status = status

    def stop(self) -> None:
        root = self._root
        if root is not None:
            try:
                root.after(0, root.quit)
            except tk.TclError:
                pass

    # ---- thread interno ----
    def _run(self) -> None:
        try:
            root = tk.Tk()
        except tk.TclError:
            return  # nessun display disponibile

        self._root = root
        root.overrideredirect(True)
        root.attributes("-topmost", True)
        try:
            root.attributes("-transparentcolor", TRANSPARENT_COLOR)
        except tk.TclError:
            pass

        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        root.geometry(f"{w}x{h}+0+0")
        root.configure(bg=TRANSPARENT_COLOR)

        canvas = tk.Canvas(root, width=w, height=h, bg=TRANSPARENT_COLOR,
                           highlightthickness=0, bd=0)
        canvas.pack()
        self._canvas = canvas

        root.update_idletasks()
        self._make_click_through(root)

        def tick() -> None:
            try:
                self._redraw()
                root.after(30, tick)
            except tk.TclError:
                pass

        root.after(30, tick)
        root.mainloop()

    def _redraw(self) -> None:
        canvas = self._canvas
        if canvas is None:
            return
        with self._lock:
            items = list(self._items)
            status = self._status

        canvas.delete("all")
        for x1, y1, x2, y2, color, label in items:
            canvas.create_rectangle(x1, y1, x2, y2, outline=color, width=2)
            if label:
                canvas.create_text(x1 + 3, y1 + 7, text=label, fill=color,
                                   anchor="w", font=("Consolas", 8))
        if status:
            canvas.create_text(12, 12, text=status, fill="#00ff88", anchor="nw",
                               font=("Consolas", 11, "bold"))

    @staticmethod
    def _make_click_through(root: tk.Tk) -> None:
        if sys.platform != "win32":
            return
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetParent(root.winfo_id())
        if not hwnd:
            hwnd = root.winfo_id()
        ex = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
        user32.SetWindowLongW(
            hwnd, _GWL_EXSTYLE,
            ex | _WS_EX_LAYERED | _WS_EX_TRANSPARENT | _WS_EX_TOOLWINDOW,
        )
