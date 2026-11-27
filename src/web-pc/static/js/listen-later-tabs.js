"use strict";
/* Onglets de la page À écouter : Reçues d'abord, pastille rouge quand un autre onglet est ouvert et qu'il y a du neuf. */
const ListenLaterTabs = (() => {
  const el = App.el, t = (key, params) => App.t("listen_later." + key, params);
  const ORDER = ["received", "bookmarks", "sent"];

  function panel(name, content) {
    return el("div.listen-later-panel", {role: "tabpanel", id: "listen-later-panel-" + name,
      "aria-labelledby": "listen-later-tab-" + name}, content);
  }

  function badge(unread) {
    return el("span.listen-later-tab-badge", {text: String(unread), title: t("unread_count", {count: unread})});
  }

  function tabButton(name, onSelect, extra) {
    return el("button.listen-later-tab", {type: "button", role: "tab", id: "listen-later-tab-" + name,
      "aria-controls": "listen-later-panel-" + name, dataset: {tab: name}, onclick: () => onSelect(name)},
      el("span", {text: t("tabs." + name)}), extra);
  }

  /**
   * contents : {received, bookmarks, sent} (nœuds) ; selected : onglet à ouvrir ; unread : nombre de conseils nouveaux.
   * onOpen(name) est appelé à chaque ouverture d'onglet (la lecture des conseils se déclenche sur « received »).
   */
  function build({contents, selected, unread, onOpen}) {
    const panels = {}, tabs = {}, mark = badge(unread);
    const select = (name, focus = false) => {
      ORDER.forEach(key => {
        panels[key].hidden = key !== name;
        tabs[key].classList.toggle("on", key === name);
        tabs[key].setAttribute("aria-selected", String(key === name));
        tabs[key].tabIndex = key === name ? 0 : -1;
      });
      mark.hidden = !unread || name === "received";
      if (focus) tabs[name].focus();
      onOpen(name);
    };
    const move = event => {
      const step = {ArrowRight: 1, ArrowLeft: -1}[event.key];
      if (!step) return;
      event.preventDefault();
      const current = ORDER.findIndex(key => tabs[key].classList.contains("on"));
      select(ORDER[(current + step + ORDER.length) % ORDER.length], true);
    };
    ORDER.forEach(name => {
      panels[name] = panel(name, contents[name]);
      tabs[name] = tabButton(name, select, name === "received" ? mark : null);
    });
    const list = el("div.listen-later-tabs", {role: "tablist", "aria-label": t("tabs_label"), onkeydown: move},
      ORDER.map(name => tabs[name]));
    return {list, panels: ORDER.map(name => panels[name]), select: () => select(selected)};
  }

  return {build};
})();
