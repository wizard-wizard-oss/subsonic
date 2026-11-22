"use strict";
/* Personal musical bookmarks and received recommendations. Search and playback use existing services. */
const ListenLaterUI = (() => {
  const el = App.el, t = (key, params) => App.t("listen_later." + key, params);
  let state = null, pending = null, generation = 0;
  let notificationGeneration = 0, renderGeneration = 0, listenersReady = false;
  let playbackGeneration = 0, unreadDiscussion = null, selectedKind = "all";
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
    playbackGeneration++;
    selectedKind = "all";
    RecommendationComments.reset();
    showIndicator(false);
  }

  function showIndicator(unread, discussion = null) {
    unreadDiscussion = discussion;
    document.querySelectorAll(".recommendation-unread-comments").forEach(button => { button.hidden = !discussion; });
    document.querySelectorAll('.topnav a[href="#/listen-later"]').forEach(link => {
      const label = unread ? t("unread_label") : App.t("nav.listen_later");
      link.classList.toggle("recommendations-unread", unread);
      link.setAttribute("aria-label", label);
      link.title = label;
    });
  }

  async function refreshNotifications(refreshPage = false, forcePage = false) {
    const current = ++notificationGeneration, owner = App.user && App.user.id;
    if (!owner) return;
    try {
      const data = await App.api.get("/api/recommendation/status");
      if (current !== notificationGeneration || !App.user || App.user.id !== owner) return;
      showIndicator(data.unread, data.unreadDiscussion);
      const route = App.music && App.music.route;
      if (refreshPage && (data.unread || forcePage) && !document.hidden && route && route.view === "listenLater") {
        await page.render(App.music.main, route);
      }
    } catch (failure) { /* Keep the current indicator; reconnecting or revisiting retries. */ }
  }

  function start() {
    if (!listenersReady) {
      const refresh = (data = {}) => {
        invalidate(); RecommendationComments.refresh(); refreshNotifications(true, !!data.discussionId);
      };
      App.live.on("recommendations", refresh);
      App.bus.on("recommendations", refresh);
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
      ondblclick: event => event.stopPropagation(),
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

  async function recommend(target) {
    const owner = App.user.id;
    const names = App.usernames.filter(name => name.toLowerCase() !== App.user.username.toLowerCase());
    if (!names.length) { App.toast(t("no_recipient")); return; }
    let data = state;
    if (!data) {
      try { data = await load(); } catch (failure) { App.toast(App.errorText(failure), "error"); return; }
    }
    if (!App.user || App.user.id !== owner) return;
    const comment = RecommendationComments.field(data.commentMaxLength, true);
    const select = el("select.recommendation-recipient", {required: true},
      names.map(name => el("option", {value: name, text: name})));
    const error = el("p.page-error", {role: "alert"});
    const submit = el("button.primary", {type: "submit", text: t("send")});
    const form = el("form.recommendation-form", {onsubmit: async event => {
      event.preventDefault();
      if (App.user.id !== owner) { Dialogs.close(); return; }
      if (submit.disabled) return;
      submit.disabled = true;
      error.textContent = "";
      try {
        const result = await App.api.post("/api/recommendation/send", Object.assign(reference(target), {
          recipient: select.value, comment: comment.input.value}));
        if (!form.isConnected || !App.user || App.user.id !== owner) return;
        Dialogs.close();
        App.bus.emit("recommendations", {discussionId: result.recommendation.id});
        if (result.created) {
          App.toast(t("sent"), "", {label: t("comments"), run: () => RecommendationComments.open(result.recommendation)});
        } else {
          RecommendationComments.open(result.recommendation, comment.input.value);
          App.toast(t("already_sent"));
        }
      } catch (failure) { if (form.isConnected) error.textContent = App.errorText(failure); }
      finally { submit.disabled = false; }
    }}, el("label", {}, el("span", {text: t("recipient")}), select), comment.node, error, submit);
    Dialogs.open(t("recommend"), form);
  }

  function recommendButton(target, compact = false) {
    return App.setIcon(el("button.recommendation-open." + (compact ? "link-button" : "icon-button"), {
        type: "button", title: t("recommend"), "aria-label": t("recommend"),
        onclick: event => { event.stopPropagation(); recommend(target); },
        ondblclick: event => event.stopPropagation()}), "reply", compact ? 16 : 18);
  }

  function actions(target) {
    return el("span.listening-actions", {}, button(target), recommendButton(target));
  }

  function searchPath(target) {
    const query = [target.artist, target.title].filter(Boolean).join(" ");
    return "#/search/" + encodeURIComponent(query);
  }

  function openLink(target) {
    let href;
    if (target.kind === "song") href = searchPath(target);
    else if (target.source === "subsonic") href = "#/" + target.kind + "/" + encodeURIComponent(target.sourceId);
    else if (target.kind === "artist") href = "#/discogs/artist/" + encodeURIComponent(target.sourceId);
    else href = "https://www.discogs.com/release/" + encodeURIComponent(target.sourceId);
    const props = {href, text: target.title};
    if (!href.startsWith("#")) Object.assign(props, {target: "_blank", rel: "noopener noreferrer"});
    return el("a.listen-later-name", props);
  }

  function searchLink(target) {
    return el("a.button.listen-later-search", {
      href: searchPath(target), text: t("search_listening")});
  }

  async function playSongs(targets, node, startId) {
    if (node.disabled || !App.can("stream")) return;
    const owner = App.user.id, playback = ++playbackGeneration;
    const current = () => playback === playbackGeneration && node.isConnected &&
      App.user && App.user.id === owner && App.can("stream");
    node.disabled = true;
    node.setAttribute("aria-busy", "true");
    try {
      const resolved = new Array(targets.length);
      let next = 0;
      const load = async () => {
        while (next < targets.length && current()) {
          const index = next++;
          try {
            resolved[index] = (await App.api.get("/api/song", {id: targets[index].sourceId})).song;
          } catch (failure) {
            if (!(failure instanceof ApiError) || failure.status !== 404) throw failure;
          }
        }
      };
      await Promise.all(Array.from({length: Math.min(4, targets.length)}, load));
      if (!current()) return;
      const songs = resolved.filter(Boolean);
      const start = startId ? songs.findIndex(song => song.id === startId) : 0;
      if (!songs.length || start < 0) { App.toast(t("song_unavailable"), "error"); return; }
      App.player.playList(songs, start);
      if (songs.length < targets.length) App.toast(t("songs_skipped", {count: targets.length - songs.length}));
    } catch (failure) {
      if (current()) { playbackGeneration++; App.toast(App.errorText(failure), "error"); }
    } finally {
      node.disabled = false;
      node.removeAttribute("aria-busy");
    }
  }

  function card(target, controls, caption) {
    const image = App.cover(target.imageRef, 72, target.title);
    image.hidden = true;
    image.addEventListener("load", () => { image.hidden = false; });
    image.addEventListener("error", () => { image.hidden = true; });
    const artwork = el("div.listen-later-artwork", {},
      App.icon({artist: "mic", album: "disc", song: "music"}[target.kind], 30), image);
    return el("article.listen-later-card", {}, artwork,
      el("div.listen-later-details", {}, openLink(target),
        target.artist ? el("span.muted", {text: target.artist}) : null,
        el("span.muted", {text: t("kinds." + target.kind) + " · " + t("sources." + target.source)}),
        caption || null,
        el("div.listen-later-actions", {},
          target.kind === "song" && App.can("stream") ? App.setIcon(el("button.listen-later-play", {
            type: "button", onclick: event => playSongs([target], event.currentTarget)}),
            "play", 16, false, t("play_song")) : null,
          searchLink(target), controls)));
  }

  async function remove(path, body, main, route) {
    try {
      await App.api.post(path, body);
      await changed();
      if (!route.stale) await page.render(main, route, false);
    } catch (failure) { App.toast(App.errorText(failure), "error"); }
  }

  function songRecommendations(groups, main, route) {
    const targets = groups.map(group => group.target);
    const table = el("table.songs.recommendation-songs-table", {},
      el("thead", {}, el("tr", {},
        el("th.title", {scope: "col", text: SongColumns.label("title")}),
        el("th.song-artist", {scope: "col", text: SongColumns.label("artist")}),
        el("th", {scope: "col", text: t("advisers")}),
        el("th.more", {scope: "col", "aria-label": SongColumns.label("actions")}))),
      el("tbody", {}, groups.map(group => {
        const target = group.target;
        const keep = button(target, () => !route.stale && page.render(main, route, false));
        keep.classList.add("link-button");
        return el("tr.song", {dataset: {id: target.sourceId},
          ondblclick: event => playSongs(targets, event.currentTarget, target.sourceId)},
          el("td.title", {}, App.can("stream") ? el("button.row-play", {
            type: "button", title: t("play_song"), "aria-label": t("play_song"),
            onclick: event => playSongs(targets, event.currentTarget, target.sourceId),
            ondblclick: event => event.stopPropagation()}, App.icon("play", 14)) : null,
            el("span", {text: target.title})),
          el("td.song-artist.muted", {text: target.artist}),
          el("td.recommendation-senders", {},
            el("span.muted", {text: group.senders.map(sender => sender.username).join(", ")}),
            group.recommendations.map(RecommendationComments.summary)),
          el("td.more", {}, keep, recommendButton(target, true),
            el("button.link-button.recommendation-remove", {
              type: "button", title: t("dismiss"), "aria-label": t("dismiss"),
              onclick: () => remove("/api/recommendation/remove", reference(target), main, route),
              ondblclick: event => event.stopPropagation()}, App.icon("close", 16))));
      })));
    const highlight = () => table.querySelectorAll("tr.song").forEach(row => {
      row.classList.toggle("playing", !!App.player.current && row.dataset.id === App.player.current.id);
    });
    highlight();
    table.destroy = App.bus.on("queue", highlight);
    page.table = table;
    return el("div.recommendation-songs", {},
      el("div.recommendation-songs-head", {},
        el("h3", {text: t("recommended_songs")}),
        el("span.muted", {text: App.plural("album.tracks", targets.length)}),
        App.can("stream") ? App.setIcon(el("button.recommendation-play-all", {
          type: "button", onclick: event => playSongs(targets, event.currentTarget)}),
          "play", 16, false, t("play_all")) : null),
      el("div.recommendation-songs-scroll", {}, table));
  }

  function discussionList(scope, route, show) {
    const owner = App.user.id, list = el("div.listen-later-list"), error = el("p.page-error", {role: "alert"});
    const more = el("button.recommendation-discussions-more", {type: "button", text: t("more_recommendations"), hidden: true});
    const empty = el("p.muted", {hidden: true});
    const root = el("div.recommendation-discussions", {}, list, empty, error, more);
    const cards = [];
    root.applyFilter = () => {
      cards.forEach(({node, target}) => { node.hidden = !show(target); });
      empty.textContent = t(cards.length ? "empty_discussions_filter" : "empty_" + scope);
      empty.hidden = cards.some(({node}) => !node.hidden);
    };
    let before = null, loading = false;
    const current = () => !route.stale && root.isConnected && App.user && App.user.id === owner;
    const fetchPage = async () => {
      if (loading) return;
      loading = more.disabled = true;
      error.textContent = "";
      try {
        const data = await App.api.get("/api/recommendation/discussions", Object.assign({scope}, before ? {before} : {}));
        if (!current()) return;
        for (const recommendation of data.recommendations) {
          const node = card(recommendation.target, [], el("div", {}, el("p.muted", {text: t("discussion_participants", {
            sender: recommendation.sender, recipient: recommendation.recipient})}), RecommendationComments.summary(recommendation)));
          cards.push({node, target: recommendation.target});
          list.appendChild(node);
        }
        root.applyFilter();
        if (data.recommendations.length) before = data.recommendations[data.recommendations.length - 1].id;
        more.hidden = !data.hasMore;
      } catch (failure) {
        if (current()) { error.textContent = App.errorText(failure); more.hidden = false; }
      } finally { loading = more.disabled = false; }
    };
    more.onclick = fetchPage;
    // Start once the surrounding page has attached the list.
    Promise.resolve().then(fetchPage);
    return root;
  }

  const page = {
    table: null,
    destroy() {
      playbackGeneration++;
      if (this.table) this.table.destroy();
      this.table = null;
    },
    async render(main, route, refresh = true) {
      this.destroy();
      const render = ++renderGeneration;
      main.textContent = t("loading");
      try {
        const data = await load(refresh);
        if (route.stale || render !== renderGeneration) return;
        const filter = el("select.listen-later-filter", {"aria-label": t("filter")},
          ["all", "artist", "album", "song"].map(kind => el("option", {value: kind, text: t("filters." + kind)})));
        const bookmarks = el("div.listen-later-list.bookmark-list");
        const recommendations = el("div.listen-later-list.recommendation-list");
        filter.value = selectedKind;
        const show = target => filter.value === "all" || target.kind === filter.value;
        const sent = discussionList("sent", route, show), archived = discussionList("archived", route, show);
        const draw = () => {
          this.destroy();
          const own = data.bookmarks.filter(entry => show(entry.target));
          const received = data.recommendations.filter(group => show(group.target));
          const songs = received.filter(group => group.target.kind === "song");
          App.append(App.clear(bookmarks), [own.length ? own.map(entry => card(entry.target, [
            el("button.listen-later-remove", {type: "button", text: t("remove_bookmark"),
              onclick: () => remove("/api/listen-later/remove", {id: entry.id}, main, route)}),
            recommendButton(entry.target)
          ])) : el("p.muted", {text: t("empty_bookmarks")})]);
          App.append(App.clear(recommendations), [received.length ? received.filter(group => group.target.kind !== "song").map(group => card(group.target, [
            button(group.target, () => !route.stale && page.render(main, route, false), true),
            el("button.recommendation-remove", {type: "button", text: t("dismiss"),
              onclick: () => remove("/api/recommendation/remove", reference(group.target), main, route)})
          ], el("div.recommendation-senders", {}, el("p", {
            text: App.t("listen_later.recommended_by", {names: group.senders.map(sender => sender.username).join(", ")})}),
            group.recommendations.map(RecommendationComments.summary))))
            : el("p.muted", {text: t("empty_recommendations")}),
            songs.length ? songRecommendations(songs, main, route) : null]);
        };
        filter.onchange = () => { selectedKind = filter.value; draw(); sent.applyFilter(); archived.applyFilter(); };
        App.append(App.clear(main), [el("h1", {text: t("title")}), el("p.muted", {text: t("intro")}),
          el("button.recommendation-unread-comments", {type: "button", text: t("open_unread_comments"),
            hidden: !unreadDiscussion, onclick: () => { if (unreadDiscussion) RecommendationComments.open(unreadDiscussion); }}),
          el("label.listen-later-filter-label", {}, el("span", {text: t("filter")}), filter),
          el("section.listen-later-bookmarks", {}, Views.heading(t("bookmarks")), bookmarks),
          el("section.listen-later-recommendations", {}, Views.heading(t("recommendations")), recommendations),
          el("section.listen-later-sent", {}, Views.heading(t("sent_recommendations")), sent),
          el("details.listen-later-archived", {}, el("summary", {text: t("archived_recommendations")}),
            archived)]);
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
  return {actions, button, recommendButton, reset, start};
})();
