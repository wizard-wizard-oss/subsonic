// Help seul dans jsdom : vrais textes du serveur et vrais composants de la page.
// Usage : node tests/e2e_help.js PORT [jsdom]
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + process.argv[2];
const root = path.join(__dirname, "..", "src", "web-pc");
const source = name => fs.readFileSync(path.join(root, "static", "js", name), "utf8");
let checks = 0;
const check = (name, run) => { run(); checks++; console.log("OK   " + name); };

(async () => {
  const response = await fetch(base + "/api/texts");
  assert.equal(response.status, 200, "Les vrais textes de l’application sont accessibles");
  const texts = await response.json();
  const html = fs.readFileSync(path.join(root, "index.html"), "utf8");
  const dom = new JSDOM(html, {url:base + "/#/whatsnew", runScripts:"outside-only", pretendToBeVisual:true});
  const window = dom.window, document = window.document;
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const evaluate = code => vm.runInContext(code, dom.getInternalVMContext());
  const writes = [], actions = [], errors = [], captures = new Set();
  try {
    window.Element.prototype.scrollIntoView = function () {};
    window.addEventListener("error", event => errors.push(event.message));
    evaluate(source("core.js"));
    evaluate(source("icons.js"));
    window.helpTexts = texts;
    window.helpWrites = writes;
    window.helpActions = actions;
    window.helpChat = {open:false, tab:"mentions", toggles:0, shows:[]};
    window.helpLyricsOpen = false;
    evaluate(`
      const Views = {};
      App.texts = window.helpTexts;
      App.user = {id:1, roles:["stream", "playlist", "download", "upload", "coverArt", "comment"]};
      App.preferences = {sidebar:"pinned", density:"comfortable", chat_panel:"closed"};
      App.player = {queue:[{id:"existing-track"}], index:0};
      App.lyrics = {open() { window.helpLyricsOpen = true; window.helpActions.push("lyrics"); },
        close() { window.helpLyricsOpen = false; }, isOpen() { return window.helpLyricsOpen; }};
      App.queuePanel = {open() { window.helpActions.push("queue"); }};
      App.chatPanel = {isOpen() { return window.helpChat.open; },
        show(name) { window.helpChat.tab = name; window.helpChat.shows.push(name); }};
      const Dialogs = {shortcuts() { window.helpActions.push("shortcuts"); }, settings() { window.helpActions.push("settings"); }};
      document.getElementById("toggle-chat").addEventListener("click", () => {
        window.helpActions.push("chat"); window.helpChat.toggles++;
        if (document.querySelector(".mobile-menu-tools")) {
          if (document.body.dataset.mobilePanel === "chat") delete document.body.dataset.mobilePanel;
          else document.body.dataset.mobilePanel = "chat";
        } else window.helpChat.open = !window.helpChat.open;
        App.lyrics.close();
      });
      App.api.request = async (...args) => { window.helpWrites.push(args); throw new Error("Help ne doit pas appeler une API en parcourant les guides"); };
    `);
    evaluate(source("whatsnew.js"));
    await evaluate("Views.whatsnew.render(document.getElementById('main'))");
    const initialPlayer = evaluate("JSON.stringify(App.player)");
    const initialPreferences = evaluate("JSON.stringify(App.preferences)");
    const selectedTheme = () => $('.help-theme[aria-pressed="true"]');
    const selectedGuide = () => $('.help-guide-button[aria-pressed="true"]');
    const chooseTheme = theme => $(`.help-theme[data-theme="${theme}"]`).click();
    const chooseGuide = guide => $(`.help-guide-button[data-guide="${guide}"]`).click();

    check("Help : nom court conservé dans le titre et le menu", () => {
      assert.equal($("#main h1").textContent, "Help");
      assert.equal(texts["nav.whatsnew"], "Help");
      assert.equal($('.topnav a[href="#/whatsnew"]').dataset.t, "nav.whatsnew");
      assert.equal($(".whatsnew-versions").getAttribute("href"), "#/versions");
    });
    check("Help : les trois mises en avant ouvrent leurs vrais guides", () => {
      const featured = [["chat", "social", "g1"], ["lyrics", "listen", "g4"], ["press", "press", "g2"]];
      assert.equal($$("button.help-feature").length, featured.length);
      for (const [feature, theme, guide] of featured) {
        $(`.help-feature[data-feature="${feature}"]`).click();
        assert.equal(selectedTheme().dataset.theme, theme);
        assert.equal(selectedGuide().dataset.guide, guide);
        assert.equal($("#help-guide-title").textContent, texts[`whatsnew.themes.${theme}.guides.${guide}.title`]);
      }
    });
    check("Help : les sept thèmes donnent accès à tous les guides sans modifier l’écoute", () => {
      const themes = [["listen", 5, "g4"], ["social", 6, "g1"], ["explore", 7, "g7"],
                      ["save", 6, "g3"], ["elsewhere", 5, "g1"], ["press", 5, "g2"], ["settings", 6, "g1"]];
      assert.equal($$(".help-theme").length, themes.length);
      let visited = 0;
      for (const [theme, count, defaultGuide] of themes) {
        chooseTheme(theme);
        assert.equal($$('.help-theme[aria-pressed="true"]').length, 1);
        assert.equal(selectedTheme().dataset.theme, theme);
        assert.equal(selectedGuide().dataset.guide, defaultGuide);
        assert.equal($("#help-theme-title").textContent, texts[`whatsnew.themes.${theme}.title`]);
        assert.equal($$(".help-guide-button").length, count);
        for (let index = 1; index <= count; index++) {
          const guide = "g" + index;
          chooseGuide(guide);
          visited++;
          assert.equal($$('.help-guide-button[aria-pressed="true"]').length, 1);
          assert.equal(selectedGuide().dataset.guide, guide);
          assert.equal($("#help-guide-title").textContent, texts[`whatsnew.themes.${theme}.guides.${guide}.title`]);
          assert.equal($$(".help-steps li").length, 3);
          assert.ok($$(".help-steps li").every(item => item.textContent.trim().length > 0));
          assert.ok(!/whatsnew\./.test($(".help-page").textContent), `Traduction manquante : ${theme}/${guide}`);
          assert.ok(!$(".help-page script"), "Le contenu des guides reste du texte");
          for (const image of $$(".help-illustration img")) {
            assert.ok(image.alt.trim(), "Chaque capture possède une alternative textuelle");
            assert.match(image.getAttribute("src"), /^\/static\/help\//);
            captures.add(image.getAttribute("src"));
          }
        }
      }
      assert.equal(visited, 40);
      assert.equal(evaluate("JSON.stringify(App.player)"), initialPlayer);
      assert.equal(evaluate("JSON.stringify(App.preferences)"), initialPreferences);
      assert.equal(writes.length, 0);
    });
    const assets = await Promise.all([...captures].map(async url => {
      const response = await fetch(base + url);
      return {url, status:response.status, type:response.headers.get("content-type"), size:(await response.arrayBuffer()).byteLength};
    }));
    check("Help : les captures des parcours illustrés sont servies par l’application", () => {
      assert.ok(assets.length >= 6, "Les parcours essentiels possèdent leurs captures");
      for (const asset of assets) {
        assert.equal(asset.status, 200, asset.url);
        assert.match(asset.type, /^image\//, asset.url);
        assert.ok(asset.size > 0, asset.url);
      }
    });
    check("Help : cibles accessibles, boutons natifs et focus du thème conservé", () => {
      const theme = $('.help-theme[data-theme="listen"]');
      theme.focus();
      theme.click();
      assert.equal(document.activeElement, theme);
      for (const button of $$(".help-theme, .help-guide-button, .help-feature")) {
        assert.equal(button.tagName, "BUTTON");
        assert.equal(button.type, "button");
        assert.ok(button.textContent.trim());
        const controls = button.getAttribute("aria-controls");
        assert.ok(controls, "Chaque sélecteur annonce le contenu qu’il contrôle");
        for (const id of controls.split(/\s+/)) assert.ok(document.getElementById(id), `Cible ARIA absente : ${id}`);
      }
    });
    check("Help : paroles synchronisées, RSS et labels expliqués sans promesse générale", () => {
      chooseTheme("listen"); chooseGuide("g4");
      assert.match($(".help-note").textContent, /synchronis/i);
      assert.match($(".help-note").textContent, /estimé|estime|disponib/i);
      chooseTheme("press"); chooseGuide("g2");
      assert.match($(".help-lesson").textContent, /RSS/);
      assert.match($(".help-lesson").textContent, /tout le monde|tous les membres/i);
      chooseGuide("g3");
      assert.match($(".help-lesson").textContent, /pour vous|pour soi|personnel/i);
      chooseTheme("explore"); chooseGuide("g7");
      assert.match($(".help-note").textContent, /édition/);
      assert.match($(".help-note").textContent, /artiste/);
      assert.match($(".help-steps").textContent, /album/i);
    });
    check("Help : recommandations privées, archives et limite YouTube conservées", () => {
      chooseTheme("social"); chooseGuide("g5");
      assert.match($(".help-lesson").textContent, /privé/);
      chooseGuide("g6");
      assert.match($(".help-lesson").textContent, /archiv/);
      chooseTheme("elsewhere"); chooseGuide("g5");
      assert.match($(".help-note").textContent, /120 recherches/);
    });
    check("Help : liens vers les mix et l’import existants", () => {
      chooseTheme("explore"); chooseGuide("g4");
      assert.ok($('a.whatsnew-link[href="#/mix"]'));
      chooseTheme("save"); chooseGuide("g5");
      assert.ok($('a.whatsnew-link[href^="#/import"]'));
      assert.match($(".help-lesson").textContent, /Spotify/);
      assert.match($(".help-lesson").textContent, /CSV/);
    });
    check("Help : les actions ouvrent les commandes existantes sans démarrer de lecture", () => {
      for (const [theme, guide, action] of [["listen", "g4", "lyrics"], ["listen", "g2", "queue"],
           ["listen", "g5", "shortcuts"], ["settings", "g1", "settings"], ["social", "g1", "chat"]]) {
        chooseTheme(theme); chooseGuide(guide);
        const button = $(`.help-action[data-action="${action}"]`);
        assert.ok(button, `Action absente : ${action}`);
        button.click();
        assert.equal(actions.at(-1), action);
      }
      chooseTheme("explore"); chooseGuide("g2");
      $('.help-action[data-action="search"]').click();
      assert.equal(document.activeElement, $("#search"));
      assert.equal(evaluate("JSON.stringify(App.player)"), initialPlayer);
      assert.equal(writes.length, 0);
    });
    check("Help : ouvrir le salon revient à la discussion sans fermer un panneau déjà ouvert", () => {
      chooseTheme("social"); chooseGuide("g1");
      const button = $('.help-action[data-action="chat"]');
      const chat = window.helpChat;
      chat.open = true; chat.tab = "mentions";
      window.helpLyricsOpen = true;
      const toggles = chat.toggles;
      button.click();
      assert.equal(chat.tab, "room");
      assert.equal(chat.open, true);
      assert.equal(chat.toggles, toggles);
      assert.equal(window.helpLyricsOpen, false);
      assert.equal(chat.shows.at(-1), "room");
    });
    check("Help : le salon mobile utilise son volet et préserve les préférences du bureau", () => {
      const tools = document.createElement("div"); tools.className = "mobile-menu-tools";
      $("#app").appendChild(tools);
      const chat = window.helpChat, button = $('.help-action[data-action="chat"]');
      try {
        chat.open = true; chat.tab = "mentions";
        delete document.body.dataset.mobilePanel;
        const toggles = chat.toggles;
        button.click();
        assert.equal(document.body.dataset.mobilePanel, "chat");
        assert.equal(chat.tab, "room");
        assert.equal(chat.toggles, toggles + 1, "Le bouton mobile est appelé même si le réglage PC est ouvert");
        chat.open = false; chat.tab = "mentions";
        button.click();
        assert.equal(document.body.dataset.mobilePanel, "chat");
        assert.equal(chat.tab, "room");
        assert.equal(chat.toggles, toggles + 1, "Un volet mobile déjà ouvert reste ouvert");
        assert.equal(evaluate("JSON.stringify(App.preferences)"), initialPreferences);
        assert.equal(writes.length, 0);
      } finally { tools.remove(); delete document.body.dataset.mobilePanel; }
    });
    check("Help : rendre la page à nouveau ne duplique ni navigation ni contenu", () => {
      evaluate("Views.whatsnew.render(document.getElementById('main'))");
      assert.equal($$(".help-page").length, 1);
      assert.equal($$(".help-theme").length, 7);
      assert.equal($$(".help-lesson").length, 1);
      assert.equal(writes.length, 0);
      assert.equal(errors.length, 0, errors.join("\n"));
    });
    console.log(checks + " groupes de contrôles Help réussis, 40 guides parcourus");
  } finally { window.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
