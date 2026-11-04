"use strict";
// Mix et radios

/* ---------- Mix et radios ---------- */
async function mixRandom(params) {
  const j = await api("getRandomSongs", Object.assign({size: 60}, params || {}));
  const s = (j.randomSongs && j.randomSongs.song) || [];
  if (!s.length) { toast("Aucun titre trouvé"); return; }
  playQueue(s, 0, {endless: params || true});
}
async function mixFav() {
  const s = shuffled((((await api("getStarred2")).starred2.song) || []).concat(await loadExtFavorites()));
  if (!s.length) { toast("Aucun titre favori"); return; }
  playQueue(s, 0);
}
async function mixAlbums(type, n) {
  const al = ((await api("getAlbumList2", {type, size: n})).albumList2.album) || [];
  const songs = [];
  for (const a of al) songs.push(...(((await api("getAlbum", {id: a.id})).album.song) || []));
  if (!songs.length) { toast("Aucun titre trouvé"); return; }
  playQueue(songs, 0);
}
async function similarOf(s) {
  let sim = [];
  try { sim = ((await api("getSimilarSongs2", {id: s.id, count: 40})).similarSongs2.song) || []; } catch (e) {}
  if (!sim.length && s.genre) { try { sim = ((await api("getRandomSongs", {size: 40, genre: s.genre})).randomSongs.song) || []; } catch (e) {} }
  if (!sim.length) sim = ((await api("getRandomSongs", {size: 40})).randomSongs.song) || [];
  return sim;
}
async function radioFromSong(s) {
  try {
    const sim = await similarOf(s);
    if (cur() && cur().id === s.id) { queue = [s].concat(sim); qi = 0; shuffleOn = false; origQueue = null; endless = true; refreshUI(); }
    else playQueue([s].concat(sim), 0, {endless: true});
    toast("Radio lancée");
  } catch (e) { toast(e.message); }
}
async function radioFromArtist(id, name) {
  try {
    let sim = [];
    try { sim = ((await api("getSimilarSongs2", {id, count: 60})).similarSongs2.song) || []; } catch (e) {}
    if (sim.length < 10) { try { sim = sim.concat(((await api("getTopSongs", {artist: name, count: 30})).topSongs.song) || []); } catch (e) {} }
    toast("Radio de " + name + " : recherche des artistes proches…");
    const w = await similarWide(id, 4, 5, 40);    // niveaux 1 à 4, selon ce qu'on trouve
    const seen = new Set(), all = [];
    sim.concat(w[1], w[2], w[3], w[4]).forEach(s => { if (!seen.has(s.id)) { seen.add(s.id); all.push(s); } });
    if (!all.length) { toast("Pas de données Last.fm : activez-le dans les réglages du serveur"); return; }
    const mixed = spreadArtists(all);
    playQueue(mixed.slice(0, 100), 0);
    toast("Radio de " + name);
  } catch (e) { toast(e.message); }
}
const safe = f => async () => { try { await f(); } catch (e) { toast(e.message); } };
