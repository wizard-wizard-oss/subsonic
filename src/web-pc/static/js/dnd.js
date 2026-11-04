"use strict";
/* Glisser-déposer de titres et d'albums vers les playlists de la barre de gauche.
   Une source (ligne de titre, pochette d'album) dit ce qu'elle porte ; une cible (playlist) dit si elle accepte.
   Ce qu'on glisse est gardé ici : le navigateur ne le montre pas aux cibles avant le dépôt. */

const Dnd = (() => {
  const TYPE = "application/x-pimedia-songs";
  let current = null;                                           // {songIds: [...]} ou {albumId}, et label

  function end() {
    if (!current) return;
    current = null;
    document.body.classList.remove("dragging-songs");
    App.bus.emit("dnd", false);
  }

  /** node devient glissable ; payload : objet, ou fonction qui le donne (null : on ne glisse rien). */
  function source(node, payload) {
    node.draggable = true;
    node.addEventListener("dragstart", event => {
      const what = typeof payload === "function" ? payload() : payload;
      if (!what) return;
      current = what;
      event.dataTransfer.effectAllowed = "copyMove";      // move : changer l'ordre d'une playlist
      event.dataTransfer.setData(TYPE, JSON.stringify(what));
      event.dataTransfer.setData("text/plain", what.label || "");
      document.body.classList.add("dragging-songs");
      App.bus.emit("dnd", true);
    });
    node.addEventListener("dragend", end);
  }

  /** node reçoit ce qu'on glisse si accepts() ; onDrop(payload) au dépôt. */
  function target(node, accepts, onDrop) {
    const over = event => {
      if (!current || !accepts()) return;
      event.preventDefault();                                   // sans cela, le navigateur refuse le dépôt
      event.dataTransfer.dropEffect = "copy";
      node.classList.add("drop-over");
    };
    node.addEventListener("dragenter", over);
    node.addEventListener("dragover", over);
    node.addEventListener("dragleave", event => {
      if (!node.contains(event.relatedTarget)) node.classList.remove("drop-over");
    });
    node.addEventListener("drop", event => {
      node.classList.remove("drop-over");
      if (!current || !accepts()) return;
      event.preventDefault();
      const dropped = current;
      end();
      onDrop(dropped);
    });
  }

  document.addEventListener("drop", end);                      // dépôt ailleurs, ou source retirée de la page
  document.addEventListener("dragend", end);
  return {source, target, active: () => !!current};
})();
