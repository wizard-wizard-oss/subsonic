"use strict";
/* Identités et discographies Discogs : composants communs aux pages artiste et label. */
const DiscogsUI = (() => {
  const el = App.el, t = key => App.t("discovery." + key);
  const source = (kind, id, text) => el("a.discogs-source", {href: "https://www.discogs.com/" + kind + "/" + id,
    target: "_blank", rel: "noopener noreferrer", text: text || t("discogs")});
  const button = (text, icon, onclick, cls) => App.setIcon(el("button" + (cls || ""),
    {type: "button", onclick}), icon, 18, false, text);

  function error(root, failure, retry) {
    App.append(App.clear(root), [el("p.page-error", {role: "status", text: App.errorText(failure)}),
      button(t("retry"), "undo", retry, ".link-button")]);
  }

  function picker(name, kind, route, choose) {
    const results = el("div.discogs-identities"), status = el("p.muted", {role: "status"});
    const input = el("input.discogs-query", {type: "search", value: name, maxLength: 300,
      "aria-label": t("identity_" + kind), required: true});
    const submit = el("button", {type: "submit", text: t("find_identity")});
    let generation = 0;
    const form = el("form.discogs-search", {onsubmit: async event => {
      event.preventDefault();
      const current = ++generation;
      submit.disabled = true;
      status.textContent = t("loading");
      try {
        const data = await App.api.get("/api/discogs/search", {name: input.value, kind});
        if (route.stale || current !== generation) return;
        status.textContent = t(data.identities.length ? "choose_identity" : "no_identity");
        App.append(App.clear(results), data.identities.map(identity => identityChoice(identity, results, choose)));
        if (data.more) status.textContent += " " + t("refine_identity");
      } catch (failure) { if (!route.stale && current === generation) status.textContent = App.errorText(failure); }
      finally { submit.disabled = false; }
    }}, el("label", {}, el("span.sr-only", {text: t("identity_" + kind)}), input), submit);
    return el("div.discogs-picker", {}, form, status, results);
  }

  function identityChoice(identity, results, choose) {
    const pick = el("button.chip.discogs-identity", {type: "button", "aria-pressed": "false", onclick: () => {
      results.querySelectorAll(".discogs-identity").forEach(node => {
        node.classList.toggle("on", node === pick);
        node.setAttribute("aria-pressed", String(node === pick));
      });
      choose(identity);
    }}, App.icon("disc", 18), el("strong", {text: identity.name}), el("span.muted", {text: "#" + identity.id}));
    return el("div.discogs-identity-choice", {}, pick, source(identity.kind, identity.id));
  }

  function card(album, extra) {
    const edition = album.editions[0];
    return el("article.album-card.discogs-album", {dataset: {album: album.id}}, el("a.album-link", {
      href: "https://www.discogs.com/release/" + edition, target: "_blank", rel: "noopener noreferrer"},
      App.cover(album.image, 180, album.title), el("strong.album-name", {text: album.title}),
      el("span.album-artist", {text: album.artist}), el("span.album-year", {
        text: [album.year || t("unknown_year"), album.format].filter(Boolean).join(" · ")})),
      ListenLaterUI.actions({kind: "album", source: "discogs", sourceId: String(edition)}), extra || null);
  }

  class Discography {
    constructor(root, route, onIdentity) {
      this.root = root;
      this.route = route;
      this.generation = 0;
      this.local = new Map();
      this.onIdentity = onIdentity;
    }

    async load(identity, page = 1, artistId = "") {
      const generation = ++this.generation;
      const loading = el("p.muted", {role: "status", text: t("loading")});
      this.root.appendChild(loading);
      try {
        const data = artistId ? await App.api.post("/api/discogs/artist-refresh", {artistId})
          : await App.api.get("/api/discogs/catalog", {kind: "artist", id: identity.id, page});
        if (this.route.stale || generation !== this.generation) return;
        this.show(data, generation);
      } catch (failure) {
        if (!this.route.stale && generation === this.generation) error(loading, failure, () => this.load(identity, page, artistId));
      }
    }

    show(data, generation) {
      if (this.onIdentity) this.onIdentity(data.identity);
      const groups = [data.albums.filter(a => a.role === "Main"), data.albums.filter(a => a.role !== "Main")];
      const cards = [];
      App.append(App.clear(this.root), [
        el("div.section-head", {}, el("h3", {text: data.identity.name}), source("artist", data.identity.id)),
        el("p.muted", {text: App.t("discovery.catalog_scope", {count: data.albums.length, total: data.total})}),
        el("p.muted", {text: t("catalog_help")}),
        ...groups.flatMap((albums, i) => albums.length ? [Views.heading(t(i ? "appearances" : "releases")),
          el("div.album-grid.discogs-grid", {}, albums.map(album => this.album(album, cards)))] : []),
        !data.albums.length ? el("p.muted", {text: t("empty")}) : null,
        !data.complete ? button(t("more"), "plus", () => this.load(data.identity, data.page + 1), ".discogs-more") : null]);
      this.markLocal(cards, generation);
    }

    album(album, cards) {
      const badge = el("div.discography-local.muted", {text: t("checking")});
      const node = card(album, badge);
      cards.push({album, badge});
      return node;
    }

    async markLocal(cards, generation) {
      for (let start = 0; start < cards.length; start += 3) {
        if (this.route.stale || generation !== this.generation) return;
        await Promise.all(cards.slice(start, start + 3).map(item => this.localAlbum(item, generation)));
      }
    }

    async localAlbum({album, badge}, generation) {
      try {
        let data = this.local.get(album.id);
        if (!data) data = await App.api.get("/api/explore/local", {title: album.title, artist: album.artist});
        if (this.route.stale || generation !== this.generation) return;
        this.local.set(album.id, data);
        App.clear(badge);
        if (data.albums.length) App.append(badge, data.albums.map(local => el("a.chip.discography-owned", {
          href: "#/album/" + encodeURIComponent(local.id)}, App.icon("disc", 14), t("in_library"))));
        else badge.appendChild(el("a", {href: "#/search/" + encodeURIComponent(album.artist + " " + album.title),
          text: t("find_record")}));
      } catch (failure) { if (!this.route.stale) badge.textContent = App.errorText(failure); }
    }
  }

  function externalArtistPanel(name, route) {
    const body = el("div.discography-body"), results = el("div.discography-results");
    const relations = el("div.discography-relations"), catalog = new Discography(results, route);
    const open = button(t("open_discography"), "discogs", () => {
      open.hidden = true;
      App.append(body, [picker(name, "artist", route, identity => {
        App.clear(results);
        catalog.load(identity);
        DiscogsCredits.loadConnections(relations, identity.id, route);
      }), results, relations]);
    }, ".discography-open");
    return el("section.discography.artist-discography", {}, Views.heading(t("discography")), open, body);
  }

  Views.discogs = {
    async render(main, route) {
      main.textContent = t("loading");
      try {
        const data = await App.api.get("/api/discogs/identity", {kind: route.kind, id: route.id});
        if (route.stale) return;
        const catalog = el("div.discography-results");
        App.append(App.clear(main), [el("h1", {text: data.name}), source(data.kind, data.id),
          data.kind === "artist" ? ListenLaterUI.actions({kind: "artist", source: "discogs", sourceId: data.id}) : null,
          data.kind === "label" ? LabelDiscoveryUI.panel(data.name, route, data) : DiscogsCredits.connections(data),
          data.kind === "artist" ? catalog : null]);
        if (data.kind === "artist") new Discography(catalog, route).load(data);
      } catch (failure) { if (!route.stale) error(main, failure, () => this.render(main, route)); }
    },
  };

  return {source, button, error, picker, card, Discography, externalArtistPanel};
})();
