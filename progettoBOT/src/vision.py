"""
vision.py - Riconoscimento della finestra di loot e degli slot pieni.

Come e' fatta la scheda di loot di Albion:
  - 4 colonne FISSE di slot quadrati;
  - SLOT VUOTO: superficie piatta, senza texture -> deviazione standard del grigio
    bassa e quasi nessun bordo;
  - SLOT PIENO: immagine dell'oggetto -> texture e bordi netti.

Strategia: dividiamo la region in una griglia rows x cols e per ogni cella
calcoliamo un punteggio di "texture". Uno slot e' PIENO se supera `fill_threshold`.

    score = deviazione_standard(grigio) * 0.8 + densita_bordi(Canny)

Sugli screenshot reali gli slot vuoti stanno attorno a 3-5 e quelli pieni a 60-75:
un distacco netto, facile da separare con la soglia.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from config import Settings


@dataclass
class Slot:
    row: int
    col: int
    x: int          # centro assoluto sullo schermo
    y: int
    score: float    # punteggio di texture (piu' alto = piu' probabilmente pieno)

    @property
    def pos(self) -> tuple[int, int]:
        return self.x, self.y


def cell_box(region: list[int], rows: int, cols: int, r: int, c: int,
             margin: int = 0, trim_bottom: int = 0) -> tuple[int, int, int, int]:
    """Coordinate assolute (x1, y1, x2, y2) di una cella.

    `margin` taglia da tutti i lati; `trim_bottom` taglia solo dal basso (per far
    aderire il riquadro all'icona, che e' piu' bassa della cella).
    """
    rx, ry, rw, rh = region
    cw = rw / cols
    ch = rh / rows
    x1 = int(rx + c * cw) + margin
    y1 = int(ry + r * ch) + margin
    x2 = int(rx + (c + 1) * cw) - margin
    y2 = int(ry + (r + 1) * ch) - margin - trim_bottom
    return x1, y1, x2, y2


def _cell_score(cell: np.ndarray) -> float:
    """Punteggio di texture di una cella (piu' alto = probabilmente piena).

    Combina la deviazione standard del grigio (gli item hanno texture, lo slot
    vuoto e' piatto) con la densita' di bordi (Canny).
    """
    if cell.size == 0:
        return 0.0
    gray = cv2.cvtColor(cell, cv2.COLOR_BGR2GRAY)
    std = float(gray.std())
    edges = cv2.Canny(gray, 40, 120)
    edge_density = float(np.count_nonzero(edges)) / edges.size * 100.0
    return std * 0.8 + edge_density * 1.0


def detect_slots(frame: np.ndarray, cfg: Settings,
                 region: list[int] | None = None) -> list[Slot]:
    """Analizza il frame (gia' ritagliato sulla region) e restituisce tutti gli slot."""
    region = region or cfg.region
    rx, ry = region[0], region[1]
    h, w = frame.shape[:2]
    slots: list[Slot] = []

    for r in range(cfg.rows):
        for c in range(cfg.cols):
            x1, y1, x2, y2 = cell_box([0, 0, w, h], cfg.rows, cfg.cols, r, c,
                                      cfg.slot_margin, cfg.cell_trim_bottom)
            cx = rx + int((c + 0.5) * (region[2] / cfg.cols))
            cy = ry + int((r + 0.5) * (region[3] / cfg.rows))
            if x2 <= x1 or y2 <= y1:
                slots.append(Slot(r, c, cx, cy, 0.0))
                continue
            cell = frame[max(0, y1):y2, max(0, x1):x2]
            slots.append(Slot(r, c, cx, cy, _cell_score(cell)))
    return slots


def cell_crop(frame: np.ndarray, cfg: Settings, row: int, col: int) -> np.ndarray:
    """Ritaglio dell'immagine (region) corrispondente a uno slot."""
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = cell_box([0, 0, w, h], cfg.rows, cfg.cols, row, col,
                              cfg.slot_margin, cfg.cell_trim_bottom)
    x1, y1 = max(0, x1), max(0, y1)
    return frame[y1:y2, x1:x2]


def filled_slots(slots: list[Slot], threshold: float) -> list[Slot]:
    """Filtra e ordina gli slot pieni (dall'alto a sinistra)."""
    full = [s for s in slots if s.score >= threshold]
    full.sort(key=lambda s: (s.row, s.col))
    return full


def find_template(frame: np.ndarray, template: np.ndarray,
                  threshold: float = 0.8) -> tuple[int, int, int, int] | None:
    """Template matching (restituisce (x, y, w, h) relativo al frame, o None)."""
    if template is None or template.size == 0:
        return None
    res = cv2.matchTemplate(frame, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(res)
    if max_val >= threshold:
        th, tw = template.shape[:2]
        return max_loc[0], max_loc[1], tw, th
    return None


def draw_debug(frame: np.ndarray, slots: list[Slot], threshold: float,
               trim_bottom: int = 0) -> np.ndarray:
    """Disegna la griglia e gli slot rilevati per il debug a video."""
    vis = frame.copy()
    h, w = vis.shape[:2]
    rows = int(round(max((s.row for s in slots), default=0) + 1))
    cols = int(round(max((s.col for s in slots), default=0) + 1))

    for s in slots:
        x1, y1, x2, y2 = cell_box([0, 0, w, h], rows, cols, s.row, s.col, 0, trim_bottom)
        is_full = s.score >= threshold
        color = (0, 255, 0) if is_full else (80, 80, 80)
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 1)
        cv2.putText(vis, f"{s.score:.0f}", (x1 + 2, y1 + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, color, 1, cv2.LINE_AA)
    return vis


def overlay_boxes(slots: list[Slot], region: list[int], rows: int, cols: int,
                  threshold: float, trim_bottom: int = 0
                  ) -> list[tuple[int, int, int, int, str, str]]:
    """Prepara i comandi di disegno per l'overlay: (x1, y1, x2, y2, colore, etichetta)."""
    out = []
    for s in slots:
        x1, y1, x2, y2 = cell_box(region, rows, cols, s.row, s.col, 0, trim_bottom)
        is_full = s.score >= threshold
        color = "#00ff88" if is_full else "#666666"
        out.append((x1, y1, x2, y2, color, f"{s.score:.0f}"))
    return out
