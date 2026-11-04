"use strict";
// File d'attente commune (écran du Pi) : la file de la page est enregistrée sur le Pi à chaque changement
// (retrouvée après un redémarrage, visible des téléphones), et les ajouts faits depuis un téléphone y sont rangés.

const QUEUE_SAVE_DELAY_MS = 600;
const QUEUE_TAKE_EVERY_MS = 1500;

class SharedQueue {
  constructor() { this.saved = ""; this.timer = null; }

  start() {
    this.restore();
    setInterval(() => this.takeRequests(), QUEUE_TAKE_EVERY_MS);
  }

  /* Au démarrage : on retrouve la file enregistrée (sans lancer la lecture) */
  async restore() {
    if (queue.length) return;
    try {
      const state = await (await fetch("/queue/state")).json();
      if (!state.items.length || queue.length) return;
      queue = state.items.map(item => Object.assign({}, item.track, {_addedBy: item.addedBy}));
      qi = Math.max(-1, state.currentIndex);
      this.saved = this.signature();
      refreshUI();
    } catch (e) { /* pas de file enregistrée : on démarre vide */ }
  }

  signature() { return JSON.stringify([qi, queue.map(s => s.id + ":" + (s._addedBy || ""))]); }

  /* Appelée à chaque rafraîchissement de l'interface : n'envoie que si la file a changé */
  scheduleSave() {
    if (this.signature() === this.saved) return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.save(), QUEUE_SAVE_DELAY_MS);
  }

  async save() {
    const signature = this.signature();
    const body = {currentIndex: qi, items: queue.map(s => ({track: s, addedBy: s._addedBy || "screen"}))};
    try {
      const r = await fetch("/queue/save", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)});
      if (r.ok) this.saved = signature;
    } catch (e) { /* nouvel essai au prochain changement */ }
  }

  /* Ajouts demandés depuis un téléphone */
  async takeRequests() {
    let requests;
    try { requests = (await (await fetch("/queue/take", {method: "POST"})).json()).requests || []; } catch (e) { return; }
    if (!requests.length) return;
    const wasIdle = !cur() || (audio.paused && qi >= queue.length - 1);
    requests.forEach(request => this.insert(Object.assign({}, request.track, {_addedBy: request.addedBy}), request.mode));
    toast(requests.length === 1 ? "Ajouté depuis un téléphone : " + requests[0].track.title
                                : requests.length + " titres ajoutés depuis un téléphone");
    if (wasIdle) playIdx(Math.max(0, cur() ? qi + 1 : 0)); else refreshUI();
  }

  /* « après ce titre » : juste après le titre en cours, derrière les autres demandes « après ce titre » */
  insert(track, mode) {
    if (mode !== "next" || qi < 0) { queue.push(track); return; }
    let at = qi + 1;
    while (at < queue.length && queue[at]._playNext) at++;
    track._playNext = true;
    queue.splice(at, 0, track);
  }
}

const sharedQueue = new SharedQueue();
sharedQueue.start();
