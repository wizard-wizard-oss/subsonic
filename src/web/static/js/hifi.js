"use strict";
// Lecture haute fidélité (écran du Pi) : le son est joué par mpv sur le Pi, à la fréquence d'origine du fichier.
// MpvAudio imite l'élément <audio> (src, play(), pause(), currentTime…) : le reste de l'application ne change pas.

const HIFI_POLL_MS = 400;

class MpvAudio {
  constructor() {
    this.dataset = {};
    this.handlers = {};
    this.url = "";
    this.state = {pos: 0, duration: 0, paused: true, ended: null, errors: null};
    this.stateAt = Date.now();
    this.wantPaused = true;
    this.error = null;
    this.vol = 1;
    this.pauseTimer = null;
    this.nextUrl = null;
    this.timer = setInterval(() => this.poll(), HIFI_POLL_MS);
  }

  fire(name) { const fn = this.handlers[name] || this[name + "_"]; if (typeof fn === "function") fn(); }

  async cmd(action, extra) {
    const r = await fetch("/player/cmd", {method: "POST", headers: {"Content-Type": "application/json"},
                                          body: JSON.stringify(Object.assign({action}, extra || {}))});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
    return j;
  }

  /* ---------- propriétés de l'élément audio ---------- */
  get src() { return this.url; }
  set src(url) {
    clearTimeout(this.pauseTimer);              // loadTrack fait pause() puis src= : pas de coupure entre les deux
    this.url = url; this.error = null; this.wantPaused = false;
    this.state.pos = 0; this.stateAt = Date.now();
    this.cmd("load", {url}).catch(e => { this.error = {code: "hifi", message: e.message}; this.fire("onerror"); });
  }
  get paused() { return this.wantPaused || this.state.paused; }
  get currentTime() {
    const running = !this.paused ? (Date.now() - this.stateAt) / 1000 : 0;
    return Math.min(this.state.pos + running, this.state.duration || Infinity);
  }
  set currentTime(t) { this.state.pos = t; this.stateAt = Date.now(); this.cmd("seek", {value: t}).catch(() => {}); }
  get duration() { return this.state.duration || NaN; }
  get readyState() { return this.state.duration ? 4 : 0; }
  get volume() { return this.vol; }
  set volume(v) { this.vol = Math.min(1, Math.max(0, v)); this.cmd("volume", {value: Math.round(this.vol * 100)}).catch(() => {}); }

  /* ---------- commandes ---------- */
  play() {
    this.wantPaused = false;
    if (!this.url) return Promise.resolve();
    return this.cmd("play").then(() => { this.fire("onplay"); }).catch(() => {});
  }
  pause() {
    this.wantPaused = true;
    clearTimeout(this.pauseTimer);
    this.pauseTimer = setTimeout(() => { this.cmd("pause").catch(() => {}); this.fire("onpause"); }, 0);
  }
  load() {}
  removeAttribute(name) { if (name === "src") this.url = ""; }

  /* Titre suivant préchargé : mpv l'enchaîne sans blanc. null = rien à précharger */
  queueNext(url) {
    if (url === this.nextUrl) return;
    this.nextUrl = url;
    this.cmd("preload", {url: url || ""}).catch(() => { this.nextUrl = null; });
  }

  /* ---------- suivi de l'état de mpv ---------- */
  async poll() {
    let s;
    try { s = await (await fetch("/player/state")).json(); } catch (e) { return; }
    const before = this.state;
    this.state = s; this.stateAt = Date.now();
    if (before.ended !== null && s.ended > before.ended) {
      if (s.url && s.url !== this.url) { this.url = s.url; this.nextUrl = null; }   // mpv a enchaîné tout seul
      this.fire("onended");
    }
    if (before.errors !== null && s.errors > before.errors) { this.error = {code: "hifi"}; this.fire("onerror"); }
    if (before.paused && !s.paused) { this.fire("onplay"); this.fire("onplaying"); }
    if (!s.paused) this.fire("ontimeupdate");
  }
}

/* Au démarrage : si la lecture haute fidélité est activée, le lecteur de la page passe par mpv */
async function setupHifi() {
  try {
    const s = await (await fetch("/player/state")).json();
    window.HIFI = s;
    if (s.enabled && s.available) audio.useOutput(new MpvAudio());
  } catch (e) { /* mpv indisponible : lecture par le navigateur */ }
}

/* Titre qui suivra : préchargé dans mpv pour un enchaînement sans blanc */
function upcomingTrack() {
  if (typeof guestHandover === "object" && guestHandover && guestHandover.armed && guestHandover.state.status === "waiting") return null;
  if (repeat === 2) return null;
  const next = qi + 1 < queue.length ? queue[qi + 1] : (repeat === 1 ? queue[0] : null);
  return next && !next.youtubeId ? next : null;
}
function syncPreload() {
  if (!audio.queueNext) return;
  const next = upcomingTrack();
  audio.queueNext(next ? trackUrl(next, 0) : null);
}

async function toggleHifi() {
  const on = !(window.HIFI && window.HIFI.enabled);
  try {
    audio.pause();
    await fetch("/player/cmd", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({action: "enable", value: on})});
    toast(on ? "Lecture haute fidélité activée" : "Lecture par le navigateur");
    setTimeout(() => location.reload(), 800);       // le lecteur de la page change de sortie au rechargement
  } catch (e) { toast(e.message); }
}

setupHifi();
