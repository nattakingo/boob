"""
autodetect.py - Trova automaticamente la finestra di loot con il template matching.

Invece di usare una region fissa, catturiamo un'area piu' grande (`search_region`),
cerchiamo dentro di essa un piccolo template distintivo della finestra (es. la
cornice o l'angolo) e da li' ricaviamo la region esatta degli slot.

Flusso:
  1. catturo search_region  (es. tutto lo schermo 1280x720)
  2. cv2.matchTemplate cerca templates/loot_frame.png
  3. se il match supera la soglia -> region = posizione_template + [dx, dy, w, h]

Il file del template si crea con:  python calibrate.py --auto
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from config import BASE_DIR, Settings


class WindowLocator:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.template: np.ndarray | None = None
        self.loaded = False
        self._load()

    def _load(self) -> None:
        path = Path(self.cfg.template_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        if path.exists():
            tmpl = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if tmpl is not None and tmpl.size:
                self.template = tmpl
                self.loaded = True

    def locate(self, frame: np.ndarray, origin: tuple[int, int]) -> list[int] | None:
        """Cerca il template nel frame e restituisce la region assoluta del loot.

        frame  : immagine catturata (search_region), formato BGR
        origin : coordinate assolute (x, y) dell'angolo in alto-sinistra del frame
        """
        if self.template is None:
            return None
        th, tw = self.template.shape[:2]
        if frame.shape[0] < th or frame.shape[1] < tw:
            return None

        res = cv2.matchTemplate(frame, self.template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(res)
        if max_val < self.cfg.template_threshold:
            return None

        fx = origin[0] + max_loc[0]
        fy = origin[1] + max_loc[1]
        dx, dy, w, h = self.cfg.auto_region

        # Se l'utente non ha configurato auto_region, usa la dimensione del template
        if w <= 0 or h <= 0:
            w, h = tw, th

        return [int(fx + dx), int(fy + dy), int(w), int(h)]

    def last_match_score(self, frame: np.ndarray) -> float:
        """Utile per il debug: punteggio del miglior match."""
        if self.template is None:
            return 0.0
        res = cv2.matchTemplate(frame, self.template, cv2.TM_CCOEFF_NORMED)
        return float(res.max())
