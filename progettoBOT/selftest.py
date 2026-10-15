"""
selftest.py - Verifica la pipeline senza Albion.

Testa, con immagini sintetiche:
  1. vision   -> rilevamento degli slot pieni
  2. autodetect -> template matching della finestra
  3. items    -> riconoscimento delle icone oggetto

    python selftest.py
"""

from __future__ import annotations

import dpi  # noqa: F401  (DPI awareness - deve essere il primo import)

import tempfile
from pathlib import Path

import cv2
import numpy as np

from config import Settings
from src.autodetect import WindowLocator
from src.items import ItemRecognizer
from src.vision import detect_slots, filled_slots

ROWS, COLS = 5, 6
W, H = 600, 400


# ----------------------------------------------------------------- 1. vision
def make_fake_window(filled: set[tuple[int, int]], seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    img = np.full((H, W, 3), 28, dtype=np.uint8)

    cw, ch = W / COLS, H / ROWS
    for r in range(ROWS):
        for c in range(COLS):
            x1, y1 = int(c * cw) + 4, int(r * ch) + 4
            x2, y2 = int((c + 1) * cw) - 4, int((r + 1) * ch) - 4
            cv2.rectangle(img, (x1, y1), (x2, y2), (60, 60, 60), 1)
            if (r, c) in filled:
                color = tuple(int(v) for v in rng.integers(90, 255, size=3))
                cv2.rectangle(img, (x1 + 3, y1 + 3), (x2 - 3, y2 - 3), color, -1)
                noise = rng.integers(0, 40, size=(y2 - y1 - 6, x2 - x1 - 6, 3), dtype=np.uint8)
                img[y1 + 3:y2 - 3, x1 + 3:x2 - 3] = np.clip(
                    img[y1 + 3:y2 - 3, x1 + 3:x2 - 3].astype(int) + noise, 0, 255
                ).astype(np.uint8)
    return img


def test_vision() -> bool:
    expected = {(0, 0), (0, 3), (1, 1), (2, 5), (4, 2)}
    frame = make_fake_window(expected)

    cfg = Settings()
    cfg.region = [0, 0, W, H]
    cfg.rows, cfg.cols = ROWS, COLS

    slots = detect_slots(frame, cfg)
    detected = {(s.row, s.col) for s in filled_slots(slots, cfg.fill_threshold)}

    print(f"  attesi   : {sorted(expected)}")
    print(f"  rilevati : {sorted(detected)}")
    ok = detected == expected

    vis = frame.copy()
    for s in slots:
        if s.score >= cfg.fill_threshold:
            x = int((s.col + 0.5) * (W / COLS))
            y = int((s.row + 0.5) * (H / ROWS))
            cv2.circle(vis, (x, y), 6, (0, 255, 0), -1)
    cv2.imwrite("selftest_preview.png", vis)
    return ok


# ------------------------------------------------------------- 2. autodetect
def test_autodetect(tmp: Path) -> bool:
    rng = np.random.default_rng(7)
    screen = np.full((720, 1280, 3), 20, dtype=np.uint8)
    screen[:] = rng.integers(10, 30, size=(720, 1280, 3), dtype=np.uint8)

    # template distintivo (struttura, non solo rumore)
    tmpl = np.full((36, 48, 3), 40, dtype=np.uint8)
    cv2.rectangle(tmpl, (2, 2), (45, 33), (200, 120, 60), 2)
    cv2.line(tmpl, (4, 4), (44, 32), (0, 255, 255), 3)
    cv2.circle(tmpl, (24, 18), 8, (255, 255, 255), -1)

    tx, ty = 300, 200
    screen[ty:ty + 36, tx:tx + 48] = tmpl

    tmpl_path = tmp / "loot_frame.png"
    cv2.imwrite(str(tmpl_path), tmpl)

    cfg = Settings()
    cfg.template_path = str(tmpl_path)
    cfg.search_region = [0, 0, 1280, 720]
    cfg.auto_region = [10, 30, 320, 260]
    cfg.template_threshold = 0.72

    locator = WindowLocator(cfg)
    region = locator.locate(screen, (0, 0))
    expected = [tx + 10, ty + 30, 320, 260]
    print(f"  atteso   : {expected}")
    print(f"  trovato  : {region}  (match={locator.last_match_score(screen):.2f})")

    ok_found = region == expected

    # caso negativo: template assente
    empty = np.full((720, 1280, 3), 20, dtype=np.uint8)
    region2 = locator.locate(empty, (0, 0))
    ok_none = region2 is None
    print(f"  caso negativo (template assente): {region2}  -> {'ok' if ok_none else 'FALLITO'}")

    return ok_found and ok_none


# ----------------------------------------------------------------- 3. items
def _make_icon_a() -> np.ndarray:
    img = np.full((44, 44, 3), 30, dtype=np.uint8)
    cv2.circle(img, (22, 22), 14, (0, 0, 220), -1)
    cv2.circle(img, (22, 22), 6, (255, 255, 255), -1)
    return img


def _make_icon_b() -> np.ndarray:
    img = np.full((44, 44, 3), 30, dtype=np.uint8)
    pts = np.array([[22, 6], [40, 38], [4, 38]], dtype=np.int32)
    cv2.fillPoly(img, [pts], (220, 140, 0))
    return img


def test_items(tmp: Path) -> bool:
    items_dir = tmp / "items"
    items_dir.mkdir(parents=True, exist_ok=True)

    icon_a = _make_icon_a()
    icon_b = _make_icon_b()
    cv2.imwrite(str(items_dir / "Pozione.png"), icon_a)
    cv2.imwrite(str(items_dir / "Anello.png"), icon_b)

    cfg = Settings()
    cfg.item_filter = True
    cfg.items_dir = str(items_dir)
    cfg.item_match_threshold = 0.6
    cfg.loot_all_if_no_match = False

    rec = ItemRecognizer(cfg)
    print(f"  icone caricate: {sorted(rec.items)}")

    # probe = icona A leggermente rumorosa
    rng = np.random.default_rng(3)
    probe = np.clip(icon_a.astype(int) + rng.integers(-10, 10, icon_a.shape), 0, 255).astype(np.uint8)
    name, score = rec.identify(probe)
    print(f"  probe Pozione -> {name} ({score:.2f})")
    ok_a = name == "Pozione"

    # probe sconosciuto (rumore) non deve passare
    unknown = rng.integers(0, 255, (44, 44, 3), dtype=np.uint8)
    do_loot, uname, uscore = rec.should_loot(unknown)
    print(f"  probe sconosciuto -> loot={do_loot} (best={uname} {uscore:.2f})")
    ok_unknown = do_loot is False

    return ok_a and ok_unknown


def main() -> int:
    results: dict[str, bool] = {}
    tmp = Path(tempfile.mkdtemp(prefix="autoloot_selftest_"))

    print("[1/3] vision ...")
    results["vision"] = test_vision()

    print("[2/3] autodetect ...")
    results["autodetect"] = test_autodetect(tmp)

    print("[3/3] items ...")
    results["items"] = test_items(tmp)

    print("\n===== RISULTATI =====")
    for name, ok in results.items():
        print(f"  {name:12s}: {'OK' if ok else 'FALLITO'}")
    print("anteprima vision: selftest_preview.png")

    return 0 if all(results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
