"""Niveaux de l'égaliseur, calculés sur le son réellement diffusé (moniteur de la sortie par défaut).

On n'écoute la sortie que lorsqu'un son est joué : écouter en permanence empêchait PipeWire de mettre la sortie
en veille, et l'ampli ne s'éteignait jamais tout seul."""
import subprocess
import time

RATE = 22050
BLOCK = 1024
CHECK_EVERY = 40        # ~2 s de son entre deux vérifications « joue-t-on encore ? »


def level_of(db, decay_from):
    """dB -> niveau 0..1, avec une retombée douce (le segment ne s'éteint pas d'un coup)."""
    return max(min(1.0, max(0.0, (db + 85) / 50)), decay_from * 0.82)


class Spectrum:
    def __init__(self, columns, pulse):
        self.columns = columns
        self.pulse = pulse
        self.levels = [0.0] * columns

    def lit(self, segments):
        """Nombre de segments allumés par colonne."""
        return [int(level * segments + 0.5) for level in self.levels]

    def clear(self):
        self.levels = [0.0] * self.columns

    def loop(self):
        try:
            import numpy
        except ImportError:
            return                      # pas de numpy : égaliseur éteint, le reste fonctionne
        window = numpy.hanning(BLOCK)
        edges = numpy.logspace(numpy.log10(2), numpy.log10(BLOCK // 2), self.columns + 1).astype(int)
        while True:
            if not self.pulse.playing():
                self.clear()
                time.sleep(2)
                continue
            self._listen(numpy, window, edges)
            time.sleep(1)

    def _listen(self, numpy, window, edges):
        process = None
        try:
            process = subprocess.Popen(["parec", "-d", "@DEFAULT_MONITOR@", "--format=s16le", "--rate=%d" % RATE,
                                        "--channels=1", "--latency-msec=40"],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            reads = 0
            while True:
                buf = process.stdout.read(BLOCK * 2)
                if len(buf) < BLOCK * 2:
                    return
                reads += 1
                if reads % CHECK_EVERY == 0 and not self.pulse.playing():
                    return                  # plus rien ne joue : on lâche la sortie pour qu'elle se mette en veille
                samples = numpy.frombuffer(buf, dtype=numpy.int16).astype(numpy.float32) / 32768.0
                spectrum = numpy.abs(numpy.fft.rfft(samples * window)) / BLOCK
                for i in range(self.columns):
                    lo = int(edges[i])
                    hi = max(int(edges[i + 1]), lo + 1)
                    db = 20 * numpy.log10(float(spectrum[lo:hi].mean()) + 1e-7)
                    self.levels[i] = level_of(db, self.levels[i])
        except OSError:
            return
        finally:
            if process is not None:
                process.kill()
