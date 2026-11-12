"use strict";
/* Crédits Discogs et liens de musiciens : source et édition explicites, sans confondre avec MusicBrainz. */
const DiscogsCredits = (() => {
  const el = App.el, t = key => App.t("discovery." + key);
  const link = person => el("a.discogs-person", {
    href: "#/discogs/artist/" + encodeURIComponent(person.id), text: person.name,
    dataset: {initials: person.name.trim().split(/\s+/).slice(0, 2).map(word => [...word][0] || "").join("").toLocaleUpperCase("fr")}});

  function people(credits) {
    return el("ul.explore-people.explore-member-cards", {}, credits.map(person => el("li.explore-member-card", {},
      link(person), person.role ? el("span.muted", {text: person.role === "artist" ? App.t("explore.roles.artist") : person.role}) : null,
      person.tracks ? el("span.muted", {text: App.t("discovery.credit_tracks", {tracks: person.tracks})}) : null)));
  }

  function connections(data) {
    const members = data.members || [], groups = data.groups || [];
    return el("section.discogs-connections", {},
      el("p.muted", {text: t("discogs_relations_help")}),
      members.length ? el("div", {}, Views.heading(t("members")), people(members)) : null,
      groups.length ? el("div", {}, Views.heading(t("groups")), people(groups)) : null,
      !members.length && !groups.length ? el("p.muted", {text: t("no_relations")}) : null);
  }

  async function loadConnections(root, identity, route) {
    root.dataset.identity = identity;
    root.textContent = t("loading");
    try {
      const data = await App.api.get("/api/discogs/identity", {kind: "artist", id: identity});
      if (route.stale || root.dataset.identity !== identity) return;
      App.append(App.clear(root), [connections(data)]);
    } catch (failure) {
      if (!route.stale && root.dataset.identity === identity) DiscogsUI.error(root, failure, () => loadConnections(root, identity, route));
    }
  }

  class Album {
    constructor(identity, route) {
      this.identity = identity;
      this.route = route;
      this.generation = 0;
      this.body = el("div.discogs-credits-body");
      this.labels = PageSections.section("album-labels", ".discogs-album-labels");
      this.labelsBody = el("div");
      App.append(this.labels, [Views.heading(App.t("explore.labels")), this.labelsBody]);
      this.root = el("section.album-exploration.discogs-credits", {id: "album-discogs", tabIndex: -1},
        el("div.section-head", {}, el("h2", {}, App.icon("discogs", 20), " ", t("album_credits"))),
        el("p.muted", {text: t("credits_help")}), this.body, this.labels);
      this.labelsBody.textContent = t("labels_choose");
      this.body.appendChild(DiscogsUI.button(t("open_credits"), "discogs", () => this.open(), ".discogs-credits-open"));
      this.loaded = false;
    }

    open() { if (!this.loaded) { this.loaded = true; this.load(); } }

    async load(release = "") {
      const generation = ++this.generation;
      this.body.textContent = t("loading");
      try {
        const data = await App.api.get("/api/discogs/album", {id: this.identity, release});
        if (this.route.stale || generation !== this.generation) return;
        this.show(data);
      } catch (failure) {
        if (!this.route.stale && generation === this.generation) DiscogsUI.error(this.body, failure, () => this.load(release));
      }
    }

    show(data) {
      App.clear(this.body);
      this.labelsBody.textContent = t("labels_choose");
      if (!data.editions.length) { this.body.textContent = t("no_editions"); return; }
      const select = el("select.discogs-edition", {onchange: () => this.load(select.value)},
        el("option", {value: "", text: App.t("explore.choose")}), data.editions.map(edition => el("option", {
          value: edition.id, selected: data.selected === edition.id,
          text: [edition.title, edition.year, edition.format, "#" + edition.id].filter(Boolean).join(" · ")})));
      this.body.appendChild(el("label.explore-picker", {}, el("span", {text: App.t("explore.edition")}), select));
      if (!data.selected) return;
      App.append(App.clear(this.labelsBody), data.labels.map(label => el("a.chip.discogs-label", {
        href: "#/discogs/label/" + encodeURIComponent(label.id), text: label.name})));
      App.append(this.body, [DiscogsUI.source("release", data.selected),
        Views.heading(App.t("explore.credits")), people(data.people), el("p.muted", {text: t("credits_incomplete")})]);
    }
  }

  return {connections, loadConnections, Album, panel: (identity, route) => new Album(identity, route).root};
})();
