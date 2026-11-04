"use strict";
// Lecteur audio : file, lecture, aléatoire, répétition

/* ---------- Lecteur ---------- */
const audio = new PlayerEngine();      // élément audio, ou lecteur YouTube (voir engine.js)
let queue = [], qi = -1, scrobbled = false;
let endless = null, shuffleOn = false, origQueue = null, repeat = 0;   // repeat : 0 non, 1 tout, 2 titre
const cur = () => queue[qi];
const isRadio = s => !!(s && String(s.id || "").startsWith("radio-"));        // radio Internet du serveur Subsonic
const isExternal = s => !!(s && (s.streamUrl || s.youtubeId));      // radio, Jamendo, YouTube : pas de scrobble ni de favori Subsonic

function playQueue(list, i, opts) {
  queue = list.slice(); endless = (opts && opts.endless) || null;
  shuffleOn = false; origQueue = null;
  playIdx(i);
}
function playShuffled(list) {
  queue = shuffled(list); origQueue = list.slice(); endless = null; shuffleOn = true;
  playIdx(0);
}
// Charge un titre dans un lecteur remis à zéro (un lecteur resté « à la fin » après un déplacement
// vers la fin du morceau ne doit jamais bloquer la suite). Garde-fou : si rien ne démarre en 12 s,
// on réessaie une fois avec une nouvelle requête, puis on passe au titre suivant.
let stuckTimer = null;
function trackUrl(s, attempt) {
  if (s.streamUrl) return s.streamUrl;
  let u = "/rest/stream.view?id=" + encodeURIComponent(s.id);
  // format=raw : le serveur envoie le fichier tel quel (FLAC, MP3…), sans recompression
  if (attempt < 2) u += "&format=raw";
  if (attempt > 0) u += "&_r=" + Date.now();
  return u;
}
function loadTrack(s, attempt) {
  clearTimeout(stuckTimer);
  audio.pause();
  audio.removeAttribute("src");
  audio.load();
  if (s.youtubeId) audio.loadYouTube(s.youtubeId); else audio.src = trackUrl(s, attempt);
  audio.dataset.attempt = String(attempt);
  audio.play().catch(() => {});
  stuckTimer = setTimeout(() => {
    const c = cur();
    if (!c || c.id !== s.id || audio.currentTime > 0 || (!audio.paused && audio.readyState >= 3)) return;
    if (attempt < 1) { loadTrack(s, attempt + 1); return; }
    toast("Ce titre ne démarre pas : passage au suivant");
    if (qi + 1 < queue.length) playIdx(qi + 1);
  }, 12000);
}
function playIdx(i) {
  if (i < 0 || i >= queue.length) return;
  qi = i; scrobbled = false;
  const s = queue[i];
  loadTrack(s, 0);
  refreshUI();
  if (!isExternal(s)) api("scrobble", {id: s.id, submission: "false"}).catch(() => {});
  if ("mediaSession" in navigator) {
    try {
      navigator.mediaSession.metadata = new MediaMetadata({
        title: s.title, artist: s.artist || "", album: s.album || "",
        artwork: coverOf(s, 256) ? [{src: coverOf(s, 256), sizes: "256x256"}] : []});
    } catch (e) {}
  }
}
async function playNext() {
  if (repeat === 2) { audio.currentTime = 0; audio.play().catch(() => {}); return; }
  if (qi + 1 < queue.length) return playIdx(qi + 1);
  if (endless) {
    try {
      const p = typeof endless === "object" ? endless : {};
      const j = await api("getRandomSongs", Object.assign({size: 40}, p));
      const more = ((j.randomSongs && j.randomSongs.song) || []);
      if (more.length) { queue = queue.concat(more); return playIdx(qi + 1); }
    } catch (e) {}
  }
  if (repeat === 1) return playIdx(0);
  audio.pause();
}
function toggleShuffle() {
  if (!queue.length) return;
  if (!shuffleOn) {
    origQueue = queue.slice();
    queue = queue.slice(0, qi + 1).concat(shuffled(queue.slice(qi + 1)));
    shuffleOn = true;
  } else {
    const id = cur() && cur().id;
    queue = origQueue || queue; origQueue = null; shuffleOn = false;
    const k = queue.findIndex(x => x.id === id); if (k >= 0) qi = k;
  }
  refreshUI();
}
async function toggleHeart() {
  const s = cur(); if (!s || (isExternal(s) && !hasLocalHeart(s))) return;
  try {
    await toggleStar(s);
    refreshUI();
  } catch (e) { toast(e.message); }
}
