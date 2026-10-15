"""
config.py - Configurazione del bot di auto-loot.

La configurazione viene salvata in config.json e puo' essere modificata a mano
oppure tramite i tool di calibrazione (calibrate.py).

Include le impostazioni per:
  - region / griglia degli slot
  - auto-detect della finestra (template matching)
  - logging delle statistiche
  - overlay grafico sopra il gioco
  - riconoscimento item (filtro sugli oggetti da lootare)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict, fields
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
TEMPLATES_DIR = BASE_DIR / "templates"

# Risoluzione di riferimento: monitor 1920x1080 (Windows scaling 125%).
# IMPORTANTE: i processi sono DPI-aware (dpi.py), quindi le coordinate sono
# quelle REALI e non virtualizzate.
DEFAULT_SEARCH_REGION = [0, 0, 1920, 1080]


@dataclass
class Settings:
    # --- Area dello schermo in cui appare la finestra del loot (pixel assoluti) ---
    # [x, y, larghezza, altezza]  -> vedi calibrate.py per impostarla col mouse
    region: list[int] = field(default_factory=lambda: [500, 250, 320, 260])

    # --- Griglia degli slot dentro la region ---
    # La finestra di loot di Albion ha SEMPRE 4 colonne di slot quadrati.
    rows: int = 4          # numero di righe VISIBILI (le altre si vedono scrollando)
    cols: int = 4          # numero di colonne (fisse: 4)
    slot_margin: int = 3   # pixel tagliati da ogni lato della cella prima di analizzarla
    # L'icona dell'item e' piu' bassa della cella: questo taglia i pixel in piu'
    # dal fondo, cosi' i riquadri aderiscono all'item. (calcolato in calibrate.py)
    cell_trim_bottom: int = 0

    # --- Rilevamento slot "pieni" ---
    # punteggio di texture: sotto la soglia = slot vuoto, sopra = slot pieno.
    # Sugli screenshot reali gli slot vuoti stanno ~3-5 e i pieni ~60-75.
    fill_threshold: float = 25.0

    # --- Tempi (millisecondi) ---
    click_delay: list[int] = field(default_factory=lambda: [18, 45])
    cycle_delay: list[int] = field(default_factory=lambda: [120, 260])
    settle_after_click: list[int] = field(default_factory=lambda: [8, 20])
    # pausa DOPO aver spostato il cursore e PRIMA di premere: da' al gioco il tempo
    # di registrare la posizione/hover del mouse.
    pre_click: list[int] = field(default_factory=lambda: [60, 120])
    # per quanto tenere PREMUTO il tasto sinistro. I giochi spesso ignorano i click
    # istantanei di pynput (down+up nello stesso frame): serve che resti giu' un attimo.
    click_hold: list[int] = field(default_factory=lambda: [40, 80])

    # --- Scroll della scheda di loot ---
    # La finestra mostra solo alcune righe: dopo aver svuotato quelle visibili il
    # bot scrolla verso il basso per far comparire le righe successive.
    scroll_enabled: bool = True
    scroll_clicks: int = -3     # tacche di rotella (negativo = giu')
    max_scrolls: int = 12       # quante volte scrollare al massimo per finestra
    scroll_settle: list[int] = field(default_factory=lambda: [80, 160])

    # --- Stato / sicurezza ---
    mouse_jitter: int = 2
    modifier: str = "shift"

    # --- Hotkey globali ---
    toggle_key: str = "f8"
    panic_key: str = "f9"

    # --- Debug ---
    debug: bool = False          # finestra OpenCV con overlay (metodo classico)

    # --- 1) Auto-detect della finestra di loot (template matching) ---
    auto_detect: bool = False
    search_region: list[int] = field(default_factory=lambda: list(DEFAULT_SEARCH_REGION))
    template_path: str = "templates/loot_frame.png"
    template_threshold: float = 0.72
    # Come si ricava la region del loot dalla posizione del template trovato:
    # [dx, dy, larghezza, altezza] relativi all'angolo in alto-sinistra del template.
    auto_region: list[int] = field(default_factory=lambda: [0, 0, 320, 260])

    # --- 2) Logging / statistiche ---
    enable_logging: bool = True
    save_crops: bool = False
    log_dir: str = "logs"

    # --- 3) Overlay grafico sopra il gioco ---
    overlay: bool = False

    # --- 4) Riconoscimento item ---
    item_filter: bool = False
    items_dir: str = "templates/items"
    item_match_threshold: float = 0.70
    loot_all_if_no_match: bool = True   # se False, loota SOLO gli item riconosciuti

    def to_json(self, path: Path = CONFIG_PATH) -> None:
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = CONFIG_PATH) -> "Settings":
        """Carica la config dal disco; se manca o e' corrotta, usa i default."""
        if not path.exists():
            cfg = cls()
            cfg.to_json(path)
            return cfg
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return cls()

        valid = {f.name for f in fields(cls)}
        data = {k: v for k, v in data.items() if k in valid}
        return cls(**data)


def random_in(bounds: list[int]) -> float:
    """Restituisce un valore casuale (in secondi) nell'intervallo [min, max] ms."""
    import random

    lo, hi = bounds
    return random.uniform(lo, hi) / 1000.0


def detect_screen_size() -> tuple[int, int]:
    """Risoluzione reale del monitor primario.

    Richiede che il processo sia DPI-aware (importa `dpi` per primo!), altrimenti
    Windows restituisce le coordinate virtualizzate.
    """
    try:
        import mss

        with mss.MSS() as m:
            mon = m.monitors[1] if len(m.monitors) > 1 else m.monitors[0]
            return int(mon["width"]), int(mon["height"])
    except Exception:
        return 1280, 720


def sync_search_region(cfg: "Settings") -> None:
    """Aggiorna `search_region` alla risoluzione reale dello schermo."""
    w, h = detect_screen_size()
    cfg.search_region = [0, 0, w, h]

