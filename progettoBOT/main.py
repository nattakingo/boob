"""
main.py - Entry point del bot di auto-loot per Albion Online.

Uso rapido:
    python main.py                 # avvia, premi F8 per accendere/spegnere
    python main.py --overlay       # riquadri sopra il gioco (trasparente)
    python main.py --debug         # anteprima in una finestra OpenCV
    python main.py --scan          # NON clicca: mostra solo i punteggi degli slot
    python main.py --auto          # usa l'auto-detect della finestra (template)
    python main.py --items         # attiva il filtro sul riconoscimento item

Tasti:
    F8  = accendi/spegni il bot
    F9  = stop immediato (panic) ed esce
    Q   = chiude la finestra di debug
"""

from __future__ import annotations

import dpi  # noqa: F401  (DPI awareness - deve essere il primo import)

import argparse
import sys
import threading
import time

from config import Settings, CONFIG_PATH, sync_search_region
from src.looter import Looter
from src.overlay import Overlay
from src.vision import overlay_boxes


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Auto-loot per Albion Online (a scopo di studio)")
    p.add_argument("--region", nargs=4, type=int, metavar=("X", "Y", "W", "H"),
                   help="area della finestra di loot")
    p.add_argument("--rows", type=int, help="numero di righe di slot")
    p.add_argument("--cols", type=int, help="numero di colonne di slot")
    p.add_argument("--threshold", type=float, help="soglia di occupazione slot")
    p.add_argument("--debug", action="store_true", help="anteprima OpenCV con overlay")
    p.add_argument("--overlay", action="store_true", help="overlay trasparente sopra il gioco")
    p.add_argument("--auto", action="store_true", help="usa l'auto-detect (template)")
    p.add_argument("--items", action="store_true", help="attiva il filtro riconoscimento item")
    p.add_argument("--no-log", action="store_true", help="disabilita il logging su CSV")
    p.add_argument("--save-crops", action="store_true", help="salva i ritagli degli slot")
    p.add_argument("--scan", action="store_true", help="solo scansione, nessun click")
    p.add_argument("--test-click", action="store_true",
                   help="diagnostica: clicca tutti gli slot e vede se si svuotano")
    p.add_argument("--test-world", action="store_true",
                   help="diagnostica: clicca nel mondo e vede se il personaggio si muove")
    p.add_argument("--image", metavar="PATH",
                   help="analizza uno screenshot salvato invece dello schermo (nessun click)")
    p.add_argument("--once", action="store_true", help="esegue un solo ciclo ed esce")
    p.add_argument("--interval", type=float, default=0.1, help="pausa tra i cicli (s)")
    return p.parse_args()


class App:
    def __init__(self, cfg: Settings, overlay: Overlay | None) -> None:
        self.cfg = cfg
        self.looter = Looter(cfg)
        self.overlay = overlay
        self.running = threading.Event()
        self.quit = threading.Event()

    def toggle(self) -> None:
        if self.running.is_set():
            self.running.clear()
            print("[bot] OFF")
        else:
            self.running.set()
            print("[bot] ON")

    def panic(self) -> None:
        print("[bot] PANIC - esco")
        self.running.clear()
        self.quit.set()

    def _paint(self) -> None:
        if self.overlay is None:
            return
        state = "ON" if self.running.is_set() else "OFF"
        status = f"auto-loot {state}  |  loot: {self.looter.looted_total}  |  {self.looter.last_status}"
        region = self.looter.last_region
        boxes = []
        if region:
            boxes = overlay_boxes(self.looter.last_slots, region,
                                  self.cfg.rows, self.cfg.cols, self.cfg.fill_threshold,
                                  self.cfg.cell_trim_bottom)
        self.overlay.update(boxes, status)

    def loop(self, scan_only: bool, interval: float) -> None:
        try:
            while not self.quit.is_set():
                if not self.running.is_set() and not scan_only and self.overlay is None and not self.cfg.debug:
                    time.sleep(0.03)
                    continue

                if scan_only:
                    self._print_scan()
                    self._paint()
                    time.sleep(interval)
                    continue

                if self.running.is_set():
                    clicked = self.looter.run_cycle()
                    if clicked:
                        print(f"[bot] cliccati {clicked} slot (totale {self.looter.looted_total})")
                    self._paint()
                    self._show_debug()
                    self.looter.controller.sleep_between_cycles()
                else:
                    # passivo: aggiorna solo la visualizzazione
                    self.looter.scan()
                    self._paint()
                    self._show_debug()
                    time.sleep(interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.looter.close()
            if self.overlay is not None:
                self.overlay.stop()

    def _print_scan(self) -> None:
        summary = self.looter.preview_summary()
        if not summary:
            print("[scan] nessuno slot (region vuota?)")
            return
        parts = [f"r{r}c{c}={s:.0f}{'*' if full else ''}" for r, c, s, full in summary]
        n_full = sum(1 for *_x, full in summary if full)
        print(f"[scan] pieni={n_full}/{len(summary)}  " + "  ".join(parts))

    def _show_debug(self) -> None:
        if not self.cfg.debug:
            return
        import cv2

        vis = self.looter.debug_view()
        if vis is None:
            return
        cv2.imshow("auto-loot debug (q per uscire)", vis)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            self.quit.set()


def run_image_scan(cfg: Settings, path: str) -> int:
    """Analizza uno screenshot salvato (nessun click, nessuna finestra di gioco)."""
    import cv2

    from pathlib import Path

    from src.vision import cell_box, detect_slots

    p = Path(path)
    if not p.is_absolute():
        p = Path(__file__).resolve().parent / p
    img = cv2.imread(str(p))
    if img is None:
        print(f"[scan] immagine non trovata: {p}")
        return 1

    x, y, w, h = cfg.region
    frame = img[y:y + h, x:x + w]
    if frame.size == 0:
        print("[scan] la region cade fuori dall'immagine: ricalibra con --image")
        return 1

    slots = detect_slots(frame, cfg, cfg.region)
    thr = cfg.fill_threshold
    n_full = sum(1 for s in slots if s.score >= thr)
    print(f"[scan] immagine={p.name} ({img.shape[1]}x{img.shape[0]})  "
          f"region={cfg.region}  grid={cfg.rows}x{cfg.cols}  soglia={thr}")
    print(f"[scan] pieni={n_full}/{len(slots)}")
    for s in slots:
        stato = "PIENO" if s.score >= thr else "vuoto"
        print(f"   r{s.row}c{s.col}  score={s.score:5.1f}  {stato}")

    vis = frame.copy()
    for s in slots:
        x1, y1, x2, y2 = cell_box([0, 0, frame.shape[1], frame.shape[0]],
                                  cfg.rows, cfg.cols, s.row, s.col, 0,
                                  cfg.cell_trim_bottom)
        color = (0, 255, 0) if s.score >= thr else (0, 0, 255)
        cv2.rectangle(vis, (x1, y1), (x2, y2), color, 1)
        cv2.putText(vis, f"{s.score:.0f}", (x1 + 2, y1 + 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
    out = Path(__file__).resolve().parent / "scan_debug.png"
    cv2.imwrite(str(out), vis)
    print(f"[scan] debug salvato: {out}")
    return 0


def run_click_test(cfg: Settings) -> int:
    """Diagnostica: clicca il primo slot pieno e verifica se si svuota.

    Aspetta che compaia uno slot pieno (cosi' puoi aprire la scheda di loot DOPO
    aver lanciato il comando). Prova PRIMA con il modificatore configurato (shift)
    e, se non funziona, con il click semplice.
    """
    import cv2

    looter = Looter(cfg)
    ctrl = looter.controller
    try:
        print("[test] in attesa di uno slot pieno... apri la scheda di loot in Albion.")
        print("[test] (Ctrl+C per annullare)")
        best = 0.0
        slot = None
        for _ in range(120):  # ~36 secondi
            ctrl.park(cfg.region)
            looter.scan()
            full = looter.full_slots()
            if full:
                slot = full[0]
                break
            scores = [s.score for s in looter.last_slots]
            best = max(best, max(scores, default=0.0))
            time.sleep(0.3)

        if slot is None:
            print(f"[test] nessuno slot pieno trovato. score massimo visto = {best:.0f}")
            print(f"[test] region in uso = {cfg.region}  (grid {cfg.rows}x{cfg.cols})")
            vis = looter.debug_view()
            if vis is not None:
                cv2.imwrite("test_debug.png", vis)
                print("[test] salvo test_debug.png: guarda se i riquadri sono sulla scheda")
            print("[test] controlla: la scheda era APERTA? la region e' sopra la scheda?")
            print("[test]   python main.py --scan   (mostra gli score dal vivo)")
            return 1

        # --- test: quanti slot pieni PRIMA e DOPO il loot ---
        # (robusto: anche se gli item si spostano di cella, se il loot funziona
        #  il numero di slot pieni deve diminuire)
        ctrl.park(cfg.region)
        looter.scan()
        full_before = looter.full_slots()
        n_before = len(full_before)
        print(f"[test] slot pieni PRIMA: {n_before}")
        print(f"[test] slot scelto r{slot.row}c{slot.col} (x={slot.x}, y={slot.y})")

        n_after = n_before
        for label, modifier in (("SHIFT+click", cfg.modifier), ("click semplice", "none")):
            print(f"[test] clicco tutti gli slot con {label} ...")
            ctrl.set_modifier(modifier)
            for s in full_before:
                ctrl.hold_modifier()
                ctrl.click(s.x, s.y)
                ctrl.release_modifier()
                time.sleep(0.15)
            ctrl.release_modifier()
            time.sleep(1.5)
            ctrl.park(cfg.region)
            looter.scan()
            n_after = len(looter.full_slots())
            print(f"[test]   slot pieni DOPO: {n_after}")
            if n_after < n_before:
                print(f"[test] OK -> {n_before - n_after} slot svuotati con {label}: "
                      f"il LOOTING FUNZIONA.")
                if modifier != "none":
                    print(f"[test] lascia  \"modifier\": \"{modifier}\"  in config.json")
                else:
                    print("[test] metti  \"modifier\": \"none\"  in config.json")
                return 0

        print(f"[test] nessuno slot si e' svuotato ({n_before} prima, {n_after} dopo).")
        print("[test] il gioco non sta prendendo gli item. In ordine di probabilita':")
        print("[test]   1) il terminale e' aperto come AMMINISTRATORE?")
        print("[test]   2) l'INVENTARIO e' pieno? (Albion non prende piu' niente)")
        print("[test]   3) col TUO mouse, un singolo click sull'item lo prende?")
        print("[test]   4) sei nel tempo di loot? (in PvP il loot si disabilita)")
        return 0
    finally:
        looter.close()


def run_world_click_test(cfg: Settings) -> int:
    """Verifica se i click arrivano AL GIOCO: clicca in un punto libero del mondo.

    Se il personaggio si muove -> i click arrivano (e il problema e' nel loot).
    Se non si muove -> Albion ignora i click iniettati (permessi/integrita').
    """
    from src.controller import Controller

    ctrl = Controller(cfg)
    x = max(1, cfg.search_region[2] // 5)
    y = max(1, cfg.search_region[3] // 4)
    print("[test] SUBITO dopo questo comando: torna su ALBION (Alt+Tab).")
    print(f"[test] tra 5 secondi clicchero' in ({x}, {y}), un punto libero del mondo.")
    print("[test] Guarda il personaggio, NON il terminale.")
    for n in (5, 4, 3, 2, 1):
        print(f"[test]   {n} ...")
        time.sleep(1.0)
    ctrl.click(x, y)
    time.sleep(2.5)
    print("[test] click inviato.")
    print("[test] DOMANDA: il personaggio si e' SPOSTATO?")
    print("[test]   - SI  -> i click arrivano ad Albion (il problema e' nel loot)")
    print("[test]   - NO  -> Albion ignora i click iniettati")
    print("[test]          -> esegui il terminale come AMMINISTRATORE e riprova")
    ctrl.release_all()
    return 0


def main() -> int:
    args = parse_args()

    cfg = Settings.load()
    sync_search_region(cfg)
    if args.region:
        cfg.region = list(args.region)
    if args.rows:
        cfg.rows = args.rows
    if args.cols:
        cfg.cols = args.cols
    if args.threshold is not None:
        cfg.fill_threshold = args.threshold
    if args.auto:
        cfg.auto_detect = True
    if args.items:
        cfg.item_filter = True
    if args.no_log:
        cfg.enable_logging = False
    if args.save_crops:
        cfg.save_crops = True
    if args.overlay:
        cfg.overlay = True
    if args.debug:
        cfg.debug = True

    print(f"[cfg] schermo rilevato={cfg.search_region[2]}x{cfg.search_region[3]}  "
          f"region={cfg.region} grid={cfg.rows}x{cfg.cols} soglia={cfg.fill_threshold}")
    print(f"[cfg] auto-detect={cfg.auto_detect}  item-filter={cfg.item_filter}  "
          f"overlay={cfg.overlay}  log={cfg.enable_logging}")
    print(f"[cfg] file: {CONFIG_PATH}")

    if args.image:
        return run_image_scan(cfg, args.image)

    if args.test_click:
        return run_click_test(cfg)

    if args.test_world:
        return run_world_click_test(cfg)

    overlay = None
    if cfg.overlay:
        overlay = Overlay()
        overlay.start()
        print("[cfg] overlay attivo")

    app = App(cfg, overlay)

    try:
        import keyboard

        keyboard.add_hotkey(cfg.toggle_key, app.toggle)
        keyboard.add_hotkey(cfg.panic_key, app.panic)
        print(f"[cfg] {cfg.toggle_key.upper()}=on/off  {cfg.panic_key.upper()}=stop")
    except Exception as exc:  # pragma: no cover
        print(f"[warn] hotkey globali non disponibili ({exc}). Esegui come amministratore.")

    if args.once:
        if args.scan:
            app._print_scan()
        else:
            clicked = app.looter.run_cycle()
            print(f"[once] cliccati {clicked} slot")
        app.looter.close()
        if overlay is not None:
            overlay.stop()
        return 0

    if args.scan:
        print("[scan] modalita' scansione (nessun click). Ctrl+C per uscire.")
    else:
        print("[bot] pronto. Premi F8 per iniziare.")

    app.loop(scan_only=args.scan, interval=args.interval)

    import cv2

    cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    sys.exit(main())
