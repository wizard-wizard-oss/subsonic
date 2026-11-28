"use strict";

/* Filtres repliables du radar. Un seul choix actif : origine, style, ou artistes proches d'un artiste suivi. */
const WeeklyFilters = (() => {
  const el = App.el, t = (key, values) => App.t("weekly." + key, values);

  class Filters {
    constructor(onChange, current) {
      this.onChange = onChange; this.filters = [];
      this.origin = el("select.weekly-origin", {disabled: true, onchange: () => this.choose(this.origin.value)});
      this.style = WeeklySourcePicker.create("style", source => {
        const filter = this.filters.find(item => item.name === source.identity);
        if (filter) this.choose(filter.key);
      }, current, source => this.name(this.filters.find(item => item.name === source.identity)) || source.name);
      this.style.toggle.disabled = true;
      this.around = WeeklySourcePicker.create("artist", artist => this.choose("all", artist), current);
      this.panel = el("section.weekly-filter-panel", {hidden: true, id: "weekly-filters-" + App.requestId(),
        "aria-label": t("filters")},
        el("div.weekly-filter-fields", {}, el("label", {}, el("span.weekly-field-label", {text: t("show")}), this.origin),
          this.style.node), this.around.node,
        el("button.link-button.weekly-filter-done", {type: "button", text: t("filters_done"), onclick: () => this.close()}));
      this.toggle = el("button.weekly-filter-toggle", {type: "button", text: t("filter_open"),
        "aria-expanded": "false", "aria-controls": this.panel.id, onclick: () => this.panel.hidden ? this.open() : this.close()});
      this.summary = el("span");
      this.active = el("div.weekly-active-filter", {hidden: true}, el("span.weekly-filter-value", {}, this.summary,
        el("button.link-button.weekly-filter-clear", {type: "button", text: "×", "aria-label": t("filter_clear"),
          onclick: () => this.choose("all")})),
        el("button.link-button", {type: "button", text: t("filter_edit"), onclick: () => this.open()}));
      this.panel.addEventListener("keydown", event => {
        if (event.key === "Escape") { event.preventDefault(); this.close(); }
      });
    }

    name(filter) {
      return filter ? (filter.name || t("filter_" + filter.key)) + " (" + filter.count + ")" : "";
    }

    update(filters, selected, artist) {
      this.filters = filters;
      const origins = filters.filter(filter => !filter.name);
      this.origin.disabled = !origins.length;
      this.style.toggle.disabled = !filters.length;
      App.clear(this.origin);
      App.append(this.origin, origins.map(filter => el("option", {value: filter.key, text: this.name(filter)})));
      const style = filters.find(filter => filter.key === selected && filter.name);
      this.origin.value = style || artist ? "all" : selected;
      this.style.select(style); this.around.select(artist);
      this.active.hidden = selected === "all" && !artist;
      this.summary.textContent = artist ? t("around_title", {name: artist.name}) : this.name(filters.find(f => f.key === selected));
    }

    choose(filter, artist = null) {
      this.close();
      this.onChange(filter, artist);
    }

    open() {
      this.panel.hidden = false;
      this.toggle.setAttribute("aria-expanded", "true");
      this.origin.focus({preventScroll: true});
    }

    close() {
      this.style.close(); this.around.close();
      this.panel.hidden = true;
      this.toggle.setAttribute("aria-expanded", "false");
      this.toggle.focus({preventScroll: true});
    }
  }

  return {create: (...args) => new Filters(...args)};
})();
