"use strict";
// Paroles synchronisées et anecdotes

/* ---- Paroles et anecdotes ---- */
let infoId = null, lyr = null, lyrId = null, lines = [], lineEl = [], lineIdx = -1, plainEl = [], lastTouch = 0, lastAuto = 0;
let facts = [], factI = 0, factTimer = null, infoData = {};
const infoQ = s => "artist=" + encodeURIComponent(s.artist || "") + "&title=" + encodeURIComponent(s.title || "");
function showFact() {
  const box = $("#fanec");
  if (!facts.length) { box.hidden = true; return; }
  const f = facts[factI % facts.length]; factI++;
  box.style.opacity = 0;
  setTimeout(() => {
    const im = box.querySelector("img");
    if (infoData.img) { im.src = infoData.img; im.hidden = false; } else im.hidden = true;
    box.hidden = false; box.querySelector("b").textContent = f.k; box.querySelector("span").textContent = f.t;
    box.style.opacity = 1;
  }, 600);
}
function infoFor(s) {
  if (!s || isRadio(s) || !s.artist || !s.title) { facts = []; infoData = {}; $("#fanec").hidden = true; return; }
  if (infoId === s.id) return;
  infoId = s.id; facts = []; infoData = {}; factI = 0; $("#fanec").hidden = true;
  clearInterval(factTimer);
  const id = s.id;
  fetch("/info/facts?" + infoQ(s) + "&aid=" + encodeURIComponent(s.artistId || "") + "&album=" + encodeURIComponent(s.album || ""))
    .then(r => r.json()).then(j => {
      if (infoId !== id) return;
      infoData = j; facts = j.facts || []; factI = 0; showFact();
      factTimer = setInterval(() => { if ($("#full").hidden) return; showFact(); }, 14000);
    }).catch(() => {});
}
function parseLrc(t) {
  const out = [];
  (t || "").split("\n").forEach(l => {
    const m = l.match(/^\[(\d+):(\d+(?:\.\d+)?)\](.*)$/);
    if (m) out.push({t: +m[1] * 60 + parseFloat(m[2]), s: m[3].trim()});
  });
  return out;
}
async function openLyrics() {
  const s = cur(), box = $("#flyr");
  if (!s) return;
  if (!box.hidden) { box.hidden = true; return; }
  $("#fqueue").hidden = true; box.hidden = false;
  if (lyrId !== s.id) {
    lyrId = s.id; lyr = null; lines = []; lineEl = []; lineIdx = -1; plainEl = [];
    box.innerHTML = '<div class="msg">Recherche des paroles\u2026</div>';
    try {
      const j = await (await fetch("/info/lyrics?" + infoQ(s) + "&album=" + encodeURIComponent(s.album || "") + "&duration=" + (s.duration || 0))).json();
      if (lyrId !== s.id) return;
      lyr = j;
    } catch (e) { lyr = {}; }
    box.innerHTML = "";
    lines = parseLrc(lyr.synced);
    if (lines.length) {
      lineEl = lines.map(l => { const p = document.createElement("p"); p.textContent = l.s || "\u266a"; box.appendChild(p); return p; });
    } else if (lyr.plain) {
      lyr.plain.split("\n").forEach(l => { const p = document.createElement("p"); p.style.color = "var(--soft)"; p.textContent = l || "\u00a0"; box.appendChild(p); plainEl.push(p); });
    } else {
      box.innerHTML = '<div class="msg">Aucune parole trouvée pour ce titre.</div>';
    }
    if (lyr.src) { const sm = document.createElement("small"); sm.textContent = "Source : " + lyr.src + (lines.length ? "" : " · non synchronisées, défilement estimé"); box.appendChild(sm); }
  }
}
// Paroles sans synchronisation : défilement estimé d'après l'avancement du morceau (approximatif)
$("#flyr").addEventListener("pointerdown", () => { lastTouch = Date.now(); });
$("#flyr").addEventListener("wheel", () => { lastTouch = Date.now(); });
function autoScrollPlain() {
  const box = $("#flyr");
  if (!plainEl.length || box.hidden || !audio.duration || lyrId !== (cur() || {}).id) return;
  const now = Date.now();
  if (now - lastTouch < 8000 || now - lastAuto < 1500) return;     // l'utilisateur lit à son rythme : on ne le dérange pas
  lastAuto = now;
  const f = Math.min(1, Math.max(0, (audio.currentTime - 8) / Math.max(1, audio.duration - 30)));
  const k = Math.min(plainEl.length - 1, Math.floor(f * plainEl.length));
  const el = plainEl[k];
  box.scrollTo({top: el.offsetTop - box.clientHeight / 3, behavior: "smooth"});
}
function syncLyrics() {
  autoScrollPlain();
  if (!lines.length || $("#flyr").hidden || lyrId !== (cur() || {}).id) return;
  const t = audio.currentTime + 0.3;
  let k = -1;
  for (let i = 0; i < lines.length && lines[i].t <= t; i++) k = i;
  if (k === lineIdx) return;
  if (lineEl[lineIdx]) lineEl[lineIdx].classList.remove("cur");
  lineIdx = k;
  if (k >= 0) {
    const el = lineEl[k]; el.classList.add("cur");
    const box = $("#flyr");
    box.scrollTo({top: el.offsetTop - box.clientHeight / 2 + el.clientHeight / 2, behavior: "smooth"});
  }
}
