"use strict";
/* One private comment component, shared by received, sent and archived recommendations. */
const RecommendationComments = (() => {
  const el = App.el, t = (key, params) => App.t("listen_later." + key, params);
  let active = null;

  function field(maxLength, optional = false) {
    const input = el("textarea.recommendation-comment-input", {
      rows: 3, maxLength, required: !optional, placeholder: t(optional ? "comment_placeholder" : "reply_placeholder")});
    return {input, node: el("label.recommendation-comment-field", {},
      el("span", {text: t(optional ? "initial_comment" : "new_comment")}), input,
      el("small.muted", {text: t("comment_limit", {count: maxLength})}))};
  }

  function current(view) {
    return active === view && view.root.isConnected && App.user && App.user.id === view.owner;
  }

  function reset() {
    if (active && active.root.isConnected) Dialogs.close();
    active = null;
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

  function open(recommendation, draft = "") {
    const view = {id: recommendation.id, owner: App.user.id, ids: new Set(), firstId: Infinity,
      lastId: 0, readThrough: 0, acknowledging: false, loading: null, refreshAgain: false, composer: null, draft};
    view.context = el("p.muted", {text: t("loading_comments")});
    view.list = el("ol.recommendation-comment-list", {"aria-label": t("comments"), "aria-live": "polite"});
    view.empty = el("p.muted", {text: t("empty_comments"), hidden: true});
    view.error = el("p.page-error", {role: "alert"});
    view.more = el("button.recommendation-comments-older", {type: "button", text: t("older_comments"),
      hidden: true, onclick: () => load(view, true)});
    view.root = el("div.recommendation-discussion", {}, view.context, view.more, view.list, view.empty, view.error,
      el("button.link-button.recommendation-comments-retry", {
        type: "button", text: t("refresh_comments"), onclick: () => load(view)}));
    Dialogs.open(t("comments"), view.root, () => { if (active === view) active = null; });
    active = view;
    load(view);
  }

  function summary(recommendation) {
    const other = App.user.id === recommendation.senderId ? recommendation.recipient : recommendation.sender;
    const button = el("button.recommendation-comments-open" + (recommendation.commentsUnread ? ".unread" : ""), {
      type: "button", dataset: {recommendationId: String(recommendation.id)},
      text: t(recommendation.commentsUnread ? "unread_comments_with" : "comments_with", {
        name: other, count: recommendation.commentCount}),
      onclick: event => { event.stopPropagation(); open(recommendation); },
      ondblclick: event => event.stopPropagation()});
    return el("div.recommendation-comment-summary", {},
      recommendation.commentPreview ? el("p.recommendation-comment-preview", {text: recommendation.commentPreview}) : null,
      button);
  }

  function refresh() { if (active) return load(active); }
  return {field, open, summary, refresh, reset};
})();
