// Filtres compacts : 500 artistes ne créent jamais une page de boutons.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {JSDOM} = require(process.argv[2] || "jsdom");
const dom = new JSDOM('<main></main>', {url: "https://example.test/", runScripts: "outside-only"});
const win = dom.window, doc = win.document;
const src = name => fs.readFileSync(path.join(__dirname, "../src/web-pc/static/js", name + ".js"), "utf8");
const calls = [];
const artists = Array.from({length: 500}, (_, i) => ({kind: "artist", id: i, identity: "id" + i, name: "Artiste " + i}));
let delayed = null, available = true;
win.fakeGet = async (url, params = {}) => {
  calls.push({url, params: {...params}});
  if (url.endsWith("/choices")) {
    if (params.q === "lent") return new Promise(resolve => { delayed = resolve; });
    const found = params.kind === "style" ? [{kind: "style", identity: "techno", name: "techno"}]
      : params.q ? [{...artists[499], name: "Björk & Cœur"}] : artists;
    const offset = params.offset || 0;
    return {sources: found.slice(offset, offset + 5), next: offset + 5 < found.length ? offset + 5 : null,
            available: params.kind === "style" || available};
  }
  if (url.endsWith("/radar") || url.endsWith("/around")) return {
    filters: [{key: "all", count: 16}, {key: "style:techno", name: "techno", count: 0},
      {key: "artists", count: 2}, {key: "labels", count: 0}], next: null,
    around: url.endsWith("/around") ? params.name : null,
    cards: [{id: "a", title: "Album", artist: "Artiste", date: "2026-11-27", type: "Album", reasons: []}]
  };
  throw new Error("appel inattendu " + url);
};
const settle = async () => { for (let i = 0; i < 5; i++) await new Promise(r => setTimeout(r, 0)); };
const change = (node, value, type = "change") => { node.value = value; node.dispatchEvent(new win.Event(type)); };
const byLabel = label => doc.querySelector('[aria-label="weekly.' + label + '"]');
(async () => {
  win.eval(["core", "icons", "weekly-week", "weekly-source-picker", "weekly-filters", "weekly-releases"].map(src).join('\n') +
    '\nconst News={tabs:()=>null};\n' + src("weekly-radar") + `
    App.api.get=window.fakeGet;
    App.texts["weekly.around_title"]="Autour de {name}";
    window.renderRadar=WeeklyRadar.render;
  `);
  const main = doc.querySelector("main"), route = {};
  await win.renderRadar(main, route); await settle();
  const heading = doc.querySelector(".weekly-heading"), grid = doc.querySelector(".weekly-grid");
  const panel = doc.querySelector(".weekly-filter-panel"), toggle = doc.querySelector(".weekly-filter-toggle");
  assert.equal(panel.hidden, true);
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  assert.equal(calls.filter(c => c.url.endsWith("/choices")).length, 0);
  assert.equal(doc.querySelectorAll(".weekly-chips button").length, 0);
  assert.equal(byLabel("next").textContent, "");
  main.scrollTop = 160;
  toggle.click();
  assert.equal(panel.hidden, false);
  const artistPicker = doc.querySelector('[data-kind="artist"]');
  artistPicker.querySelector(".weekly-picker-toggle").click(); await settle();
  assert.equal(artistPicker.querySelectorAll(".weekly-picker-results button").length, 5);
  artistPicker.querySelector(".weekly-picker-next").click(); await settle();
  assert.equal(calls.at(-1).params.offset, 5);
  assert.equal(artistPicker.querySelectorAll(".weekly-picker-results button").length, 5);
  const search = artistPicker.querySelector("input");
  change(search, "bjork coeur", "input"); await settle();
  assert.equal(calls.at(-1).params.q, "bjork coeur");
  assert.equal(calls.at(-1).params.offset, 0);
  artistPicker.querySelector(".weekly-picker-results button").click(); await settle();
  assert.equal(calls.at(-1).url, "/api/news/releases/around");
  assert.equal(calls.at(-1).params.name, "Björk & Cœur");
  assert.equal(calls.at(-1).params.mbid, "id499");
  assert.equal(panel.hidden, true);
  assert.equal(doc.querySelector(".weekly-heading"), heading);
  assert.equal(doc.querySelector(".weekly-grid"), grid);
  assert.equal(main.scrollTop, 160);
  assert.ok(doc.querySelector(".weekly-active-filter").textContent.includes("Björk & Cœur"));
  byLabel("next").click(); await settle();
  assert.equal(calls.at(-1).url, "/api/news/releases/around");
  doc.querySelector(".weekly-filter-clear").click(); await settle();
  assert.equal(calls.at(-1).params.filter, "all");
  assert.equal(doc.querySelector(".weekly-active-filter").hidden, true);

  // Un style à zéro sortie reste sélectionnable ; choisir une origine le remplace.
  toggle.click();
  const stylePicker = doc.querySelector('[data-kind="style"]');
  stylePicker.querySelector(".weekly-picker-toggle").click(); await settle();
  assert.ok(stylePicker.querySelector(".weekly-picker-results button").textContent.includes("(0)"));
  stylePicker.querySelector(".weekly-picker-results button").click(); await settle();
  assert.equal(calls.at(-1).params.filter, "style:techno");
  toggle.click();
  change(doc.querySelector(".weekly-origin"), "artists"); await settle();
  assert.equal(calls.at(-1).params.filter, "artists");
  assert.equal(panel.hidden, true);

  // Choix de date, retour à cette semaine, sans toucher aux filtres.
  const week = doc.querySelector(".weekly-week");
  change(week.querySelector('input[type="date"]'), "2027-01-03"); await settle();
  assert.equal(calls.at(-1).params.monday, "2026-12-28");
  assert.equal(calls.at(-1).params.filter, "artists");
  week.querySelector(".weekly-today").click(); await settle();
  assert.equal(week.querySelector(".weekly-today").hidden, true);

  // Réponse tardive : le sélecteur fermé ne se rouvre pas et ne conserve pas d'anciens choix cliquables.
  toggle.click(); artistPicker.querySelector(".weekly-picker-toggle").click(); await settle();
  change(search, "lent", "input"); await settle();
  toggle.click();
  delayed({sources: [artists[0]], next: null, available: true}); await settle();
  assert.equal(panel.hidden, true);
  assert.equal(artistPicker.querySelectorAll(".weekly-picker-results button").length, 0);

  // Erreur expliquée sans Last.fm ; fermeture au clavier et après navigation.
  available = false;
  toggle.click(); artistPicker.querySelector(".weekly-picker-toggle").click(); await settle();
  assert.ok(artistPicker.textContent.includes("weekly.around_unavailable"));
  panel.dispatchEvent(new win.KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
  assert.equal(panel.hidden, true);
  assert.equal(doc.activeElement, toggle);
  route.stale = true;
  dom.window.close();
  console.log("OK · filtres compacts, 500 artistes, recherche paginée, résumé, semaines et réponses tardives");
})().catch(error => { console.error(error); dom.window.close(); process.exitCode = 1; });
