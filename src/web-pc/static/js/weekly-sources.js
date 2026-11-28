"use strict";

/* Panneau « Mes sources » du radar : ce que la personne suit (styles, labels, artistes), d'où ça vient,
   retrait d'une source, ajout par le catalogue des styles ou par une recherche MusicBrainz.
   onChange recharge la grille de la page ; le panneau, lui, se met à jour sur place. */
const WeeklySources = (() => {
  const el = App.el;
  const t = (key, values) => App.t("weekly." + key, values);
  const STYLE = "style";             // un style s'ajoute par le catalogue, sans recherche
  const API = "/api/news/releases";

  class SourcesPanel {
    constructor(onChange, onClose) {
      this.onChange = onChange;
      this.onClose = onClose;
      this.box = el("section.weekly-sources", {"aria-label": t("sources")});
      this.lists = {};
      this.genres = [];
    }

    async open(container) {
      container.appendChild(this.box);
      this.box.textContent = t("loading");
      try {
        const [settings, catalog] = await Promise.all([App.api.get(API + "/sources"), App.api.get(API + "/genres")]);
        this.genres = catalog.genres.map(genre => genre.name);
        this.draw(settings);
      } catch (error) {
        App.clear(this.box).appendChild(el("p.page-error", {text: App.errorText(error)}));
      }
    }

    close() { this.box.remove(); }

    draw(settings) {
      App.clear(this.box);
      this.box.appendChild(el("div.weekly-sources-heading", {}, el("h2", {text: t("sources_title")}),
        this.onClose ? el("button.link-button", {type: "button", text: t("sources_close"), onclick: this.onClose}) : null));
      if (settings.basis === "site") this.box.appendChild(el("p.muted", {text: t("basis_site")}));
      for (const kind of settings.kinds) {
        this.lists[kind] = el("ul.weekly-source-list");
        App.append(this.box, [el("h3", {text: t("kind_" + kind)}), this.lists[kind]]);
      }
      for (const source of settings.sources) this.addRow(source);
      this.box.appendChild(this.addForm(settings.addable));
      this.status = el("p.muted", {"aria-live": "polite"});
      this.box.appendChild(this.status);
    }

    addRow(source) {
      const list = this.lists[source.kind];
      if (!list || list.querySelector('[data-source="' + source.id + '"]')) return;
      const origin = t(source.origin === "trends" ? "origin_trends" : "origin_manual");
      const hide = el("button.icon", {type: "button", text: "×", title: t("hide", {name: source.name}),
                                      "aria-label": t("hide", {name: source.name}), onclick: () => this.hide(source)});
      list.appendChild(el("li", {"data-source": String(source.id)}, el("span", {text: source.name}),
        el("span.muted", {text: origin}), hide));
    }

    async hide(source) {
      try {
        await App.api.post(API + "/sources/hide", {id: source.id});
        const row = this.box.querySelector('[data-source="' + source.id + '"]');
        if (row) row.remove();
        this.onChange();
      } catch (error) { App.toast(App.errorText(error), "error"); }
    }

    addForm(addable) {
      this.kind = el("select", {"aria-label": t("add_kind")},
        ...addable.map(kind => el("option", {value: kind, text: t("kind_" + kind)})));
      this.query = el("input", {type: "search", list: "weekly-source-genres", "aria-label": t("add_query")});
      this.results = el("div.weekly-search-results");
      const options = el("datalist", {id: "weekly-source-genres"}, ...this.genres.map(name => el("option", {value: name})));
      this.kind.addEventListener("change", () => this.kindChanged());
      this.kindChanged();
      const form = el("form.chips", {}, this.kind, this.query, options, el("button", {type: "submit", text: t("add")}));
      form.addEventListener("submit", event => { event.preventDefault(); this.submit(); });
      return el("div.weekly-add", {}, el("h3", {text: t("add_title")}), form, this.results);
    }

    kindChanged() {
      const style = this.kind.value === STYLE;
      this.query.setAttribute("placeholder", t(style ? "add_style" : "add_search"));
      if (style) this.query.setAttribute("list", "weekly-source-genres"); else this.query.removeAttribute("list");
      App.clear(this.results);
    }

    async submit() {
      const kind = this.kind.value, query = this.query.value.trim();
      if (!query) return;
      if (kind === STYLE) {
        const name = this.genres.find(genre => genre.toLowerCase() === query.toLowerCase());
        if (name) this.add(kind, name, name); else this.status.textContent = t("unknown_style");
        return;
      }
      App.clear(this.results).textContent = t("loading");
      try {
        const found = await App.api.get(API + "/search", {kind, q: query});
        App.clear(this.results);
        if (!found.results.length) { this.results.textContent = t("no_result"); return; }
        App.append(this.results, found.results.map(item => el("button.chip", {type: "button",
          text: [item.name, item.country, item.description].filter(Boolean).join(" · "),
          onclick: () => this.add(kind, item.id, item.name)})));
      } catch (error) { App.clear(this.results).textContent = App.errorText(error); }
    }

    async add(kind, identity, name) {
      try {
        const source = await App.api.post(API + "/sources/add", {kind, identity, name});
        this.addRow(source);
        App.clear(this.results);
        this.query.value = "";
        this.status.textContent = t("syncing", {name});
        this.onChange();
        // la recherche des sorties de cette source se fait sur le serveur : un seul rechargement, quelques secondes après
        setTimeout(() => { if (this.box.isConnected) this.onChange(); }, 5000);
      } catch (error) { App.toast(App.errorText(error), "error"); }
    }
  }

  return {panel: (onChange, onClose) => new SourcesPanel(onChange, onClose)};
})();
