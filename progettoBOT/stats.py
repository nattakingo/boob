r"""
stats.py - Analizza i log e suggerisce la soglia ottimale.

Legge i CSV prodotti da src/logger.py, mostra la distribuzione dei punteggi di
occupazione degli slot e calcola la soglia migliore con il metodo di Otsu
(separatore che massimizza la distanza tra i due gruppi: slot vuoti e pieni).

Uso:
    python stats.py                    # legge tutti i log in logs/
    python stats.py --log logs\loot_20260101_120000.csv
    python stats.py --bins 24
    python stats.py --save-config      # scrive la soglia suggerita in config.json
"""

from __future__ import annotations

import dpi  # noqa: F401  (DPI awareness - deve essere il primo import)

import argparse
import csv
from pathlib import Path

import numpy as np

from config import CONFIG_PATH, Settings


def read_scores(path: Path) -> list[float]:
    scores: list[float] = []
    with path.open("r", newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            try:
                scores.append(float(row["score"]))
            except (KeyError, ValueError):
                continue
    return scores


def otsu_threshold(values: list[float], nbins: int = 64) -> float | None:
    """Soglia che separa meglio due gruppi (metodo di Otsu applicato a 1D)."""
    v = np.asarray(values, dtype=float)
    if v.size == 0:
        return None
    hist, edges = np.histogram(v, bins=nbins)
    hist = hist.astype(float)
    total = hist.sum()
    if total == 0:
        return None
    prob = hist / total
    centers = (edges[:-1] + edges[1:]) / 2.0
    omega = np.cumsum(prob)
    mu = np.cumsum(prob * centers)
    mu_t = mu[-1]
    denom = omega * (1.0 - omega)
    denom[denom == 0] = 1e-12
    sigma_b = (mu_t * omega - mu) ** 2 / denom
    # Il massimo e' "piatto" in tutta la valle tra i due gruppi: prendiamo il
    # centro del plateau invece del primo indice, cosi' la soglia cade a meta'.
    mx = float(sigma_b.max())
    candidates = np.nonzero(sigma_b >= mx - 1e-9)[0]
    idx = int(candidates[len(candidates) // 2])
    return float(centers[idx])


def print_histogram(values: list[float], bins: int = 20, width: int = 44) -> None:
    if not values:
        return
    v = np.asarray(values, dtype=float)
    counts, edges = np.histogram(v, bins=bins)
    peak = counts.max() or 1
    print("\nDistribuzione dei punteggi degli slot:")
    for i, c in enumerate(counts):
        lo, hi = edges[i], edges[i + 1]
        bar = "#" * int(round(c / peak * width))
        print(f"  {lo:6.1f} - {hi:6.1f} | {bar} {c}")


def main() -> int:
    p = argparse.ArgumentParser(description="Statistiche e soglia suggerita")
    p.add_argument("--log", help="file CSV specifico")
    p.add_argument("--log-dir", default="logs", help="cartella dei log")
    p.add_argument("--bins", type=int, default=20)
    p.add_argument("--save-config", action="store_true",
                   help="scrive la soglia suggerita in config.json")
    args = p.parse_args()

    if args.log:
        files = [Path(args.log)]
    else:
        d = Path(args.log_dir)
        files = sorted(d.glob("loot_*.csv")) if d.exists() else []

    if not files:
        print(f"[stats] nessun log trovato in '{args.log_dir}'. "
              f"Avvia il bot con il logging attivo.")
        return 1

    scores: list[float] = []
    for f in files:
        s = read_scores(f)
        scores.extend(s)
        print(f"[stats] {f}: {len(s)} slot")

    print(f"\n[stats] totale slot analizzati: {len(scores)}")
    if not scores:
        print("[stats] nessun dato valido")
        return 1

    v = np.asarray(scores)
    print(f"[stats] min={v.min():.1f}  media={v.mean():.1f}  max={v.max():.1f}")

    print_histogram(scores, bins=args.bins)

    thr = otsu_threshold(scores)
    if thr is None:
        return 1

    empty = int((v < thr).sum())
    full = int((v >= thr).sum())
    print(f"\n[stats] soglia suggerita (Otsu): {thr:.1f}")
    print(f"[stats]   ~{empty} slot 'vuoti' sotto la soglia, ~{full} slot 'pieni' sopra")

    if args.save_config:
        cfg = Settings.load()
        cfg.fill_threshold = round(thr, 1)
        cfg.to_json()
        print(f"[stats] soglia {cfg.fill_threshold} salvata in {CONFIG_PATH}")
    else:
        print("[stats] per salvarla: python stats.py --save-config")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
