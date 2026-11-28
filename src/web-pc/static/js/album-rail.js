"use strict";
/* Une rangée de pochettes : défilement local et chargement de la page suivante à son extrémité. */
class AlbumRail {
  constructor(title, options = {}) {
    const el = App.el;
    this.loading = false;
    this.loadMore = null;
    this.alive = true;
    this.track = el("div.home-rail-track", {role: "group", "aria-label": title});
    this.status = el("p.home-rail-status.muted", {"aria-live": "polite"});
    this.previous = this.arrow("previous", title, -1);
    this.next = this.arrow("next", title, 1);
    const name = options.href ? el("a.home-rail-title", {href: options.href, text: title,
      "aria-label": App.t("home.see_section", {title})}) : title;
    this.root = el("section.home-rail" + (options.className || ""), {},
      el("header.home-rail-head", {}, el("h2", {}, name),
        el("div.home-rail-controls", {}, this.previous, this.next)), this.track, this.status);
    this.track.addEventListener("scroll", () => {
      this.update();
      if (this.atEnd()) this.fetchMore();
    }, {passive: true});
    if (window.ResizeObserver) {
      this.observer = new ResizeObserver(() => this.update());
      this.observer.observe(this.track);
    }
    this.update();
  }

  arrow(direction, title, step) {
    return App.setIcon(App.el("button.icon-button.home-rail-arrow", {type: "button",
      "aria-label": App.t("home." + direction, {title}), onclick: () => this.move(step)}), step < 0 ? "chevronLeft" : "chevronRight", 18);
  }

  append(nodes) {
    this.track.append(...nodes);
    this.status.textContent = "";
    this.update();
  }

  more(loader) { this.loadMore = loader; this.update(); }

  atEnd() { return this.track.scrollLeft + this.track.clientWidth >= this.track.scrollWidth - 24; }

  update() {
    this.previous.disabled = this.track.scrollLeft < 1;
    this.next.disabled = this.loading || (!this.loadMore &&
      this.track.scrollLeft + this.track.clientWidth >= this.track.scrollWidth - 1);
  }

  async move(direction) {
    if (this.loading || !this.alive) return;
    if (direction > 0 && this.loadMore && this.atEnd() && !await this.fetchMore()) return;
    if (!this.alive) return;
    const card = this.track.firstElementChild;
    const gap = parseFloat(getComputedStyle(this.track).columnGap) || 0;
    const step = (card ? card.getBoundingClientRect().width : 0) + gap;
    const distance = step > 0 ? Math.max(1, Math.floor((this.track.clientWidth + gap) / step)) * step
      : this.track.clientWidth;
    const reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (this.track.scrollBy) this.track.scrollBy({left: direction * distance, behavior: reduced ? "instant" : "smooth"});
    else this.track.scrollLeft += direction * distance;
    this.update();
  }

  async fetchMore() {
    if (this.loading || !this.alive || !this.loadMore) return false;
    this.loading = true;
    this.status.textContent = App.t("home.loading");
    this.update();
    try { await this.loadMore(); return true; }
    catch (error) { if (this.alive) this.error(error, () => this.fetchMore()); return false; }
    finally { this.loading = false; this.update(); }
  }

  error(error, retry) {
    this.status.replaceChildren(App.el("span", {text: App.errorText(error)}), " ",
      App.el("button.link-button", {type: "button", text: App.t("home.retry"), onclick: retry}));
  }

  empty(message) { this.status.textContent = message; }

  destroy() { this.alive = false; this.loadMore = null; if (this.observer) this.observer.disconnect(); }
}
