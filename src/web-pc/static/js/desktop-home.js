"use strict";
/* Accueil ordinateur : cartes et sources existantes, une rangée par thème. */
const DesktopHome = (() => {
  let page = null;

  class HomePage {
    constructor(main, route) {
      this.route = route;
      this.alive = true;
      this.owner = App.user.id;
      this.rails = [];
      this.resume = new HomeResume(route);
      this.root = App.el("div.desktop-home", {}, this.resume.root);
      App.clear(main).append(this.root);
    }

    current() { return this.alive && !this.route.stale && this.root.isConnected && App.user && App.user.id === this.owner; }

    rail(title, options) {
      const rail = new AlbumRail(title, options);
      this.rails.push(rail);
      this.root.append(rail.root);
      return rail;
    }

    albumNodes(albums) { return albums.length ? Array.from(Views.albumGrid(albums).children) : []; }

    async load(rail, request, show) {
      rail.empty(App.t("home.loading"));
      try {
        const data = await request();
        if (this.current()) show(data);
      } catch (error) {
        if (this.current()) { rail.root.hidden = false; rail.error(error, () => this.load(rail, request, show)); }
      }
    }

    start() {
      this.recommendations();
      this.personal();
      this.releases();
      this.newest();
      return this.root;
    }

    recommendations() {
      const rail = this.rail(App.t("home.recommendations"), {href: "#/listen-later", className: ".home-received"});
      rail.root.hidden = true;
      const show = data => {
        rail.root.hidden = !data.recommendations.length;
        rail.track.replaceChildren(...data.recommendations.map(group => ListenLaterUI.preview(group)));
        rail.status.textContent = "";
        rail.update();
      };
      this.load(rail, () => ListenLaterUI.load(), show);
      this.offRecommendations = App.live.on("recommendations", () => {
        if (this.current()) this.load(rail, () => ListenLaterUI.load(true), show);
      });
    }

    personal() {
      const recent = this.rail(App.t("home.personal_recent"), {className: ".home-recent"});
      const suggested = this.rail(App.t("home.for_you"), {className: ".home-suggestions"});
      suggested.root.hidden = true;
      const seen = new Set();
      const show = (data, first) => {
        const albums = data.recent.filter(album => !seen.has(album.id) && seen.add(album.id));
        recent.append(this.albumNodes(albums));
        if (!seen.size) recent.empty(App.t("home.no_recent"));
        recent.more(data.nextBefore === null ? null : async () => {
          const next = await App.api.get("/api/home/personal", {before: data.nextBefore});
          if (this.current()) show(next, false);
        });
        if (!first) return;
        const key = data.basis === "favorites" ? "home.from_favorites" : "home.because";
        if (data.seed) suggested.root.querySelector("h2").textContent = App.t(key, {artist: data.seed.artist});
        suggested.append(this.albumNodes(data.suggestions));
        suggested.root.hidden = !data.suggestions.length;
      };
      this.load(recent, () => App.api.get("/api/home/personal"), data => show(data, true));
    }

    releases() {
      const rail = this.rail(App.t("weekly.title"), {href: "#/news/releases", className: ".home-releases"});
      const monday = WeeklyReleaseView.mondayFor(new Date());
      const seen = new Set();
      const show = data => {
        const cards = data.cards.filter(card => !seen.has(card.id) && seen.add(card.id));
        rail.append(cards.map(card => WeeklyRadar.card(card)));
        if (!seen.size) rail.empty(App.t(data.empty === "no-sources" ? "weekly.no_sources" : "weekly.radar_empty"));
        rail.more(data.next == null ? null : async () => {
          const next = await WeeklyRadar.read(monday, "all", data.next);
          if (this.current()) show(next);
        });
      };
      this.load(rail, () => WeeklyRadar.read(monday), show);
    }

    newest() {
      const rail = this.rail(App.t("home.newest"), {href: "#/albums/newest", className: ".home-newest"});
      this.load(rail, () => App.api.get("/api/home"), data => {
        rail.append(this.albumNodes(data.newest));
        if (!data.newest.length) rail.empty(App.t("home.empty"));
      });
    }

    destroy() {
      this.alive = false;
      this.resume.destroy();
      this.rails.forEach(rail => rail.destroy());
      if (this.offRecommendations) this.offRecommendations();
    }
  }

  function destroy() { if (page) page.destroy(); page = null; }
  function render(main, route) { destroy(); page = new HomePage(main, route); return page.start(); }
  return {render, destroy};
})();
