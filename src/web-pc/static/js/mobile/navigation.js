"use strict";
/* Adaptation des composants existants : aucune préférence PC modifiée. */
class MobileNavigation {
  constructor() {
    this.app = document.getElementById("app");
    this.sidebar = document.getElementById("sidebar");
    this.chat = document.getElementById("chat-panel");
    this.buttons = {navigation: document.getElementById("toggle-sidebar"), chat: document.getElementById("toggle-chat")};
    this.panels = {navigation: this.sidebar, chat: this.chat};
    this.moves = [];
    this.attributes = [];
    this.opened = null;
    this.thread = App.chatPanel && App.chatPanel.thread;
    if (this.thread) {
      this.chatVisibility = this.thread.isVisible;
      this.thread.isVisible = () => this.opened === "chat" && App.chatPanel.tab === "room" && !document.hidden;
    }
    this.tools = App.el("div.mobile-menu-tools");
    const navigation = document.querySelector(".topnav");
    this.move(navigation, this.sidebar, this.sidebar.firstChild);
    for (const id of ["open-shortcuts", "open-settings"]) this.move(document.getElementById(id), this.tools);
    this.sidebar.appendChild(this.tools);
    this.closeButton = App.el("button.icon-button", {type: "button", "data-t-title": "settings.close",
      title: App.t("settings.close"), "aria-label": App.t("settings.close"), onclick: () => this.close()}, App.icon("close", 20));
    this.heading = App.el("div.mobile-panel-head", {}, App.el("strong", {"data-t": "nav.menu", text: App.t("nav.menu")}), this.closeButton);
    this.sidebar.prepend(this.heading);
    this.backdrop = App.el("button.mobile-backdrop", {type: "button", tabIndex: -1, hidden: true,
      "data-t-title": "settings.close", "aria-label": App.t("settings.close"), onclick: () => this.close()});
    this.app.appendChild(this.backdrop);
    for (const [name, button] of Object.entries(this.buttons)) {
      this.setAttribute(button, "aria-controls", this.panels[name].id);
      this.setAttribute(button, "aria-expanded", "false");
    }
    this.setAttribute(this.buttons.navigation, "data-t-title", "nav.menu");
    this.setAttribute(this.buttons.navigation, "title", App.t("nav.menu"));
    this.setAttribute(this.buttons.navigation, "aria-label", App.t("nav.menu"));
    this.click = event => this.onClick(event);
    this.key = event => this.onKey(event);
    this.escape = event => {
      const target = event.target;
      if (this.opened && event.key === "Escape" && !event.defaultPrevented &&
          !(target instanceof Element && target.closest('[role="dialog"]'))) {
        event.preventDefault();
        this.close();
      }
    };
    document.addEventListener("click", this.click, true);
    document.addEventListener("keydown", this.key, true);
    document.addEventListener("keydown", this.escape);
    this.unsubscribe = App.bus.on("route", () => this.close(false));
    this.offAccountMenu = App.bus.on("account-menu-opened", () => this.close(false));
    this.dialogs = new MutationObserver(() => {
      if (document.querySelector('#dialog-root [role="dialog"]')) this.close(false);
    });
    this.dialogs.observe(document.getElementById("dialog-root"), {childList: true});
  }

  move(node, parent, before = null) {
    const place = document.createComment("mobile navigation");
    node.before(place);
    this.moves.push({node, place});
    parent.insertBefore(node, before);
  }

  setAttribute(node, name, value) {
    this.attributes.push({node, name, value: node.getAttribute(name)});
    node.setAttribute(name, value);
  }

  onClick(event) {
    if (this.app.hidden) return;
    const target = event.target instanceof Element ? event.target : event.target.parentElement;
    for (const [name, button] of Object.entries(this.buttons)) {
      if (!button.contains(target)) continue;
      event.preventDefault();
      event.stopImmediatePropagation();
      if (this.opened === name) this.close(); else this.open(name);
      return;
    }
    if (this.opened === "navigation" && this.sidebar.contains(target) &&
        (target.closest('a[href^="#/"]') || (this.tools.contains(target) && target.closest("button, a")))) {
      this.close(false);
    }
  }

  onKey(event) {
    if (this.app.hidden) return;
    const target = event.target;
    if (target instanceof Element && target.closest('[role="dialog"]')) return;
    const editing = target instanceof Element && target.closest("input, textarea, select, [contenteditable]");
    if (!editing && !event.ctrlKey && !event.metaKey && !event.altKey && ["a", "c"].includes(event.key.toLowerCase())) {
      event.preventDefault();
      event.stopImmediatePropagation();
      const name = event.key.toLowerCase() === "a" ? "navigation" : "chat";
      if (this.opened === name) this.close(); else this.open(name);
      return;
    }
    if (!this.opened) return;
    if (event.key === "Tab") {
      const panel = this.panels[this.opened];
      const focusable = [...panel.querySelectorAll('a[href], button, input, textarea, select, [tabindex="0"]')]
        .filter(node => !node.disabled && !node.closest("[hidden]") && node.getClientRects().length);
      const first = focusable[0], last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  }

  open(name) {
    document.getElementById("account-menu").open = false;
    this.close(false);
    if (name === "chat" && App.lyrics && App.lyrics.isOpen()) App.lyrics.close();
    this.opened = name;
    document.body.dataset.mobilePanel = name;
    this.panels[name].prepend(this.heading);
    this.heading.firstChild.textContent = App.t(name === "navigation" ? "nav.menu" : "nav.chat");
    this.heading.firstChild.dataset.t = name === "navigation" ? "nav.menu" : "nav.chat";
    this.backdrop.hidden = false;
    this.buttons[name].setAttribute("aria-expanded", "true");
    this.blocked = ["main", "player"].map(id => {
      const node = document.getElementById(id), inert = node.inert;
      node.inert = true;
      return {node, inert};
    });
    const field = this.panels[name].querySelector(name === "navigation" ? '.sidebar-panel:not([hidden]) input' : ".composer-input");
    (field || this.closeButton).focus();
    if (name === "chat" && App.chatPanel) {
      App.chatPanel.thread.scrollToLatest();
      App.chatPanel.thread.markRead();
    }
  }

  close(restoreFocus = true) {
    if (!this.opened) return;
    const button = this.buttons[this.opened];
    this.opened = null;
    delete document.body.dataset.mobilePanel;
    this.backdrop.hidden = true;
    button.setAttribute("aria-expanded", "false");
    for (const {node, inert} of this.blocked) node.inert = inert;
    if (restoreFocus) button.focus();
    else if (this.sidebar.contains(document.activeElement) || this.chat.contains(document.activeElement)) {
      document.getElementById("main").focus({preventScroll: true});
    }
  }

  destroy() {
    const focusInside = this.opened && this.panels[this.opened].contains(document.activeElement);
    this.close(false);
    document.removeEventListener("click", this.click, true);
    document.removeEventListener("keydown", this.key, true);
    document.removeEventListener("keydown", this.escape);
    this.unsubscribe();
    this.offAccountMenu();
    this.dialogs.disconnect();
    if (this.thread) this.thread.isVisible = this.chatVisibility;
    this.heading.remove();
    this.backdrop.remove();
    for (const {node, place} of this.moves) place.replaceWith(node);
    this.tools.remove();
    for (const {node, name, value} of this.attributes) {
      if (value === null) node.removeAttribute(name); else node.setAttribute(name, value);
    }
    if (focusInside) this.buttons.navigation.focus();
  }
}
