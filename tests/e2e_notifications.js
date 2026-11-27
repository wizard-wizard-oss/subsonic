// Notifications sur le site réel de test : comptes séparés, envoi, lecture et reprise.
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
  const admin = client(), jar = {cookie:""};
  await admin.post("/api/login", {username:"alice", password:"secret"});
  let loseSendResponse = false, failList = false;
  const dom = await JSDOM.fromURL(base + "/#/notifications", {
    runScripts:"dangerously", resources:"usable", pretendToBeVisual:true,
    beforeParse(w) {
      w.fetch = async (url, options = {}) => {
        if (String(url).split("?")[0] === "/api/notifications" && failList) {
          failList = false;
          return {ok:false, status:503, json:async () => ({error:"subsonic.unreachable"})};
        }
        const response = await fetch(new URL(url, base), {...options, headers:{...options.headers, Cookie:jar.cookie}});
        const cookie = response.headers.get("set-cookie");
        if (cookie) jar.cookie = cookie.split(";")[0];
        if (String(url) === "/api/notifications/send" && loseSendResponse) {
          loseSendResponse = false;
          throw new Error("Simulated lost response after successful delivery");
        }
        return response;
      };
      w.EventSource = makeEventSource(jar);
      w.IntersectionObserver = class {observe() {} unobserve() {} disconnect() {}};
      w.Element.prototype.scrollIntoView = function () {};
      w.HTMLMediaElement.prototype.play = () => Promise.resolve();
      w.HTMLMediaElement.prototype.pause = function () {};
      w.HTMLMediaElement.prototype.load = function () {};
      w.errors = [];
      w.addEventListener("error", event => w.errors.push(event.message));
    }
  });
  const w=dom.window, $=selector=>w.document.querySelector(selector), $$=selector=>[...w.document.querySelectorAll(selector)];
  const until = async test => { for (let i=0;i<200;i++) {if(test()) return true;await wait(50);}return false;};
  const login = async (username,password) => {
    await until(() => !$("#login").hidden);
    const form=$("#login-form"); form.elements.username.value=username;form.elements.password.value=password;
    form.dispatchEvent(new w.Event("submit",{cancelable:true}));
    return until(()=>!$("#app").hidden && $("#me .me-name") && $("#me .me-name").textContent===username && $(".notifications-list"));
  };
  try {
    check("notifications : connexion et page vide", await login("bob","pw2") && await until(()=>$(".notifications-status").textContent.includes("aucune notification")));
    check("notifications : aucun formulaire administratif pour un membre", !$(".notification-compose"));
    check("compte : notifications et déconnexion regroupées sous la photo", !!$("#account-menu #nav-notifications") && !!$("#account-menu #logout") && !$(".topnav #nav-notifications"));
    $("#account-toggle").click();
    check("compte : clic sur la photo ouvre le menu", $("#account-menu").open);
    $("#main h1").click();
    check("compte : clic extérieur ferme le menu", !$("#account-menu").open);
    $("#account-toggle").click();
    $("#account-toggle").dispatchEvent(new w.KeyboardEvent("keydown", {key:"Escape", bubbles:true, cancelable:true}));
    check("compte : Échap ferme et rend le focus à la photo", !$("#account-menu").open && w.document.activeElement.id === "account-toggle");

    check("notifications : aucune pastille au départ", $("#notifications-badge").hidden);
    const message={recipient:"bob",title:"Envoi retiré",body:'Les MP3 seuls ne sont pas autorisés. <img src=x onerror="alert(1)">',requestId:"e2e-notification-0001"};
    const delivery=await admin.post("/api/notifications/send",message);
    check("notifications : envoi administratif accepté", delivery.status===200);
    check("notifications : pastille reçue par SSE", await until(()=>!$("#notifications-badge").hidden && $("#notifications-badge").textContent==="1"));
    check("notifications : pastille rouge sur la photo, menu fermé", !$("#account-notifications-badge").hidden && !$("#account-menu").open);
    $("#account-toggle").click(); $("#nav-notifications").click();
    check("compte : choisir Notifications ferme le menu sans effacer la pastille", !$("#account-menu").open && !$("#account-notifications-badge").hidden);
    $(".notifications-refresh").click();
    check("notifications : message privé affiché comme texte", await until(()=>$(".notification-body")) && $(".notification-body").textContent===message.body && !$(".notification-body img"));
    check("notifications : afficher le message ne le marque pas lu automatiquement", !$("#notifications-badge").hidden && $(".notification-card").classList.contains("unread"));
    $(".notification-read").click();
    check("notifications : lecture et pastille synchronisées", await until(()=>$("#notifications-badge").hidden && !$(".notification-card").classList.contains("unread") && $("#account-notifications-badge").hidden));
    $(".notifications-refresh").click();
    check("notifications : message conservé après lecture", await until(()=>$(".notification-body")) && $(".notification-read").hidden);
    failList=true;$(".notifications-refresh").click();
    check("notifications : erreur et reprise disponibles", await until(()=>!$(".notifications-more").hidden && $(".notifications-status").textContent.includes("injoignable")));
    $(".notifications-more").click();
    check("notifications : reprise sans doublon", await until(()=> $$(".notification-card").length===1));
    await w.eval("App.api.post('/api/logout').then(() => App.music.showLogin(''))");
    check("notifications : pastille remise à zéro à la déconnexion", await until(()=>!$("#login").hidden) && $("#notifications-badge").hidden);
    check("notifications : connexion de l’administrateur", await login("alice","secret") && await until(()=>$(".notification-compose form")));
    check("notifications : le compte suivant ne voit pas les messages de bob", $$(".notification-card").length===0);
    $(".notification-compose").open=true;
    const form=$(".notification-compose form");
    form.elements.recipient.value="bob";form.elements.title.value="Règle des envois";form.elements.body.value="Envoyer uniquement des albums en ZIP.";
    loseSendResponse=true;
    form.dispatchEvent(new w.Event("submit",{cancelable:true}));
    check("notifications : échec réseau après livraison expliqué", await until(()=>!form.querySelector("button").disabled && form.querySelector('[role="status"]').textContent!=="Envoi…"));
    form.dispatchEvent(new w.Event("submit",{cancelable:true}));
    check("notifications : nouvel essai confirmé", await until(()=>form.querySelector('[role="status"]').textContent.includes("envoyée à bob")));
    await w.eval("App.api.post('/api/logout').then(() => App.music.showLogin(''))");await login("bob","pw2");
    check("notifications : une seule livraison malgré la réponse perdue", await until(()=>$$(".notification-card").length===2) && $$(".notification-body").filter(node=>node.textContent==="Envoyer uniquement des albums en ZIP.").length===1);
    check("notifications : aucun formulaire après changement de compte", !$(".notification-compose"));
    await until(() => $(".sidebar-retry") || $(".artist"));
    check("notifications : aucune erreur JavaScript", w.errors.length===0);
  } finally { w.eval("App.live.stop()");dom.window.close(); }
  if(failures) throw new Error(failures+" notification checks failed");
  console.log("Notifications : tous les contrôles passent.");
})().catch(error=>{console.error(error);process.exitCode=1;});
