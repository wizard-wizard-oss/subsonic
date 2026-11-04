"use strict";
/* Barre des artistes à gauche, comme Subsonic : index par lettre, filtre, artiste en cours surligné.
   Trois modes (réglage « sidebar ») : fixe, apparaît au survol du bord gauche, masquée. */

class ArtistSidebar {
  constructor(app) {
    this.app = app;
    this.root = document.getElementById("sidebar");
    this.edge = document.getElementById("sidebar-edge");
    this.list = document.getElementById("artist-list");
    this.letters = document.getElementById("letters");
    this.shortcuts = document.getElementById("artist-shortcuts");     // dossiers épinglés (« Compilations »)
    this.filter = document.getElementById("artist-filter");
    this.index = [];
    this.groups = null;
    this.observer = null;
    this.rowHeight = 26;                                       // estimation, corrigée à la première lettre construite
    this.peeking = false;
    this.timer = null;
    this.filter.addEventListener("input", () => this.render());
    this.filter.addEventListener("keydown", e => {
      if (e.key === "Enter") {
        const first = this.list.querySelector("a.artist");
        if (first) location.hash = first.getAttribute("href");
      } else if (e.key === "Escape") { this.filter.value = ""; this.render(); this.filter.blur(); }
    });
    // mode « au survol » : la barre sort quand la souris touche le bord gauche, rentre quand elle s'en va
    this.edge.addEventListener("mouseenter", () => this.schedulePeek(true, 120));
    this.root.addEventListener("mouseenter", () => this.schedulePeek(true, 0));
    this.root.addEventListener("mouseleave", () => this.schedulePeek(false, 350));
    // en glissant un titre vers une playlist : la barre « au survol » sort au bord gauche, et rentre après le dépôt
    this.edge.addEventListener("dragenter", () => { if (Dnd.active()) this.schedulePeek(true, 0); });
    App.bus.on("dnd", dragging => { if (!dragging) this.schedulePeek(false, 600); });
    App.bus.on("preferences", () => this.applyMode());
    App.bus.on("route", () => this.highlight());
    App.live.on("artists", () => this.load(true));          // Subsonic a scanné : nouvelle liste, sans attendre
  }

  /** Subsonic peut mettre plus de 30 s à calculer la liste la première fois : on le dit, et on propose
      de réessayer en cas d'échec au lieu de laisser la barre vide. */
  async load(quiet) {
    if (!quiet) {
      App.clear(this.list);
      this.list.appendChild(App.el("p.sidebar-note", {text: App.t("nav.artists_loading")}));
    }
    try {
      const data = await App.api.get("/api/artists");
      this.index = data.index;
      this.showShortcuts(data.shortcuts || []);
      for (const group of this.index) group.artists.forEach(a => { a.key = ArtistSidebar.fold(a.name); });
    } catch (error) {
      if (quiet) return;                                     // on garde la liste affichée
      App.clear(this.list);
      this.list.appendChild(App.el("p.sidebar-note.error", {text: App.errorText(error)}));
      this.list.appendChild(App.el("button.sidebar-retry", {type: "button", text: App.t("nav.artists_retry"),
                                                           onclick: () => this.load()}));
      return;
    }
    const top = this.list.scrollTop;
    this.render();
    if (quiet) this.list.scrollTop = top;                    // la personne ne perd pas sa place
  }

  /** Dossiers épinglés en haut de la barre, toujours visibles (le filtre ne les cache pas). */
  showShortcuts(shortcuts) {
    App.clear(this.shortcuts);
    this.shortcuts.hidden = !shortcuts.length;
    for (const folder of shortcuts) {
      this.shortcuts.appendChild(App.setIcon(App.el("a.artist-shortcut", {href: "#/artist/" + encodeURIComponent(folder.id),
                                                                         dataset: {id: folder.id}}), "disc", 16, false, folder.name));
    }
    this.highlight();
  }

  applyMode() {
    const mode = App.preferences.sidebar || "pinned";
    document.body.dataset.sidebar = mode;
    document.documentElement.style.setProperty("--sidebar-width", (App.preferences.sidebar_width || 240) + "px");
    if (mode !== "hover") this.setPeek(false);
  }

  /** Raccourci et bouton ☰ : en mode fixe on masque, sinon on fait sortir la barre (ou on la rentre). */
  toggle() {
    const mode = App.preferences.sidebar || "pinned";
    if (mode === "pinned") App.savePreference("sidebar", "hidden");
    else if (mode === "hidden") App.savePreference("sidebar", "pinned");
    else { this.setPeek(!this.peeking); if (this.peeking) this.filter.focus(); }
  }

  schedulePeek(open, delay) {
    if ((App.preferences.sidebar || "pinned") !== "hover") return;
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.setPeek(open), delay);
  }

  setPeek(open) {
    this.peeking = open;
    this.root.classList.toggle("peek", open);
  }

  /** Affichage paresseux (grosse bibliothèque : des milliers d'artistes) : chaque lettre réserve sa place,
      ses artistes ne sont construits qu'à l'approche de l'écran, au clic sur la lettre ou pour l'artiste en cours.
      Sans IntersectionObserver (vieux navigateurs, jsdom) tout est construit d'un coup. */
  render() {
    const words = ArtistSidebar.fold(this.filter.value.trim());
    if (this.observer) this.observer.disconnect();
    this.observer = "IntersectionObserver" in window ? new IntersectionObserver(entries => entries.forEach(entry => {
      if (entry.isIntersecting) this.fill(entry.target);
    }), {root: this.list, rootMargin: "800px 0px"}) : null;
    this.groups = new Map();                                   // lettre -> {node, artists}
    App.clear(this.list);
    App.clear(this.letters);
    for (const group of this.index) {
      const artists = words ? group.artists.filter(a => a.key.includes(words)) : group.artists;
      if (!artists.length) continue;
      const node = App.el("div.letter-group");
      this.groups.set(group.letter, {node, artists});
      this.letters.appendChild(App.el("button.letter", {text: group.letter, onclick: () => {
        this.fill(node);
        node.previousSibling.scrollIntoView({block: "start"});
      }}));
      this.list.appendChild(App.el("h3.letter-head", {id: "letter-" + group.letter, text: group.letter}));
      this.list.appendChild(node);
      if (this.observer) {
        node.dataset.letter = group.letter;
        node.style.minHeight = artists.length * this.rowHeight + "px";      // place réservée : ascenseur juste
        this.observer.observe(node);
      } else {
        this.fill(node, group.letter);
      }
    }
    const first = this.groups.values().next().value;
    if (first) this.fill(first.node);                          // tout de suite : Entrée dans le filtre l'ouvre
    this.highlight();
  }

  fill(node, letter) {
    const group = this.groups.get(letter || node.dataset.letter);
    if (!group || node.dataset.filled) return;
    node.dataset.filled = "1";
    if (this.observer) this.observer.unobserve(node);
    for (const artist of group.artists) {          // dossiers d'artistes : Subsonic n'en donne pas le nombre d'albums
      node.appendChild(App.el("a.artist", {href: "#/artist/" + encodeURIComponent(artist.id), title: artist.name,
                                           dataset: {id: artist.id}},
        App.el("span.artist-name", {text: artist.name})));
    }
    node.style.minHeight = "";
    const row = node.firstChild;
    if (row && row.offsetHeight) this.rowHeight = row.offsetHeight;             // mesure réelle (densité)
  }

  /** Minuscules sans accents, pour le filtre. */
  static fold(text) {
    return String(text).toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  highlight() {
    const route = this.app.route || {};
    this.list.querySelectorAll("a.artist.current").forEach(a => a.classList.remove("current"));
    this.shortcuts.querySelectorAll("a").forEach(a => a.classList.toggle("current", !!route.artistId && a.dataset.id === route.artistId));
    const id = route.artistId || "";                // posé par la page artiste ou album (dossier de l'artiste)
    if (!id || !this.groups) return;
    for (const [letter, group] of this.groups) {                // la lettre de l'artiste doit être construite
      if (group.artists.some(a => a.id === id)) { this.fill(group.node, letter); break; }
    }
    const current = this.list.querySelector('a.artist[data-id="' + CSS.escape(id) + '"]');
    if (current) {
      current.classList.add("current");
      if (current.scrollIntoViewIfNeeded) current.scrollIntoViewIfNeeded(false);
    }
  }
}
