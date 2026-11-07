"use strict";
/* Icônes en SVG (dessinées ici, 24x24) : nettes à toutes les tailles et identiques sur tous les systèmes,
   contrairement aux caractères spéciaux qui dépendent des polices installées. */

const ICONS = {
  play: "M8 5v14l11-7z",
  pause: "M7 5h4v14H7zM13 5h4v14h-4z",
  previous: "M6 5h2v14H6zM9.5 12L19 5v14z",
  next: "M16 5h2v14h-2zM14.5 12L5 19V5z",
  radio: "M8.5 8.5a5 5 0 0 0 0 7M15.5 8.5a5 5 0 0 1 0 7M5.5 5.5a9 9 0 0 0 0 13M18.5 5.5a9 9 0 0 1 0 13M12 12h.01",
  shuffle: "M4 7h3.5l7 10H20M4 17h3.5l2.3-3.3M14.5 7H20M17 4l3 3-3 3M17 14l3 3-3 3",
  plus: "M12 5v14M5 12h14",
  heart: "M12 20s-7-4.4-9.2-9A5 5 0 0 1 12 6a5 5 0 0 1 9.2 5C19 15.6 12 20 12 20z",
  chat: "M4 5h16v11H9l-5 4z",
  volume: "M4 9h4l5-4v14l-5-4H4zM16 9a4 4 0 0 1 0 6M18.5 6.5a8 8 0 0 1 0 11",
  more: "M5 12h.01M12 12h.01M19 12h.01",
  list: "M4 6h16M4 12h16M4 18h16",
  reply: "M10 8L5 12l5 4M5 12h9a5 5 0 0 1 5 5v1",
  edit: "M4 20h4L19 9l-4-4L4 16zM13.5 6.5l4 4",
  trash: "M5 7h14M10 7V4h4v3M7 7l1 13h8l1-13",
  smile: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM8.5 14a4.5 4.5 0 0 0 7 0M9 10h.01M15 10h.01",
  close: "M6 6l12 12M18 6L6 18",
  down: "M12 5v14M6 13l6 6 6-6",
  download: "M12 4v11M7 10l5 5 5-5M5 20h14",
  undo: "M9 6L4 11l5 5M4 11h10a5 5 0 0 1 0 10h-3",
  settings: "M12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6zM12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1",
  mic: "M12 3a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4M9 21h6",
  disc: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM12 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4z",
  help: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zM9.5 9.5a2.5 2.5 0 1 1 3.5 2.3c-.6.3-1 .9-1 1.6V14M12 17h.01",
};
const FILLED = new Set(["play", "pause", "previous", "next"]);

/** App.icon("play", 18) : élément <svg> (filled = icône pleine, ex. cœur des favoris). */
App.icon = function (name, size, filled) {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("width", size || 18);
  svg.setAttribute("height", size || 18);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("class", "icon");
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", ICONS[name] || "");
  const solid = filled || FILLED.has(name);
  path.setAttribute("fill", solid ? "currentColor" : "none");
  path.setAttribute("stroke", solid ? "none" : "currentColor");
  path.setAttribute("stroke-width", "2");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.appendChild(path);
  return svg;
};

/** Remplace le contenu d'un bouton par une icône (et un texte facultatif). */
App.setIcon = function (button, name, size, filled, text) {
  App.clear(button);
  button.appendChild(App.icon(name, size, filled));
  if (text) button.appendChild(App.el("span", {text}));
  return button;
};

/** Les boutons de la page marqués data-icon reçoivent leur icône au démarrage. */
App.placeIcons = function (root) {
  (root || document).querySelectorAll("[data-icon]").forEach(node => App.setIcon(node, node.dataset.icon, 20));
};
