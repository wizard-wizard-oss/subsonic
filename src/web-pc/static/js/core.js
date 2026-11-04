"use strict";
/* Socle de la page : textes (i18n), appels au serveur, création d'éléments, petits formats, messages. */

const App = {
  texts: {},
  user: null,
  preferences: {},
  usernames: [],
  reactions: [],
};

/* ---------- textes ---------- */
App.t = function (key, params) {
  let text = App.texts[key];
  if (text === undefined) return key;          // clé absente : visible à l'écran, facile à repérer
  if (params) text = text.replace(/\{(\w+)\}/g, (all, name) => (name in params ? String(params[name]) : all));
  return text;
};

/** Texte au singulier ou au pluriel : clé « x_one » pour 1, « x » sinon (avec {count}). */
App.plural = function (key, count, params) {
  const one = key + "_one";
  return App.t(count === 1 && App.texts[one] !== undefined ? one : key, Object.assign({count}, params || {}));
};

/** Remplit les éléments marqués data-t (texte), data-t-title et data-t-placeholder. */
App.translate = function (root) {
  (root || document).querySelectorAll("[data-t]").forEach(node => { node.textContent = App.t(node.dataset.t); });
  (root || document).querySelectorAll("[data-t-title]").forEach(node => {
    node.title = App.t(node.dataset.tTitle);
    node.setAttribute("aria-label", node.title);
  });
  (root || document).querySelectorAll("[data-t-placeholder]").forEach(node => {
    node.placeholder = App.t(node.dataset.tPlaceholder);
  });
};

/* ---------- serveur ---------- */
class ApiError extends Error {
  constructor(status, code) {
    super(code);
    this.status = status;
    this.code = code;
  }
}

/** Texte à afficher pour une erreur du serveur (clé envoyée par le serveur, ex. « chat.too_fast »). */
/** Le compte Subsonic a-t-il ce droit (« stream », « download », « playlist », « comment »…) ? */
App.can = function (right) {
  return !!(App.user && App.user.roles && App.user.roles.includes(right));
};

App.errorText = function (error) {
  const special = {"subsonic.error": "errors.subsonic", "subsonic.unreachable": "errors.unreachable",
                   "request.invalid": "errors.invalid", "server.error": "errors.server", "chat.empty": "chat.empty_message"};
  if (!(error instanceof ApiError)) return App.t("errors.network");
  return App.t(special[error.code] || error.code);
};

App.api = {
  async request(method, path, body) {
    const options = {method, credentials: "same-origin", headers: {}};
    if (method !== "GET") {
      options.headers["X-Requested-With"] = "pmw";       // protection CSRF : demandé par le serveur
      options.headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body || {});
    }
    let response;
    try {
      response = await fetch(path, options);
    } catch (e) {
      throw new ApiError(0, "network");
    }
    let data = {};
    try { data = await response.json(); } catch (e) { /* réponse vide */ }
    if (!response.ok) {
      const error = new ApiError(response.status, data.error || "server.error");
      if (response.status === 401 && path !== "/api/login") App.onSessionLost(error);
      throw error;
    }
    return data;
  },
  get(path, params) {
    const query = params ? "?" + new URLSearchParams(params).toString() : "";
    return this.request("GET", path + query);
  },
  post(path, body) { return this.request("POST", path, body); },
};
App.onSessionLost = function () {};        // remplacé par app.js

/* ---------- éléments ---------- */
/**
 * el("div.card", {onclick: f, title: "x"}, enfant, "texte", [autres])
 * Aucun HTML n'est jamais interprété : le texte passe par des nœuds texte (pas d'injection possible).
 */
App.el = function (spec, props, ...children) {
  const [tag, ...classes] = spec.split(".");
  const node = document.createElement(tag || "div");
  if (classes.length) node.className = classes.join(" ");
  for (const [key, value] of Object.entries(props || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key === "text") node.textContent = value;
    else if (key in node && key !== "list") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  App.append(node, children);
  return node;
};
App.append = function (node, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    node.appendChild(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
};
App.clear = function (node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
};

/** Pochette Subsonic (relayée par le site) ou image d'un titre d'ailleurs (adresse https de Jamendo, YouTube). */
App.coverUrl = (id, size) => !id ? "" : /^https:\/\//.test(id) ? id : "/api/cover?" + new URLSearchParams({id, size: size || 300});

App.cover = function (id, size, alt) {
  const img = App.el("img.cover", {alt: alt || "", loading: "lazy", width: size, height: size});
  const empty = () => { img.removeAttribute("src"); img.alt = ""; img.classList.add("empty"); };
  if (id) img.src = App.coverUrl(id, size * 2 > 600 ? 600 : size * 2);
  else empty();
  img.addEventListener("error", empty, {once: true});
  return img;
};

/* ---------- formats ---------- */
App.duration = function (seconds) {
  seconds = Math.max(0, Math.round(seconds || 0));
  const h = Math.floor(seconds / 3600), m = Math.floor(seconds % 3600 / 60), s = seconds % 60;
  return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(s).padStart(2, "0");
};
App.time = epoch => new Date(epoch * 1000).toLocaleTimeString("fr-FR", {hour: "2-digit", minute: "2-digit"});
App.fullDate = epoch => new Date(epoch * 1000).toLocaleString("fr-FR", {dateStyle: "full", timeStyle: "short"});
App.dayLabel = function (epoch) {
  const day = new Date(epoch * 1000), today = new Date();
  const start = d => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const diff = Math.round((start(today) - start(day)) / 86400000);
  if (diff === 0) return App.t("chat.today");
  if (diff === 1) return App.t("chat.yesterday");
  return day.toLocaleDateString("fr-FR", {weekday: "long", day: "numeric", month: "long",
                                         year: day.getFullYear() === today.getFullYear() ? undefined : "numeric"});
};

/** Couleur stable par nom (pastille des messages). */
App.colorOf = function (name) {
  let hash = 0;
  for (const c of name || "") hash = (hash * 31 + c.charCodeAt(0)) | 0;
  return "hsl(" + (Math.abs(hash) % 360) + ", 55%, 45%)";
};

/* ---------- messages furtifs ---------- */
/** Message passager ; action facultative {label, run} : un bouton, et le message reste plus longtemps. */
App.toast = function (text, kind, action) {
  const box = document.getElementById("toasts");
  const toast = App.el("div.toast" + (kind ? "." + kind : ""), {role: "status"}, App.el("span", {text}),
    action ? App.el("button.link-button.toast-action", {type: "button", text: action.label,
                                                        onclick: () => { action.run(); toast.remove(); }}) : null);
  box.appendChild(toast);
  const shown = action ? 9000 : 3200;
  setTimeout(() => toast.classList.add("leaving"), shown);
  setTimeout(() => toast.remove(), shown + 400);
};

/* ---------- petit bus d'événements de la page ---------- */
App.bus = {
  listeners: {},
  on(name, fn) { (this.listeners[name] = this.listeners[name] || []).push(fn); return () => this.off(name, fn); },
  off(name, fn) { this.listeners[name] = (this.listeners[name] || []).filter(f => f !== fn); },
  emit(name, data) { (this.listeners[name] || []).slice().forEach(fn => fn(data)); },
};

/* ---------- réglages ---------- */
App.savePreference = async function (key, value) {
  App.preferences[key] = value;
  App.bus.emit("preferences", App.preferences);
  try {
    App.preferences = (await App.api.post("/api/preferences", {changes: {[key]: value}})).preferences;
  } catch (error) {
    App.toast(App.errorText(error), "error");
  }
};

/** Mémoire locale du navigateur (volume…) : peut être indisponible, la page marche sans. */
App.local = {
  get(key, fallback) {
    try { const v = localStorage.getItem("pmw." + key); return v === null ? fallback : JSON.parse(v); }
    catch (e) { return fallback; }
  },
  set(key, value) { try { localStorage.setItem("pmw." + key, JSON.stringify(value)); } catch (e) { /* rien */ } },
};
