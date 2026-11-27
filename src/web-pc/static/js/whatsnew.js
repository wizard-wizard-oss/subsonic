"use strict";
/* Help : catalogue de guides localisés, navigation locale et accès aux composants existants.
   Lire un guide ne change ni la lecture, ni les préférences, ni les données du compte. */

Views.whatsnew = (() => {
  const el = App.el, t = App.t;
  const THEMES = [
    {id: "listen", icon: "music", first: "g4"},
    {id: "social", icon: "chat", first: "g1"},
    {id: "explore", icon: "disc", first: "g7"},
    {id: "save", icon: "list", first: "g3"},
    {id: "elsewhere", icon: "play", first: "g1"},
    {id: "press", icon: "list", first: "g2"},
    {id: "settings", icon: "settings", first: "g1"},
  ];
  // Seules les destinations diffèrent des textes : les fiches musicales s'ouvrent après choix d'un album.
  const DESTINATIONS = {
    listen: {g1: "#/albums/newest", g2: "queue", g3: "queue", g4: "lyrics", g5: "shortcuts"},
    social: {g1: "chat", g2: "chat", g3: "chat", g4: "#/albums/newest", g5: "#/listen-later", g6: "#/listen-later"},
    explore: {g1: "#/albums/newest", g2: "search", g3: "#/albums/newest", g4: "#/mix",
      g5: "#/albums/newest", g6: "#/albums/newest", g7: "#/albums/newest"},
    save: {g1: "#/favorites", g2: "#/listen-later", g5: "#/import", g6: "#/favorites"},
    elsewhere: {g1: "search", g2: "#/favorites", g3: "#/favorites", g4: "#/favorites", g5: "search"},
    press: {g1: "#/news", g2: "#/news", g3: "#/news", g4: "#/albums/newest", g5: "#/news/releases"},
    settings: {g1: "settings", g2: "#/account", g3: "#/upload", g4: "#/albums/newest", g5: "#/account", g6: "#/account"},
  };
  const CAPTURES = {
    "listen.g1": "album", "listen.g4": "lyrics", "social.g1": "chat",
    "explore.g7": "labels", "save.g5": "import", "press.g2": "news",
  };

  function themeKey(theme) { return "whatsnew.themes." + theme; }
  function guideKey(theme, guide) { return themeKey(theme) + ".guides." + guide; }

  /** Le catalogue suit les traductions : aucun deuxième décompte des guides et de leurs étapes. */
  function guides(theme) {
    const prefix = themeKey(theme) + ".guides.";
    return Object.keys(App.texts).filter(key => key.startsWith(prefix) && key.endsWith(".title"))
      .map(key => key.slice(prefix.length, -".title".length))
      .sort((a, b) => a.localeCompare(b, undefined, {numeric: true}));
  }

  function openAction(action) {
    if (action === "chat") {
      App.chatPanel.show("room");
      // Le bouton commun laisse l'adaptateur mobile ouvrir son volet sans changer les réglages PC.
      const mobile = !!document.querySelector(".mobile-menu-tools");
      const open = mobile ? document.body.dataset.mobilePanel === "chat" : App.chatPanel.isOpen();
      if (!open) document.getElementById("toggle-chat").click();
      else if (App.lyrics.isOpen()) App.lyrics.close();
    } else if (action === "lyrics") App.lyrics.open();
    else if (action === "queue") App.queuePanel.open();
    else if (action === "shortcuts") Dialogs.shortcuts();
    else if (action === "settings") Dialogs.settings();
    else if (action === "search") document.getElementById("search").focus();
  }

  function actions(theme, guide) {
    const destination = (DESTINATIONS[theme] || {})[guide];
    const links = el("div.help-actions");
    if (destination) {
      links.appendChild(destination.startsWith("#/") ?
        el("a.whatsnew-link", {href: destination, text: t("whatsnew.open") + " →"}) :
        el("button.help-action", {type: "button", dataset: {action: destination},
          text: t("whatsnew.actions." + destination), onclick: () => openAction(destination)}));
    }
    if (theme === "save" && guide === "g5") {
      links.appendChild(el("a.whatsnew-link", {href: "#/import/guide", text: t("whatsnew.import_guide") + " →"}));
    }
    return links;
  }

  const reveal = target => {
    target.focus({preventScroll: true});
    if (target.scrollIntoView) target.scrollIntoView({block: "nearest"});
  };

  /* La page Help : thèmes, guides du thème choisi et leçon du guide choisi. */
  class HelpPage {
    constructor(main) {
      this.main = main;
      this.themes = el("nav.help-themes", {"aria-label": t("whatsnew.themes_label")});
      this.title = el("h3", {id: "help-theme-title", tabIndex: -1});
      this.description = el("p");
      this.choices = el("div.help-guide-list", {role: "group", "aria-label": t("whatsnew.guides_label")});
      this.lesson = el("article.help-lesson", {id: "help-lesson", "aria-labelledby": "help-guide-title"});
      this.panel = el("section.help-panel", {id: "help-panel", "aria-labelledby": "help-theme-title"},
        el("div.help-panel-heading", {}, this.title, this.description), this.choices, this.lesson);
      this.themeButtons = new Map();
    }

    lessonBody(theme, guide, key) {
      const capture = CAPTURES[theme + "." + guide];
      const body = el("div.help-lesson-body" + (capture ? ".has-illustration" : ""), {},
        el("ol.help-steps", {"aria-label": t("whatsnew.steps_label")}, (App.texts[key + ".steps"] || []).map(text => el("li", {text}))));
      if (capture) {
        // Cadre de hauteur fixe recadré en haut (certaines captures sont au format téléphone) ; un clic ouvre l'image entière.
        const src = "/static/help/" + capture + ".png";
        body.appendChild(el("figure.help-illustration", {},
          el("a.help-illustration-frame", {href: src, target: "_blank", rel: "noopener", title: t("whatsnew.illustration_open")},
            el("img", {src, alt: t(key + ".title"), loading: "lazy", decoding: "async"})),
          el("figcaption", {text: t("whatsnew.illustration_label")})));
      }
      return body;
    }

    selectGuide(theme, guide) {
      for (const button of this.choices.children) button.setAttribute("aria-pressed", String(button.dataset.guide === guide));
      const key = guideKey(theme, guide);
      const note = App.texts[key + ".note"] !== undefined ? t(key + ".note") : "";   // App.t rend la clé si le texte manque
      App.append(App.clear(this.lesson), [el("p.kicker", {text: t("whatsnew.steps_label")}),
        el("h4", {id: "help-guide-title", tabIndex: -1, "aria-live": "polite", text: t(key + ".title")}),
        this.lessonBody(theme, guide, key), el("p.help-note", {text: note, hidden: !note}), actions(theme, guide)]);
    }

    selectTheme(theme, guide) {
      for (const [id, button] of this.themeButtons) button.setAttribute("aria-pressed", String(id === theme.id));
      this.title.textContent = t(themeKey(theme.id) + ".title");
      this.description.textContent = t(themeKey(theme.id) + ".description");
      App.clear(this.choices);
      for (const id of guides(theme.id)) {
        this.choices.appendChild(el("button.help-guide-button", {type: "button", dataset: {guide: id},
          "aria-controls": "help-lesson", onclick: () => {
            this.selectGuide(theme.id, id);
            const bounds = this.lesson.getBoundingClientRect(), visible = this.main.getBoundingClientRect();
            if (bounds.top > visible.bottom) reveal(this.lesson.querySelector("h4"));
          }},
          App.icon("next", 12), el("span", {text: t(guideKey(theme.id, id) + ".title")})));
      }
      this.selectGuide(theme.id, guide || theme.first);
    }

    themeButton(theme) {
      const key = themeKey(theme.id);
      const button = el("button.help-theme", {type: "button", dataset: {theme: theme.id},
        "aria-controls": "help-panel", onclick: () => {
          this.selectTheme(theme);
          const navigation = this.themes.getBoundingClientRect();
          if (navigation.width && this.panel.getBoundingClientRect().top >= navigation.bottom) reveal(this.title);
        }}, App.icon(theme.icon, 20),
        el("span.help-theme-copy", {}, el("span.help-theme-title", {text: t(key + ".title")}),
          el("span.help-theme-summary", {text: t(key + ".summary")})), App.icon("next", 12));
      this.themeButtons.set(theme.id, button);
      return button;
    }

    /** Ouvre un guide depuis l'accueil (pilier, espace, recherche) et l'amène à l'écran. */
    pick(themeId, guide) {
      this.selectTheme(THEMES.find(theme => theme.id === themeId), guide);
      reveal(this.lesson.querySelector("h4"));
    }

    searchEntries() {
      return THEMES.flatMap(theme => guides(theme.id).map(guide =>
        HelpSearch.entry(theme.id, guide, guideKey(theme.id, guide), t(themeKey(theme.id) + ".title"))));
    }

    show(route) {
      App.append(this.themes, THEMES.map(theme => this.themeButton(theme)));
      const deps = {open: (theme, guide) => this.pick(theme, guide), run: openAction, reveal,
        search: HelpSearch.create(this.searchEntries(), (theme, guide) => this.pick(theme, guide))};
      const page = el("div.help-page", {}, HelpHome.top(deps),
        el("section.help-guides", {"aria-labelledby": "help-guides-title"},
          el("h2.help-plain-title", {id: "help-guides-title", text: t("whatsnew.themes_title")}),
          el("div.help-browser", {}, this.themes, this.panel)),
        HelpHome.bottom(),
        el("p.help-footer", {text: t("whatsnew.footer")}));
      App.clear(this.main).appendChild(page);
      const [themeId, guideId] = (route.id || "").split("/");
      const theme = THEMES.find(item => item.id === themeId) || THEMES[0];
      this.selectTheme(theme, guides(theme.id).includes(guideId) ? guideId : undefined);
    }
  }

  function render(main, route = {}) {
    new HelpPage(main).show(route);
  }

  return {render};
})();
