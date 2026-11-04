// Lecture haute fidélité dans jsdom : la page pilote (un faux) mpv. Usage : node tests/e2e_hifi.js PORT [jsdom]
const port = process.argv[2];
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + port;
const wait = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok) => { console.log((ok ? "OK   " : "FAIL ") + name); if (!ok) failures++; };
const post = (path, body) => fetch(base + path, {method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "pm"}, body: JSON.stringify(body)});
const state = async () => (await fetch(base + "/player/state")).json();

(async () => {
  await post("/player/cmd", {action: "enable", value: true});
  const dom = await JSDOM.fromURL(base + "/", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(new URL(u, base), Object.assign({}, o, {headers: Object.assign({"X-Requested-With": "pm"}, (o && o.headers) || {})}));
      const proto = w.HTMLMediaElement.prototype;
      proto.play = function () { return Promise.resolve(); }; proto.pause = function () {}; proto.load = function () {};
      w.errors = []; w.addEventListener("error", e => w.errors.push(e.message));
    }
  });
  const w = dom.window, $ = s => w.document.querySelector(s);
  // la page se charge plus ou moins vite selon la machine : on attend qu'elle soit prête (15 s au plus)
  const ready = async (expression, ms) => {
    for (let i = 0; i < (ms || 15000) / 100; i++) {
      try { if (w.eval(expression)) return; } catch (e) { /* scripts pas encore chargés */ }
      await wait(100);
    }
  };
  await ready('typeof audio !== "undefined" && audio.el instanceof MpvAudio');
  check("haute fidélité : le lecteur de la page passe par mpv", w.eval("audio.el instanceof MpvAudio"));
  w.eval('playQueue([{id:"s1", title:"Dancing Queen", artist:"ABBA"}, {id:"s2", title:"Knowing Me", artist:"ABBA"}], 0)');
  await wait(1200);
  let s = await state();
  check("haute fidélité : fichier original demandé à mpv", s.url === "/rest/stream.view?id=s1&format=raw");
  check("haute fidélité : titre suivant préchargé (sans blanc)", s.queued === "/rest/stream.view?id=s2&format=raw");
  check("haute fidélité : la page voit la lecture", !w.eval("audio.paused") && w.eval("audio.duration") === 261);
  w.eval("audio.pause()"); await wait(800);
  check("haute fidélité : pause transmise à mpv", (await state()).paused);
  w.eval("audio.play()"); await wait(800);
  check("haute fidélité : reprise transmise à mpv", !(await state()).paused);
  await post("/__test/mpv", {cmd: "test-finish"}); await wait(1500);
  s = await state();
  check("haute fidélité : enchaînement sur le titre suivant", w.eval("cur().id") === "s2" && s.url === "/rest/stream.view?id=s2&format=raw");
  check("haute fidélité : lecture continue après l'enchaînement", !s.paused);
  await post("/player/cmd", {action: "enable", value: false});
  check("aucune erreur JavaScript", w.errors.length === 0);
  console.log(failures ? "ÉCHECS : " + failures : "TOUT PASSE");
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
