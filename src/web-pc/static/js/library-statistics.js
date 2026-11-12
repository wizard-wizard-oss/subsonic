"use strict";
/* Les cinq compteurs du dernier scan Subsonic ; aucune collecte ni minuterie côté navigateur. */
const LibraryStatistics = (() => {
  function render(statistics) {
    if (!statistics) return null;
    const el = App.el;
    const number = value => value.toLocaleString("fr-FR");
    const metric = (key, value, icon, unit) => el("div.collection-metric" + (key === "songs" ? ".collection-highlight" : ""),
      {dataset: {metric: key}},
      el("dt", {}, App.icon(icon, 18), el("span", {text: App.t("collection." + key)})),
      el("dd", {}, el("strong", {text: value}), unit ? el("span.collection-unit", {text: unit}) : null));
    const scanned = new Date(statistics.lastScan);
    const date = scanned.toLocaleDateString("fr-FR", {day: "numeric", month: "long", year: "numeric"});
    return el("section.library-collection", {"aria-labelledby": "collection-title"},
      el("header.collection-head", {},
        el("div", {}, el("p.collection-eyebrow", {text: App.t("collection.scope")}),
          el("h2", {id: "collection-title", text: App.t("collection.title")})),
        el("time.collection-scan", {datetime: scanned.toISOString(),
          title: scanned.toLocaleString("fr-FR"), text: App.t("collection.last_scan", {date})})),
      el("dl.collection-metrics", {},
        metric("artists", number(statistics.artists), "mic"),
        metric("albums", number(statistics.albums), "disc"),
        metric("songs", number(statistics.songs), "music"),
        metric("storage", number(Math.round(statistics.bytes / 1024 ** 3)), "storage", App.t("collection.gib")),
        metric("duration", number(Math.floor(statistics.seconds / 3600)), "clock", App.t("collection.hours"))));
  }
  return {render};
})();
