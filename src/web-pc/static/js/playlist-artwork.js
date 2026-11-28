"use strict";
/* Un même visuel pour les cartes et la page ouverte ; sélection et nombre de cases fournis par le serveur. */
const PlaylistArtwork = {
  render(covers, size = 240) {
    const ids = covers || [];
    const root = App.el("div.playlist-artwork" + (ids.length > 1 ? ".mosaic" : ""), {"aria-hidden": "true"});
    for (const id of ids.length ? ids : [""]) root.appendChild(App.cover(id, size, ""));
    return root;
  },
};
