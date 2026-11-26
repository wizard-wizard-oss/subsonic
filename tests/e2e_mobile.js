// Contrôles du composant mobile avec le HTML et les gestionnaires du bureau réels.
// Usage : node tests/e2e_mobile.js [jsdom]
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {JSDOM} = require(process.argv[2] || "jsdom");
const root = path.join(__dirname, "..", "src", "web-pc");
const source = name => fs.readFileSync(path.join(root, "static", "js", name), "utf8");
const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
let checks = 0;
const check = (name, run) => { run(); checks++; console.log("OK   " + name); };

function page(mobile, mode = "pinned", chat = "closed") {
  const dom = new JSDOM(html, {url: "https://music.example/", runScripts: "outside-only", pretendToBeVisual: true});
  const window = dom.window, document = window.document, changes = [], writes = [];
  const evaluate = code => vm.runInContext(code, dom.getInternalVMContext());
  const query = {matches: mobile, addEventListener: (kind, listener) => changes.push(listener)};
  if (mobile !== null) window.matchMedia = () => query;
  window.Element.prototype.getClientRects = function () { return this.closest("[hidden]") ? [] : [{}]; };
  evaluate(source("core.js"));
  evaluate(source("icons.js"));
  evaluate(source("sidebar.js"));
  evaluate(source("app.js").split("App.music = new MusicApp();")[0]);
  window.writes = writes;
  evaluate(`
    App.texts = {"nav.menu":"Menu", "nav.artists":"Artistes", "nav.chat":"Salon", "settings.close":"Fermer"};
    App.user = {id:1};
    App.preferences = {sidebar:${JSON.stringify(mode)}, chat_panel:${JSON.stringify(chat)}};
    App.live = {on() {}};
    App.api.post = async (url, body) => { window.writes.push({url, body}); return {}; };
    App.chatPanel = {calls:0, tab:"room", toggle() { this.calls++; },
      thread:{isVisible:() => App.preferences.chat_panel === "open", scrollToLatest() {}, markRead() {}}};
    App.translate(); App.placeIcons();
    App.music = new MusicApp();
    App.music.sidebar = new ArtistSidebar(App.music);
    App.music.sidebar.applyMode();
    App.music.bindTopbar();
  `);
  document.getElementById("app").hidden = false;
  document.getElementById("login").hidden = true;
  const original = document.body.innerHTML;
  evaluate(source("mobile/navigation.js"));
  evaluate(source("mobile/bootstrap.js"));
  return {window, document, writes, original,
    $: selector => document.querySelector(selector),
    resize(value) { query.matches = value; for (const listener of changes) listener({matches:value}); },
    eval: evaluate,
    key(key, options = {}) { document.activeElement.dispatchEvent(new window.KeyboardEvent("keydown", {key, bubbles:true, cancelable:true, ...options})); },
    close() { dom.window.close(); }};
}

(async () => {
  const styles = page(false);
  check("CSS mobile : fichiers conditionnels, sans règle globale", () => {
    const links = [...styles.document.querySelectorAll('link[href^="/static/css/mobile/"]')];
    assert.equal(links.length, 2);
    for (const link of links) {
      const sheet = styles.document.createElement("style");
      sheet.textContent = fs.readFileSync(path.join(root, link.getAttribute("href").split("?")[0].slice(1)), "utf8");
      styles.document.head.appendChild(sheet);
      assert.ok(sheet.sheet.cssRules.length);
      for (const rule of sheet.sheet.cssRules) {
        assert.equal(rule.type, 4);
        assert.equal(rule.media.mediaText, link.media);
      }
    }
  });
  styles.close();

  for (const matches of [false, null]) {
    const p = page(matches);
    check("bureau : aucun changement du DOM" + (matches === null ? " sans matchMedia" : ""), () => {
      assert.equal(p.document.body.innerHTML, p.original);
      assert.equal(p.$(".mobile-menu-tools"), null);
    });
    p.$("#toggle-sidebar").click();
    await Promise.resolve();
    check("bureau : le bouton garde son gestionnaire et sa préférence", () => {
      assert.equal(p.eval("App.preferences.sidebar"), "hidden");
      assert.equal(p.writes.length, 1);
      assert.equal(p.writes[0].body.changes.sidebar, "hidden");
    });
    p.$("#toggle-chat").click();
    check("bureau : le salon garde son gestionnaire", () => assert.equal(p.eval("App.chatPanel.calls"), 1));
    p.close();
  }

  for (const mode of ["pinned", "hidden", "hover"]) {
    const p = page(true, mode), preferences = p.eval("JSON.stringify(App.preferences)");
    check("mobile : liens existants déplacés dans le menu (" + mode + ")", () => {
      assert.equal(p.$("#sidebar > .topnav").querySelectorAll("a").length, 8);
      assert.equal(p.$(".mobile-menu-tools #me").id, "me");
      assert.equal(p.$("#toggle-sidebar").getAttribute("aria-expanded"), "false");
      assert.equal(p.eval("App.chatPanel.thread.isVisible()"), false);
    });
    p.$("#toggle-sidebar").click();
    check("mobile : le clic ouvre les artistes sans toucher au bureau", () => {
      assert.equal(p.document.body.dataset.mobilePanel, "navigation");
      assert.equal(p.document.activeElement.id, "artist-filter");
      assert.equal(p.$("#toggle-sidebar").getAttribute("aria-expanded"), "true");
      assert.equal(p.$("#main").inert, true);
      assert.equal(p.document.body.dataset.sidebar, mode);
      assert.equal(p.eval("JSON.stringify(App.preferences)"), preferences);
      assert.equal(p.writes.length, 0);
    });
    p.$("#toggle-sidebar").click();
    check("mobile : un second clic ferme et rend le focus", () => {
      assert.equal(p.document.body.dataset.mobilePanel, undefined);
      assert.equal(p.document.activeElement.id, "toggle-sidebar");
      assert.equal(p.$("#main").inert, undefined);
    });
    p.$("#panel-artists").hidden = true;
    p.$("#panel-playlists").hidden = false;
    p.$("#toggle-sidebar").click();
    check("mobile : l’onglet playlists existant reste accessible", () => assert.equal(p.document.activeElement.id, "playlist-filter"));
    p.key("Escape");
    check("mobile : Échap ferme le volet", () => assert.equal(p.document.body.dataset.mobilePanel, undefined));
    p.$("#toggle-sidebar").click();
    p.$("#logout").focus();
    p.key("Tab");
    check("mobile : le focus reste dans le volet", () => assert.equal(p.document.activeElement, p.$(".mobile-panel-head button")));
    p.key("Tab", {shiftKey:true});
    check("mobile : le retour clavier reste dans le volet", () => assert.equal(p.document.activeElement.id, "logout"));
    p.$(".mobile-backdrop").click();
    check("mobile : le fond ferme le volet", () => assert.equal(p.document.body.dataset.mobilePanel, undefined));
    p.$("#toggle-sidebar").click();
    p.$('.topnav a[href="#/favorites"]').click();
    await new Promise(resolve => setTimeout(resolve, 0));
    check("mobile : choisir une page ferme le menu et garde la destination", () => {
      assert.equal(p.document.body.dataset.mobilePanel, undefined);
      assert.equal(p.window.location.hash, "#/favorites");
    });
    p.$("#toggle-chat").click();
    check("mobile : le salon s’ouvre sans changer sa préférence PC", () => {
      assert.equal(p.document.body.dataset.mobilePanel, "chat");
      assert.equal(p.eval("App.preferences.chat_panel"), "closed");
      assert.equal(p.eval("App.chatPanel.calls"), 0);
      assert.equal(p.eval("App.chatPanel.thread.isVisible()"), true);
    });
    p.$(".mobile-panel-head button").click();
    p.$("#toggle-sidebar").focus();
    p.key("a");
    check("mobile : le raccourci ouvre le menu sans sauvegarde PC", () => {
      assert.equal(p.document.body.dataset.mobilePanel, "navigation");
      assert.equal(p.writes.length, 0);
    });
    p.eval('App.bus.emit("route", {})');
    check("mobile : une navigation ferme le menu", () => assert.equal(p.document.body.dataset.mobilePanel, undefined));
    p.$("#toggle-sidebar").click();
    p.$("#app").hidden = true;
    await Promise.resolve();
    check("mobile : une session perdue ferme le volet et libère le contenu", () => {
      assert.equal(p.document.body.dataset.mobilePanel, undefined);
      assert.equal(p.$("#main").inert, undefined);
    });
    p.$("#app").hidden = false;
    await Promise.resolve();
    p.$("#panel-artists").hidden = false;
    p.$("#panel-playlists").hidden = true;
    p.$("#toggle-sidebar").click();
    p.resize(false);
    check("retour PC : nœuds, ordre, attributs et préférences restaurés", () => {
      assert.equal(p.document.body.innerHTML, p.original);
      assert.equal(p.eval("JSON.stringify(App.preferences)"), preferences);
      assert.equal(p.writes.length, 0);
    });
    p.resize(true); p.resize(false); p.resize(true);
    p.$("#toggle-sidebar").click();
    check("redimensionnements répétés : un seul menu et un seul gestionnaire", () => {
      assert.equal(p.document.querySelectorAll(".mobile-menu-tools").length, 1);
      assert.equal(p.document.body.dataset.mobilePanel, "navigation");
      assert.equal(p.writes.length, 0);
    });
    p.resize(false);
    p.$("#toggle-sidebar").click();
    await Promise.resolve();
    check("retour PC : le bouton reprend son comportement d’origine", () => {
      assert.equal(p.eval("App.preferences.sidebar"), mode === "pinned" ? "hidden" : mode === "hidden" ? "pinned" : "hover");
      assert.equal(p.writes.length, mode === "hover" ? 0 : 1);
    });
    p.close();
  }

  const chat = page(true, "pinned", "open");
  check("salon masqué sur mobile : les messages ne sont pas considérés comme lus", () => assert.equal(chat.eval("App.chatPanel.thread.isVisible()"), false));
  chat.$("#toggle-chat").click();
  check("salon mobile ouvert : les messages deviennent visibles", () => assert.equal(chat.eval("App.chatPanel.thread.isVisible()"), true));
  chat.$("#toggle-chat").click();
  chat.resize(false);
  check("retour PC : visibilité du salon et préférence initiale conservées", () => {
    assert.equal(chat.eval("App.chatPanel.thread.isVisible()"), true);
    assert.equal(chat.eval("App.preferences.chat_panel"), "open");
    assert.equal(chat.writes.length, 0);
  });
  chat.close();
  console.log(checks + " contrôles du mobile et de l’isolation PC réussis");
})().catch(error => { console.error(error); process.exitCode = 1; });
