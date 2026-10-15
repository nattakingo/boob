"""
looter.py - Logica principale di auto-loot.

Integra:
  - cattura schermo (screen.py)
  - rilevamento slot (vision.py)
  - auto-detect della finestra (autodetect.py)
  - riconoscimento item (items.py)
  - log statistiche (logger.py)
  - emulazione input (controller.py)

Un "ciclo":
  1. individua la region (fissa o auto-detect),
  2. cattura e rileva gli slot pieni,
  3. per ognuno decide se cliccarlo (eventuale filtro item),
  4. clicca tenendo premuto Shift,
  5. logga tutto su CSV.
"""

from __future__ import annotations

import numpy as np

from config import Settings
from src.autodetect import WindowLocator
from src.controller import Controller
from src.items import ItemRecognizer
from src.logger import LootLogger
from src.screen import Screen
from src.vision import Slot, cell_crop, detect_slots, draw_debug, filled_slots


class Looter:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.screen = Screen()
        self.controller = Controller(cfg)
        self.logger = LootLogger(cfg)
        self.locator = WindowLocator(cfg) if cfg.auto_detect else None
        self.recognizer = ItemRecognizer(cfg)

        self.confirm_frames = 2
        self._streak = 0
        self.looted_total = 0
        self._scrolls_here = 0      # scroll fatti per la finestra corrente
        self._scrolled_total = 0    # scroll totali (statistica)
        self._last_full_set: frozenset | None = None
        self._stuck = 0

        self.last_slots: list[Slot] = []
        self.last_frame: np.ndarray | None = None
        self.last_region: list[int] | None = None
        self.last_status: str = ""

    # ---------------------------------------------------------------- region
    def _current_region(self) -> list[int] | None:
        if not self.cfg.auto_detect or self.locator is None or not self.locator.loaded:
            return self.cfg.region
        sx, sy, _, _ = self.cfg.search_region
        search = self.screen.grab(self.cfg.search_region)
        region = self.locator.locate(search, (sx, sy))
        return region

    # ---------------------------------------------------------------- scan
    def scan(self) -> tuple[np.ndarray | None, list[Slot]]:
        region = self._current_region()
        if region is None:
            self.last_region = None
            self.last_slots = []
            self.last_frame = None
            self.last_status = "finestra non trovata"
            return None, []

        frame = self.screen.grab(region)
        slots = detect_slots(frame, self.cfg, region)
        self.last_region = region
        self.last_frame = frame
        self.last_slots = slots
        self.last_status = ""
        return frame, slots

    def full_slots(self) -> list[Slot]:
        return filled_slots(self.last_slots, self.cfg.fill_threshold)

    # ---------------------------------------------------------------- ciclo
    def _maybe_scroll(self) -> int:
        """Se non c'e' piu' nulla di visibile, scorre la scheda verso il basso."""
        if not self.cfg.scroll_enabled:
            return 0
        if self._scrolls_here >= self.cfg.max_scrolls:
            return 0
        self._scrolls_here += 1
        self._scrolled_total += 1
        region = self.last_region or self.cfg.region
        cx = region[0] + region[2] // 2
        cy = region[1] + region[3] // 2
        self.controller.scroll(self.cfg.scroll_clicks, at=(cx, cy))
        print(f"[bot] scroll {self._scrolls_here}/{self.cfg.max_scrolls}")
        return 0

    def run_cycle(self) -> int:
        # sposto il cursore fuori dalla scheda: evita hover/tooltip che falsano la
        # scansione (era il motivo del conteggio che oscillava 9 <-> 11).
        self.controller.park(self.last_region or self.cfg.region)
        frame, slots = self.scan()
        if frame is None or not slots:
            self._streak = 0
            return 0

        full = filled_slots(slots, self.cfg.fill_threshold)
        if not full:
            # niente di visibile: prova a scrollare per le righe nascoste
            self._streak = 0
            self._last_full_set = None
            self._stuck = 0
            return self._maybe_scroll()

        self._streak += 1
        if self._streak < self.confirm_frames:
            return 0
        self._streak = 0
        # c'e' roba nuova visibile -> si riparte con lo scroll dall'alto
        self._scrolls_here = 0

        clicked = 0
        for slot in slots:
            is_full = slot.score >= self.cfg.fill_threshold
            crop = cell_crop(frame, self.cfg, slot.row, slot.col)

            do_click = is_full
            item_name: str | None = None
            if is_full and self.recognizer.active:
                do_click, item_name, _ = self.recognizer.should_loot(crop)

            if do_click:
                self.controller.loot_slot(slot.x, slot.y)
                clicked += 1
                self.controller.sleep_between_clicks()

            self.logger.log_slot(slot, do_click, item_name, crop)

        self.controller.release_modifier()
        self.looted_total += clicked

        # diagnostica: se dopo i click gli stessi slot restano pieni, il gioco non
        # sta registrando i click.
        full_set = frozenset((s.row, s.col) for s in full)
        if full_set == self._last_full_set:
            self._stuck += 1
            if self._stuck == 3:
                print("[bot] ATTENZIONE: gli slot restano pieni dopo i click. "
                      "Il gioco non registra i click? Prova: python main.py --test-click")
        else:
            self._stuck = 0
        self._last_full_set = full_set
        return clicked

    # ---------------------------------------------------------------- debug
    def debug_view(self) -> np.ndarray | None:
        if self.last_frame is None:
            self.scan()
        if self.last_frame is None:
            return None
        return draw_debug(self.last_frame, self.last_slots, self.cfg.fill_threshold,
                          self.cfg.cell_trim_bottom)

    def preview_scores(self) -> list[float]:
        self.scan()
        return sorted((s.score for s in self.last_slots), reverse=True)

    def preview_summary(self) -> list[tuple[int, int, float, bool]]:
        """(row, col, score, is_full) per ogni slot, utile a --scan."""
        self.scan()
        thr = self.cfg.fill_threshold
        return [(s.row, s.col, s.score, s.score >= thr) for s in self.last_slots]

    def close(self) -> None:
        self.controller.release_all()
        self.logger.close()
        self.screen.close()
