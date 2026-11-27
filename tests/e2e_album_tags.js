// Album tag editor in the real PC shell, with deterministic metadata API responses.
// Usage: node tests/e2e_album_tags.js PORT [jsdom]
const assert = require("node:assert/strict");
const http = require("node:http");
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + process.argv[2];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const requests = [], errors = [], tagWrites = [];
const agent = new http.Agent({keepAlive: true, maxSockets: 6});
let cookie = "", failPreview = false, failSave = false, failOperation = false, operationReads = 0, mappingMode = "normal", styleMode = "normal";
let controlledOperation = false;
const pendingMetadata = new Map();
const holdMetadata = path => new Promise(resolve => pendingMetadata.set(path, resolve));
const original = [
  ["One", "Band", "band", "Rock", "2021"],
  ["Two", "Band", "Band", "Indie rock", "2021"],
  ["Guest", "Band feat. Nora", "Band", "", "2021"],
  ["Four", "band", "band", "Rock", ""],
  ["Five", "Band", "Band", "Indie rock", "2021"],
  ["Six", "Band", "Band", "", "2021"]
].map(([title, artist, albumArtist, genre, year], index) => ({
  id: "file" + (index + 1), editable: true, reason: "", format: "mp3", duration: 180 + index,
  tags: {title, artist, albumArtist, genre, year, album: "Album", track: String(index + 1), disc: "1"}
}));
const snapshot = () => ({albumId: "fdir-al1", name: "Album dossier", artist: "Artiste dossier",
  revision: "revision-1", tracks: JSON.parse(JSON.stringify(original))});
const response = (data, status = 200) => ({ok: status >= 200 && status < 300, status, json: async () => data});
const client = (url, options = {}) => new Promise((resolve, reject) => {
  const call = http.request(new URL(url, base), {method: options.method || "GET", agent,
    headers: {...options.headers, Cookie: cookie}}, result => {
    if (result.headers["set-cookie"]) cookie = result.headers["set-cookie"][0].split(";")[0];
    let body = ""; result.setEncoding("utf8"); result.on("data", part => { body += part; });
    result.on("end", () => resolve(response(body ? JSON.parse(body) : {}, result.statusCode)));
  });
  call.on("error", reject); call.end(options.body);
});

function metadata(url, options) {
  const parsed = new URL(url, base), path = parsed.pathname;
  requests.push({path, query: parsed.searchParams, options});
  if (path === "/api/tags/status") return response({fields: ["title", "artist", "albumArtist", "album", "year", "genre", "track", "disc"], writable: true, providers: {musicbrainz: true, discogs: true},
    formats: ["mp3", "flac"], limits: {text: 500, tracks: 500, number: 999, yearMin: 1000, yearMax: 9999}});
  if (path === "/api/tags/album") return response(snapshot());
  if (path === "/api/tags/search") return response({source: parsed.searchParams.get("source"), candidates: [
    {id: "original", title: "Album original", artist: "Band", date: "2021", country: "FR", format: "CD", trackCount: 6,
      genres: ["Rock"], styles: ["Indie rock"]},
    {id: "deluxe", title: "Album deluxe", artist: "Band", date: "2023", country: "EU", format: "CD", trackCount: 8},
    {id: "unknown", title: "Autre édition", artist: "Band", date: "", country: "", format: "", trackCount: 0}
  ]});
  if (path === "/api/tags/release") return response({source: parsed.searchParams.get("source"),
    id: parsed.searchParams.get("release"), title: "Album correct", artist: "Band", year: "2021",
    genre: styleMode === "absent" ? "" : "Electronic", genres: styleMode === "absent" ? [] : ["Electronic"],
    styles: styleMode === "absent" ? [] : ["Downtempo", "Indie rock", "Downtempo"],
    mapping: parsed.searchParams.get("release") === "deluxe" || mappingMode === "empty" ? [] :
      mappingMode === "duplicates" ? [0, 0, 2, 3, 4, 5] : mappingMode === "missing" ? undefined : [0, 1, 2, 3, 4, 5],
    tracks: Array.from({length: parsed.searchParams.get("release") === "deluxe" ? 8 : 6}, (_, index) => ({
      title: "Correct " + (mappingMode === "empty" ? 6 - index : index + 1), artist: index === 2 ? "Band feat. Nora" : "Band", track: String(index + 1),
      disc: "1", position: String(index + 1), duration: 180 + index}))});
  if (path === "/api/tags/preview") {
    const body = JSON.parse(options.body); tagWrites.push({path, body, headers: options.headers});
    if (failPreview) { failPreview = false; return response({error: "tags.conflict"}, 409); }
    const changes = body.tracks.flatMap(track => Object.entries(track.changes).map(([field, after]) => ({
      id: track.id, title: original.find(item => item.id === track.id).tags.title, field,
      before: original.find(item => item.id === track.id).tags[field], after})));
    return response({changes, trackCount: body.tracks.length});
  }
  if (path === "/api/tags/save") {
    tagWrites.push({path, body: JSON.parse(options.body), headers: options.headers});
    if (failSave) { failSave = false; return response({error: "tags.conflict"}, 409); }
    if (controlledOperation) return holdMetadata(path);
    operationReads = 0; return response({operationId: "op-1", state: "saving"});
  }
  if (path === "/api/tags/operation") {
    operationReads++;
    if (controlledOperation) return holdMetadata(path);
    if (failOperation) { failOperation = false; return response({operationId: "op-1", state: "failed", error: "tags.write_failed"}); }
    return response({operationId: "op-1", state: "saved", completed: 2, total: 2,
      scan: operationReads === 1 ? "started" : "updated", warnings: []});
  }
  throw new Error("Unexpected metadata request: " + url);
}

(async () => {
  assert.equal((await client("/api/login", {method: "POST", headers: {
    "Content-Type": "application/json", "X-Requested-With": "pmw"}, body: JSON.stringify({username: "bob", password: "pw2"})})).status, 200);
  const dom = await JSDOM.fromURL(base + "/#/album/al1", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(window) {
      window.fetch = (url, options = {}) => String(url).startsWith("/api/tags/") ? Promise.resolve(metadata(String(url), options)) : client(url, options);
      window.EventSource = class { addEventListener() {} close() {} };
      window.IntersectionObserver = class { observe() {} unobserve() {} disconnect() {} };
      window.Element.prototype.scrollIntoView = function () {};
      window.HTMLMediaElement.prototype.play = () => Promise.resolve();
      window.HTMLMediaElement.prototype.pause = function () {};
      window.HTMLMediaElement.prototype.load = function () {};
      window.addEventListener("error", event => errors.push(event.message));
    }
  });
  const w = dom.window, d = w.document, $ = selector => d.querySelector(selector), $$ = selector => [...d.querySelectorAll(selector)];
  const until = async (test, name) => {
    for (let index = 0; index < 200; index++) { if (test()) return; await delay(30); }
    throw new Error("Timed out: " + name + "; " + ($(".tags-dialog")?.textContent || $("#main").textContent).slice(-900));
  };
  const input = (selector, value) => { const node = $(selector); node.value = value; node.dispatchEvent(new w.Event("input", {bubbles: true})); };
  const change = (selector, value) => { const node = $(selector); node.value = value; node.dispatchEvent(new w.Event("change", {bubbles: true})); };
  const chooseEdition = id => $('.tags-edition-result[data-release-id="' + id + '"]').click();
  const apply = key => $('.tags-common-field:has([data-field="' + key + '"]) .tags-apply').click();
  const row = (id, field) => '.tags-table tr[data-track-id="' + id + '"] [data-field="' + field + '"]';
  const replyMetadata = async (path, data, status = 200) => {
    await until(() => pendingMetadata.has(path), "pending " + path);
    const resolve = pendingMetadata.get(path);
    pendingMetadata.delete(path);
    resolve(response(data, status));
  };
  const replyOperation = data => replyMetadata("/api/tags/operation", {operationId: "op-1", total: 6, warnings: [], ...data});
  try {
    await until(() => $(".album-tags-edit"), "tag editing role album action");
    const app = w.eval("App"), roles = app.user.roles;
    assert.equal(app.user.isAdmin, false);
    assert.equal(roles.includes("admin"), false);
    assert.equal(roles.includes("coverArt"), true);
    app.user.roles = [...roles.filter(role => role !== "coverArt"), "admin"];
    app.user.isAdmin = true;
    app.music.navigate();
    await until(() => $(".album-actions"), "admin without tag editing role");
    assert.equal($(".album-tags-edit"), null);
    w.eval("AlbumTagsEditor").open({id: "fdir-al1"}); assert.equal($(".tags-dialog"), null);
    app.user.roles = roles; app.user.isAdmin = false; app.music.navigate();
    await until(() => $(".album-tags-edit"), "restore non-admin editor");
    const header = $(".album-info h1").textContent;
    $(".album-tags-edit").click(); await until(() => $(".tags-common"), "editor data");
    assert.equal($(".tags-progress").hidden, true);
    assert.match($(".tags-draft-help").textContent, /brouillon/i);
    assert.match($(".tags-draft-help").textContent, /Enregistrer dans les fichiers/);
    assert.equal($(".tags-advanced").open, false);
    assert($(".tags-primary-style .tags-common-input[data-field=genre]"));
    assert.match($(".tags-primary-style h3").textContent, /Style de l’album/);
    $(".tags-advanced").open = true;
    assert.equal(requests.find(item => item.path === "/api/tags/album").query.get("id"), "fdir-al1");
    assert.equal($$(".tags-table tbody tr").length, 6);
    assert.match($('.tags-common-field [data-common-state="albumArtist"]').textContent, /Plusieurs/);
    apply("genre"); assert.match($(".tags-status").textContent, /Saisissez/);
    assert.equal($(row("file3", "genre")).value, "");
    input('.tags-common-input[data-field="albumArtist"]', "Band"); apply("albumArtist");
    assert.match($(".tags-change-count").textContent, /2 piste/);
    assert.equal($(row("file3", "artist")).value, "Band feat. Nora");
    assert.equal($(".album-info h1").textContent, header);
    $('.tags-common-field:has([data-field="year"]) .tags-clear').click();
    assert.match($(".tags-change-count").textContent, /6 piste/);
    console.log("OK editing role independent from admin, actual tag values, safe common values, guests and folder header");

    $(".tags-close").click(); assert.equal($(".tags-discard").hidden, false);
    $(".tags-discard button:not(.tags-discard-confirm)").click();
    assert.equal($(".tags-dialog") !== null, true); assert.equal($(".tags-discard").hidden, true);
    d.dispatchEvent(new w.KeyboardEvent("keydown", {key: "Escape", bubbles: true}));
    assert.equal($(".tags-discard").hidden, false);
    $(".tags-discard button:not(.tags-discard-confirm)").click();
    $(".tags-reset").click(); assert.match($(".tags-change-count").textContent, /Aucune/);
    change(".tags-scope", "missing"); input('.tags-common-input[data-field="genre"]', "Alternative"); apply("genre");
    assert.equal($(row("file1", "genre")).value, "Rock");
    assert.equal($(row("file3", "genre")).value, "Alternative");
    assert.equal($(row("file6", "genre")).value, "Alternative");
    $(".tags-reset").click();
    $('.tags-table tr[data-track-id="file2"] input[type=checkbox]').click();
    change(".tags-scope", "selection"); input('.tags-common-input[data-field="artist"]', "Band corrected"); apply("artist");
    assert.equal($(row("file2", "artist")).value, "Band corrected");
    assert.equal($(row("file3", "artist")).value, "Band feat. Nora");
    console.log("OK guarded closing, reset, missing-only and selection-only updates");

    failPreview = true; $(".tags-review").click();
    await until(() => $(".tags-status").classList.contains("page-error"), "preview conflict");
    assert.equal($(row("file2", "artist")).value, "Band corrected");
    $(".tags-reset").click();
    $(".tags-source-toggle").click(); input(".tags-search-artist", "Band"); input(".tags-search-album", "Album");
    assert.equal($(".tags-source").value, "discogs");
    change(".tags-source", "discogs"); $(".tags-search-submit").click();
    await until(() => $(".tags-edition-result"), "external candidates");
    assert.equal(requests.filter(item => item.path === "/api/tags/search").at(-1).query.get("source"), "discogs");
    assert.equal($("select.tags-edition"), null);
    assert.equal($$(".tags-edition-result").length, 3);
    assert($$(".tags-edition-result").every(node => node.getAttribute("aria-pressed") === "false"));
    assert.match($('.tags-edition-result[data-release-id="original"]').textContent, /Album original.*Band.*2021.*FR.*CD.*6 pistes.*Indie rock.*Rock/);
    assert.doesNotMatch($('.tags-edition-result[data-release-id="unknown"]').textContent, /0 pistes/);

    chooseEdition("deluxe"); await until(() => $(".tags-use-style"), "styles from mismatched edition");
    assert.equal($('.tags-edition-result[data-release-id="deluxe"]').getAttribute("aria-pressed"), "true");
    assert.equal($('.tags-edition-result[data-release-id="original"]').getAttribute("aria-pressed"), "false");
    assert.deepEqual($$(".tags-style-options input").map(node => node.value), ["Downtempo", "Indie rock", "Electronic"]);
    assert.match($(".tags-source-styles").textContent, /Downtempo/);
    assert.equal($(".tags-source-advanced").open, false);
    assert.equal($(".tags-import").disabled, true);
    assert.equal($(".tags-use-style").disabled, false);
    $(".tags-use-style").click();
    assert($$(".tags-table [data-field=genre]").every(node => node.value === "Downtempo"));
    assert.equal($('.tags-common-input[data-field="genre"]').value, "Downtempo");
    assert.equal($(row("file1", "title")).value, "One");
    assert.equal($(row("file3", "artist")).value, "Band feat. Nora");
    $(".tags-review").click(); await until(() => $(".tags-preview:not([hidden]) .tags-save"), "style-only preview");
    const stylePatch = tagWrites.filter(item => item.path === "/api/tags/preview").at(-1).body;
    assert.equal(stylePatch.tracks.length, 6);
    assert(stylePatch.tracks.every(track => Object.keys(track.changes).join() === "genre" && track.changes.genre === "Downtempo"));
    assert.equal(tagWrites.filter(item => item.path === "/api/tags/save").length, 0);
    $(".tags-preview .tags-actions button:not(.tags-save)").click(); $(".tags-reset").click();

    styleMode = "absent";
    chooseEdition("original"); await until(() => $(".tags-no-styles"), "edition without style");
    assert.match($(".tags-no-styles").textContent, /Aucun style fourni par Discogs/);
    assert.equal($(".tags-use-style"), null);
    assert.equal($(row("file1", "genre")).value, "Rock");
    assert.equal($('.tags-common-input[data-field="genre"]').disabled, false);
    change(".tags-scope", "all");
    input('.tags-common-input[data-field="genre"]', "Trip-hop"); apply("genre");
    assert($$(".tags-table [data-field=genre]").every(node => node.value === "Trip-hop"));
    $(".tags-reset").click();

    styleMode = "normal";
    chooseEdition("deluxe"); await until(() => $(".tags-use-style"), "album fields without track mapping");
    $(".tags-source-advanced").open = true;
    $$("[data-import-field]:checked").forEach(node => node.click());
    $('[data-import-field="album"]').click(); $('[data-import-field="year"]').click();
    assert.equal($(".tags-import").disabled, false);
    assert.equal($(".tags-mapping-panel").hidden, true);
    $(".tags-import").click();
    assert.equal($('.tags-common-input[data-field="album"]').value, "Album correct");
    assert.equal($('.tags-common-input[data-field="year"]').value, "2021");
    assert.equal($(row("file1", "title")).value, "One");
    $(".tags-reset").click();
    $('[data-import-field="album"]').click(); $('[data-import-field="year"]').click();
    $('[data-import-field="genre"]').click();
    $('.tags-style-options input[value="Indie rock"]').click();
    assert.equal($(".tags-import").disabled, false);
    $(".tags-import").click();
    assert($$(".tags-table [data-field=genre]").every(node => node.value === "Indie rock"));
    $(".tags-reset").click();
    console.log("OK style first, Discogs default, real style choices, genre-only draft without mapping and absent-style manual fallback");

    chooseEdition("original"); await until(() => $(".tags-import"), "server matched edition");
    $(".tags-source-advanced").open = true;
    assert.equal($(".tags-import").disabled, false);
    assert.equal($$(".tags-mapping select").map(select => select.value).join(), "0,1,2,3,4,5");
    mappingMode = "empty";
    chooseEdition("original"); await until(() => $(".tags-import"), "reordered six-track edition");
    assert.equal($(".tags-import").disabled, true);
    assert($$(".tags-mapping select").every(select => select.value === ""));
    $$(".tags-mapping select").forEach((select, index) => {select.value = String(5 - index);select.dispatchEvent(new w.Event("change"));});
    assert.equal($(".tags-import").disabled, false);
    mappingMode = "duplicates";
    chooseEdition("original"); await until(() => $(".tags-import"), "duplicate server mappings");
    assert.equal($(".tags-import").disabled, true);
    assert.equal($$(".tags-mapping select").slice(0, 2).map(select => select.value).join(), ",");
    mappingMode = "missing";
    chooseEdition("original"); await until(() => $(".tags-import"), "legacy response without mapping");
    assert.equal($(".tags-import").disabled, true);
    assert($$(".tags-mapping select").every(select => select.value === ""));
    mappingMode = "normal";
    chooseEdition("deluxe"); await until(() => $(".tags-import"), "mismatched edition");
    assert.equal($(".tags-import").disabled, true);
    assert($$(".tags-mapping select").every(select => select.value === ""));
    $$(".tags-mapping select").forEach((select, index) => {select.value = String(index);select.dispatchEvent(new w.Event("change"));});
    assert.equal($(".tags-import").disabled, false);
    $(".tags-import").click();
    assert.equal($(row("file1", "title")).value, "Correct 1");
    assert.equal($(row("file3", "artist")).value, "Band feat. Nora");
    assert.equal(tagWrites.filter(item => item.path === "/api/tags/save").length, 0);
    console.log("OK provider search, conservative server mappings, reordered/mismatched editions and draft-only import");

    $(".tags-review").click(); await until(() => $(".tags-preview:not([hidden]) .tags-save"), "server-approved diff");
    assert.match($(".tags-preview").textContent, /Correct 1/);
    const preview = tagWrites.filter(item => item.path === "/api/tags/preview").at(-1);
    assert.equal(preview.headers["X-Requested-With"], "pmw");
    assert.equal(preview.body.revision, "revision-1");
    assert.equal(preview.body.tracks.some(track => "artist" in track.changes), false);
    assert.match($(".tags-save-help").textContent, /fichiers audio/);
    assert.match($(".tags-save-help").textContent, /bibliothèque/);
    controlledOperation = true;
    $(".tags-save").click();
    assert.equal($(".tags-progress").hidden, false);
    assert.equal($(".tags-progress-bar").tagName, "PROGRESS");
    assert.equal($(".tags-progress-bar").hasAttribute("value"), false);
    assert.equal($(".tags-edit-fields").disabled, true);
    assert.equal($(".tags-preview").hidden, true);
    assert.doesNotMatch($(".tags-status").textContent, /enregistrées/);
    $(".tags-close").click(); assert($(".tags-dialog"));
    await replyMetadata("/api/tags/save", {operationId: "op-1", state: "saving", phase: "preparing", completed: 0, total: 6});
    await replyOperation({state: "saving", phase: "preparing", completed: 1});
    await until(() => /préparation/i.test($(".tags-progress-label").textContent), "preparation phase");
    assert.match($(".tags-progress-label").textContent, /1\s*\/\s*6/);
    assert.equal($(".tags-progress-bar").value, 1);
    assert.equal($(".tags-progress-bar").max, 6);
    assert($(".tags-progress-help").textContent.trim());
    assert.doesNotMatch($(".tags-status").textContent, /enregistrées/);
    const readsBeforeLongSave = operationReads, schedule = w.setTimeout;
    w.setTimeout = function (callback, timeout, ...args) {
      return schedule.call(this, callback, timeout === 1000 ? 0 : timeout, ...args);
    };
    try {
      for (let index = 0; index < 65; index++) {
        await replyOperation({state: "saving", phase: "preparing", completed: 1});
      }
      await until(() => pendingMetadata.has("/api/tags/operation"), "tracking continues beyond sixty replies");
    } finally { w.setTimeout = schedule; }
    assert(operationReads - readsBeforeLongSave >= 65);
    assert.equal($(".tags-poll-retry"), null);
    assert.equal($(".tags-progress").hidden, false);
    assert.doesNotMatch($(".tags-status").textContent, /enregistrées/);
    await replyOperation({state: "saving", phase: "publishing", completed: 1});
    await until(() => /enregistrement/i.test($(".tags-progress-label").textContent), "publishing phase");
    assert.match($(".tags-progress-label").textContent, /1\s*\/\s*6/);
    assert.equal($(".tags-progress-bar").value, 1);
    assert.equal($(".tags-progress-bar").max, 6);
    await replyMetadata("/api/tags/operation", {error: "errors.network"}, 503);
    await until(() => $(".tags-poll-retry"), "lost operation tracking");
    assert.equal(d.activeElement, $(".tags-poll-retry"));
    assert.equal($(".tags-progress").hidden, true);
    assert.doesNotMatch($(".tags-status").textContent, /enregistrées/);
    assert.equal($(".tags-edit-fields").disabled, true);
    $(".tags-poll-retry").click();
    assert.equal($(".tags-progress").hidden, false);
    assert.equal($(".tags-progress-bar").hasAttribute("value"), false);
    assert.equal(tagWrites.filter(item => item.path === "/api/tags/save").length, 1);
    await replyOperation({state: "saved", phase: "publishing", completed: 6, scan: "started"});
    await until(() => /enregistrées/.test($(".tags-status").textContent), "files saved");
    assert.match($(".tags-status").textContent, /en cours/);
    assert.equal($(".tags-progress").hidden, false);
    assert.equal($(".tags-progress-bar").hasAttribute("value"), false);
    await replyOperation({state: "saved", phase: "publishing", completed: 6, scan: "updated"});
    await until(() => /actualisée/.test($(".tags-status").textContent), "Subsonic indexed");
    assert.equal($(".tags-progress-bar").value, 6);
    assert.equal($(".tags-progress-bar").max, 6);
    assert.equal(tagWrites.filter(item => item.path === "/api/tags/save").length, 1);
    controlledOperation = false;
    $(".tags-close").click(); assert.equal($(".tags-dialog"), null);
    assert.equal(app.user.isAdmin, false);
    assert.equal(app.user.roles.includes("coverArt"), true);
    console.log("OK draft/save guidance, immediate activity, preparation/publication counts, tracking retry without rewriting and separate indexing progress");

    await until(() => $(".album-tags-edit"), "album refreshed after indexing");
    $(".album-tags-edit").click(); await until(() => $(".tags-common"), "reopen");
    $(".tags-advanced").open = true;
    input(row("file1", "title"), ""); $(".tags-review").click();
    await until(() => $(".tags-preview:not([hidden]) .tags-save"), "explicit clear diff");
    assert.match($(".tags-preview").textContent, /Effacé/);
    failSave = true; $(".tags-save").click();
    await until(() => $(".tags-status").classList.contains("page-error"), "save rejected before writing");
    assert.equal($(".tags-progress").hidden, true);
    assert.equal($(".tags-preview").hidden, false);
    assert.equal($(".tags-save").disabled, false);
    assert.equal($(".tags-edit-fields").disabled, false);
    assert.equal($(row("file1", "title")).value, "");
    assert.equal(d.activeElement, $(".tags-status"));
    failOperation = true; $(".tags-save").focus(); $(".tags-save").click();
    await until(() => $(".tags-status").classList.contains("page-error"), "write failure");
    assert.equal(d.activeElement, $(".tags-status"));
    assert.equal($(".tags-progress").hidden, true);
    assert.equal($(row("file1", "title")).value, "");
    $(".tags-close").click(); assert.equal($(".tags-discard").hidden, false);
    $(".tags-discard-confirm").click(); assert.equal($(".tags-dialog"), null);

    $(".album-tags-edit").click(); await until(() => $(".tags-common"), "scan warning editor");
    $(".tags-advanced").open = true;
    input(row("file1", "title"), "Saved despite scan failure"); $(".tags-review").click();
    await until(() => $(".tags-preview:not([hidden]) .tags-save"), "scan warning preview");
    controlledOperation = true; $(".tags-save").click();
    await replyMetadata("/api/tags/save", {operationId: "op-1", state: "saving", total: 1});
    await replyOperation({state: "saved", completed: 1, total: 1, scan: "failed", warnings: ["tags.scan_unconfirmed"]});
    await until(() => /restent enregistrés/.test($(".tags-status").textContent), "scan failure preserves saved files");
    assert.equal($(".tags-progress").hidden, false);
    assert.equal($(".tags-progress-bar").hidden, true);
    assert.equal($(".tags-progress-bar").hasAttribute("value"), false);
    assert.match($(".tags-change-count").textContent, /Aucune/);
    $(".tags-close").click(); assert.equal($(".tags-dialog"), null);
    controlledOperation = false;
    console.log("OK rejected save restores preview, write failure retains draft, scan warning keeps saved result without a success bar");

    original[5].editable = false;
    original[1].editable = false;
    $(".album-tags-edit").click(); await until(() => $(".tags-common"), "read-only track");
    assert.equal($(row("file6", "title")).disabled, true);
    $(".tags-source-toggle").click(); $(".tags-search-submit").click();
    await until(() => $(".tags-edition-result"), "read-only mapping candidates");
    chooseEdition("original"); await until(() => $(".tags-import"), "read-only mapping");
    assert.equal($$(".tags-mapping select").map(select => select.value).join(), "0,2,3,4");
    input(row("file1", "title"), "Unsaved");
    app.onSessionLost();
    assert.equal($(".tags-dialog"), null);
    assert.equal($("#login").hidden, false);
    assert.deepEqual(errors, []);
    console.log("OK explicit clear, retained draft after failure, unsupported tracks and session cleanup");
  } finally { dom.window.close(); agent.destroy(); }
})().catch(error => { console.error(error); agent.destroy(); process.exitCode = 1; });
