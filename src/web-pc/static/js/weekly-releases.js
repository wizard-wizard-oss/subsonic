"use strict";

/* Consultation « un style à la fois » : semaines hors de la période synchronisée du radar (weekly-radar.js).
   Une instance par visite. Les réponses d'une semaine précédente ne remplacent jamais la sélection. */
const WeeklyReleaseView = (() => {
  const el = App.el;
  const t = key => App.t("weekly." + key);
  const iso = date => date.toISOString().slice(0, 10);
  const display = date => new Intl.DateTimeFormat("fr-FR", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  }).format(date);
  const shift = (date, days) => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days));

  function mondayFor(now) {
    const day = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
    return shift(day, -((day.getUTCDay() + 6) % 7));
  }

  /* Une page « sorties de la semaine » : style choisi, semaine affichée et pages déjà chargées. */
  class WeekPage {
    constructor(main, route, options = {}) {
      this.main = main;
      this.route = route;
      this.back = options.back;
      this.monday = options.monday || mondayFor(new Date());
      this.genres = []; this.followed = new Set(); this.selected = null; this.generation = 0; this.saving = false;
      this.input = el("input", {type: "search", list: "weekly-genres", placeholder: t("style"), "aria-label": t("style")});
      this.options = el("datalist", {id: "weekly-genres"});
      this.week = WeeklyWeek.create(this.monday, monday => { this.monday = monday; this.reload(); });
      this.results = el("div", {"aria-live": "polite"});
      this.follows = el("div.chips");
      this.follow = el("button.primary", {type: "button", disabled: true, onclick: () => this.toggleFollow(), text: t("follow")});
      this.input.addEventListener("input", () => this.typed());
    }

    button(label, action) {
      return el("button", {type: "button", text: t(label), onclick: action});
    }

    layout() {
      const week = el("div.weekly-browse-navigation", {}, this.week.node,
        this.back ? this.button("back_to_radar", this.back) : null);
      const sidebar = el("aside.weekly-followed", {}, el("h2", {text: t("followed")}), this.follows,
        el("a", {href: "#/whatsnew/press/g5", text: t("guide")}));
      App.append(App.clear(this.main), [News.tabs(true),
        el("header.weekly-heading", {}, el("h1", {text: t("title")}), week),
        el("div.chips.weekly-filters", {}, this.input, this.options, this.follow),
        el("div.weekly-layout", {}, this.results, sidebar)]);
      this.showRange();
    }

    showRange() {
      this.week.update(this.monday);
    }

    async start() {
      this.layout();
      this.results.textContent = t("loading");
      try {
        const data = await App.api.get("/api/news/releases/genres");
        if (this.route.stale) return;
        this.genres = data.genres;
        this.followed = new Set(data.followed);
        App.append(this.options, this.genres.map(genre => el("option", {value: genre.name})));
        const initial = this.genres.find(g => this.followed.has(g.name)) || this.genres.find(g => g.name === data.default);
        if (initial) this.choose(initial);
        else { this.updateControls(); this.reload(); }
      } catch (error) {
        if (!this.route.stale) this.errorState(this.results, error, () => this.start());
      }
    }

    updateControls() {
      this.follow.disabled = !this.selected || this.saving;
      this.follow.textContent = t(this.selected && this.followed.has(this.selected.name) ? "unfollow" : "follow");
      App.clear(this.follows);
      for (const genre of this.genres.filter(item => this.followed.has(item.name))) {
        this.follows.appendChild(el("button.chip", {type: "button", text: genre.name, onclick: () => this.choose(genre)}));
      }
      if (!this.follows.firstChild) this.follows.appendChild(el("span.muted", {text: t("none")}));
    }

    async toggleFollow() {
      if (!this.selected || this.saving) return;
      const name = this.selected.name, enabled = !this.followed.has(name);
      this.saving = true;
      this.updateControls();
      try {
        await App.api.post("/api/news/releases/follow", {genre: name, enabled});
        if (enabled) this.followed.add(name); else this.followed.delete(name);
      } catch (error) { if (!this.route.stale) App.toast(App.errorText(error), "error"); }
      finally { this.saving = false; if (!this.route.stale) this.updateControls(); }
    }

    choose(genre) {
      this.input.value = genre.name;
      this.selected = genre;
      this.updateControls();
      this.reload();
    }

    typed() {
      const name = this.input.value.trim().toLowerCase();
      const genre = this.genres.find(item => item.name.toLowerCase() === name);
      if (genre) this.choose(genre);
      else if (this.selected) { this.selected = null; this.updateControls(); this.reload(); }
    }

    reload() {
      const version = ++this.generation;
      this.showRange();
      App.clear(this.results);
      if (!this.selected) { this.results.textContent = t("choose"); return; }
      const listing = {version, grid: el("div.weekly-grid"), status: el("div.muted", {text: t("loading")}), ids: new Set()};
      App.append(this.results, [listing.grid, listing.status]);
      this.page(listing, 0);
    }

    async page(listing, offset) {
      const {version, grid, status, ids} = listing, active = () => !this.route.stale && version === this.generation;
      App.clear(status).textContent = t("loading");
      try {
        const data = await App.api.get("/api/news/releases", {genre: this.selected.name, monday: iso(this.monday), offset});
        if (!active()) return;
        App.clear(status);
        const cards = data.albums.filter(album => !ids.has(album.id) && ids.add(album.id)).map(album => card(album, grid));
        markLocal(cards, active);
        if (data.stale) status.appendChild(el("p", {text: t("stale")}));
        if (data.next !== null) status.appendChild(el("button", {
          type: "button", text: App.t("news.more"), onclick: () => this.page(listing, data.next)}));
        else if (!ids.size) status.appendChild(el("p", {text: t("empty")}));
      } catch (error) {
        if (active()) this.errorState(status, error, () => this.page(listing, offset));
      }
    }

    errorState(box, error, retry) {
      App.append(App.clear(box), [el("p.page-error", {text: App.errorText(error)}), this.button("retry", retry)]);
    }
  }

  /* Pochette Cover Art Archive d'un groupe de sorties. Pour une sortie toute récente, archive.org n'a souvent pas encore
     fabriqué les miniatures : on charge alors l'image d'origine, et la pochette vide seulement si elle manque aussi.
     known : pochette déjà trouvée par le serveur, essayée en premier. */
  function releaseCover(id, title, known) {
    const original = "https://coverartarchive.org/release-group/" + id + "/front";
    const tries = [original + "-250", original];
    if (known) tries.unshift(known);                    // pochette exacte connue du serveur (ListenBrainz ou Last.fm)
    const image = el("img.cover", {alt: title, loading: "lazy", width: 180, height: 180, src: tries.shift()});
    image.addEventListener("error", () => {
      if (tries.length) { image.src = tries.shift(); return; }
      image.removeAttribute("src");
      image.alt = "";
      image.classList.add("empty");
    });
    return image;
  }

  function render(main, route) {
    return WeeklyRadar.render(main, route);
  }

  function browse(main, route, options) {
    return new WeekPage(main, route, options).start();
  }

  function card(album, grid) {
    const image = releaseCover(album.id, album.title);
    const cover = el("a", {href: "https://musicbrainz.org/release-group/" + album.id, target: "_blank", rel: "noopener"}, image);
    const actions = el("div.weekly-actions");
    const search = el("a.chip", {href: Views.listen.link(album.artist, album.title), text: t("listen")});
    const date = new Date(album.date + "T00:00:00Z");
    const now = new Date();
    const today = iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())));
    const label = App.t("weekly." + (album.date > today ? "upcoming" : "released"), {date: display(date)});
    App.append(actions, [search]);
    grid.appendChild(el("article.weekly-card", {}, cover, el("h3", {text: album.title}),
      el("span", {text: album.artist}), el("p.muted", {text: album.type + " · " + label}), actions));
    return {album, cover, actions};
  }

  async function markLocal(cards, active) {
    for (let i = 0; i < cards.length && active(); i += 3) {
      await Promise.all(cards.slice(i, i + 3).map(async ({album, cover, actions}) => {
        try {
          const data = await App.api.get("/api/explore/local", {title: album.title, artist: album.artist});
          if (!active() || data.albums.length !== 1) return;
          const local = data.albums[0];
          const href = "#/album/" + encodeURIComponent(local.id);
          cover.href = href;
          cover.removeAttribute("target");
          if (local.coverId) cover.replaceChildren(App.cover(local.coverId, 180, album.title));
          actions.replaceChildren(el("a.chip", {href, text: t("local")}),
            ListenLaterUI.actions({kind: "album", source: "subsonic", sourceId: local.folderId}));
        } catch (error) { /* La carte conserve sa recherche même si la bibliothèque est indisponible. */ }
      }));
    }
  }

  return {render, browse, mondayFor, shift, display, iso, releaseCover};
})();
