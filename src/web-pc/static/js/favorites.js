"use strict";
/* Portraits chargés seulement à l'approche de l'écran, par une file propre à la visite du compte. */
class FavoriteArtistPortraits {
  constructor(container, current) {
    this.container = container;
    this.isCurrent = current;
    this.alive = true;
    this.pending = [];
    this.entries = new Map();
    if (window.IntersectionObserver) {
      this.observer = new IntersectionObserver(entries => {
        for (const entry of entries) if (entry.isIntersecting) this.enqueue(entry.target);
      }, {root: container.closest("main"), rootMargin: "160px"});
    }
  }

  current() { return this.alive && this.isCurrent(); }

  append(artist) {
    const el = App.el;
    const initials = String(artist.name || "?").trim().split(/\s+/).slice(0, 2)
      .map(word => [...word][0] || "").join("").toLocaleUpperCase("fr");
    const fallback = el("span.favorite-artist-initials", {text: initials, "aria-hidden": "true"});
    const portrait = el("span.favorite-artist-portrait", {"aria-hidden": "true"}, fallback);
    const node = el("a.favorite-artist", {href: "#/artist/" + encodeURIComponent(artist.id)},
      portrait, el("span.favorite-artist-name", {text: artist.name}));
    this.container.appendChild(node);
    this.entries.set(node, {artist, portrait, fallback, node});
    if (this.observer) this.observer.observe(node); else this.enqueue(node);
  }

  enqueue(node) {
    const entry = this.entries.get(node);
    if (!entry || !this.current()) return;
    this.entries.delete(node);
    if (this.observer) this.observer.unobserve(node);
    this.pending.push(entry);
    this.drain();
  }

  async drain() {
    if (this.loading || !this.current()) return;
    this.loading = true;
    while (this.pending.length && this.current()) {
      const entry = this.pending.shift();
      try {
        const data = await App.api.get("/api/artist/image", {id: entry.artist.id});
        if (!this.current() || !entry.node.isConnected || !data.imageUrl) continue;
        const image = App.el("img", {src: data.imageUrl, alt: "", loading: "lazy", width: 112, height: 112,
          referrerPolicy: "no-referrer", onload: () => { entry.fallback.hidden = true; },
          onerror: () => { image.remove(); entry.fallback.hidden = false; }});
        entry.portrait.appendChild(image);
      } catch (error) { /* Les initiales restent disponibles si le portrait ne répond pas. */ }
    }
    this.loading = false;
  }

  destroy() {
    this.alive = false;
    this.pending = [];
    this.entries.clear();
    if (this.observer) this.observer.disconnect();
  }
}

/* Favoris du compte : chaque catégorie charge sa suite sous son contenu, sans reconstruire ses voisines. */
const FavoritesView = {
  current(route, owner) {
    return this.route === route && !route.stale && App.user && App.user.id === owner;
  },

  async render(main, route) {
    this.destroy();
    this.route = route;
    const owner = App.user.id;
    this.owner = owner;
    this.tables = [];
    App.clear(main).appendChild(App.el("div.loading", {text: "…"}));
    try {
      const data = await App.api.get("/api/starred", {page: 0});
      if (!this.current(route, owner)) return;
      this.layout(main, route, owner);
      this.append(data);
    } catch (error) {
      if (this.current(route, owner)) App.clear(main).appendChild(App.el("p.page-error", {text: App.errorText(error)}));
    }
  },

  layout(main, route, owner) {
    const el = App.el;
    App.clear(main).appendChild(el("h1", {text: App.t("nav.favorites")}));
    this.artists = el("div.favorite-artists");
    this.portraits = new FavoriteArtistPortraits(this.artists, () => this.current(route, owner));
    this.albums = Views.albumGrid([]);
    App.clear(this.albums);
    this.songs = el("div");
    this.sections = el("div.favorites-library");
    this.groups = {};
    for (const [kind, content] of [["artists", this.artists], ["albums", this.albums], ["songs", this.songs]]) {
      const count = el("span.favorites-count.muted", {"aria-live": "polite"});
      const more = el("button.button.favorites-more", {type: "button", text: App.t("albums.more"),
        onclick: () => this.loadMore(route, kind), dataset: {kind}});
      const section = el("section.favorites-section", {hidden: true, dataset: {kind}},
        Views.heading(App.t("search." + kind)), content, el("div.favorites-pagination", {}, count, more));
      this.groups[kind] = {section, content, count, more, page: 0, shown: 0};
      this.sections.appendChild(section);
    }
    App.append(main, [this.sections, ExtMusic.favoritesSection(route)]);
  },

  append(data, kinds = Object.keys(this.groups)) {
    for (const kind of kinds) {
      const group = this.groups[kind], items = data[kind];
      if (kind === "artists") for (const artist of items) this.portraits.append(artist);
      else if (kind === "albums" && items.length) group.content.append(...Views.albumGrid(items).childNodes);
      else if (kind === "songs" && items.length) {
        const table = Views.songTable(items, {showAlbum: true});
        this.tables.push(table);
        group.content.appendChild(table);
      }
      group.shown += items.length;
      const pagination = data.pagination && data.pagination[kind];
      group.section.hidden = !group.shown;
      group.more.hidden = pagination ? !pagination.hasMore : !data.hasMore;
      group.count.textContent = App.t("favorites.count", {shown: group.shown, total: pagination ? pagination.total : group.shown});
    }
  },

  async loadMore(route, kind) {
    const group = this.groups[kind], owner = this.owner;
    if (group.more.disabled) return;
    group.more.disabled = true;
    try {
      const data = await App.api.get("/api/starred", {page: group.page + 1});
      if (!this.current(route, owner)) return;
      this.append(data, [kind]);
      group.page += 1;
    } catch (error) {
      if (this.current(route, owner)) App.toast(App.errorText(error), "error");
    } finally {
      if (this.current(route, owner)) group.more.disabled = false;
    }
  },

  destroy() {
    if (this.portraits) this.portraits.destroy();
    for (const table of this.tables || []) if (table.destroy) table.destroy();
    this.tables = [];
    this.route = null;
  },
};
