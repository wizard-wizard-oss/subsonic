"use strict";
/* Personal artist/album bookmarks and received recommendations. Search and playback use existing views. */
const ListenLaterUI = (() => {
  const el = App.el, t = key => App.t("listen_later." + key);
  let state = null, pending = null, generation = 0;
  let notificationGeneration = 0, renderGeneration = 0, listenersReady = false;
  const key = target => JSON.stringify([target.kind, target.source, target.sourceId]);
  const reference = target => ({kind: target.kind, source: target.source, sourceId: target.sourceId});

  function invalidate() {
    generation++;
    state = pending = null;
  }

  function reset() {
    invalidate();
    notificationGeneration++;
    renderGeneration++;
    showIndicator(false);
  }

  function showIndicator(unread) {
    document.querySelectorAll('.topnav a[href="#/listen-later"]').forEach(link => {
      const label = unread ? t("unread_label") : App.t("nav.listen_later");
      link.classList.toggle("recommendations-unread", unread);
      link.setAttribute("aria-label", label);
      link.title = label;
    });
  }

  async function refreshNotifications(refreshPage = false) {
    const current = ++notificationGeneration, owner = App.user && App.user.id;
    if (!owner) return;
    try {
      const data = await App.api.get("/api/recommendation/status");
      if (current !== notificationGeneration || !App.user || App.user.id !== owner) return;
      showIndicator(data.unread);
      const route = App.music && App.music.route;
      if (refreshPage && data.unread && !document.hidden && route && route.view === "listenLater") {
        await page.render(App.music.main, route);
      }
    } catch (failure) { /* Keep the current indicator; reconnecting or revisiting retries. */ }
  }

  function start() {
    if (!listenersReady) {
      const refresh = () => { invalidate(); refreshNotifications(true); };
      App.live.on("recommendations", refresh);
      App.live.on("status", status => { if (status.connected) refresh(); });
      document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(); });
      listenersReady = true;
    }
    refreshNotifications();
  }

  async function acknowledge(data, route, render) {
    const tokens = data.recommendations.flatMap(group => group.unreadTokens || []);
    if (!tokens.length || document.hidden) return;
    const owner = App.user.id;
    showIndicator(true);
    notificationGeneration++;
    try {
      for (let offset = 0; offset < tokens.length; offset += data.readBatchSize) {
        if (route.stale || render !== renderGeneration || document.hidden || App.user.id !== owner) return;
        await App.api.post("/api/recommendation/read", {tokens: tokens.slice(offset, offset + data.readBatchSize)});
      }
      if (App.user.id === owner) await refreshNotifications();
    } catch (failure) { /* Reading failed: leave the indicator and retry when this page is opened again. */ }
  }

  function saved(target) {
    return state && state.bookmarks.find(entry => key(entry.target) === key(target));
  }

  function updateButton(node, target) {
    const active = !!saved(target), label = t(active ? "remove_bookmark" : "add_bookmark");
    node.setAttribute("aria-pressed", String(active));
    node.setAttribute("aria-label", label);
    node.title = label;
    node.classList.toggle("on", active);
    App.setIcon(node, "bookmark", 18, active, node.dataset.labelled === "true" ? t(active ? "saved" : "keep") : null);
  }

  function updateButtons() {
    document.querySelectorAll(".listen-later-toggle").forEach(node => updateButton(node, node.dataset));
  }

  function load(force = false) {
    if (!force && state) return Promise.resolve(state);
    if (pending) return pending;
    const current = generation;
    pending = App.api.get("/api/listen-later").then(data => {
      if (current !== generation) return load();
      state = data;
      updateButtons();
      return data;
    }).finally(() => { if (current === generation) pending = null; });
    return pending;
  }

  async function changed() {
    invalidate();
    await load(true);
  }

  function button(target, onChanged, labelled = false) {
    const node = App.setIcon(el("button.listen-later-toggle" + (labelled ? ".listen-later-keep" : ".icon-button"), {
      type: "button", dataset: Object.assign(reference(target), {labelled: String(labelled)}), title: t("add_bookmark"), "aria-label": t("add_bookmark"),
      "aria-pressed": "false", disabled: true,
      onclick: async () => {
        node.disabled = true;
        const owner = App.user.id;
        try {
          await load();
          if (App.user.id !== owner) return;
          const entry = saved(target);
          await App.api.post(entry ? "/api/listen-later/remove" : "/api/listen-later/add",
            entry ? {id: entry.id} : reference(target));
          if (App.user.id !== owner) return;
          await changed();
          if (onChanged) await onChanged();
          App.toast(t(entry ? "bookmark_removed" : "bookmark_added"), "",
            entry ? null : {label: t("open_list"), run: () => { location.hash = "#/listen-later"; }});
        } catch (failure) { App.toast(App.errorText(failure), "error"); }
        finally { node.disabled = false; }
      }
    }), "bookmark", 18);
    load().then(() => updateButton(node, target)).catch(() => {}).finally(() => { node.disabled = false; });
    return node;
  }

  function recommend(target) {
    const owner = App.user.id;
    const names = App.usernames.filter(name => name.toLowerCase() !== App.user.username.toLowerCase());
    if (!names.length) { App.toast(t("no_recipient")); return; }
    const select = el("select.recommendation-recipient", {required: true},
      names.map(name => el("option", {value: name, text: name})));
    const error = el("p.page-error", {role: "alert"});
    const submit = el("button.primary", {type: "submit", text: t("send")});
    const form = el("form.recommendation-form", {onsubmit: async event => {
      event.preventDefault();
      if (App.user.id !== owner) { Dialogs.close(); return; }
      submit.disabled = true;
      error.textContent = "";
      try {
        await App.api.post("/api/recommendation/send", Object.assign(reference(target), {recipient: select.value}));
        if (!form.isConnected) return;
        Dialogs.close();
        App.toast(t("sent"));
      } catch (failure) { if (form.isConnected) error.textContent = App.errorText(failure); }
      finally { submit.disabled = false; }
    }}, el("label", {}, el("span", {text: t("recipient")}), select), error, submit);
    Dialogs.open(t("recommend"), form);
  }

  function actions(target) {
    return el("span.listening-actions", {}, button(target),
      App.setIcon(el("button.icon-button.recommendation-open", {
        type: "button", title: t("recommend"), "aria-label": t("recommend"),
        onclick: () => recommend(target)}), "reply", 18));
  }

  function openLink(target) {
    let href;
    if (target.source === "subsonic") href = "#/" + target.kind + "/" + encodeURIComponent(target.sourceId);
    else if (target.kind === "artist") href = "#/discogs/artist/" + encodeURIComponent(target.sourceId);
    else href = "https://www.discogs.com/release/" + encodeURIComponent(target.sourceId);
    const props = {href, text: target.title};
    if (!href.startsWith("#")) Object.assign(props, {target: "_blank", rel: "noopener noreferrer"});
    return el("a.listen-later-name", props);
  }

  function searchLink(target) {
    const query = [target.artist, target.title].filter(Boolean).join(" ");
    return el("a.button.listen-later-search", {
      href: "#/search/" + encodeURIComponent(query), text: t("search_listening")});
  }

  function card(target, controls, caption) {
    const image = App.cover(target.imageRef, 72, target.title);
    image.hidden = true;
    image.addEventListener("load", () => { image.hidden = false; });
    image.addEventListener("error", () => { image.hidden = true; });
    const artwork = el("div.listen-later-artwork", {},
      App.icon(target.kind === "artist" ? "mic" : "disc", 30), image);
    return el("article.listen-later-card", {}, artwork,
      el("div.listen-later-details", {}, openLink(target),
        target.artist ? el("span.muted", {text: target.artist}) : null,
        el("span.muted", {text: t("kinds." + target.kind) + " · " + t("sources." + target.source)}),
        caption || null,
        el("div.listen-later-actions", {}, searchLink(target), controls)));
  }

  async function remove(path, body, main, route) {
    try {
      await App.api.post(path, body);
      await changed();
      if (!route.stale) await page.render(main, route, false);
    } catch (failure) { App.toast(App.errorText(failure), "error"); }
  }

  const page = {
    async render(main, route, refresh = true) {
      const render = ++renderGeneration;
      main.textContent = t("loading");
      try {
        const data = await load(refresh);
        if (route.stale || render !== renderGeneration) return;
        const filter = el("select.listen-later-filter", {"aria-label": t("filter")},
          ["all", "artist", "album"].map(kind => el("option", {value: kind, text: t("filters." + kind)})));
        const bookmarks = el("div.listen-later-list.bookmark-list");
        const recommendations = el("div.listen-later-list.recommendation-list");
        const show = target => filter.value === "all" || target.kind === filter.value;
        const draw = () => {
          const own = data.bookmarks.filter(entry => show(entry.target));
          const received = data.recommendations.filter(group => show(group.target));
          App.append(App.clear(bookmarks), [own.length ? own.map(entry => card(entry.target, [
            el("button.listen-later-remove", {type: "button", text: t("remove_bookmark"),
              onclick: () => remove("/api/listen-later/remove", {id: entry.id}, main, route)}),
            App.setIcon(el("button.icon-button", {type: "button", title: t("recommend"),
              "aria-label": t("recommend"), onclick: () => recommend(entry.target)}), "reply", 18)
          ])) : el("p.muted", {text: t("empty_bookmarks")})]);
          App.append(App.clear(recommendations), [received.length ? received.map(group => card(group.target, [
            button(group.target, () => !route.stale && page.render(main, route, false), true),
            el("button.recommendation-remove", {type: "button", text: t("dismiss"),
              onclick: () => remove("/api/recommendation/remove", reference(group.target), main, route)})
          ], el("p.recommendation-senders", {
            text: App.t("listen_later.recommended_by", {names: group.senders.map(sender => sender.username).join(", ")})})))
            : el("p.muted", {text: t("empty_recommendations")})]);
        };
        filter.onchange = draw;
        App.append(App.clear(main), [el("h1", {text: t("title")}), el("p.muted", {text: t("intro")}),
          el("label.listen-later-filter-label", {}, el("span", {text: t("filter")}), filter),
          el("section.listen-later-bookmarks", {}, Views.heading(t("bookmarks")), bookmarks),
          el("section.listen-later-recommendations", {}, Views.heading(t("recommendations")), recommendations)]);
        draw();
        await acknowledge(data, route, render);
      } catch (failure) {
        if (route.stale || render !== renderGeneration) return;
        App.append(App.clear(main), [el("p.page-error", {role: "alert", text: App.errorText(failure)}),
          el("button", {type: "button", text: t("retry"), onclick: () => page.render(main, route)})]);
      }
    }
  };

  Views.listenLater = page;
  return {actions, button, reset, start};
})();
