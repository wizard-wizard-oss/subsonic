"use strict";
/* Carte de playlist : mosaïque commune, accès au détail et lecture avec le lecteur existant. */
class PlaylistCard {
  constructor(data) {
    this.root = App.el("article.playlist-card", {dataset: {id: data.id}});
    this.update(data);
    Dnd.target(this.root, () => App.can("playlist") && this.data.canAdd,
      payload => App.playlists.add(this.data, payload));
  }

  update(data) {
    this.data = data;
    const el = App.el, href = "#/playlist/" + encodeURIComponent(data.id);
    const art = el("div.playlist-card-art", {},
      el("a", {href, "aria-label": data.name}, PlaylistArtwork.render(data.coverIds)));
    if (App.can("stream") && data.songCount) {
      this.play = App.setIcon(el("button.playlist-card-play", {type: "button",
        "aria-label": App.t("playlist.play_named", {name: data.name}), onclick: () => this.start()}), "play", 20);
      art.appendChild(this.play);
    }
    const facts = [App.plural("album.tracks", data.songCount), App.duration(data.duration)].join(" · ");
    this.root.replaceChildren(art, el("a.playlist-card-name", {href, text: data.name}),
      el("p.muted.playlist-card-facts", {text: facts}),
      el("p.muted.playlist-card-owner", {text: App.t("playlist.by", {name: data.owner})}));
    if (data.community) this.root.appendChild(el("span.chip.community-chip", {
      text: App.t("playlist.community"), title: App.t("playlist.community_help")}));
  }

  async start() {
    if (this.play.disabled) return;
    const button = this.play;
    button.disabled = true;
    try {
      const data = await App.api.get("/api/playlist", {id: this.data.id});
      if (!this.root.isConnected) return;
      const songs = data.songs.map(song => song.ext ? {...song, coverId: song.imageUrl || ""} : song);
      App.player.playList(songs, 0);
    } catch (error) { if (this.root.isConnected) App.toast(App.errorText(error), "error"); }
    finally { button.disabled = false; }
  }
}
