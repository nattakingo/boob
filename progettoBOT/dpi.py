"""
dpi.py - Rende il processo DPI-aware su Windows.

VA IMPORTATO PER PRIMO in ogni entry point, prima di tkinter/mss/pynput.

Perche': se un processo NON e' DPI-aware, Windows lo fa girare in un "spazio
coordinate virtualizzato" ridotto (es. su un 1920x1080 con scaling 125% vede
1536x864). In quel caso le coordinate che usiamo per catturare e per cliccare
NON combaciano con quelle reali del gioco -> calibrazione e click fuori posto.

Rendendo il processo per-monitor DPI-aware, vediamo sempre le coordinate
reali dello schermo (1920x1080) e tutto e' 1:1 con il gioco.
"""

import sys


def enable() -> str:
    if sys.platform != "win32":
        return "non-Windows, niente da fare"
    import ctypes

    user32 = ctypes.windll.user32
    shcore = ctypes.windll.shcore

    # 1) Windows 10 1703+ : per-monitor v2
    try:
        ok = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        if ok:
            return "per-monitor v2"
    except Exception:
        pass

    # 2) Windows 8.1+ : per-monitor
    try:
        shcore.SetProcessDpiAwareness(2)
        return "per-monitor"
    except Exception:
        pass

    # 3) fallback: system-aware
    try:
        user32.SetProcessDPIAware()
        return "system-aware"
    except Exception:
        return "impossibile attivare DPI awareness"


_MODE = enable()


def mode() -> str:
    """Ritorna la modalita' DPI awareness ottenuta (per i log di debug)."""
    return _MODE
