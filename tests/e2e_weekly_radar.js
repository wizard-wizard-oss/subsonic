// Radar des sorties dans jsdom : services simulés, aucune dépendance réseau.
// node tests/e2e_weekly_radar.js [chemin vers jsdom]
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {JSDOM} = require(process.argv[2] || "jsdom");
const dom = new JSDOM('<main></main>', {url: "https://example.test/", runScripts: "outside-only"});
const win = dom.window, doc = win.document;
const src = name => fs.readFileSync(path.join(__dirname, "../src/web-pc/static/js", name + ".js"), "utf8");
const calls = [], writes = [];
const WARP = "00000000-0000-4000-8000-000000000700";
const state = {empty: null, outOfWindow: false, refreshAfter: null, discoveriesAvailable: true,
               sources: [{id: 1, kind: "label", identity: WARP, name: "Warp", origin: "manual", via: null},
                         {id: 2, kind: "style", identity: "techno", name: "techno", origin: "trends", via: null},
                         {id: 3, kind: "similar", identity: "x", name: "Apparat", origin: "discovery", via: "Moderat"}]};
const card = (id, title, reasons, local = null) => ({id, title, artist: "Artiste", date: "2026-11-27", type: "Album",
                                                      reasons, score: 0.5, local});
win.fakeGet = async (url, params) => {
  calls.push({url, params: JSON.parse(JSON.stringify(params || {}))});
  if (url.endsWith("/radar")) {
    if (state.outOfWindow) return {monday: params.monday, cards: [], filters: [], outOfWindow: true, defaultStyle: "noise rock"};
    if (state.empty) return {monday: params.monday, cards: [], filters: [], empty: "no-sources", defaultStyle: "noise rock"};
    const warp = state.sources[0], techno = state.sources[1], apparat = state.sources[2];
    return {monday: params.monday, filter: params.filter, next: null, updatedAt: Math.floor(Date.now() / 1000) - 600,
            refreshAfter: state.refreshAfter, outOfWindow: false, empty: null,
            filters: [{key: "all", count: 3}, {key: "style:techno", count: 2, name: "techno"}, {key: "labels", count: 1},
                      {key: "artists", count: 0}, ...(state.discoveriesAvailable ? [{key: "discoveries", count: 1}] : [])],
            cards: [card("a", "Album label", [warp, techno], {id: "al1", coverId: "c1", folderId: "f1"}),
                    card("b", "Album style", [techno]), card("c", "Album proche", [apparat])]};
  }
  if (url.endsWith("/sources")) return {sources: state.sources, discoveriesEnabled: true,
                                         discoveriesAvailable: state.discoveriesAvailable, refreshCooldown: 600};
  if (url.endsWith("/genres")) return {genres: [{name: "techno"}, {name: "noise rock"}], followed: [], default: "noise rock"};
  if (url.endsWith("/search")) return {results: [{id: WARP, name: "Warp", country: "GB", description: ""}]};
  if (url.endsWith("/releases")) return {albums: [], next: null};
  throw new Error("appel inattendu " + url);
};
win.fakePost = async (url, body) => {
  writes.push({url, body: JSON.parse(JSON.stringify(body))});
  if (url.endsWith("/refresh")) return {refreshAfter: Math.floor(Date.now() / 1000) + 600};
  if (url.endsWith("/sources/add")) return {id: 9, kind: body.kind, identity: body.identity, name: body.name, origin: "manual"};
  return {};
};
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
const settle = async () => { for (let i = 0; i < 5; i++) await tick(); };
const radarCalls = () => calls.filter(c => c.url.endsWith("/radar"));
const button = text => [...doc.querySelectorAll("button")].find(node => node.textContent === text);
(async () => {
  win.eval(src("core") + '\nconst Views={};\n' + src("news") + '\n' + src("weekly-releases") + '\n' + src("weekly-sources") +
    '\n' + src("weekly-radar") + `
    App.api.get=window.fakeGet; App.api.post=window.fakePost; App.toast=()=>{};
    Object.assign(App.texts, {"weekly.reason_label": "label {name}", "weekly.reason_similar": "proche de {name}",
                              "weekly.origin_similar": "proche de {name}"});
    window.weekly=WeeklyReleaseView; window.news=News;
  `);
  const main = doc.querySelector("main");
  await win.news.view.render(main, {id: "releases"});
  await settle();

  // ouverture : une lecture du radar, rien vers la bibliothèque depuis le navigateur
  assert.equal(radarCalls().length, 1);
  assert.equal(radarCalls()[0].params.filter, "all");
  assert.equal(calls.filter(c => c.url.includes("/explore/local")).length, 0);
  assert.deepEqual([...doc.querySelectorAll(".weekly-card h3")].map(n => n.textContent), ["Album label", "Album style", "Album proche"]);
  const chips = doc.querySelector(".weekly-chips");
  assert.deepEqual([...chips.querySelectorAll("button")].map(b => b.dataset.key),
                   ["all", "style:techno", "labels", "artists", "discoveries"]);
  assert.ok(chips.querySelector('[data-key="style:techno"]').textContent.includes("techno"));
  const first = doc.querySelector(".weekly-card");
  assert.ok(first.querySelector(".weekly-reasons").textContent.includes("Warp"));
  assert.equal(first.querySelector("a").getAttribute("href"), "#/album/al1");
  assert.ok(doc.querySelectorAll(".weekly-card")[2].querySelector(".weekly-reasons").textContent.includes("Moderat"));

  // pastille : la grille change, l'en-tête et les pastilles restent les mêmes éléments
  const heading = doc.querySelector(".weekly-heading");
  chips.querySelector('[data-key="style:techno"]').click(); await settle();
  assert.equal(radarCalls().at(-1).params.filter, "style:techno");
  assert.equal(doc.querySelector(".weekly-heading"), heading);
  assert.equal(doc.querySelector(".weekly-chips"), chips);
  assert.ok(chips.querySelector('[data-key="style:techno"]').classList.contains("on"));

  // semaine suivante : même filtre, lundi + 7 jours
  const before = radarCalls().at(-1).params.monday;
  button("weekly.next").click(); await settle();
  assert.equal((new Date(radarCalls().at(-1).params.monday) - new Date(before)) / 86400000, 7);
  assert.equal(radarCalls().at(-1).params.filter, "style:techno");

  // actualiser : demandé une fois, bouton coupé jusqu'à l'heure donnée par le serveur
  const refresh = doc.querySelector(".weekly-refresh");
  assert.equal(refresh.disabled, false);
  refresh.click(); await settle();
  assert.equal(writes.filter(w => w.url.endsWith("/refresh")).length, 1);
  assert.equal(refresh.disabled, true);

  // panneau « Mes sources » : origine visible, masquer une source recharge la grille
  button("weekly.sources").click(); await settle();
  const panel = doc.querySelector(".weekly-sources");
  assert.ok(panel.textContent.includes("weekly.origin_trends"));
  assert.ok(panel.textContent.includes("Moderat"));
  const count = radarCalls().length;
  panel.querySelector('[data-source="1"] button').click(); await settle();
  assert.deepEqual(writes.at(-1), {url: "/api/news/releases/sources/hide", body: {id: 1}});
  assert.equal(panel.querySelector('[data-source="1"]'), null);
  assert.equal(radarCalls().length, count + 1);

  // ajouter un label par recherche
  panel.querySelector("select").value = "label";
  panel.querySelector("select").dispatchEvent(new win.Event("change"));
  panel.querySelector("input[type=search]").value = "Warp";
  panel.querySelector("form").dispatchEvent(new win.Event("submit", {cancelable: true})); await settle();
  assert.deepEqual(calls.at(-1), {url: "/api/news/releases/search", params: {kind: "label", q: "Warp"}});
  panel.querySelector(".weekly-search-results button").click(); await settle();
  assert.deepEqual(writes.at(-1), {url: "/api/news/releases/sources/add", body: {kind: "label", identity: WARP, name: "Warp"}});
  assert.ok(panel.querySelector('[data-source="9"]'));

  // ajouter un style du catalogue, sans recherche externe
  panel.querySelector("select").value = "style";
  panel.querySelector("select").dispatchEvent(new win.Event("change"));
  panel.querySelector("input[type=search]").value = "noise rock";
  const searches = calls.filter(c => c.url.endsWith("/search")).length;
  panel.querySelector("form").dispatchEvent(new win.Event("submit", {cancelable: true})); await settle();
  assert.deepEqual(writes.at(-1).body, {kind: "style", identity: "noise rock", name: "noise rock"});
  assert.equal(calls.filter(c => c.url.endsWith("/search")).length, searches);

  // découvertes : interrupteur
  const toggle = panel.querySelector("input[type=checkbox]");
  toggle.checked = false; toggle.dispatchEvent(new win.Event("change")); await settle();
  assert.deepEqual(writes.at(-1), {url: "/api/news/releases/discoveries", body: {enabled: false}});

  // sans Last.fm : ni pastille ni interrupteur
  state.discoveriesAvailable = false;
  await win.news.view.render(main, {id: "releases"}); await settle();
  assert.equal(doc.querySelector('[data-key="discoveries"]'), null);
  button("weekly.sources").click(); await settle();
  assert.equal(doc.querySelector(".weekly-sources input[type=checkbox]"), null);

  // compte sans source : invitation à choisir, qui ouvre le panneau
  state.empty = "no-sources";
  await win.news.view.render(main, {id: "releases"}); await settle();
  assert.ok(doc.querySelector(".weekly-results").textContent.includes("weekly.no_sources"));
  button("weekly.choose_sources").click(); await settle();
  assert.ok(doc.querySelector(".weekly-sources"));

  // semaine hors de la période suivie : consultation par style, comme avant
  state.empty = null; state.outOfWindow = true;
  await win.news.view.render(main, {id: "releases"}); await settle();
  assert.ok(doc.querySelector(".weekly-results").textContent.includes("weekly.out_of_window"));
  button("weekly.browse_style").click(); await settle();
  assert.ok(calls.some(c => c.url.endsWith("/genres")));
  assert.ok(calls.some(c => c.url === "/api/news/releases" && c.params.genre === "noise rock"));
  assert.ok(button("weekly.back_to_radar"));

  dom.window.close();
  console.log("OK · radar : filtres, semaines, actualisation, sources, découvertes, compte vide, hors période");
})().catch(error => { console.error(error); process.exitCode = 1; });
