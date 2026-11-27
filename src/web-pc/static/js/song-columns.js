"use strict";
/* Colonnes des morceaux : schéma fourni par /api/me, formats et visibilité communs aux listes et au lecteur. */
const SongColumns = (() => {
  const label = key => App.t("song_columns." + key);

  function format(song, key) {
    if (key === "track") return song.track ? String(song.track) : "—";
    if (key === "album") return song.ext ? App.t("ext.sources." + song.ext) : song.album || "—";
    if (key === "artist" || key === "genre") return song[key] || "—";
    if (key === "year") return song.year ? String(song.year) : "—";
    if (key === "duration") return song.duration ? App.duration(song.duration) : "—";
    if (key === "format") return song.suffix ? song.suffix.toUpperCase() : "—";
    if (key === "bitrate") return song.bitRate > 0
      ? App.t("song_columns.bitrate_value", {value: Number(song.bitRate).toLocaleString("fr-FR")}) : "—";
    if (key === "size") return song.size > 0
      ? App.t("song_columns.size_value", {value: (song.size / 1024 ** 2).toLocaleString("fr-FR", {maximumFractionDigits: 1})}) : "—";
    return "—";
  }

  function cell(song, key, selector = "td." + key) {
    const value = format(song, key);
    const description = key === "genre" && value === "—" ? App.t("song.style_missing")
      : App.t("song_columns.value", {column: label(key), value});
    const content = key === "album" && !song.ext && song.albumId
      ? App.el("a", {href: "#/album/" + encodeURIComponent(song.albumId), text: value, title: description})
      : App.el("span." + (key === "genre" ? "song-genre" : "song-value"), {text: value, title: description});
    return App.el(selector, {dataset: {songColumn: key}, "aria-label": description}, content);
  }

  /** Les titres et les commandes restent disponibles, même lorsque toutes les informations sont masquées. */
  function apply(table, context) {
    table.querySelectorAll("[data-song-column]").forEach(cell => {
      cell.hidden = App.preferences[context + "_" + cell.dataset.songColumn] === false;
    });
    const row = table.querySelector("thead tr") || table.querySelector("tr.song, tr.queue-row");
    const count = row ? Array.from(row.children).filter(cell => !cell.hidden).length : 1;
    table.querySelectorAll(".disc-row > td, tr.empty > td").forEach(cell => { cell.colSpan = count; });
  }

  /** Même grille dans les réglages rapides et Mon compte ; chaque case est enregistrée immédiatement. */
  function settings() {
    const el = App.el;
    const contexts = ["browse", "queue"];
    return el("section.song-column-settings", {},
      el("h3", {text: App.t("song_columns.settings")}),
      el("p.muted", {text: App.t("song_columns.help")}),
      el("table.song-column-options", {},
        el("thead", {}, el("tr", {}, el("th", {scope: "col", text: App.t("song_columns.show")}),
          contexts.map(context => el("th", {scope: "col", text: App.t("song_columns." + context)})))),
        el("tbody", {}, App.songColumns.map(key => el("tr", {},
          el("th", {scope: "row", text: label(key)}),
          contexts.map(context => {
            const preference = context + "_" + key;
            const input = el("input", {type: "checkbox", checked: App.preferences[preference] !== false,
              dataset: {context, column: key},
              "aria-label": App.t("song_columns.choice", {context: App.t("song_columns." + context), column: label(key)}),
              onchange: () => App.savePreference(preference, input.checked)});
            return el("td", {}, input);
          }))))));
  }

  return {label, format, cell, apply, settings};
})();
