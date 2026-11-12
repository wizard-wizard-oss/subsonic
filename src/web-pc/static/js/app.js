"use strict";
/* Démarrage : textes, connexion, puis l'application (barre des artistes, pages, lecteur, salon, raccourcis). */

class MusicApp {
  constructor() {
    this.route = null;
    this.view = null;
    this.main = document.getElementById("main");
  }

  async boot() {
    try {
      App.texts = await App.api.get("/api/texts");
    } catch (e) { /* textes absents : les clés s'affichent */ }
    App.translate();
    App.placeIcons();
    App.onSessionLost = () => this.showLogin(App.t("auth.required"));
    document.getElementById("login-form").addEventListener("submit", e => this.login(e));
    document.getElementById("login-forgot").addEventListener("click", () => this.toggleForgotHelp());
    try {
      await this.start(await App.api.get("/api/me"));
    } catch (error) {
      this.showLogin(error.status === 401 ? "" : App.errorText(error));
    }
  }

  showLogin(message) {
    App.live.stop();
    document.getElementById("app").hidden = true;
    document.getElementById("login").hidden = false;
    document.getElementById("login-error").textContent = message || "";
    document.querySelector("#login-form input[name=username]").focus();
  }

  toggleForgotHelp() {
    const help = document.getElementById("login-forgot-help");
    help.hidden = !help.hidden;
    document.getElementById("login-forgot").setAttribute("aria-expanded", String(!help.hidden));
  }

  async login(event) {
    event.preventDefault();
    const form = event.target, error = document.getElementById("login-error");
    error.textContent = "";
    try {
      await App.api.post("/api/login", {username: form.elements.username.value, password: form.elements.password.value});
      form.elements.password.value = "";
      await this.start(await App.api.get("/api/me"));
    } catch (e) {
      error.textContent = App.errorText(e);
    }
  }

  async start(me) {
    App.user = me.user;
    ListenLaterUI.reset();
    ListenLaterUI.start();
    App.preferences = me.preferences;
    App.reactions = me.reactions;
    App.usernames = me.usernames;
    App.unread = me.unread;
    document.getElementById("login").hidden = true;
    document.getElementById("app").hidden = false;
    App.append(App.clear(document.getElementById("me")), [App.avatar(App.user.username, 26),
                                                          App.el("span.me-name", {text: App.user.username})]);
    if (this.started) return;          // reconnexion après une session expirée : tout est déjà en place
    this.started = true;

    App.player = new Player(new PlaybackEngine(new Audio(), document.getElementById("video-frame")));
    ExtMusic.load();
    Versions.load();
    Avatars.load();
    setInterval(() => { if (!document.hidden) Avatars.load(); }, 10 * 60 * 1000);   // photos changées par les autres
    App.queuePanel = new QueuePanel(App.player);
    new PlayerBar(document.getElementById("player"), App.player);
    this.sidebar = new ArtistSidebar(this);
    this.playlistPanel = new PlaylistPanel(this);
    this.listeningPanel = new ListeningPanel();
    App.chatPanel = new ChatPanel(this);
    App.lyrics = new LyricsPanel(App.player);
    this.applyPreferences();
    App.bus.on("preferences", () => this.applyPreferences());
    this.bindTopbar();
    this.bindShortcuts();
    App.live.start();
    App.live.on("message", m => {        // nouvel inscrit : son nom devient mentionnable
      if (!App.usernames.includes(m.author)) App.usernames.push(m.author);
    });
    this.sidebar.load();
    this.showUploadLink();
    App.chatPanel.start();
    window.addEventListener("hashchange", () => this.navigate());
    this.navigate();
  }

  /** Le lien « Envoyer » n'apparaît que si le compte a le droit Subsonic d'envoyer et que le site sait où ranger les fichiers. */
  async showUploadLink() {
    if (!App.can("upload")) return;
    try {
      document.getElementById("nav-upload").hidden = !(await App.api.get("/api/upload/status")).enabled &&
        !App.can("admin");                                   // un administrateur voit la page, et pourquoi elle ne marche pas
    } catch (error) { /* lien absent */ }
  }

  applyPreferences() {
    document.body.dataset.density = App.preferences.density || "comfortable";
    this.sidebar.applyMode();
  }

  bindTopbar() {
    const search = document.getElementById("search");
    let timer = null;
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const q = search.value.trim();
        if (q.length >= 2) location.hash = "#/search/" + encodeURIComponent(q);
      }, 350);
    });
    search.addEventListener("keydown", e => { if (e.key === "Escape") search.blur(); });
    document.getElementById("toggle-sidebar").addEventListener("click", () => this.sidebar.toggle());
    document.getElementById("toggle-chat").addEventListener("click", () => App.chatPanel.toggle());
    document.getElementById("open-settings").addEventListener("click", () => Dialogs.settings());
    document.getElementById("open-shortcuts").addEventListener("click", () => Dialogs.shortcuts());
    document.getElementById("logout").addEventListener("click", async () => {
      try { await App.api.post("/api/logout"); } catch (e) { /* déjà déconnecté */ }
      App.player.audio.pause();
      location.hash = "#/";
      location.reload();
    });
  }

  /** Raccourcis clavier, ignorés pendant la saisie de texte. */
  bindShortcuts() {
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && (Dialogs.close() || App.queuePanel.close())) return;
      const target = event.target;
      const typing = target && (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName));
      if (typing || event.ctrlKey || event.metaKey || event.altKey || Dialogs.isOpen()) return;
      const actions = {
        " ": () => App.player.toggle(),
        "n": () => App.player.next(), "N": () => App.player.next(),
        "p": () => App.player.previous(), "P": () => App.player.previous(),
        "ArrowLeft": () => App.player.seekBy(-10), "ArrowRight": () => App.player.seekBy(10),
        "/": () => document.getElementById("search").focus(),
        "a": () => this.sidebar.toggle(), "A": () => this.sidebar.toggle(),
        "c": () => App.chatPanel.toggle(), "C": () => App.chatPanel.toggle(),
        "l": () => App.lyrics.toggle(), "L": () => App.lyrics.toggle(),
        "?": () => Dialogs.shortcuts(),
      };
      const action = actions[event.key];
      if (action) { event.preventDefault(); action(); }
    });
  }

  /** #/  #/artist/<id>  #/album/<id>  #/playlist/<id>  #/search/<texte>  #/favorites  #/albums/<onglet>[/<décennie ou genre>]
      #/mix[/<artiste de départ>]  #/news[/<flux>]  #/whatsnew  #/versions  #/account  #/import[/guide] */
  static parse(hash) {
    const [, view, ...rest] = (hash || "#/").replace(/^#/, "").split("/");
    const id = decodeURIComponent(rest.join("/") || "");
    if (view === "explore" || view === "discogs") return {view, kind: rest[0], id: rest[1] || ""};
    if (view === "artist" || view === "album" || view === "search") return id ? {view, id} : {view: "home"};
    if (view === "playlist") return id ? {view, id} : {view: "home"};
    if (view === "listen-later") return {view: "listenLater"};
    if (view === "favorites" || view === "upload" || view === "whatsnew" || view === "versions" ||
        view === "account") return {view};
    if (view === "import") return {view, id};                     // id : « guide » (facultatif)
    if (view === "mix") return {view, id};                        // id : artiste de départ (facultatif)
    if (view === "news") return {view, id};                       // id : un seul flux (facultatif)
    if (view === "albums") return {view, kind: rest[0] || "newest", value: decodeURIComponent(rest.slice(1).join("/"))};
    return {view: "home"};
  }

  navigate() {
    if (this.route) this.route.stale = true;
    if (this.view && this.view.destroy) this.view.destroy();
    this.route = MusicApp.parse(location.hash);
    this.view = Views[this.route.view];
    const section = hash => (hash || "#/").split("/")[1] || "";      // « #/albums/frequent » -> « albums »
    document.querySelectorAll(".topnav a").forEach(a =>
      a.classList.toggle("active", section(a.getAttribute("href")) === section(location.hash)));
    App.bus.emit("route", this.route);
    this.main.scrollTop = 0;
    this.view.render(this.main, this.route);
  }

  updateTitle(unread) {
    const base = App.player && App.player.current ? App.player.current.title + " · " + App.t("title") : App.t("title");
    document.title = (unread ? "(" + unread + ") " : "") + base;
  }
}

App.music = new MusicApp();
document.addEventListener("DOMContentLoaded", () => App.music.boot());
