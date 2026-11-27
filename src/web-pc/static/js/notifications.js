"use strict";
/* Messages privés de l’administration : le compteur est relu après reconnexion SSE. */
const NotificationsUI = (() => {
  const el = App.el, t = (key, params) => App.t("notifications." + key, params);
  let generation = 0, listening = false;

  function indicator(count) {
    const badge = document.getElementById("notifications-badge");
    if (!badge) return;
    badge.hidden = !count;
    document.getElementById("account-notifications-badge").hidden = !count;
    const toggle = document.getElementById("account-toggle");
    const label = count ? App.t("nav.account_notifications", {count}) : App.t("nav.account_menu");
    toggle.setAttribute("aria-label", label);
    toggle.title = label;
    badge.textContent = count > 99 ? "99+" : String(count || "");
    document.getElementById("nav-notifications").setAttribute("aria-label", t("nav_count", {count}));
  }

  function reset() { generation++; indicator(0); }

  async function refresh() {
    const current = ++generation, owner = App.user && App.user.id;
    if (!owner) return;
    try {
      const data = await App.api.get("/api/notifications/status");
      if (current === generation && App.user && App.user.id === owner) indicator(data.unread);
    } catch (error) { /* Une coupure conserve la pastille ; la reconnexion relit l’état durable. */ }
  }

  function start() {
    reset();
    if (!listening) {
      listening = true;
      App.live.on("notifications", () => refresh());
      App.live.on("reconnected", () => refresh());
      document.addEventListener("visibilitychange", () => {
        if (!document.hidden && App.user && !document.getElementById("app").hidden) refresh();
      });
    }
    refresh();
  }

  async function composer(main, route, owner, limits) {
    const section = el("details.notification-compose", {}, el("summary", {text: t("compose")}));
    main.appendChild(section);
    try {
      const data = await App.api.get("/api/notifications/recipients");
      if (route.stale || App.user.id !== owner) return;
      const recipient = el("select", {required: true, name: "recipient"},
        el("option", {value: "", text: t("choose_recipient")}),
        ...data.usernames.map(name => el("option", {value: name, text: name})));
      const title = el("input", {required: true, name: "title", maxLength: limits.title});
      const body = el("textarea", {required: true, name: "body", maxLength: limits.body});
      const submit = el("button.primary", {type: "submit", text: t("send")});
      const status = el("p.notifications-status", {role: "status"});
      const field = (key, input) => el("label", {}, el("span", {text: t(key)}), input);
      let requestId = null;
      const form = el("form", {}, field("recipient", recipient), field("subject", title), field("message", body), submit, status);
      form.addEventListener("input", () => { requestId = null; });
      form.addEventListener("submit", async event => {
        event.preventDefault();
        if (submit.disabled || !form.reportValidity()) return;
        submit.disabled = true;
        const payload = {recipient: recipient.value, title: title.value, body: body.value,
          requestId: requestId || (requestId = App.requestId())};
        status.textContent = t("sending");
        try {
          await App.api.post("/api/notifications/send", payload);
          if (route.stale || App.user.id !== owner) return;
          form.reset(); requestId = null;
          status.textContent = t("sent", {name: payload.recipient});
          refresh();
        } catch (error) {
          if (!route.stale && App.user.id === owner) status.textContent = App.errorText(error);
        } finally { if (!route.stale && App.user.id === owner) submit.disabled = false; }
      });
      section.appendChild(form);
    } catch (error) {
      if (!route.stale && App.user.id === owner) section.appendChild(el("p.page-error", {text: App.errorText(error)}));
    }
  }

  async function render(main, route) {
    const owner = App.user.id;
    App.clear(main).appendChild(el("h1", {text: t("title")}));
    main.appendChild(el("p.muted.notifications-intro", {text: t("intro")}));
    main.appendChild(el("button.notifications-refresh", {text: t("refresh"), onclick: () => render(main, route)}));
    const list = el("div.notifications-list"), status = el("p.notifications-status", {role: "status"});
    const more = el("button.notifications-more", {text: t("more"), hidden: true});
    main.append(list, status, more);
    let before = null, loading = false;
    const alive = () => !route.stale && App.user && App.user.id === owner && list.isConnected;

    function card(entry) {
      const read = el("button.notification-read", {text: t("mark_read"), hidden: entry.readAt !== null});
      const node = el("article.notification-card" + (entry.readAt === null ? ".unread" : ""), {dataset: {id: entry.id}},
        el("h2", {text: entry.title}), el("p.notification-meta", {text: t("from_admin") + " · " + App.fullDate(entry.createdAt)}),
        el("p.notification-body", {text: entry.body}), read);
      read.addEventListener("click", async () => {
        if (read.disabled) return;
        read.disabled = true;
        try {
          await App.api.post("/api/notifications/read", {id: entry.id});
          if (!alive()) return;
          read.hidden = true; node.classList.remove("unread"); refresh();
        } catch (error) { if (alive()) status.textContent = App.errorText(error); }
        finally { if (alive()) read.disabled = false; }
      });
      return node;
    }

    async function load() {
      if (loading) return;
      loading = true; more.disabled = true; status.textContent = "";
      try {
        const data = await App.api.get("/api/notifications", before ? {before} : {});
        if (!alive()) return;
        data.entries.forEach(entry => list.appendChild(card(entry)));
        if (!list.children.length) status.textContent = t("empty");
        before = data.before; more.hidden = !before; more.textContent = t("more");
        // Le compteur passe par une lecture dédiée pour écarter toute réponse arrivée en retard.
        refresh();
        if (App.can("admin") && !main.querySelector(".notification-compose")) composer(main, route, owner, data.limits);
      } catch (error) {
        if (alive()) {
          status.textContent = App.errorText(error);
          more.hidden = false; more.textContent = t("retry");
        }
      } finally { loading = false; if (alive()) more.disabled = false; }
    }
    more.addEventListener("click", load);
    await load();
  }

  return {start, reset, render};
})();
Views.notifications = {render: NotificationsUI.render};
