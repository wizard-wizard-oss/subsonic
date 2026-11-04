#!/usr/bin/env python3
"""Diagnostic de la veille de l'ampli : qui garde ouverte la sortie audio vers le DAC USB ?

À lancer sur le Pi, après avoir mis la musique en PAUSE (ou l'avoir arrêtée) :
    python3 diagnostic-ampli.py [secondes]        (90 s par défaut)
Toutes les 5 s : état de la sortie PipeWire (RUNNING / IDLE / SUSPENDED), flux de lecture (en pause ou non),
programmes qui enregistrent, et état réel de la carte USB (/proc/asound : « closed » = l'ampli ne reçoit plus rien).
"""
import glob
import re
import sys
import time

from pimedia.menu.audio import parse_sink_inputs, run_command

DEFAULT_SECONDS = 90
EVERY = 5


def parse_sinks(text):
    """« pactl list short sinks » -> [(nom, état)]."""
    sinks = []
    for line in text.splitlines():
        fields = line.split("\t") if "\t" in line else line.split()
        if len(fields) >= 2:
            sinks.append((fields[1], fields[-1]))
    return sinks


def open_cards():
    """Cartes dont un flux de lecture est ouvert : {« card1/pcm0p »: état}. Fermée = absente."""
    cards = {}
    for path in glob.glob("/proc/asound/card*/pcm*p/sub*/status"):
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        if "closed" not in text:
            match = re.search(r"state:\s*(\w+)", text)
            cards["/".join(path.split("/")[3:5])] = match.group(1) if match else "?"
    return cards


def verdict(sinks, streams, recorders, cards):
    """Phrase qui dit pourquoi l'ampli ne peut pas s'endormir, ou qu'il le peut."""
    playing = [s.label for s in streams if not s.corked]
    paused = [s.label for s in streams if s.corked]
    if playing:
        return "Un programme joue : %s. Mettez-le en pause puis relancez." % ", ".join(playing)
    if not cards:
        return "OK : la carte son est fermée, l'ampli ne reçoit plus de flux (il peut s'endormir)."
    if paused:
        return ("La carte reste ouverte alors que tout est en pause. Flux encore ouverts (en pause) : %s. "
                "Si c'est « pi-media-hifi » : mpv n'a pas été libéré (il l'est après 30 s de pause)."
                % ", ".join(paused))
    if recorders:
        return "Aucun flux de lecture, mais un programme enregistre la sortie : %s." % ", ".join(recorders)
    if any(state == "SUSPENDED" for _, state in sinks):
        return "La sortie PipeWire est suspendue mais la carte reste ouverte : voir « pw-top » et wireplumber."
    return ("Aucun flux, aucun enregistreur, et pourtant la carte reste ouverte : PipeWire/WirePlumber ne suspend pas "
            "la sortie (voir « wpctl status », « pw-top », réglage session.suspend-timeout-seconds).")


def sample():
    sinks = parse_sinks(run_command(["pactl", "list", "short", "sinks"]))
    streams = parse_sink_inputs(run_command(["pactl", "list", "sink-inputs"]))
    recorders = [line.split("\t")[-1] for line in run_command(["pactl", "list", "short", "source-outputs"]).splitlines() if line]
    return sinks, streams, recorders, open_cards()


def main():
    seconds = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SECONDS
    print("Mettez la musique en pause. Mesure pendant %d s…\n" % seconds)
    end = time.time() + seconds
    last = None
    while True:
        sinks, streams, recorders, cards = sample()
        print("%s  sorties=%s  flux=%s  enregistreurs=%d  cartes ouvertes=%s" % (
            time.strftime("%H:%M:%S"), ", ".join("%s:%s" % s for s in sinks) or "-",
            ", ".join("%s%s" % (s.label, " (pause)" if s.corked else "") for s in streams) or "aucun",
            len(recorders), cards or "aucune"))
        last = verdict(sinks, streams, recorders, cards)
        if time.time() >= end:
            break
        time.sleep(EVERY)
    print("\nConclusion :", last)


if __name__ == "__main__":
    main()
