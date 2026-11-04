"use strict";
// Artistes similaires sur plusieurs niveaux

/* ---------- Artistes similaires sur 2 niveaux ---------- */
async function runPool(items, n, fn) {
  let i = 0;
  await Promise.all(Array.from({length: Math.min(n, items.length)}, async () => { while (i < items.length) await fn(items[i++]); }));
}
// Artistes proches sur plusieurs niveaux : niveau 1 = proches de l'artiste, niveau 2 = proches de ceux-là, etc.
// On descend d'un niveau tant qu'on n'a pas assez d'artistes (target), jusqu'à maxDepth.
async function similarArtists(id, maxDepth, target) {
  const get = async (aid, count) => [].concat(((await api("getArtistInfo2", {id: aid, count})).artistInfo2 || {}).similarArtist || []);
  const seen = new Set([id]), all = [];
  let prev = [{id}];
  for (let lvl = 1; lvl <= (maxDepth || 1); lvl++) {
    const cur = [];
    const sources = lvl === 1 ? prev : shuffled(prev).slice(0, 8);
    await runPool(sources, 4, async src => {
      try {
        (await get(src.id, lvl === 1 ? 12 : 10)).forEach(x => {
          if (x.id && !seen.has(x.id)) { seen.add(x.id); const a = {id: x.id, name: x.name, level: lvl}; cur.push(a); all.push(a); }
        });
      } catch (e) {}
    });
    if (!cur.length || all.length >= (target || 30)) break;
    prev = cur;
  }
  return all;
}
// Titres populaires de ces artistes, rangés par niveau
async function similarWide(id, depth, perArtist, target) {
  const out = {1: [], 2: [], 3: [], 4: []};
  let arts = [];
  try { arts = await similarArtists(id, depth, target); } catch (e) {}
  await runPool(arts, 4, async a => {
    try { out[a.level].push(...([].concat(((await api("getTopSongs", {artist: a.name, count: perArtist || 5})).topSongs || {}).song || []))); } catch (e) {}
  });
  return out;
}
// Mélange sans deux titres du même artiste à la suite
function spreadArtists(list) {
  const res = []; let rest = shuffled(list);
  while (rest.length) {
    const k = rest.findIndex(s => !res.length || s.artist !== res[res.length - 1].artist);
    res.push(...rest.splice(k < 0 ? 0 : k, 1));
  }
  return res;
}
