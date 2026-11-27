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
  let failNextSong = false, holdSongRequests = false, loseNextCommentResponse = false;
  const heldSongs = [], unavailableSongs = new Set();
  const dom = await JSDOM.fromURL(base + "/#/listen-later", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = (url, options) => {
        requests.push(String(url));
        if (String(url) === "/api/recommendation/comment" && loseNextCommentResponse) {
          loseNextCommentResponse = false;
          return bob.request(url, options).then(() => { throw new Error("Connection lost after recording comment"); });
        }
        if (String(url).startsWith("/api/song?")) {
          if (failNextSong) {
            failNextSong = false;
            return Promise.resolve({ok:false, status:503, json:async () => ({error:"subsonic.unreachable"})});
          }
          if (unavailableSongs.has(new URL(url, base).searchParams.get("id"))) {
            return Promise.resolve({ok:false, status:404, json:async () => ({error:"subsonic.error"})});
          }
          if (holdSongRequests) return new Promise(resolve => { heldSongs.push(() => resolve(bob.request(url, options))); });
        }
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
    assert.deepEqual($$(".listen-later-tab").map(tab => tab.dataset.tab), ["received", "bookmarks", "sent"], "Reçues est le premier onglet");
    assert.equal($(".listen-later-tab.on").dataset.tab, "received");
    assert.match($(".listen-later-tabs").textContent, /Reçues.*Marque-pages.*Envoyées/);
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
    await until(() => $(".recommendation-recipient"), "artist recommendation form");
    assert($(".recommendation-recipient"));
    assert(!$$(".recommendation-recipient option").some(option => option.value === "bob"));
    $(".recommendation-recipient").value = "alice";
    $(".recommendation-comment-input").value = "Tu aimeras cet artiste.";
    $(".recommendation-form").dispatchEvent(new window.Event("submit", {cancelable: true}));
    await until(() => !$(".recommendation-form"), "recommendation sent");
    const receivedByAlice = await (await alice.request("/api/listen-later")).json();
    assert.equal(receivedByAlice.recommendations.length, 1);
    assert.equal(receivedByAlice.bookmarks.length, 0);
    assert.equal(receivedByAlice.recommendations[0].recommendations[0].commentPreview, "Tu aimeras cet artiste.");
    console.log("OK advice does not create recipient bookmark");

    // A specific track can be sent from its album, then received as a playable recommendation list.
    const app = window.eval("App"), listeningPage = window.eval("Views.listenLater");
    await navigate("#/album/al1", () => $('.song[data-id="s2"] .recommendation-open'));
    const recommendSong = $('.song[data-id="s2"] .recommendation-open');
    const beforeShare = app.player.current;
    recommendSong.click();
    recommendSong.dispatchEvent(new window.MouseEvent("dblclick", {bubbles:true}));
    assert.equal(app.player.current, beforeShare, "sharing must not start album playback");
    await until(() => $(".recommendation-recipient"), "song recommendation form");
    $(".recommendation-recipient").value = "alice";
    $(".recommendation-form").dispatchEvent(new window.Event("submit", {cancelable:true}));
    await until(() => !$(".recommendation-form"), "song recommendation sent");
    const songReceivedByAlice = (await (await alice.request("/api/listen-later")).json()).recommendations
      .find(group => group.target.kind === "song");
    assert.equal(songReceivedByAlice.target.sourceId, "s2");
    assert.equal(songReceivedByAlice.target.title, "Knowing Me");
    await alice.post("/api/recommendation/remove", songReceivedByAlice.target);

    for (const [sender, sourceId] of [[alice,"s1"], [alice,"s2"], [charlie,"s2"]]) {
      assert.equal((await sender.post("/api/recommendation/send", {
        recipient:"bob", kind:"song", source:"subsonic", sourceId})).status, 200);
    }
    await navigate("#/listen-later", () => $$(".recommendation-songs-table tr.song").length === 2);
    const songOrder = $$(".recommendation-songs-table tr.song").map(row => row.dataset.id);
    assert.equal($(".recommendation-play-all").textContent, "Tout écouter");
    assert.match($('.recommendation-songs-table tr[data-id="s2"] .recommendation-senders').textContent, /alice, charlie|charlie, alice/);
    const songFilter = $(".listen-later-filter");
    songFilter.value = "song";
    songFilter.dispatchEvent(new window.Event("change"));
    assert.equal($$(".recommendation-songs-table tr.song").length, 2);
    assert.equal($$(".bookmark-list .listen-later-card").length, 0);
    console.log("OK specific song sharing and received track list with grouped advisers");
    songFilter.value = "all";
    songFilter.dispatchEvent(new window.Event("change"));

    const original = (await app.api.get("/api/song", {id:"s4"})).song;
    app.player.playList([original], 0);
    failNextSong = true;
    $(".recommendation-play-all").click();
    await until(() => !$(".recommendation-play-all").disabled &&
      $("#toasts").textContent.includes("injoignable"), "song loading error");
    assert.equal(app.player.current.id, "s4");
    assert.equal(app.player.queue.length, 1);

    holdSongRequests = true;
    $(".recommendation-play-all").click();
    $(".recommendation-play-all").click();
    await until(() => heldSongs.length === 2, "one playlist load despite double click");
    assert.equal($(".recommendation-play-all").getAttribute("aria-busy"), "true");
    assert.equal(app.player.current.id, "s4", "keep the current queue until all songs are ready");
    holdSongRequests = false;
    heldSongs.splice(0).forEach(release => release());
    await until(() => app.player.queue.length === 2 && app.player.current.id === songOrder[0], "play all received songs");
    assert.deepEqual(Array.from(app.player.queue, song => song.id), songOrder);
    assert(app.player.queue.every(song => song.duration > 0 && song.albumId));
    app.player.next();
    assert.equal(app.player.current.id, songOrder[1], "playback advances to the next recommended song");
    $('.recommendation-songs-table tr[data-id="' + songOrder[0] + '"] .row-play').click();
    await until(() => app.player.current.id === songOrder[0], "start the recommendation playlist from a row");
    console.log("OK play all, playlist order, next track, row playback and errors preserving the current queue");

    unavailableSongs.add("s1");
    $(".recommendation-play-all").click();
    await until(() => app.player.queue.length === 1 && app.player.current.id === "s2", "skip unavailable recommendation");
    assert.match($("#toasts").textContent, /indisponibles ignorés : 1/);
    unavailableSongs.clear();
    const roles = app.user.roles;
    app.user.roles = roles.filter(role => role !== "stream");
    await listeningPage.render($("#main"), app.music.route);
    assert(!$(".recommendation-play-all"));
    assert(!$(".recommendation-songs-table .row-play"));
    assert($(".recommendation-songs-table .recommendation-remove"));
    app.user.roles = roles;
    await listeningPage.render($("#main"), app.music.route);

    const keepSong = '.recommendation-songs-table tr[data-id="s2"] .listen-later-toggle';
    await until(() => !$(keepSong).disabled, "keep button ready");
    $(keepSong).click();
    await until(() => $$(".bookmark-list .listen-later-card").length === 3, "keep received song as bookmark");
    $('.recommendation-songs-table tr[data-id="s2"] .recommendation-remove').click();
    await until(() => $$(".recommendation-songs-table tr.song").length === 1, "remove one recommended track");
    assert.equal($('.recommendation-songs-table tr.song').dataset.id, "s1");
    assert.equal(app.player.current.id, "s2", "removing a recommendation does not interrupt playback");
    assert.equal($$(".bookmark-list .listen-later-card").length, 3);
    assert.equal((await (await bob.request("/api/listen-later")).json()).recommendations.length, 1);
    $(".recommendation-songs-table .recommendation-remove").click();
    await until(() => !$(".recommendation-songs-table"), "remove the last recommended song");
    assert(!$(".recommendation-play-all"));
    const savedSong = $$(".bookmark-list .listen-later-card").find(card => card.textContent.includes("Knowing Me"));
    assert(savedSong.querySelector(".listen-later-play"));
    assert.match(savedSong.querySelector(".listen-later-name").hash, /^#\/search\//);
    savedSong.querySelector(".listen-later-remove").click();
    await until(() => $$(".bookmark-list .listen-later-card").length === 2, "remove saved song independently");
    await navigate("#/artist/ar1", () => $(".artist-actions .listen-later-toggle:not(:disabled)"));
    console.log("OK stream rights, unavailable songs and individual removal without affecting bookmarks or playback");

    const menu = () => $('.topnav a[href="#/listen-later"]');
    const hasDot = () => menu().classList.contains("recommendations-unread");
    const live = (data = {}) => window.recommendationSources.at(-1).fire("recommendations", data);
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
    const sentBefore = (await (await bob.request("/api/recommendation/discussions?scope=sent")).json()).recommendations.length;
    const archivedSection = $("details.listen-later-archived");
    archivedSection.open = true;
    $$(".bookmark-list .listen-later-card").find(card => card.textContent.includes("Rare")).querySelector(".recommendation-open").click();
    await until(() => $(".recommendation-recipient"), "recommend from listening list");
    $(".recommendation-recipient").value = "alice";
    $(".recommendation-comment-input").value = "Pour les arrangements de ce disque.";
    $(".recommendation-form").dispatchEvent(new window.Event("submit", {cancelable:true}));
    await until(() => $$(".listen-later-sent .listen-later-card").length === sentBefore + 1, "sent list updates without navigating or a server event");
    $(".listen-later-sent .recommendation-bubble").click();
    await until(() => /Pour les arrangements de ce disque/.test($(".listen-later-sent").textContent), "sent thread opens in place");
    $(".listen-later-sent .recommendation-bubble").click();
    await until(() => !$(".listen-later-sent .recommendation-comment"), "sent thread folds away");
    $$(".bookmark-list .listen-later-card").find(card => card.textContent.includes("Rare")).querySelector(".recommendation-open").click();
    await until(() => $(".recommendation-recipient"), "existing advice form");
    $(".recommendation-recipient").value = "alice";
    $(".recommendation-comment-input").value = "Un autre détail à partager.";
    $(".recommendation-form").dispatchEvent(new window.Event("submit", {cancelable:true}));
    await until(() => $(".recommendation-comment-form"), "existing advice opens its single thread");
    assert.equal($(".recommendation-comment-input").value, "Un autre détail à partager.");
    assert.equal($$(".recommendation-comment").length, 1, "a second recommendation submission does not post another comment");
    $(".recommendation-comment-form").dispatchEvent(new window.Event("submit", {cancelable:true}));
    await until(() => $$(".recommendation-comment").length === 2 && !$(".recommendation-comment-form button").disabled, "preserved draft explicitly sent as a comment");
    $(".dialog-head button").click();
    assert.ok(archivedSection.isConnected && archivedSection.open, "the page stays in place: archived section still open");
    assert.equal($$(".listen-later-sent .listen-later-card").length, sentBefore + 1);
    await alice.post("/api/recommendation/remove", {kind:"album", source:"discogs", sourceId:"104"});
    console.log("OK sending from a bookmark refreshes sent advice; an existing advice preserves the draft without duplication");

    const shared = (await (await alice.post("/api/recommendation/send", {
      recipient: "bob", kind: "album", source: "subsonic", sourceId: "al1",
      comment: '<img src=x onerror="alert(1)"> Pour la basse.'})).json()).recommendation;
    live({discussionId: shared.id});
    await until(() => $('.recommendation-list .recommendation-bubble[data-recommendation-id="' + shared.id + '"]'), "private thread entry");
    assert(!$(".recommendation-comment-summary img"), "comment text must not become HTML");
    $('.recommendation-list .recommendation-bubble[data-recommendation-id="' + shared.id + '"]').click();
    await until(() => $(".recommendation-comment-form") && $$(".recommendation-comment").length === 1, "initial comment");
    assert.match($(".recommendation-comment p").textContent, /<img src=x/);
    assert.equal($(".recommendation-comment-input").maxLength, receivedByAlice.commentMaxLength);
    await until(() => !hasDot(), "displayed comments acknowledged");
    const submitComment = text => {
      $(".recommendation-comment-input").value = text;
      $(".recommendation-comment-form").dispatchEvent(new window.Event("submit", {cancelable:true}));
    };
    submitComment("Trop bien, surtout le deuxième titre !");
    $(".recommendation-comment-form").dispatchEvent(new window.Event("submit", {cancelable:true}));
    await until(() => $$(".recommendation-comment").length === 2 && !$(".recommendation-comment-form button").disabled, "one recipient comment despite double submit");
    $(".recommendation-comment-input").value = "Mon brouillon reste ici";
    await alice.post("/api/recommendation/comment", {recommendationId: shared.id, body: "Essaie leur album précédent."});
    live({discussionId: shared.id});
    await until(() => $$(".recommendation-comment").length === 3, "sender continues the exchange");
    assert.equal($(".recommendation-comment-input").value, "Mon brouillon reste ici");
    submitComment("Je vais l’écouter.");
    await until(() => $$(".recommendation-comment").length === 4 && !$(".recommendation-comment-form button").disabled, "unlimited alternating replies");
    console.log("OK dedicated private comments, escaped text, both participants, draft preserved and duplicate submit blocked");

    Object.defineProperty(document, "hidden", {configurable:true, value:true});
    await alice.post("/api/recommendation/comment", {recommendationId: shared.id, body: "Encore un détail."});
    live({discussionId: shared.id});
    await until(hasDot, "hidden thread remains unread");
    assert.equal($$(".recommendation-comment").length, 4);
    Object.defineProperty(document, "hidden", {configurable:true, value:false});
    document.dispatchEvent(new window.Event("visibilitychange"));
    await until(() => $$(".recommendation-comment").length === 5 && !hasDot(), "visible thread catches up");

    loseNextCommentResponse = true;
    submitComment("Une réponse à conserver malgré la coupure.");
    await until(() => $(".recommendation-discussion .page-error").textContent && !$(".recommendation-comment-form button").disabled, "lost comment response");
    assert.equal($(".recommendation-comment-input").value, "Une réponse à conserver malgré la coupure.");
    $(".recommendation-comment-form").dispatchEvent(new window.Event("submit", {cancelable:true}));
    await until(() => $$(".recommendation-comment").length === 6 && !$(".recommendation-comment-form button").disabled, "retry reuses comment request id");
    const history = await (await bob.request("/api/recommendation/comments?id=" + shared.id)).json();
    assert.equal(history.comments.length, 6);
    assert.equal(history.comments.filter(comment => comment.body.startsWith("Une réponse à conserver")).length, 1);
    console.log("OK hidden thread stays unread and network retry keeps exactly one comment");

    await until(() => $('.recommendation-list .recommendation-remove'), "received list after discussion");
    $('.recommendation-list .recommendation-remove').click();
    await until(() => !$(".recommendation-list .listen-later-card"), "archive recommendation with conversation");
    await alice.post("/api/recommendation/comment", {recommendationId: shared.id, body: "La discussion reste accessible."});
    live({discussionId: shared.id});
    await until(() => $(".recommendation-unread-comments") && !$(".recommendation-unread-comments").hidden, "archived thread notification");
    $(".recommendation-unread-comments").click();
    await until(() => $$(".recommendation-comment").length === 7, "open archived thread from notification");
    $(".dialog-head button").click();

    const sentArtist = receivedByAlice.recommendations[0].recommendations[0];
    await alice.post("/api/recommendation/comment", {recommendationId: sentArtist.id, body: "J’ai adoré cet artiste."});
    live({discussionId: sentArtist.id});
    await until(() => $('.listen-later-sent .recommendation-bubble.unread[data-recommendation-id="' + sentArtist.id + '"]'), "reply on a sent recommendation");
    $('.listen-later-sent .recommendation-bubble[data-recommendation-id="' + sentArtist.id + '"]').click();
    await until(() => $$(".recommendation-comment").length === 2 && $(".recommendation-comment-form"), "same thread component on sent advice");
    submitComment("Je suis content que ça te plaise !");
    await until(() => $$(".recommendation-comment").length === 3 && !$(".recommendation-comment-form button").disabled, "sender replies again");
    assert.equal($$(".recommendation-comment-form").length, 1);
    console.log("OK archived conversations remain reachable and sent advice uses the same comment entity and component");

    const threadPage = await (await bob.request("/api/recommendation/comments?id=" + sentArtist.id)).json();
    for (let index = 0; index < threadPage.pageSize + 3; index++) {
      await alice.post("/api/recommendation/comment", {recommendationId: sentArtist.id, body: "Commentaire de pagination " + index});
    }
    live({discussionId: sentArtist.id});
    await until(() => $$(".recommendation-comment").length === threadPage.pageSize + 6, "catch up more than one page of new comments");
    const sentToggle = '.listen-later-sent .recommendation-bubble[data-recommendation-id="' + sentArtist.id + '"]';
    $(sentToggle).click();   // referme le fil déplié
    await until(() => !$(".recommendation-comment"), "collapsing hides the inline thread once folded");
    $(sentToggle).click();
    await until(() => $$(".recommendation-comment").length === threadPage.pageSize && !$(".recommendation-comments-older").hidden
      && !$(".recommendation-comments-older").disabled, "bounded initial comment page");
    $(".recommendation-comments-older").click();
    await until(() => $$(".recommendation-comment").length === threadPage.pageSize + 6 && $(".recommendation-comments-older").hidden, "older comments prepend without duplicates");
    assert.equal(new Set($$(".recommendation-comment").map(node => node.dataset.id)).size, threadPage.pageSize + 6);
    console.log("OK paginated history, multiple-page live catch-up and unique comment nodes");

    // Onglets, pastille, aperçu du dernier commentaire et fil déplié en place sous la pochette.
    for (const [sender, comment] of [[alice, "Premier avis d’Alice."], [charlie, "Et celui de Charlie."]]) {
      const sentGroup = await sender.post("/api/recommendation/send", {recipient: "bob", kind: "album", source: "discogs",
        sourceId: "102", comment});
      assert.equal(sentGroup.status, 200);
    }
    await listeningPage.render($("#main"), app.music.route);
    await until(() => $$(".recommendation-list .listen-later-tile").some(tile =>
      tile.querySelector(".recommendation-comments-all")), "grouped advisers");
    const grouped = $$(".recommendation-list .listen-later-tile").find(tile => tile.querySelector(".recommendation-comments-all"));
    assert.equal(grouped.querySelectorAll(".recommendation-comment-others .recommendation-comment-summary").length, 1);
    assert(grouped.querySelector(".listen-later-new"), "pastille de nouveauté sur la pochette");
    assert(!grouped.querySelector(".recommendation-thread:not([hidden])"), "commentaires repliés au départ");
    assert(!grouped.querySelector(".recommendation-comment"), "aucun commentaire affiché tant qu'on ne déplie pas");
    assert(grouped.querySelector(".recommendation-comments-all").hidden, "les autres conseillers attendent le premier fil");
    grouped.querySelector(".recommendation-bubble").click();
    await until(() => grouped.querySelector(".recommendation-thread:not([hidden]) .recommendation-comment-form"), "thread opens in place");
    assert(grouped.classList.contains("expanded"), "la carte est marquée dépliée (hauteurs libres) quand le fil est ouvert");
    assert(!$(".dialog"), "aucune fenêtre superposée");
    assert(grouped.querySelector(".recommendation-comment-input").rows === 1, "saisie d'une ligne, à la Facebook");
    assert(grouped.querySelector(".recommendation-comment-others").hidden, "les autres conseillers sont repliés");
    const quick = grouped.querySelector(".recommendation-comment-input");
    quick.value = "Envoyé avec Entrée.";
    quick.dispatchEvent(new window.KeyboardEvent("keydown", {key: "Enter", bubbles: true, cancelable: true}));
    await until(() => /Envoyé avec Entrée/.test(grouped.textContent), "Entrée envoie le commentaire");
    assert(!grouped.querySelector(".recommendation-comments-all").hidden);
    grouped.querySelector(".recommendation-comments-all").click();
    assert(!grouped.querySelector(".recommendation-comment-others").hidden, "Voir les autres conseillers les ouvre");
    await until(() => grouped.querySelectorAll(".recommendation-comment-form").length === 2, "other advisers threads open");
    grouped.querySelector(".recommendation-bubble").click();
    assert(grouped.querySelector(".recommendation-thread.folding"), "le repli s'anime avant de masquer le fil");
    await until(() => !grouped.classList.contains("expanded") && !grouped.querySelector(".recommendation-thread:not([hidden])"),
      "tous les fils se referment");
    assert(!grouped.querySelector(".recommendation-thread.folding"));

    const tabs = Object.fromEntries($$(".listen-later-tab").map(tab => [tab.dataset.tab, tab]));
    tabs.bookmarks.click();
    assert(!$("#listen-later-panel-bookmarks").hidden && $("#listen-later-panel-received").hidden);
    assert.equal(tabs.bookmarks.getAttribute("aria-selected"), "true");
    assert(!$(".listen-later-tab-badge").hidden, "pastille rouge sur Reçues quand un autre onglet est ouvert");
    tabs.sent.click();
    assert(!$("#listen-later-panel-sent").hidden);
    tabs.received.click();
    assert($("#listen-later-panel-bookmarks").hidden && !$("#listen-later-panel-received").hidden);
    assert($(".listen-later-tab-badge").hidden);
    console.log("OK tabs with unread badge, grouped advisers and thread unfolding in place");

    // Changing account closes the private thread and discards late results for its previous owner.
    bob.jar.cookie = alice.jar.cookie;
    const me = await (await alice.request("/api/me")).json();
    await window.eval("App.music").start(me);
    await until(() => $(".bookmark-list") && !$(".bookmark-list .listen-later-card"), "account reset");
    assert.equal($$(".recommendation-list .listen-later-card").length, 1);
    assert(!$(".recommendation-discussion"));
    assert.deepEqual(errors, []);
    console.log("OK account isolation and no browser errors");
  } finally {
    dom.window.close();
    agent.destroy();
  }
})().catch(error => { console.error(error); agent.destroy(); process.exitCode = 1; });
