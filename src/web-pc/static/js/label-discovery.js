"use strict";
/* Un parcours de label : catalogue identifié, sélection variée ou classement explicite, puis playlist mixte. */
const LabelDiscoveryUI = (() => {
  const el = App.el, t = key => App.t("discovery." + key);

  class Panel {
    constructor(name, route, identity) {
      this.route = route;
      this.generation = 0;
      this.offset = 0;
      this.phase = "idle";
      this.progress = el("div.discovery-progress.muted", {role: "status"});
      this.rankings = el("div.discovery-rankings");
      this.tracks = PageSections.section("label-selection", ".discovery-preview");
      this.notice = el("div.discovery-label-notice", {hidden: true});
      this.controls = el("div.discovery-controls", {hidden: true});
      this.source = el("select.discovery-source", {"aria-label": t("criterion"), onchange: () => this.start("top")});
      this.stop = DiscogsUI.button(t("pause"), "pause", () => this.pause(), ".discovery-stop");
      this.resume = DiscogsUI.button(t("continue"), "plus", () => this.start("top", true), ".discovery-resume");
      this.stop.hidden = this.resume.hidden = true;
      this.root = el("section.label-discovery", {}, this.intro(),
        identity ? DiscogsUI.source("label", identity.id, identity.name) :
          DiscogsUI.picker(name, "label", route, selected => this.choose(selected)), this.notice, this.controls,
        this.progress, this.rankings, this.tracks);
      if (identity) this.choose(identity);
    }

    intro() {
      return el("div.discovery-intro", {}, el("div.discovery-mark", {}, App.icon("disc", 38)),
        el("div", {}, el("span.kicker", {text: t("label_kicker")}), el("h2", {text: t("label_title")}),
          el("p.muted", {text: t("label_help")})));
    }

    async choose(identity) {
      const generation = ++this.generation;
      this.identity = identity;
      this.catalog = null;
      this.offset = 0;
      this.ranking = null;
      App.clear(this.tracks);
      App.clear(this.rankings);
      this.progress.textContent = "";
      this.controls.hidden = this.notice.hidden = true;
      try {
        const [status, details] = await Promise.all([App.api.get("/api/discogs/status"),
          "companyOnly" in identity ? Promise.resolve(identity) : App.api.get("/api/discogs/identity", {kind: "label", id: identity.id})]);
        if (!this.active(generation)) return;
        this.identity = details;
        if (details.companyOnly) { this.showCompany(details); return; }
        this.showControls(status);
      } catch (failure) { if (this.active(generation)) this.progress.textContent = App.errorText(failure); }
    }

    showCompany(details) {
      this.notice.hidden = false;
      App.append(App.clear(this.notice), [el("p", {role: "status", text: t("company_only")}),
        details.labels.length ? el("div.chips", {}, details.labels.map(label => el("a.button.primary.discovery-related-label", {
          href: "#/discogs/label/" + encodeURIComponent(label.id), text: App.t("discovery.open_label", {name: label.name})}))) :
          DiscogsUI.picker(details.name, "label", this.route, identity => this.choose(identity))]);
    }

    showControls(status) {
      App.append(App.clear(this.source), status.sources.map(value => el("option", {value, text: t("source_" + value)})));
      this.discover = this.mode("discover", "shuffle");
      this.top = this.mode("top", "list");
      App.append(App.clear(this.controls), [
        el("div.discovery-mode-grid", {}, this.discover, this.top),
        el("label.discovery-criterion", {}, el("span", {text: t("criterion")}), this.source),
        el("div.discovery-actions", {}, this.stop, this.resume)]);
      this.controls.hidden = false;
    }

    mode(mode, icon) {
      return el("button.discovery-mode", {type: "button", dataset: {mode}, "aria-pressed": "false",
        onclick: () => this.start(mode)}, App.icon(icon, 24), el("strong", {text: t(mode)}),
        el("span.muted", {text: t(mode + "_help")}));
    }

    active(generation) { return !this.route.stale && this.generation === generation; }

    busy(on, mode) {
      this.discover.disabled = this.top.disabled = this.source.disabled = on;
      this.controls.setAttribute("aria-busy", String(on));
      this.stop.hidden = !on || mode !== "top" || this.phase !== "ranking";
      for (const button of [this.discover, this.top]) {
        button.classList.toggle("on", button.dataset.mode === mode);
        button.setAttribute("aria-pressed", String(button.dataset.mode === mode));
      }
    }

    async start(mode, continuing = false) {
      const generation = ++this.generation;
      this.paused = false;
      this.phase = "catalog";
      this.stop.disabled = false;
      if (!continuing) { this.ranking = null; this.offset = 0; App.clear(this.rankings); }
      this.resume.hidden = true;
      App.clear(this.tracks);
      this.busy(true, mode);
      try {
        await this.loadCatalog(generation);
        if (!this.active(generation)) return;
        const albums = mode === "discover" ? await this.discoverAlbums(generation) : await this.topAlbums(generation, continuing);
        if (!this.active(generation)) return;
        await this.prepareSelection(albums, mode, generation);
      } catch (failure) {
        if (this.active(generation)) {
          if (["discovery.load_catalog", "discovery.rank_restart"].includes(failure.code)) this.catalog = null;
          DiscogsUI.error(this.progress, failure, () => this.start(mode));
        }
      } finally {
        if (this.active(generation)) this.busy(false, mode);
      }
    }

    pause() {
      if (this.paused || this.phase !== "ranking") return;
      this.paused = true;
      this.stop.disabled = true;
      this.progress.textContent = t("pausing");
      if (this.ranking) {
        const generation = ++this.generation;
        this.prepareSelection(this.ranking.scores.map(score => score.album), "top", generation);
      }
    }

    async prepareSelection(albums, mode, generation) {
      this.phase = "selection";
      this.stop.hidden = true;
      try { await this.loadTracks(albums, mode, generation); }
      catch (failure) {
        if (this.active(generation)) {
          const expired = ["discovery.load_catalog", "discovery.rank_restart"].includes(failure.code);
          if (expired) this.catalog = null;
          DiscogsUI.error(this.progress, failure, () => expired ? this.start(mode) :
            this.prepareSelection(albums, mode, ++this.generation));
        }
      } finally { if (this.active(generation)) this.busy(false, mode); }
    }

    async loadCatalog(generation) {
      if (this.catalog && this.catalog.complete) return;
      let page = this.catalog ? this.catalog.page + 1 : 1;
      do {
        this.progress.textContent = App.t("discovery.loading_catalog", {page});
        const data = await App.api.get("/api/discogs/catalog", {kind: "label", id: this.identity.id, page});
        if (!this.active(generation)) return;
        this.catalog = data;
        page += 1;
      } while (!this.catalog.complete);
    }

    async discoverAlbums(generation) {
      const result = await App.api.get("/api/labels/discover", {id: this.identity.id});
      if (!this.active(generation)) return [];
      App.append(App.clear(this.rankings), [el("p.muted", {text: t("diversity")}),
        el("div.album-grid.discogs-grid", {}, result.albums.map(album => DiscogsUI.card(album)))]);
      return result.albums;
    }

    async topAlbums(generation, continuing) {
      if (!continuing) this.offset = 0;
      this.phase = "ranking";
      this.stop.hidden = false;
      let data;
      do {
        data = await App.api.get("/api/labels/ranking", {id: this.identity.id, source: this.source.value, offset: this.offset});
        if (!this.active(generation)) return [];
        this.ranking = data;
        this.offset = data.analyzed;
        this.showRanking(data);
        this.progress.textContent = App.t("discovery.ranking_progress", {done: data.analyzed, total: data.total});
      } while (!data.complete && !this.paused);
      this.resume.hidden = data.complete;
      return data.scores.map(score => score.album);
    }

    showRanking(data) {
      App.append(App.clear(this.rankings), [el("p.discovery-method", {text: t("method_" + data.source)}),
        el("p.discovery-scope", {text: App.t(data.complete ? "discovery.rank_complete" : "discovery.rank_partial",
          {done: data.analyzed, total: data.total})}),
        data.excluded ? el("p.muted", {text: App.t("discovery.excluded", {count: data.excluded})}) : null,
        el("ol.discovery-top", {}, data.scores.map((score, i) => this.rankRow(score, i))),
        !data.scores.length ? el("p.muted", {text: t("no_scores")}) : null]);
    }

    rankRow(score, index) {
      const album = score.album;
      const figures = score.source === "discogs" ? App.t("discovery.rating", {rating: score.value.toFixed(2), votes: score.votes}) :
        App.t("discovery.popularity", {listeners: score.listeners.toLocaleString("fr"), plays: score.plays.toLocaleString("fr")});
      return el("li", {}, el("span.discovery-rank", {text: String(index + 1).padStart(2, "0")}),
        App.cover(album.image, 56, album.title), el("div.discovery-ranked-title", {}, el("strong", {text: album.title}),
          el("span.muted", {text: [album.artist, album.year].filter(Boolean).join(" · ")})),
        el("div.discovery-figures", {}, el("strong", {text: figures}), score.edition ?
          DiscogsUI.source("release", score.edition, t("rated_edition")) : el("a.discogs-source", {
            href: "https://www.last.fm/music/" + encodeURIComponent(album.artist) + "/" + encodeURIComponent(album.title),
            target: "_blank", rel: "noopener noreferrer", text: t("lastfm")})));
    }

    async loadTracks(albums, mode, generation) {
      const name = App.t("discovery.playlist_default", {mode: t(mode), label: this.identity.name});
      const playlist = new DiscoveryTracks.Playlist(this.tracks, this.route, name, () => this.active(generation));
      playlist.show([], true);
      playlist.progress(0, albums.length);
      if (mode === "top") this.resume.hidden = !this.ranking || this.ranking.complete;
      if (this.paused) {
        if (typeof this.tracks.scrollIntoView === "function") this.tracks.scrollIntoView({block: "start"});
        this.tracks.focus({preventScroll: true});
      }
      let excluded = 0;
      for (let i = 0; i < albums.length; i++) {
        this.progress.textContent = App.t("discovery.matching", {done: i + 1, total: albums.length});
        const data = await App.api.get("/api/labels/tracks", {id: this.identity.id, album: albums[i].id, mode});
        if (!this.active(generation)) return;
        const card = this.rankings.querySelector('[data-album="' + albums[i].id + '"]');
        if (data.eligible === false) { excluded++; if (card) card.remove(); }
        else if (card) card.replaceWith(DiscogsUI.card(data.album));
        playlist.append(data.tracks);
        playlist.progress(i + 1, albums.length);
      }
      if (!this.active(generation)) return;
      playlist.finish();
      this.progress.textContent = this.paused ? t(albums.length ? "paused_selection" : "paused_empty") : "";
      if (excluded) this.rankings.appendChild(el("p.muted", {text: App.t("discovery.excluded", {count: excluded})}));
    }
  }

  return {panel: (name, route, identity) => new Panel(name, route, identity).root};
})();
