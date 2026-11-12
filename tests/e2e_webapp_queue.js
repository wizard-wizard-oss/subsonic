// File PC : API Subsonic, rafraîchissement, copie locale hors réseau, comptes et réponses lentes.
// Usage : node tests/e2e_webapp_queue.js PORT [jsdom]
const {JSDOM} = require(process.argv[3] || "jsdom");
const fs = require("fs");
const vm = require("vm");
const path = require("path");
const base = "http://127.0.0.1:" + process.argv[2];
const wait = ms => new Promise(resolve => setTimeout(resolve, ms));
let failures = 0;
const check = (name, ok) => { console.log((ok ? "OK   " : "FAIL ") + name); if (!ok) failures++; };
const until = async test => {
  for (let i = 0; i < 240; i++) { if (test()) return true; await wait(50); }
  return false;
};
const doms = [];
const song = id => ({id, title: id, duration: 200});
const memory = w => Object.fromEntries(Object.keys(w.localStorage).map(k => [k, w.localStorage.getItem(k)]));

function stubMedia(w) {
  const proto = w.HTMLMediaElement.prototype;
  proto.play = function () {
    Object.defineProperty(this, "paused", {value: false, configurable: true});
    this.dispatchEvent(new w.Event("play"));
    return Promise.resolve();
  };
  proto.pause = function () {
    Object.defineProperty(this, "paused", {value: true, configurable: true});
    this.dispatchEvent(new w.Event("pause"));
  };
  proto.load = function () { this.currentTime = 0; };
}

/** Vrais composants sans serveur : maîtrise des courses réseau et du stockage indisponible. */
function component(saved = {}) {
  const dom = new JSDOM('<div><div id="video"></div></div>', {url: base, runScripts: "outside-only"});
  doms.push(dom);
  const w = dom.window;
  stubMedia(w);
  for (const [k, v] of Object.entries(saved)) w.localStorage.setItem(k, v);
  for (const name of ["core", "engine", "player", "queue-memory"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, "../src/web-pc/static/js/" + name + ".js"), "utf8"), dom.getInternalVMContext());
  }
  w.eval(`App.user = {id: 1, username: "bob", roles: ["stream"]};
    App.api.get = async () => ({songs: [], index: 0, position: 0});
    App.api.post = async () => ({});
    App.player = new Player(new PlaybackEngine(new Audio(), document.getElementById("video")));
    App.memory = new QueueMemory(App.player);`);
  return w;
}

async function componentChecks() {
  const w = component();
  await w.eval("App.memory.start()");
  w.songs = [song("s1"), song("s2"), song("s1")];
  w.eval("App.player.playList(songs, 2)");
  check("copie immédiate : ordre, doublons et rang exact", w.eval(
    'App.local.get("queue.1").songs.map(s => s.id).join() === "s1,s2,s1" && App.local.get("queue.1").index === 2'));
  w.eval("App.player.audio.audio.dispatchEvent(new Event('loadedmetadata')); App.player.audio.currentTime = 37.125");
  w.eval("App.api.post = async (url, body, options) => { window.departureOptions = options; return {}; }");
  w.dispatchEvent(new w.Event("pagehide"));
  await w.eval("App.memory.flush()");
  check("départ de page : la requête de sauvegarde utilise keepalive", w.departureOptions.keepalive);
  const saved = memory(w);
  const restored = component(saved);
  restored.eval("App.api.get = async () => { throw new Error('offline'); }");
  await restored.eval("App.memory.start()");
  check("hors réseau : doublon courant et position restaurés sans lecture", restored.eval(
    'App.player.queue.length === 3 && App.player.index === 2 && App.player.position === 37.125 && !App.player.audio.src'));
  restored.eval("App.player.seekBy(10)");
  check("file restaurée en pause : déplacement et sauvegarde de position possibles", restored.eval("App.player.position === 47.125 && App.memory.state.position === 47.125 && !App.player.audio.src"));
  restored.eval("App.player.toggle(); App.player.audio.audio.dispatchEvent(new Event('loadedmetadata'))");
  check("reprise explicite à la position sauvée", restored.eval("App.player.playing && App.player.position === 47.125"));
  restored.eval("App.player.previous()");
  check("précédent remet la position à zéro", restored.eval("App.player.position === 0"));

  const externals = [
    {id: "yt-a", title: "Vidéo", ext: "youtube", youtubeId: "a"},
    {id: "sc-a", title: "Son", ext: "soundcloud", soundcloudUrl: "https://api.soundcloud.com/tracks/1"},
    {id: "jm-a", title: "Piste", ext: "jamendo", streamUrl: "https://example.org/track"},
  ];
  for (let index = 0; index < externals.length; index++) {
    const external = component({"pmw.queue.1": JSON.stringify({songs: externals, index, position: 12,
      dirty: false, remote: JSON.stringify({ids: [], current: "", position: 0})})});
    await external.eval("App.memory.start()");
    check("source " + externals[index].ext + " : file et position locales, sans lecteur ni requête externe", external.eval(
      "App.player.queue.length === 3 && App.player.position === 12 && !App.player.audio.src && !document.querySelector('iframe, script')"));
  }

  const corrupt = component({"pmw.queue.1": '{"songs":null}'});
  await corrupt.eval("App.memory.start()");
  check("copie locale invalide : démarrage possible", corrupt.eval("App.player.queue.length === 0"));
  corrupt.eval(`Object.defineProperty(window, "localStorage", {get() { throw new Error("denied"); }});`);
  await corrupt.eval("App.memory.start()");
  corrupt.songs = [song("s1")];
  corrupt.eval("App.player.playList(songs)");
  await corrupt.eval("App.memory.flush()");
  check("stockage refusé : lecture et sauvegarde API possibles", corrupt.eval("App.player.current.id === 's1'"));

  const full = component();
  await full.eval("App.memory.start()");
  full.songs = [song("s1")];
  full.eval("App.player.playList(songs)");
  full.eval("Object.defineProperty(Storage.prototype, 'setItem', {value() { throw new Error('quota'); }});");
  full.songs = [song("s2")];
  full.eval("App.player.playList(songs)");
  await full.eval("App.memory.flush()");
  check("quota local : la copie périmée est retirée, la sauvegarde serveur continue", full.eval("App.local.get('queue.1', null) === null && !App.memory.state.dirty"));

  const racing = component();
  racing.eval("App.api.get = () => new Promise(resolve => window.finishRestore = resolve)");
  const loading = racing.eval("App.memory.start()");
  racing.songs = [song("s2")];
  racing.eval("App.player.playList(songs)");
  racing.finishRestore({songs: [song("s1")], index: 0, position: 0});
  await loading;
  check("réponse lente : la sélection récente reste en place", racing.eval("App.player.current.id === 's2'"));

  racing.eval(`window.sent = []; window.activeWrites = 0; window.maxWrites = 0;
    App.api.post = (url, body) => {
      sent.push(body); activeWrites++; maxWrites = Math.max(maxWrites, activeWrites);
      return new Promise(resolve => window.finishSave = () => { activeWrites--; resolve({}); });
    };`);
  const saving = racing.eval("App.memory.flush()");
  racing.songs = [song("s1")];
  racing.eval("App.player.add(songs)");
  const newer = racing.eval("App.memory.flush()");
  racing.finishSave();
  await saving;
  await until(() => racing.sent.length === 2);
  racing.finishSave();
  await newer;
  check("écritures sérialisées : le dernier ordre est envoyé", racing.maxWrites === 1 &&
    racing.sent[1].ids.join() === "s2,s1" && racing.eval("!App.memory.state.dirty"));

  const switched = component();
  switched.eval("App.api.get = () => new Promise(resolve => window.finishRestore = resolve)");
  const oldLoading = switched.eval("App.memory.start()");
  switched.eval("App.memory.suspend(); App.user = {id: 2, username: 'alice', roles: ['stream']}; App.api.get = async () => ({songs: [], index: 0, position: 0})");
  await switched.eval("App.memory.start()");
  switched.finishRestore({songs: [song("s1")], index: 0, position: 0});
  await oldLoading;
  check("changement de compte : réponse ancienne ignorée", switched.eval("App.player.queue.length === 0 && App.memory.key === 'queue.2'"));

  const retry = component();
  retry.eval("App.api.get = async () => { throw new Error('offline'); }");
  await retry.eval("App.memory.start()");
  retry.songs = [song("s1")];
  retry.eval("App.api.get = async () => ({songs, index: 0, position: 9}); window.dispatchEvent(new Event('online'))");
  check("aucune copie locale : restauration au retour du réseau", await until(() => retry.eval("App.player.current && App.player.position === 9")));

  for (const dom of doms.splice(0)) dom.window.close();
}

async function client(jar, url, body) {
  const response = await fetch(base + url, {method: body ? "POST" : "GET",
    headers: {Cookie: jar.cookie, "Content-Type": "application/json", "X-Requested-With": "pmw"},
    body: body ? JSON.stringify(body) : undefined});
  const cookie = response.headers.get("set-cookie");
  if (cookie) jar.cookie = cookie.split(";")[0];
  if (!response.ok) throw new Error(url + ": " + response.status);
  return response.json();
}

async function page(jar, saved = {}, network = {offline: false}) {
  const dom = await JSDOM.fromURL(base + "/", {
    resources: "usable", runScripts: "dangerously", pretendToBeVisual: true,
    beforeParse(w) {
      for (const [k, v] of Object.entries(saved)) w.localStorage.setItem(k, v);
      stubMedia(w);
      w.errors = [];
      w.addEventListener("error", event => w.errors.push(event.message));
      w.fetch = async (url, options = {}) => {
        if (network.offline && String(url).startsWith("/api/play-queue")) throw new Error("offline");
        const response = await fetch(new URL(url, base), {...options,
          headers: {...options.headers, Cookie: jar.cookie}});
        const cookie = response.headers.get("set-cookie");
        if (cookie) jar.cookie = cookie.split(";")[0];
        return response;
      };
      w.IntersectionObserver = class { observe() {} disconnect() {} unobserve() {} };
      w.Element.prototype.scrollIntoView = function () {};
    },
  });
  doms.push(dom);
  if (!await until(() => {
    try { return dom.window.eval("App.music.queueMemory && App.music.queueMemory.state"); }
    catch (error) { return false; }
  })) throw new Error("page non prête");
  await dom.window.eval("App.music.queueMemory.ready");
  return dom.window;
}

async function pageChecks() {
  const jar = {cookie: ""};
  await client(jar, "/api/login", {username: "bob", password: "pw2"});
  await client(jar, "/api/play-queue/save", {ids: ["s1", "s2", "s1"], current: "s2", position: 42.375});
  let w = await page(jar);
  await w.eval("App.music.queueMemory.ready");
  w.document.querySelector(".queue-toggle").click();
  check("page : file Subsonic et titre courant affichés au démarrage", w.eval(
    "App.player.queue.map(s => s.id).join() === 's1,s2,s1' && App.player.index === 1") &&
    w.document.querySelectorAll(".queue-row").length === 3 &&
    w.document.querySelector(".queue-row.current .col-title").textContent === "Knowing Me");
  check("page : position conservée, aucun flux chargé ni scrobble", w.eval(
    "App.player.position === 42.375 && !App.player.playing && !App.player.audio.src") &&
    (await client(jar, "/api/now-playing")).entries.length === 0);
  w.eval("App.player.toggle(); App.player.audio.audio.dispatchEvent(new Event('loadedmetadata'))");
  check("page : le bouton lecture reprend le flux au bon endroit", w.eval("App.player.playing && App.player.position === 42.375"));
  w.eval("App.player.move(2, 0); App.player.removeAt(1); App.player.undo()");
  w.ext = {id: "yt:abc", ext: "youtube", youtubeId: "abc", title: "Vidéo", artist: "Auteur", duration: 100};
  w.eval("App.player.playNext([ext])");
  check("page : copie locale immédiate de la file mixte après déplacement et annulation", w.eval(
    'App.music.queueMemory.state.songs.map(s => s.id).join() === "s1,s1,s2,yt:abc" && App.music.queueMemory.state.index === 2'));
  await w.eval("App.music.queueMemory.flush()");
  let remote = await client(jar, "/api/play-queue");
  check("page : sauvegarde API des titres Subsonic seulement, ordre et position", remote.songs.map(s => s.id).join() === "s1,s1,s2" && remote.index === 2 && remote.position === 42.375);
  const saved = memory(w);
  w.eval("App.music.queueMemory.suspend()");
  w = await page(jar, saved);
  await w.eval("App.music.queueMemory.ready");
  check("rafraîchissement : la file mixte et son ordre sont retrouvés", w.eval(
    "App.player.queue.map(s => s.id).join() === 's1,s1,s2,yt:abc' && App.player.index === 2 && !App.player.playing"));

  const network = {offline: true};
  const offlineSaved = memory(w);
  w.eval("App.music.queueMemory.suspend()");
  w = await page(jar, offlineSaved, network);
  check("Subsonic injoignable : copie locale affichée", w.eval("App.player.queue.length === 4 && App.player.index === 2"));
  w.eval("App.player.removeAt(0); App.player.clearUpcoming()");
  await w.eval("App.music.queueMemory.flush()");
  check("hors réseau : les modifications restent en attente", w.eval("App.music.queueMemory.state.dirty && App.player.queue.length === 2"));
  const pending = memory(w);
  w.eval("App.music.queueMemory.suspend()");
  w = await page(jar, pending, network);
  check("rafraîchissement hors réseau : la dernière modification est retrouvée", w.eval("App.player.queue.map(s => s.id).join() === 's1,s2' && App.player.index === 1"));
  network.offline = false;
  w.dispatchEvent(new w.Event("online"));
  check("retour réseau : sauvegarde rattrapée automatiquement", await until(() => w.eval("!App.music.queueMemory.state.dirty")));
  remote = await client(jar, "/api/play-queue");
  check("serveur : ordre rattrapé conforme", remote.songs.map(s => s.id).join() === "s1,s2" && remote.index === 1);

  await client(jar, "/api/play-queue/save", {ids: ["s4"], current: "s4", position: 7});
  const clean = memory(w);
  w.eval("App.music.queueMemory.suspend()");
  w = await page(jar, clean);
  check("autre application : la nouvelle file serveur remplace la copie synchronisée", await until(() => w.eval("App.player.current.id === 's4' && App.player.position === 7")));
  w.eval("App.music.queueMemory.suspend()");
  // Même compte, autre navigateur : aucune copie locale.
  w = await page(jar);
  check("autre navigateur : file et position retrouvées via Subsonic", w.eval("App.player.current.id === 's4' && App.player.position === 7"));
  await client(jar, "/api/logout", {});
  w.eval("App.music.showLogin('')");
  await client(jar, "/api/login", {username: "alice", password: "secret"});
  await w.eval("App.api.get('/api/me').then(me => App.music.start(me))");
  check("reconnexion avec un autre compte : ancienne file et source effacées", await until(() => w.eval(
    "App.user.username === 'alice' && App.player.queue.length === 0 && !App.player.audio.src")));
  w.eval("App.music.queueMemory.suspend()");
  await client(jar, "/api/logout", {});
  await client(jar, "/api/login", {username: "bob", password: "pw2"});
  await w.eval("App.api.get('/api/me').then(me => App.music.start(me))");
  check("reconnexion au compte initial : sa file revient", await until(() => w.eval("App.player.current && App.player.current.id === 's4'")));
  check("page : aucune erreur JavaScript", doms.every(dom => !dom.window.errors || dom.window.errors.length === 0));
  for (const dom of doms.splice(0)) dom.window.close();
}

(async () => {
  await componentChecks();
  await pageChecks();
  console.log(failures ? "ÉCHECS : " + failures : "TOUT PASSE");
  process.exit(failures ? 1 : 0);
})().catch(error => { console.error(error); for (const dom of doms) dom.window.close(); process.exit(2); });
