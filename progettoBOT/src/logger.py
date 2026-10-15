"""
logger.py - Log delle statistiche su CSV.

Una riga per slot analizzato, con il tempo, la posizione, il punteggio e se e'
stato cliccato. Serve a tre cose:
  1. scegliere la soglia guardando la distribuzione reale dei punteggi,
  2. capire perche' si e' rotto dopo una patch (i punteggi cambiano?),
  3. statistiche divertenti (slot/ora, ecc.).

Opzionalmente salva i ritagli (crop) PNG di ogni slot cliccato, per ispezione.
"""

from __future__ import annotations

import csv
import datetime as _dt
from pathlib import Path

import cv2
import numpy as np

from config import Settings


class LootLogger:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.enabled = cfg.enable_logging
        self.dir = Path(cfg.log_dir)
        self.path: Path | None = None
        self._fh = None
        self._writer = None
        self.crops_dir = self.dir / "crops"
        self._count = 0

        if not self.enabled:
            return

        self.dir.mkdir(parents=True, exist_ok=True)
        stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.dir / f"loot_{stamp}.csv"
        self._fh = self.path.open("w", newline="", encoding="utf-8")
        self._writer = csv.writer(self._fh)
        self._writer.writerow(
            ["timestamp", "row", "col", "x", "y", "score", "clicked", "item", "crop"]
        )
        if cfg.save_crops:
            self.crops_dir.mkdir(parents=True, exist_ok=True)

    def log_slot(self, slot, clicked: bool, item: str | None = None,
                 crop: np.ndarray | None = None) -> None:
        if not self.enabled or self._writer is None:
            return

        crop_name = ""
        if crop is not None and self.cfg.save_crops:
            crop_name = f"{self._count:06d}_r{slot.row}c{slot.col}.png"
            cv2.imwrite(str(self.crops_dir / crop_name), crop)

        self._writer.writerow([
            _dt.datetime.now().strftime("%H:%M:%S.%f")[:-3],
            slot.row, slot.col, slot.x, slot.y,
            f"{slot.score:.1f}", int(clicked), item or "", crop_name,
        ])
        self._count += 1
        # flush periodico per non perdere dati se il processo viene chiuso
        if self._count % 20 == 0:
            self._fh.flush()

    def close(self) -> None:
        if self._fh is not None:
            try:
                self._fh.flush()
                self._fh.close()
            finally:
                self._fh = None
