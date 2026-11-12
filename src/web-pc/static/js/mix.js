"use strict";
/* Page Mix (#/mix, #/mix/<artiste>) : mix rapides, et créateur de mix comme sur le Pi (artiste de départ, styles,
   époques, nombre de titres, favoris d'abord, profondeur des artistes proches, chronologique). Les titres sont choisis par le
   serveur du site (/api/mix/build) ; on les écoute tout de suite ou on les garde en playlist Subsonic. */

Views.mix = (() => {
  const el = App.el, t = App.t;
  const QUICK = [["random", "shuffle"], ["favorites", "heart"], ["discover", "play"], ["newest", "plus"]];

  /** Pastille qui s'allume et s'éteint. */
  function toggleChip(label, on, onchange, extra) {
    const chip = el("button.chip.toggle" + (on ? ".on" : ""), {type: "button", "aria-pressed": String(!!on), onclick: () => {
      const next = onchange();
      chip.classList.toggle("on", next);
      chip.setAttribute("aria-pressed", String(next));
    }}, label, extra || null);
    return chip;
  }

  async function play(request) {
    App.toast(t("mix.building"));
    try {
      const songs = (await request()).songs;
      App.player.playList(songs, 0);
      App.toast(App.plural("album.tracks", songs.length));
    } catch (error) { App.toast(App.errorText(error), "error"); }
  }

  return {
    async render(main, route) {
      App.clear(main);
      let settings;
      try {
        settings = await App.api.get("/api/mix/genres");
      } catch (error) {
        if (!route.stale) main.appendChild(el("p.error", {text: App.errorText(error)}));
        return;
      }
      if (route.stale) return;
      this.route = route;
      this.settings = settings.options;
      this.options = {genres: [], decades: [], size: this.settings.defaultSize, favoritesFirst: false,
                      depth: this.settings.defaultDepth, chronological: false,
                      seedArtistId: "", seedArtistName: ""};
      this.seedPending = !!route.id;
      this.building = false;
      this.seedBox = el("div.mix-seed");
      this.genreBox = el("div.chips.mix-genres", {}, el("span.muted", {text: "…"}));
      App.append(App.clear(main), [
        el("header.page-head", {}, el("h1", {text: t("mix.title")})),
        Views.heading(t("mix.quick")),
        el("div.mix-quick", {}, QUICK.map(([kind, icon]) =>
          App.setIcon(el("button.mix-card", {type: "button", dataset: {kind},
            onclick: () => play(() => App.api.get("/api/mix", {kind}))}), icon, 22, false, t("mix.quick_" + kind)))),
        Views.heading(t("mix.builder")),
        el("p.muted", {text: t("mix.builder_help")}),
        el("h3.mix-label", {text: t("mix.seed")}), this.seedBox,
        el("h3.mix-label", {id: "mix-depth-label", text: t("mix.depth")}),
        el("p.muted", {id: "mix-depth-help", text: t("mix.depth_help")}), this.depthChips(),
        el("h3.mix-label", {text: t("mix.genres")}), this.genreBox,
        el("h3.mix-label", {text: t("mix.decades")}),
        el("div.chips.mix-decades", {}, this.settings.decades.map(year => toggleChip(t("mix.decade", {decade: String(year).slice(2)}), false,
          () => this.flip(this.options.decades, year)))),
        el("h3.mix-label", {text: t("mix.settings")}),
        this.sizeChips(),
        el("div.chips.mix-flags", {},
          toggleChip(t("mix.favorites_first"), false, () => (this.options.favoritesFirst = !this.options.favoritesFirst)),
          toggleChip(t("mix.chronological"), false, () => (this.options.chronological = !this.options.chronological))),
        el("div.mix-actions", {},
          App.setIcon(el("button.primary.mix-play", {type: "button", disabled: this.seedPending,
            onclick: () => this.build(false)}), "play", 16, false, t("mix.play")),
          App.can("playlist") ? App.setIcon(el("button.mix-save", {type: "button", disabled: this.seedPending,
            onclick: () => this.build(true)}),
                                            "plus", 16, false, t("mix.save")) : null)]);
      this.showSeed();
      if (route.id) this.loadSeed(route);
      this.showGenres(settings.genres);
    },

    flip(list, value) {
      const i = list.indexOf(value);
      if (i >= 0) list.splice(i, 1); else list.push(value);
      return i < 0;
    },

    sizeChips() {
      const box = el("div.chips.mix-sizes");
      const chips = this.settings.sizes.map(size => el("button.chip.toggle" + (size === this.options.size ? ".on" : ""), {type: "button",
        text: App.plural("album.tracks", size), onclick: () => {
          this.options.size = size;
          chips.forEach((chip, i) => chip.classList.toggle("on", this.settings.sizes[i] === size));
        }}));
      App.append(box, chips);
      return box;
    },

    depthChips() {
      const box = el("div.chips.mix-depths", {role: "group", "aria-labelledby": "mix-depth-label",
                                            "aria-describedby": "mix-depth-help"});
      const chips = this.settings.depths.map(depth => el("button.chip.toggle" + (depth === this.options.depth ? ".on" : ""),
        {type: "button", dataset: {depth}, text: App.plural("mix.depth_levels", depth),
         "aria-pressed": String(depth === this.options.depth), onclick: () => {
          this.options.depth = depth;
          chips.forEach((chip, i) => {
            chip.classList.toggle("on", this.settings.depths[i] === depth);
            chip.setAttribute("aria-pressed", String(this.settings.depths[i] === depth));
          });
        }}));
      App.append(box, chips);
      return box;
    },

    showGenres(genres) {
      App.clear(this.genreBox);
      if (!genres.length) this.genreBox.appendChild(el("span.muted", {text: t("mix.no_genres")}));
      App.append(this.genreBox, genres.slice(0, 40).map(g => toggleChip(g.label, false,
        () => this.flip(this.options.genres, g.key), el("span.chip-count", {text: " " + g.count}))));
    },

    /** #/mix/<id> (bouton « Créer un mix » de la page artiste) : artiste de départ déjà choisi. */
    async loadSeed(route, id = route.id) {
      this.seedPending = true;
      this.setBusy(this.building);
      try {
        const artist = await App.api.get("/api/artist", {id});
        if (route.stale) return;
        const musicId = artist.id3Id || (id.startsWith("f") ? "" : id);
        if (!musicId) {
          this.seedBox.appendChild(el("p.error", {text: t("mix.empty")}));
          return;
        }
        this.setSeed(musicId, artist.name);
      } catch (error) {
        if (!route.stale) this.seedBox.appendChild(el("p.error", {text: App.errorText(error)}));
      }
    },

    setSeed(id, name) {
      this.options.seedArtistId = id || "";
      this.options.seedArtistName = name || "";
      this.seedPending = false;
      this.setBusy(this.building);
      this.showSeed();
    },

    setBusy(busy) {
      document.querySelectorAll(".mix-play, .mix-save").forEach(button => {
        button.disabled = busy || this.seedPending;
      });
    },

    /** Soit l'artiste choisi (avec ✕), soit un champ de recherche qui propose des artistes. */
    showSeed() {
      App.clear(this.seedBox);
      if (this.options.seedArtistId) {
        this.seedBox.appendChild(el("button.chip.toggle.on.mix-seed-chosen", {type: "button", title: t("mix.seed_clear"),
          onclick: () => this.setSeed("", "")}, t("mix.seed_like", {name: this.options.seedArtistName}), " ✕"));
        return;
      }
      const results = el("div.chips.mix-seed-results");
      const route = this.route;
      let timer = null;
      const input = el("input.mix-seed-input", {type: "search", placeholder: t("mix.seed_placeholder"), oninput: () => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
          const query = input.value.trim();
          App.clear(results);
          if (query.length < 2) return;
          let artists = [];
          try { artists = (await App.api.get("/api/search", {q: query})).artists; } catch (error) { return; }
          if (route.stale || input.value.trim() !== query) return;
          App.append(results, artists.slice(0, 8).map(a =>
            el("button.chip", {type: "button", text: a.name, onclick: async () => {
              input.disabled = true;
              App.clear(results);
              await this.loadSeed(route, a.id);
              input.disabled = false;
            }})));
        }, 250);
      }});
      App.append(this.seedBox, [input, results]);
    },

    async build(save) {
      if (this.seedPending || this.building) return;
      this.building = true;
      this.setBusy(true);
      App.toast(t("mix.building"));
      try {
        const result = await App.api.post("/api/mix/build", this.options);
        if (!save) {
          App.player.playList(result.songs, 0);
          App.toast(App.plural("album.tracks", result.songs.length));
          return;
        }
        const name = await Dialogs.ask(t("mix.save_name"), result.name);
        if (!name) return;
        await App.api.post("/api/playlist/create", {name, songIds: result.songs.map(s => s.id)});
        App.toast(t("mix.saved", {name, count: result.songs.length}));
      } catch (error) {
        App.toast(App.errorText(error), "error");
      } finally {
        this.building = false;
        this.setBusy(false);
      }
    },
  };
})();
