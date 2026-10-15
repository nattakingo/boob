"""
items.py - Riconoscimento item tramite template matching delle icone.

Nella cartella `templates/items/` metti un PNG per ogni oggetto di interesse
(il nome del file diventa il nome dell'item, es. `Borsa_T8.png`).

Per ogni slot confrontiamo il ritaglio con ciascuna icona:
  - normalizziamo entrambi a una dimensione fissa in scala di grigi,
  - calcoliamo la correlazione normalizzata (matchTemplate su immagini della
    stessa dimensione restituisce un singolo valore in [-1, 1]).

Il file template si crea con:  python calibrate.py --item NomeItem
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from config import BASE_DIR, Settings

_NORM_SIZE = (44, 44)  # dimensione a cui normalizzare i ritagli e le icone


class ItemRecognizer:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.items: dict[str, np.ndarray] = {}
        self._load()

    def _load(self) -> None:
        dir_path = Path(self.cfg.items_dir)
        if not dir_path.is_absolute():
            dir_path = BASE_DIR / dir_path
        if not dir_path.exists():
            return
        for png in sorted(dir_path.glob("*.png")):
            img = cv2.imread(str(png), cv2.IMREAD_COLOR)
            if img is None or img.size == 0:
                continue
            self.items[png.stem] = self._normalize(img)

    @staticmethod
    def _normalize(img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return cv2.resize(gray, _NORM_SIZE, interpolation=cv2.INTER_AREA)

    @property
    def active(self) -> bool:
        return self.cfg.item_filter and len(self.items) > 0

    def identify(self, slot_img: np.ndarray) -> tuple[str | None, float]:
        """Restituisce (nome_item, punteggio) del miglior match, o (None, score)."""
        if not self.items or slot_img.size == 0:
            return None, 0.0
        probe = self._normalize(slot_img)
        best_name, best_score = None, -1.0
        for name, tmpl in self.items.items():
            score = float(cv2.matchTemplate(probe, tmpl, cv2.TM_CCOEFF_NORMED)[0, 0])
            if score > best_score:
                best_name, best_score = name, score
        return best_name, best_score

    def should_loot(self, slot_img: np.ndarray) -> tuple[bool, str | None, float]:
        """Decide se uno slot va lootato in base al filtro item.

        - Se il filtro e' disattivo -> loota sempre.
        - Se e' attivo e c'e' un match sopra soglia -> loota.
        - Se e' attivo ma nessun match:
            * loot_all_if_no_match = True  -> loota comunque
            * loot_all_if_no_match = False -> salta lo slot
        """
        if not self.active:
            return True, None, 0.0

        name, score = self.identify(slot_img)
        if name is not None and score >= self.cfg.item_match_threshold:
            return True, name, score
        return self.cfg.loot_all_if_no_match, name, score
