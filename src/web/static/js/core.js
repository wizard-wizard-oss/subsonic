"use strict";
// Outils, état partagé, réglages

// Toutes les requêtes de la page portent un en-tête qu'une page d'un autre site ne peut pas ajouter (anti-CSRF)
const _fetch = window.fetch.bind(window);
window.fetch = (u, o) => { o = o || {}; o.headers = Object.assign({"X-Requested-With": "pm"}, o.headers || {}); return _fetch(u, o); };
const $ = s => document.querySelector(s);
let browseMode = "folders";
fetch("/settings").then(r => r.ok ? r.json() : {}).then(j => { browseMode = j.browse_mode || "folders"; }).catch(() => {});
async function artistIdOf(s) {      // en mode dossiers, les titres n\u2019ont pas toujours d\u2019identifiant d\u2019artiste
  if (s.artistId) return s.artistId;
  try {
    const r = (await api("search3", {query: s.artist || "", artistCount: 5, albumCount: 0, songCount: 0})).searchResult3 || {};
    const n = (s.artist || "").toLowerCase();
    const a = (r.artist || []).find(x => (x.name || "").toLowerCase() === n) || (r.artist || [])[0];
    return a ? a.id : null;
  } catch (e) { return null; }
}
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmt = s => { s = Math.round(s || 0); return Math.floor(s / 60) + ":" + String(s % 60).padStart(2, "0"); };
// Versions d'URL pour forcer le rechargement d'une pochette (rafraîchissement d'un album ou de tout)
let bust = {}, bustAll = "";
try { bust = JSON.parse(localStorage.getItem("bust") || "{}"); bustAll = localStorage.getItem("bustAll") || ""; } catch (e) {}
const saveBust = () => { try { localStorage.setItem("bust", JSON.stringify(bust)); localStorage.setItem("bustAll", bustAll); } catch (e) {} };
const cover = (id, size) => id ? "/rest/getCoverArt.view?id=" + encodeURIComponent(id) + "&size=" + (size || 96) +
  ((bust[id] || bustAll) ? "&_b=" + (bust[id] || "") + bustAll : "") : "";
const coverOf = (s, size) => (s && s.imageUrl) || cover(s && s.coverArt, size);
const shuffled = a => { a = a.slice(); for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const stripHtml = h => h ? (new DOMParser().parseFromString(h, "text/html").body.textContent || "").replace(/\s*Read more on Last\.fm.*$/i, "").trim() : "";
const main = $("#main");
let toastTimer = null;
/* Clavier : quand il est ouvert, onglets et lecteur sont masqués pour laisser de la place aux résultats */
function setKb(open) { $("#kbwrap").hidden = !open; $("#app").classList.toggle("kbopen", open); }
