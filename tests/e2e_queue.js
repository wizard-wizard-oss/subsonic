// File d'attente commune dans jsdom : file retrouvée au démarrage, ajout depuis un téléphone. Usage : node tests/e2e_queue.js PORT [jsdom]
const port = process.argv[2];
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + port;
const wait = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok) => { console.log((ok ? "OK   " : "FAIL ") + name); if (!ok) failures++; };
const post = (url, body, headers) => fetch(url, {method: "POST", headers: Object.assign({"Content-Type": "application/json", "X-Requested-With": "pm"}, headers || {}), body: JSON.stringify(body)});

(async () => {
  await post(base + "/queue/save", {currentIndex: 0, items: [
    {track: {id: "s1", title: "Dancing Queen", artist: "ABBA"}}, {track: {id: "s2", title: "Knowing Me", artist: "ABBA"}}]});
  const dom = await JSDOM.fromURL(base + "/", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(new URL(u, base), Object.assign({}, o, {headers: Object.assign({"X-Requested-With": "pm"}, (o && o.headers) || {})}));
      const proto = w.HTMLMediaElement.prototype;
      proto.play = function () { Object.defineProperty(this, "paused", {value: false, configurable: true}); return Promise.resolve(); };
      proto.pause = function () { Object.defineProperty(this, "paused", {value: true, configurable: true}); };
      proto.load = function () {};
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
  await ready('typeof queue !== "undefined" && queue.length === 2');
  check("file retrouvée au démarrage", w.eval("queue.length") === 2 && w.eval("qi") === 0 && w.eval("cur().id") === "s1");
  check("pas de lecture automatique au démarrage", w.eval("audio.paused"));

  w.eval("playIdx(0)"); await wait(300);
  const remote = await (await post(base + "/ext/remote", {})).json();
  const phoneUrl = new URL(remote.url), phone = "http://127.0.0.1:" + phoneUrl.port, code = phoneUrl.searchParams.get("c");
  const found = await (await post(phone + "/tel/search", {code, text: "waterloo"})).json();
  check("téléphone : recherche dans la bibliothèque", found.songs.some(s => s.title === "Waterloo"));
  const waterloo = found.songs.find(s => s.title === "Waterloo");
  await post(phone + "/tel/queue/add", {code, id: waterloo.id, mode: "next"});
  await post(phone + "/tel/queue/add", {code, id: waterloo.id, mode: "end"});
  await wait(2200);
  check("ajout « après ce titre » rangé juste après le titre en cours", w.eval("queue[1].title") === "Waterloo" && w.eval("queue[1]._addedBy") === "phone");
  check("ajout « à la fin » rangé en dernier", w.eval("queue[queue.length - 1].title") === "Waterloo" && w.eval("queue.length") === 4);
  check("message sur l'écran", $("#toast").textContent.includes("téléphone"));
  await wait(1200);
  const state = await (await fetch(base + "/queue/state")).json();
  check("file enregistrée sur le Pi avec qui a ajouté quoi", state.items.length === 4 && state.items[1].addedBy === "phone" && state.currentIndex === 0);
  const view = await (await post(phone + "/tel/queue", {code})).json();
  check("téléphone : voit ce qui va passer", view.current.title === "Dancing Queen" && view.upcoming[0].title === "Waterloo");
  // --- page du téléphone ---
  const phoneDom = await JSDOM.fromURL(phone + "/tel?c=" + code, {runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(pw) { pw.errors = []; pw.addEventListener("error", e => pw.errors.push(e.message)); pw.fetch = (u, o) => fetch(new URL(u, phone), o); }});
  await wait(1500);
  const pd = phoneDom.window.document;
  check("page téléphone : file affichée", pd.querySelector("#queue").textContent.includes("Dancing Queen"));
  check("page téléphone : lien et envoi de fichier proposés", !!pd.querySelector("#link") && !!pd.querySelector("#file"));
  check("page téléphone : aucune erreur JavaScript", phoneDom.window.errors.length === 0);
  check("aucune erreur JavaScript", w.errors.length === 0);
  console.log(failures ? "ÉCHECS : " + failures : "TOUT PASSE");
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
