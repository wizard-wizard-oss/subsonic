"use strict";
/* Page « Importer une playlist » (#/import) : un lien Deezer ou un fichier (CSV Spotify, XML Apple Music, M3U, texte)
   est lu par le serveur ; chaque titre est cherché dans la bibliothèque par lots, ceux qui manquent sur YouTube ;
   la personne vérifie (un choix par titre), puis la playlist est créée, titres YouTube compris, dans l'ordre.
   Droit Subsonic « playlist » requis. */

Views.import = (() => {
  const el = App.el, t = App.t;
  const MATCH_BATCH = 25, YOUTUBE_BATCH = 5;
  const MAX_FILE_BYTES = 4 * 1024 * 1024;            // le serveur accepte 5 Mo de JSON : marge pour l'échappement
  const SKIP = "skip", YOUTUBE = "youtube";
  const GUIDE = ["deezer", "spotify", "apple_mac", "apple_phone", "others", "after"];

  /** Ligne d'un titre : ce qu'on cherchait, l'état, et le choix (titre de la bibliothèque, YouTube, rien). */
  class Row {
    constructor(track) {
      this.track = track;
      this.status = "";                               // found | doubt | missing, donné par le serveur
      this.choices = [];
      this.youtube = null;
      this.badge = el("span.import-status");
      this.select = el("select.import-choice", {disabled: true, onchange: () => this.show()});
      const details = [track.artist, track.album, track.duration ? App.duration(track.duration) : ""].filter(Boolean);
      this.node = el("li.import-row", {},
        this.badge,
        el("div.import-wanted", {}, el("strong", {text: track.title}), el("span.muted", {text: details.join(" · ")})),
        this.select);
    }

    matched(result) {
      this.status = result.status;
      this.choices = result.choices;
      this.fill();
    }

    found(item) {
      this.youtube = item;
      this.fill();
      if (item && this.status === "missing") this.select.value = YOUTUBE;
      this.show();
    }

    fill() {
      App.clear(this.select);
      this.choices.forEach((song, i) => this.select.appendChild(el("option", {value: String(i),
        text: t(song.album ? "import.in_album" : "import.in_library", {title: song.title, artist: song.artist, album: song.album})})));
      if (this.youtube) this.select.appendChild(el("option", {value: YOUTUBE,
        text: t("import.on_youtube", {title: this.youtube.title, artist: this.youtube.artist})}));
      this.select.appendChild(el("option", {value: SKIP, text: t("import.skip")}));
      this.select.value = this.choices.length ? "0" : SKIP;
      this.select.disabled = false;
      this.show();
    }

    /** État affiché : celui du choix fait (un titre douteux accepté reste « à vérifier »). */
    get shown() {
      if (this.select.value === YOUTUBE) return "youtube";
      if (this.select.value === SKIP || !this.status) return this.status ? "missing" : "";
      return this.status === "found" ? "found" : "doubt";
    }

    show() {
      const state = this.shown;
      this.badge.className = "import-status" + (state ? " import-" + state : "");
      this.badge.textContent = state ? t("import.status_" + state) : "…";
    }

    /** Ce que la ligne apporte à la playlist : {songId}, {item} (YouTube) ou null. */
    entry() {
      if (this.select.disabled || this.select.value === SKIP) return null;
      if (this.select.value === YOUTUBE) return {item: this.youtube};
      return {songId: this.choices[Number(this.select.value)].id};
    }
  }

  return {
    render(main, route) {
      this.route = route;
      App.clear(main);
      main.appendChild(el("h1", {text: t("import.title")}));
      if (!App.can("playlist")) {
        main.appendChild(el("p.page-error", {text: t("import.no_right")}));
        return;
      }
      this.main = main;
      if (route.id === "guide") this.showGuide();
      else this.showSources();
    },

    /** Guide pas à pas, une carte par plateforme ; textes import.guide.<plateforme>.step_1, step_2… */
    showGuide() {
      const steps = key => {
        const items = [];
        for (let n = 1; App.texts[key + ".step_" + n] !== undefined; n++) items.push(el("li", {text: t(key + ".step_" + n)}));
        return el("ol.import-steps", {}, items);
      };
      App.append(this.main, [
        el("p.muted", {text: t("import.guide.intro")}),
        el("div.import-guide", {}, GUIDE.map(name => {
          const key = "import.guide." + name;
          return el("section.import-part", {},
            el("h2", {text: t(key + ".title")}),
            App.texts[key + ".note"] !== undefined ? el("p.muted", {text: t(key + ".note")}) : null,
            steps(key));
        })),
        el("a.button.primary", {href: "#/import", text: t("import.guide.go")})]);
    },

    showSources() {
      const link = el("input.import-link", {type: "url", placeholder: t("import.link_placeholder"), autocomplete: "off"});
      const file = el("input", {type: "file", hidden: true, accept: ".csv,.xml,.m3u,.m3u8,.txt",
                                onchange: () => { if (file.files[0]) this.readFile(file.files[0]); file.value = ""; }});
      this.sources = el("div.import-sources", {},
        el("p.muted", {}, t("import.intro") + " ", el("a", {href: "#/import/guide", text: t("import.guide_link")})),
        el("form.import-part", {onsubmit: e => { e.preventDefault(); this.read({link: link.value}); }},
          el("h2", {text: t("import.link_title")}),
          el("p.muted", {text: t("import.link_help")}),
          el("div.import-line", {}, link, el("button.primary", {type: "submit", text: t("import.read_link")}))),
        el("section.import-part", {},
          el("h2", {text: t("import.file_title")}),
          ["file_spotify", "file_apple", "file_other"].map(key => el("p.muted", {text: t("import." + key)})),
          file, el("button", {type: "button", text: t("import.choose_file"), onclick: () => file.click()})));
      App.append(this.main, [this.sources]);
    },

    readFile(file) {
      if (file.size > MAX_FILE_BYTES) {
        App.toast(t("import.file_too_big"), "error");
        return;
      }
      const reader = new FileReader();
      reader.onload = () => this.read({name: file.name, content: String(reader.result || "")});
      reader.onerror = () => App.toast(t("import.unknown_format"), "error");
      reader.readAsText(file);
    },

    async read(body) {
      const route = this.route;
      App.toast(t("import.reading"));
      let playlist;
      try {
        playlist = await App.api.post("/api/import/read", body);
      } catch (error) {
        if (!route.stale) App.toast(App.errorText(error), "error");
        return;
      }
      if (route.stale) return;
      if (playlist.choose) {                    // export de toute la bibliothèque Apple : quelle playlist ?
        this.showChoice(body, playlist.choose);
        return;
      }
      this.sources.remove();
      if (this.choice) this.choice.remove();
      this.showPlaylist(playlist);
      await this.matchAll(route);
      if (!route.stale) await this.youtubeAll(route);
    },

    /** Le fichier contient plusieurs playlists : une ligne par playlist, le fichier est relu avec celle choisie. */
    showChoice(body, playlists) {
      if (this.choice) this.choice.remove();
      this.sources.hidden = true;
      this.choice = el("section.import-part.import-choose", {},
        el("h2", {text: t("import.choose_title")}),
        el("p.muted", {text: t("import.choose_help", {count: playlists.length})}),
        el("ul.import-playlists", {}, playlists.map(p => el("li", {},
          el("button", {type: "button", onclick: () => this.read(Object.assign({}, body, {playlist: p.index}))},
            el("strong", {text: p.name}), el("span.muted", {text: App.plural("import.choose_count", p.count)}))))),
        el("button", {type: "button", text: t("import.choose_other"), onclick: () => App.music.navigate()}));
      this.main.appendChild(this.choice);
    },

    showPlaylist(playlist) {
      this.rows = playlist.tracks.map(track => new Row(track));
      this.name = el("input.import-name", {type: "text", maxLength: 100, value: playlist.name});
      this.progress = el("p.import-progress");
      this.summary = el("p.import-summary");
      this.create = el("button.primary", {type: "button", disabled: true, onclick: () => this.save()});
      const list = el("ol.import-list", {}, this.rows.map(r => r.node));
      list.addEventListener("change", () => this.count());
      App.append(this.main, [
        el("label.import-name-label", {}, el("span", {text: t("import.name")}), this.name),
        this.progress, this.summary, list,
        el("div.import-actions", {}, this.create,
          el("button", {type: "button", text: t("import.restart"), onclick: () => App.music.navigate()}))]);
      this.count();
    },

    async matchAll(route) {
      for (let start = 0; start < this.rows.length; start += MATCH_BATCH) {
        this.progress.textContent = t("import.searching", {done: start, total: this.rows.length});
        const batch = this.rows.slice(start, start + MATCH_BATCH);
        try {
          const {results} = await App.api.post("/api/import/match", {tracks: batch.map(r => r.track)});
          if (route.stale) return;
          results.forEach((result, i) => batch[i].matched(result));
        } catch (error) {
          if (!route.stale) App.toast(App.errorText(error), "error");
          return;
        }
        this.count();
      }
      this.progress.textContent = "";
    },

    async youtubeAll(route) {
      let status = {};
      try { status = await App.api.get("/api/ext/status"); } catch (error) { /* sans YouTube : on s'arrête là */ }
      const missing = this.rows.filter(r => r.status === "missing");
      if (!status.youtube || !missing.length || route.stale) return;
      for (let start = 0; start < missing.length; start += YOUTUBE_BATCH) {
        this.progress.textContent = t("import.searching_youtube", {done: start, total: missing.length});
        const batch = missing.slice(start, start + YOUTUBE_BATCH);
        let answer;
        try {
          answer = await App.api.post("/api/import/youtube", {tracks: batch.map(r => r.track)});
        } catch (error) {
          answer = {items: [], stopped: error.code || "server.error"};
        }
        if (route.stale) return;
        answer.items.forEach((item, i) => batch[i].found(item));
        this.count();
        if (answer.stopped) {
          App.toast(t("import.youtube_stopped", {reason: App.errorText(new ApiError(400, answer.stopped))}), "error");
          break;
        }
      }
      this.progress.textContent = "";
    },

    count() {
      const counts = {found: 0, doubt: 0, youtube: 0, missing: 0};
      this.rows.forEach(r => { if (r.shown) counts[r.shown] += 1; });
      this.summary.textContent = t("import.summary", counts);
      const chosen = this.rows.filter(r => r.entry()).length;
      this.create.textContent = t("import.create", {count: chosen});
      this.create.disabled = !chosen;
    },

    async save() {
      const entries = this.rows.map(r => r.entry()).filter(Boolean);
      this.create.disabled = true;
      try {
        const {playlist} = await App.api.post("/api/import/create", {name: this.name.value, entries});
        App.toast(t("import.created", {name: playlist.name, count: entries.length}));
        await App.playlists.load();
        if (playlist.id) location.hash = "#/playlist/" + encodeURIComponent(playlist.id);
      } catch (error) {
        App.toast(App.errorText(error), "error");
        this.create.disabled = false;
      }
    },
  };
})();
