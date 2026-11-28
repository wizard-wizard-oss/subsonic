"use strict";
/* Collections de la Bibliothèque : même source que le menu, actualisée sans refaire la page. */
class LibraryShortcuts {
  constructor(route) {
    this.route = route;
    this.owner = App.user.id;
    this.alive = true;
    this.source = App.music.sidebar;
    this.root = App.el("span.library-shortcuts", {hidden: true});
    this.off = App.bus.on("artist-index", () => this.refresh());
    if (this.source && this.source.owner !== this.owner) this.source.load(true);
    this.refresh();
  }

  refresh() {
    if (!this.alive || this.route.stale || !App.user || App.user.id !== this.owner) return;
    const source = this.source;
    if (!source || source.owner !== this.owner) return;
    this.root.replaceChildren(...(source.shortcutItems || []).map(folder => App.el("a.tab.library-shortcut", {
      href: "#/artist/" + encodeURIComponent(folder.id), text: folder.name})));
    if (source.loadError) this.root.append(App.el("button.link-button", {type: "button",
      text: App.t("nav.shortcuts_retry"), onclick: () => source.load(true)}));
    this.root.hidden = !this.root.childNodes.length;
  }

  destroy() { this.alive = false; this.off(); }
}
