"use strict";
// Taper depuis le téléphone (écran du Pi) : QR code à scanner, puis le texte tapé arrive dans la recherche

class PhoneRemote {
  constructor() { this.version = null; this.pickVersion = null; this.timer = null; this.overlay = null; this.shared = false; }

  /* Une seule fois : noms et identifiants des artistes, pour que le téléphone affiche les suggestions */
  shareArtists(artists) {
    if (this.shared || !artists.length) return;
    this.shared = true;
    fetch("/ext/remote/artists", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({artists: artists.map(a => ({id: a.id, name: a.name}))})}).catch(() => { this.shared = false; });
  }

  async fetchState(renew) {
    const r = await fetch("/ext/remote", renew ? {method: "POST"} : {});
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
    return j;
  }

  /* Tant que l'écran de recherche est affiché, on regarde si le téléphone a envoyé du texte */
  watch(isVisible) {
    clearInterval(this.timer);
    this.version = this.pickVersion = null;
    this.timer = setInterval(async () => {
      if (!isVisible()) { clearInterval(this.timer); this.close(); return; }
      try {
        const s = await this.fetchState(false);
        if (this.version !== null && s.version !== this.version) this.received(s.text);
        if (this.pickVersion !== null && s.pickVersion !== this.pickVersion && s.pick) this.picked(s.pick);
        this.version = s.version; this.pickVersion = s.pickVersion;
      } catch (e) { /* serveur téléphone arrêté : la recherche au clavier reste disponible */ }
    }, 500);
  }

  received(text) {
    this.close();
    setKb(false);
    setSearchText(text);
  }

  /* Suggestion touchée sur le téléphone : l'artiste s'ouvre sur l'écran du Pi */
  picked(artist) {
    this.close();
    setKb(false);
    musicHistory.remember(qtext);
    openView(artist.name, c => artistView(artist.id, c));
  }

  async open() {
    let s;
    try { s = await this.fetchState(true); } catch (e) { toast(e.message); return; }   // nouveau code à chaque affichage
    this.version = s.version; this.pickVersion = s.pickVersion;
    this.close();
    const qr = qrcode(0, "M"); qr.addData(s.url); qr.make();
    const veil = document.createElement("div"); veil.id = "phoneqr";
    veil.innerHTML = '<div class="pqbox"><div class="pqcode"></div><div class="pqtext"><b>Scannez avec votre téléphone</b>'
      + "<span>Même Wi-Fi que le Pi. Ce que vous tapez sur le téléphone s’affiche ici, dans la recherche.</span>"
      + '<small></small><button type="button">Fermer</button></div></div>';
    veil.querySelector(".pqcode").innerHTML = qr.createSvgTag(5, 2);
    veil.querySelector("small").textContent = s.url;
    veil.querySelector("button").onclick = () => this.close();
    veil.onclick = e => { if (e.target === veil) this.close(); };
    document.body.appendChild(veil);
    this.overlay = veil;
  }

  close() { if (this.overlay) { this.overlay.remove(); this.overlay = null; } }
}

const phoneRemote = new PhoneRemote();

/* Petit bouton discret dans la barre du clavier : le clavier de l'écran reste la saisie principale */
function addPhoneButton() {
  const bar = $("#kbbar");
  if (!bar) return;
  const b = document.createElement("button"); b.type = "button"; b.id = "kbphone";
  b.textContent = "Saisir sur le téléphone";
  b.onclick = () => phoneRemote.open();
  bar.insertBefore(b, bar.firstChild);
}
addPhoneButton();
