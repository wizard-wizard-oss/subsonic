"use strict";
// Podcasts : lecteur (reprise, ±15/30 s, vitesse, minuteur d'arrêt, enregistrement de la progression)

class PodcastPlayer {
  static SPEEDS = [1, 1.25, 1.5, 1.75, 2, 0.8];
  static SLEEP_STEPS = [0, 15, 30, 45, 60];
  static SAVE_EVERY_MS = 10000;

  constructor() {
    this.audio = new Audio();
    this.audio.preload = "auto";
    this.episode = null;
    this.speedIndex = 0;
    this.sleepIndex = 0;
    this.sleepTimer = null;
    this.lastSave = 0;
    this.bindAudio();
    this.bindControls();
  }

  isCurrent(id) { return !!this.episode && this.episode.id === id; }

  /* ---------- lecture ---------- */
  play(episode) {
    if (this.isCurrent(episode.id)) { this.toggle(); return; }
    this.saveNow();
    this.episode = episode;
    this.audio.src = episode.audio;
    this.audio.playbackRate = PodcastPlayer.SPEEDS[this.speedIndex];
    const start = episode.pos > 10 ? episode.pos : 0;
    this.audio.onloadedmetadata = () => { if (start) this.audio.currentTime = start; this.refresh(); };
    this.audio.play().catch(() => toast("Lecture impossible : épisode introuvable ou réseau coupé"));
    $("#bar").hidden = false;
    this.show();
    this.refresh();
  }
  toggle() { if (this.audio.paused) this.audio.play().catch(() => {}); else this.audio.pause(); }
  skip(seconds) { this.audio.currentTime = Math.max(0, Math.min(this.length(), this.audio.currentTime + seconds)); }
  seekRatio(ratio) { if (this.length()) this.audio.currentTime = ratio * this.length(); }
  length() { return this.audio.duration || (this.episode && this.episode.duration) || 0; }

  /* ---------- vitesse et minuteur ---------- */
  cycleSpeed() {
    this.speedIndex = (this.speedIndex + 1) % PodcastPlayer.SPEEDS.length;
    this.audio.playbackRate = PodcastPlayer.SPEEDS[this.speedIndex];
    this.refresh();
  }
  cycleSleep() {
    this.sleepIndex = (this.sleepIndex + 1) % PodcastPlayer.SLEEP_STEPS.length;
    clearTimeout(this.sleepTimer);
    const minutes = PodcastPlayer.SLEEP_STEPS[this.sleepIndex];
    if (minutes) this.sleepTimer = setTimeout(() => this.sleepNow(), minutes * 60000);
    this.refresh();
  }
  sleepNow() { this.audio.pause(); this.sleepIndex = 0; this.refresh(); toast("Minuteur : lecture arrêtée"); }

  /* ---------- progression ---------- */
  saveNow() {
    if (!this.episode) return;
    const e = this.episode;
    ppost("progress", {id: e.id, feed: e.feed, title: e.title, podcast: e.podcast, image: e.image, audio: e.audio,
                       pos: this.audio.currentTime || 0, dur: this.length()}).catch(() => {});
    this.lastSave = Date.now();
  }
  markDone() {
    if (!this.episode) return;
    ppost("played", {id: this.episode.id, played: true}).then(() => toast("Marqué comme écouté")).catch(() => {});
  }

  /* ---------- liaisons ---------- */
  bindAudio() {
    const a = this.audio;
    a.ontimeupdate = () => { this.paintProgress(); if (Date.now() - this.lastSave > PodcastPlayer.SAVE_EVERY_MS) this.saveNow(); };
    a.onpause = () => { this.saveNow(); this.refresh(); };
    a.onplay = () => this.refresh();
    a.onended = () => { this.saveNow(); this.refresh(); };
    a.onerror = () => toast("Erreur de lecture");
    window.addEventListener("pagehide", () => this.saveNow());
    setInterval(() => { if (!$("#np").hidden && !a.paused) fetch("/control/awake?on=1").catch(() => {}); }, 15000);
    setInterval(async () => {          // le menu du Pi peut demander une pause (une radio démarre ailleurs)
      try { if ((await (await fetch("/control/poll")).json()).cmd === "pause" && !a.paused) a.pause(); } catch (e) {}
    }, 1500);
  }
  bindControls() {
    $("#bpp").onclick = $("#nppp").onclick = () => this.toggle();
    $("#bback").onclick = $("#npback").onclick = () => this.skip(-15);
    $("#bfwd").onclick = $("#npfwd").onclick = () => this.skip(30);
    $("#npspeed").onclick = () => this.cycleSpeed();
    $("#npsleep").onclick = () => this.cycleSleep();
    $("#npdone").onclick = () => this.markDone();
    $("#bnp").onclick = () => { $("#np").hidden = false; this.refresh(); };
    $("#npclose").onclick = () => { $("#np").hidden = true; };
    for (const [id, host] of [["bprog", "#bprog"], ["npbar", "#npbar"]]) {
      $(host).onclick = ev => { const r = $(host).getBoundingClientRect(); this.seekRatio((ev.clientX - r.left) / r.width); };
    }
    $("#bback").innerHTML = $("#npback").innerHTML = ic("back", 26);
    $("#bfwd").innerHTML = $("#npfwd").innerHTML = ic("fwd", 26);
    $("#npclose").innerHTML = ic("down", 28);
  }

  /* ---------- affichage ---------- */
  show() {
    const e = this.episode;
    $("#btitle").textContent = $("#nptitle").textContent = e.title;
    $("#bsub").textContent = $("#npsub").textContent = e.podcast;
    $("#npdesc").textContent = e.desc || "";
    for (const sel of ["#bimg", "#npimg"]) { $(sel).src = e.image || ""; $(sel).style.visibility = e.image ? "visible" : "hidden"; }
    $("#npbg").style.backgroundImage = e.image ? 'url("' + e.image.replace(/"/g, "%22") + '")' : "none";
  }
  refresh() {
    const icon = ic(this.audio.paused ? "play" : "pause", 30);
    $("#bpp").innerHTML = $("#nppp").innerHTML = icon;
    $("#npspeed").textContent = PodcastPlayer.SPEEDS[this.speedIndex] + "×";
    const minutes = PodcastPlayer.SLEEP_STEPS[this.sleepIndex];
    $("#npsleep").textContent = minutes ? "Arrêt dans " + minutes + " min" : "Minuteur";
    this.paintProgress();
  }
  paintProgress() {
    const length = this.length(), now = this.audio.currentTime || 0;
    const width = (length ? Math.min(100, now / length * 100) : 0) + "%";
    document.querySelectorAll("#bprog i, #npbar i").forEach(i => { i.style.width = width; });
    $("#npcur").textContent = fmtTime(now);
    $("#npdur").textContent = fmtTime(length);
  }
}
const player = new PodcastPlayer();
