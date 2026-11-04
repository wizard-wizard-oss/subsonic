"use strict";
// Interface du lecteur (barre et plein écran)

/* ---------- Interface du lecteur ---------- */
function refreshUI() {
  const s = cur();
  if (typeof syncPreload === "function") syncPreload();      // haute fidélité : titre suivant préchargé (hifi.js)
  if (typeof sharedQueue === "object" && sharedQueue) sharedQueue.scheduleSave();   // file commune (queue.js)
  if (typeof placeVideo === "function") placeVideo();      // lecteur YouTube : voir ext.js
  const playing = !audio.paused && !!audio.src;
  $("#pp").innerHTML = ic(playing ? "pause" : "play", 30);
  $("#fpp").innerHTML = ic(playing ? "pause" : "play", 34);
  $("#prev").innerHTML = ic("prev"); $("#next").innerHTML = ic("next");
  $("#fprev").innerHTML = ic("prev", 28); $("#fnext").innerHTML = ic("next", 28);
  $("#fshuf").innerHTML = ic("shuffle", 24); $("#fshuf").classList.toggle("on", shuffleOn);
  $("#frep").innerHTML = ic("repeat", 24) + (repeat === 2 ? '<i class="one">1</i>' : ""); $("#frep").classList.toggle("on", repeat > 0);
  $("#fclose").innerHTML = ic("down", 28);
  $("#npshuf").innerHTML = ic("shuffle", 22); $("#npshuf").classList.toggle("on", shuffleOn);
  $("#nplist").innerHTML = ic("list", 24);
  $("#fplaylist").innerHTML = ic("plus", 18) + "<span>Playlist</span>";
  $("#fradio").innerHTML = ic("radio", 18) + "<span>Radio</span>";
  $("#fqbtn").innerHTML = ic("list", 18) + "<span>File</span>";
  $("#flbtn").innerHTML = ic("list", 18) + "<span>Paroles</span>";
  $("#fibtn").innerHTML = ic("user", 18) + "<span>Infos</span>";
  $("#fvbtn").innerHTML = ic("volume", 18) + "<span>Volume</span>"; $("#fvm").textContent = "\u2212"; $("#fvp").textContent = "+";
  if (!s) { $("#npheart").innerHTML = ic("heart", 24); return; }
  const fmtq = [s.suffix ? s.suffix.toUpperCase() : "", s.bitDepth && s.samplingRate ? s.bitDepth + " bits / " + (s.samplingRate / 1000) + " kHz" : "",
                s.bitRate ? s.bitRate + " kbps" : ""].filter(Boolean).join(" · ");
  const sub = (s.artist || "") + (s.album ? " · " + s.album : "") + (fmtq ? " · " + fmtq : "");
  $("#nptitle").textContent = s.title; $("#npsub").textContent = sub;
  $("#npimg").src = coverOf(s, 96);
  $("#ftitle").textContent = s.title; $("#fartist").textContent = s.artist || "";
  $("#falbum").textContent = (s.album || "") + (fmtq ? "  ·  " + fmtq : "");
  const big = coverOf(s, 400);
  $("#fcover").src = big; $("#fbg").style.backgroundImage = big ? 'url("' + big + '")' : "none";
  const starred = isStarred(s), hv = starred ? "heartfill" : "heart";
  $("#npheart").innerHTML = ic(hv, 24); $("#npheart").classList.toggle("on", starred);
  $("#fheart").innerHTML = ic(hv, 18) + "<span>" + (starred ? "Favori" : "Favoris") + "</span>";
  if (!$("#fqueue").hidden) renderQueue();
  if (!$("#full").hidden) infoFor(s);
}
function renderQueue(keepScroll) {
  const q = $("#fqueue"), top = q.scrollTop; q.innerHTML = "";
  queue.forEach((s, i) => {
    const d = row(coverOf(s, 64), s.title, (s.artist || "") + (s.duration ? " · " + fmt(s.duration) : ""), () => playIdx(i));
    if (i === qi) d.classList.add("cur");
    const g = document.createElement("button"); g.className = "grip"; g.innerHTML = ic("list", 22);
    g.onclick = e => e.stopPropagation();
    attachDrag(g, d, i);
    d.appendChild(g);
    q.appendChild(d);
  });
  if (keepScroll) { q.scrollTop = top; return; }
  const el = q.children[qi];      // pas de scrollIntoView : il décalait tout l'écran plein écran
  if (el) q.scrollTop = el.offsetTop - q.clientHeight / 2 + el.offsetHeight / 2;
}
// Réorganisation par glisser-déposer : on attrape la poignée à droite d'une ligne
function attachDrag(g, d, i) {
  g.onpointerdown = e => {
    e.preventDefault(); e.stopPropagation();
    const q = $("#fqueue"), rows = Array.from(q.children), hh = d.offsetHeight;
    g.setPointerCapture(e.pointerId);
    const y0 = e.clientY, s0 = q.scrollTop;
    let lastY = y0, to = i;
    d.classList.add("drag");
    const update = () => {
      const dy = lastY - y0 + (q.scrollTop - s0);
      d.style.transform = "translateY(" + dy + "px)";
      to = Math.max(0, Math.min(rows.length - 1, i + Math.round(dy / hh)));
      rows.forEach((r, k) => {
        if (r === d) return;
        let sh = 0;
        if (i < to && k > i && k <= to) sh = -hh; else if (i > to && k < i && k >= to) sh = hh;
        r.style.transform = sh ? "translateY(" + sh + "px)" : "";
      });
    };
    const timer = setInterval(() => {      // défilement automatique près des bords
      const r = q.getBoundingClientRect();
      if (lastY < r.top + 50) q.scrollTop -= 12; else if (lastY > r.bottom - 50) q.scrollTop += 12; else return;
      update();
    }, 16);
    g.onpointermove = ev => { lastY = ev.clientY; update(); };
    const end = () => {
      clearInterval(timer); g.onpointermove = g.onpointerup = g.onpointercancel = null;
      if (to !== i) {
        const m = queue.splice(i, 1)[0]; queue.splice(to, 0, m);
        if (qi === i) qi = to; else if (i < qi && to >= qi) qi--; else if (i > qi && to <= qi) qi++;
      }
      renderQueue(true);
    };
    g.onpointerup = g.onpointercancel = end;
  };
}
function seek(e) {
  const r = e.currentTarget.getBoundingClientRect();
  if (audio.duration && isFinite(audio.duration)) {
    const ratio = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    if (ratio > 0.985) { playNext(); return; }       // tout au bout de la barre : on passe directement au titre suivant
    audio.currentTime = audio.duration * ratio;
  }
}
audio.onended = () => {
  if (typeof guestHandover === "object" && guestHandover.onTrackEnd()) return;     // un téléphone attend son tour (guest.js)
  playNext();
};
audio.onplaying = () => clearTimeout(stuckTimer);
audio.onplay = refreshUI; audio.onpause = refreshUI;
// Codes d'erreur du lecteur YouTube intégré
const YT_ERRORS = {2: "paramètre refusé", 5: "lecteur HTML5", 100: "vidéo supprimée ou privée",
                   101: "intégration interdite", 150: "intégration interdite", 152: "intégration interdite",
                   153: "configuration du lecteur", "yt-load": "YouTube injoignable"};
const YT_VIDEO_REFUSALS = [100, 101, 150, 152];
/* Vidéo refusée : on cherche une autre vidéo du même titre (une seule fois), sinon titre suivant */
async function youtubeRefused(s, code) {
  const refused = YT_VIDEO_REFUSALS.includes(code);
  // seuls les refus propres à la vidéo la font retenir comme illisible ; les autres codes viennent plutôt de notre côté
  if (refused) extPost("unplayable", {id: s.youtubeId}).catch(() => {});
  const label = "Vidéo illisible (code " + code + (YT_ERRORS[code] ? " : " + YT_ERRORS[code] : "") + ")";
  if (refused && !s.altTried && EXT.youtube.enabled) {
    toast(label + " — recherche d’une autre version…");
    try {
      const alt = (await extGet("alternative", {id: s.youtubeId, title: s.title, artist: s.artist || ""})).item;
      if (alt && cur() === s) {
        queue[qi] = Object.assign({}, alt, {altTried: true});
        toast("Autre version trouvée : " + alt.title);
        playIdx(qi);
        return;
      }
    } catch (e) { /* pas de remplacement : on passe à la suite */ }
  }
  if (cur() !== s) return;
  if (refused && typeof offerYouTubeWindow === "function") { offerYouTubeWindow(s, label); return; }   // ytpopup.js
  toast(label + (qi + 1 < queue.length ? " — titre suivant" : ""));
  if (qi + 1 < queue.length) setTimeout(() => { if (cur() === s) playIdx(qi + 1); }, 1500);
}
audio.onerror = () => {
  const s = cur();
  if (s && s.youtubeId) { youtubeRefused(s, audio.error ? audio.error.code : "?"); return; }
  if (!s || s.streamUrl) { toast("Lecture impossible"); return; }
  const attempt = parseInt(audio.dataset.attempt || "0", 10);
  // 1) nouvelle requête ; 2) format non lisible par le navigateur (rare : APE, WMA…) : le serveur convertit
  if (attempt < 2) { loadTrack(s, attempt + 1); return; }
  const code = audio.error ? audio.error.code : "?";
  toast("Lecture impossible (code " + code + ")" + (qi + 1 < queue.length ? " : titre suivant" : ""));
  if (qi + 1 < queue.length) setTimeout(() => { if (cur() === s) playIdx(qi + 1); }, 1500);   // la file ne reste jamais bloquée
};
