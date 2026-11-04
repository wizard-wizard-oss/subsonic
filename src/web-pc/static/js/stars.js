"use strict";
/* Étoiles 1 à 5 d'un album. Survol : aperçu ; clic : envoyé à Subsonic avec votre compte ;
   clic sur la même étoile : note retirée. Sous les étoiles : la moyenne de tous les comptes Subsonic. */

class StarRating {
  constructor(rating, options) {
    this.rating = Object.assign({mine: 0, average: 0}, rating);
    this.readonly = !!(options && options.readonly);
    this.small = !!(options && options.small);
    this.stars = [];
    this.root = App.el("div.stars" + (this.small ? ".small" : "") + (this.readonly ? ".readonly" : ""), {
      role: this.readonly ? "img" : "radiogroup", "aria-label": App.t("album.your_rating")});
    for (let value = 1; value <= 5; value++) {
      const star = App.el(this.readonly ? "span.star" : "button.star", {
        type: this.readonly ? undefined : "button", text: "★",
        title: this.readonly ? undefined : value + " / 5",
        "aria-label": value + " / 5",
        onmouseenter: () => this.preview(value),
        onclick: () => this.choose(value)});
      this.stars.push(star);
      this.root.appendChild(star);
    }
    if (!this.readonly) {
      this.root.addEventListener("mouseleave", () => this.preview(0));
      this.root.title = App.t("album.remove_rating");
    }
    this.summary = this.small ? null : App.el("div.stars-summary");
    this.element = App.el("div.rating", {}, this.root, this.summary);
    this.paint(0);
  }

  preview(value) { if (!this.readonly) this.paint(value); }

  paint(hover) {
    const shown = hover || this.rating.mine || (this.readonly ? Math.round(this.rating.average) : 0);
    this.stars.forEach((star, i) => {
      star.classList.toggle("on", i < shown);
      star.classList.toggle("hover", !!hover && i < hover);
      if (star.setAttribute) star.setAttribute("aria-checked", String(i + 1 === this.rating.mine));
    });
    if (this.summary) {
      this.summary.textContent = this.rating.average
        ? App.t("album.average_rating", {average: this.rating.average.toLocaleString("fr-FR", {maximumFractionDigits: 1})})
        : App.t("album.no_rating");
    }
  }

  async choose(value) {
    if (this.readonly || this.busy) return;
    const wanted = value === this.rating.mine ? 0 : value;
    this.busy = true;
    try {
      const result = await App.api.post("/api/rating", {albumId: this.rating.albumId, rating: wanted});
      this.rating = result.rating;
      App.bus.emit("rating", this.rating);
    } catch (error) {
      App.toast(App.errorText(error), "error");
    } finally {
      this.busy = false;
      this.paint(0);
    }
  }
}
