"use strict";
/* « Écouté en ce moment », en haut du panneau de droite (comme dans Subsonic) : ce que chacun écoute sur le serveur
   (getNowPlaying), soi-même compris. Le lecteur signale chaque titre démarré (player.js) ; liste relue toutes les 30 s. */

class ListeningPanel {
  constructor() {
    this.box = document.getElementById("listening");
    this.list = document.getElementById("listening-list");
    App.bus.on("listening", () => this.refresh());           // je viens de lancer un titre
    setInterval(() => { if (!document.hidden) this.refresh(); }, 30000);
    this.refresh();
  }

  async refresh() {
    let entries;
    try {
      entries = (await App.api.get("/api/now-playing")).entries;
    } catch (error) {
      return;                                                // on garde ce qui est affiché
    }
    this.render(entries);
  }

  render(entries) {
    const me = App.user.username;
    entries = entries.slice().sort((a, b) => (b.username === me) - (a.username === me) || a.minutesAgo - b.minutesAgo);
    this.box.hidden = !entries.length;
    App.clear(this.list);
    for (const entry of entries) this.list.appendChild(this.row(entry, entry.username === me));
  }

  row(entry, mine) {
    const el = App.el;
    const ago = entry.minutesAgo ? App.t("listening.ago", {minutes: entry.minutesAgo}) : App.t("listening.now");
    return el("a.listening-row" + (mine ? ".me" : ""), {href: entry.albumId ? "#/album/" + encodeURIComponent(entry.albumId) : "#/",
                                                         title: entry.title, dataset: {user: entry.username}},
      App.avatar(entry.username),
      el("span.listening-text", {},
        el("strong.listening-who", {text: mine ? App.t("listening.you") : entry.username}),
        el("span.listening-song", {text: entry.title + (entry.artist ? " — " + entry.artist : "")}),
        el("span.listening-ago", {text: ago})),
      entry.coverId ? App.cover(entry.coverId, 40, entry.album) : null);
  }
}
