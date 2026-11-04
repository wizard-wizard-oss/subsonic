"use strict";
/* Changer la pochette d'un album (crayon sur la pochette, droit Subsonic « upload »), comme dans Subsonic V1 : artiste et
   album modifiables, recherche sur Last.fm, puis un clic sur une image l'écrit dans le dossier de l'album ; ou l'adresse
   d'une image collée à la main. */

const CoverEditor = (() => {
  const el = App.el, t = App.t;

  /** Ouvre la fenêtre pour l'album {id, name, artist} ; onSaved() est appelé quand la nouvelle pochette est écrite. */
  function open(album, onSaved) {
    const artist = el("input.dialog-input", {type: "text", value: album.artist, maxLength: 200, "aria-label": t("cover.artist")});
    const title = el("input.dialog-input", {type: "text", value: album.name, maxLength: 200, "aria-label": t("cover.album")});
    const url = el("input.dialog-input", {type: "text", placeholder: "http://", maxLength: 2000, "aria-label": t("cover.address")});
    const status = el("p.muted.cover-status", {role: "status"});
    const grid = el("div.cover-grid");
    let busy = false;

    async function save(address) {
      if (busy) return;
      busy = true;
      status.textContent = t("cover.saving");
      try {
        await App.api.post("/api/cover/save", {albumId: album.id, url: address});
        Dialogs.close();
        App.toast(t("cover.saved"));
        onSaved();
      } catch (error) {
        status.textContent = App.errorText(error);
        busy = false;
      }
    }

    async function search() {
      if (busy) return;
      status.textContent = t("cover.searching");
      grid.replaceChildren();
      try {
        const found = (await App.api.get("/api/cover/search", {artist: artist.value, album: title.value})).covers;
        status.textContent = found.length ? "" : t("cover.nothing");
        grid.replaceChildren(...found.map(c => el("button.cover-choice", {type: "button", title: t("cover.choose"),
          onclick: () => save(c.url)},
          el("img", {src: c.thumb, alt: "", loading: "lazy", referrerPolicy: "no-referrer"}),
          el("span", {}, el("strong", {text: c.name}), el("span.muted", {text: c.artist})))));
      } catch (error) { status.textContent = App.errorText(error); }
    }

    const enter = action => e => { if (e.key === "Enter") { e.preventDefault(); action(); } };
    [artist, title].forEach(input => input.addEventListener("keydown", enter(search)));
    url.addEventListener("keydown", enter(() => url.value.trim() && save(url.value.trim())));
    const box = Dialogs.open(t("cover.title"), el("div.cover-editor", {},
      el("div.cover-row", {}, artist, title,
         el("button", {type: "button", text: t("cover.search"), onclick: search})),
      el("div.cover-row.address", {}, el("span", {text: t("cover.or_address")}), url,
         el("button", {type: "button", text: t("cover.ok"), onclick: () => url.value.trim() && save(url.value.trim())})),
      status, grid, el("p.muted.cover-credit", {text: t("cover.credit")})));
    box.classList.add("dialog-wide");
    App.api.get("/api/cover/status").then(info => {
      if (!info.writable) status.textContent = t("cover.off");
      else if (!info.search) status.textContent = t("cover.no_lastfm");
    }).catch(() => {});
  }

  return {open};
})();
