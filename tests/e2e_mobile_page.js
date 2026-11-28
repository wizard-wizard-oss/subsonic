// Parcours de la vraie page mobile sur le faux Subsonic, sans API de navigation simulée.
// Usage : node tests/e2e_mobile_page.js PORT [jsdom]
const assert = require("node:assert/strict");
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + process.argv[2];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

(async () => {
  let cookie = "", changeScreen;
  const requests = [], errors = [], screen = {matches:true, addEventListener(kind, callback) { changeScreen = callback; }};
  const dom = await JSDOM.fromURL(base + "/", {
    runScripts:"dangerously", resources:"usable", pretendToBeVisual:true,
    beforeParse(window) {
      window.matchMedia = () => screen;
      window.CSS = {escape: value => String(value)}; // identifiants alphanumériques du faux Subsonic
      window.fetch = async (url, options = {}) => {
        requests.push({url:String(url), method:options.method || "GET", body:options.body});
        const response = await fetch(new URL(url, base), {...options, headers:{...options.headers, Cookie:cookie}});
        if (response.headers.get("set-cookie")) cookie = response.headers.get("set-cookie").split(";")[0];
        return response;
      };
      window.EventSource = class { addEventListener() {} close() {} };
      window.Element.prototype.scrollIntoView = function () {};
      window.HTMLMediaElement.prototype.play = () => Promise.resolve();
      window.HTMLMediaElement.prototype.pause = function () {};
      window.HTMLMediaElement.prototype.load = function () {};
      window.addEventListener("error", event => errors.push(event.message));
    }
  });
  const window = dom.window, document = window.document, $ = selector => document.querySelector(selector);
  const until = async (test, description) => {
    for (let attempt = 0; attempt < 300; attempt++) { if (test()) return; await delay(20); }
    throw new Error("Attente dépassée : " + description);
  };
  try {
    await until(() => !$("#login").hidden, "page de connexion");
    assert.equal($(".mobile-menu-tools"), null);
    $('#login-form input[name="username"]').value = "alice";
    $('#login-form input[name="password"]').value = "secret";
    $('#login-form button[type="submit"]').click();
    await until(() => $(".mobile-menu-tools") && window.eval("App.music.started"), "application mobile connectée");
    const sidebar = window.eval("App.preferences.sidebar"), chat = window.eval("App.preferences.chat_panel");
    $("#toggle-sidebar").click();
    assert.equal(document.body.dataset.mobilePanel, "navigation");
    await until(() => $(".sidebar-retry"), "premier chargement Subsonic refusé");
    $(".sidebar-retry").click();
    await until(() => $("#artist-list a.artist"), "artistes");
    assert.equal(document.activeElement.id, "artist-filter");
    console.log("OK mobile connecté : menu et vrais artistes accessibles");

    $("#tab-playlists").click();
    await until(() => !$("#panel-playlists").hidden && $("#playlist-list .playlist-note"), "playlists vides");
    $("#playlist-new").click();
    await until(() => $(".dialog-input"), "création de playlist existante");
    $(".dialog-input").value = "Playlist mobile";
    $(".dialog button.primary").click();
    await until(() => $("#playlist-list a.playlist-row") && window.eval("App.music.route.view") === "playlist", "playlist créée");
    $("#toggle-sidebar").click();
    const playlist = $("#playlist-list a.playlist-row"), destination = playlist.getAttribute("href");
    playlist.click();
    await until(() => window.location.hash === destination && $("#main h1"), "page de playlist");
    assert.equal(document.body.dataset.mobilePanel, undefined);
    assert.ok(!$("#main").inert);
    console.log("OK mobile connecté : choisir une playlist ouvre sa page et ferme le menu");

    $("#toggle-sidebar").click();
    $('#panel-playlists .playlist-see-all').click();
    await until(()=>$(".playlist-card"),"galerie mobile");
    assert.equal(window.eval("App.music.route.view"),"playlists");
    assert.equal(document.body.dataset.mobilePanel,undefined);
    assert.equal($(".playlist-card-name").textContent,"Playlist mobile");

    $("#toggle-sidebar").click();
    $('.topnav a[href="#/favorites"]').click();
    await until(() => window.eval("App.music.route.view") === "favorites", "favoris");
    assert.equal(document.body.dataset.mobilePanel, undefined);
    $("#toggle-chat").click();
    assert.equal(document.body.dataset.mobilePanel, "chat");
    assert.equal(window.eval("App.chatPanel.thread.isVisible()"), true);
    window.eval('App.chatPanel.thread.startReply({id:1, author:"bob", body:"Message de test"})');
    $(".composer-input").dispatchEvent(new window.KeyboardEvent("keydown", {key:"Escape", bubbles:true, cancelable:true}));
    assert.equal(document.body.dataset.mobilePanel, "chat");
    assert.equal(window.eval("App.chatPanel.thread.replyTo"), null);
    $(".composer-input").dispatchEvent(new window.KeyboardEvent("keydown", {key:"Escape", bubbles:true, cancelable:true}));
    assert.equal(document.body.dataset.mobilePanel, undefined);
    $("#toggle-chat").click();
    $("#toggle-chat").click();
    assert.equal(window.eval("App.chatPanel.thread.isVisible()"), false);
    console.log("OK mobile connecté : liens existants et salon visibles à la demande");

    $("#toggle-sidebar").click();
    $("#open-settings").click();
    await until(() => $('.dialog[role="dialog"]'), "réglages existants");
    assert.equal(document.body.dataset.mobilePanel, undefined);
    assert.equal(window.eval("App.preferences.sidebar"), sidebar);
    assert.equal(window.eval("App.preferences.chat_panel"), chat);
    assert.ok(!requests.some(request => request.url === "/api/preferences" && /"(sidebar|chat_panel)":/.test(request.body || "")));
    screen.matches = false; changeScreen();
    assert.ok($("#sidebar > .topnav"));
    assert.equal(document.body.dataset.desktopLayout, "true");
    assert.ok($(".topbar-right > #account-menu #me"));
    assert.equal($(".mobile-menu-tools"), null);
    assert.equal(errors.length, 0, errors.join("\n"));
    console.log("OK mobile connecté : réglages PC préservés, retour au bureau et aucune erreur JavaScript");
  } finally { window.close(); }
})().then(() => process.exit(0)).catch(error => { console.error(error); process.exit(1); });
