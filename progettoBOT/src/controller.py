"""
controller.py - Emulazione mouse/tastiera.

Usa `pynput`, che sfrutta le API native di Windows (SendInput).
Tiene premuto il modificatore (Shift) per il loot rapido e clicca gli slot.
"""

from __future__ import annotations

import random
import time

from pynput.keyboard import Controller as KeyboardController, Key, KeyCode
from pynput.mouse import Button, Controller as MouseController

from config import Settings, detect_screen_size, random_in

_MODIFIER_KEYS = {
    "shift": Key.shift,
    "ctrl": Key.ctrl,
    "alt": Key.alt,
    "none": None,
}


class Controller:
    def __init__(self, cfg: Settings) -> None:
        self.cfg = cfg
        self.kb = KeyboardController()
        self.mouse = MouseController()
        self._modifier = _MODIFIER_KEYS.get(cfg.modifier, Key.shift)
        self._holding = False
        self.screen_w, self.screen_h = detect_screen_size()

    # --- Modificatore (Shift) ---
    def hold_modifier(self) -> None:
        if self._modifier is None:
            return
        if not self._holding:
            self.kb.press(self._modifier)
            self._holding = True

    def release_modifier(self) -> None:
        if self._modifier is None:
            return
        if self._holding:
            self.kb.release(self._modifier)
            self._holding = False

    def set_modifier(self, name: str) -> None:
        """Cambia il modificatore al volo ('shift' / 'ctrl' / 'alt' / 'none')."""
        self.release_modifier()
        self.cfg.modifier = name
        self._modifier = _MODIFIER_KEYS.get(name, Key.shift)

    # --- Click ---
    def click(self, x: int, y: int) -> None:
        """Click reale: sposta, aspetta, PREME, tiene premuto, rilascia.

        I giochi (Unity/Albion compreso) spesso non registrano i click
        istantanei di pynput: il tasto sinistro deve restare giu' per un attimo.
        """
        j = self.cfg.mouse_jitter
        jx = x + random.randint(-j, j)
        jy = y + random.randint(-j, j)
        self.mouse.position = (jx, jy)
        time.sleep(random_in(self.cfg.pre_click))
        self.mouse.press(Button.left)
        time.sleep(random_in(self.cfg.click_hold))
        self.mouse.release(Button.left)
        time.sleep(random_in(self.cfg.settle_after_click))

    def park(self, region: list[int]) -> None:
        """Sposta il cursore appena FUORI dalla region.

        Serve a due cose: evita che l'hover del mouse "illumini" uno slot
        (falsi positivi) e fa sparire eventuali tooltip prima della scansione.
        """
        x, y, w, h = region
        px = x + w // 2
        offset = max(24, h // 3)
        py = y - offset
        if py < 0:
            py = y + h + offset
        px = max(1, min(px, self.screen_w - 2))
        py = max(1, min(py, self.screen_h - 2))
        self.mouse.position = (px, py)
        time.sleep(0.08)

    def loot_slot(self, x: int, y: int) -> None:
        """Click con Shift tenuto premuto (loot rapido di Albion)."""
        self.hold_modifier()
        self.click(x, y)

    def sleep_between_clicks(self) -> None:
        time.sleep(random_in(self.cfg.click_delay))

    def sleep_between_cycles(self) -> None:
        time.sleep(random_in(self.cfg.cycle_delay))

    # --- Scroll (per far comparire le righe nascoste della scheda di loot) ---
    def scroll(self, clicks: int, at: tuple[int, int] | None = None) -> None:
        """Ruota la rotella del mouse (negativo = verso il basso).

        Sposta prima il puntatore sul punto indicato (es. il centro della
        scheda di loot) cosi' lo scroll agisce sulla finestra giusta.
        """
        if at is not None:
            self.mouse.position = at
            time.sleep(random_in([20, 45]))
        self.mouse.scroll(0, clicks)
        time.sleep(random_in(self.cfg.scroll_settle))

    def release_all(self) -> None:
        """Rilascia tutto (chiamata in panico / alla chiusura)."""
        self.release_modifier()
