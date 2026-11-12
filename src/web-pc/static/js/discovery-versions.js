"use strict";
/* Recherche et choix visibles des versions d'un morceau ; aucune lecture ni sélection automatique. */
const DiscoveryVersions = (() => {
  const el = App.el, t = key => App.t("discovery." + key);

  class Versions {
    constructor(result, active, received, choose) {
      this.result = result;
      this.active = active;
      this.received = received;
      this.choose = choose;
      this.items = [];
      this.status = el("p.discovery-video-status.muted", {role: "status", text: t("youtube_waiting")});
      this.results = el("div.discovery-video-list");
      this.button = DiscogsUI.button(t("youtube_versions"), "disc", () => this.find(), ".link-button.discovery-youtube");
      this.root = el("div.discovery-versions", {hidden: result.status === "found"}, this.status, this.results, this.button);
    }

    find() {
      if (this.pending) return this.pending;
      if (this.loaded || !this.active()) return Promise.resolve(null);
      this.pending = this.load().finally(() => { this.pending = null; });
      return this.pending;
    }

    busy(on) {
      this.root.setAttribute("aria-busy", String(on));
      this.button.disabled = on;
      this.button.hidden = on || !!this.loaded;
      if (on) {
        this.status.textContent = t("youtube_searching");
        App.setIcon(this.button, "disc", 18, false, t("youtube_searching"));
      }
    }

    async load() {
      this.busy(true);
      try {
        const data = await App.api.post("/api/labels/versions", {release: this.result.edition, track: this.result.track});
        if (!this.active()) return null;
        this.items = data.items;
        this.loaded = true;
        this.show(data.warning);
        this.received(this.items);
        return null;
      } catch (failure) {
        if (this.active()) {
          this.status.textContent = App.errorText(failure);
          this.status.classList.add("page-error");
          App.setIcon(this.button, "undo", 18, false, t("retry"));
        }
        return failure;
      } finally { if (this.active()) this.busy(false); }
    }

    show(warning) {
      this.status.classList.remove("page-error");
      this.status.textContent = this.items.length ? App.plural("discovery.youtube_found", this.items.length) : t("no_video");
      if (warning) this.status.textContent += " · " + App.t(warning);
      App.append(App.clear(this.results), this.items.map(item => this.card(item)));
      this.button.hidden = true;
    }

    card(item) {
      const source = item.discoverySource === "discogs" ? t("youtube_discogs") : t("youtube_source");
      const details = [source, item.duration ? App.duration(item.duration) : "", item.artist].filter(Boolean).join(" · ");
      return el("button.discovery-video", {type: "button", dataset: {video: item.youtubeId}, "aria-pressed": "false",
        "aria-label": App.t("discovery.select_video", {title: item.title}), onclick: () => this.choose(item)},
        App.cover(item.imageUrl, 64, ""), el("span.discovery-video-copy", {},
          el("strong", {text: item.title}), el("span.muted", {text: details})), App.icon("disc", 18));
    }

    mark(item) {
      this.results.querySelectorAll(".discovery-video").forEach(button => {
        const selected = !!item && item.youtubeId === button.dataset.video;
        button.classList.toggle("on", selected);
        button.setAttribute("aria-pressed", String(selected));
      });
    }

    stopped(message) { if (!this.loaded && !this.pending) this.status.textContent = message; }
  }

  return Versions;
})();
