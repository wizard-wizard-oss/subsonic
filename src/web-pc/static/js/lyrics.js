"use strict";
/* Paroles du titre en cours, à droite à la place du salon. Paroles synchronisées : la ligne chantée est en
   surbrillance et reste au milieu. Paroles simples : défilement estimé d'après l'avancement du titre, mis en pause
   quelques secondes dès qu'on fait défiler soi-même. Au-dessus, un cadre d'anecdotes (sortie de l'album, la chanson,
   l'artiste) qui change toutes les 14 s, comme sur le Pi. */

const FACT_SECONDS = 14;

/** « [01:02.50]texte » -> [{time: 62.5, text}] (lignes sans horodatage ignorées). */
function parseLrc(text) {
  const lines = [];
  for (const line of (text || "").split("\n")) {
    const match = line.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/);
    if (match) lines.push({time: +match[1] * 60 + parseFloat(match[2]), text: match[3].trim()});
  }
  return lines;
}

class LyricsPanel {
  constructor(player) {
    const el = App.el;
    this.player = player;
    this.root = document.getElementById("lyrics-panel");
    this.body = el("div.lyrics-body");
    this.title = el("div.lyrics-song");
    this.factPhoto = el("img.fact-photo", {alt: "", hidden: true, referrerPolicy: "no-referrer"});
    this.factKind = el("strong.fact-kind");
    this.factText = el("p.fact-text");
    this.factBox = el("button.facts-box", {type: "button", hidden: true, title: App.t("lyrics.next_fact"),
                                           "aria-label": App.t("lyrics.facts"), onclick: () => this.showFact()},
                      this.factPhoto, el("span.fact-words", {}, this.factKind, this.factText));
    App.append(this.root, [
      el("header.lyrics-head", {}, el("h2", {text: App.t("lyrics.title")}),
         el("button.icon-button", {type: "button", title: App.t("lyrics.close"), onclick: () => this.close()},
            App.icon("close", 18))),
      this.title, this.factBox, this.body]);
    this.facts = [];
    this.factIndex = 0;
    this.factTimer = null;
    this.songId = null;
    this.lines = [];
    this.lineNodes = [];
    this.plainNodes = [];
    this.current = -1;
    this.userScrolledAt = 0;
    for (const kind of ["wheel", "pointerdown", "keydown"]) {
      this.body.addEventListener(kind, () => { this.userScrolledAt = Date.now(); });
    }
    App.bus.on("player", () => this.follow());
  }

  isOpen() { return document.body.dataset.lyrics === "open"; }

  toggle() { if (this.isOpen()) this.close(); else this.open(); }

  open() {
    document.body.dataset.lyrics = "open";
    this.follow();
  }

  /** Fermé : plus d'anecdotes qui tournent ; à la réouverture, paroles et anecdotes sont rechargées (gardées par le serveur). */
  close() {
    delete document.body.dataset.lyrics;
    this.songId = null;
    this.clearFacts();
  }

  /** Appelé à chaque changement du lecteur : nouveau titre -> nouvelles paroles ; sinon, suivre le rythme. */
  follow() {
    if (!this.isOpen()) return;
    const song = this.player.current;
    if (!song) { this.message(App.t("lyrics.nothing_playing")); this.songId = null; this.clearFacts(); return; }
    if (song.id !== this.songId) { this.load(song); return; }
    this.sync();
  }

  message(text) {
    App.clear(this.body).appendChild(App.el("p.lyrics-message", {text}));
  }

  async load(song) {
    this.songId = song.id;
    this.lines = []; this.lineNodes = []; this.plainNodes = []; this.current = -1;
    this.title.textContent = song.title + (song.artist ? " — " + song.artist : "");
    this.message(App.t("lyrics.searching"));
    this.loadFacts(song);
    let found = {};
    try {
      found = await App.api.get("/api/lyrics", {artist: song.artist || "", title: song.title || "",
                                                album: song.album || "", duration: song.duration || 0});
    } catch (error) { /* rien trouvé : message ci-dessous */ }
    if (this.songId !== song.id) return;               // le titre a changé pendant la recherche
    App.clear(this.body);
    this.lines = parseLrc(found.synced);
    if (this.lines.length) {
      this.lineNodes = this.lines.map(line => this.body.appendChild(App.el("p.lyric-line", {text: line.text || "♪"})));
    } else if (found.plain) {
      this.plainNodes = found.plain.split("\n").map(line => this.body.appendChild(App.el("p.lyric-plain", {text: line || " "})));
    } else {
      this.message(App.t("lyrics.none"));
      return;
    }
    this.body.appendChild(App.el("small.lyrics-source", {
      text: App.t("lyrics.source", {source: found.src}) + (this.lines.length ? "" : App.t("lyrics.not_synced"))}));
    this.sync();
  }

  sync() {
    const audio = this.player.audio;
    if (this.lines.length) {
      const now = audio.currentTime + 0.3;               // un léger temps d'avance : la ligne s'allume à temps
      let index = -1;
      for (let i = 0; i < this.lines.length && this.lines[i].time <= now; i++) index = i;
      if (index === this.current) return;
      if (this.lineNodes[this.current]) this.lineNodes[this.current].classList.remove("current");
      this.current = index;
      if (index >= 0) {
        this.lineNodes[index].classList.add("current");
        this.scrollTo(this.lineNodes[index], 2);
      }
    } else if (this.plainNodes.length && isFinite(audio.duration) && audio.duration > 0) {
      if (Date.now() - (this.plainScrolledAt || 0) < 1500) return;     // pas besoin de bouger plus souvent
      this.plainScrolledAt = Date.now();
      const progress = Math.min(1, Math.max(0, (audio.currentTime - 8) / Math.max(1, audio.duration - 30)));
      this.scrollTo(this.plainNodes[Math.min(this.plainNodes.length - 1, Math.floor(progress * this.plainNodes.length))], 3);
    }
  }

  /* ---------- anecdotes ---------- */
  async loadFacts(song) {
    this.clearFacts();
    if (!song.artist || !song.title) return;
    let found = {};
    try {
      found = await App.api.get("/api/facts", {artist: song.artist, title: song.title, album: song.album || "",
                                               artistId: song.artistId || ""});
    } catch (error) { return; }
    if (this.songId !== song.id || !this.isOpen()) return;      // le titre a changé ou le panneau est fermé
    this.facts = found.facts || [];
    if (!this.facts.length) return;
    this.factPhoto.hidden = !found.img;
    if (found.img) this.factPhoto.src = found.img;
    this.factBox.hidden = false;
    this.showFact();
  }

  /** Anecdote suivante (au clic, ou toutes les 14 s). */
  showFact() {
    if (!this.facts.length) return;
    const fact = this.facts[this.factIndex % this.facts.length];
    this.factIndex++;
    this.factKind.textContent = fact.k;
    this.factText.textContent = fact.t;
    clearTimeout(this.factTimer);
    this.factTimer = this.facts.length > 1 ? setTimeout(() => this.showFact(), FACT_SECONDS * 1000) : null;
  }

  clearFacts() {
    clearTimeout(this.factTimer);
    this.factTimer = null;
    this.facts = [];
    this.factIndex = 0;
    this.factBox.hidden = true;
    this.factPhoto.hidden = true;
  }

  /** Amène une ligne au milieu (ou au tiers), sauf si la personne fait défiler elle-même depuis peu. */
  scrollTo(node, fraction) {
    if (Date.now() - this.userScrolledAt < 8000 || !this.body.scrollTo) return;
    this.body.scrollTo({top: node.offsetTop - this.body.clientHeight / fraction + node.clientHeight / 2, behavior: "smooth"});
  }
}
