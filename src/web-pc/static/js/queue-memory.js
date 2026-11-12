"use strict";
/* File du compte : Subsonic est la référence entre navigateurs ; la copie locale garde aussi les sources
   externes et les changements pas encore envoyés. Aucun flux n'est chargé à la restauration. */

class QueueMemory {
  constructor(player) {
    this.player = player;
    this.enabled = false;
    this.restoring = false;
    this.revision = 0;
    this.generation = 0;
    this.state = null;
    this.remote = null;
    this.timer = null;
    this.saving = null;
    App.bus.on("queue", () => this.record());
    player.audio.addEventListener("pause", () => { this.record(); this.flush(); });
    this.checkpoint = event => {
      if (!this.enabled) return;
      if (this.retryRestore && !this.player.queue.length) this.start();
      else { this.record(); this.flush({keepalive: !!event && event.type === "pagehide"}); }
    };
    window.addEventListener("pagehide", this.checkpoint);
    window.addEventListener("online", this.checkpoint);
    document.addEventListener("visibilitychange", () => { if (document.hidden) this.checkpoint(); });
    setInterval(this.checkpoint, 15000);
  }

  /** Refuse une copie locale corrompue plutôt que d'empêcher le démarrage du lecteur. */
  static valid(state) {
    return !!state && Array.isArray(state.songs) && state.songs.length > 0 &&
      state.songs.every(song => song && typeof song === "object" &&
        (typeof song.id === "string" || typeof song.id === "number") && typeof song.title === "string") &&
      Number.isInteger(state.index) && state.index >= 0 && state.index < state.songs.length &&
      Number.isFinite(state.position) && state.position >= 0;
  }

  /** Seuls les identifiants Subsonic traversent cette API ; les doublons et leur ordre sont conservés. */
  static body(state) {
    const ids = state.songs.filter(song => !song.ext).map(song => String(song.id));
    const current = state.songs[state.index];
    return {ids, current: current && !current.ext ? String(current.id) : ids[0] || "",
      position: current && !current.ext ? Math.floor(state.position * 1000) / 1000 : 0};
  }

  write() {
    // Une ancienne copie « en attente » ne doit pas écraser le serveur si le quota empêche de la mettre à jour.
    if (!App.local.set(this.key, this.state)) App.local.remove(this.key);
  }

  apply(state) {
    this.restoring = true;
    try { this.player.restoreQueue(state.songs, state.index, state.position); }
    finally { this.restoring = false; }
  }

  start() {
    this.ready = this.restore();
    return this.ready;
  }

  async restore() {
    const generation = ++this.generation;
    this.key = "queue." + App.user.id;
    this.enabled = true;
    this.retryRestore = false;
    this.remote = null;
    this.state = App.local.get(this.key, null);
    if (!QueueMemory.valid(this.state)) this.state = null;
    if (this.state) this.apply(this.state);
    else this.apply({songs: [], index: -1, position: 0});
    const revision = ++this.revision, key = this.key;
    try {
      const remote = await App.api.get("/api/play-queue");
      if (!this.enabled || key !== this.key || revision !== this.revision) return;
      const signature = this.remote = JSON.stringify(QueueMemory.body(remote));
      // Une modification locale non envoyée prime. Sinon, une autre application peut avoir changé la file.
      if (this.state && (this.state.dirty || this.state.remote === signature)) {
        this.flush();
        return;
      }
      this.state = QueueMemory.valid(remote) ? Object.assign(remote, {dirty: false, remote: signature}) : null;
      this.apply(this.state || {songs: [], index: -1, position: 0});
      this.write();
    } catch (error) {
      if (generation !== this.generation) return;
      this.retryRestore = true;                      // aucune copie locale : relire au retour du réseau
    }
    if (this.state && this.state.dirty) this.flush();
  }

  record() {
    if (!this.enabled || this.restoring || !this.player.current) return;
    const next = {songs: this.player.queue.slice(), index: this.player.index, position: this.player.position};
    if (this.state && JSON.stringify([next.songs, next.index, next.position]) ===
        JSON.stringify([this.state.songs, this.state.index, this.state.position])) return;
    this.revision++;
    this.state = Object.assign(next, {dirty: true, remote: this.state ? this.state.remote : this.remote});
    this.write();                                      // synchrone : un rafraîchissement immédiat conserve l'ajout
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.flush(), 600);
  }

  async flush(options = {}) {
    clearTimeout(this.timer);
    if (!this.enabled || this.restoring || !this.state || !this.state.dirty) return;
    if (this.saving) {
      await this.saving;
      if (this.enabled && this.state && this.state.dirty) return this.flush(options);
      return;
    }
    const body = QueueMemory.body(this.state), signature = JSON.stringify(body), generation = this.generation;
    if (!body.ids.length || signature === this.state.remote) {
      this.state.dirty = false;
      this.write();
      return;
    }
    // Sérialiser évite qu'une sauvegarde lente écrase un ordre plus récent. Échec : nouvel essai au prochain point.
    // keepalive survit au départ de la page ; au-delà de sa limite navigateur, la copie locale assure le relais.
    if (options.keepalive && new Blob([JSON.stringify(body)]).size > 60000) options = {};
    this.saving = App.api.post("/api/play-queue/save", body, options).then(() => {
      if (!this.enabled || generation !== this.generation || !this.state) return;
      this.state.remote = signature;
      this.state.dirty = JSON.stringify(QueueMemory.body(this.state)) !== signature;
      this.write();
    }).catch(() => {}).finally(() => { this.saving = null; });
    await this.saving;
  }

  suspend() {
    this.record();
    this.enabled = false;
    this.revision++;
    clearTimeout(this.timer);
  }
}
