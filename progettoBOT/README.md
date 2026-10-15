# Auto-Loot per Albion Online (progetto di studio)

Bot di automazione del loot scritto in **Python** con **OpenCV**, **mss** e **pynput**.
Nasce come progetto per imparare computer vision e automazione di input: **non** inietta
nulla nel gioco, non legge la memoria e non tocca i pacchetti. Vede i pixel dello schermo
e muove il mouse come farebbe una persona.

> ⚠️ **Avviso.** L'automazione del gameplay viola i Termini di Servizio di Albion Online e
> puo' portare a ban (anche permanente). Usalo consapevolmente, idealmente su un account
> secondario e mai in attivita' competitive. Il progetto e' fornito a scopo didattico.

---

## Funzionalita'

| # | Feature | File | Stato |
|---|---------|------|-------|
| — | Rilevamento slot + auto-loot | `src/vision.py`, `src/looter.py` | ✅ |
| 1 | **Auto-detect della finestra** (template matching) | `src/autodetect.py` | ✅ |
| 2 | **Overlay trasparente** click-through sopra il gioco | `src/overlay.py` | ✅ |
| 3 | **Riconoscimento item** (filtro sulle icone) | `src/items.py` | ✅ |
| 4 | **Log statistiche** + soglia suggerita | `src/logger.py`, `stats.py` | ✅ |

## Risoluzione, DPI scaling e modalita' video

Il progetto legge le coordinate **reali** dello schermo: tutti i processi sono
**DPI-aware** (`dpi.py`). Inoltre il bot **rileva da solo la risoluzione** del
monitor all'avvio (la scrive in `search_region`), quindi non devi piu' indicarla a mano.

**Setup consigliato (il piu' semplice):** Windows, Albion e le catture tutti alla
**stessa risoluzione**, cioe' **1280×720**:
- **Windows**: Impostazioni → Sistema → Schermo → Risoluzione **1280×720**, scala **100%**;
- **Albion**: Impostazioni → Video → Risoluzione **1280×720**, modalita' **Borderless Fullscreen**.

Cosi' non c'e' nessuna scalatura di mezzo e le coordinate combaciano 1:1.

> Perche' **borderless** e non fullscreen esclusivo: il fullscreen esclusivo
> **non permette overlay** sopra il gioco. In borderless l'overlay funziona.

Se preferisci il **Window mode** va bene lo stesso: calibra sulla finestra del gioco.

Tutte le coordinate sono in pixel assoluti.


---

## Installazione

```powershell
python -m pip install -r requirements.txt
```

Richiede **Python 3.10+**. Sul tuo sistema e' gia' tutto installato (Python 3.15, OpenCV 5).

---

## Come funziona

```
captura schermo (mss)
      │
      ▼
[auto-detect]  trova la finestra con template matching  ────►  region dinamica
      │                                                          │
      ▼                                                          ▼
  region fissa ──► griglia 4 colonne ──► confronto celle ──► slot pieni
                                                              │
                     ┌────────────────────────────────────────┤
                     ▼                                        ▼
           [overlay] disegna sopra il gioco          [items] filtro icone
                     │                                        │
                     └────────────► click con Shift ◄─────────┘
                                        │
                                        ▼
                            [scroll] righe successive (se ce ne sono)
                                        │
                                        ▼
                             [logger] CSV statistiche
```

**Come si riconosce uno slot pieno.** La scheda di loot di Albion ha sempre
**4 colonne** di slot quadrati. Uno slot **vuoto** e' una superficie **piatta**
(nessuna texture), mentre uno **pieno** contiene l'icona dell'oggetto (texture e
bordi netti). Il punteggio combina:

    score = deviazione_standard(grigio) * 0.8 + densita_bordi(Canny)

Sugli screenshot reali gli slot vuoti stanno attorno a **3-5** e quelli pieni a
**60-75**: un distacco netto, facile da separare con `fill_threshold` (default 25).

Puoi **verificare il rilevamento su uno screenshot salvato**, senza il gioco aperto:
```powershell
python main.py --image snapshots\loot.png
```
Stampa `pieni=N/12` con lo score di ogni cella e salva `scan_debug.png`
(riquadri verdi = pieni, rossi = vuoti).

Serve che gli slot pieni restino tali per **2 frame consecutivi** prima di cliccare.

**Scroll.** La scheda mostra solo alcune righe: dopo aver svuotato quelle visibili,
il bot ruota la rotella del mouse dentro la finestra per far comparire le righe
successive e continua finche' non trova piu' nulla (fino a `max_scrolls` volte).

---

## Guida rapida (5 passi)

### 1. Calibra con DUE selezioni
```powershell
python calibrate.py
```
Il bot ti chiede **due rettangoli**:
1. **Tutto il blocco delle celle** — l'area che contiene tutte le caselle degli slot
   (non la barra del titolo, solo le celle). INVIO.
2. **Una sola cella** — un singolo slot, al centro. INVIO.

Da queste due misure il bot calcola le **righe visibili**; le **colonne sono
sempre 4** (fisse nella scheda di loot di Albion). Alla fine mostra un'anteprima:
controlla che ogni cella contenga un item.

> L'icona dell'item e' un po' piu' bassa della cella, quindi il bot taglia
> automaticamente qualche pixel dal fondo (`cell_trim_bottom`) cosi' i riquadri
> aderiscono all'item. Se vuoi ritoccarlo: `python gridtune.py` e usa i tasti
> **n** / **m**.

> **Consigliato se la finestra di loot e' difficile da catturare dal vivo** (si chiude
> subito, o davanti c'e' un'altra finestra): prima ferma lo schermo con uno screenshot:
> ```powershell
> python snapshot.py --delay 8          # torna su Albion e apri il loot entro 8s
> python calibrate.py --image snapshots\loot.png
> ```
> Cosi' le due selezioni le fai con calma sull'immagine ferma.

> Se vuoi ritoccare a mano la griglia in tempo reale: `python gridtune.py`
> (trascina la region, `+`/`-` righe, `[`/`]` colonne, `n`/`m` taglio dal fondo, `S` salva).
> Se invece vuoi scegliere tu la region e le righe/colonne: `python calibrate.py --region`.



### 2. (Opzionale) Auto-detect della finestra
Serve un dettaglio **fisso e distintivo** della finestra (cornice, angolo, sfondo del
titolo). Con la finestra di loot visibile:
```powershell
python calibrate.py --auto
```
1. seleziona il **dettaglio** (template),
2. seleziona la **region degli slot**.

Vengono salvati `templates/loot_frame.png` e l'offset, e l'auto-detect viene attivato.
Da ora la region si aggiorna da sola ovunque appaia la finestra.

### 3. Taratura della soglia (SENZA cliccare)
```powershell
python main.py --scan
```
Possibile variante con dati salvati: gioca un po' col bot attivo e poi
```powershell
python stats.py            # istogramma + soglia suggerita (Otsu)
python stats.py --save-config
```
`stats.py` legge i log, mostra la distribuzione dei punteggi e trova la **valle** tra
slot vuoti e pieni: e' la soglia migliore.

### 4. Avvia il bot
```powershell
python main.py --overlay --threshold 25
```
- **F8** = accendi/spegni
- **F9** = stop immediato (panic)
- **Q** = chiude la finestra di debug

### 5. (Opzionale) Filtro item
```powershell
python calibrate.py --item Borsa_T8     # cattura l'icona di un oggetto
python main.py --overlay --items        # loota secondo il filtro
```

---

## Riferimento comandi

| Comando | Descrizione |
|---|---|
| `python calibrate.py` | due selezioni (blocco celle + una cella) → righe/colonne automatiche |
| `python calibrate.py --image PATH` | come sopra, ma su uno screenshot salvato |
| `python snapshot.py` | screenshot con countdown (per la calibrazione) |
| `python gridtune.py` | regola la griglia a occhio, in tempo reale |
| `python calibrate.py --region` | (avanzato) region singola + righe/colonne a mano |
| `python calibrate.py --auto` | calibra l'auto-detect (template + region) |
| `python calibrate.py --item NOME` | salva l'icona di un oggetto |
| `python main.py --scan` | mostra i punteggi senza cliccare |
| `python main.py --image PATH` | analizza uno screenshot salvato (nessun click) |
| `python main.py --test-click` | diagnostica: clicca 1 slot e verifica se si svuota |
| `python main.py --overlay` | avvia con overlay sopra il gioco |
| `python main.py --debug` | avvia con anteprima OpenCV |
| `python main.py --auto` | usa l'auto-detect |
| `python main.py --items` | attiva il filtro item |
| `python main.py --save-crops` | salva i ritagli degli slot analizzati |
| `python main.py --no-log` | disabilita il CSV |
| `python main.py --once --scan` | un solo rilevamento, senza click |
| `python stats.py` | istogramma + soglia suggerita dai log |
| `python selftest.py` | testa vision + auto-detect + item senza il gioco |

---

## Le quattro feature in dettaglio

### 1. Auto-detect della finestra (`src/autodetect.py`)
Invece di una region fissa, cattura `search_region` (default 1280×720) e cerca
`templates/loot_frame.png` con `cv2.matchTemplate`. Se il match supera
`template_threshold` (0.72), ricava la region degli slot dalla posizione trovata
+ offset `auto_region = [dx, dy, w, h]`.
- **Pro:** la finestra puo' stare ovunque, non serve ricalibrare.
- **Contro:** il template va rifatto se cambi risoluzione o scala UI.

### 2. Overlay trasparente (`src/overlay.py`)
Finestra Tkinter frameless, topmost, con `-transparentcolor` (magenta) e
**click-through** via `WS_EX_TRANSPARENT` (i click passano al gioco).
Disegna i riquadri degli slot sopra il gioco in tempo reale: verde = da cliccare,
grigio = vuoto. Gira su un thread dedicato; `update()` aggiorna il disegno.

### 3. Riconoscimento item (`src/items.py`)
Metti un PNG per oggetto in `templates/items/` (nome file = nome item). Ogni slot
viene normalizzato a 44×44 in scala di grigi e confrontato con le icone tramite
correlazione normalizzata.
- `item_match_threshold`: quanto deve somigliare (default 0.70).
- `loot_all_if_no_match`: se `true` loota comunque i non riconosciuti, se `false`
  loota **solo** gli oggetti presenti nella libreria.

### 4. Log e statistiche (`src/logger.py`, `stats.py`)
Un CSV per sessione in `logs/` con: timestamp, riga, colonna, x, y, punteggio,
cliccato, item, crop. `save_crops` salva anche i ritagli PNG per ispezione.
`stats.py` calcola la soglia ottimale con **Otsu** (separatore a massima varianza
tra classi) e la salva con `--save-config`.

---

## Struttura del progetto

```
progetto BOT/
├─ config.py            # Settings + salvataggio/caricamento JSON
├─ main.py              # entry point: hotkey + loop + overlay
├─ calibrate.py         # region / auto-detect / icone item
├─ stats.py             # istogramma + soglia Otsu
├─ selftest.py          # test di vision, auto-detect e item
├─ requirements.txt
├─ config.json          # generato al primo avvio
├─ logs/                # CSV e crop
├─ templates/
│  ├─ loot_frame.png    # template per l'auto-detect (creato da calibrate --auto)
│  └─ items/            # icone oggetto (create da calibrate --item)
└─ src/
   ├─ screen.py         # cattura schermo (mss)
   ├─ vision.py         # punteggi slot, griglia, overlay_boxes, debug
   ├─ controller.py     # emulazione mouse/tastiera (pynput)
   ├─ autodetect.py     # template matching della finestra          [1]
   ├─ overlay.py        # overlay trasparente click-through          [2]
   ├─ items.py          # riconoscimento icone                       [3]
   ├─ logger.py         # log CSV                                    [4]
   └─ looter.py         # logica dei cicli (integra tutto)
```

---

## Taratura e problemi comuni

- **Clicca slot vuoti** → alza `fill_threshold` (es. 30–40); aumenta `slot_margin`.
- **Non clicca item pieni** → abbassa `fill_threshold`; controlla l'allineamento
  della griglia (deve esserci **1 item per cella**).
- **Il cursore si muove ma non loota / gli slot restano pieni** → l'emulazione del
  click non viene registrata dal gioco. Diagnostica precisa:
  `python main.py --test-click` (prova sia shift+click sia click semplice e dice
  quale funziona). Cause tipiche: click troppo rapidi (`pre_click`, `click_hold`),
  Albion non in primo piano, oppure serve il terminale **come amministratore**.
  Come ultima spiaggia prova `"modifier": "none"` in `config.json`.
- **Combacia ma non scrolla** → controlla `scroll_enabled` e `scroll_clicks` (negativo = giu').
- **Scrolla la visuale del gioco invece della scheda** → assicurati che la `region`
  sia sopra la scheda di loot (il bot porta il mouse al centro della region prima di scrollare).
- **Auto-detect non trova la finestra** → prova `calibrate.py --auto` con un template
  piu' contrastato; abbassa `template_threshold`.
- **Overlay non si vede / si vedono bordi magenta** → e' normale un piccolo alone sul
  testo; assicurati che il gioco sia in **finestra** o **borderless** (non fullscreen
  esclusivo), altrimenti l'overlay non puo' starci sopra.
- **Click troppo lenti/veloci** → `click_delay`, `cycle_delay`, `pre_click`,
  `click_hold` in `config.json` (millisecondi).
- **Hotkey non funzionano** → esegui il terminale **come amministratore**.
- **Scala UI di Albion** → se la cambi, ricalibra region e template.

---

## Idee future

- Rilevamento della finestra anche senza template (bordi/luminosita').
- Overlay con anteprima del crop per ogni slot.
- Stima del valore in silver con prezzo di mercato (Albion Online Data Project).
- Dialogo "loota tutto" se la finestra e' piena (piu' veloce del click per slot).

Buon divertimento con il codice! 🧪
