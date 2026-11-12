"use strict";
/* En-tête artiste : la biographie sous le nom et le visuel se chargent indépendamment. */
class ArtistProfile {
  constructor(data, route, heart) {
    this.data = data;
    this.route = route;
    this.imageGeneration = 0;
    this.bio = App.el("section.artist-bio", {hidden: true, "aria-label": App.t("artist.bio")});
    this.portrait = App.el("figure.artist-portrait", {hidden: true});
    this.root = App.el("header.artist-head", {}, App.el("div.artist-heading", {},
      App.el("div.page-head", {}, App.el("h1", {text: data.name}), heart), this.bio), this.portrait);
  }

  load() { this.loadBio(); this.loadImage(); }

  async loadBio() {
    let bio;
    try { bio = await App.api.get("/api/artist/bio", {name: this.data.name, id: this.data.id3Id || ""}); }
    catch (error) { return; }
    if (this.route.stale || !bio.text) return;
    const text = App.el("div.bio-text", {}, bio.text.split(/\n+/).map(p => App.el("p", {text: p})));
    const more = App.el("button.link-button.bio-more", {type: "button", text: App.t("artist.bio_more"),
      "aria-expanded": "false", onclick: () => {
        const open = this.bio.classList.toggle("open");
        more.textContent = App.t(open ? "artist.bio_less" : "artist.bio_more");
        more.setAttribute("aria-expanded", String(open));
      }});
    const source = bio.url ? App.el("a", {href: bio.url, target: "_blank", rel: "noopener noreferrer", text: bio.src}) : bio.src;
    App.append(App.clear(this.bio), [text, App.el("div.bio-foot", {}, more,
      App.el("small.bio-source", {}, App.t("artist.bio_source"), source))]);
    this.bio.hidden = false;
    setTimeout(() => { if (!this.route.stale && text.scrollHeight <= text.clientHeight + 2) more.hidden = true; }, 0);
  }

  async loadImage() {
    const generation = ++this.imageGeneration;
    this.portrait.hidden = true;
    try {
      const data = await App.api.get("/api/artist/image", {id: this.data.id});
      if (this.route.stale || generation !== this.imageGeneration) return;
      App.clear(this.portrait);
      this.portrait.hidden = !data.imageUrl;
      if (!data.imageUrl) return;
      const image = App.el("img", {src: data.imageUrl, alt: this.data.name, loading: "lazy", referrerPolicy: "no-referrer",
        onerror: () => { if (generation === this.imageGeneration) this.portrait.hidden = true; }});
      const name = App.t("artist.image_sources." + data.source);
      const source = data.sourceUrl ? App.el("a", {href: data.sourceUrl, target: "_blank", rel: "noopener noreferrer", text: name}) : name;
      App.append(this.portrait, [image, App.el("figcaption", {}, source)]);
    } catch (error) { /* Un visuel indisponible ne masque pas la biographie ou les albums. */ }
  }
}
