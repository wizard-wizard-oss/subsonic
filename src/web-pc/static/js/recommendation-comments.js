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

  /** Saisie d'une ligne à la Facebook : Entrée envoie, Maj+Entrée passe à la ligne. */
  function compactField(maxLength, send) {
    const input = el("textarea.recommendation-comment-input", {rows: 1, maxLength, required: true,
      placeholder: t("write_comment"), "aria-label": t("new_comment"),
      onkeydown: event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); send(); } },
      oninput: () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; }});
    return {input, node: el("div.recommendation-comment-field.compact", {}, input)};
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
    const comment = compactField(maxLength, () => view.composer.dispatchEvent(new Event("submit", {cancelable: true})));
    comment.input.value = view.draft;
    const submit = el("button.primary", {type: "submit", text: t("send_comment"), title: t("post_comment"),
      "aria-label": t("post_comment")});
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

  const FOLD_MS = 300;  // durée de l'animation de repli (voir listen-later.css)
  const calm = () => !!(window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches);

  /** Referme un fil : il n'est plus suivi tout de suite, mais reste à l'écran le temps de l'animation. */
  function fold(view, thread, done) {
    views.delete(view);
    const finish = () => { view.root.remove(); thread.hidden = true; thread.classList.remove("folding"); done(); };
    if (calm()) { finish(); return null; }
    thread.classList.add("folding");
    return {finish, timer: setTimeout(finish, FOLD_MS)};
  }

  /** Fil d'une recommandation : replié au départ, il se déplie sous la carte ou la ligne. */
  function summary(recommendation, options = {}) {
    let current = recommendation, view = null;
    const other = rec => App.user.id === rec.senderId ? rec.recipient : rec.sender;
    const inner = el("div.recommendation-thread-inner", {},
      options.named ? el("p.recommendation-thread-name", {text: other(recommendation)}) : null);
    const thread = el("div.recommendation-thread", {hidden: true}, inner);
    const node = el("div.recommendation-comment-summary", {dataset: {recommendationId: String(recommendation.id)}}, thread);
    const paint = () => {
      node.classList.toggle("open", !!view);
      if (options.onPaint) options.onPaint(node);
    };
    let folding = null;
    const toggled = () => node.dispatchEvent(new CustomEvent("thread-toggle", {bubbles: true}));
    const settle = () => { if (folding) { clearTimeout(folding.timer); const {finish} = folding; folding = null; finish(); } };
    node.toggle = () => {
      if (view) {
        const closing = view;
        view = null;
        folding = fold(closing, thread, () => { folding = null; toggled(); });
      } else {
        settle();
        thread.hidden = false;
        view = mount(current, inner);
        toggled();
      }
      paint();
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
   * Fils d'une même carte : repliés au départ ; la bulle déplie celui du conseiller le plus récent, et
   * « Voir les autres conseillers » ouvre les autres. node.bubble est le bouton « commentaires » (avec son
   * compteur) à placer dans les commandes de la carte.
   */
  /** Le bouton « commentaires » d'une carte : compteur, accent si non lu, état déplié. */
  function bubbleControl(first, toggle) {
    const count = el("small");
    const bubble = el("button.recommendation-bubble", {type: "button", title: t("comments"), "aria-label": t("comments"),
      dataset: {recommendationId: String(first.id)},
      onclick: event => { event.stopPropagation(); toggle(); }, ondblclick: event => event.stopPropagation()});
    App.append(bubble, [App.icon("chat", 18), count]);
    const paint = summaries => {
      const recs = summaries.map(item => item.recommendation());
      const total = recs.reduce((sum, rec) => sum + rec.commentCount, 0);
      count.textContent = total ? String(total) : "";
      bubble.classList.toggle("unread", recs.some(rec => rec.commentsUnread));
      bubble.setAttribute("aria-expanded", String(summaries.some(item => item.isOpen())));
    };
    return {bubble, paint};
  }

  /** « Voir les autres conseillers » : ouvre ou referme les fils des autres personnes. */
  function othersControl(others) {
    const rest = el("div.recommendation-comment-others", {hidden: true}, others);
    let all = null;
    const show = visible => {
      rest.hidden = !visible;
      all.textContent = t(visible ? "fewer_advisers" : "all_advisers", {count: others.length});
      others.forEach(item => { if (item.isOpen() !== visible) item.toggle(); });
    };
    if (others.length) {
      all = el("button.link-button.recommendation-comments-all", {
        type: "button", hidden: true, text: t("all_advisers", {count: others.length}),
        onclick: event => { event.stopPropagation(); show(rest.hidden); }});
    }
    return {rest, all, show};
  }

  /**
   * Fils d'une même carte : repliés au départ ; la bulle déplie celui du conseiller le plus récent, et
   * « Voir les autres conseillers » ouvre les autres. node.bubble est le bouton « commentaires » à placer
   * dans les commandes de la carte.
   */
  function group(recommendations) {
    const first = latest(recommendations), summaries = [];
    const controls = bubbleControl(first, () => node.toggle());
    const make = (rec, named) => {
      const item = summary(rec, {named, onPaint: () => controls.paint(summaries)});
      summaries.push(item);
      return item;
    };
    const main = make(first, recommendations.length > 1);
    const more = othersControl(recommendations.filter(rec => rec !== first).map(rec => make(rec, true)));
    const node = el("div.recommendation-comment-group", {}, main, more.all, more.rest);
    node.bubble = controls.bubble;
    node.toggle = () => {
      main.toggle();
      if (!more.all) return;
      more.all.hidden = !main.isOpen();
      if (!main.isOpen() && !more.rest.hidden) more.show(false);
    };
    node.isOpen = () => summaries.some(item => item.isOpen());
    controls.paint(summaries);
    return node;
  }

  function hasInline() { return [...views].some(view => !view.dialog && view.root.isConnected); }
  function refresh() { return Promise.all([...views].map(view => load(view))); }
  return {field, open, summary, group, refresh, reset, hasInline};
})();
