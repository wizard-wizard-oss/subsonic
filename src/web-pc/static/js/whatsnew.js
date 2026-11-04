"use strict";
/* Page « Nouveautés » (#/whatsnew), pour les personnes qui utilisent le site : ce qu'il fait en plus de Subsonic, et
   l'idée qui va avec (Subsonic reste la bibliothèque, le site ajoute le reste). Tous les textes sont dans fr.yaml
   (section whatsnew) ; ici seulement leur ordre, une icône par partie et le lien vers la page concernée. */

Views.whatsnew = (() => {
  const el = App.el, t = App.t;

  // [partie, icône, [[sujet, lien facultatif], …]]
  const PARTS = [
    ["together", "chat", [["chat"], ["listening"], ["comments"], ["news", "#/news"]]],
    ["discover", "shuffle", [["mix", "#/mix"], ["builder", "#/mix"], ["radio"], ["similar"], ["home", "#/albums/newest"]]],
    ["playlists", "list", [["drag"], ["community"], ["shared"], ["mixed"], ["import", "#/import"]]],
    ["elsewhere", "play", [["search"], ["sources"], ["what"], ["quota"], ["refused"], ["favorites", "#/favorites"],
                           ["likes"], ["fine_print"]]],
    ["comfort", "mic", [["lyrics"], ["queue"], ["shortcuts"], ["download"]]],
    ["where", "disc", [["subsonic"], ["site"]]],
  ];

  function card(part, [topic, link]) {
    const key = "whatsnew." + part + "." + topic;
    return el("article.whatsnew-card", {},
      el("h3", {text: t(key + ".title")}),
      el("p", {text: t(key + ".text")}),
      link ? el("a.whatsnew-link", {href: link, text: t("whatsnew.open") + " →"}) : null);
  }

  function part([name, icon, topics]) {
    return el("section.whatsnew-part", {},
      App.setIcon(el("h2.whatsnew-part-title"), icon, 20, false, t("whatsnew." + name + ".title")),
      el("div.whatsnew-grid", {}, topics.map(topic => card(name, topic))));
  }

  return {
    render(main) {
      App.clear(main);
      App.append(main, [
        el("h1", {text: t("whatsnew.title")}),
        el("a.whatsnew-link.whatsnew-versions", {href: "#/versions", text: t("whatsnew.versions") + " →"}),
        el("section.whatsnew-idea", {},
          el("h2", {text: t("whatsnew.idea_title")}),
          ["idea_1", "idea_2", "idea_3"].map(key => el("p", {text: t("whatsnew." + key)}))),
        PARTS.map(part),
        el("p.muted.whatsnew-footer", {text: t("whatsnew.footer")})]);
    },
  };
})();
