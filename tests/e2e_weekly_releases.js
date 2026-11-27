// Page réelle dans jsdom, services simulés, aucune dépendance réseau.
// node tests/e2e_weekly_releases.js [chemin vers jsdom]
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {JSDOM} = require(process.argv[2] || "jsdom");
const dom = new JSDOM('<main></main>', {url: "https://example.test/", runScripts: "outside-only"});
const win = dom.window, doc = win.document;
const src = name => fs.readFileSync(path.join(__dirname, "../src/web-pc/static/js", name + ".js"), "utf8");
const calls = [], writes = [];
const ids = ["noise", "techno"];
let pending;
win.getWeekly = async (url, params) => {
  calls.push({url, params});
  if (url.endsWith("/genres")) return {genres: ids.map((id, i) => ({id, name: ["noise rock", "techno"][i]})), followed: []};
  if (url.endsWith("/local")) return {albums: []};
  if (params.genre === "techno") return new Promise(resolve => { pending = resolve; });
  const date = new Date(params.monday + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + 4);
  return {albums: [{id: "id", artist: "Artiste", title: "Album vendredi", type: "Album", date: date.toISOString().slice(0, 10)}], next: null};
};
win.writeWeekly = async (url, body) => writes.push({url, body});
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
(async () => {
  win.eval(src("core") + '\nconst Views={};\n' + src("news") + '\n' + src("weekly-releases") + `
    App.api.get=window.getWeekly; App.api.post=window.writeWeekly;
    window.weekly=WeeklyReleaseView; window.news=News;
  `);
  assert.equal(win.weekly.mondayFor(new win.Date(2026, 10, 23)).toISOString().slice(0, 10), "2026-11-23");
  assert.equal(win.weekly.mondayFor(new win.Date(2027, 0, 3)).toISOString().slice(0, 10), "2026-12-28");
  await win.news.view.render(doc.querySelector("main"), {id: "releases"});
  await tick();
  assert.equal(doc.querySelector("h3").textContent, "Album vendredi");
  assert.ok(doc.querySelector('a[href="#/whatsnew/press/g5"]'));
  const button = doc.querySelector("button.primary");
  button.click(); await tick();
  assert.deepEqual(JSON.parse(JSON.stringify(writes[0].body)), {genre: "noise", enabled: true});
  assert.equal(doc.querySelector(".weekly-followed button").textContent, "noise rock");
  button.click(); await tick();
  assert.equal(doc.querySelector(".weekly-followed button"), null);
  const input = doc.querySelector("input");
  input.value = "techno"; input.dispatchEvent(new win.Event("input"));
  input.value = "noise rock"; input.dispatchEvent(new win.Event("input"));
  await tick(); pending({albums: [], next: null}); await tick();
  assert.equal(doc.querySelector("h3").textContent, "Album vendredi");
  const before = calls.filter(x => x.url.endsWith("/releases")).at(-1).params.monday;
  [...doc.querySelectorAll("button")].find(node => node.textContent === "weekly.next").click(); await tick();
  const after = calls.filter(x => x.url.endsWith("/releases")).at(-1).params.monday;
  assert.equal((new Date(after) - new Date(before)) / 86400000, 7);
  dom.window.close();
  console.log("OK · dates, annonces, abonnements, navigation et réponses désordonnées");
})().catch(error => { console.error(error); process.exitCode = 1; });
