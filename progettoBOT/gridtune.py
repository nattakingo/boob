r"""
gridtune.py - Regola la griglia a occhio, in tempo reale.

Apre lo screenshot `snapshots/loot.png` e mostra la regione + la griglia.
Trascini il rettangolo e cambi righe/colonne con i tasti finche' ogni cella
non combacia con un item. Poi salvi.

    python gridtune.py                       # usa snapshots/loot.png
    python gridtune.py --image snapshots\loot.png

Tasti:
    trascina col mouse  = seleziona la regione (finestra di loot)
    +  /  -             = aumenta / diminuisci RIGHE
    ]  /  [             = aumenta / diminuisci COLONNE
    frecce              = sposta la regione di 5px
    shift + frecce      = allarga/restringe di 5px
    n  /  m             = aumenta / diminuisci il taglio dal FONDO (aderenza item)
    S                   = salva in config.json
    ESC                 = esci senza salvare
"""

from __future__ import annotations

import dpi  # noqa: F401  (DPI awareness - deve essere il primo import)

import argparse
import sys
from pathlib import Path

import cv2
import tkinter as tk

from config import BASE_DIR, Settings
from src.vision import cell_box


class GridTuner:
    def __init__(self, path: Path, smoke: bool = False) -> None:
        self.img = cv2.imread(str(path))
        if self.img is None:
            raise SystemExit(f"[gridtune] immagine non leggibile: {path}")
        self.ih, self.iw = self.img.shape[:2]

        self.cfg = Settings.load()
        self.region = list(self.cfg.region)
        self.rows = max(1, self.cfg.rows)
        self.cols = max(1, self.cfg.cols)
        self.trim_bottom = max(0, self.cfg.cell_trim_bottom)

        self.root = tk.Tk()
        self.root.title("Grid Tuner  -  trascina | +/- righe | [ ] colonne | n/m trim | S salva | ESC esci")
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.cw = min(1500, sw - 40)
        self.ch = min(820, sh - 120)
        self.root.geometry(f"{self.cw}x{self.ch}+0+0")

        self.canvas = tk.Canvas(self.root, width=self.cw, height=self.ch,
                                bg="black", highlightthickness=0)
        self.canvas.pack()

        self.scale = min(self.cw / self.iw, self.ch / self.ih)
        disp = cv2.resize(self.img, (int(self.iw * self.scale), int(self.ih * self.scale)))
        ok, buf = cv2.imencode(".ppm", disp)
        self.photo = tk.PhotoImage(data=buf.tobytes())
        self.canvas.create_image(0, 0, anchor="nw", image=self.photo)

        self.status = ""
        self._drag0 = None
        self._bind()
        self.redraw()

        if smoke:
            self.root.after(900, self.root.destroy)

    # ------------------------------------------------------------- helpers
    def to_img(self, cx: int, cy: int) -> tuple[float, float]:
        return cx / self.scale, cy / self.scale

    def to_canvas(self, x: float, y: float) -> tuple[float, float]:
        return x * self.scale, y * self.scale

    # ------------------------------------------------------------- events
    def _bind(self) -> None:
        c = self.canvas
        c.bind("<ButtonPress-1>", self.on_press)
        c.bind("<B1-Motion>", self.on_drag)
        c.bind("<ButtonRelease-1>", self.on_release)
        self.root.bind("<plus>", lambda e: self._bump("rows", +1))
        self.root.bind("<equal>", lambda e: self._bump("rows", +1))
        self.root.bind("<KP_Add>", lambda e: self._bump("rows", +1))
        self.root.bind("<minus>", lambda e: self._bump("rows", -1))
        self.root.bind("<KP_Subtract>", lambda e: self._bump("rows", -1))
        self.root.bind("<bracketright>", lambda e: self._bump("cols", +1))
        self.root.bind("<bracketleft>", lambda e: self._bump("cols", -1))
        self.root.bind("<Up>", lambda e: self._move(0, -5))
        self.root.bind("<Down>", lambda e: self._move(0, 5))
        self.root.bind("<Left>", lambda e: self._move(-5, 0))
        self.root.bind("<Right>", lambda e: self._move(5, 0))
        self.root.bind("<Shift-Up>", lambda e: self._resize(0, -5))
        self.root.bind("<Shift-Down>", lambda e: self._resize(0, 5))
        self.root.bind("<Shift-Left>", lambda e: self._resize(-5, 0))
        self.root.bind("<Shift-Right>", lambda e: self._resize(5, 0))
        self.root.bind("<n>", lambda e: self._trim(+1))
        self.root.bind("<N>", lambda e: self._trim(+1))
        self.root.bind("<m>", lambda e: self._trim(-1))
        self.root.bind("<M>", lambda e: self._trim(-1))
        self.root.bind("<s>", lambda e: self.save())
        self.root.bind("<S>", lambda e: self.save())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.canvas.focus_set()

    def on_press(self, e) -> None:
        self._drag0 = self.to_img(e.x, e.y)

    def on_drag(self, e) -> None:
        if self._drag0 is None:
            return
        x1, y1 = self._drag0
        x2, y2 = self.to_img(e.x, e.y)
        self.region = [int(min(x1, x2)), int(min(y1, y2)),
                       int(abs(x2 - x1)), int(abs(y2 - y1))]
        self.redraw()

    def on_release(self, e) -> None:
        self._drag0 = None

    def _bump(self, what: str, d: int) -> None:
        if what == "rows":
            self.rows = max(1, self.rows + d)
        else:
            self.cols = max(1, self.cols + d)
        self.redraw()

    def _move(self, dx: int, dy: int) -> None:
        self.region[0] += dx
        self.region[1] += dy
        self.redraw()

    def _resize(self, dx: int, dy: int) -> None:
        self.region[2] = max(10, self.region[2] + dx)
        self.region[3] = max(10, self.region[3] + dy)
        self.redraw()

    def _trim(self, d: int) -> None:
        """Taglia/aggiunge pixel dal fondo della cella (per far aderire i riquadri)."""
        self.trim_bottom = max(0, self.trim_bottom + d)
        self.redraw()

    # ------------------------------------------------------------- drawing
    def redraw(self) -> None:
        c = self.canvas
        c.delete("grid")
        x, y, w, h = self.region

        # regione (verde)
        cx1, cy1 = self.to_canvas(x, y)
        cx2, cy2 = self.to_canvas(x + w, y + h)
        c.create_rectangle(cx1, cy1, cx2, cy2, outline="#00ff88", width=2, tags="grid")

        # celle (giallo)
        for r in range(self.rows):
            for col in range(self.cols):
                bx1, by1, bx2, by2 = cell_box(self.region, self.rows, self.cols,
                                              r, col, 0, self.trim_bottom)
                a1, b1 = self.to_canvas(bx1, by1)
                a2, b2 = self.to_canvas(bx2, by2)
                c.create_rectangle(a1, b1, a2, b2, outline="#00d0ff", width=1, tags="grid")
                c.create_text(a1 + 3, b1 + 8, text=f"{r},{col}", fill="#ffd000",
                              anchor="nw", font=("Consolas", 8), tags="grid")

        info = (f"region=[{x},{y},{w},{h}]  grid={self.rows}x{self.cols}  "
                f"cella={w/self.cols:.0f}x{h/self.rows:.0f}px  trim_fondo={self.trim_bottom}px   "
                f"| +- righe  [] colonne  n/m trim  S salva")
        c.delete("info")
        c.create_text(10, 10, text=info, fill="#00ff88", anchor="nw",
                      font=("Consolas", 12, "bold"), tags="info")

    # ------------------------------------------------------------- save
    def save(self) -> None:
        self.cfg.region = list(self.region)
        self.cfg.rows = self.rows
        self.cfg.cols = self.cols
        self.cfg.cell_trim_bottom = self.trim_bottom
        self.cfg.to_json()
        x, y, w, h = self.region
        crop = self.img[y:y + h, x:x + w].copy()
        for r in range(self.rows):
            for c in range(self.cols):
                bx1, by1, bx2, by2 = cell_box([0, 0, w, h], self.rows, self.cols,
                                              r, c, 0, self.trim_bottom)
                cv2.rectangle(crop, (bx1, by1), (bx2, by2), (0, 200, 255), 1)
        cv2.imwrite("calibration_preview.png", crop)
        print(f"[gridtune] salvato: region={self.region} grid={self.rows}x{self.cols} "
              f"cella={w/self.cols:.0f}x{h/self.rows:.0f}px")
        print("[gridtune] anteprima: calibration_preview.png")


def main() -> int:
    p = argparse.ArgumentParser(description="Regolazione interattiva della griglia")
    p.add_argument("--image", default="snapshots/loot.png")
    p.add_argument("--smoke", action="store_true", help="(test) chiude subito")
    args = p.parse_args()

    path = Path(args.image)
    if not path.is_absolute():
        path = BASE_DIR / path
    if not path.exists():
        print(f"[gridtune] immagine non trovata: {path}")
        print("[gridtune] prima fai:  python snapshot.py --delay 8")
        return 1
    GridTuner(path, smoke=args.smoke).root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
