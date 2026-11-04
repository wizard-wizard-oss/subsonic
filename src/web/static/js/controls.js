"use strict";
// Boutons du lecteur plein écran, raccourcis média

$("#flbtn").onclick = () => { $("#finf").hidden = true; openLyrics(); };
$("#fibtn").onclick = () => {
  const box = $("#finf"), s = cur();
  if (!box.hidden) { box.hidden = true; return; }
  if (!s) return;
  $("#flyr").hidden = true; $("#fqueue").hidden = true; box.hidden = false;
  box.innerHTML = "";
  if (infoData.img) { const im = document.createElement("img"); im.src = infoData.img; box.appendChild(im); }
  const t = document.createElement("h3"); t.textContent = s.artist || ""; box.appendChild(t);
  if (infoData.bio) { const p = document.createElement("p"); p.textContent = infoData.bio; box.appendChild(p); }
  (infoData.facts || []).forEach(f => { const p = document.createElement("p"); p.textContent = f.t; box.appendChild(p); });
  if (!infoData.bio && !(infoData.facts || []).length) { const p = document.createElement("p"); p.textContent = "Pas d\u2019informations trouvées (elles se chargent quelques secondes après le début du titre)."; box.appendChild(p); }
};
audio.ontimeupdate = () => {
  syncLyrics();
  if (audio.duration && isFinite(audio.duration)) {
    const pct = (100 * audio.currentTime / audio.duration) + "%";
    document.querySelectorAll(".prog i").forEach(i => { i.style.width = pct; });
    $("#ftcur").textContent = fmt(audio.currentTime); $("#ftdur").textContent = fmt(audio.duration);
  }
  const s = cur();
  if (!scrobbled && s && !isExternal(s) && audio.duration && (audio.currentTime > 240 || audio.currentTime > audio.duration / 2)) {
    scrobbled = true;
    api("scrobble", {id: s.id, submission: "true"}).catch(() => {});
  }
};
const toggle = () => { if (audio.src) { if (audio.paused) audio.play(); else audio.pause(); } };
const prevTrack = () => { if (audio.currentTime > 4) audio.currentTime = 0; else playIdx(qi - 1); };
$("#prog").onclick = seek; $("#fbar").onclick = seek;
$("#pp").onclick = toggle; $("#fpp").onclick = toggle;
$("#next").onclick = () => { playNext(); }; $("#fnext").onclick = () => { playNext(); };
$("#prev").onclick = prevTrack; $("#fprev").onclick = prevTrack;
$("#npheart").onclick = toggleHeart; $("#fheart").onclick = toggleHeart;
$("#fshuf").onclick = toggleShuffle;
$("#frep").onclick = () => { repeat = (repeat + 1) % 3; refreshUI(); };
$("#fplaylist").onclick = () => { const s = cur(); if (s && !isRadio(s)) addToPlaylist([s]); };
$("#fradio").onclick = () => { const s = cur(); if (s && !isExternal(s)) radioFromSong(s); else toast("Rien à lancer"); };
$("#fqbtn").onclick = () => {
  const q = $("#fqueue"); $("#flyr").hidden = true; $("#finf").hidden = true; q.hidden = !q.hidden; $("#fbody").hidden = !q.hidden;
  if (!q.hidden) renderQueue();
};
$("#fartist").onclick = async () => { const s = cur(); if (!s || !s.artist) return; const id = await artistIdOf(s); if (id) { closeFull(); openView(s.artist, c => artistView(id, c)); } };
$("#np").onclick = () => { if (cur()) { $("#full").hidden = false; $("#full").scrollTop = 0; $("#flyr").hidden = true; $("#finf").hidden = true; $("#fqueue").hidden = true; $("#fbody").hidden = false; refreshUI(); } };
$("#fclose").onclick = closeFull;
// Sécurité : l'écran plein écran ne doit jamais se décaler (la flèche verte de fermeture resterait hors de vue)
$("#full").addEventListener("scroll", () => { $("#full").scrollTop = 0; $("#full").scrollLeft = 0; });
$("#npshuf").onclick = toggleShuffle;
$("#nplist").onclick = () => {   // ouvre directement la file de lecture
  if (!cur()) { toast("File vide"); return; }
  $("#full").hidden = false; $("#full").scrollTop = 0; $("#flyr").hidden = true;
  $("#fqueue").hidden = false; $("#fbody").hidden = true;
  refreshUI(); renderQueue();
};
if ("mediaSession" in navigator) {
  const h = (a, f) => { try { navigator.mediaSession.setActionHandler(a, f); } catch (e) {} };
  h("play", () => audio.play()); h("pause", () => audio.pause());
  h("nexttrack", () => playNext()); h("previoustrack", prevTrack);
}
refreshUI();
