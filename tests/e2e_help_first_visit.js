// Première visite de Help dans jsdom : la page s'ouvre d'office une seule fois par compte, puis est notée « vue ».
// Usage : node tests/e2e_help_first_visit.js PORT [jsdom]   (serveur de test lancé avec E2E_HELP_UNSEEN=1)
const port = process.argv[2];
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + port;
const wait = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok) => { console.log((ok ? "OK   " : "FAIL ") + name); if (!ok) failures++; };

/** Une page du site avec son cookie : même session d'un chargement à l'autre, comme un navigateur. */
async function open(path, jar) {
  const dom = await JSDOM.fromURL(base + path, {
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
      w.EventSource = class { addEventListener() {} close() {} };
      w.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
      w.CSS = w.CSS || {escape: s => String(s).replace(/["\\]/g, "\\$&")};
      w.Element.prototype.scrollIntoView = function () {};
      const proto = w.HTMLMediaElement.prototype;
      proto.play = function () { return Promise.resolve(); };
      proto.pause = function () {};
      proto.load = function () {};
      w.errors = [];
      w.addEventListener("error", e => w.errors.push(e.message));
    },
  });
  const w = dom.window, d = w.document;
  const until = async (test, ms) => { for (let i = 0; i < (ms || 5000) / 50; i++) { if (test()) return true; await wait(50); } return false; };
  const $ = selector => d.querySelector(selector);
  const login = async (username, password) => {
    await until(() => d.readyState === "complete" && !$("#login").hidden, 12000);
    const form = $("#login-form");
    form.elements.username.value = username; form.elements.password.value = password;
    form.dispatchEvent(new w.Event("submit", {cancelable: true}));
    return until(() => !$("#app").hidden && $("#me .me-name") && $("#me .me-name").textContent === username, 12000);
  };
  return {w, d, $, until, login, close: () => w.close()};
}

/** Ce que le serveur a retenu pour ce compte. */
async function helpSeen(jar) {
  const response = await fetch(base + "/api/me", {headers: {Cookie: jar.cookie}});
  return (await response.json()).preferences.help_seen;
}

(async () => {
  const alice = {cookie: ""};
  let page = await open("/", alice);
  check("première connexion : on se connecte", await page.login("alice", "secret"));
  check("première connexion : la page Help s'ouvre avant les autres",
        await page.until(() => page.w.location.hash === "#/whatsnew" && page.$("#main h1") &&
                               page.$("#main h1").textContent === "Bienvenue dans le sub"));
  check("première connexion : le menu Help est actif", page.$('.topnav a[href="#/whatsnew"]').classList.contains("active"));
  check("première connexion : « vu » est noté pour le compte", await (async () => {
    for (let i = 0; i < 40 && !(await helpSeen(alice)); i++) await wait(50);
    return helpSeen(alice);
  })());
  check("première connexion : aucune erreur JavaScript", page.w.errors.length === 0);

  page = await open("/", alice);
  check("deuxième visite : déjà connecté, on arrive sur l'accueil", await page.until(() => !page.$("#app").hidden) &&
        await page.until(() => page.$("#main") && page.$("#main").textContent.length > 0));
  check("deuxième visite : Help n'est plus imposée", page.w.location.hash !== "#/whatsnew" &&
        !(page.$("#main h1") && page.$("#main h1").textContent === "Bienvenue dans le sub"));

  const bob = {cookie: ""};
  page = await open("/#/album/al1", bob);
  check("lien direct : connexion de bob", await page.login("bob", "pw2"));
  await wait(600);
  check("lien direct : on respecte la page demandée", page.w.location.hash === "#/album/al1");
  check("lien direct : Help n'est pas notée comme vue", (await helpSeen(bob)) === false);
  page.w.location.hash = "#/whatsnew";
  check("visite volontaire : Help est notée comme vue", await (async () => {
    for (let i = 0; i < 40 && !(await helpSeen(bob)); i++) await wait(50);
    return helpSeen(bob);
  })());
  check("visite volontaire : aucune erreur JavaScript", page.w.errors.length === 0);

  console.log(failures ? failures + " contrôle(s) en échec" : "Première visite de Help : tous les contrôles réussis");
  process.exit(failures ? 1 : 0);
})().catch(error => { console.error(error); process.exit(1); });
