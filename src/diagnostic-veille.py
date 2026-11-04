#!/usr/bin/env python3
"""Diagnostic de l'écran de veille : quel périphérique d'entrée « réveille » le menu ?

À lancer sur le Pi, SANS toucher l'écran, pendant une radio qui joue :
    sudo python3 diagnostic-veille.py
Le menu repousse l'écran de veille à chaque événement d'un périphérique (/dev/input/event*).
Si un périphérique envoie des événements tout seul, l'horloge ne démarre jamais.
"""
import glob
import os
import select
import time

DURATION = 40


def device_name(path):
    try:
        with open("/sys/class/input/%s/device/name" % os.path.basename(path), encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return "?"


def main():
    devices = {}
    for path in sorted(glob.glob("/dev/input/event*")):
        try:
            devices[os.open(path, os.O_RDONLY | os.O_NONBLOCK)] = path
        except OSError as error:
            print("Illisible : %s (%s) — lancez avec sudo ?" % (path, error))
    counts = dict.fromkeys(devices.values(), 0)
    print("Écoute de %d périphériques pendant %d s. Ne touchez pas l'écran…" % (len(devices), DURATION))
    end = time.time() + DURATION
    while time.time() < end and devices:
        ready, _, _ = select.select(list(devices), [], [], 1)
        for fd in ready:
            try:
                counts[devices[fd]] += len(os.read(fd, 4096)) // 24 or 1
            except OSError:
                pass
    print()
    for path, count in counts.items():
        print("%-20s %-40s %d événement(s)" % (path, device_name(path), count))
    noisy = [p for p, c in counts.items() if c]
    print("\nConclusion :", "ces périphériques bougent sans que vous touchiez : " + ", ".join(noisy)
          if noisy else "aucun événement : l'écran de veille ne vient pas des périphériques d'entrée.")


if __name__ == "__main__":
    main()
