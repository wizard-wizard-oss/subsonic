// Édition PC dans jsdom : connexion, barre des artistes, album, étoiles, salon en temps réel, commentaires.
// Usage : node tests/e2e_webapp.js PORT [jsdom] [instantané.html]
const port = process.argv[2];
const {JSDOM} = require(process.argv[3] || "jsdom");
const snapshotPath = process.argv[4];
const http = require("http");
const fs = require("fs");
const path = require("path");
const base = "http://127.0.0.1:" + port;
const wait = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok) => { console.log((ok ? "OK   " : "FAIL ") + name); if (!ok) failures++; };

/** Client HTTP avec son cookie (un « autre utilisateur » piloté par le test). */
function client() {
  const jar = {cookie: ""};
  const call = async (method, url, body) => {
    const headers = {"Cookie": jar.cookie};
    if (method === "POST") Object.assign(headers, {"Content-Type": "application/json", "X-Requested-With": "pmw"});
    const response = await fetch(new URL(url, base), {method, headers, body: body ? JSON.stringify(body) : undefined});
    const set = response.headers.get("set-cookie");
    if (set) jar.cookie = set.split(";")[0];
    return response;
  };
  return {jar, get: url => call("GET", url), post: (url, body) => call("POST", url, body)};
}

/** EventSource minimal pour Node (jsdom n'en a pas) : même protocole, avec le cookie de la page. */
function makeEventSource(jar) {
  return class EventSource {
    constructor(url) {
      this.listeners = {};
      this.closed = false;
      this.connect(url);
    }
    addEventListener(kind, fn) { (this.listeners[kind] = this.listeners[kind] || []).push(fn); }
    fire(kind, data) { (this.listeners[kind] || []).forEach(fn => fn({data})); }
    connect(url) {
      this.request = http.get(new URL(url, base), {headers: {Cookie: jar.cookie, Accept: "text/event-stream"}}, res => {
        this.fire("open");
        let buffer = "", kind = "message", data = "";
        res.setEncoding("utf8");
        res.on("data", chunk => {
          buffer += chunk;
          let index;
          while ((index = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, index);
            buffer = buffer.slice(index + 1);
            if (line === "") { if (data) this.fire(kind, data); kind = "message"; data = ""; }
            else if (line.startsWith("event: ")) kind = line.slice(7);
            else if (line.startsWith("data: ")) data += line.slice(6);
          }
        });
        res.on("end", () => { if (!this.closed) { this.fire("error"); setTimeout(() => this.connect(url), 300); } });
      });
      this.request.on("error", () => {});
    }
    close() { this.closed = true; this.request.destroy(); }
  };
}

(async () => {
  const jar = {cookie: ""};
  const dom = await JSDOM.fromURL(base + "/", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = async (url, options) => {
        options = Object.assign({}, options);
        options.headers = Object.assign({}, options.headers, {Cookie: jar.cookie});
        const response = await fetch(new URL(url, base), options);
        const set = response.headers.get("set-cookie");
        if (set) jar.cookie = set.split(";")[0].endsWith("=") ? "" : set.split(";")[0];
        return response;
      };
      w.EventSource = makeEventSource(jar);
      // faux IntersectionObserver : rien n'approche de l'écran tant que le test ne le dit pas (show)
      w.observers = [];
      w.IntersectionObserver = class {
        constructor(callback) { this.callback = callback; this.nodes = new Set(); w.observers.push(this); }
        observe(node) { this.nodes.add(node); }
        unobserve(node) { this.nodes.delete(node); }
        disconnect() { this.nodes.clear(); }
        show() { this.callback([...this.nodes].map(target => ({target, isIntersecting: true}))); }
      };
      w.CSS = w.CSS || {escape: s => String(s).replace(/["\\]/g, "\\$&")};
      w.Element.prototype.scrollIntoView = function () {};
      const proto = w.HTMLMediaElement.prototype;
      proto.play = function () { Object.defineProperty(this, "paused", {value: false, configurable: true}); this.dispatchEvent(new w.Event("play")); return Promise.resolve(); };
      proto.pause = function () { Object.defineProperty(this, "paused", {value: true, configurable: true}); this.dispatchEvent(new w.Event("pause")); };
      proto.load = function () {};
      w.errors = [];
      w.addEventListener("error", e => w.errors.push(e.message));
    },
  });
  const w = dom.window, d = w.document, $ = s => d.querySelector(s), $$ = s => Array.from(d.querySelectorAll(s));
  const until = async (test, ms) => { for (let i = 0; i < (ms || 3000) / 50; i++) { if (test()) return true; await wait(50); } return false; };
  const type = (input, text) => { input.value = text; input.dispatchEvent(new w.Event("input")); };
  const key = (target, k, extra) => target.dispatchEvent(new w.KeyboardEvent("keydown", Object.assign({key: k, bubbles: true}, extra || {})));

  // --- connexion ---
  await until(() => !$("#login").hidden);
  check("page de connexion en français", $("#login h1").textContent === "Connexion");
  check("mot de passe oublié : aide cachée au départ", $("#login-forgot-help").hidden);
  $("#login-forgot").click();
  check("mot de passe oublié : l'aide renvoie à l'administrateur",
    !$("#login-forgot-help").hidden && $("#login-forgot-help").textContent.includes("administrateur") &&
    $("#login-forgot").getAttribute("aria-expanded") === "true");
  $("#login-forgot").click();
  check("mot de passe oublié : l'aide se referme", $("#login-forgot-help").hidden);
  const form = $("#login-form");
  form.elements.username.value = "bob"; form.elements.password.value = "mauvais";
  form.dispatchEvent(new w.Event("submit", {cancelable: true}));
  check("mauvais mot de passe expliqué", await until(() => $("#login-error").textContent.includes("incorrect")));
  form.elements.password.value = "pw2";
  form.dispatchEvent(new w.Event("submit", {cancelable: true}));
  check("connecté avec son compte Subsonic", await until(() => !$("#app").hidden && $("#me .me-name").textContent === "bob"));

  // --- barre des artistes ---
  check("barre des artistes : attente expliquée", await until(() => $(".sidebar-note") &&
        $(".sidebar-note").textContent.startsWith("Chargement des artistes")));
  check("barre des artistes : échec expliqué, « Réessayer »", await until(() => $(".sidebar-retry")) &&
        $(".sidebar-note.error").textContent === "Serveur Subsonic injoignable");
  $(".sidebar-retry").click();
  check("affichage paresseux : seule la première lettre construite", await until(() => $$(".letter-group").length === 2) &&
        $$(".artist").length === 1 && $$(".letter-head").map(h => h.textContent).join() === "A,B");
  w.observers.forEach(o => o.show());                         // B approche de l'écran
  check("barre des artistes remplie, par lettre", await until(() => $$(".artist").length === 2));
  type($("#artist-filter"), "bjo");
  check("filtre sans accents", $$(".artist").length === 1 && $(".artist").textContent.startsWith("Björk"));
  type($("#artist-filter"), "");
  $$(".letter")[1].click();
  check("clic sur une lettre : ses artistes construits", $$(".artist").length === 2);
  type($("#artist-filter"), "");
  check("barre : dossiers d'artistes, sans Incoming", $$(".letter-head").map(h => h.textContent).join() === "A,B" &&
        $(".artist").getAttribute("href") === "#/artist/fdir-ar1");
  w.location.hash = "#/artist/ar3";                          // lien par l'identifiant des tags : ramené au dossier
  check("artiste en cours d'une lettre pas encore construite : surligné", await until(() =>
        $(".artist.current") && $(".artist.current").dataset.id === "fdir-ar3"));
  w.location.hash = "#/";
  let reloaded = false;
  const app = w.eval("App"), listCalls = app.api.get;
  app.api.get = url => { if (url === "/api/artists") reloaded = true; return listCalls.call(app.api, url); };
  app.live.emit("artists");                                 // Subsonic a scanné : la barre se recharge seule
  check("bibliothèque changée : barre rechargée sans message d'attente", await until(() => reloaded) &&
        !$(".sidebar-note") && await until(() => $$(".artist").length >= 1));
  app.api.get = async (url, params) => url === "/api/artists"          // un dossier « Compilations » épinglé
    ? Object.assign(await listCalls.call(app.api, url), {shortcuts: [{id: "fdir-ar3", name: "Compilations"}]})
    : listCalls.call(app.api, url, params);
  app.live.emit("artists");
  check("raccourci « Compilations » en haut de la barre", await until(() => !$("#artist-shortcuts").hidden &&
        $(".artist-shortcut").textContent === "Compilations" && $(".artist-shortcut").getAttribute("href") === "#/artist/fdir-ar3"));
  w.location.hash = "#/artist/fdir-ar3";
  check("raccourci surligné sur sa page", await until(() => $(".artist-shortcut.current")));
  w.location.hash = "#/";
  app.api.get = listCalls;
  check("mode fixe par défaut", d.body.dataset.sidebar === "pinned");

  // --- accueil ---
  check("accueil : derniers albums", await until(() => $$(".album-card").length >= 3));
  check("accueil : plus écoutés, avec « Écouté 12 fois »", await until(() => $(".most-played .play-count") &&
        $(".most-played .play-count").textContent === "Écouté 12 fois"));

  // --- pochettes : la flèche existante lit l'album, la carte reste un lien séparé ---
  const homeAlbum = $$(".album-card").find(card => card.querySelector(".album-name").textContent === "Arrival");
  const homePlay = homeAlbum.querySelector(".album-card-play");
  check("accueil : même flèche de lecture sur les pochettes", $$(".album-card-play").length === $$(".album-card").length &&
        homePlay.querySelector("svg path").getAttribute("d") === w.eval("ICONS.play") &&
        homePlay.getAttribute("aria-label") === "Lire l’album « Arrival »" && !homePlay.closest("a"));
  const beforeAlbumPlay = app.api.get;
  let releaseAlbumPlay, albumPlayCalls = 0;
  const albumReady = new Promise(resolve => { releaseAlbumPlay = resolve; });
  app.api.get = async function(url, params) {
    if (url === "/api/album") { albumPlayCalls++; await albumReady; }
    return beforeAlbumPlay.call(this, url, params);
  };
  homePlay.click();
  homePlay.click();
  check("accueil : un seul chargement de l'album à la fois", homePlay.disabled && albumPlayCalls === 1);
  releaseAlbumPlay();
  check("accueil : l'album se lit en entier sans quitter l'accueil", await until(() => !homePlay.disabled &&
        w.eval('App.player.current && App.player.current.id === "s1" && App.player.queue.length === 2')) &&
        w.location.hash === "#/" && w.eval('App.player.queue.map(s => s.id).join()') === "s1,s2");
  const albumQueue = w.eval('App.player.queue.map(s => s.id).join()');
  app.api.get = async function(url, params) {
    if (url === "/api/album") throw w.eval('new ApiError(503, "subsonic.unreachable")');
    return beforeAlbumPlay.call(this, url, params);
  };
  homePlay.click();
  check("accueil : erreur expliquée sans perdre la file", await until(() => !homePlay.disabled &&
        $$(".toast.error").some(t => t.textContent === "Serveur Subsonic injoignable")) &&
        w.eval('App.player.queue.map(s => s.id).join()') === albumQueue && w.eval('App.player.current.id') === "s1");
  app.api.get = beforeAlbumPlay;
  homeAlbum.querySelector(".album-name").click();
  check("accueil : cliquer le nom ouvre la fiche de l'album", await until(() => $(".album-info h1") &&
        $(".album-info h1").textContent === "Arrival") && w.location.hash === "#/album/al1");

  // --- page Albums : listes de Subsonic en onglets ---
  w.location.hash = "#/albums/frequent";
  check("albums : 9 onglets, « Plus écoutés » actif", await until(() => $$(".tabs .tab").length === 9 &&
        $(".tabs .tab.active").textContent === "Plus écoutés"));
  check("albums : triés par écoutes", await until(() => $$(".album-card .album-name").map(n => n.textContent).join() ===
        "Arrival,Post,Waterloo"));
  check("albums : lien Albums surligné", $$(".topnav a.active").map(a => a.getAttribute("href")).join() === "#/albums/newest");
  w.location.hash = "#/albums/genre";
  check("albums : genres en pastilles, avec leur nombre", await until(() => $$(".chips.big .chip").length === 2) &&
        $(".chips.big .chip").textContent === "Pop 2");
  $(".chips.big .chip").click();
  w.location.hash = $(".chips.big .chip").getAttribute("href");
  check("albums : un genre", await until(() => $$(".album-card").length === 2 && $(".section-head h2").textContent === "Pop"));
  w.location.hash = "#/albums/decade/1970";
  check("albums : années 1970", await until(() => $(".section-head h2") && $(".section-head h2").textContent === "Années 1970" &&
        $$(".album-card").length === 2));
  check("albums : pas de « Afficher plus » quand tout est là", $("button.more").hidden);

  // --- artiste : titres populaires (Last.fm par Subsonic) ---
  w.location.hash = "#/artist/ar1";
  check("artiste : titres populaires", await until(() => $$(".popular tr.song").length === 3 &&
        $(".popular .section-head h2").textContent === "Titres populaires"));
  check("artiste : biographie (Wikipédia, photo, source)", await until(() => $(".artist-bio .bio-text p")) &&
        $(".artist-bio h2").textContent === "Biographie" &&
        $(".artist-bio .bio-text p").textContent.startsWith("ABBA est un groupe") &&
        $(".bio-photo").getAttribute("src") === "https://upload.wikimedia.org/abba.jpg" &&
        $(".bio-source a").textContent === "Wikipédia");
  check("artiste : artistes similaires (Last.fm par Subsonic)", await until(() => $$(".similar a.chip").length === 1) &&
        $(".similar a.chip").getAttribute("href") === "#/artist/ar3" && $(".similar h2").textContent === "Artistes similaires");
  $(".artist-radio").click();
  check("artiste : radio lancée", await until(() => w.eval("App.player.queue.length") >= 1));
  check("artiste : « Créer un mix » mène au créateur", $(".artist-mix").getAttribute("href") === "#/mix/ar1");
  check("artiste : albums = ses dossiers, liens vers le dossier", $$(".album-card .album-name").map(n => n.textContent).join() ===
        "Waterloo,Arrival" && $(".album-card .album-link").getAttribute("href").startsWith("#/album/fdir-"));

  // --- album, étoiles ---
  w.location.hash = "#/album/al1";
  check("page album", await until(() => $(".album-info h1") && $(".album-info h1").textContent === "Arrival"));
  check("album : « Télécharger » (droit Subsonic)", $("a.download") &&
        $("a.download").getAttribute("href") === "/api/download?album=al1");
  check("titres : « Télécharger ce titre » sur chaque ligne", $$("tr.song a.song-download").length === 2 &&
        $("tr.song a.song-download").getAttribute("href") === "/api/download?song=s1");
  check("artiste surligné dans la barre", await until(() => $(".artist.current") && $(".artist.current").dataset.id === "fdir-ar1"));
  check("titres de l'album", $$("tr.song").length === 2);
  // --- radio d'un titre : API réelle du faux Subsonic, attente et erreur sans perdre la file ---
  const songRadio = $('tr.song[data-id="s2"] .song-radio');
  check("radio d'un titre : bouton nommé sur chaque morceau Subsonic", $$("tr.song .song-radio").length === 2 &&
        songRadio.getAttribute("aria-label") === "Radio de ce titre");
  const beforeSongRadio = app.api.get;
  let releaseSongRadio, songRadioCalls = 0;
  const radioReady = new Promise(resolve => { releaseSongRadio = resolve; });
  app.api.get = async function(url, params) {
    if (url === "/api/radio/song") { songRadioCalls++; await radioReady; }
    return beforeSongRadio.call(this, url, params);
  };
  songRadio.click();
  songRadio.click();
  check("radio d'un titre : un seul chargement à la fois", songRadio.disabled &&
        songRadio.getAttribute("aria-busy") === "true" && songRadioCalls === 1);
  releaseSongRadio();
  check("radio d'un titre : le morceau choisi puis ses voisins dans la file", await until(() =>
        !songRadio.disabled && w.eval('App.player.current.id === "s2" && App.player.queue.length === 4')) &&
        w.eval('new Set(App.player.queue.map(s => s.id)).size === 4') && !songRadio.hasAttribute("aria-busy"));
  const radioQueue = w.eval('App.player.queue.map(s => s.id).join()');
  app.api.get = async function(url, params) {
    if (url === "/api/radio/song") throw w.eval('new ApiError(503, "subsonic.unreachable")');
    return beforeSongRadio.call(this, url, params);
  };
  songRadio.click();
  check("radio d'un titre : erreur expliquée, file conservée et bouton réutilisable", await until(() =>
        !songRadio.disabled && $$(".toast.error").some(t => t.textContent === "Serveur Subsonic injoignable")) &&
        w.eval('App.player.queue.map(s => s.id).join()') === radioQueue && w.eval('App.player.current.id') === "s2");
  app.api.get = beforeSongRadio;
  const radioRoles = app.user.roles;
  app.user.roles = radioRoles.filter(role => role !== "stream");
  const noStreamTable = w.eval('Views.songTable([{id: "s1", title: "Dancing Queen"}])');
  check("radio d'un titre : absente sans le droit d'écouter", !noStreamTable.querySelector(".song-radio"));
  noStreamTable.destroy();
  app.user.roles = radioRoles;

  // --- labels et collaborations : choix d'édition, label, bibliothèque, membre et groupe ---
  const beforeExplore = app.api.get;
  app.api.get = async function(url, params) {
    const data = await beforeExplore.call(this, url, params);
    return url.startsWith("/api/explore/") ? Object.assign(data, {stale: true}) : data;
  };
  check("crédits : chargement à la demande", !!$(".explore-open") && !$(".explore-edition"));
  $(".explore-open").click();
  check("crédits : éditions proposées sans choix arbitraire", await until(() => $$(".explore-edition option").length === 3) &&
        $(".explore-edition").value === "" && !$(".explore-people"));
  check("crédits : consultables malgré un premier 503, cache ancien signalé", !!$(".explore-cached") &&
        $(".explore-cached").textContent.includes("informations conservées"));
  $(".explore-edition").value = "00000000-0000-4000-8000-000000000001";
  $(".explore-edition").dispatchEvent(new w.Event("change"));
  check("crédits : label, producteur et musicien cliquables", await until(() => $$(".explore-body > .explore-people .explore-link").length === 4) &&
        $$(".explore-link").some(a => a.textContent === "Polar") &&
        $(".album-exploration").textContent.includes("Production") && $(".album-exploration").textContent.includes("guitar"));
  check("album : membres du groupe affichés directement avec les crédits", await until(() => $(".explore-member-card")) &&
        $(".explore-member-card").textContent.includes("Musicien test") && $(".explore-connections").textContent.includes("toutes périodes"));
  $(".explore-member-projects").click();
  check("album : autres groupes du membre, sans répéter le groupe de départ", await until(() => $(".explore-member-links .explore-link")) &&
        $$(".explore-member-links .explore-link").length === 1 && $(".explore-member-links .explore-link").textContent === "Autre groupe" &&
        $(".explore-member-links").textContent.includes("1980") && $(".explore-member-links").textContent.includes("1990"));
  w.location.hash = $$(".explore-link").find(a => a.textContent === "Polar").getAttribute("href");
  check("label : catalogue et source", await until(() => $("#main h1") && $("#main h1").textContent === "Polar") &&
        $$(".explore-work").length === 1 && $(".explore-source").getAttribute("href").includes("musicbrainz.org/label/"));
  check("label : cache ancien signalé", !$(".explore-cached").hidden);
  $(".explore-find").click();
  check("label : album retrouvé dans sa bibliothèque", await until(() => $(".explore-local a")) &&
        $(".explore-local a").getAttribute("href") === "#/album/al1");
  $(".explore-more").click();
  check("label : catalogue paginé", await until(() => $$(".explore-work").length === 2) && $(".explore-more").hidden);
  w.location.hash = "#/explore/artist/00000000-0000-4000-8000-000000000003";
  check("groupe : membres et participations", await until(() => $("#main h1") && $("#main h1").textContent === "ABBA") &&
        $(".explore-people").textContent.includes("Membre du groupe") && $$(".explore-work").length === 2);
  w.location.hash = $(".explore-link").getAttribute("href");
  check("musicien : retour vers son groupe", await until(() => $("#main h1") && $("#main h1").textContent === "Musicien test") &&
        $(".explore-link").textContent === "ABBA");
  w.location.hash = $$(".explore-link").find(a => a.textContent === "Autre groupe").getAttribute("href");
  check("musicien : un autre projet s'ouvre", await until(() => $("#main h1") && $("#main h1").textContent === "Autre groupe"));
  app.api.get = beforeExplore;
  w.location.hash = "#/artist/ar1";
  await until(() => $(".artist-exploration .explore-artist-open"));
  $(".explore-artist-open").click();
  check("page artiste : homonymes proposés sans choisir arbitrairement", await until(() => $$(".explore-artist-choice option").length === 3) &&
        $(".explore-artist-choice").value === "" && !$(".explore-member-card"));
  $(".explore-artist-choice").value = "00000000-0000-4000-8000-000000000003";
  $(".explore-artist-choice").dispatchEvent(new w.Event("change"));
  check("page artiste : membres après choix de la bonne identité", await until(() => $(".artist-exploration .explore-member-card")));
  $(".explore-member-projects").click();
  check("page artiste : autres groupes du membre", await until(() => $(".explore-member-links .explore-link")) &&
        $(".explore-member-links .explore-link").textContent === "Autre groupe");
  w.location.hash = "#/album/al1";
  await until(() => $(".album-info h1") && $(".album-info h1").textContent === "Arrival");
  // --- pochette : crayon, recherche Last.fm, choix d'une image ---
  check("album : crayon pour changer la pochette (droit « upload »)", !!$(".cover-edit button.cover-pencil"));
  $(".cover-pencil").click();
  check("pochette : fenêtre préremplie (artiste, album)", await until(() => $(".cover-editor") &&
        $$(".cover-editor input")[0].value === "ABBA" && $$(".cover-editor input")[1].value === "Arrival"));
  $(".cover-row button").click();
  check("pochette : propositions de Last.fm", await until(() => $$(".cover-choice").length === 3));
  $$(".cover-choice")[1].click();
  const coverSaved = await until(() => !$(".cover-editor") && $$(".toast").some(t => t.textContent.includes("Pochette enregistrée")));
  check("pochette : enregistrée, fenêtre fermée", coverSaved || (console.log("  état : " + ($(".cover-status") || {}).textContent), false));
  const stars = $$(".album-rating .star");
  check("5 étoiles, rien de noté", stars.length === 5 && !stars.some(s => s.classList.contains("on")) &&
        $(".stars-summary").textContent.includes("Pas encore"));
  stars[3].click();
  check("4 étoiles enregistrées", await until(() => $$(".album-rating .star.on").length === 4 &&
        $(".stars-summary").textContent === "Moyenne de tous les comptes : 4"));
  check("écoutes de l'album affichées", $(".album-info p.muted").textContent.endsWith("Écouté 12 fois"));
  const alice = client();
  await alice.post("/api/login", {username: "alice", password: "secret"});
  const albumForAlice = await (await alice.get("/api/album?id=al1")).json();
  check("Subsonic garde la note de bob, pas celle d'alice", albumForAlice.rating.mine === 0 && albumForAlice.rating.average === 4);

  // --- lecture ---
  $$("tr.song")[1].dispatchEvent(new w.MouseEvent("dblclick", {bubbles: true}));
  check("double-clic : lecture", await until(() => $(".player-title").textContent === "Knowing Me"));
  check("titre en cours surligné", $$("tr.song")[1].classList.contains("playing"));
  key(d.body, " ");
  check("Espace : pause", w.eval("App.player.audio.paused"));

  // --- survol du lecteur : détails, puis file d'attente en bas (réordonnable) ---
  const titlesInQueue = () => $$(".queue-row .col-title").map(c => c.textContent).join();
  $("#player").dispatchEvent(new w.MouseEvent("mouseenter"));
  check("survol du lecteur : détails du titre (album, année…)", await until(() => d.body.dataset.player === "open") &&
        $(".player-details").textContent.includes("Arrival"));
  check("la souris reste : file d'attente ouverte en bas", await until(() => !$("#queue").hidden) &&
        titlesInQueue() === "Dancing Queen,Knowing Me" && $(".queue-count").textContent.startsWith("2 titres"));
  check("file : titre en cours marqué", $$(".queue-row")[1].classList.contains("current"));
  const rows = $$(".queue-row");
  rows[0].dispatchEvent(new w.MouseEvent("dragstart", {bubbles: true}));
  rows[1].dispatchEvent(new w.MouseEvent("dragover", {bubbles: true, cancelable: true, clientY: 10}));
  rows[1].dispatchEvent(new w.MouseEvent("drop", {bubbles: true, cancelable: true, clientY: 10}));
  check("glisser-déposer : ordre changé, la lecture continue", titlesInQueue() === "Knowing Me,Dancing Queen" &&
        w.eval("App.player.index") === 0 && w.eval("App.player.current.title") === "Knowing Me");
  $(".queue-actions .link-button:last-child").click();
  check("« Annuler » : ordre d'avant", titlesInQueue() === "Dancing Queen,Knowing Me" && w.eval("App.player.index") === 1);
  key($$(".queue-row")[0], "ArrowDown", {altKey: true});
  check("Alt+↓ : titre descendu", titlesInQueue() === "Knowing Me,Dancing Queen");
  $("#main").dispatchEvent(new w.MouseEvent("mousedown", {bubbles: true}));
  check("clic ailleurs : file fermée", $("#queue").hidden && !d.body.dataset.player);
  $(".queue-toggle").click();
  check("bouton ☰ : file rouverte", !$("#queue").hidden);
  $("#queue").dispatchEvent(new w.MouseEvent("mouseleave"));
  check("la souris repart au-dessus : file fermée", await until(() => $("#queue").hidden));
  $(".queue-toggle").click();
  key(d.body, "Escape");
  check("Échap : file fermée", $("#queue").hidden);

  // --- paroles : à droite à la place du salon, ligne chantée en surbrillance ---
  key(d.body, "l");
  check("L : paroles à la place du salon", d.body.dataset.lyrics === "open" &&
        w.getComputedStyle($("#chat-panel")).display === "none");
  check("paroles synchronisées affichées", await until(() => $$(".lyric-line").length === 2) &&
        $(".lyrics-source").textContent === "Source : LRCLIB");
  check("anecdotes au-dessus des paroles (sortie de l'album)", await until(() => !$(".facts-box").hidden) &&
        $(".fact-kind").textContent === "Sortie" && $(".fact-text").textContent.includes("« Arrival », sorti en 1976"));
  Object.defineProperty(w.eval("App.player.audio"), "currentTime", {value: 5, configurable: true, writable: true});
  w.eval("App.player.audio").dispatchEvent(new w.Event("timeupdate"));
  check("ligne en cours suivie en rythme", await until(() => $(".lyric-line.current") &&
        $(".lyric-line.current").textContent === "Deuxième ligne"));
  key(d.body, "c");
  check("C : le salon reprend sa place", !d.body.dataset.lyrics && w.getComputedStyle($("#chat-panel")).display !== "none");

  // --- musique d'ailleurs : Jamendo, YouTube (faux lecteur officiel), vidéo refusée ---
  const yt = {players: []};
  w.YT = {Player: class {
    constructor(node, options) { this.options = options; this.video = options.videoId; this.state = -1; yt.players.push(this);
                                 setTimeout(() => this.setState(1), 10); }
    setState(state) { this.state = state; this.options.events.onStateChange({data: state}); }
    refuse(code) { this.options.events.onError({data: code}); }
    loadVideoById(id) { this.video = id; setTimeout(() => this.setState(1), 10); }
    playVideo() { this.setState(1); } pauseVideo() { this.setState(2); } stopVideo() { this.state = 5; }
    getCurrentTime() { return 3; } getDuration() { return 320; } setVolume() {} seekTo() {}
  }};
  w.open = (url) => { yt.opened = url; };
  w.location.hash = "#/search/army";
  check("ailleurs : YouTube proposé même quand la bibliothèque a le titre", await until(() => !!$(".ext-youtube")) &&
        $(".ext-youtube").textContent.startsWith("Pas ce que vous cherchiez"));
  w.location.hash = "#/search/" + encodeURIComponent("one more time");
  check("ailleurs : Jamendo tout de suite", await until(() => !!$(".ext-youtube") &&
        $(".ext-youtube").textContent.startsWith("Pas dans la bibliothèque") && $(".ext-part.jamendo .ext-songs") &&
        $(".ext-part.jamendo .title span").textContent === "Groove"));
  check("ailleurs : YouTube seulement sur demande", $$(".ext-part.youtube tr.song").length === 0 && !!$(".ext-youtube"));
  $(".ext-youtube").click();
  check("ailleurs : résultats YouTube (live écarté)", await until(() => $$(".ext-part.youtube tr.song").length === 2));
  $$(".ext-part.youtube .row-play")[0].click();
  check("YouTube : lecteur officiel dans la fenêtre vidéo", await until(() => yt.players.length === 1 &&
        d.body.dataset.video === "on" && yt.players[0].video === "abc123def45" && !w.eval("App.player.audio.paused")));
  check("YouTube : titre dans le lecteur", $(".player-title").textContent.startsWith("Daft Punk - One More Time"));
  yt.players[0].refuse(150);
  check("vidéo refusée : autre version lancée", await until(() => yt.players[0].video === "otherone123" &&
        w.eval("App.player.current.youtubeId") === "otherone123"));
  w.eval(`window.asked = []; const post = App.api.post.bind(App.api);
           App.api.post = (path, body) => { window.asked.push(path); return post(path, body); };`);
  yt.players[0].refuse(150);
  check("rien de sûr : « Ouvrir sur YouTube » proposé", await until(() => !!$(".toast-action")));
  check("autre version refusée aussi : notée, sans chercher une troisième", await until(() =>
        w.eval("window.asked").includes("/api/ext/unplayable")) && !w.eval("window.asked").includes("/api/ext/alternative"));
  $(".toast-action").click();
  check("ouverture sur youtube.com", yt.opened === "https://www.youtube.com/watch?v=otherone123");
  await w.eval('App.api.post("/api/ext/played", {id: "otherone123"})');   // plus tard, elle passe : lue ici
  w.location.hash = "#/search/" + encodeURIComponent("one more");
  check("ailleurs : vidéos déjà trouvées proposées sans recherche YouTube", await until(() =>
        $$(".youtube-known tr.song").length > 0 && $$(".ext-part.youtube tr.song").length === 0));
  await until(() => !!$(".ext-youtube"));
  $(".ext-youtube").click();
  check("vidéo lue ici : en tête avec « déjà lue ici », la refusée n'est plus proposée", await until(() =>
        $$(".ext-part.youtube tr.song").length === 1 && $(".ext-part.youtube .ext-played") &&
        $(".ext-part.youtube tr.song").dataset.id === "yt-otherone123"));
  $(".ext-part.jamendo .row-play").click();
  check("Jamendo : son direct, fenêtre vidéo fermée", await until(() => !d.body.dataset.video &&
        w.eval("App.player.audio.audio.src").startsWith("https://prod-1.storage.jamendo.com/")));
  w.eval("App.player.audio").pause();

  // --- favoris d'ailleurs : cœur, liens collés (playlist YouTube, titre SoundCloud), lecteur officiel SoundCloud ---
  $(".ext-part.jamendo .ext-heart .heart").click();
  check("cœur d'un titre Jamendo : favori d'ailleurs", await until(() => !!$(".ext-part.jamendo .ext-heart .heart.on")));
  w.location.hash = "#/favorites";
  check("favoris : section « D'ailleurs » avec le titre Jamendo", await until(() =>
        $$(".ext-favorites tr.song").length === 1 && $(".ext-favorites .ext-source").textContent.startsWith("Jamendo")));
  const pasteLink = value => {
    $(".ext-link").value = value;
    $(".ext-link-form").dispatchEvent(new w.Event("submit", {cancelable: true}));
  };
  pasteLink("https://www.youtube.com/playlist?list=PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf");
  check("lien de playlist YouTube : vidéos lisibles ajoutées", await until(() => $$(".ext-favorites tr.song").length === 3) &&
        await until(() => $$(".toast").some(t => t.textContent.includes("2 titres ajoutés"))));
  check("lien de playlist YouTube : vidéo illisible signalée", $$(".toast").some(t => t.textContent.includes("1 vidéo ne peut pas")));
  pasteLink("https://www.youtube.com/playlist?list=LL");
  check("« J'aime » de YouTube : privée, expliqué", await until(() => $$(".toast").some(t => t.textContent.startsWith("Playlist privée"))));
  pasteLink("https://soundcloud.com/m83/midnight-city");
  check("lien SoundCloud : titre ajouté", await until(() => !!$('.ext-favorites tr.song[data-id="sc-29912345"]')) &&
        $('.ext-favorites tr.song[data-id="sc-29912345"] .title span').textContent === "Midnight City");
  // le cadre du lecteur SoundCloud n'est jamais chargé (jsdom irait le chercher sur Internet) : son adresse est gardée
  Object.defineProperty(w.HTMLIFrameElement.prototype, "src", {configurable: true,
    get() { return this.getAttribute("data-test-src") || ""; }, set(value) { this.setAttribute("data-test-src", value); }});
  const sc = {widgets: []};
  const scEvents = {READY: "ready", PLAY: "play", PAUSE: "pause", FINISH: "finish", PLAY_PROGRESS: "playProgress", ERROR: "error"};
  w.SC = {Widget: Object.assign(frame => {
    const widget = {frame, handlers: {}, bind(kind, fn) { this.handlers[kind] = fn; },
                    fire(kind, event) { if (this.handlers[kind]) this.handlers[kind](event); },
                    play() { this.fire(scEvents.PLAY); }, pause() { this.fire(scEvents.PAUSE); },
                    setVolume() {}, seekTo() {}, getDuration(callback) { callback(245000); }};
    sc.widgets.push(widget);
    setTimeout(() => { widget.fire(scEvents.READY); widget.fire(scEvents.PLAY); }, 10);
    return widget;
  }, {Events: scEvents})};
  $('.ext-favorites tr.song[data-id="sc-29912345"] .row-play').click();
  check("SoundCloud : lecteur officiel dans la fenêtre", await until(() => sc.widgets.length === 1 &&
        d.body.dataset.videoSource === "soundcloud" && !w.eval("App.player.audio.paused")) &&
        $(".soundcloud-frame").src.startsWith("https://w.soundcloud.com/player/?url=https%3A%2F%2Fapi.soundcloud.com%2Ftracks%2F29912345"));
  check("SoundCloud : durée lue par son API", w.eval("App.player.audio.duration") === 245);
  w.eval("delete App.player.audio.currentTime");          // figé par le parcours des paroles : on rend celui du moteur
  sc.widgets[0].fire(scEvents.PLAY_PROGRESS, {currentPosition: 12000});
  check("SoundCloud : position suivie", w.eval("App.player.audio.currentTime") === 12);
  w.eval("App.player.audio").pause();
  check("SoundCloud : pause", w.eval("App.player.audio.paused"));
  sc.widgets[0].fire(scEvents.ERROR);
  check("SoundCloud refuse : « Ouvrir sur SoundCloud » proposé", await until(() =>
        $$(".toast").some(t => t.textContent.includes("SoundCloud refuse"))));
  $$(".toast").filter(t => t.textContent.includes("SoundCloud refuse")).pop().querySelector(".toast-action").click();
  check("ouverture de la page SoundCloud", yt.opened === "https://soundcloud.com/m83/midnight-city");
  w.eval("App.player.audio").pause();
  w.location.hash = "#/album/al1";                        // retour à l'album pour la suite du parcours
  await until(() => $(".comments .composer-input"));

  // --- commentaires de l'album ---
  const comment = $(".comments .composer-input");
  type(comment, "Le meilleur album d'ABBA");
  key(comment, "Enter");
  check("commentaire publié sous l'album", await until(() => $$(".comments .message").length === 1 &&
        $(".comments .message-text").textContent.includes("meilleur")));

  // --- salon global ---
  const room = $("#chat-panel .composer-input");
  check("salon ouvert, vide au départ", !!room && $("#chat-panel .chat-empty") !== null);
  type(room, "Salut à tous, **écoutez** ça : https://exemple.fr");
  key(room, "Enter");
  check("message envoyé (gras + lien)", await until(() => $$("#chat-panel .message").length === 1) &&
        $("#chat-panel .message-text strong").textContent === "écoutez" &&
        $("#chat-panel .message-text a").getAttribute("rel").includes("noopener"));
  await alice.post("/api/chat/post", {topic: "general", body: "@bob tu as vu le nouvel album ? <img src=x onerror=alert(1)>"});
  check("message d'un autre en temps réel", await until(() => $$("#chat-panel .message").length === 2));
  // salon : le plus récent en bas, ou en haut si ChatThread.NEWEST_FIRST_IN_ROOM (mis de côté) est remis
  const newestFirst = w.eval("ChatThread.NEWEST_FIRST_IN_ROOM");
  const newest = () => newestFirst ? $$("#chat-panel .message")[0] : $$("#chat-panel .message").pop();
  const last = newest();
  check("salon : le plus récent du bon côté, la saisie aussi", last.textContent.includes("nouvel album") &&
        $("#chat-panel .chat-thread").firstElementChild.classList.contains("composer") === newestFirst);
  check("mention de moi mise en avant", last.classList.contains("mentions-me") && last.querySelector(".mention.me"));
  check("HTML d'un message jamais interprété", !last.querySelector("img") && last.textContent.includes("<img"));
  check("notification de mention", await until(() => $$(".toast").some(t => t.textContent.includes("alice vous a mentionné"))));

  // réponse, réaction, modification, suppression
  last.querySelector('.message-actions button[title="Répondre"]').click();
  check("barre « Réponse à alice »", !$("#chat-panel .composer-context").hidden &&
        $("#chat-panel .composer-context").textContent.includes("alice"));
  type(room, "Oui, génial");
  key(room, "Enter");
  check("réponse avec extrait du message", await until(() => $$("#chat-panel .message").length === 3 &&
        newest().querySelector(".reply-preview")));
  $$("#chat-panel .message")[1].querySelector('.message-actions button[title="Réagir"]').click();
  $$(".reaction-picker button")[0].click();
  check("réaction 👍 visible", await until(() => $$("#chat-panel .reaction.mine").length === 1));
  key(room, "ArrowUp");
  check("Flèche haut : modifier son dernier message", room.value === "Oui, génial" && $("#chat-panel .composer-context").textContent.includes("Modification"));
  type(room, "Oui, vraiment génial");
  key(room, "Enter");
  check("message modifié, marqué « modifié »", await until(() => newest().textContent.includes("vraiment") &&
        newest().querySelector(".edited")));

  // suggestions de @noms
  type(room, "@al");
  room.selectionStart = room.selectionEnd = 3;
  room.dispatchEvent(new w.Event("input"));
  check("suggestion @alice", !$("#chat-panel .mention-picker").hidden && $("#chat-panel .mention-picker li").textContent === "@alice");
  key(room, "Tab");
  check("Tab complète le nom", room.value === "@alice ");
  type(room, "");

  // « écrit… » et présence
  await alice.post("/api/chat/typing", {topic: "general"});
  check("« alice écrit… »", await until(() => $("#chat-panel .typing-line").textContent === "alice écrit…"));

  // partage d'album
  w.location.hash = "#/album/al3";
  await until(() => $(".album-info h1") && $(".album-info h1").textContent === "Post");
  $$(".album-actions button").find(b => b.textContent.includes("Partager")).click();
  check("album partagé : carte dans le salon", await until(() => $$("#chat-panel .attachment").length === 1 &&
        $("#chat-panel .attachment").getAttribute("href") === "#/album/al3"));

  // suppression par l'auteur (confirmation)
  const mine = newestFirst ? $$("#chat-panel .message.mine").pop() : $$("#chat-panel .message.mine")[0];   // le premier envoyé
  mine.querySelector('.message-actions button[title="Supprimer"]').click();
  check("confirmation avant suppression", await until(() => !!$(".dialog")));
  $$(".dialog button").find(b => b.textContent === "Supprimer").click();
  check("message supprimé pour tout le monde", await until(() => $$("#chat-panel .message.deleted").length === 1));
  const history = await (await alice.get("/api/chat/history?topic=general")).json();
  check("contenu supprimé jamais renvoyé", history.messages.some(m => m.deleted && m.body === ""));

  // non-lus quand le salon est fermé
  key(d.body, "c");
  check("C : salon fermé", await until(() => d.body.dataset.chat === "closed"));
  await alice.post("/api/chat/post", {topic: "general", body: "Quelqu'un ?"});
  check("pastille de non-lus", await until(() => !$("#chat-badge").hidden && $("#chat-badge").textContent === "1"));
  check("non-lus dans le titre de l'onglet", d.title.startsWith("(1)"));
  key(d.body, "c");
  check("salon rouvert : non-lus effacés", await until(() => $("#chat-badge").hidden));

  // mentions et recherche
  $$("#chat-panel .chat-tabs button")[1].click();
  check("onglet Mentions", await until(() => $$("#chat-panel .result-row").length === 1));
  $$("#chat-panel .chat-tabs button")[2].click();
  type($("#chat-panel .chat-search input"), "nouvel album");
  check("recherche dans le salon", await until(() => $$("#chat-panel .chat-search .result-row").length === 1, 2000));
  $$("#chat-panel .chat-tabs button")[0].click();

  // --- réglages : barre des artistes au survol ---
  $("#open-settings").click();
  const sidebarSelect = $(".dialog select");
  sidebarSelect.value = "hover";
  sidebarSelect.dispatchEvent(new w.Event("change"));
  check("réglage « au survol » appliqué", d.body.dataset.sidebar === "hover");
  check("réglages : droits du compte Subsonic", $$(".rights-list li.yes").length === 7 &&
        $(".rights-list li.no").textContent.includes("Administrer"));
  key(d.body, "Escape");
  check("Échap ferme la fenêtre", !$(".dialog"));
  $("#sidebar-edge").dispatchEvent(new w.MouseEvent("mouseenter"));
  check("la barre sort au survol du bord", await until(() => $("#sidebar").classList.contains("peek")));
  $("#sidebar").dispatchEvent(new w.MouseEvent("mouseleave"));
  check("et rentre quand la souris s'en va", await until(() => !$("#sidebar").classList.contains("peek")));
  const me = await (await fetch(base + "/api/me", {headers: {Cookie: jar.cookie}})).json();
  check("réglage enregistré pour cet utilisateur", me.preferences.sidebar === "hover");

  // --- raccourcis et recherche ---
  key(d.body, "?");
  check("? : aide des raccourcis", await until(() => $(".dialog") && $(".dialog").textContent.includes("Raccourcis")));
  key(d.body, "Escape");
  w.location.hash = "#/search/post";
  check("recherche : album trouvé", await until(() => $$(".album-card").some(c => c.textContent.includes("Post"))));
  w.location.hash = "#/";
  check("accueil : album commenté listé", await until(() => $$(".discussed-row").length === 1));
  check("accueil : mieux notés", $$(".album-card .stars").length >= 1);

  // --- Mix : mix rapides et créateur (comme sur le Pi) ---
  w.location.hash = "#/mix";
  check("mix : lien Mix dans le menu, 4 mix rapides", await until(() => $$(".mix-card").length === 4) &&
        $(".topnav a.active").getAttribute("href") === "#/mix");
  w.eval("App.player.queue = []");
  $(".mix-card[data-kind=random]").click();
  check("mix rapide « Au hasard » : lancé", await until(() => w.eval("App.player.queue.length") === 4));
  check("créateur : styles de la bibliothèque", await until(() => $$(".mix-genres .chip").length >= 2));
  const depths = $$(".mix-depths .chip");
  check("créateur : profondeur de 1 à 4 niveaux, 4 par défaut", depths.length === 4 &&
        depths.map(c => c.textContent).join(",") === "1 niveau,2 niveaux,3 niveaux,4 niveaux" &&
        $(".mix-depths .on").dataset.depth === "4");
  for (const chip of depths) {
    chip.click();
    chip.click();
    check("créateur : profondeur " + chip.dataset.depth + ", choix unique accessible",
          $$(".mix-depths .on").length === 1 && chip.classList.contains("on") &&
          depths.every(c => c.getAttribute("aria-pressed") === String(c === chip)));
  }
  depths[1].click();
  w.eval(`window.mixBuildRequests = []; window.mixOriginalPost = App.api.post;
          App.api.post = function (url, body) {
            if (url === "/api/mix/build") window.mixBuildRequests.push(JSON.parse(JSON.stringify(body)));
            return window.mixOriginalPost.call(this, url, body);
          };`);
  const pop = $$(".mix-genres .chip").find(c => c.textContent.startsWith("Pop"));
  pop.click();
  check("créateur : style choisi", pop.classList.contains("on"));
  type($(".mix-seed-input"), "bjö");
  check("créateur : artiste de départ proposé", await until(() => $$(".mix-seed-results .chip").length === 1));
  $(".mix-seed-results .chip").click();
  check("créateur : « Comme : Björk »", $(".mix-seed-chosen").textContent.startsWith("Comme : Björk"));
  w.eval("App.player.queue = []");
  $(".mix-play").click();
  check("créateur : mix lancé", await until(() => w.eval("App.player.queue.length") >= 1));
  check("créateur : lancement limité à 2 niveaux, artiste et style conservés",
        w.mixBuildRequests.length === 1 && w.mixBuildRequests[0].depth === 2 &&
        w.mixBuildRequests[0].seedArtistName === "Björk" && w.mixBuildRequests[0].genres.includes("pop"));
  depths[2].click();
  $(".mix-save").click();
  check("créateur : nom de playlist proposé", await until(() => $(".dialog-input")) && $(".dialog-input").value.length > 0);
  $(".dialog-ask button.primary").click();
  check("créateur : playlist enregistrée dans Subsonic", await until(() =>
        $$(".toast").some(t => t.textContent.startsWith("Playlist « "))));
  check("créateur : playlist construite avec 3 niveaux",
        w.mixBuildRequests.length === 2 && w.mixBuildRequests[1].depth === 3);
  w.eval("App.api.post = window.mixOriginalPost;");
  // Le chargement de l'artiste de la fiche doit précéder toute construction du mix.
  const beforeSeedLoad = app.api.get;
  let releaseSeedLoad;
  const seedReady = new Promise(resolve => { releaseSeedLoad = resolve; });
  app.api.get = async function(url, params) {
    if (url === "/api/artist" && params.id === "ar1") await seedReady;
    return beforeSeedLoad.call(this, url, params);
  };
  w.location.hash = "#/mix/ar1";
  check("créateur depuis la fiche : attente de l’artiste avant écoute et sauvegarde", await until(() =>
        $(".mix-seed-input") && $(".mix-play").disabled && $(".mix-save").disabled));
  const seedQueue = w.eval("App.player.queue.map(s => s.id).join()");
  $(".mix-play").click();
  check("créateur depuis la fiche : aucun mix sans l’artiste pendant le chargement",
        w.eval("App.player.queue.map(s => s.id).join()") === seedQueue);
  releaseSeedLoad();
  check("créateur depuis la page artiste : artiste déjà choisi", await until(() =>
        $(".mix-seed-chosen") && $(".mix-seed-chosen").textContent.startsWith("Comme : ABBA")) &&
        !$(".mix-play").disabled && !$(".mix-save").disabled);
  app.api.get = beforeSeedLoad;

  const beforeSeedBuild = app.api.post;
  let releaseSeedBuild, seedBuildCalls = 0, seedBuildOptions;
  const seedBuildReady = new Promise(resolve => { releaseSeedBuild = resolve; });
  app.api.post = async function(url, body) {
    if (url === "/api/mix/build") {
      seedBuildCalls++;
      seedBuildOptions = JSON.parse(JSON.stringify(body));
      await seedBuildReady;
    }
    return beforeSeedBuild.call(this, url, body);
  };
  $(".mix-play").click();
  $(".mix-save").click();
  check("créateur : écoute et sauvegarde partagent un seul chargement",
        $(".mix-play").disabled && $(".mix-save").disabled && seedBuildCalls === 1);
  releaseSeedBuild();
  check("créateur depuis la fiche : l’identifiant musical est envoyé, pas celui du dossier", await until(() =>
        !$(".mix-play").disabled) && seedBuildOptions.seedArtistId === "ar1" &&
        w.eval('App.player.queue.length === 3 && App.player.queue.every(s => s.artistId === "ar1")'));
  const loadedSeedQueue = w.eval("App.player.queue.map(s => s.id).join()");
  app.api.post = beforeSeedBuild;

  app.api.get = async function(url, params) {
    if (url === "/api/artist" && params.id === "missing") throw w.eval('new ApiError(404, "mix.empty")');
    return beforeSeedLoad.call(this, url, params);
  };
  w.location.hash = "#/mix/missing";
  check("créateur depuis la fiche : erreur visible sans repli vers un mix quelconque", await until(() =>
        $(".mix-seed .error")) && $(".mix-play").disabled && $(".mix-save").disabled &&
        w.eval("App.player.queue.map(s => s.id).join()") === loadedSeedQueue);
  type($(".mix-seed-input"), "bjö");
  check("créateur : un autre artiste peut remplacer celui qui manque", await until(() =>
        $$(".mix-seed-results .chip").length === 1));
  $(".mix-seed-results .chip").click();
  check("créateur : choix manuel après erreur réactive les actions", await until(() => $(".mix-seed-chosen")) &&
        !$(".mix-play").disabled && !$(".mix-save").disabled &&
        !$(".mix-seed .error"));
  app.api.get = beforeSeedLoad;

  const beforeMixSettings = app.api.get;
  app.api.get = async function(url, params) {
    const data = await beforeMixSettings.call(this, url, params);
    if (url !== "/api/mix/genres") return data;
    return Object.assign({}, data, {options: {depths: [1, 2], defaultDepth: 2,
      sizes: [30, 100], defaultSize: 100, decades: [1980]}});
  };
  w.location.hash = "#/mix";
  check("créateur : choix et valeurs initiales fournis par le serveur", await until(() =>
        $$(".mix-depths .chip").length === 2) && $(".mix-depths .on").dataset.depth === "2" &&
        $$(".mix-sizes .chip").length === 2 && $(".mix-sizes .on").textContent.startsWith("100") &&
        $$(".mix-decades .chip").length === 1 && w.eval("Views.mix.options.size") === 100);
  app.api.get = beforeMixSettings;

  // --- playlists : onglet de la barre, création, glisser-déposer, communautaires ---
  const shared = (await (await alice.post("/api/playlist/create", {name: "Soirée à tous", songIds: ["s1"], community: true})).json()).playlist;
  await w.eval("App.playlists.load()");
  w.location.hash = "#/";
  check("barre : onglet Artistes affiché par défaut", !$("#panel-artists").hidden && $("#panel-playlists").hidden);
  $("#tab-playlists").click();
  check("barre : onglet Playlists", $("#panel-artists").hidden && !$("#panel-playlists").hidden &&
        $("#tab-playlists").classList.contains("active"));
  check("barre : playlist communautaire d'un autre listée à part", await until(() =>
        $$("#playlist-list .letter-head").map(h => h.textContent).includes("Communautaires")) &&
        $$(".playlist-row").some(r => r.textContent.startsWith("Soirée à tous") && !r.classList.contains("no-drop")));
  check("onglet choisi gardé dans les réglages", await until(() => w.eval("App.preferences.sidebar_tab") === "playlists"));
  $("#playlist-new").click();
  check("nouvelle playlist : fenêtre avec le choix communautaire", await until(() => $(".dialog-ask input[type=checkbox]")));
  $(".dialog-input").value = "Mes soirées";
  $(".dialog-ask input[type=checkbox]").checked = true;
  $(".dialog-ask button.primary").click();
  check("nouvelle playlist : créée et ouverte", await until(() => w.location.hash.startsWith("#/playlist/") &&
        $("#main h1") && $("#main h1").textContent === "Mes soirées"));
  check("playlist communautaire : pastille, réglage du créateur",
        !!$(".community-chip") && $(".community-toggle input").checked);
  check("barre : « Mes playlists » avant « Communautaires »", await until(() =>
        $$("#playlist-list .letter-head").map(h => h.textContent).join() === "Mes playlists,Communautaires") &&
        $(".playlist-row.current").textContent.startsWith("Mes soirées"));

  // glisser un titre : la barre est sur Artistes, l'onglet Playlists s'ouvre tout seul
  const drag = (node, kind, data) => {
    const event = new w.Event(kind, {bubbles: true, cancelable: true});
    event.dataTransfer = {setData() {}, effectAllowed: "", dropEffect: ""};
    node.dispatchEvent(event);
    return event;
  };
  $("#tab-artists").click();
  w.location.hash = "#/album/al1";
  check("album : titres glissables", await until(() => $$("tr.song[draggable=true]").length >= 1));
  drag($("tr.song"), "dragstart");
  check("glisser : la page le sait", d.body.classList.contains("dragging-songs"));
  drag($("#tab-playlists"), "dragenter");
  check("glisser sur l'onglet Playlists : il s'ouvre", await until(() => !$("#panel-playlists").hidden, 1000));
  const ownRow = $$(".playlist-row").find(r => r.textContent.startsWith("Mes soirées"));
  check("glisser : playlists où déposer repérées", !ownRow.classList.contains("no-drop"));
  check("glisser : survol accepté", drag(ownRow, "dragover").defaultPrevented);
  drag(ownRow, "drop");
  check("déposer : titre ajouté à sa playlist", await until(() => $$(".toast").some(t => t.textContent.includes("ajouté à « Mes soirées »"))));
  check("déposer : fin du glisser", !d.body.classList.contains("dragging-songs"));
  check("déposer : compteur de la barre à jour", await until(() =>
        $$(".playlist-row").find(r => r.textContent.startsWith("Mes soirées")).querySelector(".count").textContent === "1"));

  // un titre d'ailleurs glissé dans la même playlist : gardé par le site, Subsonic n'en sait rien
  w.location.hash = "#/favorites";
  await until(() => !!$('.ext-favorites tr.song[data-id="sc-29912345"]'));
  drag($('.ext-favorites tr.song[data-id="sc-29912345"]'), "dragstart");
  drag($$(".playlist-row").find(r => r.textContent.startsWith("Mes soirées")), "drop");
  check("titre SoundCloud déposé dans une playlist", await until(() =>
        $$(".playlist-row").find(r => r.textContent.startsWith("Mes soirées")).querySelector(".count").textContent === "2"));
  $$(".playlist-row").find(r => r.textContent.startsWith("Mes soirées")).click();
  check("playlist mélangée : le titre d'ailleurs après le titre Subsonic", await until(() => $$("#main tr.song").length === 2) &&
        $$("#main tr.song")[1].dataset.id === "sc-29912345" && $$("#main tr.song")[1].querySelector("td.album").textContent === "SoundCloud" &&
        !$$("#main tr.song")[1].querySelector(".song-download"));
  check("radio d'un titre : proposée seulement pour le morceau Subsonic de la playlist",
        !!$$("#main tr.song")[0].querySelector(".song-radio") && !$$("#main tr.song")[1].querySelector(".song-radio"));
  const order = () => $$("#main tr.song").map(r => r.dataset.id).join();
  const before = order();
  check("sa playlist : poignée pour changer l'ordre", $$("#main td.grip").length === 2);
  $$("#main tr.song")[1].dispatchEvent(new w.KeyboardEvent("keydown", {key: "ArrowUp", altKey: true, bubbles: true}));
  check("ordre changé au clavier (Alt + ↑), ligne gardée", await until(() => order() === "sc-29912345," + before.split(",")[0]) &&
        d.activeElement === $$("#main tr.song")[0]);
  drag($$("#main tr.song")[1], "dragstart");
  check("ordre : survol d'une ligne accepté", drag($$("#main tr.song")[0], "dragover").defaultPrevented);
  drag($$("#main tr.song")[0], "drop");
  check("ordre changé en glissant", await until(() => order() === before));
  $$("#main tr.song")[1].querySelector(".song-remove").click();
  check("playlist mélangée : titre d'ailleurs retiré", await until(() => $$("#main tr.song").length === 1));
  w.location.hash = "#/album/al1";                        // retour à l'album pour la suite du parcours
  await until(() => $$("tr.song[draggable=true]").length >= 2);

  // déposer sur la playlist communautaire de alice : écrit au nom de alice, crédité à bob
  drag($$("tr.song")[1], "dragstart");                               // le 1er titre y est déjà (ajouté par alice)
  drag($$(".playlist-row").find(r => r.textContent.startsWith("Soirée à tous")), "drop");
  check("déposer sur une communautaire d'un autre", await until(() => $$(".toast").some(t => t.textContent.includes("« Soirée à tous »"))));
  w.location.hash = "#/playlist/" + shared.id;
  check("communautaire : « ajouté par » sur chaque titre", await until(() => $$("td.added-by").length === 2) &&
        $$("td.added-by").map(td => td.textContent).join() === "alice,bob");
  check("communautaire : retirer seulement ce que j'ai ajouté", $$("tr.song").map(r => !!r.querySelector(".song-remove")).join() === "false,true" &&
        !$(".community-toggle"));
  check("communautaire d'un autre : pas de changement d'ordre", !$("td.grip"));
  $(".song-remove").click();
  check("communautaire : titre retiré", await until(() => $$("tr.song").length === 1));

  // un album entier glissé sur « + » crée une playlist
  w.location.hash = "#/albums/newest";
  await until(() => $$(".album-card[draggable=true]").length >= 1);
  drag($(".album-card"), "dragstart");
  drag($("#playlist-new"), "drop");
  check("album glissé sur « + » : fenêtre de création", await until(() => $(".dialog-input") && $(".dialog-input").value.length > 0));
  $(".dialog-ask button.primary").click();
  check("album glissé sur « + » : playlist créée avec ses titres", await until(() => $$(".toast").some(t => t.textContent.startsWith("Playlist « "))) &&
        await until(() => $$(".playlist-row").length === 4));
  w.eval("Dialogs.close()");

  // --- écoute : « en cours » au démarrage, « écoutée » à la moitié, onglet « En écoute » ---
  w.eval(`window.posts = []; const post = App.api.post.bind(App.api);
          App.api.post = (url, body) => { if (url === "/api/scrobble") window.posts.push(body); return post(url, body); }`);
  w.eval("App.player.playList([{id: 's1', title: 'Dancing Queen', artist: 'ABBA', albumId: 'al1'}], 0)");
  check("lecteur : titre signalé « en cours » à Subsonic", await until(() =>
        JSON.stringify(w.posts) === JSON.stringify([{id: "s1", submission: false}])));
  w.eval("window.t = 0; Object.defineProperty(App.player.audio, 'currentTime', {get: () => window.t, set() {}, configurable: true});" +
         "Object.defineProperty(App.player.audio, 'duration', {get: () => 100, configurable: true})");
  w.eval("window.t = 90; App.player.countListen()");
  check("lecteur : un saut en avant ne compte pas comme une écoute", w.posts.length === 1);
  w.eval("App.player.listen.heard = 49.5; App.player.listen.last = 49; window.t = 50; App.player.countListen(); App.player.countListen()");
  check("lecteur : écoute comptée à la moitié du titre, une seule fois",
        JSON.stringify(w.posts.slice(1)) === JSON.stringify([{id: "s1", submission: true}]));
  await alice.post("/api/scrobble", {id: "s3", submission: false});
  w.eval("App.bus.emit('listening')");
  check("« Écouté en ce moment » (panneau de droite) : moi d'abord, puis les autres", await until(() => $$("#chat-panel .listening-row").length === 2) &&
        !$("#listening").hidden && $$(".listening-row").map(r => r.dataset.user).join() === "bob,alice" &&
        $(".listening-row.me .listening-who").textContent === "Vous" &&
        $(".listening-row .listening-song").textContent === "Dancing Queen — ABBA");
  check("« Écouté en ce moment » : au-dessus du salon", $("#chat-panel").firstElementChild.id === "listening");

  // --- envoi de fichiers dans Incoming ---
  check("lien « Envoyer » affiché (droit upload, dossier réglé)", await until(() => !$("#nav-upload").hidden) &&
        $("#nav-upload").textContent === "Envoyer");
  dom.cookieJar.setCookieSync(jar.cookie, base);                 // la page envoie avec XMLHttpRequest : même session que le reste
  w.location.hash = "#/upload";
  check("envoi : page et dossier de la personne", await until(() => $(".upload-zone")) &&
        $("#main .muted").textContent.includes("« Incoming »"));
  w.eval(`Views.upload.add([new File([new Uint8Array(2000)], "Essai.flac"), new File(["x"], "virus.exe"), new File([new Uint8Array(10)], "Autre.mp3")])`);
  check("envoi : format refusé expliqué tout de suite", await until(() => $$(".upload-row.failed .upload-state").some(s => s.textContent === "Format non accepté")));
  check("envoi : fichiers envoyés un par un", await until(() => $$(".upload-row.done").length === 2, 5000));
  check("envoi : Subsonic invité à scanner", await until(() => $(".upload-summary").textContent.startsWith("2 fichiers envoyés. Subsonic scanne"), 5000));
  check("envoi : fichier seul signalé hors nomenclature", $$(".upload-row.done .upload-state").every(s => s.textContent.includes("à ranger")));
  // un album en zip, rangé Artiste/Album (2 titres et une pochette) : décompressé sur le serveur, nomenclature respectée
  const albumZip = "UEsDBBQAAAAAANVtWl3sfd8UGAAAABgAAAAWAAAAQWJiYS9BcnJpdmFsLzAxIEEuZmxhY2ZMYUMAAAAAAAAAAAAAAAAAAAAAAAAAAFBLAwQUAAAAAADVbVpd7H3fFBgAAAAYAAAAFgAAAEFiYmEvQXJyaXZhbC8wMiBCLmZsYWNmTGFDAAAAAAAAAAAAAAAAAAAAAAAAAABQSwMEFAAAAAAA1W1aXeka6EYDAAAAAwAAABYAAABBYmJhL0Fycml2YWwvY292ZXIuanBnanBnUEsBAhQDFAAAAAAA1W1aXex93xQYAAAAGAAAABYAAAAAAAAAAAAAAIABAAAAAEFiYmEvQXJyaXZhbC8wMSBBLmZsYWNQSwECFAMUAAAAAADVbVpd7H3fFBgAAAAYAAAAFgAAAAAAAAAAAAAAgAFMAAAAQWJiYS9BcnJpdmFsLzAyIEIuZmxhY1BLAQIUAxQAAAAAANVtWl3pGuhGAwAAAAMAAAAWAAAAAAAAAAAAAACAAZgAAABBYmJhL0Fycml2YWwvY292ZXIuanBnUEsFBgAAAAADAAMAzAAAAM8AAAAAAA==";
  w.eval(`Views.upload.add([new File([Uint8Array.from(atob("${albumZip}"), c => c.charCodeAt(0))], "Album.zip")])`);
  check("envoi : zip décompressé et album rangé chez l'artiste", await until(() => $$(".upload-state").some(s =>
        s.textContent === "Décompressé : 3 fichiers — rangé dans Abba/Arrival"), 5000));
  check("envoi : barre du lot entier, terminée", await until(() => !$(".upload-total").hidden &&
        $(".upload-total progress").value === 1 && $(".upload-total .upload-state").textContent === "Terminé", 5000));

  // --- Actualité : flux des webzines, partagés par tout le site ---
  w.location.hash = "#/news";
  check("actualité : page, « Tout » et les trois webzines de départ", await until(() => $$(".news-feed").length === 4) &&
        $("#main h1").textContent === "Actualité" && $(".news-feed.on").textContent === "Tout" &&
        $$(".topnav a.active").map(a => a.getAttribute("href")).join() === "#/news");
  check("actualité : vide expliqué", $(".news-list li.muted").textContent.startsWith("Aucun article"));
  check("actualité : flux de départ, seul l'admin les retire", !$(".news-remove"));
  $(".news-address").value = "webzine.example";
  $(".news-add button").click();
  check("actualité : site ajouté, son flux trouvé et lu", await until(() => /^#\/news\/\d+$/.test(w.location.hash) &&
        $$(".news-article").length === 3) && $(".news-feed.on a").textContent === "Webzine");
  const firstArticle = $(".news-article .news-title");
  check("actualité : lien vers le webzine, nouvel onglet", firstArticle.getAttribute("href") === "https://webzine.example/fontaines" &&
        firstArticle.target === "_blank" && firstArticle.rel === "noopener noreferrer" &&
        firstArticle.textContent === "Fontaines D.C. : nouvel album en écoute");
  check("actualité : résumé sans HTML", $(".news-summary").textContent === "Le groupe revient .");
  $(".news-address").value = "webzine.example";
  $(".news-add button").click();
  check("actualité : flux déjà suivi expliqué", await until(() => $$(".toast").some(t => t.textContent === "Ce flux est déjà suivi")));
  w.location.hash = "#/news";
  check("actualité : tous les flux, nom du webzine sur chaque article", await until(() => $$(".news-article").length === 3 &&
        $(".news-meta").textContent.startsWith("Webzine · ")));
  const showBox = () => $$(".news-feed").find(c => c.textContent.includes("Webzine")).querySelector(".news-show");
  check("actualité : chaque flux affiché par défaut", showBox().checked);
  showBox().click();
  check("actualité : flux décoché, masqué pour soi", await until(() => !$(".news-article") &&
        $$(".news-feed.news-hidden").length === 1 && !showBox().checked));
  showBox().click();
  check("actualité : flux recoché, articles revenus", await until(() => $$(".news-article").length === 3 && showBox().checked));
  w.location.hash = "#/artist/fdir-ar3";
  check("artiste : « Dans la presse », articles qui le citent", await until(() => $$(".press .news-article").length === 1) &&
        $(".press h2").textContent === "Dans la presse" && $(".press .news-title").textContent === "Björk en interview");
  w.location.hash = "#/news";
  await until(() => $(".news-remove"));
  $(".news-remove").click();
  await until(() => $(".dialog .primary.danger"));
  $(".dialog .primary.danger").click();
  check("actualité : flux ajouté retiré par la personne, ses articles oubliés", await until(() =>
        $$(".news-feed").length === 4 && !$(".news-article")));

  // --- Nouveautés : page pour les utilisateurs, tous les textes présents ---
  w.location.hash = "#/whatsnew";
  check("nouveautés : page, lien du menu actif", await until(() => $("#main h1") &&
        $("#main h1").textContent.startsWith("Nouveautés")) &&
        $('.topnav a[href="#/whatsnew"]').classList.contains("active"));
  check("nouveautés : le principe puis six parties", !!$(".whatsnew-idea") && $$(".whatsnew-part").length === 6 &&
        $$(".whatsnew-card").length === 28);
  check("nouveautés : playlists (glisser-déposer, communautaires, partagées)",
        ["Glisser-déposer", "Communautaires", "Partagées"].every(w => $$(".whatsnew-card h3").some(h => h.textContent.startsWith(w))));
  check("nouveautés : aucun texte manquant", ![...$$("#main h2, #main h3, #main p")].some(n => /whatsnew\./.test(n.textContent)));
  check("nouveautés : le quota YouTube expliqué", $$(".whatsnew-card").some(c => c.textContent.includes("120 recherches par heure")));
  $$(".whatsnew-link").find(a => a.getAttribute("href") === "#/mix").click();
  check("nouveautés : lien vers la page Mix", await until(() => w.location.hash === "#/mix"));
  w.location.hash = "#/";

  // --- Versions : numéro à côté du titre, pastille tant que la dernière version n'a pas été vue ---
  check("versions : numéro et pastille à côté du titre", await until(() => !$("#version-tag").hidden) &&
        /^v\d+\.\d+(\.\d+)?$/.test($("#version-tag").textContent) && $("#version-tag").classList.contains("fresh"));
  $("#version-tag").click();
  check("versions : la plus récente en haut, marquée nouvelle", await until(() => $$(".version").length >= 4) &&
        $(".version .version-head span").textContent === "Version " + $("#version-tag").textContent.slice(1) &&
        $$(".version.fresh").length === $$(".version").length && $(".version-changes li"));
  check("versions : aucun texte manquant", ![...$$("#main h1, #main h2, #main p")].some(n => /versions\./.test(n.textContent)));
  check("versions : pastille retirée une fois vue", !$("#version-tag").classList.contains("fresh"));
  w.location.hash = "#/whatsnew";
  await until(() => $(".whatsnew-versions"));
  check("versions : lien depuis Nouveautés", $(".whatsnew-versions").getAttribute("href") === "#/versions");
  w.location.hash = "#/";

  // --- Importer une playlist : guide, lien Deezer, rapprochement, YouTube, création dans l'ordre ---
  check("import : bouton dans la barre des playlists", $("#playlist-import").getAttribute("href") === "#/import" &&
        !$("#playlist-import").hidden);
  w.location.hash = "#/import";
  check("import : la page, un lien Deezer et un fichier", await until(() => $$(".import-part").length === 2) &&
        $("#main h1").textContent === "Importer une playlist" && !!$(".import-link"));
  $('a[href="#/import/guide"]').click();
  check("import : guide pas à pas, six parties", await until(() => w.location.hash === "#/import/guide" &&
        $$(".import-guide .import-part").length === 6) && $$(".import-steps li").length >= 20 &&
        $$(".import-guide h2").some(h => h.textContent.startsWith("Spotify")));
  check("import : guide sans texte manquant", ![...$$("#main h2, #main p, #main li, #main a")].some(n => /import\./.test(n.textContent)));
  $("#main a.button.primary").click();
  check("import : retour au formulaire", await until(() => w.location.hash === "#/import" && $(".import-link")));
  $(".import-link").value = "https://www.deezer.com/fr/playlist/77";
  $(".import-part button.primary").click();
  check("import : playlist lue, nom proposé", await until(() => $$(".import-row").length === 4) &&
        $(".import-name").value === "En mode 70");
  check("import : bibliothèque puis YouTube", await until(() => $(".import-summary").textContent ===
        "2 trouvés · 0 à vérifier · 1 sur YouTube · 1 introuvables" && $(".import-progress").textContent === ""));
  check("import : un état et un choix par titre", $$(".import-row .import-found").length === 2 &&
        $$(".import-row .import-youtube").length === 1 && $$(".import-row select")[3].value === "skip" &&
        $$(".import-row select")[2].value === "youtube");
  check("import : bouton avec le nombre de titres", $(".import-actions .primary").textContent === "Créer la playlist (3 titres)");
  $(".import-actions .primary").click();
  check("import : playlist créée, sa page ouverte", await until(() => w.location.hash.startsWith("#/playlist/") &&
        $("#main h1") && $("#main h1").textContent.includes("En mode 70")));
  // export de toute la bibliothèque Apple Music : la page demande quelle playlist importer
  const plist = items => "<dict><key>Playlist Items</key><array>" +
    items.map(id => "<dict><key>Track ID</key><integer>" + id + "</integer></dict>").join("") + "</array>";
  const library = '<?xml version="1.0" encoding="UTF-8"?><plist version="1.0"><dict><key>Tracks</key><dict>' +
    '<key>1</key><dict><key>Name</key><string>Dancing Queen</string><key>Artist</key><string>ABBA</string></dict>' +
    '<key>2</key><dict><key>Name</key><string>Army of Me</string><key>Artist</key><string>Björk</string></dict></dict>' +
    "<key>Playlists</key><array>" + plist([1, 2]) + "<key>Name</key><string>Bibliothèque</string><key>Master</key><true/></dict>" +
    plist([2]) + "<key>Name</key><string>Acid</string></dict>" + plist([1, 2]) + "<key>Name</key><string>Thomas</string></dict>" +
    "</array></dict></plist>";
  w.location.hash = "#/import";
  await until(() => $(".import-link"));
  w.eval("Views.import").readFile(new w.File([library], "Bibliothèque.xml", {type: "text/xml"}));
  check("import : export de toute la bibliothèque, choix de la playlist", await until(() =>
        $$(".import-playlists button").length === 2) && $(".import-playlists button").textContent === "Acid1 titre" &&
        $$(".import-sources").every(n => n.hidden));
  $$(".import-playlists button")[1].click();
  check("import : la playlist choisie est lue", await until(() => $$(".import-row").length === 2 &&
        $(".import-name").value === "Thomas") && !$(".import-choose"));

  // --- Mon compte : photo (Subsonic, Gravatar), affichage, droits, Last.fm, import d'un lien ---
  const meImage = () => $("#me .avatar img") && $("#me .avatar img").getAttribute("src");
  check("en haut : ma photo Subsonic à côté de mon nom, lien vers Mon compte", await until(() => meImage()) &&
        meImage().startsWith("/api/avatar?user=bob&v=s") && $("#me").getAttribute("href") === "#/account");
  check("salon : photo pour qui en a une, initiale sinon", $$("#chat-panel .avatar[data-user=bob] img").length > 0 &&
        $$("#chat-panel .avatar[data-user=alice]").length > 0 && !$("#chat-panel .avatar[data-user=alice] img") &&
        $("#chat-panel .avatar[data-user=alice]").textContent === "A");
  $("#open-settings").click();
  check("réglages rapides gardés (largeur en px), avec un lien vers Mon compte", !!$(".dialog .settings-account") &&
        $$(".dialog option").some(o => o.textContent === "280 px"));
  $(".dialog .settings-account").click();
  check("Mon compte : la page, la fenêtre fermée", await until(() => $("#main h1") && $("#main h1").textContent === "Mon compte") &&
        !$(".dialog"));
  check("Mon compte : cinq parties", $$(".account-part").length === 5 && $$("#main .rights-list li").length === 8 &&
        $$("#main .account-part select").length === 5 && !!$("#main .ext-link-form"));
  check("Mon compte : photo venue de Subsonic, rien à retirer", await until(() => $(".account-photo")) &&
        $(".account-photo-side p").textContent.startsWith("Photo de votre compte Subsonic") &&
        !$$(".account-buttons button").some(b => b.textContent.startsWith("Retirer")));
  check("Mon compte : lien vers les réglages personnels de Subsonic (Last.fm)", await until(() => $("#main a.button")) &&
        $("#main a.button").href.endsWith("/personalSettings.view") && $("#main a.button").target === "_blank");
  const missingTexts = $$("#main h1, #main h2, #main h3, #main p, #main button, #main a")
    .filter(n => /\b(account|avatar|settings)\.[a-z_]+$/m.test(n.textContent))      // une clé affichée telle quelle.map(n => n.textContent);
  check("Mon compte : aucun texte manquant", !missingTexts.length);
  if (missingTexts.length) console.log(missingTexts);
  const gravatarForm = $(".account-gravatar");
  check("Gravatar : pas d'adresse dans Subsonic, champ vide", gravatarForm.elements[0].value === "");
  gravatarForm.dispatchEvent(new w.Event("submit", {cancelable: true}));
  check("Gravatar : sans adresse, expliqué", await until(() => $$(".toast").some(t => t.textContent.includes("pas d'adresse e-mail"))));
  gravatarForm.elements[0].value = "Alice@exemple.fr";
  gravatarForm.dispatchEvent(new w.Event("submit", {cancelable: true}));
  check("Gravatar : photo copiée sur le site", await until(() => $(".account-photo-side p") &&
        $(".account-photo-side p").textContent === "Photo choisie sur ce site."));
  check("Gravatar : la photo du haut suit", await until(() => meImage() && !meImage().includes("&v=s")));
  $$(".account-buttons button").find(b => b.textContent.startsWith("Retirer")).click();
  check("photo retirée : celle de Subsonic revient", await until(() => $(".account-photo-side p") &&
        $(".account-photo-side p").textContent.startsWith("Photo de votre compte Subsonic")) &&
        await until(() => meImage() && meImage().includes("&v=s")));
  w.location.hash = "#/";

  if (snapshotPath) {        // instantané visuel (sans scripts) pour vérifier la mise en page
    w.eval("App.savePreference('sidebar', 'pinned')");
    w.location.hash = "#/album/al1";
    await until(() => $(".album-info h1") && $(".album-info h1").textContent === "Arrival" && $$(".comments .message").length);
    await wait(300);
    d.querySelectorAll("script").forEach(s => s.remove());
    d.querySelectorAll("link[rel=stylesheet]").forEach(link => {
      const file = path.join(__dirname, "..", "src", "web-pc", new URL(link.href).pathname);
      const style = d.createElement("style");
      style.textContent = fs.readFileSync(file, "utf8");
      link.replaceWith(style);
    });
    d.querySelectorAll("img").forEach(img => { img.removeAttribute("src"); img.alt = ""; });
    d.querySelectorAll(".toast").forEach(t => t.remove());
    // aperçu d'un écran de PC (1440 px) dans un panneau étroit : sans la règle « petit écran », réduit à l'échelle
    d.querySelectorAll("style").forEach(st => { st.textContent = st.textContent.replace(/@media \(max-width: 820px\)[\s\S]*?\n\}\n/, ""); });
    const zoom = d.createElement("style");
    zoom.textContent = "html { zoom: 0.42; } .app { width: 1440px; height: 900px; }";
    d.head.appendChild(zoom);
    fs.writeFileSync(snapshotPath, "<!doctype html>\n" + d.documentElement.outerHTML);
  }
  check("aucune erreur JavaScript", w.errors.length === 0);
  if (w.errors.length) console.log(w.errors);
  console.log(failures ? "ÉCHECS : " + failures : "TOUT PASSE");
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
