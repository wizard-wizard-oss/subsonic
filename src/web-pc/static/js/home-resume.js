"use strict";
/* Le point de reprise suit le lecteur existant, sans lancer de lecture ni modifier sa file. */
class HomeResume {
  constructor(route) {
    const el = App.el;
    this.route = route;
    this.alive = true;
    this.owner = App.user.id;
    this.image = App.cover("", 148);
    this.name = el("strong.personal-resume-song");
    this.artist = el("p.muted");
    this.title = el("h1", {text: App.t("home.resume")});
    this.button = App.setIcon(el("button.primary", {type: "button", onclick: () => App.player.toggle()}), "play", 16);
    this.root = el("section.personal-resume", {hidden: true}, this.image,
      el("div.personal-resume-details", {}, this.title, this.name, this.artist, this.button));
    this.off = App.bus.on("player", () => this.refresh());
    this.queueOff = App.bus.on("queue", () => this.refresh());
    Promise.resolve(App.music.queueMemory.ready).then(() => this.refresh());
  }

  refresh() {
    if (!this.alive || this.route.stale || !App.user || App.user.id !== this.owner) return;
    const player = App.player, song = player.current;
    this.root.hidden = !song;
    if (!song) return;
    if (this.coverId !== song.coverId) {
      this.coverId = song.coverId;
      if (song.coverId) this.image.src = App.coverUrl(song.coverId, 300);
      else this.image.removeAttribute("src");
    }
    this.image.alt = song.album || song.title;
    this.name.textContent = song.title;
    this.artist.textContent = [song.artist, song.album].filter(Boolean).join(" · ");
    this.title.textContent = App.t(player.playing ? "home.now_playing" : "home.resume");
    const position = Math.floor(player.position || 0), key = [player.playing, position].join(":");
    if (key === this.buttonKey) return;
    this.buttonKey = key;
    const text = player.playing ? App.t("player.pause") : App.t("home.continue", {position: App.duration(position)});
    App.setIcon(this.button, player.playing ? "pause" : "play", 16, false, text);
    this.button.setAttribute("aria-label", text);
  }

  destroy() { this.alive = false; this.off(); this.queueOff(); }
}
