"use strict";

/* Une instance par visite. Les réponses d'une semaine précédente ne remplacent jamais la sélection. */
const WeeklyReleaseView = (() => {
  const el = App.el;
  const t = key => App.t("weekly." + key);
  const iso = date => date.toISOString().slice(0, 10);
  const display = date => new Intl.DateTimeFormat("fr-FR", {
    day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
  }).format(date);
  const shift = (date, days) => new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate() + days));

  function mondayFor(now) {
    const day = new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()));
    return shift(day, -((day.getUTCDay() + 6) % 7));
  }

  async function render(main, route) {
    const input = el("input", {type: "search", list: "weekly-genres", placeholder: t("style"), "aria-label": t("style")});
    const options = el("datalist", {id: "weekly-genres"});
    const range = el("strong");
    const results = el("div", {"aria-live": "polite"});
    const follows = el("div.chips");
    const follow = el("button.primary", {type: "button", disabled: true, onclick: toggleFollow, text: t("follow")});
    const week = el("div.chips.weekly-week", {}, button("previous", () => move(-7)), range, button("next", () => move(7)),
      button("today", () => { monday = mondayFor(new Date()); reload(); }));
    const sidebar = el("aside.weekly-followed", {}, el("h2", {text: t("followed")}), follows,
      el("a", {href: "#/whatsnew/press/g5", text: t("guide")}));
    const form = el("div.chips.weekly-filters", {}, input, options, follow);
    let monday = mondayFor(new Date()), genres = [], followed = new Set(), selected = null;
    let generation = 0, saving = false;

    function button(label, action) {
      return el("button", {type: "button", text: t(label), onclick: action});
    }

    function updateControls() {
      follow.disabled = !selected || saving;
      follow.textContent = t(selected && followed.has(selected.id) ? "unfollow" : "follow");
      App.clear(follows);
      for (const genre of genres.filter(item => followed.has(item.id))) {
        follows.appendChild(el("button.chip", {type: "button", text: genre.name, onclick: () => choose(genre)}));
      }
      if (!follows.firstChild) follows.appendChild(el("span.muted", {text: t("none")}));
    }

    async function toggleFollow() {
      if (!selected || saving) return;
      const id = selected.id, enabled = !followed.has(id);
      saving = true;
      updateControls();
      try {
        await App.api.post("/api/news/releases/follow", {genre: id, enabled});
        if (enabled) followed.add(id); else followed.delete(id);
      } catch (error) { if (!route.stale) App.toast(App.errorText(error), "error"); }
      finally { saving = false; if (!route.stale) updateControls(); }
    }

    function choose(genre) {
      input.value = genre.name;
      selected = genre;
      updateControls();
      reload();
    }

    input.addEventListener("input", () => {
      const name = input.value.trim().toLowerCase();
      const genre = genres.find(item => item.name.toLowerCase() === name);
      if (genre) choose(genre);
      else if (selected) { selected = null; updateControls(); reload(); }
    });

    function move(days) {
      monday = shift(monday, days);
      reload();
    }

    function reload() {
      const version = ++generation;
      range.textContent = display(monday) + " – " + display(shift(monday, 6));
      App.clear(results);
      if (!selected) { results.textContent = t("choose"); return; }
      const grid = el("div.weekly-grid");
      const status = el("div.muted", {text: t("loading")});
      App.append(results, [grid, status]);
      const ids = new Set();

      async function page(offset) {
        App.clear(status).textContent = t("loading");
        try {
          const data = await App.api.get("/api/news/releases", {genre: selected.id, monday: iso(monday), offset});
          if (route.stale || version !== generation) return;
          App.clear(status);
          const cards = [];
          for (const album of data.albums) {
            if (ids.has(album.id)) continue;
            ids.add(album.id);
            cards.push(card(album, grid));
          }
          markLocal(cards, () => !route.stale && version === generation);
          if (data.stale) status.appendChild(el("p", {text: t("stale")}));
          if (data.next !== null) status.appendChild(el("button", {
            type: "button", text: App.t("news.more"), onclick: () => page(data.next),
          }));
          else if (!ids.size) status.appendChild(el("p", {text: t("empty")}));
        } catch (error) {
          if (!route.stale && version === generation) errorState(status, error, () => page(offset));
        }
      }
      page(0);
    }

    function errorState(box, error, retry) {
      App.append(App.clear(box), [el("p.page-error", {text: App.errorText(error)}), button("retry", retry)]);
    }

    App.append(App.clear(main), [News.tabs(true),
      el("header.weekly-heading", {}, el("h1", {text: t("title")}), week), form,
      el("div.weekly-layout", {}, results, sidebar)]);
    range.textContent = display(monday) + " – " + display(shift(monday, 6));
    results.textContent = t("loading");
    try {
      const data = await App.api.get("/api/news/releases/genres");
      if (route.stale) return;
      genres = data.genres;
      followed = new Set(data.followed);
      App.append(options, genres.map(genre => el("option", {value: genre.name})));
      const initial = genres.find(g => followed.has(g.id)) || genres.find(g => g.name === "noise rock");
      if (initial) choose(initial);
      else { updateControls(); reload(); }
    } catch (error) {
      if (!route.stale) errorState(results, error, () => render(main, route));
    }
  }

  function card(album, grid) {
    const image = App.cover("https://coverartarchive.org/release-group/" + album.id + "/front-250", 180, album.title);
    const cover = el("a", {href: "https://musicbrainz.org/release-group/" + album.id, target: "_blank", rel: "noopener"}, image);
    const actions = el("div.weekly-actions");
    const search = el("a.chip", {href: "#/search/" + encodeURIComponent(album.artist + " " + album.title), text: t("listen")});
    const date = new Date(album.date + "T00:00:00Z");
    const now = new Date();
    const today = iso(new Date(Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())));
    const label = App.t("weekly." + (album.date > today ? "upcoming" : "released"), {date: display(date)});
    App.append(actions, [search]);
    grid.appendChild(el("article.weekly-card", {}, cover, el("h3", {text: album.title}),
      el("span", {text: album.artist}), el("p.muted", {text: album.type + " · " + label}), actions));
    return {album, cover, actions};
  }

  async function markLocal(cards, active) {
    for (let i = 0; i < cards.length && active(); i += 3) {
      await Promise.all(cards.slice(i, i + 3).map(async ({album, cover, actions}) => {
        try {
          const data = await App.api.get("/api/explore/local", {title: album.title, artist: album.artist});
          if (!active() || data.albums.length !== 1) return;
          const local = data.albums[0];
          const href = "#/album/" + encodeURIComponent(local.id);
          cover.href = href;
          cover.removeAttribute("target");
          if (local.coverId) cover.replaceChildren(App.cover(local.coverId, 180, album.title));
          actions.replaceChildren(el("a.chip", {href, text: t("local")}),
            ListenLaterUI.actions({kind: "album", source: "subsonic", sourceId: local.id}));
        } catch (error) { /* La carte conserve sa recherche même si la bibliothèque est indisponible. */ }
      }));
    }
  }

  return {render, mondayFor};
})();
