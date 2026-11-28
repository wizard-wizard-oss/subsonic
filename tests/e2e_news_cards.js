// Les cartes, leurs images et les mises à jour locales utilisent le vrai composant.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {JSDOM} = require(process.argv[2] || "jsdom");
const dom = new JSDOM("<main></main><section class='press'></section>", {url: "https://music.example/#/news", runScripts: "outside-only"});
const w = dom.window, d = w.document;
const run = source => vm.runInContext(source, dom.getInternalVMContext());
const load = name => run(fs.readFileSync(path.join(__dirname, "../src/web-pc/static/js/" + name + ".js"), "utf8"));
const article = (id, imageUrl = "") => ({id, feedId: 1, feed: "Journal <b>musical</b>", title: "Disque <img src=x onerror=bad()>",
  summary: "Résumé <script>bad()</script>", link: "https://journal.example/" + id, publishedAt: 100 + id, imageUrl});
let shown = true, next = false, navigate = 0;
w.read = async url => {
  if (url === "/api/news/feeds") return {feeds: [{id: 1, title: "Journal", shown, articles: 3, canRemove: true}]};
  if (url === "/api/news/artist") return {articles: [article(1, "/api/news/image?id=1")]};
  return next ? {articles: [article(3)], more: false} : {articles: shown ? [article(1, "/api/news/image?id=1"), article(2)] : [], more: shown};
};
w.write = async (url, data) => { shown = data.shown; return {}; };
load("core"); load("icons");
run(`const Views={}; App.texts={"news.title":"Actualités","news.more":"Afficher plus","news.read":"Lire l’article",
  "news.image_missing":"{source}","news.empty":"Aucun article","artist.press":"Dans la presse"};
  App.api.get=window.read; App.api.post=window.write; App.music={navigate(){window.navigated();}};`);
w.navigated = () => { navigate++; };
load("news");
const tick = () => new Promise(resolve => setTimeout(resolve, 0));
(async () => {
  await run('News.view.render(document.querySelector("main"), {})');
  const first = d.querySelector(".news-article"), image = first.querySelector("img");
  assert.ok(image, "une image du flux accompagne la carte");
  assert.equal(image.getAttribute("src"), "/api/news/image?id=1");
  assert.equal(image.getAttribute("loading"), "lazy");
  assert.equal(d.querySelectorAll(".news-image-fallback").length, 1);
  assert.equal(d.querySelector(".news-title").textContent, article(1).title);
  assert.equal(d.querySelectorAll("script, .news-summary img").length, 0);
  image.dispatchEvent(new w.Event("error"));
  assert.equal(first.querySelector("img"), null);
  assert.equal(d.querySelector(".news-article"), first, "l'échec d'une image ne recrée pas les cartes");
  next = true;
  d.querySelector(".news-more").click(); await tick(); await tick();
  assert.equal(d.querySelectorAll(".news-article").length, 3);
  assert.equal(d.querySelector(".news-article"), first, "la pagination conserve les cartes déjà présentes");
  next = false;
  const heading = d.querySelector("main h1"), filter = d.querySelector(".news-show");
  filter.click(); await tick(); await tick();
  assert.equal(navigate, 0, "masquer un flux ne reconstruit pas la page");
  assert.equal(d.querySelector("main h1"), heading);
  assert.equal(d.querySelector(".news-show"), filter);
  assert.equal(d.querySelectorAll("main .news-article").length, 0);
  filter.click(); await tick(); await tick();
  await run('News.pressSection(document.querySelector(".press"), "Artist", {})');
  assert.ok(d.querySelector(".press .news-article img"));
  console.log("OK presse : images, repli, texte sûr, pagination et mise à jour locale");
  w.close();
})().catch(error => { console.error(error); w.close(); process.exitCode = 1; });
