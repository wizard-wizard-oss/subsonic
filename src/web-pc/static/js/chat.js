"use strict";
/* Salon global (un seul salon pour tout le monde) et commentaires sous les albums.
   ChatThread : une discussion (« general » ou « album:<id> ») avec sa liste et sa zone de saisie.
   ChatPanel : le panneau de droite (salon, mentions, recherche, personnes en ligne). */

const GROUP_SECONDS = 300;          // messages d'une même personne à moins de 5 min : regroupés

/* ---------- saisie avec suggestions de @noms ---------- */
class MentionPicker {
  constructor(textarea) {
    this.textarea = textarea;
    this.box = App.el("ul.mention-picker", {hidden: true, role: "listbox"});
    this.choices = [];
    this.active = 0;
  }

  /** Mot « @deb » juste avant le curseur, ou null. */
  query() {
    const before = this.textarea.value.slice(0, this.textarea.selectionStart);
    const match = /(^|[^\w@])@([\w.+-]{0,64})$/.exec(before);
    return match ? match[2] : null;
  }

  update() {
    const query = this.query();
    if (query === null) return this.close();
    const lower = query.toLowerCase();
    this.choices = App.usernames.filter(n => n.toLowerCase().startsWith(lower) &&
                                             n.toLowerCase() !== (App.user.username || "").toLowerCase()).slice(0, 6);
    if (!this.choices.length) return this.close();
    this.active = Math.min(this.active, this.choices.length - 1);
    App.clear(this.box);
    this.choices.forEach((name, i) => this.box.appendChild(App.el("li" + (i === this.active ? ".active" : ""), {
      role: "option", text: "@" + name, onmousedown: e => { e.preventDefault(); this.pick(name); }})));
    this.box.hidden = false;
  }

  close() { this.box.hidden = true; this.choices = []; this.active = 0; }

  /** Gère les flèches, Entrée et Tab quand la liste est ouverte. True si la touche a été utilisée. */
  key(event) {
    if (this.box.hidden) return false;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      this.active = (this.active + (event.key === "ArrowDown" ? 1 : -1) + this.choices.length) % this.choices.length;
      this.update();
      return true;
    }
    if (event.key === "Enter" || event.key === "Tab") { this.pick(this.choices[this.active]); return true; }
    if (event.key === "Escape") { this.close(); return true; }
    return false;
  }

  pick(name) {
    const area = this.textarea, caret = area.selectionStart;
    const before = area.value.slice(0, caret).replace(/@[\w.+-]*$/, "@" + name + " ");
    area.value = before + area.value.slice(caret);
    area.selectionStart = area.selectionEnd = before.length;
    this.close();
    area.dispatchEvent(new Event("input"));
    area.focus();
  }
}

/* ---------- une discussion ---------- */
class ChatThread {
  /* Salon « le plus récent en haut » (27/10/2026, mis de côté à la demande : on garde pour l'instant le dernier en bas,
     qui reste en vue grâce à « stuck »). Pour y revenir : mettre true. Tout est prêt : saisie au-dessus des messages,
     anciens chargés en bas, non-lus en haut, CSS « .newest-first » (chat.css) ; le parcours tests/e2e_webapp.js lit
     ce réglage et attend le bon ordre. Les commentaires sous un album restent toujours dans l'ordre de lecture. */
  static NEWEST_FIRST_IN_ROOM = false;

  constructor(topic, options) {
    const el = App.el;
    this.topic = topic;
    this.mode = (options && options.mode) || "room";        // « room » (salon) ou « comments » (sous un album)
    this.isVisible = (options && options.isVisible) || (() => true);
    this.readOnly = !!(options && options.readOnly);            // sans le droit Subsonic « commentaires »
    this.newestFirst = this.mode === "room" && ChatThread.NEWEST_FIRST_IN_ROOM;
    this.stuck = true;                                        // les derniers messages sont en vue : on les y garde
    this.messages = new Map();
    this.order = [];
    this.nodes = new Map();
    this.hasMore = false;
    this.lastRead = 0;
    this.unseen = 0;                                         // arrivés hors de vue
    this.replyTo = null;
    this.editing = null;
    this.typingPeople = new Map();
    this.unsubscribe = [];

    this.list = el("div.messages", {role: "log", "aria-live": "polite", onscroll: () => this.onScroll()});
    this.olderButton = el("button.load-older", {hidden: true, text: App.t("chat.load_older"), onclick: () => this.loadOlder()});
    this.jumpButton = el("button.jump-latest", {hidden: true, onclick: () => this.scrollToLatest(true)});
    this.typingLine = el("div.typing-line");
    this.contextBar = el("div.composer-context", {hidden: true});
    this.textarea = el("textarea.composer-input", {
      rows: 1, maxLength: 2000,
      placeholder: App.t(this.mode === "room" ? "chat.placeholder" : "chat.comment_placeholder"),
      oninput: () => this.onInput(), onkeydown: e => this.onKey(e)});
    this.picker = new MentionPicker(this.textarea);
    this.sendButton = el("button.primary.send", {text: App.t("chat.send"), onclick: () => this.submit()});
    const wrap = el("div.messages-wrap", {}, this.list, this.jumpButton);
    const composer = this.readOnly ? el("p.composer-locked", {text: App.t("chat.comments_locked")}) :
      el("div.composer", {}, this.contextBar, this.picker.box,
         el("div.composer-row", {}, this.textarea, this.sendButton),
         el("div.composer-help", {text: App.t("chat.formatting")}));
    this.element = el("div.chat-thread." + this.mode + (this.newestFirst ? ".newest-first" : ""), {},
      this.newestFirst ? [composer, this.typingLine, wrap] : [wrap, this.typingLine, composer]);
    this.list.appendChild(this.olderButton);

    this.unsubscribe.push(
      App.live.on("message", m => this.onLive(m)),
      App.live.on("message_updated", m => this.onUpdated(m)),
      App.live.on("typing", t => this.onTyping(t)),
      App.live.on("reconnected", () => this.catchUp()));
    // Zone qui change de taille (« Écouté en ce moment » qui apparaît, saisie sur plusieurs lignes, panneau rouvert)
    // ou image qui finit de se charger (pochette d'un album partagé) : sans cela, le dernier message glisse hors de vue.
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(() => this.keepLatest()).observe(this.list);
    this.list.addEventListener("load", () => this.keepLatest(), true);
  }

  destroy() { this.unsubscribe.forEach(off => off()); this.unsubscribe = []; }

  get newestId() { return this.order.length ? this.order[this.order.length - 1] : 0; }
  get oldestId() { return this.order.length ? this.order[0] : 0; }

  /* --- chargement --- */
  async load() {
    try {
      const page = await App.api.get("/api/chat/history", {topic: this.topic, limit: 50});
      this.lastRead = page.lastRead;
      this.hasMore = page.hasMore;
      this.messages.clear();
      this.order = [];
      page.messages.forEach(m => this.store(m));
      this.renderAll();
      this.scrollToUnreadOrLatest();
      this.markRead();
    } catch (error) {
      this.list.appendChild(App.el("p.chat-error", {text: App.errorText(error)}));
    }
  }

  async loadOlder() {
    if (!this.hasMore || this.loadingOlder) return;
    this.loadingOlder = true;
    const height = this.list.scrollHeight, top = this.list.scrollTop;
    try {
      const page = await App.api.get("/api/chat/history", {topic: this.topic, before: this.oldestId, limit: 50});
      this.hasMore = page.hasMore;
      page.messages.forEach(m => this.store(m));
      this.renderAll();
      // la lecture ne saute pas (en haut : ajoutés au-dessus ; le plus récent en haut : ajoutés au-dessous)
      this.list.scrollTop = this.newestFirst ? top : this.list.scrollHeight - height + top;
    } catch (error) {
      App.toast(App.errorText(error), "error");
    } finally {
      this.loadingOlder = false;
    }
  }

  /** Après une coupure : messages arrivés entre-temps. */
  async catchUp() {
    if (!this.order.length) return this.load();
    try {
      let page;
      do {
        page = await App.api.get("/api/chat/history", {topic: this.topic, after: this.newestId, limit: 200});
        page.messages.forEach(m => this.onLive(m));
      } while (page.messages.length === 200);
    } catch (error) { /* nouvel essai à la prochaine reconnexion */ }
  }

  store(message) {
    if (!this.messages.has(message.id)) {
      this.order.push(message.id);
      this.order.sort((a, b) => a - b);
    }
    this.messages.set(message.id, message);
  }

  /* --- temps réel --- */
  onLive(message) {
    if (message.topic !== this.topic || this.messages.has(message.id)) return;
    const atLatest = this.isAtLatest();
    const mine = message.userId === App.user.id;
    this.store(message);
    if (this.newestFirst) {                                    // ajouté en haut : ce qu'on lisait plus bas ne bouge pas
      const fromEnd = this.list.scrollHeight - this.list.scrollTop;
      this.renderAll();
      this.list.scrollTop = this.list.scrollHeight - fromEnd;
    } else if (message.id === this.newestId) this.appendNode(message);
    else this.renderAll();
    this.typingPeople.delete(message.author);
    this.renderTyping();
    if (mine || atLatest) {
      this.scrollToLatest();
      this.markRead();
    } else {
      this.unseen++;
      this.renderJump();
    }
    App.bus.emit("chat-activity", {topic: this.topic, message, seen: (mine || atLatest) && this.isVisible()});
  }

  onUpdated(message) {
    if (message.topic !== this.topic || !this.messages.has(message.id)) return;
    this.messages.set(message.id, message);
    const old = this.nodes.get(message.id);
    if (old) {
      const fresh = this.messageNode(message, old.classList.contains("grouped"));
      old.replaceWith(fresh);
      this.nodes.set(message.id, fresh);
    }
    // les réponses à ce message montrent son nouvel extrait
    for (const other of this.messages.values()) {
      if (other.replyTo && other.replyTo.id === message.id) {
        other.replyTo = Object.assign({}, other.replyTo, {deleted: message.deleted,
                                                          excerpt: message.deleted ? "" : message.body.slice(0, 120)});
        this.onUpdated(other);
      }
    }
    this.keepLatest();                                       // message modifié, réaction : la hauteur a pu changer
  }

  onTyping(event) {
    if (event.topic !== this.topic) return;
    clearTimeout(this.typingPeople.get(event.user));
    this.typingPeople.set(event.user, setTimeout(() => { this.typingPeople.delete(event.user); this.renderTyping(); }, 4000));
    this.renderTyping();
  }

  renderTyping() {
    const names = Array.from(this.typingPeople.keys());
    this.typingLine.textContent = !names.length ? "" : names.length === 1
      ? App.t("chat.typing_one", {name: names[0]}) : App.t("chat.typing_many");
  }

  /* --- affichage --- */
  /** Bouton « plus anciens » du côté des anciens : en haut, ou en bas quand le plus récent est en haut. */
  renderAll() {
    App.clear(this.list);
    if (!this.newestFirst) this.list.appendChild(this.olderButton);
    this.olderButton.hidden = !this.hasMore;
    this.nodes.clear();
    this.previous = null;
    if (!this.order.length) {
      this.list.appendChild(App.el("p.chat-empty", {text: App.t(this.mode === "room" ? "chat.empty" : "album.comments_empty")}));
      return;
    }
    // « Nouveaux messages » : entre le dernier lu et le premier non lu d'un autre
    const firstUnread = this.lastRead ? this.order.find(id => id > this.lastRead && this.messages.get(id).userId !== App.user.id) : 0;
    const divider = () => {
      this.list.appendChild(App.el("div.unread-divider", {}, App.el("span", {text: App.t("chat.new_messages")})));
      this.previous = null;
    };
    for (const id of this.newestFirst ? this.order.slice().reverse() : this.order) {
      if (id === firstUnread && !this.newestFirst) divider();
      this.appendNode(this.messages.get(id));
      if (id === firstUnread && this.newestFirst) divider();
    }
    if (this.newestFirst) this.list.appendChild(this.olderButton);
  }

  /** Message sous le précédent affiché (previous : plus ancien, ou plus récent quand le plus récent est en haut). */
  appendNode(message) {
    const empty = this.list.querySelector(".chat-empty");
    if (empty) empty.remove();
    const previous = this.previous;
    if (!previous || App.dayLabel(previous.createdAt) !== App.dayLabel(message.createdAt)) {
      this.list.appendChild(App.el("div.day-divider", {}, App.el("span", {text: App.dayLabel(message.createdAt)})));
    }
    const grouped = !!previous && previous.userId === message.userId && !message.replyTo && !previous.deleted &&
      Math.abs(message.createdAt - previous.createdAt) < GROUP_SECONDS &&
      App.dayLabel(previous.createdAt) === App.dayLabel(message.createdAt);
    const node = this.messageNode(message, grouped);
    this.nodes.set(message.id, node);
    this.list.appendChild(node);
    this.previous = message;
  }

  messageNode(message, grouped) {
    const el = App.el;
    const mine = message.userId === App.user.id;
    const mentionsMe = (message.mentions || []).some(n => n.toLowerCase() === App.user.username.toLowerCase());
    const node = el("article.message" + (grouped ? ".grouped" : "") + (mine ? ".mine" : "") +
                    (mentionsMe ? ".mentions-me" : "") + (message.deleted ? ".deleted" : ""),
                    {id: "msg-" + this.topic.replace(":", "-") + "-" + message.id, dataset: {id: message.id}});
    node.appendChild(grouped ? el("span.gutter-time", {text: App.time(message.createdAt), title: App.fullDate(message.createdAt)})
                             : App.avatar(message.author));

    const body = el("div.message-body");
    if (!grouped) {
      body.appendChild(el("header.message-head", {},
        el("strong.author", {text: message.author}),
        el("time", {text: App.time(message.createdAt), title: App.fullDate(message.createdAt),
                    datetime: new Date(message.createdAt * 1000).toISOString()})));
    }
    if (message.replyTo) body.appendChild(this.replyPreview(message.replyTo));
    if (message.deleted) {
      body.appendChild(el("p.message-text.muted", {text: App.t("chat.deleted")}));
    } else {
      if (message.body) {
        const text = el("p.message-text");
        text.appendChild(MessageFormat.render(message.body, {me: App.user.username, usernames: App.usernames}));
        if (message.editedAt) text.appendChild(el("span.edited", {text: " (" + App.t("chat.edited") + ")",
                                                                  title: App.fullDate(message.editedAt)}));
        body.appendChild(text);
      }
      if (message.attachment) body.appendChild(this.attachmentCard(message.attachment));
      const reactions = this.reactionChips(message);
      if (reactions) body.appendChild(reactions);
    }
    node.appendChild(body);
    if (!message.deleted) node.appendChild(this.actions(message, mine));
    return node;
  }

  replyPreview(reply) {
    return App.el("button.reply-preview", {type: "button", onclick: () => this.reveal(reply.id)},
      App.el("span.reply-author", {}, App.icon("reply", 12), " " + reply.author),
      App.el("span.reply-excerpt", {text: reply.deleted ? App.t("chat.deleted") : reply.excerpt}));
  }

  attachmentCard(item) {
    const albumId = item.kind === "album" ? item.id : item.albumId;
    return App.el("a.attachment", {href: albumId ? "#/album/" + encodeURIComponent(albumId) : "#/"},
      App.cover(item.coverId, 56),
      App.el("span.attachment-text", {}, App.el("strong", {text: item.title}), App.el("span", {text: item.artist})));
  }

  reactionChips(message) {
    const entries = Object.entries(message.reactions || {});
    if (!entries.length) return null;
    return App.el("div.reactions", {}, entries.map(([emoji, names]) => App.el(
      "button.reaction" + (names.includes(App.user.username) ? ".mine" : ""),
      {type: "button", title: names.join(", "), onclick: () => this.react(message, emoji)},
      emoji + " " + names.length)));
  }

  actions(message, mine) {
    const el = App.el;
    const bar = el("div.message-actions");
    bar.appendChild(el("button", {type: "button", title: App.t("chat.react"),
                                  onclick: e => this.openReactionPicker(message, e.currentTarget)}, App.icon("smile", 16)));
    bar.appendChild(el("button", {type: "button", title: App.t("chat.reply"), onclick: () => this.startReply(message)}, App.icon("reply", 16)));
    if (mine) bar.appendChild(el("button", {type: "button", title: App.t("chat.edit"), onclick: () => this.startEdit(message)}, App.icon("edit", 16)));
    if (mine || App.user.isAdmin) {
      bar.appendChild(el("button.danger", {type: "button", title: App.t("chat.delete"), onclick: () => this.remove(message)}, App.icon("trash", 16)));
    }
    return bar;
  }

  openReactionPicker(message, anchor) {
    const existing = document.querySelector(".reaction-picker");
    if (existing) existing.remove();
    const picker = App.el("div.reaction-picker", {role: "menu"}, App.reactions.map(emoji => App.el("button", {
      type: "button", text: emoji, onclick: () => { picker.remove(); this.react(message, emoji); }})));
    anchor.parentNode.appendChild(picker);
    const close = e => { if (!picker.contains(e.target)) { picker.remove(); document.removeEventListener("mousedown", close); } };
    setTimeout(() => document.addEventListener("mousedown", close), 0);
  }

  reveal(messageId) {
    const node = this.nodes.get(messageId);
    if (!node) return;
    node.scrollIntoView({block: "center", behavior: "smooth"});
    node.classList.add("flash");
    setTimeout(() => node.classList.remove("flash"), 1600);
  }

  /* --- défilement, non-lus --- */
  isAtBottom() { return this.list.scrollHeight - this.list.scrollTop - this.list.clientHeight < 60; }

  /** Les messages les plus récents sont en vue (en bas, ou en haut quand le plus récent est en haut). */
  isAtLatest() { return this.newestFirst ? this.list.scrollTop < 60 : this.isAtBottom(); }

  /** On était sur les derniers messages : on y reste. */
  keepLatest() {
    if (this.stuck && !this.isAtLatest()) this.list.scrollTop = this.newestFirst ? 0 : this.list.scrollHeight;
  }

  scrollToLatest(clicked) {
    this.list.scrollTop = this.newestFirst ? 0 : this.list.scrollHeight;
    this.unseen = 0;
    this.renderJump();
    if (clicked) this.markRead();
  }

  /** Le plus récent en haut : les non-lus y sont déjà. */
  scrollToUnreadOrLatest() {
    const divider = this.list.querySelector(".unread-divider");
    if (!this.newestFirst && divider && this.list.scrollHeight > this.list.clientHeight) divider.scrollIntoView({block: "center"});
    else this.scrollToLatest();
  }

  onScroll() {
    this.stuck = this.isAtLatest();
    const nearOldest = this.newestFirst ? this.isAtBottom() : this.list.scrollTop < 40;
    if (nearOldest && this.hasMore) this.loadOlder();
    if (this.isAtLatest() && this.unseen) { this.unseen = 0; this.renderJump(); this.markRead(); }
  }

  renderJump() {
    this.jumpButton.hidden = !this.unseen;
    App.setIcon(this.jumpButton, "down", 14, false,                       // flèche tournée vers le haut en CSS si besoin
                App.t("chat.jump_latest") + (this.unseen ? " (" + this.unseen + ")" : ""));
  }

  async markRead() {
    if (!this.newestId || !this.isVisible() || this.newestId <= this.lastRead) return;
    this.lastRead = this.newestId;
    try {
      const result = await App.api.post("/api/chat/read", {topic: this.topic, id: this.newestId});
      App.bus.emit("chat-read", {topic: this.topic, unread: result.unread});
    } catch (error) { /* sans gravité */ }
  }

  /* --- saisie --- */
  onInput() {
    this.textarea.style.height = "auto";
    this.textarea.style.height = Math.min(this.textarea.scrollHeight, 160) + "px";
    this.picker.update();
    const now = Date.now();
    if (this.textarea.value.trim() && !this.editing && now - (this.lastTyping || 0) > 2500) {
      this.lastTyping = now;
      App.api.post("/api/chat/typing", {topic: this.topic}).catch(() => {});
    }
  }

  onKey(event) {
    if (this.picker.key(event)) { event.preventDefault(); return; }
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
      event.preventDefault();
      this.submit();
    } else if (event.key === "Escape") {
      if (this.replyTo || this.editing) { event.preventDefault(); this.cancelContext(); }
    } else if (event.key === "ArrowUp" && !this.textarea.value) {
      const last = this.order.slice().reverse().map(id => this.messages.get(id))
        .find(m => m.userId === App.user.id && !m.deleted);
      if (last) { event.preventDefault(); this.startEdit(last); }
    }
  }

  startReply(message) {
    this.editing = null;
    this.replyTo = message;
    this.showContext(App.t("chat.replying_to", {name: message.author}));
    this.textarea.focus();
  }

  startEdit(message) {
    this.replyTo = null;
    this.editing = message;
    this.textarea.value = message.body;
    this.showContext(App.t("chat.editing"));
    this.onInput();
    this.textarea.focus();
  }

  showContext(text) {
    App.clear(this.contextBar);
    App.append(this.contextBar, [App.el("span", {text}),
      App.el("button.link-button", {type: "button", text: App.t("chat.cancel"), onclick: () => this.cancelContext()})]);
    this.contextBar.hidden = false;
  }

  cancelContext() {
    if (this.editing) this.textarea.value = "";
    this.replyTo = null;
    this.editing = null;
    this.contextBar.hidden = true;
    this.onInput();
  }

  async submit() {
    const body = this.textarea.value.trim();
    if (!body || this.sending) return;
    this.sending = true;
    try {
      if (this.editing) {
        const result = await App.api.post("/api/chat/edit", {id: this.editing.id, body});
        this.onUpdated(result.message);
      } else {
        const result = await App.api.post("/api/chat/post", {topic: this.topic, body,
                                                             replyTo: this.replyTo ? this.replyTo.id : null});
        this.onLive(result.message);        // affiché tout de suite, même avant l'événement temps réel
      }
      this.textarea.value = "";
      this.cancelContext();
    } catch (error) {
      App.toast(App.errorText(error), "error");
    } finally {
      this.sending = false;
    }
  }

  async react(message, emoji) {
    try {
      this.onUpdated((await App.api.post("/api/chat/react", {id: message.id, emoji})).message);
    } catch (error) {
      App.toast(App.errorText(error), "error");
    }
  }

  async remove(message) {
    if (!(await Dialogs.confirm(App.t("chat.confirm_delete")))) return;
    try {
      this.onUpdated((await App.api.post("/api/chat/delete", {id: message.id})).message);
    } catch (error) {
      App.toast(App.errorText(error), "error");
    }
  }
}

/* ---------- panneau de droite ---------- */
class ChatPanel {
  constructor(app) {
    const el = App.el;
    this.app = app;
    this.root = document.getElementById("chat-panel");
    this.badge = document.getElementById("chat-badge");
    this.unread = (App.unread && App.unread.general) || 0;
    this.thread = new ChatThread("general", {mode: "room", isVisible: () => this.isOpen() && this.tab === "room" && !document.hidden});
    this.onlineButton = el("button.online-button", {type: "button", onclick: () => this.toggleOnline()});
    this.onlineList = el("ul.online-list", {hidden: true});
    this.status = el("div.connection-lost", {hidden: true, text: App.t("chat.reconnecting")});
    this.tabs = {};
    this.panes = {room: this.thread.element, mentions: el("div.side-list"), search: this.buildSearch()};
    const tabBar = el("nav.chat-tabs", {role: "tablist"});
    for (const [name, key] of [["room", "chat.title"], ["mentions", "chat.mentions"], ["search", "chat.search"]]) {
      this.tabs[name] = el("button", {type: "button", role: "tab", text: App.t(key), onclick: () => this.show(name)});
      tabBar.appendChild(this.tabs[name]);
    }
    App.append(this.root, [
      el("header.chat-head", {}, el("h2", {text: App.t("chat.title")}), this.onlineButton, this.onlineList),
      tabBar, this.status, this.panes.room, this.panes.mentions, this.panes.search]);
    this.show("room");

    App.live.on("presence", data => this.renderOnline(data.online));
    App.live.on("status", data => { this.status.hidden = data.connected; });
    App.live.on("mention", message => this.onMention(message));
    App.bus.on("chat-activity", event => {
      if (event.topic === "general" && !event.seen && event.message.userId !== App.user.id) this.setUnread(this.unread + 1);
    });
    App.bus.on("chat-read", event => { if (event.topic === "general") this.setUnread(event.unread); });
    App.bus.on("preferences", () => this.applyOpen());
    document.addEventListener("visibilitychange", () => { if (!document.hidden && this.isOpen()) this.thread.markRead(); });
    this.setUnread(this.unread);
    this.applyOpen();
  }

  start() {
    this.thread.load();
    App.api.get("/api/chat/online").then(data => this.renderOnline(data.online)).catch(() => {});
  }

  isOpen() { return (App.preferences.chat_panel || "open") === "open"; }

  applyOpen() {
    document.body.dataset.chat = this.isOpen() ? "open" : "closed";
    if (this.isOpen() && this.tab === "room") { this.thread.scrollToLatest(); this.thread.markRead(); }
  }

  /** Les paroles occupent la même place : si elles sont affichées, le salon revient à leur place. */
  toggle() {
    if (App.lyrics && App.lyrics.isOpen()) {
      App.lyrics.close();
      if (this.isOpen()) return;
    }
    App.savePreference("chat_panel", this.isOpen() ? "closed" : "open");
  }

  show(name) {
    this.tab = name;
    for (const [key, pane] of Object.entries(this.panes)) {
      pane.hidden = key !== name;
      this.tabs[key].classList.toggle("active", key === name);
      this.tabs[key].setAttribute("aria-selected", String(key === name));
    }
    if (name === "mentions") this.loadMentions();
    if (name === "search") this.searchInput.focus();
    if (name === "room") this.thread.markRead();
  }

  setUnread(count) {
    this.unread = Math.max(0, count);
    this.badge.hidden = !this.unread;
    this.badge.textContent = this.unread > 99 ? "99+" : String(this.unread);
    this.app.updateTitle(this.unread);
  }

  renderOnline(names) {
    this.onlineButton.textContent = "● " + names.length + " " + App.t("chat.online").toLowerCase();
    App.clear(this.onlineList);
    names.forEach(name => this.onlineList.appendChild(App.el("li", {text: name})));
  }

  toggleOnline() { this.onlineList.hidden = !this.onlineList.hidden; }

  async loadMentions() {
    const pane = App.clear(this.panes.mentions);
    try {
      const messages = (await App.api.get("/api/chat/mentions")).messages;
      if (!messages.length) pane.appendChild(App.el("p.chat-empty", {text: App.t("chat.mentions_empty")}));
      messages.forEach(m => pane.appendChild(this.resultRow(m)));
    } catch (error) {
      pane.appendChild(App.el("p.chat-error", {text: App.errorText(error)}));
    }
  }

  buildSearch() {
    this.searchInput = App.el("input.sidebar-filter", {type: "search", placeholder: App.t("chat.search_placeholder")});
    this.searchResults = App.el("div.side-list");
    let timer = null;
    this.searchInput.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(() => this.search(this.searchInput.value), 300);
    });
    return App.el("div.chat-search", {}, this.searchInput, this.searchResults);
  }

  async search(text) {
    const pane = App.clear(this.searchResults);
    if (text.trim().length < 2) return;
    try {
      const messages = (await App.api.get("/api/chat/search", {topic: "general", q: text})).messages;
      if (!messages.length) pane.appendChild(App.el("p.chat-empty", {text: App.t("chat.search_empty")}));
      messages.forEach(m => pane.appendChild(this.resultRow(m)));
    } catch (error) {
      pane.appendChild(App.el("p.chat-error", {text: App.errorText(error)}));
    }
  }

  /** Message trouvé (mention ou recherche) : un clic l'ouvre là où il a été écrit. */
  resultRow(message) {
    const album = message.topic.startsWith("album:") ? message.topic.slice(6) : null;
    const row = App.el("button.result-row", {type: "button", onclick: () => {
      if (album) location.hash = "#/album/" + encodeURIComponent(album);
      else { this.show("room"); this.thread.reveal(message.id); }
    }},
      App.el("span.result-meta", {text: message.author + " · " + App.dayLabel(message.createdAt) + " " + App.time(message.createdAt)}),
      App.el("span.result-text"));
    row.lastChild.appendChild(MessageFormat.render(message.body, {me: App.user.username, usernames: App.usernames}));
    return row;
  }

  onMention(message) {
    if (!App.preferences.notify_mentions) return;
    const text = App.t("chat.mention_notice", {name: message.author});
    if (document.hidden && typeof Notification !== "undefined" && Notification.permission === "granted") {
      const notice = new Notification(text, {body: message.body.slice(0, 140), tag: "pmw-" + message.id});
      notice.onclick = () => { window.focus(); notice.close(); };
    } else {
      App.toast(text + " : " + message.body.slice(0, 80));
    }
  }

  /** Partage d'un album ou d'un titre dans le salon (carte cliquable). */
  async share(attachment) {
    try {
      const result = await App.api.post("/api/chat/post", {topic: "general", body: "", attachment});
      this.thread.onLive(result.message);
      App.toast(App.t("album.shared"));
    } catch (error) {
      App.toast(App.errorText(error), "error");
    }
  }
}
