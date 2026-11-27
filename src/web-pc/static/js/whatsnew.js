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
  const FEATURES = [
    {id: "chat", label: "nav.chat", theme: "social", guide: "g1", icon: "chat"},
    {id: "lyrics", label: "lyrics.title", theme: "listen", guide: "g4", icon: "mic"},
    {id: "press", label: "nav.news", theme: "press", guide: "g2", icon: "list"},
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

  function preview(feature) {
    const key = "whatsnew.preview.";
    const box = el("div.help-feature-preview.help-preview-" + feature, {"aria-hidden": "true"});
    if (feature === "chat") {
      for (const [name, icon] of [["chat_question", "chat"], ["chat_answer", "disc"]]) {
        box.appendChild(el("div.help-preview-message", {},
          el("span.help-preview-avatar", {}, App.icon(icon, 16)), el("p", {text: t(key + name)})));
      }
    } else if (feature === "lyrics") {
      for (const name of ["lyrics_previous", "lyrics_current", "lyrics_next"]) {
        box.appendChild(el("p" + (name === "lyrics_current" ? ".is-sung" : ""), {text: t(key + name)}));
      }
    } else {
      App.append(box, [el("p.help-preview-source", {text: t(key + "press_source")}),
        el("p", {text: t(key + "press_title")}), el("p.help-preview-path", {text: t(key + "press_path")})]);
    }
    return box;
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

  function render(main, route = {}) {
    const page = el("div.help-page");
    const themes = el("nav.help-themes", {"aria-label": t("whatsnew.themes_label")});
    const title = el("h3", {id: "help-theme-title", tabIndex: -1});
    const description = el("p");
    const choices = el("div.help-guide-list", {role: "group", "aria-label": t("whatsnew.guides_label")});
    const lesson = el("article.help-lesson", {id: "help-lesson", "aria-labelledby": "help-guide-title"});
    const panel = el("section.help-panel", {id: "help-panel", "aria-labelledby": "help-theme-title"},
      el("div.help-panel-heading", {}, title, description), choices, lesson);
    const themeButtons = new Map();

    function reveal(target) {
      target.focus({preventScroll: true});
      if (target.scrollIntoView) target.scrollIntoView({block: "nearest"});
    }

    function selectGuide(theme, guide) {
      for (const button of choices.children) button.setAttribute("aria-pressed", String(button.dataset.guide === guide));
      const key = guideKey(theme, guide);
      const steps = App.texts[key + ".steps"] || [];
      const capture = CAPTURES[theme + "." + guide];
      const body = el("div.help-lesson-body" + (capture ? ".has-illustration" : ""), {},
        el("ol.help-steps", {"aria-label": t("whatsnew.steps_label")}, steps.map(text => el("li", {text}))));
      if (capture) {
        body.appendChild(el("figure.help-illustration", {},
          el("img", {src: "/static/help/" + capture + ".png", alt: t(key + ".title"), loading: "lazy", decoding: "async"}),
          el("figcaption", {text: t("whatsnew.illustration_label")})));
      }
      const note = t(key + ".note");
      App.append(App.clear(lesson), [el("p.kicker", {text: t("whatsnew.steps_label")}),
        el("h4", {id: "help-guide-title", tabIndex: -1, "aria-live": "polite", text: t(key + ".title")}),
        body, el("p.help-note", {text: note, hidden: !note}), actions(theme, guide)]);
    }

    function selectTheme(theme, guide) {
      for (const [id, button] of themeButtons) button.setAttribute("aria-pressed", String(id === theme.id));
      title.textContent = t(themeKey(theme.id) + ".title");
      description.textContent = t(themeKey(theme.id) + ".description");
      App.clear(choices);
      for (const id of guides(theme.id)) {
        choices.appendChild(el("button.help-guide-button", {type: "button", dataset: {guide: id},
          "aria-controls": "help-lesson", onclick: () => {
            selectGuide(theme.id, id);
            const bounds = lesson.getBoundingClientRect(), visible = main.getBoundingClientRect();
            if (bounds.top > visible.bottom) reveal(lesson.querySelector("h4"));
          }},
          App.icon("next", 12), el("span", {text: t(guideKey(theme.id, id) + ".title")})));
      }
      selectGuide(theme.id, guide || theme.first);
    }

    for (const theme of THEMES) {
      const key = themeKey(theme.id);
      const button = el("button.help-theme", {type: "button", dataset: {theme: theme.id},
        "aria-controls": "help-panel", onclick: () => {
          selectTheme(theme);
          const navigation = themes.getBoundingClientRect();
          if (navigation.width && panel.getBoundingClientRect().top >= navigation.bottom) reveal(title);
        }}, App.icon(theme.icon, 20),
        el("span.help-theme-copy", {}, el("span.help-theme-title", {text: t(key + ".title")}),
          el("span.help-theme-summary", {text: t(key + ".summary")})), App.icon("next", 12));
      themes.appendChild(button);
      themeButtons.set(theme.id, button);
    }

    const features = FEATURES.map(feature => el("button.help-feature", {type: "button", dataset: {feature: feature.id},
      "aria-controls": "help-panel", onclick: () => {
        selectTheme(THEMES.find(theme => theme.id === feature.theme), feature.guide);
        reveal(lesson.querySelector("h4"));
      }}, el("span.help-feature-label", {}, App.icon(feature.icon, 18), el("span", {text: t(feature.label)})),
      preview(feature.id), el("h3", {text: t("whatsnew.featured." + feature.id + ".title")}),
      el("p.help-feature-text", {text: t("whatsnew.featured." + feature.id + ".text")})));

    App.append(page, [
      el("header.help-header", {}, el("div.help-heading", {}, el("p.kicker", {text: t("whatsnew.eyebrow")}),
        el("h1", {text: t("whatsnew.title")}), el("p.help-intro", {text: t("whatsnew.intro")})),
        el("a.whatsnew-versions.help-versions", {href: "#/versions", text: t("whatsnew.versions") + " →"})),
      el("section.help-featured", {"aria-labelledby": "help-featured-title"}, el("h2", {id: "help-featured-title", text: t("whatsnew.featured_title")}),
        el("div.help-feature-grid", {}, features)),
      el("section.help-guides", {"aria-labelledby": "help-guides-title"}, el("h2", {id: "help-guides-title", text: t("whatsnew.themes_title")}),
        el("div.help-browser", {}, themes, panel)),
      el("p.help-footer", {text: t("whatsnew.footer")}),
    ]);
    App.clear(main).appendChild(page);
    const [themeId, guideId] = (route.id || "").split("/");
    const theme = THEMES.find(item => item.id === themeId) || THEMES[0];
    selectTheme(theme, guides(theme.id).includes(guideId) ? guideId : undefined);
  }

  return {render};
})();
