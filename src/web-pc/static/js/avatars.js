"use strict";
/* Photos de profil : l'initiale en couleur, recouverte par la photo quand la personne en a une (envoyée sur le site,
   copiée de Gravatar ou choisie dans Subsonic). La liste des versions (/api/avatars) dit qui a une photo : on ne
   demande l'image que pour elles, et une nouvelle version fait recharger l'image. */

const Avatars = {
  versions: {},

  async load() {
    try { this.versions = (await App.api.get("/api/avatars")).versions; } catch (error) { return; }
    document.querySelectorAll(".avatar[data-user]").forEach(node => this.decorate(node));
  },

  /** Pastille d'une personne ; size : côté en pixels (sinon celui de la feuille de style). */
  node(username, size) {
    const name = username || "?";
    const node = App.el("span.avatar", {text: name.charAt(0).toUpperCase(), "aria-hidden": "true", dataset: {user: name}});
    node.style.background = App.colorOf(name);
    if (size) Object.assign(node.style, {width: size + "px", height: size + "px", fontSize: Math.round(size * 0.42) + "px"});
    this.decorate(node);
    return node;
  },

  decorate(node) {
    const version = this.versions[node.dataset.user];
    const image = node.querySelector("img");
    if (!version) { if (image) image.remove(); return; }
    const src = "/api/avatar?user=" + encodeURIComponent(node.dataset.user) + "&v=" + encodeURIComponent(version);
    if (image && image.getAttribute("src") === src) return;
    const fresh = App.el("img", {src, alt: "", loading: "lazy", onerror: () => fresh.remove()});
    if (image) image.replaceWith(fresh); else node.appendChild(fresh);
  },
};

App.avatar = (username, size) => Avatars.node(username, size);
