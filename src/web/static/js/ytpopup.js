"use strict";
// Vidéo refusée par le lecteur intégré (écran du Pi) : on propose de la lire sur la vraie page YouTube,
// dans une petite fenêtre par-dessus l'interface (pas un onglet). Ce n'est pas un titre de la file :
// à la fermeture, ou à la fin prévue du morceau, la liste reprend au titre suivant.

const POPUP_FEATURES = "popup,width=760,height=340,left=20,top=8";   // laisse le bandeau visible en bas de l’écran 800×480
const LOAD_MARGIN_S = 8;              // temps de chargement de la page avant le début du morceau
const CLOSE_WARNING_S = 15;           // « Fermeture dans 15 s » : on peut garder la fenêtre ouverte
const ANSWER_TIMEOUT_MS = 12000;      // sans réponse à la proposition : titre suivant

class YouTubeWindow {
  constructor() { this.win = null; this.veil = null; this.watch = null; this.endTimer = null; this.countdown = null; }

  open(song) {
    this.close(false);
    this.win = window.open("https://www.youtube.com/watch?v=" + encodeURIComponent(song.youtubeId), "pm-youtube", POPUP_FEATURES);
    if (!this.win) { toast("Fenêtre bloquée par le navigateur"); this.finish(); return; }
    this.showVeil(song);
    this.watch = setInterval(() => { if (!this.win || this.win.closed) this.finish(); }, 1000);
    if (song.duration > 0) this.endTimer = setTimeout(() => this.warnBeforeClosing(), (song.duration + LOAD_MARGIN_S) * 1000);
  }

  /* Fond assombri derrière la fenêtre, comme une pop-in */
  showVeil(song) {
    const veil = document.createElement("div"); veil.id = "ytveil";
    veil.innerHTML = '<div class="ytvbox"><b></b><span>Lecture sur YouTube. Votre liste reprendra à la fermeture.</span>'
      + '<em></em><div class="ytvbtns"><button type="button" class="keep" hidden>Garder ouverte</button>'
      + '<button type="button" class="close">Fermer YouTube</button></div></div>';
    veil.querySelector("b").textContent = song.title + (song.artist ? " · " + song.artist : "");
    veil.querySelector(".close").onclick = () => this.close(true);
    veil.querySelector(".keep").onclick = () => this.keepOpen();
    document.body.appendChild(veil);
    this.veil = veil;
  }

  warnBeforeClosing() {
    if (!this.veil) return;
    let left = CLOSE_WARNING_S;
    const note = this.veil.querySelector("em"), keep = this.veil.querySelector(".keep");
    keep.hidden = false;
    const paint = () => { note.textContent = "Fermeture de YouTube dans " + left + " s"; };
    paint();
    this.countdown = setInterval(() => { if (--left <= 0) this.close(true); else paint(); }, 1000);
  }

  keepOpen() {
    clearInterval(this.countdown); this.countdown = null;
    if (!this.veil) return;
    this.veil.querySelector("em").textContent = "";
    this.veil.querySelector(".keep").hidden = true;
  }

  close(resume) {
    clearInterval(this.watch); clearTimeout(this.endTimer); clearInterval(this.countdown);
    this.watch = this.endTimer = this.countdown = null;
    if (this.win && !this.win.closed) this.win.close();
    this.win = null;
    if (this.veil) { this.veil.remove(); this.veil = null; }
    if (resume) this.resumeList();
  }

  finish() { this.close(true); }

  resumeList() { if (qi + 1 < queue.length) playIdx(qi + 1); }
}

const youTubeWindow = new YouTubeWindow();

/* Appelée quand le lecteur intégré refuse une vidéo et qu'aucune autre version n'a été trouvée */
function offerYouTubeWindow(song, label) {
  let answered = false;
  openSheet(label + " — lecture impossible ici", [
    {icon: "play", label: "Lire sur YouTube (fenêtre)", fn: () => { answered = true; youTubeWindow.open(song); }},
    {icon: "next", label: qi + 1 < queue.length ? "Passer au titre suivant" : "Ne rien faire", fn: () => { answered = true; youTubeWindow.resumeList(); }}
  ]);
  setTimeout(() => {
    if (answered || cur() !== song) return;
    closeSheet();
    youTubeWindow.resumeList();                 // personne n'a répondu : la musique ne reste pas bloquée
  }, ANSWER_TIMEOUT_MS);
}
