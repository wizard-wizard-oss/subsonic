"use strict";
/* Lecteur : file d'attente + moteur de lecture (engine.js : flux Subsonic relayé par le site, son Jamendo,
   lecteurs officiels YouTube et SoundCloud), et sa barre en bas de page. */

class Player {
  constructor(engine) {
    this.audio = engine;
    this.queue = [];
    this.index = -1;
    this.resumePosition = null;
    this.audio.volume = App.local.get("volume", 0.8);
    this.audio.addEventListener("ended", () => this.next());
    this.audio.addEventListener("error", () => {
      if (!this.current) return;
      if (this.audio.isYouTube) this.videoRefused(this.current);
      else if (this.audio.isSoundCloud) this.soundRefused(this.current);
      else App.toast(App.t("player.error") + " : " + this.current.title, "error");
    });
    this.audio.addEventListener("play", () => this.reportVideoPlayed());
    this.audio.addEventListener("timeupdate", () => this.countListen());
    for (const kind of ["play", "pause", "timeupdate", "durationchange", "volumechange"]) {
      this.audio.addEventListener(kind, () => App.bus.emit("player", this));
    }
  }

  get current() { return this.queue[this.index] || null; }
  get playing() { return !this.audio.paused && !!this.audio.src; }
  get position() { return this.resumePosition === null ? this.audio.currentTime : this.resumePosition; }

  /** Retrouver la liste sans charger de flux, lancer de lecture ou compter une écoute. */
  restoreQueue(songs, index, position) {
    this.audio.stop();
    this.queue = songs.slice();
    this.index = songs.length ? index : -1;
    this.resumePosition = position;
    this.history = [];
    this.listen = null;
    this.reported = null;
    if (this.current) this.updateMediaSession(this.current);
    else if ("mediaSession" in navigator) navigator.mediaSession.metadata = null;
    App.bus.emit("queue", this);
    App.bus.emit("player", this);
  }

  playList(songs, start, shuffle) {
    if (!songs.length) return;
    this.history = [];                                       // nouvelle file : rien à annuler
    this.queue = shuffle ? Player.shuffled(songs) : songs.slice();
    this.load(shuffle ? 0 : start || 0);
  }

  add(songs) {
    this.queue.push(...songs);
    if (this.index < 0) this.load(0);
    App.bus.emit("queue", this);
  }

  playNext(songs) {
    if (this.index < 0) return this.add(songs);
    this.remember();
    this.queue.splice(this.index + 1, 0, ...songs);
    App.bus.emit("queue", this);
  }

  load(index, position = 0) {
    if (index < 0 || index >= this.queue.length) return;
    if (!this.queue[index].ext && !App.can("stream")) {          // droit Subsonic « écouter »
      App.toast(App.t("auth.missing_right"), "error");
      return;
    }
    this.index = index;
    this.resumePosition = null;
    this.reported = null;
    const song = this.current;
    this.startListen(song);
    const started = song.ext === "youtube" ? this.audio.playYouTube(song.youtubeId, position)
      : song.ext === "soundcloud" ? this.audio.playSoundCloud(song.soundcloudUrl, position)
      : this.audio.playUrl(song.ext === "jamendo" ? song.streamUrl : "/api/stream?" + new URLSearchParams({id: song.id}), position);
    if (started && started.catch) started.catch(() => { /* lecture refusée par le navigateur : bouton lecture */ });
    this.updateMediaSession(song);
    App.bus.emit("queue", this);
    App.bus.emit("player", this);
  }

  /** Écoute suivie par Subsonic (et Last.fm si la personne l'a relié) : « en cours » au démarrage, puis « écoutée » après
      la moitié du titre ou 4 minutes réellement écoutées (un saut en avant ne compte pas). Titres de Subsonic seulement. */
  startListen(song) {
    this.listen = null;
    if (song.ext || !App.can("scrobble")) return;
    this.listen = {song, heard: 0, last: 0, counted: false};
    App.api.post("/api/scrobble", {id: song.id, submission: false})
      .then(() => App.bus.emit("listening")).catch(() => { /* sans importance */ });
  }

  countListen() {
    const listen = this.listen;
    if (!listen || listen.counted) return;
    const time = this.audio.currentTime, step = time - listen.last;
    listen.last = time;
    if (step > 0 && step < 2) listen.heard += step;            // du temps écouté, pas un saut dans le titre
    const length = this.audio.duration;
    if (listen.heard < 240 && !(isFinite(length) && length >= 30 && listen.heard >= length / 2)) return;
    listen.counted = true;
    App.api.post("/api/scrobble", {id: listen.song.id, submission: true}).catch(() => { /* sans importance */ });
  }

  /** Une vidéo YouTube a vraiment démarré : le site s'en souvient (elle passera en tête des résultats). */
  reportVideoPlayed() {
    const song = this.current;
    if (!song || song.ext !== "youtube" || this.reported === song) return;
    this.reported = song;
    App.api.post("/api/ext/played", {id: song.youtubeId}).catch(() => { /* sans importance */ });
  }

  /** Vidéo refusée par le lecteur intégré : une autre version du même titre si le serveur en trouve une sûre,
      sinon on propose de l'ouvrir sur youtube.com et on passe au titre suivant. Une seule autre version par titre :
      si elle est refusée aussi, on n'en cherche pas une troisième (sinon les refus s'enchaînent sans fin). */
  async videoRefused(song) {
    let other = null;
    if ((this.audio.error || {}).code !== "youtube-unreachable" && !song.replaces) {
      try {
        other = (await App.api.post("/api/ext/alternative", {id: song.youtubeId, title: song.title, artist: song.artist,
                                                             code: String((this.audio.error || {}).code || "")})).item;
      } catch (error) { /* rien de sûr : titre suivant */ }
    } else if (song.replaces) {                 // l'autre version refusée aussi : notée, sans en chercher une autre
      App.api.post("/api/ext/unplayable", {id: song.youtubeId, code: String((this.audio.error || {}).code || "")})
        .catch(() => { /* sans importance */ });
    }
    if (this.current !== song) return;
    if (other) {
      this.queue[this.index] = Object.assign({}, other, {coverId: other.imageUrl || "", replaces: song.youtubeId});
      App.toast(App.t("ext.other_version"));
      this.load(this.index);
      return;
    }
    App.toast(App.t("ext.refused") + " : " + song.title, "error", {label: App.t("ext.open_youtube"),
      run: () => window.open("https://www.youtube.com/watch?v=" + encodeURIComponent(song.youtubeId), "youtube",
                             "width=980,height=640")});
    this.next();
  }

  /** Titre refusé par le lecteur SoundCloud (privé, retiré, bloqué ici) : on propose sa page et on passe au suivant. */
  soundRefused(song) {
    App.toast(App.t("ext.refused_soundcloud") + " : " + song.title, "error", {label: App.t("ext.open_soundcloud"),
      run: () => window.open(song.pageUrl || "https://soundcloud.com", "soundcloud", "noopener")});
    this.next();
  }

  toggle() {
    if (!this.current) return;
    if (this.resumePosition !== null) this.load(this.index, this.resumePosition);
    else if (this.audio.paused) this.audio.play(); else this.audio.pause();
  }

  next() { if (this.index + 1 < this.queue.length) this.load(this.index + 1); }

  previous() {
    if (this.position > 4 || this.index === 0) this.seekTo(0);
    else this.load(this.index - 1);
  }

  get duration() {
    return isFinite(this.audio.duration) && this.audio.duration > 0 ? this.audio.duration : (this.current && this.current.duration) || 0;
  }

  seekTo(seconds) {
    if (!this.current || !this.duration) return;
    const position = Math.max(0, Math.min(this.duration, seconds));
    if (this.resumePosition !== null) this.resumePosition = position;
    else this.audio.currentTime = position;
    App.bus.emit("player", this);
    App.bus.emit("queue", this);
  }

  seekBy(seconds) { this.seekTo(this.position + seconds); }

  seekRatio(ratio) { this.seekTo(this.duration * ratio); }

  setVolume(value) {
    this.audio.volume = Math.max(0, Math.min(1, value));
    App.local.set("volume", this.audio.volume);
  }

  removeAt(index) {
    if (index === this.index || index < 0 || index >= this.queue.length) return;
    this.remember();
    this.queue.splice(index, 1);
    if (index < this.index) this.index--;
    App.bus.emit("queue", this);
  }

  clearUpcoming() {
    if (this.index + 1 >= this.queue.length) return;
    this.remember();
    this.queue = this.queue.slice(0, this.index + 1);
    App.bus.emit("queue", this);
  }

  /** Déplace un titre de la file (glisser-déposer) : il se retrouve à la place `to` ; la lecture continue. */
  move(from, to) {
    const last = this.queue.length - 1;
    if (from === to || from < 0 || from > last || to < 0 || to > last) return;
    this.remember();
    const [song] = this.queue.splice(from, 1);
    this.queue.splice(to, 0, song);
    if (from === this.index) this.index = to;
    else if (from < this.index && to >= this.index) this.index--;
    else if (from > this.index && to <= this.index) this.index++;
    App.bus.emit("queue", this);
  }

  /** « Annuler » : la file d'avant la dernière modification (retrait, vidage, déplacement). */
  remember() {
    this.history = (this.history || []).slice(-19);
    this.history.push({queue: this.queue.slice(), current: this.current});
  }

  get canUndo() { return !!(this.history && this.history.length); }

  undo() {
    if (!this.canUndo) return;
    const before = this.history.pop();
    const current = this.current;
    this.queue = before.queue;
    const kept = this.queue.indexOf(current);              // le titre en cours continue, où qu'il soit
    this.index = kept >= 0 ? kept : Math.min(this.index, this.queue.length - 1);
    App.bus.emit("queue", this);
  }

  updateMediaSession(song) {
    if (!("mediaSession" in navigator) || typeof MediaMetadata === "undefined") return;
    navigator.mediaSession.metadata = new MediaMetadata({
      title: song.title, artist: song.artist, album: song.album,
      artwork: song.coverId ? [{src: App.coverUrl(song.coverId, 300), sizes: "300x300"}] : []});
    navigator.mediaSession.setActionHandler("nexttrack", () => this.next());
    navigator.mediaSession.setActionHandler("previoustrack", () => this.previous());
  }

  static shuffled(list) {
    const copy = list.slice();
    for (let i = copy.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [copy[i], copy[j]] = [copy[j], copy[i]];
    }
    return copy;
  }
}

class PlayerBar {
  constructor(root, player) {
    const el = App.el;
    this.player = player;
    this.cover = App.cover("", 48);
    this.title = el("a.player-title", {href: "#/"});
    this.artist = el("div.player-artist");
    this.playButton = el("button.round.play", {onclick: () => player.toggle(), title: App.t("player.play")}, App.icon("play", 20));
    this.position = el("span.time", {}, "0:00");
    this.length = el("span.time", {}, "0:00");
    this.bar = el("div.progress-fill");
    this.progress = el("div.progress", {onclick: e => {
      const box = this.progress.getBoundingClientRect();
      player.seekRatio(Math.min(1, Math.max(0, (e.clientX - box.left) / (box.width || 1))));
    }}, this.bar);
    this.volume = el("input.volume", {type: "range", min: 0, max: 1, step: 0.01, value: player.audio.volume,
                                      title: App.t("player.volume"), oninput: e => player.setVolume(+e.target.value)});
    this.details = el("div.player-details");          // album, année, genre, format : visibles au survol
    this.hoverTimer = null;
    App.append(root, [
      el("div.player-now", {}, this.cover, el("div.player-text", {}, this.title, this.artist)),
      el("div.player-controls", {},
        el("div.player-buttons", {},
          el("button.round", {onclick: () => player.previous(), title: App.t("player.previous")}, App.icon("previous", 18)),
          this.playButton,
          el("button.round", {onclick: () => player.next(), title: App.t("player.next")}, App.icon("next", 18))),
        el("div.player-progress", {}, this.position, this.progress, this.length)),
      el("div.player-extra", {},
        el("button.icon-button.lyrics-toggle", {onclick: () => App.lyrics.toggle(), title: App.t("player.lyrics")}, App.icon("mic", 20)),
        el("button.icon-button.queue-toggle", {onclick: () => App.queuePanel.toggle(), title: App.t("player.queue")},
           App.icon("list", 20)),
        el("span.volume-icon", {}, App.icon("volume", 18)), this.volume),
      this.details,
    ]);
    // survol : la barre s'agrandit (détails du titre) ; si la souris reste, la file d'attente s'ouvre
    root.addEventListener("mouseenter", () => this.hover(true));
    root.addEventListener("mouseleave", () => this.hover(false));
    App.bus.on("queue-panel", open => { if (!open && !root.matches(":hover")) this.expand(false); });
    App.bus.on("player", () => this.refresh());
    App.bus.on("queue", () => this.refreshDetails());
    this.refresh();
  }

  hover(inside) {
    clearTimeout(this.hoverTimer);
    if (inside) {
      App.queuePanel.stay();
      this.hoverTimer = setTimeout(() => {
        this.expand(true);
        this.hoverTimer = setTimeout(() => { if (this.player.queue.length) App.queuePanel.open(); }, 700);
      }, 150);
    } else {
      App.queuePanel.leaveSoon();
      this.hoverTimer = setTimeout(() => { if (!App.queuePanel.isOpen) this.expand(false); }, 300);
    }
  }

  expand(on) {
    if (on) document.body.dataset.player = "open";
    else delete document.body.dataset.player;
  }

  /** « Album · 2017 · Avant-garde · FLAC 1 024 kbps · 3 / 10 » */
  refreshDetails() {
    const player = this.player, song = player.current;
    App.clear(this.details);
    if (!song) return;
    const parts = [song.year, song.genre, QueuePanel.format(song),
                   player.queue.length > 1 ? (player.index + 1) + " / " + player.queue.length : ""].filter(Boolean);
    App.append(this.details, [
      song.albumId ? App.el("a.details-album", {href: "#/album/" + encodeURIComponent(song.albumId), text: song.album || ""})
                   : (song.album ? App.el("span.details-album", {text: song.album}) : null),
      parts.map(part => App.el("span.details-part", {text: String(part)}))]);
  }

  refresh() {
    const player = this.player, song = player.current;
    if (this.shownPlaying !== player.playing) {
      this.shownPlaying = player.playing;
      App.setIcon(this.playButton, player.playing ? "pause" : "play", 20);
    }
    this.position.textContent = App.duration(player.position);
    this.length.textContent = App.duration(player.duration);
    const ratio = player.duration ? player.position / player.duration : 0;
    this.bar.style.width = (ratio * 100).toFixed(2) + "%";
    if (!song && this.shown) {
      this.shown = null;
      this.title.textContent = "";
      this.title.href = "#/";
      this.artist.textContent = "";
      const fresh = App.cover("", 48);
      this.cover.replaceWith(fresh);
      this.cover = fresh;
      this.refreshDetails();
      if (App.music) App.music.updateTitle(0);
    }
    if (song && this.shown !== song) {
      this.shown = song;
      this.title.textContent = song.title;
      this.title.href = song.albumId ? "#/album/" + encodeURIComponent(song.albumId) : "#/";
      this.artist.textContent = song.artist || "";
      const fresh = App.cover(song.coverId, 48);
      this.cover.replaceWith(fresh);
      this.cover = fresh;
      if (App.music) App.music.updateTitle(App.chatPanel ? App.chatPanel.unread : 0);
      this.refreshDetails();
    }
  }
}
