"use strict";
// Podcasts : outils communs (requêtes, formats, icônes, messages)

const $ = s => document.querySelector(s);
const main = $("#main");
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));

/* ---------- Requêtes ---------- */
async function pget(name, params) {
  const r = await fetch("/podcast-api/" + name + "?" + new URLSearchParams(params || {}));
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  return j;
}
async function ppost(name, body) {
  const r = await fetch("/podcast-api/" + name, {method: "POST", body: JSON.stringify(body || {}),
    headers: {"Content-Type": "application/json", "X-Requested-With": "pm"}});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  return j;
}

/* ---------- Formats ---------- */
function fmtTime(s) {
  s = Math.max(0, Math.round(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0");
}
function fmtLength(s) {
  s = Math.round((s || 0) / 60);
  if (!s) return "";
  return s >= 60 ? Math.floor(s / 60) + " h " + String(s % 60).padStart(2, "0") : s + " min";
}
function fmtDate(t) {
  if (!t) return "";
  const days = Math.floor((Date.now() / 1000 - t) / 86400);
  if (days <= 0) return "aujourd’hui";
  if (days === 1) return "hier";
  if (days < 7) return "il y a " + days + " jours";
  return new Date(t * 1000).toLocaleDateString("fr-FR", {day: "numeric", month: "short", year: days > 300 ? "numeric" : undefined});
}
const stripTags = s => String(s || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

/* ---------- Icônes ---------- */
const ICON = {
  play: "M8 5v14l11-7z", pause: "M6 5h4v14H6zM14 5h4v14h-4z", left: "M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z",
  down: "M7.41 8.59L12 13.17l4.59-4.58L18 10l-6 6-6-6z", check: "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
  plus: "M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z",
  back: "M12 5V1L7 6l5 5V7c3.31 0 6 2.69 6 6s-2.69 6-6 6-6-2.69-6-6H4c0 4.42 3.58 8 8 8s8-3.58 8-8-3.58-8-8-8z",
  fwd: "M12 5V1l5 5-5 5V7c-3.31 0-6 2.69-6 6s2.69 6 6 6 6-2.69 6-6h2c0 4.42-3.58 8-8 8s-8-3.58-8-8 3.58-8 8-8z",
  mic: "M12 14c1.66 0 3-1.34 3-3V5c0-1.66-1.34-3-3-3S9 3.34 9 5v6c0 1.66 1.34 3 3 3zm5.3-3c0 3-2.54 5.1-5.3 5.1S6.7 14 6.7 11H5c0 3.41 2.72 6.23 6 6.72V21h2v-3.28c3.28-.48 6-3.3 6-6.72h-1.7z"
};
const ic = (n, s) => '<svg viewBox="0 0 24 24" width="' + (s || 24) + '" height="' + (s || 24) + '" fill="currentColor"><path d="' + ICON[n] + '"/></svg>';

let toastTimer = null;
function toast(msg) {
  const t = $("#toast"); t.textContent = msg; t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, 2800);
}

/* ---------- Défilement au doigt (secours si le navigateur émule la souris) ---------- */
let dragState = null, dragSuppress = false;
document.addEventListener("pointerdown", e => {
  if (e.pointerType === "touch") return;
  const shelf = e.target.closest(".pshelf");
  const el = shelf || (e.target.closest("#main") ? main : null);
  if (el) dragState = {el, horiz: !!shelf, x: e.clientX, y: e.clientY, sl: el.scrollLeft, st: el.scrollTop, moved: false};
});
window.addEventListener("pointermove", e => {
  if (!dragState) return;
  const dx = e.clientX - dragState.x, dy = e.clientY - dragState.y;
  if (Math.abs(dx) > 6 || Math.abs(dy) > 6) dragState.moved = true;
  if (!dragState.moved) return;
  if (dragState.horiz) dragState.el.scrollLeft = dragState.sl - dx; else dragState.el.scrollTop = dragState.st - dy;
});
window.addEventListener("pointerup", () => {
  if (dragState && dragState.moved) { dragSuppress = true; setTimeout(() => { dragSuppress = false; }, 60); }
  dragState = null;
});
document.addEventListener("click", e => { if (dragSuppress) { e.stopPropagation(); e.preventDefault(); } }, true);
