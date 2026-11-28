"use strict";

/* Choix d'une source suivie : recherche serveur normalisée et pages bornées, partagées par styles et artistes. */
const WeeklySourcePicker = (() => {
  const el = App.el, t = (key, values) => App.t("weekly." + key, values);

  class SourcePicker {
    constructor(kind, onChoose, current, label = source => source.name) {
      this.kind = kind; this.onChoose = onChoose; this.current = current; this.label = label;
      this.generation = 0; this.history = []; this.offset = 0;
      this.input = el("input", {type: "search", placeholder: t("search_" + kind),
        "aria-label": t("search_" + kind), autocomplete: "off", oninput: () => { this.history = []; this.load(0); }});
      this.results = el("div.weekly-picker-results");
      this.status = el("div.muted", {"aria-live": "polite"});
      this.previous = el("button.link-button.weekly-picker-previous", {type: "button", text: t("choices_previous"),
        onclick: () => this.load(this.history.pop())});
      this.next = el("button.link-button.weekly-picker-next", {type: "button", text: t("choices_next"),
        onclick: () => { this.history.push(this.offset); this.load(this.nextOffset); }});
      this.pages = el("div.weekly-picker-pages", {}, this.previous, this.next);
      this.panel = el("div.weekly-picker-panel", {hidden: true, id: "weekly-picker-" + App.requestId()},
        this.input, this.results, this.status, this.pages);
      this.caption = el("span", {text: t("any_" + kind)});
      this.caption.id = this.panel.id + "-value";
      const field = el("span.weekly-field-label", {id: this.panel.id + "-label", text: t("pick_" + kind)});
      this.toggle = el("button.weekly-picker-toggle", {type: "button", "aria-expanded": "false",
        "aria-labelledby": field.id + " " + this.caption.id,
        "aria-controls": this.panel.id, onclick: () => this.panel.hidden ? this.open() : this.close()},
        this.caption, el("span", {text: "▾", "aria-hidden": "true"}));
      this.node = el("div.weekly-picker", {dataset: {kind}}, field, this.toggle, this.panel);
      this.node.addEventListener("keydown", event => {
        if (event.key === "Escape" && !this.panel.hidden) {
          event.stopPropagation(); this.close(); this.toggle.focus({preventScroll: true});
        }
      });
    }

    open() {
      this.panel.hidden = false;
      this.toggle.setAttribute("aria-expanded", "true");
      this.input.value = ""; this.history = [];
      this.load(0); this.input.focus();
    }

    close() {
      ++this.generation;
      this.panel.hidden = true;
      this.toggle.setAttribute("aria-expanded", "false");
      App.clear(this.results);
    }

    select(source) { this.caption.textContent = source ? source.name : t("any_" + this.kind); }

    async load(offset) {
      const version = ++this.generation, q = this.input.value;
      const active = () => this.current() && !this.panel.hidden && version === this.generation;
      this.offset = offset;
      App.clear(this.results); this.status.textContent = t("loading");
      this.previous.disabled = true; this.next.disabled = true;
      try {
        const data = await App.api.get("/api/news/releases/sources/choices", {kind: this.kind, q, offset});
        if (!active()) return;
        this.show(data);
      } catch (error) {
        if (!active()) return;
        App.append(App.clear(this.status), [el("span", {text: App.errorText(error)}),
          el("button.link-button", {type: "button", text: t("retry"), onclick: () => this.load(offset)})]);
      }
    }

    show(data) {
      this.nextOffset = data.next;
      this.previous.disabled = !this.history.length;
      this.next.disabled = data.next === null;
      this.pages.hidden = !this.history.length && data.next === null;
      if (!data.available) { this.status.textContent = t("around_unavailable"); return; }
      this.status.textContent = data.sources.length ? "" : t(this.input.value ? "no_result" : "no_" + this.kind);
      App.append(this.results, data.sources.map(source => el("button", {type: "button", text: this.label(source),
        onclick: () => { this.close(); this.onChoose(source); }})));
    }
  }

  return {create: (...args) => new SourcePicker(...args)};
})();
