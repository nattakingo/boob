"""
screen.py - Cattura dello schermo.

Usa `mss` che e' molto piu' veloce di PIL/ImageGrab: una cattura di una region
piccola costa pochi millisecondi, quindi possiamo scansionare a ~60 fps.
"""

from __future__ import annotations

import cv2
import mss
import numpy as np


class Screen:
    def __init__(self) -> None:
        # mss va istanziato una volta sola e riusato (aprire un handle ogni volta e' lento)
        self._sct = mss.mss()

    def grab(self, region: list[int]) -> np.ndarray:
        """Cattura la region [x, y, w, h] e restituisce un'immagine BGR (formato OpenCV)."""
        x, y, w, h = region
        if w <= 0 or h <= 0:
            raise ValueError(f"Regione non valida: {region}")

        shot = self._sct.grab({"left": x, "top": y, "width": w, "height": h})
        # mss restituisce BGRA -> lo convertiamo in BGR per OpenCV
        frame = np.asarray(shot)
        return cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)

    def virtual_screen(self) -> dict:
        """Info sul monitor virtuale (utile in calibrate.py)."""
        return dict(self._sct.monitors[0])

    def close(self) -> None:
        try:
            self._sct.close()
        except Exception:
            pass
