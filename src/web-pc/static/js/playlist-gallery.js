"use strict";
/* Page dédiée : filtres et pagination restent en place quand une playlist est modifiée. */
Views.playlists = {
  async render(main, route) {
    this.destroy();
    this.route = route;
    this.owner = App.user.id;
    this.cards = new Map();
    this.page = 0;
    this.revision = 0;
    const el = App.el;
    this.search = el("input", {type: "search", placeholder: App.t("playlist.search"),
      "aria-label": App.t("playlist.search"), oninput: () => this.filter(true)});
    this.sort = el("select", {"aria-label": App.t("playlist.sort"), onchange: () => this.filter(false)});
    this.grid = el("div.playlist-gallery-grid");
    this.status = el("p.muted", {role: "status", "aria-live": "polite"});
    this.more = el("button.button.playlist-gallery-more", {type: "button", hidden: true,
      text: App.t("albums.more"), onclick: () => this.load(false)});
    this.retry = el("button.button", {type: "button", hidden: true, text: App.t("nav.artists_retry"),
      onclick: () => this.load(this.failedReset)});
    const actions = App.can("playlist") ? [
      el("button.primary", {type: "button", text: App.t("playlist.new"), onclick: async () => {
        const created = await App.playlists.create(null);
        if (created && created.id && this.current(route)) location.hash = "#/playlist/" + encodeURIComponent(created.id);
      }}), el("a.button", {href: "#/import", text: App.t("playlist.import")})] : [];
    App.clear(main).appendChild(el("section.playlist-gallery", {},
      el("header.page-head", {}, el("h1", {text: App.t("playlist.tab")}), actions),
      el("div.playlist-gallery-filters", {}, this.search, this.sort), this.grid, this.status, this.more, this.retry));
    this.offChanged = App.bus.on("playlist-changed", id => this.refresh(id));
    this.offLists = App.bus.on("playlists", items => this.reconcile(items));
    await this.load(true);
  },

  current(route, revision = this.revision) {
    return route && this.route === route && !route.stale && App.user && App.user.id === this.owner && revision === this.revision;
  },

  filter(debounce) {
    clearTimeout(this.timer);
    this.revision += 1;
    this.more.hidden = true;
    this.timer = setTimeout(() => this.load(true), debounce ? 250 : 0);
  },

  async load(reset) {
    const route = this.route, revision = this.revision;
    if (!this.current(route, revision) || (!reset && this.more.disabled)) return;
    this.more.disabled = true;
    this.retry.hidden = true;
    this.status.textContent = App.t("playlist.loading");
    try {
      const page = reset ? 0 : this.page;
      const data = await App.api.get("/api/playlists/page", {page, q: this.search.value, sort: this.sort.value});
      if (!this.current(route, revision)) return;
      if (!this.sort.options.length) for (const sort of data.sorts) {
        this.sort.appendChild(App.el("option", {value: sort, text: App.t("playlist.sort_" + sort)}));
      }
      this.sort.value = data.sort;
      if (reset) { this.cards.clear(); App.clear(this.grid); }
      for (const item of data.playlists) {
        if (this.cards.has(item.id)) continue;
        const card = new PlaylistCard(item);
        this.cards.set(item.id, card);
        this.grid.appendChild(card.root);
      }
      this.page = page + 1;
      this.more.hidden = !data.hasMore;
      this.status.textContent = this.cards.size ? "" : App.t("playlist.no_results");
    } catch (error) {
      if (this.current(route, revision)) {
        this.failedReset = reset;
        this.status.textContent = App.errorText(error);
        this.retry.hidden = false;
      }
    } finally { if (this.current(route, revision)) this.more.disabled = false; }
  },

  async refresh(id) {
    const route = this.route, revision = this.revision, card = this.cards.get(String(id));
    if (!card || !this.current(route, revision)) return;
    const request = card.request = (card.request || 0) + 1;
    try {
      const detail = await App.api.get("/api/playlist", {id});
      if (!this.current(route, revision) || card.request !== request || this.cards.get(String(id)) !== card) return;
      card.update(detail);
    } catch (error) { if (this.current(route, revision)) App.toast(App.errorText(error), "error"); }
  },

  reconcile(items) {
    if (!this.current(this.route)) return;
    const present = new Map(items.map(item => [String(item.id), item]));
    for (const [id, card] of this.cards) {
      const item = present.get(id);
      if (!item) { card.root.remove(); this.cards.delete(id); continue; }
      if (["name", "songCount", "community", "canAdd"].some(key => item[key] !== card.data[key])) this.refresh(id);
    }
    if (!this.cards.size) this.status.textContent = App.t("playlist.no_results");
  },

  destroy() {
    clearTimeout(this.timer);
    if (this.offChanged) this.offChanged();
    if (this.offLists) this.offLists();
    this.offChanged = this.offLists = null;
    this.route = null;
  },
};
