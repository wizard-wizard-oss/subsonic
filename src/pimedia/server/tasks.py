"""Tâches de fond (rafraîchir le cache, détecter les nouveautés…) : les erreurs n'interrompent jamais le serveur."""
import threading


def in_background(func, *args, delay=0):
    def job():
        try:
            func(*args)
        except Exception:       # noqa: BLE001 - une tâche de fond ratée sera refaite plus tard
            pass
    runner = threading.Timer(delay, job) if delay else threading.Thread(target=job)
    runner.daemon = True
    runner.start()
    return runner
