"use strict";
/* Aperçu écoutable et playlist : reprend les recherches YouTube et l'enregistrement mixte déjà disponibles. */
const DiscoveryTracks = (() => {
  const el = App.el, t = key => App.t("discovery." + key);

  class Row {
    constructor(result, active, changed) {
      this.result = result;
      this.changed = changed;
      this.items = [...result.choices];
      this.select = el("select.discovery-version", {"aria-label": App.t("discovery.version_of", {title: result.track.title}),
        onchange: () => this.update()});
      this.note = el("span.import-status", {text: App.t("import.status_" + result.status)});
      this.versions = new DiscoveryVersions(result, active, items => this.received(items), item => this.choose(item));
      this.node = el("li.discovery-track", {}, this.note,
        el("div.import-wanted", {}, el("strong", {text: result.track.title}),
          el("span.muted", {text: [result.track.artist, result.track.album].filter(Boolean).join(" · ")})),
        this.select, this.versions.root);
      this.fill(result.status === "found" ? 0 : -1);
    }

    fill(chosen) {
      App.append(App.clear(this.select), [el("option", {value: "-1", text: t("skip")}),
        ...this.items.map((item, i) => el("option", {value: String(i), text: App.t(item.ext ? "discovery.youtube_choice" :
          "discovery.local_choice", {title: item.title, artist: item.artist, album: item.album || ""})}))]);
      this.select.value = String(chosen);
      this.update();
    }

    get item() { return this.items[Number(this.select.value)] || null; }
    get entry() { const item = this.item; return item ? item.ext ? {item} : {songId: item.id} : null; }

    received(items) {
      const chosen = this.item;
      this.items = [...this.result.choices, ...items];
      this.fill(chosen ? this.items.findIndex(item => item.id === chosen.id) : -1);
    }

    choose(item) {
      this.select.value = String(this.items.findIndex(candidate => candidate.id === item.id));
      this.update();
    }

    update() {
      this.versions.mark(this.item);
      this.note.textContent = this.item && this.item.ext ? t("youtube_source") :
        this.versions.items.length && !this.item ? t("choose_version") : App.t("import.status_" + this.result.status);
      this.changed();
    }
  }

  class Playlist {
    constructor(root, route, name, current = () => true) {
      this.root = root;
      this.route = route;
      this.name = name;
      this.rows = [];
      this.active = () => !route.stale && current() && root.isConnected;
    }

    show(results, preparing = false) {
      this.rows = [];
      this.preparing = preparing;
      this.searchTotal = this.searchDone = 0;
      this.searchStopped = false;
      this.searchTask = Promise.resolve();
      if (!results.length && !preparing) {
        App.append(App.clear(this.root), [Views.heading(t("your_selection")),
          el("p.discovery-empty.muted", {role: "status", text: t("empty_selection")})]);
        return;
      }
      this.count = el("p.discovery-chosen", {role: "status"});
      this.play = DiscogsUI.button(t("listen"), "play", () => this.listen(), ".primary.discovery-play");
      this.save = DiscogsUI.button(t("save"), "plus", () => this.persist(), ".discovery-save");
      this.searchStatus = el("p.discovery-search-progress.muted", {role: "status"});
      this.preparation = el("p.discovery-preparation.muted", {role: "status", hidden: !preparing});
      this.list = el("ol.discovery-tracks");
      App.append(App.clear(this.root), [Views.heading(t("your_selection")),
        el("p.muted", {text: t("versions_help")}), this.preparation, this.count,
        el("div.discovery-actions", {}, App.can("stream") ? this.play : null, App.can("playlist") ? this.save : null),
        this.searchStatus, this.list]);
      this.append(results);
      this.update();
    }

    append(results) {
      const rows = results.map(result => new Row(result, this.active, () => this.update()));
      this.rows.push(...rows);
      App.append(this.list, rows.map(row => row.node));
      this.update();
      const missing = rows.filter(row => row.result.status !== "found");
      if (!missing.length) return;
      this.searchTotal += missing.length;
      if (!this.searchStopped) this.searchProgress();
      this.searchTask = this.searchTask.then(() => this.searchMissing(missing));
    }

    progress(done, total) {
      this.preparation.textContent = App.t("discovery.selection_progress", {done, total});
    }

    finish() {
      this.preparing = false;
      this.preparation.hidden = true;
      if (!this.rows.length) { this.show([]); return; }
      if (this.searchTotal && !this.searchStopped) this.searchProgress();
    }

    async searchMissing(rows) {
      if (!this.active()) return;
      if (this.searchStopped) { rows.forEach(row => row.versions.stopped(t("youtube_paused"))); return; }
      this.queue = [...rows];
      try {
        if (!this.sourceCheck) this.sourceCheck = App.api.get("/api/ext/status");
        const status = await this.sourceCheck;
        if (!this.active()) return;
        if (!status.youtube) { this.stopSearches(App.t("ext.disabled")); return; }
        await Promise.all([this.searchWorker(), this.searchWorker()]);
      } catch (failure) { if (this.active()) this.stopSearches(App.errorText(failure)); }
    }

    async searchWorker() {
      while (this.active() && this.queue.length) {
        const row = this.queue.shift();
        const failure = row.item ? null : await row.versions.find();
        if (!this.active()) return;
        this.searchDone++;
        if (failure) { this.stopSearches(App.errorText(failure)); return; }
        if (!this.searchStopped) this.searchProgress();
      }
    }

    searchProgress() {
      this.searchStatus.textContent = App.t(this.searchDone === this.searchTotal && !this.preparing ? "discovery.youtube_complete" :
        "discovery.youtube_progress", {done: this.searchDone, total: this.searchTotal});
    }

    stopSearches(message) {
      this.searchStopped = true;
      this.searchStatus.textContent = message;
      this.rows.forEach(row => row.versions.stopped(t("youtube_paused")));
      this.queue = [];
    }

    chosen() {
      const seen = new Set();
      return this.rows.filter(row => {
        if (!row.item || seen.has(row.item.id)) return false;
        seen.add(row.item.id);
        return true;
      });
    }

    update() {
      const count = this.chosen().length;
      this.count.hidden = !this.rows.length;
      this.count.textContent = App.t("discovery.selected_count", {count, total: this.rows.length});
      this.play.disabled = !count;
      this.save.disabled = !count || !!this.saving;
    }

    listen() {
      const songs = this.chosen().map(row => row.item);
      if (songs.length) App.player.playList(songs, 0);
    }

    async persist() {
      if (this.saving) return;
      const name = await Dialogs.ask(t("playlist_name"), this.name);
      if (!name || !this.active() || this.saving) return;
      const chosen = this.chosen();
      this.saving = true;
      this.save.disabled = true;
      try {
        const {playlist} = await App.api.post("/api/import/create", {name, entries: chosen.map(row => row.entry)});
        await App.playlists.load();
        App.toast(App.t("import.created", {name: playlist.name, count: chosen.length}));
        if (!this.route.stale) location.hash = "#/playlist/" + encodeURIComponent(playlist.id);
      } catch (failure) { App.toast(App.errorText(failure), "error"); }
      finally { this.saving = false; this.update(); }
    }
  }

  return {Playlist};
})();
