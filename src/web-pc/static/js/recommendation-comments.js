"use strict";
/* One private comment component, shared by received, sent and archived recommendations. */
const RecommendationComments = (() => {
  const el = App.el, t = (key, params) => App.t("listen_later." + key, params);
  const views = new Set();  // fils affichés : la fenêtre de dialogue et tous les fils dépliés dans la page

  function field(maxLength, optional = false) {
    const input = el("textarea.recommendation-comment-input", {
      rows: 3, maxLength, required: !optional, placeholder: t(optional ? "comment_placeholder" : "reply_placeholder")});
    return {input, node: el("label.recommendation-comment-field", {},
      el("span", {text: t(optional ? "initial_comment" : "new_comment")}), input,
      el("small.muted", {text: t("comment_limit", {count: maxLength})}))};
  }

  function current(view) {
    return views.has(view) && view.root.isConnected && App.user && App.user.id === view.owner;
  }

  function reset() {
    if ([...views].some(view => view.dialog && view.root.isConnected)) Dialogs.close();
    views.clear();
  }

  async function acknowledge(view) {
    if (!current(view) || document.hidden || view.acknowledging || view.lastId <= view.readThrough) return;
    const displayedId = view.lastId;
    view.acknowledging = true;
    try {
      await App.api.post("/api/recommendation/comments/read", {recommendationId: view.id, commentId: displayedId});
      if (current(view)) {
        view.readThrough = Math.max(view.readThrough, displayedId);
        App.bus.emit("recommendations", {discussionId: view.id});
      }
    } catch (failure) { return; } // Reopening or returning to the foreground retries the displayed range.
    finally { view.acknowledging = false; }
    if (current(view) && view.lastId > displayedId) acknowledge(view);
  }

  function append(view, comments, older = false) {
    const nodes = [];
    for (const comment of comments) {
      if (view.ids.has(comment.id)) continue;
      view.ids.add(comment.id);
      view.firstId = Math.min(view.firstId, comment.id);
      view.lastId = Math.max(view.lastId, comment.id);
      nodes.push(el("li.recommendation-comment" + (comment.authorId === view.owner ? ".own" : ""), {
        dataset: {id: String(comment.id)}},
        el("div.recommendation-comment-meta", {}, el("strong", {text: comment.author}),
          el("time.muted", {text: App.time(comment.createdAt), title: App.fullDate(comment.createdAt),
            dateTime: new Date(comment.createdAt * 1000).toISOString()})),
        el("p", {text: comment.body})));
    }
    const atBottom = view.list.scrollHeight - view.list.scrollTop - view.list.clientHeight < 40;
    const height = view.list.scrollHeight;
    if (older) view.list.prepend(...nodes);
    else App.append(view.list, nodes);
    view.empty.hidden = view.ids.size > 0;
    if (older) view.list.scrollTop += view.list.scrollHeight - height;
    else if (atBottom) view.list.scrollTop = view.list.scrollHeight;
  }

  async function load(view, older = false) {
    if (!current(view) || document.hidden) return;
    if (view.loading) { if (!older) view.refreshAgain = true; return view.loading; }
    view.loading = (async () => {
      view.error.textContent = "";
      view.more.disabled = true;
      try {
        let more;
        do {
          const params = {id: view.id};
          if (older) params.before = view.firstId;
          else if (view.lastId) params.after = view.lastId;
          const data = await App.api.get("/api/recommendation/comments", params);
          if (!current(view)) return;
          view.context.textContent = t("discussion_context", {
            title: data.recommendation.target.title, sender: data.recommendation.sender, recipient: data.recommendation.recipient});
          if (!view.composer) compose(view, data.maxLength);
          const initial = !view.lastId;
          append(view, data.comments, older);
          if (older || initial) view.more.hidden = !data.hasMore;
          more = !older && !initial && data.hasMore;
          await acknowledge(view);
        } while (more && current(view) && !document.hidden);
      } catch (failure) {
        if (current(view)) view.error.textContent = App.errorText(failure);
      } finally { view.more.disabled = false; }
    })();
    try { await view.loading; }
    finally {
      view.loading = null;
      if (current(view) && view.refreshAgain) { view.refreshAgain = false; load(view); }
    }
  }

  function compose(view, maxLength) {
    const comment = field(maxLength);
    comment.input.value = view.draft;
    const submit = el("button.primary", {type: "submit", text: t("post_comment")});
    let request = null;
    view.composer = el("form.recommendation-comment-form", {onsubmit: async event => {
      event.preventDefault();
      if (!current(view) || submit.disabled || !comment.input.value.trim()) return;
      const body = comment.input.value.trim();
      if (!request || request.body !== body) request = {body, requestId: App.requestId()};
      submit.disabled = comment.input.disabled = true;
      view.error.textContent = "";
      try {
        await App.api.post("/api/recommendation/comment", Object.assign({recommendationId: view.id}, request));
        if (!current(view)) return;
        comment.input.value = "";
        request = null;
        App.bus.emit("recommendations", {discussionId: view.id});
        await load(view);
      } catch (failure) { if (current(view)) view.error.textContent = App.errorText(failure); }
      finally {
        submit.disabled = comment.input.disabled = false;
        if (current(view)) comment.input.focus();
      }
    }}, comment.node, submit);
    view.root.appendChild(view.composer);
  }

  function build(recommendation, draft) {
    const view = {id: recommendation.id, owner: App.user.id, ids: new Set(), firstId: Infinity,
      lastId: 0, readThrough: 0, acknowledging: false, loading: null, refreshAgain: false, composer: null, draft,
      dialog: false};
    view.context = el("p.muted", {text: t("loading_comments")});
    view.list = el("ol.recommendation-comment-list", {"aria-label": t("comments"), "aria-live": "polite"});
    view.empty = el("p.muted", {text: t("empty_comments"), hidden: true});
    view.error = el("p.page-error", {role: "alert"});
    view.more = el("button.recommendation-comments-older", {type: "button", text: t("older_comments"),
      hidden: true, onclick: () => load(view, true)});
    view.root = el("div.recommendation-discussion", {}, view.context, view.more, view.list, view.empty, view.error,
      el("button.link-button.recommendation-comments-retry", {
        type: "button", text: t("refresh_comments"), onclick: () => load(view)}));
    return view;
  }

  function open(recommendation, draft = "") {
    const view = build(recommendation, draft);
    view.dialog = true;
    Dialogs.open(t("comments"), view.root, () => views.delete(view));
    views.add(view);
    load(view);
  }

  /** Fil déplié dans la page, sous la carte ou la ligne. */
  function mount(recommendation, container) {
    const view = build(recommendation, "");
    view.context.hidden = true;
    container.appendChild(view.root);
    views.add(view);
    load(view);
    return view;
  }

  function unmount(view) {
    views.delete(view);
    view.root.remove();
  }

  /** Aperçu du dernier commentaire + bouton qui déplie le fil de cette recommandation, sous l'aperçu. */
  function summary(recommendation, options = {}) {
    let current = recommendation, view = null;
    const other = rec => App.user.id === rec.senderId ? rec.recipient : rec.sender;
    const preview = el("p.recommendation-comment-preview");
    const thread = el("div.recommendation-thread", {hidden: true});
    const button = el("button.recommendation-comments-open", {
      type: "button", "aria-expanded": "false", dataset: {recommendationId: String(recommendation.id)},
      onclick: event => { event.stopPropagation(); node.toggle(); },
      ondblclick: event => event.stopPropagation()});
    const node = el("div.recommendation-comment-summary", {}, preview, button, thread);
    const paint = () => {
      preview.textContent = "";
      if (current.commentPreview) {
        if (options.named) preview.append(el("strong", {text: other(current)}), " ");
        preview.append(current.commentPreview);
      }
      preview.hidden = !current.commentPreview || !!view;
      const key = view ? "hide_comments" : current.commentsUnread ? "unread_comments_with" : "comments_with";
      button.textContent = t(key, {name: other(current), count: current.commentCount});
      button.classList.toggle("unread", !!current.commentsUnread);
      button.setAttribute("aria-expanded", String(!!view));
      node.classList.toggle("no-comments", !current.commentCount);
      node.classList.toggle("open", !!view);
      if (options.onPaint) options.onPaint(node);
    };
    node.toggle = () => {
      if (view) { unmount(view); view = null; thread.hidden = true; }
      else { thread.hidden = false; view = mount(current, thread); }
      paint();
      node.dispatchEvent(new CustomEvent("thread-toggle", {bubbles: true}));
    };
    node.update = rec => { current = rec; paint(); };
    node.recommendation = () => current;
    node.isOpen = () => !!view;
    paint();
    return node;
  }

  /** Le plus récent d'abord : non lu, puis avec un message, puis le plus récent. */
  function latest(recommendations) {
    const rank = rec => [rec.commentsUnread ? 1 : 0, rec.commentPreview ? 1 : 0, rec.createdAt, rec.id];
    return recommendations.slice().sort((a, b) => {
      const x = rank(a), y = rank(b);
      for (let i = 0; i < x.length; i++) if (x[i] !== y[i]) return y[i] - x[i];
      return 0;
    })[0];
  }

  /**
   * Fils d'une même carte : celui du conseiller le plus récent, les autres derrière « Voir tout ».
   * node.bubble est le bouton « commentaires » (avec son compteur) à placer dans les commandes de la carte.
   */
  function group(recommendations) {
    const first = latest(recommendations);
    const summaries = [];
    const bubble = el("button.recommendation-bubble", {type: "button", title: t("comments"), "aria-label": t("comments"),
      onclick: event => { event.stopPropagation(); main.toggle(); }, ondblclick: event => event.stopPropagation()});
    const count = el("small");
    const paintBubble = () => {
      const recs = summaries.map(item => item.recommendation());
      const total = recs.reduce((sum, rec) => sum + rec.commentCount, 0);
      count.textContent = total ? String(total) : "";
      bubble.classList.toggle("unread", recs.some(rec => rec.commentsUnread));
    };
    const make = (rec, named) => {
      const item = summary(rec, {named, onPaint: paintBubble});
      summaries.push(item);
      return item;
    };
    const main = make(first, recommendations.length > 1);
    const others = recommendations.filter(rec => rec !== first).map(rec => make(rec, true));
    App.append(bubble, [App.icon("chat", 18), count]);
    const rest = el("div.recommendation-comment-others", {hidden: true}, others);
    const all = recommendations.length > 1 ? el("button.link-button.recommendation-comments-all", {
      type: "button", "aria-expanded": "false", text: t("all_advisers", {count: recommendations.length}),
      onclick: event => {
        event.stopPropagation();
        rest.hidden = !rest.hidden;
        all.setAttribute("aria-expanded", String(!rest.hidden));
        all.textContent = rest.hidden ? t("all_advisers", {count: recommendations.length}) : t("fewer_advisers");
      }}) : null;
    const node = el("div.recommendation-comment-group", {}, main, all, rest);
    node.bubble = bubble;
    node.toggle = () => main.toggle();
    node.isOpen = () => summaries.some(item => item.isOpen());
    paintBubble();
    return node;
  }

  function hasInline() { return [...views].some(view => !view.dialog && view.root.isConnected); }
  function refresh() { return Promise.all([...views].map(view => load(view))); }
  return {field, open, summary, group, refresh, reset, hasInline};
})();
