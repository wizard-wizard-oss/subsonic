"use strict";
// Invités AirPlay / Bluetooth (écran du Pi) :
// - un téléphone se met à jouer : la musique baisse, se met en pause, puis reprend quand il s'arrête ;
// - un téléphone se connecte et attend en pause : il passera après le titre en cours.

const FADE_MS = 1200;
const POLL_MS = 1500;
const HANDOVER_TIMEOUT_MS = 8000;      // le téléphone n'a pas démarré : on reprend notre musique

class GuestHandover {
  constructor(banner) {
    this.banner = banner;
    this.state = {status: null};
    this.armed = false;                  // « passera après ce titre » : automatique pour un téléphone qui vient d'arriver
    this.pausedForGuest = false;
    this.nextAfterGuest = false;         // passage en fin de titre : au retour, on enchaîne sur le titre suivant
    this.handoverAt = 0;
    this.lastPlayingAt = 0;
    this.quietPolls = 0;
  }

  start() {
    setInterval(() => { if (!audio.paused) this.lastPlayingAt = Date.now(); }, 500);
    setInterval(() => this.poll(), POLL_MS);
  }

  async poll() {
    let s;
    try { s = await (await fetch("/control/guest")).json(); } catch (e) { return; }
    const before = this.state.status;
    this.state = s;
    if (s.status === "waiting" && !before) this.armed = true;           // téléphone qui vient de se connecter
    if (s.status === "waiting" && before === "playing") this.armed = false;  // il vient de finir : pas de nouveau passage tout seul
    if (s.status === "playing") this.guestPlaying();
    else this.guestQuiet();
    this.paintBanner();
  }

  guestPlaying() {
    this.quietPolls = 0;
    this.handoverAt = 0;
    if (!audio.paused) { this.fadeOutAndPause(); this.pausedForGuest = true; }
    else if (Date.now() - this.lastPlayingAt < 4000) this.pausedForGuest = true;   // déjà mis en pause par le menu
  }

  guestQuiet() {
    if (!audio.paused) { this.pausedForGuest = false; this.nextAfterGuest = false; return; }   // on a relancé à la main
    if (this.handoverAt && Date.now() - this.handoverAt > HANDOVER_TIMEOUT_MS) {
      this.handoverAt = 0; this.armed = false;
      toast("Le téléphone n’a pas démarré : la musique reprend");
      this.resume();
      return;
    }
    if (this.pausedForGuest && !this.handoverAt && ++this.quietPolls >= 2) this.resume();
  }

  /* Appelée à la fin de chaque titre : true si on passe la main au téléphone (la page n'enchaîne pas) */
  onTrackEnd() {
    if (this.state.status !== "waiting" || !this.armed) return false;
    this.handOver(true);
    return true;
  }

  async handOver(afterTrack) {
    if (afterTrack) audio.pause();                       // titre terminé : on reste dessus en attendant le retour
    else if (!audio.paused) await this.fadeOutAndPause();
    try {
      const r = await fetch("/control/guest", {method: "POST"});
      if (!r.ok) throw new Error();
    } catch (e) {
      toast("Le téléphone ne répond pas");
      if (afterTrack) playNext(); else this.resume();
      return;
    }
    this.armed = false;
    this.pausedForGuest = true;
    this.nextAfterGuest = afterTrack;
    this.handoverAt = Date.now();
    toast("À " + this.state.label + " de jouer…");
    this.paintBanner();
  }

  resume() {
    this.pausedForGuest = false;
    this.quietPolls = 0;
    if (this.nextAfterGuest) {
      this.nextAfterGuest = false;
      if (qi + 1 < queue.length) { playIdx(qi + 1); return; }
      return;
    }
    if (cur()) this.fadeIn();
  }

  fadeOutAndPause() {
    return new Promise(done => {
      const start = audio.volume, steps = 12;
      let i = 0;
      const t = setInterval(() => {
        audio.volume = start * (1 - ++i / steps);
        if (i >= steps) { clearInterval(t); audio.pause(); audio.volume = start; done(); }
      }, FADE_MS / steps);
    });
  }

  fadeIn() {
    const target = audio.volume || 1, steps = 12;
    let i = 0;
    audio.volume = 0;
    audio.play().catch(() => {});
    const t = setInterval(() => {
      audio.volume = target * (++i / steps);
      if (i >= steps) clearInterval(t);
    }, FADE_MS / steps);
  }

  /* Bandeau discret au-dessus de la barre du lecteur */
  paintBanner() {
    if (typeof syncPreload === "function") syncPreload();   // haute fidélité : pas de titre préchargé si un téléphone attend
    const s = this.state, b = this.banner;
    const show = s.status === "waiting" && !this.handoverAt && !audio.paused && cur();
    b.hidden = !show;
    if (!show) return;
    b.innerHTML = "";
    const text = document.createElement("span");
    text.textContent = this.armed ? s.label + " en attente : passera après ce titre" : s.label + " connecté";
    b.appendChild(text);
    const button = (label, fn) => { const x = document.createElement("button"); x.type = "button"; x.textContent = label; x.onclick = fn; b.appendChild(x); };
    if (this.armed) button("Annuler", () => { this.armed = false; this.paintBanner(); });
    else button("Après ce titre", () => { this.armed = true; this.paintBanner(); });
    button("Maintenant", () => this.handOver(false));
  }
}

const guestHandover = (() => {
  const banner = document.createElement("div"); banner.id = "guestbar"; banner.hidden = true;
  document.body.appendChild(banner);
  const g = new GuestHandover(banner);
  g.start();
  return g;
})();
