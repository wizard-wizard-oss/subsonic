"use strict";
// Recherche

/* ---------- Suggestions : artistes de la bibliothèque, dès les premières lettres ---------- */
const plainText = s => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

class ArtistSuggestions {
  /* La liste des artistes vient de getArtists, déjà en cache côté serveur : rien à attendre du serveur Subsonic */
  constructor(limit) { this.limit = limit; this.artists = null; this.loading = null; }

  load() {
    if (!this.loading) {
      this.loading = api("getArtists").then(r => {
        this.artists = [];
        ((r.artists || {}).index || []).forEach(group => (group.artist || []).forEach(ar =>
          this.artists.push({ar, name: plainText(ar.name), words: plainText(ar.name).split(/[^a-z0-9]+/)})));
      }).catch(() => { this.loading = null; });
    }
    return this.loading;
  }

  /* Le nom commence par le texte tapé d'abord, puis un mot du nom qui commence par lui */
  find(text) {
    const wanted = plainText(text).trim();
    if (wanted.length < 2 || !this.artists) return [];
    const starts = [], inside = [];
    for (const a of this.artists) {
      if (a.name.startsWith(wanted)) starts.push(a.ar);
      else if (a.words.some(w => w.startsWith(wanted))) inside.push(a.ar);
      if (starts.length >= this.limit) break;
    }
    return starts.concat(inside).slice(0, this.limit);
  }

  show(container, text) {
    container.innerHTML = "";
    const found = this.find(text);
    if (!found.length) return;
    found.forEach(ar => {
      const b = document.createElement("button");
      b.textContent = ar.name;
      b.onclick = () => { musicHistory.remember(qtext); openView(ar.name, c => artistView(ar.id, c)); };
      container.appendChild(b);
    });
  }
}

/* ---------- Recherche avec clavier intégré ---------- */
let qtext = "", qtimer = null, qbox = null, qres = null, qsug = null;
const musicHistory = new SearchHistoryList("music");
const suggestions = new ArtistSuggestions(8);

/* Point d'entrée unique pour changer le texte : clavier, historique, téléphone */
function setSearchText(text) {
  qtext = text;
  if (qbox) qbox.textContent = qtext || "Artiste, album, titre…";
  if (qsug) suggestions.show(qsug, qtext);           // tout de suite, sans attendre le serveur
  runSearch();
}
const pickFromHistory = text => setSearchText(text);

function runSearch() {
  clearTimeout(qtimer);
  qtimer = setTimeout(async () => {
    if (!qres) return;
    qres.innerHTML = "";
    if (qtext.trim().length < 2) { musicHistory.show(qres, pickFromHistory); return; }
    try {
      const r = (await api("search3", {query: qtext.trim(), artistCount: 6, albumCount: 12, songCount: 30})).searchResult3 || {};
      if ((r.artist || []).length) { header(qres, "Artistes"); r.artist.forEach(ar => qres.appendChild(artistRow(ar))); }
      if ((r.album || []).length) { header(qres, "Albums"); r.album.forEach(al => qres.appendChild(albumRow(al))); }
      if ((r.song || []).length) { header(qres, "Titres"); songRows(qres, r.song, {search: true}); }
      if (!qres.children.length) qres.innerHTML = '<div class="msg">Aucun résultat.</div>';
      if (typeof extSearchSection === "function") extSearchSection(qres, qtext.trim());      // « Ailleurs » (ext.js)
    } catch (e) { qres.innerHTML = '<div class="msg">' + esc(e.message) + "</div>"; }
  }, 350);
}
new TouchKeyboard($("#kb"), async k => {
  if (k === KEY.ENTER) { setKb(false); return; }
  setSearchText(k === KEY.PASTE ? qtext + await clipboardText(toast) : applyKey(qtext, k));
});
tabs.search = () => openView("Recherche", async c => {
  qbox = document.createElement("div"); qbox.id = "qbox"; qbox.textContent = qtext || "Artiste, album, titre…";
  qsug = document.createElement("div"); qsug.className = "chips qsug";
  qres = document.createElement("div");
  // toucher un résultat = la recherche a servi : on la garde dans l'historique
  qres.addEventListener("click", e => { if (!e.target.closest(".hist, .msg")) musicHistory.remember(qtext); }, true);
  c.appendChild(qbox); c.appendChild(qsug); c.appendChild(qres);
  if (typeof phoneRemote === "object") phoneRemote.watch(() => qsug.isConnected);      // texte envoyé du téléphone (remote.js)
  setKb(true);
  qbox.onclick = () => { setKb(true); };          // toucher la zone rouvre le clavier
  main.onscroll = () => { if (main.scrollTop > 20) setKb(false); };   // défiler le ferme
  suggestions.load().then(() => {
    if (qsug && qsug.isConnected) suggestions.show(qsug, qtext);
    if (typeof phoneRemote === "object" && suggestions.artists) phoneRemote.shareArtists(suggestions.artists.map(a => a.ar));
  });
  runSearch();
});
$("#kbclose").onclick = () => { setKb(false); };
