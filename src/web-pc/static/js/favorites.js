/* Favoris du compte : artistes, albums et titres ; la suite s'ajoute sans reconstruire la page. */
const FavoritesView = {
  async render(main, route) {
    this.destroy();
    this.route = route;
    this.page = 0;
    this.tables = [];
    App.clear(main).appendChild(App.el("div.loading", {text: "…"}));
    try {
      const data = await App.api.get("/api/starred", {page: 0});
      if (this.route !== route || route.stale) return;
      App.clear(main).appendChild(App.el("h1", {text: App.t("nav.favorites")}));
      this.artists = App.el("div.chips");
      this.albums = Views.albumGrid([]);
      App.clear(this.albums);
      this.songs = App.el("div");
      this.sections = App.el("div.favorites-library");
      for (const [key, content] of [["artists", this.artists], ["albums", this.albums], ["songs", this.songs]]) {
        const section = App.el("section", {}, Views.heading(App.t("search." + key)), content);
        section.hidden = true;
        this.sections.appendChild(section);
      }
      this.more = App.el("button.button.favorites-more", {type: "button", text: App.t("albums.more"),
        onclick: () => this.loadMore(route)});
      App.append(main, [this.sections, this.more, ExtMusic.favoritesSection(route)]);
      this.append(data);
    } catch (error) {
      if (this.route === route && !route.stale) App.clear(main).appendChild(
        App.el("p.page-error", {text: App.errorText(error)}));
    }
  },

  append(data) {
    for (const artist of data.artists) this.artists.appendChild(App.el("a.chip", {
      href: "#/artist/" + encodeURIComponent(artist.id), text: artist.name}));
    const grid = Views.albumGrid(data.albums);
    if (data.albums.length) this.albums.append(...grid.childNodes);
    if (data.songs.length) {
      const table = Views.songTable(data.songs, {showAlbum: true});
      this.tables.push(table);
      this.songs.appendChild(table);
    }
    for (const content of [this.artists, this.albums, this.songs]) {
      content.parentElement.hidden = !content.children.length;
    }
    if (!data.hasMore) this.more.remove();
  },

  async loadMore(route) {
    if (this.more.disabled) return;
    this.more.disabled = true;
    try {
      const data = await App.api.get("/api/starred", {page: this.page + 1});
      if (this.route !== route || route.stale) return;
      this.append(data);
      this.page += 1;
    } catch (error) {
      if (this.route === route && !route.stale) App.toast(App.errorText(error), "error");
    } finally {
      if (this.route === route && !route.stale) this.more.disabled = false;
    }
  },

  destroy() {
    for (const table of this.tables || []) if (table.destroy) table.destroy();
    this.tables = [];
    this.route = null;
  },
};
