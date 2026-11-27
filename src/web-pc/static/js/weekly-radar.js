"use strict";

/* Radar des sorties : ce que la personne suit, lu en base par le serveur (aucun appel MusicBrainz à l'affichage).
   Pastilles de filtre en haut, grille des cartes, « ⚙ Mes sources » à part (weekly-sources.js).
   Changer de pastille ou de semaine remplace la grille seulement ; l'en-tête et les pastilles restent en place. */
const WeeklyRadar = (() => {
  const el = App.el;
  const t = (key, values) => App.t("weekly." + key, values);
  const W = WeeklyReleaseView;
  const API = "/api/news/releases";

  class RadarPage {
    constructor(main, route) {
      this.main = main;
      this.route = route;
      this.monday = W.mondayFor(new Date());
      this.filter = "all";
      this.generation = 0;
      this.panel = null;
      this.range = el("strong");
      this.updated = el("span.muted.weekly-updated");
      this.refreshButton = el("button.weekly-refresh", {type: "button", text: "↻", "aria-label": t("refresh"),
                                                        onclick: () => this.refresh()});
      this.chips = el("div.chips.weekly-chips", {role: "group", "aria-label": t("filters")});
      this.panelBox = el("div");
      this.grid = el("div.weekly-grid");
      this.status = el("div.muted", {"aria-live": "polite"});
      this.results = el("div.weekly-results", {}, this.grid, this.status);
    }

    button(label, action) {
      return el("button", {type: "button", text: t(label), onclick: action});
    }

    start() {
      const week = el("div.chips.weekly-week", {}, this.button("previous", () => this.move(-7)), this.range,
        this.button("next", () => this.move(7)), this.button("today", () => this.move(null)));
      App.append(App.clear(this.main), [News.tabs(true),
        el("header.weekly-heading", {}, el("h1", {text: t("title")}), week,
          el("div.chips", {}, this.updated, this.refreshButton)),
        el("div.weekly-toolbar", {}, this.chips, this.button("sources", () => this.toggleSources())),
        this.panelBox, this.results]);
      return this.load();
    }

    current(version) {
      return !this.route.stale && version === this.generation;
    }

    move(days) {
      this.monday = days === null ? W.mondayFor(new Date()) : W.shift(this.monday, days);
      this.load();
    }

    async load(offset = 0) {
      const version = ++this.generation;
      this.range.textContent = W.display(this.monday) + " – " + W.display(W.shift(this.monday, 6));
      if (!offset) App.clear(this.grid);
      App.clear(this.status).textContent = t("loading");
      try {
        const data = await App.api.get(API + "/radar", {monday: W.iso(this.monday), filter: this.filter, offset});
        if (this.current(version)) this.show(data, offset);
      } catch (error) {
        if (!this.current(version)) return;
        if (this.filter !== "all" && error.status === 400) { this.filter = "all"; this.load(); return; }
        App.append(App.clear(this.status), [el("p.page-error", {text: App.errorText(error)}),
                                             this.button("retry", () => this.load(offset))]);
      }
    }

    show(data, offset) {
      App.clear(this.status);
      if (data.outOfWindow) return this.message("out_of_window", "browse_style", () => this.browse());
      if (data.empty) return this.message("no_sources", "choose_sources", () => this.openSources());
      this.showChips(data.filters);
      this.showUpdate(data.updatedAt, data.refreshAfter);
      App.append(this.grid, data.cards.map(card));
      if (data.next !== null) {
        this.status.appendChild(el("button", {type: "button", text: App.t("news.more"), onclick: () => this.load(data.next)}));
      } else if (!offset && !data.cards.length) this.status.textContent = t("radar_empty");
    }

    message(text, action, onclick) {
      App.clear(this.chips);
      App.append(this.status, [el("p", {text: t(text)}), el("button.primary", {type: "button", text: t(action), onclick})]);
    }

    showChips(filters) {
      App.clear(this.chips);
      for (const filter of filters) {
        const name = filter.key === "all" ? t("filter_all") : filter.name || t("filter_" + filter.key);
        const chip = el("button.chip", {type: "button", dataset: {key: filter.key}, text: name + " (" + filter.count + ")",
          "aria-pressed": String(filter.key === this.filter), onclick: () => { this.filter = filter.key; this.load(); }});
        if (filter.key === this.filter) chip.classList.add("on");
        this.chips.appendChild(chip);
      }
    }

    showUpdate(updatedAt, refreshAfter) {
      const minutes = updatedAt ? Math.max(0, Math.round((Date.now() / 1000 - updatedAt) / 60)) : null;
      this.updated.textContent = minutes === null ? t("never_updated") : t("updated", {minutes});
      this.refreshAfter = refreshAfter;
      const waiting = refreshAfter && refreshAfter * 1000 > Date.now();
      this.refreshButton.disabled = Boolean(waiting);
      this.refreshButton.title = waiting ? t("refresh_after", {time: new Date(refreshAfter * 1000).toLocaleTimeString("fr-FR",
        {hour: "2-digit", minute: "2-digit"})}) : t("refresh");
    }

    async refresh() {
      this.refreshButton.disabled = true;
      try {
        const data = await App.api.post(API + "/refresh", {});
        this.showUpdate(null, data.refreshAfter);
        App.toast(t("refresh_started"));
        const version = this.generation;
        // la synchronisation tourne sur le serveur : un seul rechargement, un peu plus tard
        setTimeout(() => { if (this.current(version)) this.load(); }, 30000);
      } catch (error) {
        App.toast(App.errorText(error), "error");
      }
    }

    toggleSources() {
      if (this.panel) { this.panel.close(); this.panel = null; return; }
      this.openSources();
    }

    openSources() {
      if (this.panel) return;
      this.panel = WeeklySources.panel(() => this.load());
      this.panel.open(this.panelBox);
    }

    browse() {
      W.browse(this.main, this.route, {monday: this.monday, back: () => render(this.main, this.route)});
    }
  }

  function reason(source) {
    if (source.kind === "style") return source.name;
    if (source.kind === "similar") return t("reason_similar", {name: source.via || source.name});
    return t("reason_" + source.kind, {name: source.name});
  }

  function card(item) {
    const local = item.local;
    const image = local ? App.cover(local.coverId, 180, item.title)
      : App.cover(null, 180, item.title);
    if (!local) {
      image.src = "https://coverartarchive.org/release-group/" + item.id + "/front-250";
      image.classList.remove("empty");
    }
    const cover = local ? el("a", {href: "#/album/" + encodeURIComponent(local.id)}, image)
      : el("a", {href: "https://musicbrainz.org/release-group/" + item.id, target: "_blank", rel: "noopener"}, image);
    const date = new Date(item.date + "T00:00:00Z");
    const label = App.t("weekly." + (item.date > W.iso(new Date()) ? "upcoming" : "released"), {date: W.display(date)});
    return el("article.weekly-card", {}, cover, el("h3", {text: item.title}), el("span", {text: item.artist}),
      el("p.muted", {text: item.type + " · " + label}),
      el("p.weekly-reasons", {text: [...new Set(item.reasons.map(reason))].join(" · ")}), actions(item));
  }

  function actions(item) {
    if (!item.local) {
      return el("div.weekly-actions", {}, el("a.chip", {href: "#/search/" + encodeURIComponent(item.artist + " " + item.title),
                                                       text: t("listen")}));
    }
    const later = typeof ListenLaterUI === "undefined" ? null
      : ListenLaterUI.actions({kind: "album", source: "subsonic", sourceId: item.local.folderId});
    return el("div.weekly-actions", {}, el("a.chip", {href: "#/album/" + encodeURIComponent(item.local.id), text: t("local")}),
      later);
  }

  function render(main, route) {
    return new RadarPage(main, route).start();
  }

  return {render};
})();
