"use strict";
/* File d'attente : panneau sur toute la largeur, au-dessus du lecteur (comme dans Subsonic). Il s'ouvre quand la
   souris reste sur le lecteur (ou bouton ☰), se ferme quand on clique ailleurs, quand la souris repart au-dessus
   ou avec Échap. Réordonner : glisser la poignée ⋮⋮, ou Alt+↑ / Alt+↓ sur une ligne. */

class QueuePanel {
  constructor(player) {
    const el = App.el, t = App.t;
    this.player = player;
    this.isOpen = false;
    this.dragFrom = -1;
    this.leaveTimer = null;
    this.count = el("span.queue-count");
    this.clearButton = App.setIcon(el("button.link-button", {type: "button", onclick: () => player.clearUpcoming()}),
                                   "trash", 14, false, t("player.clear"));
    this.undoButton = App.setIcon(el("button.link-button", {type: "button", onclick: () => player.undo()}),
                                  "undo", 14, false, t("player.undo"));
    this.body = el("tbody");
    const columns = ["", "#", "cover", "title", "album", "artist", "duration", "genre", "year", "format", ""];
    this.root = el("section.queue-drawer", {id: "queue", hidden: true, "aria-label": t("player.queue")},
      el("header.queue-head", {},
        el("h2", {text: t("player.queue")}), this.count,
        el("div.queue-actions", {}, this.clearButton, this.undoButton),
        el("button.icon-button", {type: "button", title: t("settings.close"), onclick: () => this.close()},
           App.icon("close", 16))),
      el("div.queue-scroll", {},
        el("table.queue-table", {},
          el("thead", {}, el("tr", {}, columns.map(c =>
            el("th.col-" + (c === "#" ? "num" : c || "tool"), {text: c === "cover" ? "" : c && c !== "#" ? t("queue_cols." + c) : c})))),
          this.body)));
    document.body.appendChild(this.root);
    // la souris repart au-dessus du panneau (ni sur lui, ni sur le lecteur) : on ferme, sans précipitation
    this.root.addEventListener("mouseenter", () => this.stay());
    this.root.addEventListener("mouseleave", () => this.leaveSoon());
    document.addEventListener("mousedown", event => {
      if (this.isOpen && !this.root.contains(event.target) && !this.inPlayer(event.target)) this.close();
    });
    App.bus.on("queue", () => this.render());
  }

  inPlayer(node) {
    const bar = document.getElementById("player");
    return !!(bar && node && bar.contains(node));
  }

  open() {
    if (this.isOpen) return;
    this.isOpen = true;
    this.root.hidden = false;
    document.body.dataset.queue = "open";
    this.render();
    App.bus.emit("queue-panel", true);
  }

  /** true si le panneau était ouvert (Échap s'arrête là). */
  close() {
    if (!this.isOpen) return false;
    this.stay();
    this.isOpen = false;
    this.root.hidden = true;
    delete document.body.dataset.queue;
    App.bus.emit("queue-panel", false);
    return true;
  }

  toggle() { if (this.isOpen) this.close(); else this.open(); }

  stay() { clearTimeout(this.leaveTimer); }

  /** Appelé aussi par le lecteur quand la souris le quitte ; jamais pendant un glisser-déposer. */
  leaveSoon() {
    this.stay();
    if (!this.isOpen || this.dragFrom >= 0) return;
    this.leaveTimer = setTimeout(() => this.close(), 600);
  }

  render() {
    if (!this.isOpen) return;
    const el = App.el, player = this.player, songs = player.queue;
    const total = songs.reduce((sum, song) => sum + (song.duration || 0), 0);
    this.count.textContent = songs.length ? App.plural("album.tracks", songs.length) + " • " + App.duration(total) : "";
    this.clearButton.disabled = player.index + 1 >= songs.length;
    this.undoButton.disabled = !player.canUndo;
    App.clear(this.body);
    if (!songs.length) {
      this.body.appendChild(el("tr.empty", {}, el("td", {colSpan: 11, text: App.t("player.queue_empty")})));
      return;
    }
    songs.forEach((song, i) => this.body.appendChild(this.row(song, i)));
  }

  row(song, i) {
    const el = App.el, player = this.player, current = i === player.index;
    const row = el("tr.queue-row" + (current ? ".current" : ""), {
      draggable: "true", tabIndex: 0, dataset: {index: i},
      ondblclick: () => player.load(i),
      onkeydown: e => this.onKey(e, i),
      ondragstart: e => this.dragStart(e, i, row), ondragover: e => this.dragOver(e, row),
      ondragleave: () => row.classList.remove("drop-before", "drop-after"),
      ondrop: e => this.drop(e, i, row), ondragend: () => this.dragEnd()},
      el("td.col-grip", {title: App.t("player.drag"), text: "⋮⋮"}),
      el("td.col-num", {}, current ? App.icon(player.playing ? "volume" : "play", 14) : String(i + 1)),
      el("td.col-cover", {}, App.cover(song.coverId || song.imageUrl, 32)),
      el("td.col-title", {text: song.title}),
      el("td.col-album", {}, song.albumId
        ? el("a", {href: "#/album/" + encodeURIComponent(song.albumId), text: song.album || ""}) : (song.album || "")),
      el("td.col-artist", {text: song.artist || ""}),
      el("td.col-duration", {text: song.duration ? App.duration(song.duration) : ""}),
      el("td.col-genre", {text: song.genre || ""}),
      el("td.col-year", {text: song.year || ""}),
      el("td.col-format", {text: QueuePanel.format(song)}),
      el("td.col-tool", {}, current ? null : App.setIcon(el("button.link-button", {type: "button",
        title: App.t("player.remove"), onclick: e => { e.stopPropagation(); player.removeAt(i); }}), "close", 14)));
    return row;
  }

  /** « FLAC 1 024 kbps », « YouTube », « Jamendo ». */
  static format(song) {
    if (song.ext) return song.ext === "youtube" ? "YouTube" : "Jamendo";
    return [(song.suffix || "").toUpperCase(), song.bitRate ? song.bitRate + " kbps" : ""].filter(Boolean).join(" ");
  }

  onKey(event, i) {
    const player = this.player;
    if (event.altKey && (event.key === "ArrowUp" || event.key === "ArrowDown")) {
      event.preventDefault();
      event.stopPropagation();
      const to = i + (event.key === "ArrowUp" ? -1 : 1);
      player.move(i, to);
      const moved = this.body.querySelector('tr[data-index="' + Math.max(0, Math.min(to, player.queue.length - 1)) + '"]');
      if (moved) moved.focus();
    } else if (event.key === "Enter") {
      player.load(i);
    } else if (event.key === "Delete" || event.key === "Backspace") {
      player.removeAt(i);
    }
  }

  // --- glisser-déposer ---
  dragStart(event, i, row) {
    this.dragFrom = i;
    this.stay();
    row.classList.add("dragging");
    if (event.dataTransfer) {
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", String(i));
    }
  }

  dragOver(event, row) {
    if (this.dragFrom < 0) return;
    event.preventDefault();
    const after = QueuePanel.isAfter(event, row);
    row.classList.toggle("drop-after", after);
    row.classList.toggle("drop-before", !after);
  }

  drop(event, i, row) {
    if (this.dragFrom < 0) return;
    event.preventDefault();
    let to = QueuePanel.isAfter(event, row) ? i + 1 : i;
    if (this.dragFrom < to) to--;                              // la ligne déplacée libère sa place
    const from = this.dragFrom;
    this.dragEnd();
    this.player.move(from, to);
  }

  dragEnd() {
    this.dragFrom = -1;
    this.body.querySelectorAll(".dragging, .drop-before, .drop-after")
      .forEach(row => row.classList.remove("dragging", "drop-before", "drop-after"));
  }

  /** Dépôt sous la ligne visée si la souris est dans sa moitié basse. */
  static isAfter(event, row) {
    const box = row.getBoundingClientRect();
    return event.clientY > box.top + box.height / 2;
  }
}
