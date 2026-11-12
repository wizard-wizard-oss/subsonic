// Listening intentions in the real application served by the simulated Subsonic harness.
// Usage: node tests/e2e_listen_later.js PORT [jsdom]
const assert = require("node:assert/strict");
const http = require("node:http");
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + process.argv[2];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const requests = [];
const agent = new http.Agent({keepAlive: true, maxSockets: 6});

function client() {
  const jar = {cookie: ""};
  const request = (url, options = {}) => new Promise((resolve, reject) => {
    const headers = Object.assign({}, options.headers, {Cookie: jar.cookie});
    const call = http.request(new URL(url, base), {method: options.method || "GET", headers, agent}, response => {
      const cookie = response.headers["set-cookie"];
      if (cookie) jar.cookie = cookie[0].split(";")[0];
      let body = "";
      response.setEncoding("utf8");
      response.on("data", part => { body += part; });
      response.on("end", () => resolve({
        ok: response.statusCode >= 200 && response.statusCode < 300, status: response.statusCode,
        json: async () => JSON.parse(body), text: async () => body,
        headers: {get: name => response.headers[name.toLowerCase()]}
      }));
    });
    call.on("error", reject);
    call.end(options.body);
  });
  const post = (url, body) => request(url, {method: "POST", headers: {
    "Content-Type": "application/json", "X-Requested-With": "pmw"}, body: JSON.stringify(body)});
  return {jar, request, post};
}

(async () => {
  const alice = client(), bob = client(), charlie = client();
  for (const [person, username, password] of [[alice, "alice", "secret"], [bob, "bob", "pw2"], [charlie, "charlie", "pw3"]]) {
    assert.equal((await person.post("/api/login", {username, password})).status, 200);
  }
  const errors = [];
  let holdNextStatus = false, heldStatus = null, holdNextRead = false, heldRead = null, failNextList = false;
  const dom = await JSDOM.fromURL(base + "/#/listen-later", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = (url, options) => {
        requests.push(String(url));
        if (String(url) === "/api/recommendation/status" && holdNextStatus) {
          holdNextStatus = false;
          return bob.request(url, options).then(response => new Promise(resolve => {
            heldStatus = () => resolve(response);
          }));
        }
        if (String(url) === "/api/recommendation/read" && holdNextRead) {
          holdNextRead = false;
          return new Promise(resolve => { heldRead = () => resolve(bob.request(url, options)); });
        }
        if (String(url) === "/api/listen-later" && failNextList) {
          failNextList = false;
          return Promise.resolve({ok:false, status:503, json:async () => ({error:"subsonic.unreachable"})});
        }
        return bob.request(url, options);
      };
      window.recommendationSources = [];
      window.EventSource = class {
        constructor() {
          this.listeners = {};
          this.closed = false;
          window.recommendationSources.push(this);
          setTimeout(() => this.fire("open"), 0);
        }
        addEventListener(kind, callback) { (this.listeners[kind] ||= []).push(callback); }
        fire(kind, data = {}) {
          if (!this.closed) (this.listeners[kind] || []).forEach(callback => callback({data:JSON.stringify(data)}));
        }
        close() { this.closed = true; }
      };
      window.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
      window.Element.prototype.scrollIntoView = function () {};
      window.HTMLMediaElement.prototype.play = () => Promise.resolve();
      window.HTMLMediaElement.prototype.pause = function () {};
      window.HTMLMediaElement.prototype.load = function () {};
      window.addEventListener("error", event => errors.push(event.message));
    }
  });
  const window = dom.window, document = window.document;
  const $ = selector => document.querySelector(selector);
  const $$ = selector => [...document.querySelectorAll(selector)];
  const until = async (test, name) => {
    for (let attempt = 0; attempt < 200; attempt++) { if (test()) return; await delay(50); }
    throw new Error("Timed out: " + name + "; main=" + $("#main").textContent.slice(0, 500));
  };
  const navigate = async (hash, test) => {
    window.location.hash = hash;
    await until(test, hash);
  };
  try {
    await until(() => $(".bookmark-list") && !$("#app").hidden, "listening page");
    assert.match($("#main").textContent, /Mes marque-pages/);
    assert.match($("#main").textContent, /recommandations reçues/);
    $("#open-settings").click();
    assert.equal($(".settings-listen-later").hash, "#/listen-later");
    $(".settings-listen-later").click();
    assert(!$(".dialog"));
    await delay(0); // Let the anchor's default navigation finish before the next user action.
    console.log("OK separate empty sections and settings navigation");

    await navigate("#/album/al1", () => $(".album-actions .listen-later-toggle:not(:disabled)"));
    $(".album-actions .listen-later-toggle").click();
    await until(() => $(".album-actions .listen-later-toggle").getAttribute("aria-pressed") === "true", "save album");
    await navigate("#/artist/ar1", () => $(".artist-actions .listen-later-toggle:not(:disabled)"));
    $(".artist-actions .listen-later-toggle").click();
    await until(() => $(".artist-actions .listen-later-toggle").getAttribute("aria-pressed") === "true", "save artist");
    console.log("OK bookmark album and artist from existing pages");

    $(".artist-actions .recommendation-open").click();
    assert($(".recommendation-recipient"));
    assert(!$$(".recommendation-recipient option").some(option => option.value === "bob"));
    $(".recommendation-recipient").value = "alice";
    $(".recommendation-form").dispatchEvent(new window.Event("submit", {cancelable: true}));
    await until(() => !$(".recommendation-form"), "recommendation sent");
    const receivedByAlice = await (await alice.request("/api/listen-later")).json();
    assert.equal(receivedByAlice.recommendations.length, 1);
    assert.equal(receivedByAlice.bookmarks.length, 0);
    console.log("OK advice does not create recipient bookmark");

    const menu = () => $('.topnav a[href="#/listen-later"]');
    const hasDot = () => menu().classList.contains("recommendations-unread");
    const live = () => window.recommendationSources.at(-1).fire("recommendations");
    const advise = async (sourceId, sender = alice) => {
      assert.equal((await sender.post("/api/recommendation/send", {
        recipient: "bob", kind: "album", source: "discogs", sourceId})).status, 200);
    };
    assert.equal(hasDot(), false);
    await advise("104");
    live();
    await until(hasDot, "new recommendation indicator");
    assert.match(menu().getAttribute("aria-label"), /nouveaux conseils/);

    holdNextStatus = true;
    live();
    await until(() => heldStatus, "hold stale unread response");
    await navigate("#/listen-later", () => $(".recommendation-senders") && !hasDot());
    assert.equal((await (await bob.request("/api/recommendation/status")).json()).unread, false);
    heldStatus();
    await delay(50);
    assert.equal(hasDot(), false);
    await advise("104");
    live();
    await delay(50);
    assert.equal(hasDot(), false);
    console.log("OK live unread indicator, persistent acknowledgment and stale response ignored");

    await navigate("#/artist/ar1", () => $(".artist-actions .listen-later-toggle:not(:disabled)"));
    await bob.post("/api/recommendation/remove", {kind:"album", source:"discogs", sourceId:"104"});
    await advise("104");
    holdNextRead = true;
    await navigate("#/listen-later", () => heldRead && $(".recommendation-senders"));
    await advise("101");
    heldRead();
    await until(() => !holdNextRead && hasDot(), "advice arriving during acknowledgment remains unread");
    await delay(50);
    assert.equal($$(".recommendation-list .listen-later-card").length, 1);
    assert.equal((await (await bob.request("/api/recommendation/status")).json()).unread, true);
    live();
    await until(() => $$(".recommendation-list .listen-later-card").length === 2 && !hasDot(), "display and acknowledge new advice");
    console.log("OK advice arriving during consultation is read only after display");

    Object.defineProperty(document, "hidden", {configurable:true, value:true});
    await advise("104", charlie);
    live();
    await until(hasDot, "hidden page keeps unread advice");
    assert(!$(".recommendation-list").textContent.includes("charlie"));
    Object.defineProperty(document, "hidden", {configurable:true, value:false});
    document.dispatchEvent(new window.Event("visibilitychange"));
    await until(() => $(".recommendation-list")?.textContent.includes("charlie") && !hasDot(), "visible page catches up");
    console.log("OK background tab does not acknowledge hidden advice");

    await navigate("#/artist/ar1", () => $(".artist-actions .listen-later-toggle:not(:disabled)"));
    await advise("103");
    live();
    await until(hasDot, "new advice before failed page load");
    failNextList = true;
    await navigate("#/listen-later", () => $("#main .page-error"));
    assert.equal(hasDot(), true);
    $("#main button").click();
    await until(() => $$(".recommendation-list .listen-later-card").length === 3 && !hasDot(), "retry marks successfully displayed advice");
    for (const sourceId of ["101","103","104"]) {
      await bob.post("/api/recommendation/remove", {kind:"album", source:"discogs", sourceId});
    }
    await navigate("#/artist/ar1", () => $(".artist-actions .listen-later-toggle:not(:disabled)"));
    live();
    await until(() => !hasDot(), "clear dismissed advice");
    console.log("OK failed page load preserves indicator and retry clears it");

    const suggestion = {recipient: "bob", kind: "album", source: "discogs", sourceId: "104"};
    for (const sender of [alice, charlie, alice]) assert.equal((await sender.post("/api/recommendation/send", suggestion)).status, 200);
    await navigate("#/listen-later", () => $$(".recommendation-list .listen-later-card").length === 1);
    assert.equal($$(".bookmark-list .listen-later-card").length, 2);
    assert.match($(".recommendation-senders").textContent, /alice/);
    assert.match($(".recommendation-senders").textContent, /charlie/);
    assert.equal($(".recommendation-list .listen-later-name").href, "https://www.discogs.com/release/104");
    $(".recommendation-list .listen-later-toggle").click();
    await until(() => $$(".bookmark-list .listen-later-card").length === 3, "keep recommended album");
    assert.equal($$(".recommendation-list .listen-later-card").length, 1);
    console.log("OK multiple advisers and optional duplicate personal bookmark");

    const filter = $(".listen-later-filter");
    filter.value = "artist";
    filter.dispatchEvent(new window.Event("change"));
    assert.equal($$(".bookmark-list .listen-later-card").length, 1);
    assert.equal($$(".recommendation-list .listen-later-card").length, 0);
    filter.value = "all";
    filter.dispatchEvent(new window.Event("change"));
    $(".recommendation-remove").click();
    await until(() => !$(".recommendation-list .listen-later-card"), "dismiss recommendations");
    assert.equal($$(".bookmark-list .listen-later-card").length, 3);
    console.log("OK filters and independent recommendation dismissal");
    const localCard = $$(".bookmark-list .listen-later-card").find(card => card.textContent.includes("Arrival"));
    localCard.querySelector(".listen-later-remove").click();
    await until(() => $$(".bookmark-list .listen-later-card").length === 2, "remove personal bookmark");
    console.log("OK personal bookmark removal");

    const search = $$(".bookmark-list .listen-later-card").find(card => card.textContent.includes("Rare")).querySelector(".listen-later-search");
    assert.match(search.hash, /^#\/search\//);
    search.click();
    await until(() => requests.some(url => url.startsWith("/api/search?") && url.includes("Rare")) && $(".ext-youtube"), "existing search");
    console.log("OK existing Subsonic and YouTube search reused");

    await navigate("#/discogs/artist/7", () => $("#main > .listening-actions .listen-later-toggle:not(:disabled)"));
    $("#main > .listening-actions .listen-later-toggle").click();
    await until(() => $("#main > .listening-actions .listen-later-toggle").getAttribute("aria-pressed") === "true", "save external artist");
    await until(() => $(".discogs-album .listen-later-toggle"), "catalog bookmark controls");
    assert.equal($$(".discogs-album .listening-actions").length, $$(".discogs-album").length);
    console.log("OK shared Discogs cards and external artist controls");

    await navigate("#/listen-later", () => $$(".bookmark-list .listen-later-card").length === 3);
    bob.jar.cookie = alice.jar.cookie;
    const me = await (await alice.request("/api/me")).json();
    await window.eval("App.music").start(me);
    await until(() => $(".bookmark-list") && !$(".bookmark-list .listen-later-card"), "account reset");
    assert.equal($$(".recommendation-list .listen-later-card").length, 1);
    assert.deepEqual(errors, []);
    console.log("OK account isolation and no browser errors");
  } finally {
    dom.window.close();
    agent.destroy();
  }
})().catch(error => { console.error(error); agent.destroy(); process.exitCode = 1; });
