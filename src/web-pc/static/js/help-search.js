"use strict";
/* Help : recherche locale dans les guides. Elle ne lit que les textes déjà chargés : aucune requête, aucune écriture. */

const HelpSearch = (() => {
  const el = App.el, t = App.t;
  const MAX_RESULTS = 8;

  /** Sans accent ni casse, « œ » compris : « coeur » retrouve « Cœurs ». */
  const fold = text => text.normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/œ/g, "oe").toLowerCase();

  /** Une entrée par guide : le titre est cherché en priorité, puis les étapes et la précision. */
  function entry(theme, guide, key, themeTitle) {
    const title = t(key + ".title");
    const body = [].concat(App.texts[key + ".steps"] || [], App.texts[key + ".note"] || []).join(" ");
    return {theme, guide, title, themeTitle, foldedTitle: fold(title), haystack: fold([title, themeTitle, body].join(" "))};
  }

  function matches(entries, query) {
    const words = fold(query).split(/\s+/).filter(Boolean);
    if (!words.length) return [];
    const found = entries.filter(item => words.every(word => item.haystack.includes(word)));
    const inTitle = item => words.every(word => item.foldedTitle.includes(word));
    return found.sort((a, b) => inTitle(b) - inTitle(a)).slice(0, MAX_RESULTS);
  }

  /* Le champ et sa liste de résultats : seule la liste est redessinée à chaque saisie. */
  class Search {
    constructor(entries, onPick) {
      this.entries = entries;
      this.onPick = onPick;
      this.input = el("input.help-search-input", {id: "help-search", type: "search", autocomplete: "off",
        placeholder: t("whatsnew.search_placeholder"), oninput: () => this.update()});
      this.results = el("div.help-search-results", {"aria-live": "polite"});
      this.element = el("div.help-search", {},
        el("label.help-search-label", {for: "help-search", text: t("whatsnew.search_label")}),
        this.input, this.results);
    }

    result(item) {
      return el("button.help-search-result", {type: "button", dataset: {theme: item.theme, guide: item.guide},
        onclick: () => this.onPick(item.theme, item.guide)},
        el("span.help-search-title", {text: item.title}), el("span.help-search-theme", {text: item.themeTitle}));
    }

    update() {
      App.clear(this.results);
      if (!this.input.value.trim()) return;
      const found = matches(this.entries, this.input.value);
      if (!found.length) this.results.appendChild(el("p.help-search-empty", {text: t("whatsnew.search_empty")}));
      for (const item of found) this.results.appendChild(this.result(item));
    }
  }

  const create = (entries, onPick) => new Search(entries, onPick).element;

  return {create, entry, matches, fold};
})();
