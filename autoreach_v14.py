# -*- coding: utf-8 -*-
"""
autoreach_v14.py — Entry point for AutoReach v14
Run: python autoreach_v14.py
"""
import logging
import os
import sys
import tkinter as tk
from tkinter import messagebox, simpledialog

# ── Logging setup ────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("autoreach.log", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("autoreach")

from core.database  import Database
from core.settings  import SettingsManager
from core.sender    import Sender, WhatsAppWebAdapter, DryRunAdapter
from core.scheduler import CampaignScheduler, SchedulerCallbacks
from security.auth  import PINLock
from ui.theme       import apply_styles, BG, ACCENT, MUTED, TEXT
from ui.app         import AutoReachApp


def _check_pin(root: tk.Tk, lock: PINLock) -> bool:
    """Show PIN dialog if lock is enabled. Returns True if access granted."""
    if not lock.is_enabled():
        return True
    for attempt in range(3):
        pin = simpledialog.askstring(
            "AutoReach v14 — Locked",
            f"Enter PIN to unlock (attempt {attempt+1}/3):",
            show="*", parent=root,
        )
        if pin is None:
            return False
        if lock.verify(pin):
            return True
        messagebox.showwarning("Wrong PIN",
                               "Incorrect PIN. Try again.", parent=root)
    messagebox.showerror("Locked", "Too many failed attempts. Exiting.")
    return False


def main() -> None:
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    root = tk.Tk()
    root.withdraw()           # hide until PIN check passes
    root.title("AutoReach v14")
    root.geometry("980x920")
    root.configure(bg=BG)
    root.minsize(860, 800)

    apply_styles(root)

    # ── Core services ────────────────────────────────────────
    db   = Database()
    mgr  = SettingsManager()
    lock = PINLock(mgr)

    # ── PIN check ────────────────────────────────────────────
    if not _check_pin(root, lock):
        root.destroy()
        return

    root.deiconify()          # show window after PIN passed

    # ── Crash recovery ───────────────────────────────────────
    s = mgr.settings
    adapter = DryRunAdapter() if s.dry_run else WhatsAppWebAdapter(s)
    sched   = CampaignScheduler(db=db, settings=s, adapter=adapter)
    sched.recover_on_startup()

    # ── Launch UI ────────────────────────────────────────────
    app = AutoReachApp(root, db=db, mgr=mgr, scheduler=sched)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()
    # ── Cleanup ──────────────────────────────────────────────
    sched.shutdown(timeout=5)
    db.close()
    logger.info("AutoReach v14 exited cleanly.")


if __name__ == "__main__":
    main()
