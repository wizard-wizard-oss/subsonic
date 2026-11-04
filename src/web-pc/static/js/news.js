"use strict";
/* Page « Actualité » (#/news[/<flux>]) : les derniers articles des webzines suivis par le site (flux RSS ou Atom lus
   toutes les heures par le serveur), filtrables par webzine. Chacun peut ajouter un flux (adresse du flux ou du site) ;
   l'admin ou la personne qui l'a ajouté peut le retirer. Le site ne montre que des liens : l'article s'ouvre chez le webzine.
   Aussi : les articles qui parlent d'un artiste, sous sa page (News.pressSection). */

const News = (() => {
  const el = App.el, t = App.t;

  function articleDate(epoch) {
    return new Date(epoch * 1000).toLocaleDateString("fr-FR", {day: "numeric", month: "long", year: "numeric"});
  }

  /** Un article : titre (lien vers le webzine, nouvel onglet), webzine et date, début du résumé. */
  function articleRow(article, showFeed) {
    return el("li.news-article", {},
      el("a.news-title", {href: article.link, target: "_blank", rel: "noopener noreferrer", text: article.title}),
      el("div.news-meta.muted", {text: (showFeed ? article.feed + " · " : "") + articleDate(article.publishedAt)}),
      article.summary ? el("p.news-summary", {text: article.summary}) : null);
  }

  /** Section « Dans la presse » de la page d'un artiste : rien si aucun article ne cite son nom. */
  async function pressSection(section, name, route) {
    let articles;
    try { articles = (await App.api.get("/api/news/artist", {name})).articles; } catch (error) { return; }
    if (route.stale || !articles.length) return;
    App.append(section, [el("div.section-head", {}, el("h2", {text: t("artist.press")})),
                         el("ul.news-list.compact", {}, articles.map(a => articleRow(a, true)))]);
  }

  const view = {
    async render(main, route) {
      App.clear(main).appendChild(el("div.loading", {text: "…"}));
      this.feedId = Number(route.id) || null;
      this.last = null;
      let feeds, page;
      try {
        [feeds, page] = await Promise.all([App.api.get("/api/news/feeds"), this.fetch()]);
      } catch (error) {
        App.clear(main).appendChild(el("p.page-error", {text: App.errorText(error)}));
        return;
      }
      if (route.stale) return;
      this.list = el("ul.news-list");
      this.more = el("button.link-button.news-more", {type: "button", text: t("news.more"), onclick: () => this.loadMore()});
      App.append(App.clear(main), [
        el("header.page-head", {}, el("h1", {text: t("news.title")})),
        el("p.muted", {text: t("news.intro")}),
        this.addForm(),
        this.feedChips(feeds.feeds),
        this.list, this.more]);
      this.show(page);
    },

    fetch(before) {
      const params = {};
      if (this.feedId) params.feed = this.feedId;
      if (before) Object.assign(params, {beforeDate: before.publishedAt, beforeId: before.id});
      return App.api.get("/api/news", params);
    },

    show(page) {
      this.last = page.articles[page.articles.length - 1] || this.last;
      if (!this.list.firstChild && !page.articles.length) this.list.appendChild(el("li.muted", {text: t("news.empty")}));
      App.append(this.list, page.articles.map(a => articleRow(a, !this.feedId)));
      this.more.hidden = !page.more;
    },

    async loadMore() {
      this.more.disabled = true;
      try { this.show(await this.fetch(this.last)); } catch (error) { App.toast(App.errorText(error), "error"); }
      this.more.disabled = false;
    },

    /** « Tout », puis un bouton par webzine : case « afficher » (décochée : masqué pour soi), nombre d'articles gardés,
        ⚠ si la dernière lecture a échoué, × pour retirer. */
    feedChips(feeds) {
      const chip = (href, label, on, before, extra, hidden) =>
        el("span.chip.toggle.news-feed" + (on ? ".on" : "") + (hidden ? ".news-hidden" : ""), {},
           before, el("a", {href, text: label}), extra);
      return el("div.chips.news-feeds", {},
        chip("#/news", t("news.all"), !this.feedId),
        feeds.map(f => chip("#/news/" + f.id, f.title, f.id === this.feedId,
          el("input.news-show", {type: "checkbox", checked: f.shown, title: t("news.show", {title: f.title}),
                                 "aria-label": t("news.show", {title: f.title}), onchange: e => this.setShown(f, e.target.checked)}), [
          el("span.chip-count", {text: " " + f.articles}),
          f.error ? el("span.news-feed-error", {title: t("news.feed_error") + " : " + t(f.error), text: " ⚠"}) : null,
          f.canRemove ? el("button.news-remove", {type: "button", title: t("news.remove", {title: f.title}),
                                                   "aria-label": t("news.remove", {title: f.title}), text: "×",
                                                   onclick: () => this.remove(f)}) : null], !f.shown)));
    },

    addForm() {
      const input = el("input.news-address", {type: "text", inputMode: "url", placeholder: t("news.add_placeholder"), required: true});
      const button = el("button.primary", {type: "submit", text: t("news.add")});
      return el("form.news-add", {onsubmit: async event => {
        event.preventDefault();
        button.disabled = true;
        App.toast(t("news.adding"));
        try {
          const feed = (await App.api.post("/api/news/feed/add", {address: input.value})).feed;
          App.toast(t("news.added", {title: feed.title}));
          location.hash = "#/news/" + feed.id;
        } catch (error) {
          App.toast(App.errorText(error), "error");
        }
        button.disabled = false;
      }}, input, button);
    },

    async setShown(feed, shown) {
      try {
        await App.api.post("/api/news/feed/show", {id: feed.id, shown});
        App.music.navigate();                                    // pastilles et liste « Tout » suivent le choix
      } catch (error) { App.toast(App.errorText(error), "error"); }
    },

    async remove(feed) {
      if (!(await Dialogs.confirm(t("news.remove_confirm", {title: feed.title})))) return;
      try {
        await App.api.post("/api/news/feed/remove", {id: feed.id});
        App.toast(t("news.removed", {title: feed.title}));
        if (location.hash === "#/news") App.music.navigate(); else location.hash = "#/news";
      } catch (error) { App.toast(App.errorText(error), "error"); }
    },
  };

  return {view, pressSection};
})();

Views.news = News.view;
