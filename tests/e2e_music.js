// Parcours de la musique d'ailleurs dans jsdom, avec un faux lecteur YouTube. Usage : node tests/e2e_music.js PORT [jsdom]
const port = process.argv[2];
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + port;
const wait = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok) => { console.log((ok ? "OK   " : "FAIL ") + name); if (!ok) failures++; };

(async () => {
  const dom = await JSDOM.fromURL(base + "/", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(new URL(u, base), Object.assign({}, o, {headers: Object.assign({"X-Requested-With": "pm"}, (o && o.headers) || {})}));
      const proto = w.HTMLMediaElement.prototype;
      proto.play = function () { this._paused = false; Object.defineProperty(this, "paused", {value: false, configurable: true}); return Promise.resolve(); };
      proto.pause = function () { Object.defineProperty(this, "paused", {value: true, configurable: true}); };
      proto.load = function () {};
      w.YT = {Player: class {
        constructor(id, opts) { this.opts = opts; this.videoId = opts.videoId; this.t = 0; this.stopped = false; w.__yt = this; }
        loadVideoById(v) { this.videoId = v; this.stopped = false; }
        playVideo() {} pauseVideo() {} stopVideo() { this.stopped = true; }
        getCurrentTime() { return this.t; } getDuration() { return 200; } seekTo(t) { this.t = t; }
        emit(state) { this.opts.events.onStateChange({data: state}); }
        fail(code) { this.opts.events.onError({data: code}); }
      }};
      w.errors = []; w.addEventListener("error", e => w.errors.push(e.message));
    }
  });
  const w = dom.window, d = w.document, $ = s => d.querySelector(s), $$ = s => [...d.querySelectorAll(s)];
  const click = e => e.dispatchEvent(new w.MouseEvent("click", {bubbles: true}));
  const post = (path, body) => w.eval("extPost(" + JSON.stringify(path) + ", " + JSON.stringify(body) + ")");
  await wait(3500);

  check("chargement sans erreur JavaScript", w.errors.length === 0);
  check("tout est désactivé au départ", w.eval("!EXT.jamendo.enabled && !EXT.youtube.enabled"));

  // --- réglages ---
  const settingsBtn = $$("button").find(b => b.textContent.includes("Sources externes"));
  check("bouton « Sources externes » sur l'accueil", !!settingsBtn);
  click(settingsBtn); await wait(500);
  check("réglages : deux sources « clé manquante »", $$(".h").filter(h => h.textContent.includes("clé manquante")).length === 2);
  let refused = false;
  try { await post("settings", {youtube_on: true}); } catch (e) { refused = /clé/.test(e.message); }
  check("activation refusée sans clé", refused);
  await post("settings", {jamendo_id: "abcd", jamendo_on: true});
  await post("settings", {youtube_key: "KEY", youtube_on: true});
  check("sources activées", w.eval("EXT.jamendo.enabled && EXT.youtube.enabled"));

  // --- recherche « Ailleurs » ---
  w.eval('tab("search")'); await wait(500);
  w.eval('setSearchText("bjo")'); await wait(300);
  check("suggestions : artiste proposé dès 3 lettres, accents ignorés", $$(".qsug button").some(b => b.textContent === "Björk"));
  w.eval('setSearchText("b")'); await wait(50);
  check("suggestions : rien avant 2 lettres", $$(".qsug button").length === 0);
  // --- saisie depuis le téléphone : petit bouton discret, QR code, texte reçu en direct ---
  check("téléphone : petit bouton dans la barre du clavier", !!$("#kbphone"));
  click($("#kbphone")); await wait(400);
  check("téléphone : QR code affiché", !!$("#phoneqr svg"));
  const phone = await (await fetch(base + "/ext/remote")).json();
  const phoneUrl = new URL(phone.url);
  const sendFromPhone = (code, text) => fetch("http://127.0.0.1:" + phoneUrl.port + "/tel/text",
    {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify({code, text})});
  check("téléphone : mauvais code refusé", (await sendFromPhone("faux", "x")).status === 403);
  check("téléphone : page du téléphone servie", (await fetch("http://127.0.0.1:" + phoneUrl.port + "/tel")).status === 200);
  await sendFromPhone(phoneUrl.searchParams.get("c"), "björk"); await wait(1300);
  check("téléphone : texte reçu dans la recherche du Pi", w.eval("qtext") === "björk" && !$("#phoneqr"));
  const fromPhone = await (await sendFromPhone(phoneUrl.searchParams.get("c"), "bjo")).json();
  const bjork = (fromPhone.suggestions || []).find(a => a.name === "Björk");
  check("téléphone : suggestions renvoyées au téléphone", !!bjork);
  await fetch("http://127.0.0.1:" + phoneUrl.port + "/tel/pick", {method: "POST", headers: {"Content-Type": "application/json"},
    body: JSON.stringify({code: phoneUrl.searchParams.get("c"), id: bjork && bjork.id})});
  await wait(1200);
  check("téléphone : suggestion touchée = artiste ouvert sur le Pi", $("#title") ? $("#title").textContent.includes("Björk") : d.body.textContent.includes("Post"));
  w.eval('tab("search")'); await wait(500);
  const kdel = $("#kb button.del");
  w.eval('qtext = "grooves"'); click(kdel); await wait(50);
  check("clavier : grande touche effacer (un caractère par appui court)", w.eval("qtext") === "groove");
  w.eval('runSearch()'); await wait(2500);
  check("recherche : section Jamendo", $$(".h").some(h => h.textContent.includes("Jamendo")));
  check("recherche : titre Jamendo affiché", $$(".row b").some(b => b.textContent === "Groove"));
  check("recherche : bouton YouTube (pas d'appel automatique)", $$("button").some(b => b.textContent.includes("aussi sur YouTube")));
  check("recherche : aucun résultat YouTube avant le clic", !$$(".row b").some(b => b.textContent.includes("Daft")));

  // --- lecture Jamendo ---
  click($$(".row").find(r => r.textContent.includes("Groove"))); await wait(500);
  w.eval('qtext = ""; runSearch()'); await wait(800);
  check("historique : la recherche utilisée est proposée", $$(".histtext").some(b => b.textContent === "groove"));
  click($$(".histtext").find(b => b.textContent === "groove")); await wait(100);
  check("historique : un toucher relance la recherche", w.eval("qtext") === "groove");
  click($$(".histdel")[0]); await wait(300);
  check("historique : une recherche peut être retirée", !$$(".histtext").some(b => b.textContent === "groove"));
  check("Jamendo : titre en cours", w.eval("cur().id") === "jamendo-11");
  check("Jamendo : lecteur audio habituel", w.eval("!audio.isYouTube") && w.eval("audio.src").includes("jamendo.com"));
  check("Jamendo : ni scrobble ni favori", w.eval("isExternal(cur())"));
  check("Jamendo : pochette externe dans la barre", $("#npimg").src === "https://img/11.jpg");

  // --- playlist locale mélangée ---
  const created = await post("create", {name: "Mélange", songs: [w.eval("cur()")]});
  w.eval('tab("playlists")'); await wait(800);
  check("playlists : section locale", $$(".h").some(h => h.textContent.includes("Playlists locales")) && $$(".row b").some(b => b.textContent === "Mélange"));
  click($$(".row").find(r => r.textContent.includes("Mélange"))); await wait(600);
  check("playlist locale : titre listé", $$(".row b").some(b => b.textContent === "Groove"));

  // --- YouTube ---
  w.eval('tab("search")'); await wait(400);
  w.eval('qtext = "daft"; runSearch()'); await wait(2500);
  click($$("button").find(b => b.textContent.includes("aussi sur YouTube"))); await wait(1500);
  check("YouTube : résultat affiché après le clic", $$(".row b").some(b => b.textContent === "Daft Punk & Co 'Live'"));
  click($$(".row").find(r => r.textContent.includes("Daft Punk"))); await wait(800);
  check("YouTube : moteur YouTube actif", w.eval("audio.isYouTube") && w.eval("audio.src") === "youtube:abc123");
  check("YouTube : lecteur créé avec la bonne vidéo", !!w.__yt && w.__yt.videoId === "abc123");
  check("YouTube : fenêtre vidéo visible", !$("#ytbox").hidden && d.body.classList.contains("yt"));
  w.__yt.emit(1);
  check("YouTube : état lecture reconnu", w.eval("!audio.paused"));
  w.__yt.t = 42;
  check("YouTube : position et durée", w.eval("audio.currentTime") === 42 && w.eval("audio.duration") === 200);
  w.eval("audio.currentTime = 100"); check("YouTube : déplacement dans la barre", w.__yt.t === 100);
  w.__yt.emit(2);
  check("YouTube : pause reconnue", w.eval("audio.paused"));

  // --- enchaînement YouTube -> Jamendo dans une même file ---
  w.eval('playQueue([{id:"yt-abc123", youtubeId:"abc123", title:"Vidéo", artist:"A", ext:"youtube"}, {id:"jamendo-11", title:"Groove", artist:"Fankel", streamUrl:"https://prod-1.storage.jamendo.com/?trackid=11", ext:"jamendo"}], 0)');
  await wait(400); w.__yt.emit(1);
  w.__yt.emit(0); await wait(600);
  check("fin de vidéo : passage au titre suivant", w.eval("cur().id") === "jamendo-11");
  check("retour au lecteur audio, fenêtre vidéo masquée", w.eval("!audio.isYouTube") && $("#ytbox").hidden && !d.body.classList.contains("yt"));

  // --- vidéo refusée : une autre version du même titre est lancée à la place ---
  w.eval('playQueue([{id:"yt-zzz", youtubeId:"zzz", title:"Daft Punk - Co (Official Video)", artist:"DaftPunkVEVO", ext:"youtube"}], 0)');
  await wait(400); w.__yt.fail(150); await wait(1200);
  check("vidéo refusée : autre version du même titre lancée", w.eval("cur().youtubeId") === "abc123" && w.eval("cur().altTried") === true);

  // --- vidéo refusée sans autre version : proposition de la lire sur la vraie page YouTube ---
  w.eval('playQueue([{id:"yt-x", youtubeId:"x", title:"Bloquée", artist:"A", ext:"youtube", duration:200}, {id:"jamendo-11", title:"Groove", artist:"Fankel", streamUrl:"https://prod-1.storage.jamendo.com/?trackid=11", ext:"jamendo"}], 0)');
  await wait(400); w.__yt.fail(150); await wait(100);
  check("vidéo refusée : le code d'erreur est affiché", $("#toast").textContent.includes("code 150 : intégration interdite"));
  await wait(1200);
  check("vidéo refusée : proposition « Lire sur YouTube »", !$("#sheet").hidden && $("#sheet").textContent.includes("Lire sur YouTube"));
  const fakeWin = {closed: false, close() { this.closed = true; }};
  w.open = (url, name, features) => { w.__opened = {url, features}; return fakeWin; };
  click($$("#sheet .si").find(b => b.textContent.includes("Lire sur YouTube"))); await wait(200);
  check("fenêtre YouTube : vraie page, en fenêtre surgissante", w.__opened && w.__opened.url === "https://www.youtube.com/watch?v=x" && w.__opened.features.startsWith("popup"));
  check("fenêtre YouTube : fond assombri avec bouton de fermeture", !!$("#ytveil") && $("#ytveil").textContent.includes("Fermer YouTube"));
  w.eval("youTubeWindow.warnBeforeClosing()"); await wait(100);
  check("fenêtre YouTube : compte à rebours avant fermeture", $("#ytveil em").textContent.includes("Fermeture de YouTube dans"));
  click($("#ytveil .keep")); await wait(100);
  check("fenêtre YouTube : « Garder ouverte » arrête le compte à rebours", $("#ytveil em").textContent === "");
  fakeWin.closed = true; await wait(1300);
  check("fenêtre YouTube fermée : la liste reprend au titre suivant", !$("#ytveil") && w.eval("cur().id") === "jamendo-11");

  // --- invités AirPlay / Bluetooth ---
  const guest = async body => (await fetch(base + "/__test/guest", {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)})).json();
  const T1 = '{id:"jamendo-21", title:"Un", artist:"A", streamUrl:"https://prod-1.storage.jamendo.com/?trackid=21", ext:"jamendo"}';
  const T2 = '{id:"jamendo-22", title:"Deux", artist:"A", streamUrl:"https://prod-1.storage.jamendo.com/?trackid=22", ext:"jamendo"}';
  w.eval("playQueue([" + T1 + "," + T2 + "], 0)"); await wait(400);
  await guest({players: {"bluez_player.AA": "Paused"}}); await wait(1900);
  check("invité : bandeau « passera après ce titre »", !$("#guestbar").hidden && $("#guestbar").textContent.includes("Bluetooth en attente"));
  w.eval("audio.onended()"); await wait(500);
  check("invité : en fin de titre, le téléphone reçoit « lecture »", (await guest({players: {"bluez_player.AA": "Paused"}})).played.length === 1);
  check("invité : la musique ne passe pas au titre suivant tout de suite", w.eval("cur().id") === "jamendo-21" && w.eval("audio.paused"));
  await guest({streams: [{name: "bluez_source", corked: false}], players: {"bluez_player.AA": "Playing"}}); await wait(1900);
  await guest({players: {"bluez_player.AA": "Paused"}}); await wait(3600);
  check("invité : quand le téléphone s'arrête, on enchaîne sur le titre suivant", w.eval("cur().id") === "jamendo-22" && !w.eval("audio.paused"));
  check("invité : pas de nouveau passage automatique après son morceau", $("#guestbar").hidden || $("#guestbar").textContent.includes("connecté"));
  await guest({streams: [{name: "shairport-sync", corked: false}]}); await wait(3200);
  check("AirPlay qui démarre : notre musique baisse puis se met en pause", w.eval("audio.paused"));
  await guest({}); await wait(3600);
  check("AirPlay arrêté : notre musique reprend au même titre", w.eval("cur().id") === "jamendo-22" && !w.eval("audio.paused"));

  // --- désactivation ---
  await post("settings", {youtube_on: false, jamendo_on: false});
  w.eval('tab("search")'); await wait(400);
  w.eval('qtext = "groove"; runSearch()'); await wait(2000);
  check("sources désactivées : plus de section Ailleurs", !$$(".h").some(h => h.textContent.includes("Ailleurs")));

  check("aucune erreur JavaScript pendant le parcours", w.errors.length === 0);
  console.log(failures ? "ÉCHECS : " + failures : "TOUT PASSE");
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
