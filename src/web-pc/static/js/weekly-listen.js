"use strict";

/* #/listen/<artiste>/<titre> : écouter une sortie qui vient de sortir, donc absente de la bibliothèque. On cherche
   l'album lui-même sur YouTube Music (même recherche que le reste du site, sans clé), pas des titres voisins.
   Introuvable : la recherche habituelle reste proposée. */
Views.listen = (() => {
  const el = App.el;
  const t = (key, values) => App.t("weekly." + key, values);

  function link(artist, title) {
    return "#/listen/" + encodeURIComponent(artist) + "/" + encodeURIComponent(title);
  }

  async function render(main, route) {
    const artist = route.artist || "", title = route.id || "";
    const status = el("p.muted", {"aria-live": "polite", text: t("listen_searching")});
    const fallback = el("a.chip.listen-fallback", {href: "#/search/" + encodeURIComponent(artist + " " + title),
                                                   text: t("listen_search")});
    App.append(App.clear(main), [News.tabs(true), el("h1", {text: t("listen_title", {title, artist})}),
      el("p.muted", {text: t("listen_intro")}), status]);
    let songs = [];
    try {
      songs = (await App.api.get("/api/ext/album", {artist, title})).items
        .map(song => Object.assign({}, song, {coverId: song.imageUrl || ""}));
    } catch (error) {
      if (!route.stale) App.append(App.clear(status), [App.errorText(error), " ", fallback]);
      return;
    }
    if (route.stale) return;
    await ExtMusic.favoritesReady();
    if (!songs.length) { App.append(App.clear(status), [t("listen_none"), " ", fallback]); return; }
    status.replaceWith(ExtMusic.table(songs));
  }

  return {render, link};
})();
