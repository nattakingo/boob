"""
calibrate.py - Tool di calibrazione.

Modalita':
  1) default            -> seleziona la region della finestra di loot
  2) --auto             -> seleziona (a) un dettaglio distintivo della finestra
                           (template) e (b) la region degli slot; salva il
                           template e imposta l'auto-detect.
  3) --item NOME        -> seleziona l'icona di un oggetto e la salva in
                           templates/items/NOME.png (per il filtro item).

Uso:
    python calibrate.py
    python calibrate.py --auto
    python calibrate.py --item Borsa_T8
    python calibrate.py --rows 4 --cols 5
"""

from __future__ import annotations

import dpi  # noqa: F401  (DPI awareness - deve essere il primo import)

import argparse
import sys
import tkinter as tk
from pathlib import Path

import cv2

from config import BASE_DIR, Settings, sync_search_region
from src.autodetect import WindowLocator
from src.screen import Screen
from src.vision import cell_box


def select_region(screen_info: dict, prompt: str) -> list[int] | None:
    origin_x = screen_info["left"]
    origin_y = screen_info["top"]
    width = screen_info["width"]
    height = screen_info["height"]

    root = tk.Tk()
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.attributes("-alpha", 0.30)
    root.geometry(f"{width}x{height}+{origin_x}+{origin_y}")
    root.configure(bg="black")

    canvas = tk.Canvas(root, width=width, height=height, bg="black",
                       highlightthickness=0, cursor="crosshair")
    canvas.pack(fill="both", expand=True)
    canvas.create_text(width // 2, 40, fill="white", font=("Segoe UI", 15, "bold"),
                       text=f"{prompt}  |  INVIO=conferma  ESC=annulla")

    state = {"x0": 0, "y0": 0, "rect": None}
    result: dict[str, list[int] | None] = {"region": None}

    def on_press(event: tk.Event) -> None:
        state["x0"], state["y0"] = event.x, event.y
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                                 outline="#00ff88", width=2)

    def on_drag(event: tk.Event) -> None:
        if state["rect"] is not None:
            canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)

    def on_release(event: tk.Event) -> None:
        x1, y1 = min(state["x0"], event.x), min(state["y0"], event.y)
        x2, y2 = max(state["x0"], event.x), max(state["y0"], event.y)
        if x2 - x1 < 5 or y2 - y1 < 5:
            return
        result["region"] = [x1 + origin_x, y1 + origin_y, x2 - x1, y2 - y1]

    def confirm(_event: tk.Event | None = None) -> None:
        root.destroy()

    def cancel(_event: tk.Event | None = None) -> None:
        result["region"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Return>", confirm)
    root.bind("<Escape>", cancel)
    root.focus_force()
    root.mainloop()
    return result["region"]


def _screen_info() -> dict:
    screen = Screen()
    info = screen.virtual_screen()
    screen.close()
    return info


def select_region_on_image(path: Path, origin: tuple[int, int], prompt: str) -> list[int] | None:
    """Mostra un PNG salvato e permette di selezionare una region trascinando.

    Le coordinate dell'immagine vengono convertite in coordinate schermo
    sommando `origin` (l'angolo in alto-sinistra della cattura).
    """
    import tkinter as tk

    root = tk.Tk()
    root.title(prompt)
    img = tk.PhotoImage(file=str(path))  # tenere il riferimento!
    w, h = img.width(), img.height()

    canvas = tk.Canvas(root, width=w, height=h, highlightthickness=0, cursor="crosshair")
    canvas.pack()
    canvas.create_image(0, 0, anchor="nw", image=img)
    canvas.create_text(10, 10, anchor="nw", fill="#00ff00",
                       font=("Segoe UI", 11, "bold"),
                       text=f"{prompt}  |  INVIO=conferma  ESC=annulla")
    canvas.image = img  # evita il garbage collector

    state = {"x0": 0, "y0": 0, "rect": None}
    result: dict[str, list[int] | None] = {"region": None}

    def on_press(event: tk.Event) -> None:
        state["x0"], state["y0"] = event.x, event.y
        if state["rect"] is not None:
            canvas.delete(state["rect"])
        state["rect"] = canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                                 outline="#00ff88", width=2)

    def on_drag(event: tk.Event) -> None:
        if state["rect"] is not None:
            canvas.coords(state["rect"], state["x0"], state["y0"], event.x, event.y)

    def on_release(event: tk.Event) -> None:
        x1, y1 = min(state["x0"], event.x), min(state["y0"], event.y)
        x2, y2 = max(state["x0"], event.x), max(state["y0"], event.y)
        if x2 - x1 < 5 or y2 - y1 < 5:
            return
        result["region"] = [x1 + origin[0], y1 + origin[1], x2 - x1, y2 - y1]

    def confirm(_e: tk.Event | None = None) -> None:
        root.destroy()

    def cancel(_e: tk.Event | None = None) -> None:
        result["region"] = None
        root.destroy()

    canvas.bind("<ButtonPress-1>", on_press)
    canvas.bind("<B1-Motion>", on_drag)
    canvas.bind("<ButtonRelease-1>", on_release)
    root.bind("<Return>", confirm)
    root.bind("<Escape>", cancel)
    root.focus_force()
    root.mainloop()
    return result["region"]


# --------------------------------------------------------------- modo default
def mode_region(cfg: Settings, rows: int, cols: int, no_preview: bool) -> int:
    region = select_region(_screen_info(), "Seleziona la FINESTRA DI LOOT (solo gli slot)")
    if not region:
        print("[calib] annullato")
        return 1
    cfg.region = region
    cfg.to_json()
    print(f"[calib] region salvata: {region}  (grid {cfg.rows}x{cfg.cols})")
    if not no_preview:
        _preview_grid(region, rows, cols)
    return 0


def _preview_grid(region: list[int], rows: int, cols: int) -> None:
    import numpy as np

    frame = Screen().grab(region)
    vis = frame.copy()
    h, w = vis.shape[:2]
    for r in range(rows):
        for c in range(cols):
            x1, y1, x2, y2 = cell_box([0, 0, w, h], rows, cols, r, c, 0)
            cv2.rectangle(vis, (x1, y1), (x2, y2), (0, 200, 255), 1)
    cv2.imwrite("calibration_preview.png", vis)
    print("[calib] anteprima salvata in calibration_preview.png")
    cv2.imshow(f"griglia {rows}x{cols} - premi un tasto per chiudere", np.hstack([vis]))
    cv2.waitKey(0)
    cv2.destroyAllWindows()


# --------------------------------------------------------------- modo --image
def mode_image(cfg: Settings, image: str, rows: int, cols: int) -> int:
    import numpy as np

    path = Path(image)
    if not path.is_absolute():
        path = BASE_DIR / path
    if not path.exists():
        print(f"[calib] immagine non trovata: {path}")
        return 1

    origin = (cfg.search_region[0], cfg.search_region[1])
    region = select_region_on_image(path, origin, "Seleziona la FINESTRA DI LOOT")
    if not region:
        print("[calib] annullato")
        return 1

    cfg.region = region
    cfg.rows = rows
    cfg.cols = cols
    cfg.to_json()
    print(f"[calib] region salvata: {region}  (grid {rows}x{cols})")

    full = cv2.imread(str(path))
    ox, oy = origin
    x, y, w, h = region
    crop = full[y - oy:y - oy + h, x - ox:x - ox + w].copy()
    if crop.size:
        for r in range(rows):
            for c in range(cols):
                x1, y1, x2, y2 = cell_box([0, 0, crop.shape[1], crop.shape[0]], rows, cols, r, c, 0)
                cv2.rectangle(crop, (x1, y1), (x2, y2), (0, 200, 255), 1)
                cv2.putText(crop, f"{r},{c}", (x1 + 2, y1 + 11),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 200, 255), 1, cv2.LINE_AA)
        out = "calibration_preview.png"
        cv2.imwrite(out, crop)
        print(f"[calib] anteprima salvata: {out}  -> aprilo per controllare la griglia")
        cv2.imshow(f"griglia {rows}x{cols} - premi un tasto per chiudere", np.hstack([crop]))
        cv2.waitKey(0)
        cv2.destroyAllWindows()
    return 0


# --------------------------------------------------------------- modo 2 selezioni
def _source_and_selector(cfg: Settings, image: str | None):
    """Prepara immagine di riferimento + funzione di selezione (live o su immagine)."""
    origin = (cfg.search_region[0], cfg.search_region[1])
    if image:
        path = Path(image)
        if not path.is_absolute():
            path = BASE_DIR / path
        if not path.exists():
            return None, origin, None
        img = cv2.imread(str(path))
        if img is None:
            return None, origin, None
        return img, origin, (lambda prompt: select_region_on_image(path, origin, prompt))

    # live: catturo subito lo schermo (cosi' l'anteprima usa la stessa "foto")
    info = _screen_info()
    screen = Screen()
    img = screen.grab(cfg.search_region)
    screen.close()
    return img, origin, (lambda prompt: select_region(info, prompt))


def _preview_from_image(img, origin: tuple[int, int], region: list[int],
                        rows: int, cols: int, trim_bottom: int = 0) -> None:
    import numpy as np

    ox, oy = origin
    x, y, w, h = region
    crop = img[y - oy:y - oy + h, x - ox:x - ox + w].copy()
    if crop.size == 0:
        return
    for r in range(rows):
        for c in range(cols):
            x1, y1, x2, y2 = cell_box([0, 0, crop.shape[1], crop.shape[0]], rows, cols,
                                      r, c, 0, trim_bottom)
            cv2.rectangle(crop, (x1, y1), (x2, y2), (0, 200, 255), 1)
            cv2.putText(crop, f"{r},{c}", (x1 + 2, y1 + 11),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (0, 200, 255), 1, cv2.LINE_AA)
    cv2.imwrite("calibration_preview.png", crop)
    print("[calib] anteprima salvata: calibration_preview.png  -> controllala!")
    cv2.imshow(f"verifica griglia {rows}x{cols} (premi un tasto)", np.hstack([crop]))
    cv2.waitKey(0)
    cv2.destroyAllWindows()


def mode_cells(cfg: Settings, image: str | None = None) -> int:
    """Due selezioni: (1) tutto il blocco delle celle, (2) una singola cella.

    Righe e colonne vengono calcolate automaticamente.
    """
    img, origin, sel = _source_and_selector(cfg, image)
    if sel is None:
        print("[calib] immagine non trovata")
        return 1

    block = sel("1/2 - Seleziona TUTTO IL BLOCCO DELLE CELLE (solo le caselle degli slot)")
    if not block:
        print("[calib] annullato")
        return 1

    cell = sel("2/2 - Seleziona UNA SOLA CELLA (un singolo slot, al centro)")
    if not cell:
        print("[calib] annullato")
        return 1

    bx, by, bw, bh = block
    _, _, cw, ch = cell

    # Albion: la griglia ha SEMPRE 4 colonne fisse. Le righe visibili le
    # ricaviamo dall'altezza di una cella.
    cols = max(1, cfg.cols)
    rows = max(1, round(bh / ch))

    cfg.region = [bx, by, bw, bh]
    cfg.rows = rows
    cfg.cols = cols
    # l'icona dell'item e' piu' bassa della cella: ritagliamo il fondo in modo che
    # i riquadri aderiscano all'item (solo se la cella singola e' piu' bassa).
    cfg.cell_trim_bottom = max(0, int(round(bh / rows - ch)))
    cfg.to_json()

    print(f"[calib] blocco celle = {bw}x{bh}px, cella singola = {cw}x{ch}px")
    print(f"[calib] => righe={rows}  colonne={cols} (fisse)  "
          f"(cella risultante {bw / cols:.0f}x{bh / rows:.0f}px, "
          f"trim_bottom={cfg.cell_trim_bottom})")

    attesa = bw / cols
    if cw > 0 and abs(attesa - cw) > max(6.0, 0.20 * cw):
        print("[calib][avviso] la cella che hai selezionato non combacia con la "
              "larghezza del blocco diviso 4. Trascina il blocco piu' aderente "
              "alle 4 colonne (senza bordi ne' barra di scorrimento).")

    _preview_from_image(img, origin, cfg.region, rows, cols, cfg.cell_trim_bottom)
    return 0


# --------------------------------------------------------------- modo --auto
def mode_auto(cfg: Settings) -> int:
    info = _screen_info()

    tmpl_region = select_region(info, "1/2 - Seleziona un DETTAGLIO FISSO della finestra (cornice/angolo)")
    if not tmpl_region:
        print("[calib] annullato")
        return 1

    loot_region = select_region(info, "2/2 - Seleziona la REGION DEGLI SLOT")
    if not loot_region:
        print("[calib] annullato")
        return 1

    screen = Screen()
    tmpl_img = screen.grab(tmpl_region)
    screen.close()

    path = Path(cfg.template_path)
    if not path.is_absolute():
        path = BASE_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), tmpl_img)

    tx, ty, _, _ = tmpl_region
    lx, ly, lw, lh = loot_region
    cfg.auto_region = [lx - tx, ly - ty, lw, lh]
    cfg.region = loot_region
    cfg.auto_detect = True
    cfg.to_json()

    print(f"[calib] template salvato: {path}  ({tmpl_region[2]}x{tmpl_region[3]})")
    print(f"[calib] offset loot dal template: {cfg.auto_region}")
    print("[calib] auto-detect ATTIVATO")

    _verify_auto(cfg)
    return 0


def _verify_auto(cfg: Settings) -> None:
    locator = WindowLocator(cfg)
    if not locator.loaded:
        print("[calib] attenzione: template non caricabile")
        return
    screen = Screen()
    frame = screen.grab(cfg.search_region)
    screen.close()
    sx, sy = cfg.search_region[0], cfg.search_region[1]
    region = locator.locate(frame, (sx, sy))
    score = locator.last_match_score(frame)
    print(f"[calib] verifica: match={score:.2f}  region trovata={region}")


# --------------------------------------------------------------- modo --item
def mode_item(cfg: Settings, name: str) -> int:
    region = select_region(_screen_info(), f"Seleziona l'ICONA dell'oggetto '{name}'")
    if not region:
        print("[calib] annullato")
        return 1

    safe = "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in name)
    dir_path = Path(cfg.items_dir)
    if not dir_path.is_absolute():
        dir_path = BASE_DIR / dir_path
    dir_path.mkdir(parents=True, exist_ok=True)
    path = dir_path / f"{safe}.png"

    screen = Screen()
    img = screen.grab(region)
    screen.close()
    cv2.imwrite(str(path), img)
    print(f"[calib] icona salvata: {path}  ({region[2]}x{region[3]})")
    print("[calib] usa --items per attivare il filtro (soglia: item_match_threshold)")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Calibrazione del bot")
    p.add_argument("--auto", action="store_true",
                   help="calibra auto-detect (template + region)")
    p.add_argument("--item", metavar="NOME", help="salva un'icona oggetto per il filtro item")
    p.add_argument("--image", metavar="PATH", help="usa uno screenshot salvato invece dello schermo")
    p.add_argument("--region", action="store_true",
                   help="(avanzato) singola selezione region + righe/colonne a mano")
    p.add_argument("--rows", type=int, help="solo con --region")
    p.add_argument("--cols", type=int, default=4,
                   help="numero di colonne (Albion: 4 fisse)")
    p.add_argument("--no-preview", action="store_true")
    args = p.parse_args()

    cfg = Settings.load()
    sync_search_region(cfg)
    cfg.cols = args.cols
    if args.rows:
        cfg.rows = args.rows

    if args.item:
        return mode_item(cfg, args.item)
    if args.auto:
        return mode_auto(cfg)
    if args.region:
        if args.image:
            return mode_image(cfg, args.image, cfg.rows, cfg.cols)
        print(f"[calib] schermo virtuale: {_screen_info()}")
        return mode_region(cfg, cfg.rows, cfg.cols, args.no_preview)

    # default: due selezioni (blocco celle + una cella) -> righe/colonne automatiche
    if not args.image:
        print(f"[calib] schermo virtuale: {_screen_info()}")
    return mode_cells(cfg, args.image)


if __name__ == "__main__":
    sys.exit(main())
