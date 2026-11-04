"use strict";
// Créateur de mix par style

/* ---------- Créateur de mix par style ---------- */
const normG = g => (g || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "").replace(/[^a-z0-9]/g, "");
let genreCache = null;
async function genreGroups() {      // regroupe « Hip-Hop », « Hip hop », « hiphop »… en un seul style
  if (genreCache) return genreCache;
  const gs = ((await api("getGenres")).genres || {}).genre || [];
  const m = {};
  gs.forEach(g => {
    const k = normG(g.value); if (!k) return;
    const e = m[k] || (m[k] = {key: k, names: [], count: 0, best: 0, label: g.value});
    e.names.push(g.value); e.count += g.songCount || 0;
    if ((g.songCount || 0) > e.best) { e.best = g.songCount || 0; e.label = g.value; }
  });
  genreCache = Object.values(m).sort((a, b) => b.count - a.count);
  return genreCache;
}
const DECADES = [1960, 1970, 1980, 1990, 2000, 2010, 2020];
async function buildMix(o) {
  const variants = [].concat(...o.genres.map(g => g.names.slice(0, 4)));
  const ranges = o.decades.map(y => [y, y + 9]);
  const gl = variants.length ? variants : [null], dl = ranges.length ? ranges : [null];
  const jobs = [];
  gl.forEach(g => dl.forEach(r => jobs.push({g, r})));
  const per = Math.min(150, Math.max(30, Math.ceil(300 / jobs.length)));
  const pool = [];
  for (let i = 0; i < jobs.length; i += 3) {       // 3 requêtes à la fois : on ménage le serveur
    await Promise.all(jobs.slice(i, i + 3).map(async ({g, r}) => {
      const p = {size: per};
      if (g) p.genre = g;
      if (r) { p.fromYear = r[0]; p.toYear = r[1]; }
      try { pool.push(...((await api("getRandomSongs", p)).randomSongs || {}).song || []); } catch (e) {}
    }));
  }
  const inRanges = s => !ranges.length || (s.year && ranges.some(r => s.year >= r[0] && s.year <= r[1]));
  const inGenres = s => !o.genres.length || o.genres.some(g => g.names.some(n => normG(n) === normG(s.genre)));
  let seed = [], near = [], far = [];
  if (o.seed) {
    try { seed = (((await api("getSimilarSongs2", {id: o.seed.id, count: 80})).similarSongs2 || {}).song || []).filter(inRanges); } catch (e) {}
    try { seed = seed.concat((((await api("getTopSongs", {artist: o.seed.name, count: 15})).topSongs || {}).song || []).filter(inRanges)); } catch (e) {}
    const w = await similarWide(o.seed.id, o.wide ? 4 : 1, 5, 30);     // jusqu'à 4 niveaux si les premiers sont maigres
    near = w[1].filter(inRanges); far = w[2].concat(w[3], w[4]).filter(inRanges);
  }
  let favs = [];
  if (o.favs) {
    try { favs = (((await api("getStarred2")).starred2 || {}).song || []).filter(s => inRanges(s) && inGenres(s)); } catch (e) {}
  }
  const seen = new Set(), out = [], perArtist = {};
  let cap = 2;
  const take = (list, max) => {
    let n = 0;
    for (const s of shuffled(list)) {
      if (n >= max || out.length >= o.size) break;
      if (seen.has(s.id) || (perArtist[s.artist] || 0) >= cap) continue;
      seen.add(s.id); perArtist[s.artist] = (perArtist[s.artist] || 0) + 1; out.push(s); n++;
    }
  };
  take(seed, Math.ceil(o.size * 0.2));
  take(near, Math.ceil(o.size * (far.length ? 0.2 : 0.3)));
  take(far, Math.ceil(o.size * 0.2));
  take(favs, Math.ceil(o.size * 0.3));
  take(pool, o.size);
  if (out.length < o.size * 0.8) { cap = 5; take(pool, o.size); }   // peu de choix : on assouplit la limite par artiste
  if (!out.length) return out;
  if (o.order === "year") return out.sort((a, b) => (a.year || 0) - (b.year || 0));
  return spreadArtists(out);
}
async function mixBuilder(c) {
  const o = {genres: [], decades: [], seed: null, size: 60, favs: false, order: "mix", wide: true};
  const groups = await genreGroups();
  const chipRow = (title, wrap = true) => {
    header(c, title); const d = document.createElement("div"); d.className = "chips" + (wrap ? " wrap" : ""); c.appendChild(d); return d;
  };
  const toggle = (d, label, on, fn, cls) => {
    const b = document.createElement("button"); b.textContent = label; if (cls) b.className = cls;
    b.classList.toggle("on", !!on);
    b.onclick = () => { const v = fn(); b.classList.toggle("on", v); };
    d.appendChild(b); return b;
  };
  // Partir d'un artiste
  const sd = chipRow("Partir d’un artiste (facultatif)");
  const seedBtn = document.createElement("button"); seedBtn.textContent = "Choisir un artiste…"; sd.appendChild(seedBtn);
  // Styles
  const gh = chipRow("Styles");
  const gbtn = {};
  groups.slice(0, 40).forEach(g => {
    gbtn[g.key] = toggle(gh, g.label, false, () => {
      const i = o.genres.indexOf(g); if (i >= 0) o.genres.splice(i, 1); else o.genres.push(g);
      return i < 0;
    });
  });
  // Époques
  const dh = chipRow("Époques");
  DECADES.forEach(y => toggle(dh, "Années " + String(y).slice(2), false, () => {
    const i = o.decades.indexOf(y); if (i >= 0) o.decades.splice(i, 1); else o.decades.push(y);
    return i < 0;
  }));
  // Réglages
  const oh = chipRow("Réglages");
  const sizes = [30, 60, 100].map(n => toggle(oh, n + " titres", n === o.size, () => { o.size = n; sizes.forEach((b, i) => b.classList.toggle("on", [30, 60, 100][i] === n)); return true; }));
  toggle(oh, "Mes favoris d’abord", false, () => (o.favs = !o.favs));
  toggle(oh, "Artistes proches de proches (jusqu\u2019à 4 niveaux)", true, () => (o.wide = !o.wide));
  const ord = toggle(oh, "Chronologique", false, () => { o.order = o.order === "year" ? "mix" : "year"; return o.order === "year"; });
  // choix de l'artiste : recherche + styles suggérés par MusicBrainz
  seedBtn.onclick = safe(async () => {
    if (o.seed) { o.seed = null; seedBtn.textContent = "Choisir un artiste…"; seedBtn.classList.remove("on"); return; }
    const q = await askText("Nom de l’artiste", "");
    if (!q) return;
    const r = (await api("search3", {query: q, artistCount: 3, albumCount: 0, songCount: 0})).searchResult3 || {};
    const a = (r.artist || [])[0];
    if (!a) { toast("Artiste introuvable"); return; }
    o.seed = a; seedBtn.textContent = "Comme : " + a.name + "  ✕"; seedBtn.classList.add("on");
    try {
      const j = await (await fetch("/info/genres?artist=" + encodeURIComponent(a.name))).json();
      let n = 0;
      (j.genres || []).forEach(name => {
        const k = normG(name);
        const g = groups.find(x => x.key === k) || groups.find(x => x.key.length > 3 && (x.key.includes(k) || k.includes(x.key)));
        if (g && gbtn[g.key] && !gbtn[g.key].classList.contains("sug")) {
          gbtn[g.key].classList.add("sug");
          if (n++ < 3 && o.genres.indexOf(g) < 0) { o.genres.push(g); gbtn[g.key].classList.add("on"); }
        }
      });
      if (n) toast("Styles suggérés : " + n);
    } catch (e) {}
  });
  // Actions
  const run = async save => {
    toast("Création du mix…");
    const songs = await buildMix(o);
    if (!songs.length) { toast("Aucun titre ne correspond"); return; }
    if (!save) { playQueue(songs, 0); toast(songs.length + " titres"); return; }
    const label = o.genres.map(g => g.label).slice(0, 2).join(" + ") || (o.seed ? o.seed.name : "Mix");
    const name = await askText("Nom de la playlist", "Mix " + label + (o.decades.length ? " " + o.decades.map(y => String(y).slice(2) + "s").join("/") : ""));
    if (!name) return;
    await api("createPlaylist", {name, songId: songs.map(x => x.id)});
    toast("Playlist « " + name + " » créée (" + songs.length + " titres)");
  };
  const a = document.createElement("div"); a.className = "actions";
  const b1 = document.createElement("button"); b1.className = "primary"; b1.innerHTML = ic("play", 20) + " Lancer le mix"; b1.onclick = safe(() => run(false));
  const b2 = document.createElement("button"); b2.innerHTML = ic("plus", 20) + " Enregistrer en playlist"; b2.onclick = safe(() => run(true));
  a.appendChild(b1); a.appendChild(b2); c.appendChild(a);
}
