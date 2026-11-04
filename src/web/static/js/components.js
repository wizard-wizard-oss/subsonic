"use strict";
// Éléments d'interface : lignes, cartes, vues album/artiste/playlist

/* ---------- Éléments d'interface ---------- */
function row(img, title, sub, onclick, round) {
  const d = document.createElement("div");
  d.className = "row" + (round ? " round" : "");
  d.innerHTML = (img ? '<img src="' + img + '" loading="lazy" alt="">' : '<span class="ph"></span>') +
    '<div class="t"><b>' + esc(title) + "</b><small>" + esc(sub) + "</small></div>";
  d.onclick = onclick;
  return d;
}
function header(c, text) {
  const h = document.createElement("div"); h.className = "h"; h.textContent = text; c.appendChild(h); return h;
}
function iconBtn(icon, onclick, extraClass) {
  const b = document.createElement("button"); b.className = "sb" + (extraClass ? " " + extraClass : "");
  b.innerHTML = ic(icon, 22); b.onclick = e => { e.stopPropagation(); onclick(b); };
  return b;
}
function heartBtn(s) {
  const b = document.createElement("button");
  const paint = () => { const on = isStarred(s); b.className = "sb" + (on ? " on" : ""); b.innerHTML = ic(on ? "heartfill" : "heart", 22); };
  paint();
  b.onclick = async e => {
    e.stopPropagation();
    try {
      await toggleStar(s);
      paint(); refreshUI();
    } catch (err) { toast(err.message); }
  };
  return b;
}
function playNow(s) {      // joue ce titre tout de suite, sans perdre la file en cours
  if (!queue.length) { playQueue([s], 0); return; }
  queue.splice(qi + 1, 0, s);
  playIdx(qi + 1);
}
function songRows(c, songs, ctx) {
  const search = ctx && ctx.search;
  songs.forEach((s, i) => {
    const d = row(coverOf(s, 64), (s.track ? s.track + ". " : "") + s.title,
      (s.artist || "") + (s.duration ? " · " + fmt(s.duration) : ""), search ? () => playNow(s) : () => playQueue(songs, i));
    if (cur() && cur().id === s.id) d.classList.add("cur");
    if (search) d.appendChild(iconBtn("play", () => playNow(s)));
    d.appendChild(iconBtn("plus", () => enqueue([s], false)));
    if (!isExternal(s) || hasLocalHeart(s)) d.appendChild(heartBtn(s));
    d.appendChild(iconBtn("more", () => songMenu(s, ctx ? {playlistId: ctx.playlistId, localPlaylistId: ctx.localPlaylistId, index: i} : null)));
    c.appendChild(d);
  });
}
function actions(c, songs, extra) {
  const a = document.createElement("div"); a.className = "actions";
  if (songs.length) {
    const b1 = document.createElement("button"); b1.className = "primary"; b1.innerHTML = ic("play", 20) + " Lire";
    b1.onclick = () => { b1.className = "primary"; b2.className = ""; playQueue(songs, 0); };
    const b2 = document.createElement("button"); b2.innerHTML = ic("shuffle", 20) + " Aléatoire";
    b2.onclick = () => { b2.className = "primary"; b1.className = ""; playShuffled(songs); toast("Lecture aléatoire"); };
    a.appendChild(b1); a.appendChild(b2);
  }
  (extra || []).forEach(([icon, label, fn]) => {
    const b = document.createElement("button"); b.innerHTML = ic(icon, 20) + " " + label; b.onclick = fn; a.appendChild(b);
  });
  if (a.children.length) c.appendChild(a);
}
function card(al) {
  const d = document.createElement("div"); d.className = "card";
  d.innerHTML = (al.coverArt ? '<img src="' + cover(al.coverArt, 200) + '" loading="lazy" alt="">' : '<span class="ph"></span>') +
    "<b>" + esc(al.name || al.title) + "</b><small>" + esc((al.artist || "") + (al.year ? " · " + al.year : "")) + "</small>";
  d.onclick = () => openView(al.name || al.title, c => albumView(al.id, c));
  return d;
}
function artistCard(ar) {
  const d = document.createElement("div"); d.className = "card round";
  const src = ar.artistImageUrl || cover(ar.coverArt, 200);
  d.innerHTML = (src ? '<img src="' + esc(src) + '" loading="lazy" alt="">' : '<span class="ph"></span>') +
    "<b>" + esc(ar.name) + "</b>";
  d.onclick = () => openView(ar.name, c => artistView(ar.id, c));
  return d;
}
const albumRow = al => row(cover(al.coverArt), al.name || al.title,
  (al.artist || "") + (al.year ? " · " + al.year : ""),
  () => openView(al.name || al.title, c => albumView(al.id, c)));
const artistRow = ar => row(cover(ar.coverArt), ar.name,
  (ar.albumCount != null ? ar.albumCount + " album(s)" : ""),
  () => openView(ar.name, c => artistView(ar.id, c)), true);

function heroToggle(hero) { hero.querySelector("img").onclick = () => hero.classList.toggle("big"); }

async function albumView(id, c) {
  const al = (await api("getAlbum", {id})).album;
  const songs = al.song || [];
  const dur = songs.reduce((t, s) => t + (s.duration || 0), 0);
  const hero = document.createElement("div"); hero.className = "ahero";
  hero.innerHTML = '<img src="' + cover(al.coverArt, 500) + '" alt=""><div class="hinfo"><b>' + esc(al.name) +
    '</b><span class="lnk">' + esc(al.artist || "") + "</span><small>" + esc((al.year ? al.year + " · " : "") +
    songs.length + " titre(s) · " + fmt(dur)) + "</small></div>";
  heroToggle(hero);
  if (al.artistId) hero.querySelector(".lnk").onclick = () => openView(al.artist, cc => artistView(al.artistId, cc));
  c.appendChild(hero);
  actions(c, songs, [["plus", "Playlist", () => addToPlaylist(songs)]]);
  // appui long (1,5 s) sur la pochette : recharge cet album (titres + pochette) depuis le serveur
  const him = hero.querySelector("img");
  if (him) {
    let t = null;
    const stop = () => { if (t) { clearTimeout(t); t = null; } };
    him.addEventListener("pointerdown", () => { t = setTimeout(async () => {
      t = null; him.dataset.long = "1";
      bust[al.coverArt] = Date.now(); saveBust();
      try { await fetch("/cache/refresh?album=" + encodeURIComponent(id) + "&artist=" + encodeURIComponent(al.artistId || "")); toast("Album rafraîchi"); render(); } catch (e) { toast(e.message); }
    }, 1500); });
    ["pointerup", "pointerleave", "pointercancel"].forEach(ev => him.addEventListener(ev, stop));
    him.addEventListener("click", e => { if (him.dataset.long) { delete him.dataset.long; e.stopImmediatePropagation(); } }, true);
  }
  songRows(c, songs);
}
async function artistView(id, c) {
  const [d, inf] = await Promise.all([api("getArtist", {id}), api("getArtistInfo2", {id, count: 12}).catch(() => null)]);
  const ar = d.artist, info = (inf && inf.artistInfo2) || {};
  const albums = ar.album || [];
  const fallback = cover(ar.coverArt || (albums[0] && albums[0].coverArt), 400);
  const hero = document.createElement("div"); hero.className = "hero";
  hero.innerHTML = '<img alt=""><div class="hinfo"><b>' + esc(ar.name) + "</b><small>" + albums.length + " album(s)</small></div>";
  const img = hero.querySelector("img");
  img.onerror = () => { if (fallback && img.src.indexOf(fallback) < 0) img.src = fallback; };
  img.src = info.largeImageUrl || info.mediumImageUrl || fallback;
  heroToggle(hero);
  c.appendChild(hero);
  actions(c, [], [["radio", "Radio de l'artiste", () => radioFromArtist(ar.id, ar.name)]]);
  const bio = stripHtml(info.biography);
  if (bio) {
    const b = document.createElement("div"); b.className = "bio"; b.textContent = bio;
    const hint = document.createElement("div"); hint.className = "biohint"; hint.textContent = "Toucher pour lire la suite";
    b.onclick = () => { b.classList.toggle("open"); hint.textContent = b.classList.contains("open") ? "Toucher pour réduire" : "Toucher pour lire la suite"; };
    c.appendChild(b); c.appendChild(hint);
  }
  const topHolder = document.createElement("div"); c.appendChild(topHolder);
  api("getTopSongs", {artist: ar.name, count: 5}).then(j => {
    const songs = (j.topSongs && j.topSongs.song) || [];
    if (songs.length) { header(topHolder, "Titres populaires"); songRows(topHolder, songs); }
  }).catch(() => {});
  header(c, "Albums");
  const g = document.createElement("div"); g.className = "grid"; albums.forEach(al => g.appendChild(card(al))); c.appendChild(g);
  const sim = info.similarArtist || [];
  if (sim.length) {
    header(c, "Artistes similaires");
    const sh = document.createElement("div"); sh.className = "shelf"; sim.forEach(a => sh.appendChild(artistCard(a))); c.appendChild(sh);
  }
}
async function playlistView(id, c) {
  const p = (await api("getPlaylist", {id})).playlist;
  const songs = p.entry || [];
  actions(c, songs, [["trash", "Supprimer", () => openSheet("Supprimer « " + p.name + " » ?", [
    {icon: "trash", label: "Oui, supprimer la playlist", fn: async () => {
      try { await api("deletePlaylist", {id}); toast("Playlist supprimée"); stack.pop(); render(); } catch (e) { toast(e.message); } }}])]]);
  if (!songs.length) { c.insertAdjacentHTML("beforeend", '<div class="msg">Playlist vide. Ajoutez des titres avec le bouton « ⋯ » d’un morceau.</div>'); return; }
  songRows(c, songs, {playlistId: id});
}
