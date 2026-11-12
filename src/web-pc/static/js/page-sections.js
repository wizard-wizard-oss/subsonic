"use strict";
/* Raccourcis internes : les liens gardent la fiche courante et donnent le focus à leur section. */
const PageSections = (() => {
  function link(text, section, open, className) {
    return App.el("a" + (className || ""), {href: "#" + section.id, text, onclick: event => {
      event.preventDefault();
      if (open) open();
      if (typeof section.scrollIntoView === "function") section.scrollIntoView({block: "start"});
      section.focus({preventScroll: true});
    }});
  }

  function nav(items) {
    return App.el("nav.page-sections", {"aria-label": App.t("artist.sections")},
      items.map(item => link(item.text, item.section, item.open, item.className)));
  }

  function section(id, className) {
    return App.el("section" + (className || ""), {id, tabIndex: -1});
  }

  return {link, nav, section};
})();
