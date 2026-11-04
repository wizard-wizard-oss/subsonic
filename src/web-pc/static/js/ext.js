"use strict";
/* Musique d'ailleurs dans la recherche : vidéos YouTube déjà trouvées sur le site (sans quota) et Jamendo (musique
   libre) tout de suite ; nouvelle recherche YouTube seulement sur demande (bouton), même quand la bibliothèque
   Subsonic a trouvé quelque chose : ce n'est peut-être pas le bon titre. Son quota (~100 recherches par jour) est
   partagé par tout le site, d'où le clic. Les titres se lisent dans le lecteur habituel.
   Favoris d'ailleurs, propres à chacun : cœur de chaque titre, et section « D'ailleurs » de la page Favoris où l'on
   colle un lien (vidéo ou playlist YouTube, titre SoundCloud). */

const ExtMusic = {
  status: {jamendo: false, youtube: false},
  favorites: new Set(),            // identifiants (« yt-… », « sc-… », « jamendo-… ») des favoris de la personne
  favoritesLoaded: null,

  async load() {
    try { this.status = await App.api.get("/api/ext/status"); } catch (error) { /* sources indisponibles */ }
  },

  /** Favoris d'ailleurs de la personne (titres complets) ; les cœurs s'allument d'après eux. */
  async loadFavorites() {
    const items = (await App.api.get("/api/ext/favorites")).items;
    this.favorites = new Set(items.map(item => item.id));
    this.favoritesLoaded = Promise.resolve();
    return items.map(item => Object.assign({}, item, {coverId: item.imageUrl || ""}));
  },

  /** Avant d'afficher des cœurs : les favoris sont lus une fois (sans eux, les cœurs restent éteints). */
  favoritesReady() {
    if (!this.favoritesLoaded) this.favoritesLoaded = this.loadFavorites().catch(() => { this.favoritesLoaded = null; });
    return this.favoritesLoaded;
  },

  /** Section « Ailleurs » de la page de recherche (null si aucune source n'est réglée sur le serveur).
      foundInLibrary : Subsonic a déjà des titres ou des albums pour cette recherche (seul le texte du bouton change). */
  section(term, foundInLibrary) {
    if (!this.status.jamendo && !this.status.youtube) return null;
    const el = App.el;
    const box = el("section.ext", {}, el("div.section-head", {}, el("h2", {text: App.t("ext.title")})));
    if (this.status.youtube) this.fillKnown(box.appendChild(el("div.ext-part.youtube-known")), term);
    if (this.status.jamendo) this.fill(box.appendChild(el("div.ext-part.jamendo")), "jamendo", term);
    if (this.status.youtube) {
      const part = box.appendChild(el("div.ext-part.youtube"));
      part.appendChild(el("button.ext-youtube", {type: "button",
        text: App.t(foundInLibrary ? "ext.search_youtube_anyway" : "ext.search_youtube"),
        onclick: () => this.fill(part, "youtube", term)}));
    }
    return box;
  },

  /** Vidéos YouTube déjà trouvées par quelqu'un du site : rien n'est affiché s'il n'y en a pas. */
  async fillKnown(part, term) {
    let songs = [];
    try {
      songs = (await App.api.get("/api/ext/known", {q: term})).items
        .map(item => Object.assign({}, item, {coverId: item.imageUrl || ""}));
    } catch (error) { /* sans importance : le bouton de recherche YouTube reste là */ }
    await this.favoritesReady();
    if (songs.length) App.append(part, [App.el("h3", {text: App.t("ext.known")}), this.table(songs)]);
  },

  async fill(part, source, term) {
    const el = App.el;
    App.clear(part).appendChild(el("p.muted", {text: App.t("ext.searching")}));
    let songs;
    try {
      songs = (await App.api.get("/api/ext/search", {src: source, q: term})).items
        .map(item => Object.assign({}, item, {coverId: item.imageUrl || ""}));
    } catch (error) {
      App.clear(part).appendChild(el("p.muted", {text: App.errorText(error)}));
      return;
    }
    await this.favoritesReady();
    App.append(App.clear(part), [el("h3", {text: App.t("ext.sources." + source)}),
      songs.length ? this.table(songs) : el("p.muted", {text: App.t("search.nothing")})]);
  },

  /** Section « D'ailleurs » de la page Favoris : coller un lien, puis les favoris de la personne (derniers ajoutés
      d'abord). La liste se redessine après chaque lien ajouté. */
  favoritesSection(route) {
    const el = App.el;
    const box = el("section.ext.ext-favorites");
    const list = el("div.ext-favorites-list", {}, el("p.muted", {text: "…"}));
    const play = el("button.ext-play-all", {type: "button", hidden: true});
    App.setIcon(play, "play", 16, false, App.t("ext.favorites_play"));
    const show = async () => {
      let songs;
      try { songs = await this.loadFavorites(); } catch (error) {
        App.clear(list).appendChild(el("p.muted", {text: App.errorText(error)}));
        return;
      }
      if (route.stale) return;
      play.hidden = !songs.length;
      play.onclick = () => App.player.playList(songs, 0);
      App.clear(list).appendChild(songs.length ? this.table(songs)
                                               : el("p.muted", {text: App.t("ext.favorites_empty")}));
    };
    App.append(box, [el("div.section-head", {}, el("h2", {text: App.t("ext.favorites_title")}), play),
                     this.linkForm(show), el("p.muted.ext-link-help", {text: App.t("ext.link_help")}), list]);
    show();
    return box;
  },

  /** Champ « coller un lien » (vidéo ou playlist YouTube, titre SoundCloud) : les titres vont dans les favoris
      d'ailleurs de la personne. Page Favoris et page « Mon compte ». onAdded : après un ajout réussi. */
  linkForm(onAdded, action) {
    const el = App.el;
    const input = el("input.ext-link", {type: "text", inputMode: "url", placeholder: App.t("ext.link_placeholder"),
                                        required: true, "aria-label": App.t("ext.link_placeholder")});
    const button = el("button.primary", {type: "submit", text: App.t("ext.link_add")});
    return el("form.ext-link-form", {onsubmit: async event => {
      event.preventDefault();
      button.disabled = true;
      button.textContent = App.t("ext.link_adding");
      try {
        const result = await App.api.post("/api/ext/link", {link: input.value});
        App.toast(result.added ? App.plural("ext.link_added", result.added) : App.t("ext.link_added_zero"), "", action);
        if (result.skipped) App.toast(App.plural("ext.link_skipped", result.skipped), "error");
        input.value = "";
        if (onAdded) await onAdded();
      } catch (error) {
        App.toast(App.errorText(error), "error");
      }
      button.disabled = false;
      button.textContent = App.t("ext.link_add");
    }}, input, button);
  },

  heart(song) {
    const on = this.favorites.has(song.id);
    const button = App.el("button.heart" + (on ? ".on" : ""), {type: "button", title: App.t("ext.favorite"),
                                                             onclick: () => this.toggleFavorite(song, button)});
    return App.setIcon(button, "heart", 16, on);
  },

  async toggleFavorite(song, button) {
    const on = !this.favorites.has(song.id);
    try {
      await App.api.post("/api/ext/favorite", {item: song, on});
      if (on) this.favorites.add(song.id); else this.favorites.delete(song.id);
      button.classList.toggle("on", on);
      App.setIcon(button, "heart", 16, on);
    } catch (error) {
      App.toast(App.errorText(error), "error");
    }
  },

  /** Titres d'ailleurs : lecture (double-clic ou bouton), cœur (favoris d'ailleurs de la personne), ajout à la file ou
      à une playlist (bouton, ou glissé vers la barre de gauche). */
  table(songs) {
    const el = App.el;
    const playlistRight = App.can("playlist");
    return el("table.songs.ext-songs", {}, el("tbody", {}, songs.map((song, i) => {
      const payload = {extItems: [song], label: song.title};
      const row = el("tr.song", {dataset: {id: song.id}, ondblclick: () => App.player.playList(songs, i)},
        el("td.num", {}, el("button.row-play", {type: "button", title: App.t("album.play"),
                                                 onclick: () => App.player.playList(songs, i)}, App.icon("play", 14))),
        el("td.ext-cover", {}, App.cover(song.coverId, 40)),
        el("td.title", {}, el("span", {text: song.title}), el("span.muted", {text: song.artist ? " — " + song.artist : ""}),
           song.playedHere ? el("span.ext-played", {text: App.plural("ext.played_here", song.playedHere)}) : null),
        el("td.ext-source.muted", {text: App.t("ext.sources." + song.ext)}),
        el("td.ext-heart", {}, this.heart(song)),
        el("td.duration.muted", {text: song.duration ? App.duration(song.duration) : ""}),
        el("td.more", {},
           el("button.link-button.song-play-next", {type: "button", title: App.t("album.play_next"),
                                     onclick: () => { App.player.playNext([song]); App.toast("→ " + song.title); }},
              App.icon("next", 16)),
           el("button.link-button", {type: "button", title: App.t("album.queue"),
                                     onclick: () => { App.player.add([song]); App.toast("+ " + song.title); }},
              App.icon("plus", 16)),
           playlistRight ? el("button.link-button.song-playlist", {type: "button", title: App.t("playlist.add_to"),
                                                                   onclick: () => App.playlists.pick(payload)},
                              App.icon("list", 16)) : null));
      if (playlistRight) Dnd.source(row, payload);
      return row;
    })));
  },
};
