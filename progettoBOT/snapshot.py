r"""
snapshot.py - Cattura uno screenshot dopo un conto alla rovescia.

Serve a "fermare" la finestra di loot: lanci il comando, torni su Albion, apri
la finestra di loot e aspetti lo scatto. Il PNG salvato si usa poi con
`calibrate.py --image` per selezionare la region con calma.

    python snapshot.py                 # 6 secondi di attesa
    python snapshot.py --delay 10
    python snapshot.py --out snapshots\loot.png
"""

from __future__ import annotations

import dpi  # noqa: F401  (DPI awareness - deve essere il primo import)

import argparse
import sys
import time
from pathlib import Path

import cv2

from config import BASE_DIR, Settings, sync_search_region
from src.screen import Screen


def main() -> int:
    p = argparse.ArgumentParser(description="Screenshot con countdown")
    p.add_argument("--delay", type=float, default=6.0, help="secondi di attesa (default 6)")
    p.add_argument("--out", default="snapshots/loot.png")
    p.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"))
    args = p.parse_args()

    cfg = Settings.load()
    sync_search_region(cfg)
    region = list(args.region) if args.region else cfg.search_region

    print(f"[snap] apri Albion e mostra la FINESTRA DI LOOT. Scatto tra {int(args.delay)}s...")
    for i in range(int(args.delay), 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    # piccolo extra per l'ultimo secondo
    time.sleep(max(0.0, args.delay - int(args.delay)))

    screen = Screen()
    frame = screen.grab(region)
    screen.close()

    out = Path(args.out)
    if not out.is_absolute():
        out = BASE_DIR / out
    out.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out), frame)

    print(f"[snap] salvato: {out}  ({frame.shape[1]}x{frame.shape[0]})")
    print(f"[snap] ora:  python calibrate.py --image \"{out}\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
