"use strict";
/* Exploration à la demande : aucune requête externe ne retarde les titres de l'album. */
const AlbumExploration = (() => {
  const el = App.el, t = key => App.t("explore." + key);
  const source = (kind, id) => el("a.explore-source", {href: "https://musicbrainz.org/" + kind + "/" + id,
    target: "_blank", rel: "noopener noreferrer", text: t("source")});
  const link = person => el("a.explore-link", {
    href: "#/explore/" + person.kind + "/" + encodeURIComponent(person.id), text: person.name, "aria-label": person.name,
    dataset: {initials: (person.name || "").trim().split(/\s+/).slice(0, 2)
      .map(word => [...word][0] || "").join("").toLocaleUpperCase("fr")}});

  function role(person) {
    const dates = person.begin || person.end || person.ended;
    return [t("roles." + person.role), person.detail, dates &&
      [person.begin || t("unknown_begin"), person.end || t(person.ended ? "unknown_end" : "present")]
        .join(" — ")].filter(Boolean).join(" · ");
  }

  function groupedPeople(people) {
    const groups = new Map();
    for (const person of people) {
      const key = person.id + ":" + person.role;
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(person);
    }
    return [...groups.values()];
  }

  function peopleList(people) {
    return el("ul.explore-people", {}, groupedPeople(people).map(periods => el("li", {}, link(periods[0]),
      periods.map(person => el("span.muted", {text: role(person)})))));
  }

  function failure(root, error, retry) {
    App.append(App.clear(root), [el("p", {role: "status", text: App.errorText(error)}),
      el("button.link-button", {type: "button", text: t("retry"), onclick: retry})]);
  }

  function memberCard(periods, origin, route) {
    const person = periods[0], projects = el("div.explore-member-links", {hidden: true});
    let loaded = false;
    const button = el("button.link-button.explore-member-projects", {type: "button", text: t("other_projects"),
      "aria-label": App.t("explore.projects_of", {name: person.name}), "aria-expanded": "false",
      onclick: async () => {
        if (loaded) {
          projects.hidden = !projects.hidden;
          button.setAttribute("aria-expanded", String(!projects.hidden));
          return;
        }
        const load = async () => {
          button.disabled = true;
          projects.hidden = false;
          button.setAttribute("aria-expanded", "true");
          App.append(App.clear(projects), [el("p.muted", {role: "status", text: t("loading")})]);
          try {
            const data = await App.api.get("/api/explore/connections", {id: person.id});
            if (route.stale) return;
            const others = data.relations.filter(other => other.id !== origin && other.id !== person.id);
            App.append(App.clear(projects), [
              data.stale ? el("p.explore-cached.muted", {role: "status", text: t("cached")}) : null,
              others.length ? peopleList(others) : el("p.muted", {text: t("no_other_projects")})]);
            loaded = true;
          } catch (error) { if (!route.stale) failure(projects, error, load); }
          finally { button.disabled = false; }
        };
        await load();
      }});
    return el("li.explore-member-card", {}, link(person),
      periods.map(period => el("span.muted", {text: role(period)})), button, projects);
  }

  function connectionsView(data, route) {
    const relations = data.relations.filter(person => person.id !== data.id);
    const memberRoles = ["member", "supporting_member", "collaborator"];
    const members = relations.filter(person => memberRoles.includes(person.role));
    const others = relations.filter(person => !memberRoles.includes(person.role));
    return el("div.explore-connections-content", {},
      el("p.muted", {text: t("all_periods")}),
      data.stale ? el("p.explore-cached.muted", {role: "status", text: t("cached")}) : null,
      members.length ? el("ul.explore-people.explore-member-cards", {},
        groupedPeople(members).map(periods => memberCard(periods, data.id, route))) : null,
      others.length ? peopleList(others) : null,
      !relations.length ? el("p.muted", {text: t("no_connections")}) : null);
  }

  function connectionsPanel(identity, name, route) {
    const body = el("div.explore-connections-body");
    const box = el("section.explore-connections", {},
      el("h3", {text: App.t("explore.connections_of", {name})}), body);
    async function load() {
      App.append(App.clear(body), [el("p.muted", {role: "status", text: t("loading")})]);
      try {
        const data = await App.api.get("/api/explore/connections", {id: identity});
        if (route.stale) return;
        App.append(App.clear(body), [source("artist", identity), connectionsView(data, route)]);
      } catch (error) { if (!route.stale) failure(body, error, load); }
    }
    load();
    return box;
  }

  function artistPanel(name, route) {
    const body = el("div.explore-artist-body");
    const box = el("section.album-exploration.artist-exploration", {}, Views.heading(t("connections")), body);
    async function search() {
      App.append(App.clear(body), [el("p.muted", {role: "status", text: t("loading")})]);
      try {
        const data = await App.api.get("/api/explore/artists", {name});
        if (route.stale) return;
        App.clear(body);
        if (data.stale) body.appendChild(el("p.explore-cached.muted", {role: "status", text: t("cached")}));
        if (!data.artists.length) { body.appendChild(el("p.muted", {text: t("no_artist")})); return; }
        if (data.artists.length === 1) {
          body.appendChild(connectionsPanel(data.artists[0].id, data.artists[0].name, route));
          return;
        }
        const result = el("div.explore-artist-result");
        const types = {Person: "person", Group: "group", Orchestra: "orchestra", Choir: "choir", Character: "character", Other: "other"};
        const select = el("select.explore-artist-choice", {onchange: () => {
          App.clear(result);
          const artist = data.artists.find(a => a.id === select.value);
          if (artist) result.appendChild(connectionsPanel(artist.id, artist.name, route));
        }}, el("option", {value: "", text: t("choose_artist")}), data.artists.map(artist => el("option", {
          value: artist.id, text: [artist.name, types[artist.type] ? t("types." + types[artist.type]) : artist.type,
            artist.country, artist.description].filter(Boolean).join(" · ")})));
        App.append(body, [el("label.explore-picker", {}, el("span", {text: t("artist_identity")}), select),
          el("p.muted", {text: t("homonyms")}), result]);
      } catch (error) { if (!route.stale) failure(body, error, search); }
    }
    body.appendChild(el("button.link-button.explore-artist-open", {type: "button", text: t("show_connections"), onclick: search}));
    return box;
  }

  function panel(albumId, route) {
    const body = el("div.explore-body"), box = el("section.album-exploration", {},
      Views.heading(t("title")), el("p.muted", {text: t("intro")}), body);
    let generation = 0;
    async function load(release) {
      const current = ++generation;
      App.append(App.clear(body), [el("p.muted", {role: "status", text: t("loading")})]);
      try {
        const data = await App.api.get("/api/explore/album", {id: albumId, release: release || ""});
        if (route.stale || generation !== current) return;
        App.clear(body);
        if (data.stale) body.appendChild(el("p.explore-cached.muted", {role: "status", text: t("cached")}));
        if (!data.editions.length) {
          body.appendChild(el("p.muted", {text: t("no_match")}));
          return;
        }
        const select = el("select.explore-edition", {onchange: () => load(select.value)},
          el("option", {value: "", text: t("choose")}), data.editions.map(edition => el("option", {
            value: edition.id, selected: edition.id === data.selected,
            text: [edition.title, edition.date, edition.country, edition.format, ...edition.labels, edition.id.slice(0, 8)]
              .filter(Boolean).join(" · ")})));
        App.append(body, [el("label.explore-picker", {}, el("span", {text: t("edition")}), select),
          el("p.muted", {text: t("edition_help")})]);
        if (!data.selected) return;
        App.append(body, [source("release", data.selected),
          el("h3", {text: t("labels")}), data.labels.length ? peopleList(data.labels) : el("p.muted", {text: t("no_labels")}),
          el("h3", {text: t("credits")}), peopleList(data.people), el("p.muted", {text: t("incomplete")})]);
        const principals = new Map(data.people.filter(person => person.role === "artist").map(person => [person.id, person]));
        for (const artist of principals.values()) body.appendChild(connectionsPanel(artist.id, artist.name, route));
      } catch (error) {
        if (!route.stale && generation === current) failure(body, error, () => load(release));
      }
    }
    body.appendChild(el("button.link-button.explore-open", {type: "button", text: t("open"), onclick: () => load()}));
    return box;
  }

  function workRow(work, route) {
    const local = el("div.explore-local");
    const button = el("button.link-button.explore-find", {type: "button", text: t("find_local"), onclick: async () => {
      button.disabled = true;
      try {
        const data = await App.api.get("/api/explore/local", {title: work.title, artist: work.artist});
        if (route.stale) return;
        App.clear(local);
        for (const album of data.albums) local.appendChild(el("a", {
          href: "#/album/" + encodeURIComponent(album.id), text: album.artist + " — " + album.name}));
        for (const song of data.songs.filter(s => s.albumId)) local.appendChild(el("a", {
          href: "#/album/" + encodeURIComponent(song.albumId), text: song.artist + " — " + song.title}));
        if (!local.childNodes.length) local.appendChild(el("span.muted", {text: t("no_local")}));
        local.appendChild(el("a", {href: "#/search/" + encodeURIComponent(work.title), text: t("search_local")}));
      } catch (error) {
        if (!route.stale) local.textContent = App.errorText(error);
      } finally { button.disabled = false; }
    }});
    return el("li.explore-work", {},
      el("div", {}, el("strong", {text: work.title}), el("span.muted", {
        text: [work.artist, work.date, t("kinds." + work.kind), t("roles." + work.role)].filter(Boolean).join(" · ")})),
      el("div.explore-work-actions", {}, source(work.kind, work.id), button), local);
  }

  const view = {
    async render(main, route) {
      App.append(App.clear(main), [el("p.muted", {role: "status", text: t("loading")})]);
      try {
        const data = await App.api.get("/api/explore/profile", {kind: route.kind, id: route.id});
        if (route.stale) return;
        const list = el("ul.explore-works", {}, data.works.map(work => workRow(work, route)));
        const notice = el("p.explore-cached.muted", {role: "status", hidden: !data.stale, text: t("cached")});
        let offset = data.nextOffset;
        const more = el("button.link-button.explore-more", {type: "button", text: t("more"), hidden: !data.more,
          onclick: async () => {
            more.disabled = true;
            try {
              const next = await App.api.get("/api/explore/profile", {kind: route.kind, id: route.id, offset});
              if (route.stale) return;
              if (next.stale) notice.hidden = false;
              next.works.forEach(work => list.appendChild(workRow(work, route)));
              offset = next.nextOffset;
              more.hidden = !next.more;
            } catch (error) { if (!route.stale) App.toast(App.errorText(error), "error"); }
            finally { more.disabled = false; }
          }});
        App.append(App.clear(main), [el("h1", {text: data.name}), el("p.muted", {text: data.description}),
          source(data.kind, data.id), notice, el("p.muted", {text: t("incomplete")}),
          data.kind === "artist" ? el("section", {}, Views.heading(t("connections")), connectionsView(data, route)) : null,
          Views.heading(data.kind === "label" ? t("catalog") : t("works")), list,
          !data.works.length ? el("p.muted", {text: t("no_works")}) : null, more]);
      } catch (error) { if (!route.stale) failure(main, error, () => this.render(main, route)); }
    },
  };
  Views.explore = view;
  return {panel, artistPanel};
})();
