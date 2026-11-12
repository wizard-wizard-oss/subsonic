"use strict";
/* Fenêtres : réglages rapides, aide des raccourcis, confirmation, saisie d'un nom. Une seule à la fois ; Échap ou clic à côté ferme. */

const Dialogs = (() => {
  const el = App.el;
  let current = null;

  function open(title, content, onClose) {
    close();
    const root = document.getElementById("dialog-root");
    const box = el("div.dialog", {role: "dialog", "aria-modal": "true", "aria-label": title},
      el("header.dialog-head", {}, el("h2", {text: title}),
         el("button.icon-button", {type: "button", title: App.t("settings.close"), onclick: () => close()}, App.icon("close", 18))),
      content);
    const veil = el("div.veil", {onmousedown: e => { if (e.target === veil) close(); }}, box);
    root.appendChild(veil);
    current = {veil, onClose};
    const focusable = box.querySelector("input, select, button.primary, button");
    if (focusable) focusable.focus();
    return box;
  }

  function close() {
    if (!current) return false;
    const {veil, onClose} = current;
    current = null;
    veil.remove();
    if (onClose) onClose();
    return true;
  }

  function choice(label, key, values) {
    const select = el("select", {onchange: () => {
      const raw = select.value;
      const value = typeof values[0][0] === "number" ? Number(raw) : raw;
      App.savePreference(key, value);
    }}, values.map(([value, text]) => el("option", {value: String(value), text, selected: App.preferences[key] === value})));
    return el("label.setting", {}, el("span", {text: label}), select);
  }

  function toggle(label, key, onEnable) {
    const box = el("input", {type: "checkbox", checked: !!App.preferences[key], onchange: () => {
      App.savePreference(key, box.checked);
      if (box.checked && onEnable) onEnable();
    }});
    return el("label.setting.check", {}, box, el("span", {text: label}));
  }

  /** Réglages rapides (roue dentée) : l'affichage, les droits, et le lien vers la page « Mon compte ». */
  function settings() {
    open(App.t("settings.title"), el("div.settings", {}, display(), rights(),
      el("a.settings-listen-later", {href: "#/listen-later", text: App.t("nav.listen_later") + " →", onclick: () => close()}),
      el("a.settings-account", {href: "#/account", text: App.t("nav.account") + " →", onclick: () => close()})));
  }

  /** Réglages d'affichage, propres à chacun (aussi sur la page « Mon compte »). */
  function display() {
    const t = App.t;
    return [
      choice(t("settings.sidebar"), "sidebar", [["pinned", t("settings.sidebar_pinned")], ["hover", t("settings.sidebar_hover")],
                                                 ["hidden", t("settings.sidebar_hidden")]]),
      choice(t("settings.sidebar_width"), "sidebar_width", [[200, "200 px"], [240, "240 px"], [280, "280 px"], [320, "320 px"]]),
      choice(t("settings.chat_panel"), "chat_panel", [["open", "✓"], ["closed", "—"]]),
      choice(t("settings.density"), "density", [["comfortable", t("settings.density_comfortable")], ["compact", t("settings.density_compact")]]),
      choice(t("settings.album_grid"), "album_grid", [["large", t("settings.album_grid_large")], ["small", t("settings.album_grid_small")]]),
      toggle(t("settings.notify_mentions"), "notify_mentions", () => {
        if (typeof Notification !== "undefined" && Notification.permission === "default") Notification.requestPermission();
      })];
  }

  /** Ce que le compte Subsonic permet sur le site (réglé par l'administrateur, dans Subsonic). */
  function rights() {
    const shown = ["stream", "download", "playlist", "comment", "share", "upload", "coverArt", "admin"];
    return el("section.setting.rights", {},
      el("h3", {text: App.t("settings.rights")}),
      el("ul.rights-list", {}, shown.map(right => el("li" + (App.can(right) ? ".yes" : ".no"), {},
        el("span.mark", {text: App.can(right) ? "✓" : "—"}), el("span", {text: App.t("rights." + right)})))),
      el("p.muted", {text: App.t("settings.rights_help")}));
  }

  function shortcuts() {
    const rows = [["Espace", "shortcuts.play"], ["N", "shortcuts.next"], ["P", "shortcuts.previous"],
                  ["← / →", "shortcuts.seek"], ["/", "shortcuts.search"], ["A", "shortcuts.sidebar"],
                  ["C", "shortcuts.chat"], ["L", "shortcuts.lyrics"], ["?", "shortcuts.help"], ["Échap", "shortcuts.close"]];
    open(App.t("shortcuts.title"), el("table.shortcuts", {}, el("tbody", {}, rows.map(([key, text]) =>
      el("tr", {}, el("td", {}, el("kbd", {text: key})), el("td", {text: App.t(text)}))))));
  }

  function confirm(question) {
    return new Promise(resolve => {
      let answered = false;
      const answer = value => { answered = true; close(); resolve(value); };
      open(question, el("div.dialog-buttons", {},
        el("button", {type: "button", text: App.t("chat.cancel"), onclick: () => answer(false)}),
        el("button.primary.danger", {type: "button", text: App.t("chat.delete"), onclick: () => answer(true)})),
        () => { if (!answered) resolve(false); });
    });
  }

  /** Demande un texte (nom d'une playlist…) : le texte saisi, ou null si on annule. */
  function ask(question, value) {
    return new Promise(resolve => {
      let answered = false;
      const input = el("input.dialog-input", {type: "text", value: value || "", maxLength: 100});
      const answer = text => { answered = true; close(); resolve(text); };
      const submit = () => { if (input.value.trim()) answer(input.value.trim()); };
      input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); submit(); } });
      open(question, el("div.dialog-ask", {}, input, el("div.dialog-buttons", {},
        el("button", {type: "button", text: App.t("chat.cancel"), onclick: () => answer(null)}),
        el("button.primary", {type: "button", text: App.t("mix.save_ok"), onclick: submit}))),
        () => { if (!answered) resolve(null); });
      input.select();
    });
  }

  /** Nouvelle playlist : son nom, et si elle est communautaire. {name, community}, ou null si on annule. */
  function newPlaylist(suggested) {
    return new Promise(resolve => {
      let answered = false;
      const input = el("input.dialog-input", {type: "text", value: suggested || "", maxLength: 100,
                                              placeholder: App.t("playlist.name")});
      const community = el("input", {type: "checkbox"});
      const answer = value => { answered = true; close(); resolve(value); };
      const submit = () => { if (input.value.trim()) answer({name: input.value.trim(), community: community.checked}); };
      input.addEventListener("keydown", e => { if (e.key === "Enter") { e.preventDefault(); submit(); } });
      open(App.t("playlist.new"), el("div.dialog-ask", {}, input,
        el("label.setting.check", {}, community, el("span", {text: App.t("playlist.community_help")})),
        el("div.dialog-buttons", {},
          el("button", {type: "button", text: App.t("chat.cancel"), onclick: () => answer(null)}),
          el("button.primary", {type: "button", text: App.t("playlist.create"), onclick: submit}))),
        () => { if (!answered) resolve(null); });
      input.select();
    });
  }

  return {open, close, settings, display, rights, shortcuts, confirm, ask, newPlaylist, isOpen: () => !!current};
})();
