"use strict";
/* Disposition ordinateur : les liens, playlists et gestionnaires existants gardent leur identité. */
class DesktopNavigation {
  constructor() {
    this.moves = [];
    this.originals = new Map();
    this.owner = App.user.id;
    this.opened = true;
    this.chatOpen = false;
    this.sidebar = document.getElementById("sidebar");
    this.button = document.getElementById("toggle-sidebar");
    this.chat = document.getElementById("toggle-chat");
    document.body.dataset.desktopLayout = "true";
    this.moveTopbar();
    this.moveNavigation();
    this.offRoute = App.bus.on("route", route => this.highlightNews(route));
    this.highlightNews(App.music.route);
    this.moveAccountTools();
    this.bindVisibility();
    this.offPreferences = App.bus.on("preferences", () => this.refreshOwner());
    this.applyMenu();
    if (App.chatPanel) App.chatPanel.applyOpen();
    else document.body.dataset.chat = "closed";
    this.chat.setAttribute("aria-expanded", "false");
  }

  remember(node, attributes = [], content = false) {
    let original = this.originals.get(node);
    if (!original) { original = {attributes: new Map()}; this.originals.set(node, original); }
    for (const name of attributes) {
      if (!original.attributes.has(name)) original.attributes.set(name, node.getAttribute(name));
    }
    if (content && !original.children) original.children = Array.from(node.childNodes);
  }

  move(node, parent, before = null) {
    const place = document.createComment("desktop navigation");
    node.before(place);
    this.moves.push({node, place});
    parent.insertBefore(node, before);
  }

  label(node, key, icon) {
    this.remember(node, ["data-t"], true);
    node.removeAttribute("data-t");
    node.replaceChildren(...(icon ? [App.icon(icon, 18)] : []), App.el("span", {"data-t": key, text: App.t(key)}));
  }

  moveTopbar() {
    const bar = document.querySelector(".topbar"), input = document.getElementById("search");
    this.topStart = App.el("div.desktop-top-start");
    bar.prepend(this.topStart);
    this.move(this.button, this.topStart);
    this.move(document.querySelector(".brand"), this.topStart);
    this.searchBox = App.el("label.desktop-search", {}, App.icon("search", 17),
      App.el("span.sr-only", {text: App.t("nav.search")}));
    input.before(this.searchBox);
    this.remember(input, ["data-t-placeholder", "placeholder"]);
    input.dataset.tPlaceholder = "nav.search_hint";
    input.placeholder = App.t("nav.search_hint");
    this.move(input, this.searchBox);
    this.remember(this.chat, ["class"], true);
    this.chat.prepend(App.icon("message", 17));
  }

  moveNavigation() {
    const nav = document.querySelector(".topnav");
    const link = path => nav.querySelector('a[href="' + path + '"]');
    const library = link("#/albums/newest");
    this.label(library, "nav.library", "library");
    this.label(link("#/"), "nav.home", "home");
    this.label(link("#/favorites"), "nav.favorites", "heart");
    this.label(link("#/mix"), "nav.create_mix", "shuffle");
    this.news = link("#/news");
    const later = link("#/listen-later");
    this.remember(later, ["href"]);
    later.href = "#/listen-later/bookmarks";
    this.label(later, "nav.listen_later", "bookmark");
    this.label(this.news, "nav.webzines", "radio");
    this.releases = App.el("a", {href: "#/news/releases"}, App.icon("disc", 18),
      App.el("span", {"data-t": "nav.releases", text: App.t("nav.releases")}));
    this.news.after(this.releases);
    this.move(link("#/mix"), nav, document.getElementById("nav-upload"));
    this.label(document.getElementById("nav-upload"), App.can("upload") ? "nav.send_album" : "upload.activity", "upload");
    this.guide = link("#/whatsnew");
    this.remember(this.guide, ["data-t", "data-t-title", "title", "aria-label", "class"], true);
    this.guide.removeAttribute("data-t");
    this.guide.classList.add("desktop-guide", "icon-button");
    this.guide.setAttribute("aria-label", App.t("nav.guide"));
    this.guide.title = App.t("nav.guide");
    this.guide.replaceChildren(App.el("img", {src: "/static/favicon.svg", alt: "", width: 30, height: 30}));
    this.move(this.guide, document.querySelector(".topbar-right"), document.getElementById("account-menu"));
    this.move(nav, this.sidebar, this.sidebar.firstChild);
    const tools = App.el("div.desktop-playlist-actions");
    this.playlistHeading = App.el("div.desktop-playlist-heading", {},
      App.el("h2", {text: App.t("playlist.tab")}), tools);
    document.getElementById("panel-playlists").before(this.playlistHeading);
    this.move(document.querySelector(".playlist-see-all"), this.playlistHeading);
    this.move(document.getElementById("playlist-new"), tools);
    this.move(document.getElementById("playlist-import"), tools);
  }

  highlightNews(route) {
    const news = route && route.view === "news";
    this.news.classList.toggle("active", !!news && route.id !== "releases");
    this.releases.classList.toggle("active", !!news && route.id === "releases");
  }

  moveAccountTools() {
    const panel = document.querySelector(".account-menu-panel"), logout = document.getElementById("logout");
    for (const [id, key] of [["open-settings", "nav.settings"], ["open-shortcuts", "nav.shortcuts"]]) {
      const node = document.getElementById(id);
      this.label(node, key);
      this.move(node, panel, logout);
    }
    const version = document.getElementById("version-tag");
    this.remember(version, ["data-account-version", "class"], true);
    version.dataset.accountVersion = "true";
    version.classList.remove("version-tag");
    version.textContent = App.t("nav.versions");
    this.move(version, panel, logout);
    if (typeof Versions !== "undefined") Versions.load();
  }

  bindVisibility() {
    this.remember(this.button, ["data-t-title", "title", "aria-label", "aria-expanded", "aria-controls"]);
    this.remember(this.chat, ["aria-expanded"]);
    this.click = event => {
      if (!this.button.contains(event.target)) return;
      event.preventDefault(); event.stopImmediatePropagation(); this.toggle();
    };
    this.button.addEventListener("click", this.click, true);
    if (App.music.sidebar) {
      this.oldSidebarToggle = App.music.sidebar.toggle;
      App.music.sidebar.toggle = () => this.toggle();
    }
    if (!App.chatPanel) return;
    this.oldChatToggle = App.chatPanel.toggle;
    this.oldChatIsOpen = App.chatPanel.isOpen;
    App.chatPanel.isOpen = () => App.user.id === this.owner && this.chatOpen;
    App.chatPanel.toggle = () => {
      if (App.lyrics && App.lyrics.isOpen()) App.lyrics.close();
      this.chatOpen = !this.chatOpen;
      App.chatPanel.applyOpen();
      this.chat.setAttribute("aria-expanded", String(this.chatOpen));
    };
  }

  toggle() { this.opened = !this.opened; this.applyMenu(); }

  applyMenu() {
    document.body.dataset.desktopMenu = this.opened ? "open" : "closed";
    this.button.dataset.tTitle = this.opened ? "nav.hide_menu" : "nav.show_menu";
    this.button.title = App.t(this.button.dataset.tTitle);
    this.button.setAttribute("aria-label", this.button.title);
    this.button.setAttribute("aria-controls", "sidebar");
    this.button.setAttribute("aria-expanded", String(this.opened));
    this.sidebar.inert = !this.opened;
    if (!this.opened && this.sidebar.contains(document.activeElement)) this.button.focus();
  }

  refreshOwner() {
    if (this.owner === App.user.id) return;
    this.owner = App.user.id;
    this.chatOpen = false;
    this.opened = true;
    if (App.music.sidebar && App.music.sidebar.owner !== this.owner) App.music.sidebar.load(true);
    this.applyMenu();
    if (App.chatPanel) App.chatPanel.applyOpen();
  }

  destroy() {
    this.offPreferences();
    this.offRoute();
    this.button.removeEventListener("click", this.click, true);
    if (this.oldSidebarToggle) App.music.sidebar.toggle = this.oldSidebarToggle;
    if (this.oldChatToggle) {
      App.chatPanel.toggle = this.oldChatToggle;
      App.chatPanel.isOpen = this.oldChatIsOpen;
      document.body.dataset.chat = App.chatPanel.isOpen() ? "open" : "closed";
    }
    this.sidebar.inert = false;
    for (const {node, place} of this.moves.slice().reverse()) place.replaceWith(node);
    for (const [node, original] of this.originals) {
      for (const [key, value] of original.attributes) {
        if (value === null) node.removeAttribute(key); else node.setAttribute(key, value);
      }
      if (original.children) node.replaceChildren(...original.children);
    }
    this.playlistHeading.remove(); this.releases.remove();
    this.topStart.remove(); this.searchBox.remove();
    this.news.classList.toggle("active", !!App.music.route && App.music.route.view === "news");
    delete document.body.dataset.desktopLayout;
    delete document.body.dataset.desktopMenu;
    if (typeof Versions !== "undefined") Versions.load();
  }
}
