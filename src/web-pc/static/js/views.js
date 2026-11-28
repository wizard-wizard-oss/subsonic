"use strict";
/* Pages de la zone centrale : accueil, artiste, album (avec étoiles et commentaires), recherche, favoris.
   Chaque page : render(conteneur, route) ; destroy() éventuel pour se désabonner en partant. */

const Views = (() => {
  const el = App.el;

  function heading(text, extra) {
    return el("div.section-head", {}, el("h2", {text}), extra || null);
  }

  /** Grille de pochettes : style, étoiles et commentaires ; écoutes uniquement pour « Plus écoutés ». */
  function albumGrid(albums, options = {}) {
    const grid = el("div.album-grid" + (App.preferences.album_grid === "small" ? ".small" : ""));
    if (!albums.length) grid.appendChild(el("p.muted", {text: App.t("home.empty")}));
    for (const album of albums) {
      const meta = el("div.album-meta");
      if (album.rating && album.rating.average) meta.appendChild(new StarRating(album.rating, {readonly: true, small: true}).element);
      if (options.showPlays) {
        if (album.plays) meta.appendChild(el("span.play-count", {text: playCount(album.plays)}));
      } else if (album.genre) {
        meta.appendChild(el("span.album-genre", {text: album.genre, title: album.genre}));
      }
      if (album.comments) meta.appendChild(el("span.comment-count", {title: App.plural("album.comments_count", album.comments)},
                                              App.icon("chat", 12), " " + album.comments));
      const play = App.can("stream") ? App.setIcon(el("button.play-big.album-card-play", {
        type: "button", title: App.t("album.play_named", {name: album.name}),
        "aria-label": App.t("album.play_named", {name: album.name}),
        onclick: e => { e.stopPropagation(); playAlbum(album, e.currentTarget); }}), "play", 16) : null;
      const card = el("div.album-card", {},
        el("a.album-link", {href: "#/album/" + encodeURIComponent(album.id), title: album.name},
          App.cover(album.coverId, 180, album.name),
          el("strong.album-name", {text: album.name}),
          options.hideArtist ? null : el("span.album-artist", {text: album.artist || ""}),
          album.year ? el("span.album-year", {text: album.year}) : null,
          album.uploadedBy ? el("span.album-uploader.muted", {text: App.t("upload.by", {name: album.uploadedBy.username})}) : null,
          meta), play);
      if (App.can("playlist")) Dnd.source(card, {albumId: album.id, label: album.name});      // vers une playlist
      grid.appendChild(card);
    }
    return grid;
  }

  /** La flèche lit l'album sans navigation ; le lien de la carte ouvre toujours sa fiche. */
  async function playAlbum(album, button) {
    if (button.disabled) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    try {
      const data = await App.api.get("/api/album", {id: album.id});
      const songs = data.songs.map(song => Object.assign({}, song, {coverId: song.coverId || data.coverId}));
      if (!songs.length) { App.toast(App.t("mix.empty"), "error"); return; }
      App.player.playList(songs, 0);
    } catch (error) {
      App.toast(App.errorText(error), "error");
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  /** « Écouté 18 719 fois », comme dans Subsonic. */
  function playCount(plays) {
    return App.plural("album.plays", plays, {plays: plays.toLocaleString("fr-FR")});
  }

  function discussedList(albums) {
    const list = el("div.discussed");
    if (!albums.length) list.appendChild(el("p.muted", {text: App.t("home.empty")}));
    for (const album of albums) {
      list.appendChild(el("a.discussed-row", {href: "#/album/" + encodeURIComponent(album.id)},
        App.cover(album.coverId, 48), el("span", {}, el("strong", {text: album.title}), el("span.muted", {text: album.artist})),
        el("span.comment-count", {}, App.icon("chat", 12), " " + album.comments)));
    }
    return list;
  }

  /** Tableau des titres. Double-clic : lecture à partir de ce titre. Glisser un titre vers une playlist de la barre
      de gauche l'y ajoute. options : showAlbum, albumArtist,
      addedBy (colonne « ajouté par », playlist communautaire), canRemove(titre) + onRemove(titre, rang),
      onMove(de, vers) : changer l'ordre (poignée ⋮⋮ glissée dans le tableau, ou Alt + ↑ / ↓ sur une ligne).
      Une playlist peut mêler des titres d'ailleurs (song.ext) : leur cœur est celui des favoris d'ailleurs, leur source
      remplace l'album, et ils ne se téléchargent pas. Les colonnes suivent les réglages personnels
      de parcours, sans relire la liste ni modifier ses tags. */
  const songColumnClass = key => key === "artist" ? "song-artist" : key;

  function songTableHead(view) {
    const {options, metadata} = view;
    const header = key => el("th." + songColumnClass(key), {scope: "col", dataset: {songColumn: key}, text: SongColumns.label(key)});
    return el("thead", {}, el("tr", {},
      view.onMove ? el("th.grip", {scope: "col", "aria-label": App.t("playlist.move")}) : null,
      el("th.track-play", {scope: "col", "aria-label": App.t("album.play")}), header("track"),
      view.showAlbum ? el("th.thumb", {scope: "col"}) : null,
      el("th.title", {scope: "col", text: SongColumns.label("title")}), metadata.map(header),
      options.addedBy ? el("th.added-by", {scope: "col", text: SongColumns.label("added_by")}) : null,
      el("th.fav", {scope: "col", "aria-label": App.t("album.favorite")}),
      el("th.more", {scope: "col", "aria-label": SongColumns.label("actions")})));
  }

  /* Boutons d'une ligne : télécharger, radio, conseiller, jouer ensuite, file, playlist, retirer. */
  function songActions(song, i, view, payload) {
    const {options} = view, stop = e => e.stopPropagation();
    return el("td.more", {},
      App.can("download") && !song.ext ? el("a.link-button.song-download", {                // droit Subsonic « télécharger »
        href: "/api/download?" + new URLSearchParams({song: song.id}), download: "", title: App.t("album.download_song"),
        ondblclick: stop}, App.icon("download", 16)) : null,
      App.can("stream") && !song.ext ? el("button.link-button.song-radio", {
        type: "button", title: App.t("album.song_radio"), "aria-label": App.t("album.song_radio"),
        onclick: e => { stop(e); playSongRadio(song, e.currentTarget); }, ondblclick: stop}, App.icon("radio", 16)) : null,
      !song.ext ? ListenLaterUI.recommendButton({kind: "song", source: "subsonic", sourceId: song.id}, true) : null,
      el("button.link-button.song-play-next", {type: "button", title: App.t("album.play_next"),
        onclick: e => { stop(e); App.player.playNext([song]); App.toast("→ " + song.title); }}, App.icon("next", 16)),
      el("button.link-button", {type: "button", title: App.t("album.queue"),
        onclick: () => { App.player.add([song]); App.toast("+ " + song.title); }}, App.icon("plus", 16)),
      view.playlistRight ? el("button.link-button.song-playlist", {type: "button", title: App.t("playlist.add_to"),
        onclick: () => App.playlists.pick(payload)}, App.icon("list", 16)) : null,
      options.canRemove && options.canRemove(song) ? el("button.link-button.song-remove", {
        type: "button", title: App.t("playlist.remove"), onclick: () => options.onRemove(song, i)}, App.icon("close", 16)) : null);
  }

  function songRow(song, i, songs, view) {
    const heart = song.ext ? ExtMusic.heart(song)
      : heartButton(song, 16, e => { e.stopPropagation(); toggleFavorite("song", song, heart); });
    const payload = song.ext ? {extItems: [song], label: song.title} : {songIds: [song.id], label: song.title};
    const row = el("tr.song", {dataset: {id: song.id}, ondblclick: () => App.player.playList(songs, i)},
      view.onMove ? el("td.grip", {title: App.t("playlist.move"), text: "⋮⋮"}) : null,
      el("td.track-play", {}, el("button.row-play", {type: "button", title: App.t("album.play"),
        onclick: () => App.player.playList(songs, i), ondblclick: e => e.stopPropagation()}, App.icon("play", 14))),
      SongColumns.cell(song, "track", "td.num"),
      view.showAlbum ? el("td.thumb", {}, App.cover(song.coverId || song.imageUrl, 36)) : null,   // titres d'albums différents
      el("td.title", {}, el("span", {text: song.title})),
      view.metadata.map(key => SongColumns.cell(song, key, "td." + songColumnClass(key) + ".muted")),
      view.options.addedBy ? el("td.added-by.muted", {text: song.addedBy}) : null,
      el("td.fav", {}, heart), songActions(song, i, view, payload));
    if (view.playlistRight) Dnd.source(row, payload);
    if (view.onMove) movable(row, i, songs.length, view.onMove);
    return row;
  }

  function songTable(songs, options) {
    options = options || {};
    const view = {options, showAlbum: options.showAlbum, onMove: options.onMove, playlistRight: App.can("playlist"),
                  metadata: App.songColumns.filter(key => key !== "track")};
    const body = el("tbody");
    const discs = new Set(songs.map(s => s.disc).filter(Boolean)).size > 1 && options.albumArtist;
    songs.forEach((song, i) => {
      if (discs && song.disc !== (songs[i - 1] || {}).disc) {
        body.appendChild(el("tr.disc-row", {}, el("td", {text: App.t("album.disc", {number: song.disc || "?"})})));
      }
      body.appendChild(songRow(song, i, songs, view));
    });
    const highlight = () => body.querySelectorAll("tr.song").forEach(row => {
      row.classList.toggle("playing", !!App.player.current && row.dataset.id === App.player.current.id);
    });
    highlight();
    const offQueue = App.bus.on("queue", highlight);
    const table = el("table.songs", {}, songTableHead(view), body);
    const showColumns = () => SongColumns.apply(table, "browse");
    showColumns();
    const offPreferences = App.bus.on("preferences", showColumns);
    table.destroy = () => { offQueue(); offPreferences(); };
    return table;
  }

  /** Le serveur choisit les titres proches ; une erreur laisse la file et la lecture actuelles en place. */
  async function playSongRadio(song, button) {
    if (button.disabled) return;
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    App.toast(App.t("mix.building"));
    try {
      const {songs} = await App.api.get("/api/radio/song", {id: song.id});
      App.player.playList(songs, 0);
      App.toast(App.plural("album.tracks", songs.length));
    } catch (error) {
      App.toast(App.errorText(error), "error");
    } finally {
      button.disabled = false;
      button.removeAttribute("aria-busy");
    }
  }

  /** Ligne déplaçable dans son tableau : glissée (dépôt au-dessus ou au-dessous de la ligne visée, selon la moitié
      où est la souris) ou Alt + ↑ / ↓. Glissée sur une playlist de la barre de gauche, elle y est ajoutée comme avant. */
  function movable(row, i, count, onMove) {
    const body = () => row.parentNode;
    const clear = () => body() && body().querySelectorAll(".dragging, .drop-before, .drop-after")
      .forEach(r => r.classList.remove("dragging", "drop-before", "drop-after"));
    const after = event => { const box = row.getBoundingClientRect(); return event.clientY > box.top + box.height / 2; };
    const from = () => body() ? body().dataset.dragFrom : undefined;
    row.draggable = true;
    row.tabIndex = 0;
    row.addEventListener("dragstart", () => { body().dataset.dragFrom = i; row.classList.add("dragging"); });
    row.addEventListener("dragover", event => {
      if (from() === undefined) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      row.classList.toggle("drop-after", after(event));
      row.classList.toggle("drop-before", !after(event));
    });
    row.addEventListener("dragleave", () => row.classList.remove("drop-before", "drop-after"));
    row.addEventListener("drop", event => {
      if (from() === undefined) return;
      event.preventDefault();
      const start = Number(from());
      delete body().dataset.dragFrom;
      clear();
      let to = after(event) ? i + 1 : i;
      if (start < to) to--;                                    // la ligne déplacée libère sa place
      if (start !== to) onMove(start, to);
    });
    row.addEventListener("dragend", () => { if (body()) delete body().dataset.dragFrom; clear(); });
    row.addEventListener("keydown", event => {
      if (!event.altKey || (event.key !== "ArrowUp" && event.key !== "ArrowDown")) return;
      event.preventDefault();
      const to = i + (event.key === "ArrowUp" ? -1 : 1);
      if (to >= 0 && to < count) onMove(i, to);
    });
  }

  function heartButton(item, size, onclick) {
    const button = el("button.heart" + (size > 20 ? ".big" : "") + (item.starred ? ".on" : ""),
                      {type: "button", title: App.t("album.favorite"), onclick});
    return App.setIcon(button, "heart", size, !!item.starred);
  }

  async function toggleFavorite(kind, item, button) {
    const on = !item.starred;
    try {
      await App.api.post("/api/favorite", {kind, id: item.id, on});
      item.starred = on;
      button.classList.toggle("on", on);
      App.setIcon(button, "heart", button.classList.contains("big") ? 24 : 16, on);
    } catch (error) {
      App.toast(App.errorText(error), "error");
    }
  }

  function loading(main) {
    App.clear(main).appendChild(el("div.loading", {text: "…"}));
  }

  function failed(main, error) {
    App.clear(main).appendChild(el("p.page-error", {text: App.errorText(error)}));
  }

  /* ---------- accueil ---------- */
  const home = {
    destroy() { if (typeof DesktopHome !== "undefined") DesktopHome.destroy(); },
    async render(main, route) {
      if (App.layout === "desktop") return DesktopHome.render(main, route);
      loading(main);
      try {
        const data = await App.api.get("/api/home");
        if (route.stale) return;           // on a changé de page entre-temps
        App.clear(main);
        App.append(main, [
          LibraryStatistics.render(data.statistics),
          el("section", {}, heading(App.t("home.newest")), albumGrid(data.newest)),
          el("section.most-played", {}, heading(App.t("home.most_played")), albumGrid(data.mostPlayed, {showPlays: true})),
          el("div.home-columns", {},
            el("section", {}, heading(App.t("home.top_rated")), albumGrid(data.topRated)),
            el("section", {}, heading(App.t("home.discussed")), discussedList(data.discussed)))]);
      } catch (error) { failed(main, error); }
    },
  };

  /* ---------- artiste ---------- */
  const artist = {
    async render(main, route) {
      loading(main);
      try {
        const data = await App.api.get("/api/artist", {id: route.id});
        if (route.stale) return;           // on a changé de page entre-temps
        route.artistId = data.id;                    // dossier de l'artiste : la barre de gauche le surligne
        App.bus.emit("route", route);
        App.clear(main);
        const heart = heartButton(data, 24, () => toggleFavorite("folder", data, heart));
        const profile = new ArtistProfile(data, route, heart);
        this.discogs = new ArtistDiscography(data, route, () => profile.loadImage());
        const popular = el("section.popular"), similar = el("section.similar"),
              press = el("section.press");
        const albums = PageSections.section("artist-albums");
        App.append(albums, [heading(App.t("artist.albums")), albumGrid(data.albums, {hideArtist: true})]);
        // radio, mix et artistes proches passent par l'artiste ID3 (tags) : absents s'il n'a aucun titre
        const actions = el("div.artist-actions", {}, data.id3Id ? [
          App.setIcon(el("button.primary.artist-radio", {type: "button", onclick: () => this.radio(data)}),
                      "play", 16, false, App.t("artist.radio")),
          App.setIcon(el("a.button.artist-mix", {href: "#/mix/" + encodeURIComponent(data.id3Id)}),
                      "shuffle", 16, false, App.t("artist.mix_short"))] : null,
          App.setIcon(PageSections.link(App.t("artist.discogs_short"), this.discogs.root,
            () => { if (!this.discogs.identity) this.discogs.open(); }, ".button.artist-discogs-shortcut"),
            "discogs", 16, false, App.t("artist.discogs_short")));
        App.append(actions, [ListenLaterUI.actions({kind: "artist", source: "subsonic", sourceId: data.id})]);
        App.append(main, [
          profile.root,
          actions,
          PageSections.nav([{text: App.t("artist.albums"), section: albums},
            {text: App.t("artist.discogs_short"), section: this.discogs.root,
              open: () => { if (!this.discogs.identity) this.discogs.open(); }, className: ".discogs-section-link"},
            {text: App.t("discovery.members_and_groups"), section: this.discogs.relations}]),
          popular,
          albums,
          this.discogs.root,
          this.discogs.relations,
          AlbumExploration.artistPanel(data.name, route),
          similar,
          press]);
        profile.load();
        this.loadPopular(popular, data.name, route);
        News.pressSection(press, data.name, route);                 // articles des webzines suivis qui le citent
        if (data.id3Id) this.loadSimilar(similar, data.id3Id, route);
      } catch (error) { failed(main, error); }
    },
    /** Titres populaires (Last.fm, par Subsonic) : chargés après la page ; 5, puis 10 avec « Afficher plus ». */
    async loadPopular(section, name, route) {
      let songs;
      try { songs = (await App.api.get("/api/artist/top", {name})).songs; } catch (error) { return; }
      if (route.stale || !songs.length) return;
      const show = count => {
        if (this.table && this.table.destroy) this.table.destroy();
        this.table = songTable(songs.slice(0, count), {showAlbum: true});
        const more = songs.length > count
          ? el("button.link-button.more-songs", {type: "button", text: App.t("artist.more_popular"), onclick: () => show(10)})
          : null;
        App.append(App.clear(section), [heading(App.t("artist.popular")), this.table, more]);
      };
      show(5);
    },
    /** Artistes proches présents dans la bibliothèque (Last.fm, par Subsonic) : rien sans Last.fm. */
    async loadSimilar(section, id, route) {
      let artists;
      try { artists = (await App.api.get("/api/artist/similar", {id})).artists; } catch (error) { return; }
      if (route.stale || !artists.length) return;
      App.append(section, [heading(App.t("artist.similar")), el("div.chips.big", {}, artists.map(a =>
        el("a.chip", {href: "#/artist/" + encodeURIComponent(a.id)}, a.name,
           a.albumCount ? el("span.chip-count", {text: " " + a.albumCount}) : null)))]);
    },
    /** Radio de l'artiste : ses titres, puis ceux des artistes proches (calculée par le serveur). */
    async radio(data) {
      App.toast(App.t("mix.building"));
      try {
        App.player.playList((await App.api.get("/api/radio/artist", {id: data.id3Id, name: data.name})).songs, 0);
      } catch (error) { App.toast(App.errorText(error), "error"); }
    },
    destroy() {
      if (this.table && this.table.destroy) this.table.destroy();
      if (this.discogs) this.discogs.destroy();
      this.table = this.discogs = null;
    },
  };

  /** Couleur moyenne de la pochette, posée en `--tint` sur l'en-tête (dégradé du fond). Sans effet si le navigateur
      ne sait pas lire l'image (pas de canvas, image d'un autre site). */
  function tintFromCover(img) {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 8;
      const context = canvas.getContext("2d");
      context.drawImage(img, 0, 0, 8, 8);
      const pixels = context.getImageData(0, 0, 8, 8).data;
      const sum = [0, 0, 0];
      for (let i = 0; i < pixels.length; i += 4) for (let c = 0; c < 3; c++) sum[c] += pixels[i + c];
      const count = pixels.length / 4;
      img.closest(".album-head").style.setProperty("--tint", "rgb(" + sum.map(v => Math.round(v / count)).join(",") + ")");
    } catch (error) { /* pas de teinte */ }
  }

  /** Barre sous l'en-tête d'un album : gros bouton lecture, aléatoire, cœur, téléchargement, puis menu « ⋯ ». */
  function albumActions(data, songs, heart) {
    const menu = el("div.album-menu", {hidden: true, onclick: () => { menu.hidden = true; }},
      App.setIcon(el("button.link-button", {type: "button", onclick: () => { App.player.playNext(songs); App.toast("→ " + data.name); }}),
                  "next", 16, false, App.t("album.play_album_next")),
      App.setIcon(el("button.link-button", {type: "button", onclick: () => App.player.add(songs)}),
                  "plus", 16, false, App.t("album.queue")),
      App.setIcon(el("button.link-button", {type: "button", onclick: () => App.chatPanel.share({
        kind: "album", id: data.id, title: data.name, artist: data.artist, coverId: data.coverId})}),
                  "chat", 16, false, App.t("album.share")));
    const toggle = App.setIcon(el("button.icon-button", {type: "button", title: App.t("album.more"),
      onclick: () => { menu.hidden = !menu.hidden; }}), "more", 20);
    const iconButton = (name, title, onclick) => App.setIcon(el("button.icon-button", {type: "button", title, onclick}), name, 20);
    return el("div.album-actions", {},
      App.setIcon(el("button.play-big", {type: "button", title: App.t("album.play"),
                                         onclick: () => App.player.playList(songs, 0)}), "play", 26),
      iconButton("shuffle", App.t("album.shuffle"), () => App.player.playList(songs, 0, true)),
      heart,
      ListenLaterUI.actions({kind: "album", source: "subsonic", sourceId: data.folderId || data.id}),
      App.can("download") ? App.setIcon(el("a.icon-button.download", {title: App.t("album.download"), href: "/api/download?" +
        new URLSearchParams({album: data.id}), download: ""}), "download", 20) : null,
      App.can("coverArt") ? App.setIcon(el("button.album-tags-edit", {type: "button", text: App.t("tags.edit_ui"),
        onclick: () => AlbumTagsEditor.open({id: data.folderId || data.id, name: data.name, artist: data.artist}, () => {
          App.bus.emit("library-changed", {albumId: data.folderId || data.id});
          if (App.music.route && App.music.route.view === "album") App.music.navigate();
        })}), "edit", 16, false, App.t("tags.edit_ui")) : null,
      el("div.album-more", {}, toggle, menu));
  }

  /** Pochette de la page album avec le crayon (droit « upload ») : ouvre la recherche de pochettes ; une fois la nouvelle
      écrite, l'image est rechargée (et la teinte de l'en-tête refaite). */
  function coverWithPencil(cover, data) {
    const reload = () => {
      cover.addEventListener("load", () => tintFromCover(cover), {once: true});
      cover.src = App.coverUrl(data.coverId || data.id, 440) + "&v=" + Date.now();
    };
    return el("div.cover-edit", {}, cover,
      App.setIcon(el("button.cover-pencil", {type: "button", title: App.t("cover.edit"),
        onclick: () => CoverEditor.open({id: data.id, name: data.name, artist: data.artist}, reload)}), "edit", 18));
  }

  /* ---------- album ---------- */
  const album = {
    async render(main, route) {
      loading(main);
      let data;
      try {
        data = await App.api.get("/api/album", {id: route.id});
        if (route.stale) return;           // on a changé de page entre-temps
      } catch (error) { if (!route.stale) failed(main, error); return; }
      route.artistId = data.artistId;              // la barre de gauche surligne l'artiste
      App.bus.emit("route", route);
      App.clear(main);
      const songs = data.songs.map(s => Object.assign({}, s, {coverId: s.coverId || data.coverId}));
      const stars = new StarRating(data.rating, {readonly: !App.can("comment")});       // droit Subsonic
      const heart = heartButton(data, 24, () => toggleFavorite("album", data, heart));
      const facts = [data.year, data.genre, App.plural("album.tracks", songs.length), App.duration(data.duration),
                     data.plays ? playCount(data.plays) : null]
        .filter(Boolean).join(" · ");
      const cover = App.cover(data.coverId, 220, data.name);
      cover.addEventListener("load", () => tintFromCover(cover), {once: true});
      const coverBox = App.can("upload") ? coverWithPencil(cover, data) : cover;
      this.table = songTable(songs, {albumArtist: data.artist});
      const credits = new DiscogsCredits.Album(data.folderId || data.id, route);
      const tracks = PageSections.section("album-tracks");
      tracks.appendChild(this.table);
      this.thread = new ChatThread("album:" + data.id, {mode: "comments", isVisible: () => !document.hidden,
                                                         readOnly: !App.can("comment")});
      App.append(main, [
        el("header.album-head", {},
          coverBox,
          el("div.album-info", {},
            el("span.kicker", {text: "Album"}),
            el("h1", {text: data.name}),
            el("a.album-artist-link", {href: "#/artist/" + encodeURIComponent(data.artistId), text: data.artist}),
            el("p.muted", {text: facts}),
            data.uploadedBy ? el("p.album-uploader.muted", {text: App.t("upload.by", {name: data.uploadedBy.username}),
              title: App.fullDate(data.uploadedBy.uploadedAt)}) : null,
            el("div.album-rating", {}, el("span.label", {text: App.t("album.your_rating")}), stars.element))),
        albumActions(data, songs, heart),
        PageSections.nav([{text: App.t("search.songs"), section: tracks},
          {text: App.t("discovery.credits_short"), section: credits.root, open: () => credits.open(), className: ".discogs-section-link"},
          {text: App.t("explore.labels"), section: credits.labels, open: () => credits.open()}]),
        tracks,
        credits.root,
        AlbumExploration.panel(data.folderId || data.id, route),
        el("section.comments", {}, heading(App.t("album.comments")), this.thread.element)]);
      this.thread.load();
    },
    destroy() {
      if (this.thread) this.thread.destroy();
      if (this.table && this.table.destroy) this.table.destroy();
      this.thread = this.table = null;
    },
  };

  /* ---------- recherche ---------- */
  const search = {
    async render(main, route) {
      loading(main);
      try {
        const data = await App.api.get("/api/search", {q: route.id});
        if (route.stale) return;           // on a changé de page entre-temps
        App.clear(main);
        if (!data.artists.length && !data.albums.length && !data.songs.length) {
          main.appendChild(el("p.muted", {text: App.t("search.nothing")}));
        }
        if (data.artists.length) {
          App.append(main, [heading(App.t("search.artists")), el("div.chips", {}, data.artists.map(a =>
            el("a.chip", {href: "#/artist/" + encodeURIComponent(a.id), text: a.name})))]);
        }
        if (data.albums.length) App.append(main, [heading(App.t("search.albums")), albumGrid(data.albums)]);
        if (data.songs.length) {
          this.table = songTable(data.songs, {showAlbum: true});
          App.append(main, [heading(App.t("search.songs")), this.table]);
        }
        const elsewhere = ExtMusic.section(route.id, data.songs.length > 0 || data.albums.length > 0);
        if (elsewhere) main.appendChild(elsewhere);
      } catch (error) { failed(main, error); }
    },
    destroy() { if (this.table && this.table.destroy) this.table.destroy(); this.table = null; },
  };

  /* ---------- albums : toutes les listes de Subsonic, en onglets ---------- */
  const ALBUM_TABS = ["newest", "frequent", "highest", "recent", "random", "starred", "decade", "genre", "alphabetical"];
  const DECADES = [2020, 2010, 2000, 1990, 1980, 1970, 1960, 1950];

  function albumsLink(kind, value) {
    return "#/albums/" + kind + (value ? "/" + encodeURIComponent(value) : "");
  }

  const albums = {
    destroy() { if (this.shortcuts) this.shortcuts.destroy(); this.shortcuts = null; },
    async render(main, route) {
      const kind = ALBUM_TABS.includes(route.kind) ? route.kind : "newest";
      const tabs = el("nav.tabs", {}, ALBUM_TABS.map(k =>
        el("a.tab" + (k === kind ? ".active" : ""), {href: albumsLink(k), text: App.t("albums.kinds." + k)})));
      this.shortcuts = new LibraryShortcuts(route);
      tabs.firstElementChild.after(this.shortcuts.root);
      App.clear(main);
      App.append(main, [el("h1", {text: App.t(App.layout === "desktop" ? "nav.library" : "nav.albums")}), tabs]);
      if ((kind === "decade" || kind === "genre") && !route.value) return this.chooser(main, route, kind);
      if (route.value) main.appendChild(heading(kind === "decade" ? App.t("albums.decade", {decade: route.value}) : route.value));
      this.grid = albumGrid([]);
      this.more = el("button.more", {type: "button", text: App.t("albums.more"), hidden: true,
                                     onclick: () => this.load(route, kind)});
      App.append(main, [this.grid, this.more]);
      this.page = 0;
      await this.load(route, kind);
    },
    /** Page suivante ajoutée sous les précédentes (« Afficher plus »), sans recharger. */
    async load(route, kind) {
      this.more.disabled = true;
      try {
        const data = await App.api.get("/api/albums", {kind, value: route.value || "", page: this.page});
        if (route.stale) return;
        const cards = albumGrid(data.albums, {showPlays: kind === "frequent"});
        if (this.page === 0) {
          this.grid.replaceWith(cards);
          this.grid = cards;
        } else {
          Array.from(cards.querySelectorAll(".album-card")).forEach(card => this.grid.appendChild(card));
        }
        this.page += 1;
        this.more.hidden = !data.hasMore;
      } catch (error) { App.toast(App.errorText(error), "error"); }
      finally { this.more.disabled = false; }
    },
    async chooser(main, route, kind) {
      if (kind === "decade") {
        main.appendChild(el("div.chips.big", {}, DECADES.map(d =>
          el("a.chip", {href: albumsLink("decade", d), text: App.t("albums.decade", {decade: d})}))));
        return;
      }
      try {
        const data = await App.api.get("/api/genres");
        if (route.stale) return;
        main.appendChild(el("div.chips.big", {}, data.genres.map(g =>
          el("a.chip", {href: albumsLink("genre", g.name), title: App.plural("albums.genre_count", g.albums)},
             g.name, el("span.chip-count", {text: " " + g.albums})))));
      } catch (error) { failed(main, error); }
    },
  };

  /* ---------- favoris ---------- */
  const favorites = {
    render(main, route) { return FavoritesView.render(main, route); },
    destroy() { FavoritesView.destroy(); },
  };

  return {home, artist, album, search, favorites, albums, heading, songTable, albumGrid};
})();
