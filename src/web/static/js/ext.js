"use strict";
// Musique d'ailleurs (écran du Pi seulement) : Jamendo, YouTube, playlists locales, réglages

let EXT = {jamendo: {enabled: false}, youtube: {enabled: false}};

async function extGet(path, params) {
  const r = await fetch("/ext/" + path + "?" + new URLSearchParams(params || {}));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  return j;
}
async function extPost(path, body) {
  const r = await fetch("/ext/" + path, {method: "POST", body: JSON.stringify(body || {}), headers: {"Content-Type": "application/json"}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  if (j.status) EXT = j.status;
  return j;
}
async function loadExtStatus() {
  try { EXT = await extGet("status"); } catch (e) { /* sources externes indisponibles : l'application reste complète */ }
  loadExtFavorites();
}

/* ---------- Favoris des titres d'ailleurs (le cœur de Subsonic ne les connaît pas) ---------- */
let EXT_FAVS = new Set();
const hasLocalHeart = s => !!(s && !isRadio(s) && (s.streamUrl || s.youtubeId));
async function loadExtFavorites() {
  try {
    const songs = (await extGet("favorites")).songs;
    EXT_FAVS = new Set(songs.map(x => x.id));
    return songs;
  } catch (e) { return []; }
}
/* Un seul point d'entrée pour tous les cœurs : titre Subsonic ou titre d'ailleurs */
const isStarred = s => hasLocalHeart(s) ? EXT_FAVS.has(s.id) : !!(s && s.starred);
async function toggleStar(s) {
  if (hasLocalHeart(s)) {
    const r = await extPost("favorite", {song: s});
    if (r.starred) EXT_FAVS.add(s.id); else EXT_FAVS.delete(s.id);
    return;
  }
  await api(s.starred ? "unstar" : "star", {id: s.id});
  s.starred = s.starred ? undefined : new Date().toISOString();
}

/* ---------- Lecteur YouTube : où l'afficher ---------- */
function placeVideo() {
  const box = $("#ytbox"), on = document.body.classList.contains("yt");
  box.hidden = !on;
  const cover = $("#fcover");
  if (!on) { cover.style.visibility = ""; return; }
  const showsCover = !$("#full").hidden && !$("#fbody").hidden && $("#fqueue").hidden && $("#flyr").hidden && $("#finf").hidden;
  box.classList.toggle("big", showsCover);
  const r = cover.getBoundingClientRect();
  for (const [prop, value] of [["left", r.left], ["top", r.top], ["width", r.width], ["height", r.height]]) {
    box.style[prop] = showsCover ? value + "px" : "";
  }
  cover.style.visibility = showsCover ? "hidden" : "";
}
setInterval(() => { if (document.body.classList.contains("yt")) placeVideo(); }, 700);

/* ---------- Recherche : section « Ailleurs » ---------- */
function extSearchSection(container, text) {
  if (text.length < 2) return;
  if (EXT.jamendo.enabled) jamendoResults(container, text);
  if (EXT.youtube.enabled) youtubeButton(container, text);
}
async function jamendoResults(container, text) {
  const holder = document.createElement("div"); container.appendChild(holder);
  try {
    const items = (await extGet("search", {src: "jamendo", q: text})).items;
    if (!items.length || !holder.isConnected) return;
    header(holder, "Ailleurs · Jamendo (musique libre)");
    songRows(holder, items, {search: true});
  } catch (e) { holder.innerHTML = '<div class="msg">Jamendo : ' + esc(e.message) + "</div>"; }
}
function youtubeButton(container, text) {
  const holder = document.createElement("div"); container.appendChild(holder);
  const box = document.createElement("div"); box.className = "actions";
  const b = document.createElement("button"); b.innerHTML = ic("radio", 20) + " Chercher aussi sur YouTube";
  b.onclick = async () => {
    b.disabled = true; b.textContent = "Recherche…";
    try {
      const items = (await extGet("search", {src: "youtube", q: text})).items;
      holder.innerHTML = "";
      header(holder, "Ailleurs · YouTube (vidéo visible, publicités possibles)");
      if (items.length) songRows(holder, items, {search: true}); else holder.insertAdjacentHTML("beforeend", '<div class="msg">Aucun résultat.</div>');
    } catch (e) { b.disabled = false; b.innerHTML = ic("radio", 20) + " Chercher aussi sur YouTube"; toast(e.message); }
  };
  box.appendChild(b); holder.appendChild(box);
}

/* ---------- Playlists locales ---------- */
function localPlaylistItems(songs) {
  const items = [{icon: "plus", label: "Nouvelle playlist locale…", fn: async () => {
    const name = await askText("Nom de la playlist locale", "");
    if (!name) return;
    try { await extPost("create", {name, songs}); toast("Playlist locale « " + name + " » créée"); } catch (e) { toast(e.message); }
  }}];
  return items;
}
async function localPlaylistChoices(songs) {
  const items = localPlaylistItems(songs);
  try {
    (await extGet("playlists")).lists.forEach(p => items.push({icon: "list", label: "Locale : " + p.name + " (" + p.count + ")", fn: async () => {
      try { const r = await extPost("add", {id: p.id, songs}); toast(r.added ? "Ajouté à « " + p.name + " »" : "Déjà dans « " + p.name + " »"); } catch (e) { toast(e.message); }
    }}));
  } catch (e) { /* on propose au moins la création */ }
  return items;
}
async function localPlaylistsSection(container) {
  header(container, "Playlists locales (ce Pi)");
  actions(container, [], [["plus", "Nouvelle playlist locale", async () => {
    const name = await askText("Nom de la playlist locale", "");
    if (!name) return;
    try { await extPost("create", {name}); toast("Playlist locale créée"); tab("playlists"); } catch (e) { toast(e.message); }
  }]]);
  try {
    (await extGet("playlists")).lists.forEach(p => container.appendChild(row("", p.name, p.count + " titre(s) · mélange possible avec la musique d’ailleurs",
      () => openView(p.name, c => localPlaylistView(p.id, c)))));
  } catch (e) { container.insertAdjacentHTML("beforeend", '<div class="msg">' + esc(e.message) + "</div>"); }
}
async function localPlaylistView(id, c) {
  const p = await extGet("playlist", {id});
  actions(c, p.songs, [["trash", "Supprimer", () => openSheet("Supprimer « " + p.name + " » ?", [
    {icon: "trash", label: "Oui, supprimer la playlist", fn: async () => {
      try { await extPost("delete", {id}); toast("Playlist supprimée"); stack.pop(); render(); } catch (e) { toast(e.message); } }}])]]);
  if (!p.songs.length) { c.insertAdjacentHTML("beforeend", '<div class="msg">Playlist vide. Ajoutez des titres avec le bouton « ⋯ » d’un morceau.</div>'); return; }
  songRows(c, p.songs, {localPlaylistId: id});
}

/* ---------- Réglages des sources ---------- */
const EXT_SOURCES = [
  {key: "jamendo", title: "Jamendo", field: "jamendo_id", label: "Client ID Jamendo",
   text: "Musique libre en streaming, sans publicité, qui se mélange à vos playlists. Catalogue indépendant, pas les grands titres. Clé gratuite : devportal.jamendo.com."},
  {key: "youtube", title: "YouTube", field: "youtube_key", label: "Clé API YouTube",
   text: "Presque tout le catalogue, avec le lecteur officiel de YouTube : la vidéo reste visible (petite fenêtre) et les publicités sont possibles. Clé gratuite (API YouTube Data v3, environ 100 recherches par jour) : console.cloud.google.com."}];

function externalSettingsView(c) {
  c.insertAdjacentHTML("beforeend", '<div class="msg" style="color:var(--soft)">Chaque source est désactivée tant que vous ne l’activez pas. Rien n’est envoyé à ces services sans activation.</div>');
  header(c, "Versions originales seulement — " + (EXT.studio !== false ? "oui" : "non"));
  c.insertAdjacentHTML("beforeend", '<div class="msg" style="color:var(--soft);padding-top:4px">Écarte les versions live, reprises, remix et karaoké quand le titre l’indique.</div>');
  actions(c, [], [[EXT.studio !== false ? "pause" : "play", EXT.studio !== false ? "Montrer toutes les versions" : "Versions originales seulement", async () => {
    try { await extPost("settings", {studio: EXT.studio === false}); render(); } catch (e) { toast(e.message); }
  }]]);
  EXT_SOURCES.forEach(src => {
    const st = EXT[src.key] || {};
    header(c, src.title + " — " + (st.enabled ? "activé" : st.configured ? "désactivé" : "clé manquante"));
    c.insertAdjacentHTML("beforeend", '<div class="msg" style="color:var(--soft);padding-top:4px">' + esc(src.text) + "</div>");
    actions(c, [], [
      ["plus", st.configured ? "Changer la clé" : "Saisir la clé", async () => {
        const v = await askText(src.label, "");
        if (!v) return;
        try { await extPost("settings", {[src.field]: v}); toast("Clé enregistrée"); render(); } catch (e) { toast(e.message); }
      }],
      [st.enabled ? "pause" : "play", st.enabled ? "Désactiver" : "Activer", async () => {
        try { await extPost("settings", {[src.key + "_on"]: !st.enabled}); render(); } catch (e) { toast(e.message); }
      }]]);
  });
}

loadExtStatus();
