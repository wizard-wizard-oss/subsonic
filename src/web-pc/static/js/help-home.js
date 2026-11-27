"use strict";
/* Help : l'accueil du sub. Il raconte l'idée (hero, piliers), mène à l'action (parcours, espace) et dépanne (FAQ).
   Rien n'est écrit : chaque bouton ouvre un guide ou une fonction existante, la page ne change aucun réglage. */

const HelpHome = (() => {
  const el = App.el, t = App.t;
  // Chaque pilier ouvre le guide qui explique le geste ; sa pochette (static/help/) s'affiche en noir et blanc.
  const PILLARS = [
    {id: "elsewhere", theme: "elsewhere", guide: "g1", cover: "dark-side-of-the-moon", icon: "play"},
    {id: "press", theme: "press", guide: "g5", cover: "unknown-pleasures", icon: "radio"},
    {id: "discover", theme: "explore", guide: "g4", cover: "discovery", icon: "disc"},
    {id: "share", theme: "social", guide: "g1", cover: "abbey-road", icon: "chat"},
  ];
  const TROUBLE_COVER = "licensed-to-ill";
  const JOURNEY = [
    {id: "s1", icon: "play", destination: "#/albums/newest"},
    {id: "s2", icon: "heart"},
    {id: "s3", icon: "chat", destination: "chat"},
    {id: "s4", icon: "bookmark", destination: "#/listen-later"},
  ];
  const SPACE = [
    {id: "i1", icon: "radio", theme: "press", guide: "g2"},
    {id: "i2", icon: "list", theme: "press", guide: "g5"},
    {id: "i3", icon: "music", theme: "social", guide: "g5"},
    {id: "i4", icon: "plus", theme: "save", guide: "g4"},
    {id: "i5", icon: "download", theme: "save", guide: "g5"},
    {id: "i6", icon: "storage", theme: "settings", guide: "g3"},
  ];
  const FAQ = ["f1", "f2", "f3", "f4", "f5"];

  /** Un titre de section : le sujet en petit, puis le titre de la chanson en grand, sur un bandeau de pochette si on en a une. */
  function heading(id, section, cover) {
    const box = el("div.help-section-heading", {},
      el("p.help-topic", {text: t("whatsnew." + section + ".topic")}),
      el("h2", {id, tabIndex: -1, text: t("whatsnew." + section + ".song")}));
    if (cover) {
      box.classList.add("has-cover");
      box.dataset.cover = "/static/help/" + cover + ".jpg";
      box.style.setProperty("--cover", 'url("' + box.dataset.cover + '")');
    }
    return box;
  }

  /** La pochette du pilier. */
  function shot(item, key) {
    return el("div.help-pillar-shot", {}, el("img", {src: "/static/help/" + item.cover + ".jpg", alt: t(key + ".image_alt"),
      loading: "lazy", decoding: "async"}));
  }

  function hero(deps) {
    const journey = el("button.help-hero-journey", {type: "button", text: t("whatsnew.journey_button") + " ↓",
      onclick: () => deps.reveal(document.getElementById("help-journey-title"))});
    return el("header.help-header.help-hero", {},
      el("div.help-sub", {"aria-hidden": "true"},   // le sous-marin du favicon dans un hublot, au-dessus du cadre : « le sub »
        el("img", {src: "/static/favicon.svg", alt: "", width: 56, height: 56})),
      el("div.help-heading", {}, el("p.kicker", {text: t("whatsnew.eyebrow")}), el("h1", {text: t("whatsnew.title")}),
        el("p.help-intro", {text: t("whatsnew.intro")}),
        el("div.help-hero-actions", {}, journey,
          el("a.whatsnew-versions.help-versions", {href: "#/versions", text: t("whatsnew.versions") + " →"}))),
      deps.search);
  }

  function pillar(item, deps) {
    const key = "whatsnew.pillars." + item.id;
    return el("article.help-pillar", {dataset: {pillar: item.id}},
      shot(item, key),
      el("span.help-pillar-topic", {}, App.icon(item.icon, 16), el("span", {text: t(key + ".topic")})),
      el("h3", {text: t(key + ".song")}), el("p", {text: t(key + ".text")}),
      el("button.help-pillar-go", {type: "button", "aria-controls": "help-panel", onclick: () => deps.open(item.theme, item.guide)},
        el("span", {text: t("whatsnew.pillar_go")}), App.icon("next", 12)));
  }

  function pillars(deps) {
    return el("section.help-pillars", {"aria-labelledby": "help-pillars-title"},
      el("h2.help-plain-title", {id: "help-pillars-title", text: t("whatsnew.pillars_title")}),
      el("div.help-pillar-grid", {}, PILLARS.map(item => pillar(item, deps))));
  }

  /** Un geste du parcours : un lien vers une page du site, ou un bouton qui ouvre un panneau existant. */
  function step(item, deps, number) {
    const key = "whatsnew.journey.steps." + item.id;
    const go = !item.destination ? null : item.destination.startsWith("#/") ?
      el("a.whatsnew-link", {href: item.destination, text: t("whatsnew.open") + " →"}) :
      el("button.help-journey-go", {type: "button", dataset: {action: item.destination},
        text: t("whatsnew.actions." + item.destination), onclick: () => deps.run(item.destination)});
    return el("li", {dataset: {step: number}}, el("span.help-step-icon", {"aria-hidden": "true"}, App.icon(item.icon, 22)),
      el("h3", {text: t(key + ".title")}), el("p", {text: t(key + ".text")}), go);
  }

  function journey(deps) {
    return el("section.help-journey-section", {"aria-labelledby": "help-journey-title"},
      heading("help-journey-title", "journey"),
      el("ol.help-journey", {}, JOURNEY.map((item, index) => step(item, deps, index + 1))));
  }

  function space(deps) {
    return el("section.help-space", {"aria-labelledby": "help-space-title"},
      heading("help-space-title", "space"), el("p.help-space-text", {text: t("whatsnew.space.text")}),
      el("div.help-space-grid", {}, SPACE.map(item => el("button.help-space-item", {type: "button", "aria-controls": "help-panel",
        onclick: () => deps.open(item.theme, item.guide)}, App.icon(item.icon, 20),
        el("span.help-space-copy", {}, el("strong", {text: t("whatsnew.space.items." + item.id + ".title")}),
          el("span", {text: t("whatsnew.space.items." + item.id + ".text")}))))));
  }

  function trouble() {
    return el("section.help-trouble", {"aria-labelledby": "help-trouble-title"}, heading("help-trouble-title", "trouble", TROUBLE_COVER),
      el("div.help-faq-list", {}, FAQ.map(id => el("details.help-faq", {},
        el("summary", {text: t("whatsnew.trouble.faq." + id + ".question")}),
        el("p", {text: t("whatsnew.trouble.faq." + id + ".answer")})))));
  }

  /** Les deux parties de l'accueil, de part et d'autre des guides par thème. */
  return {
    top: deps => [hero(deps), pillars(deps), journey(deps), space(deps)],
    bottom: () => [trouble()],
  };
})();
