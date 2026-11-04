"use strict";
/* Playlists : liste dans la barre de gauche (onglet à côté des artistes), pages d'une playlist, ajout par
   glisser-déposer ou par le menu « Ajouter à une playlist ».
   Playlist de Subsonic : la sienne, ou celle d'un autre rendue publique (lecture seule).
   Communautaire : tout le monde peut y ajouter, chaque titre garde le nom de la personne qui l'a ajouté.
   Titres d'ailleurs (YouTube, SoundCloud, Jamendo) : gardés par le site à côté de la playlist Subsonic, montrés à leur
   place ici ; les applications Subsonic ne voient que les titres Subsonic. */

App.playlists = {
  items: [],

  async load() {
    try {
      this.items = (await App.api.get("/api/playlists")).playlists;
    } catch (error) {
      return;                                                  // on garde la liste affichée
    }
    App.bus.emit("playlists", this.items);
  },

  /** Où la personne peut ajouter : ses playlists, et les communautaires. */
  writable() {
    return App.can("playlist") ? this.items.filter(p => p.canAdd) : [];
  },

  /** Les titres d'un glissé : ceux du payload, ou ceux de l'album glissé. */
  async songIds(payload) {
    if (payload.songIds) return payload.songIds;
    return (await App.api.get("/api/album", {id: payload.albumId})).songs.map(s => s.id);
  },

  /** Ajout de titres Subsonic ({songIds} ou {albumId}) ou de titres d'ailleurs ({extItems}). */
  async send(playlistId, payload) {
    if (payload.extItems) return (await App.api.post("/api/playlist/add-ext", {id: playlistId, items: payload.extItems})).added;
    const ids = await this.songIds(payload);
    return ids.length ? (await App.api.post("/api/playlist/add", {id: playlistId, songIds: ids})).added : 0;
  },

  async add(playlist, payload) {
    try {
      const added = await this.send(playlist.id, payload);
      App.toast(added ? App.plural("playlist.added", added, {name: playlist.name})
                      : App.t("playlist.already", {name: playlist.name}));
      await this.load();
      App.bus.emit("playlist-changed", playlist.id);
    } catch (error) {
      App.toast(App.errorText(error), "error");
    }
  },

  /** Nouvelle playlist (avec ce qu'on a glissé, s'il y en a). Renvoie la playlist créée, ou null. */
  async create(payload) {
    const choice = await Dialogs.newPlaylist(payload && payload.label);
    if (!choice) return null;
    try {
      const ids = payload && !payload.extItems ? await this.songIds(payload) : [];
      const created = (await App.api.post("/api/playlist/create", {name: choice.name, songIds: ids,
                                                                   community: choice.community})).playlist;
      if (payload && payload.extItems && created.id) await this.send(created.id, payload);
      App.toast(App.t("playlist.created", {name: created.name}));
      await this.load();
      return created;
    } catch (error) {
      App.toast(App.errorText(error), "error");
      return null;
    }
  },

  /** Menu « Ajouter à une playlist » : la même chose que le glisser-déposer, au clic. */
  pick(payload) {
    const el = App.el;
    const rows = this.writable().map(p => el("button.pick-row", {type: "button", onclick: () => {
      Dialogs.close();
      this.add(p, payload);
    }}, el("span", {text: p.name}), p.community && !p.mine ? el("span.muted", {text: App.t("playlist.by", {name: p.owner})}) : null));
    Dialogs.open(App.t("playlist.add_to"), el("div.playlist-pick", {},
      el("button.primary", {type: "button", text: App.t("playlist.new"), onclick: async () => {
        Dialogs.close();
        const created = await this.create(payload);
        if (created) App.bus.emit("playlist-changed", created.id);
      }}),
      rows));
  },
};

/** Barre de gauche : onglets Artistes | Playlists, et la liste des playlists. */
class PlaylistPanel {
  constructor(app) {
    this.app = app;
    const names = ["artists", "playlists"];
    this.tabs = Object.fromEntries(names.map(n => [n, document.getElementById("tab-" + n)]));
    this.panels = Object.fromEntries(names.map(n => [n, document.getElementById("panel-" + n)]));
    this.list = document.getElementById("playlist-list");
    this.filter = document.getElementById("playlist-filter");
    this.add = document.getElementById("playlist-new");
    this.timer = null;
    for (const name of Object.keys(this.tabs)) {
      this.tabs[name].addEventListener("click", () => this.show(name, true));
      // en glissant un titre : l'onglet des playlists s'ouvre tout seul, pour pouvoir y déposer
      this.tabs[name].addEventListener("dragenter", () => {
        if (!Dnd.active()) return;
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.show(name, false), 300);
      });
      this.tabs[name].addEventListener("dragleave", () => clearTimeout(this.timer));
    }
    this.filter.addEventListener("input", () => this.render());
    this.add.addEventListener("click", async () => {
      const created = await App.playlists.create(null);
      if (created && created.id) location.hash = "#/playlist/" + encodeURIComponent(created.id);
    });
    Dnd.target(this.add, () => App.can("playlist"), async payload => {
      const created = await App.playlists.create(payload);
      if (created && created.id) App.bus.emit("playlist-changed", created.id);
    });
    App.bus.on("playlists", () => this.render());
    App.bus.on("preferences", () => this.show(App.preferences.sidebar_tab || "artists", false));
    App.bus.on("route", () => this.highlight());
    this.add.hidden = !App.can("playlist");
    document.getElementById("playlist-import").hidden = !App.can("playlist");
    this.show(App.preferences.sidebar_tab || "artists", false);
    App.playlists.load();
  }

  show(name, save) {
    for (const key of Object.keys(this.tabs)) {
      this.tabs[key].classList.toggle("active", key === name);
      this.tabs[key].setAttribute("aria-selected", String(key === name));
      this.panels[key].hidden = key !== name;
    }
    if (save && App.preferences.sidebar_tab !== name) App.savePreference("sidebar_tab", name);
  }

  render() {
    const words = ArtistSidebar.fold(this.filter.value.trim());
    const shown = App.playlists.items.filter(p => !words || ArtistSidebar.fold(p.name).includes(words));
    App.clear(this.list);
    if (!App.playlists.items.length) {
      this.list.appendChild(App.el("p.playlist-note", {text: App.t("playlist.empty")}));
      return;
    }
    const sections = [["playlist.mine", shown.filter(p => p.mine)],
                      ["playlist.community_section", shown.filter(p => !p.mine && p.community)],
                      ["playlist.shared", shown.filter(p => !p.mine && !p.community)]];
    for (const [title, playlists] of sections) {
      if (!playlists.length) continue;
      this.list.appendChild(App.el("h3.letter-head", {text: App.t(title)}));
      playlists.forEach(p => this.list.appendChild(this.row(p)));
    }
    this.highlight();
  }

  row(playlist) {
    const el = App.el;
    const droppable = () => App.can("playlist") && playlist.canAdd;
    const row = el("a.playlist-row" + (droppable() ? "" : ".no-drop"), {
      href: "#/playlist/" + encodeURIComponent(playlist.id), title: playlist.name, dataset: {id: playlist.id}},
      el("span.artist-name", {text: playlist.name}),
      playlist.community ? el("span.badge-community", {title: App.t("playlist.community_help"), text: "⚑"}) : null,
      el("span.count", {text: playlist.songCount || ""}));
    Dnd.target(row, droppable, payload => App.playlists.add(playlist, payload));
    return row;
  }

  highlight() {
    const route = this.app.route || {};
    this.list.querySelectorAll("a.playlist-row.current").forEach(a => a.classList.remove("current"));
    if (route.view !== "playlist") return;
    const current = this.list.querySelector('a.playlist-row[data-id="' + CSS.escape(route.id) + '"]');
    if (current) current.classList.add("current");
  }
}

/* ---------- page d'une playlist ---------- */
Views.playlist = (() => {
  const el = App.el, t = App.t;

  return {
    /** focus : rang de la ligne à reprendre au clavier, après un déplacement (la page est alors relue sans « … »). */
    async render(main, route, focus) {
      if (focus === undefined) App.clear(main).appendChild(el("div.loading", {text: "…"}));
      this.stop();
      this.off = App.bus.on("playlist-changed", id => { if (id === route.id && !route.stale) this.render(main, route); });
      let data;
      try {
        data = await App.api.get("/api/playlist", {id: route.id});
      } catch (error) {
        if (!route.stale) App.clear(main).appendChild(el("p.page-error", {text: App.errorText(error)}));
        return;
      }
      if (route.stale) return;
      const songs = data.songs.map(s => (s.ext ? Object.assign({}, s, {coverId: s.imageUrl || ""}) : s));
      if (songs.some(s => s.ext)) await ExtMusic.favoritesReady();            // cœurs des titres d'ailleurs
      if (route.stale) return;
      const reload = async () => { await App.playlists.load(); this.render(main, route); };
      const canRemove = song => data.mine || (data.community && song.addedBy === App.user.username);
      const move = async (from, to) => {                     // le créateur seul ; un déplacement à la fois
        if (this.moving) return;
        this.moving = true;
        const order = songs.slice();
        order.splice(to, 0, order.splice(from, 1)[0]);
        try {
          await App.api.post("/api/playlist/reorder", {id: data.id,
            order: order.map(s => (s.ext ? {extId: s.extId} : {position: s.position}))});
        } catch (error) {
          App.toast(App.errorText(error), "error");
          to = from;
        }
        this.moving = false;
        if (!route.stale) this.render(main, route, to);      // relue : les rangs Subsonic ont changé
      };
      this.table = songs.length ? Views.songTable(songs, {showAlbum: true, numbered: true, addedBy: data.community,
        onMove: data.mine && App.can("playlist") && songs.length > 1 ? move : null,
        canRemove: App.can("playlist") ? canRemove : null,
        onRemove: async song => {
          try {
            if (song.ext) await App.api.post("/api/playlist/remove-ext", {id: data.id, extIds: [song.extId]});
            else await App.api.post("/api/playlist/remove", {id: data.id, positions: [song.position]});
            reload();
          } catch (error) { App.toast(App.errorText(error), "error"); }
        }}) : el("p.muted", {text: t("playlist.no_songs")});
      const facts = [data.mine ? null : t("playlist.by", {name: data.owner}), App.plural("album.tracks", songs.length),
                     songs.length ? App.duration(data.duration || songs.reduce((n, s) => n + (s.duration || 0), 0)) : null]
        .filter(Boolean).join(" · ");
      App.clear(main);
      App.append(main, [
        el("header.page-head", {}, el("h1", {text: data.name}),
          data.community ? el("span.chip.community-chip", {title: t("playlist.community_help"), text: t("playlist.community")}) : null),
        el("p.muted", {text: facts}),
        el("div.album-actions", {},
          App.setIcon(el("button.primary", {type: "button", disabled: !songs.length, onclick: () => App.player.playList(songs, 0)}),
                      "play", 16, false, t("album.play")),
          App.setIcon(el("button", {type: "button", disabled: !songs.length, onclick: () => App.player.playList(songs, 0, true)}),
                      "shuffle", 16, false, t("album.shuffle")),
          App.setIcon(el("button", {type: "button", disabled: !songs.length, onclick: () => App.player.add(songs)}),
                      "plus", 16, false, t("album.queue")),
          data.mine ? this.ownerTools(data, reload) : null),
        this.table]);
      const row = focus === undefined ? null : main.querySelectorAll("tr.song")[focus];
      if (row) row.focus();
    },

    /** Réservé au créateur : communautaire oui/non, renommer, supprimer. */
    ownerTools(data, reload) {
      const community = el("input", {type: "checkbox", checked: data.community, onchange: async () => {
        try {
          await App.api.post("/api/playlist/community", {id: data.id, on: community.checked});
          reload();
        } catch (error) { community.checked = !community.checked; App.toast(App.errorText(error), "error"); }
      }});
      return [
        el("label.community-toggle", {title: t("playlist.community_help")}, community, el("span", {text: t("playlist.community")})),
        el("button", {type: "button", text: t("playlist.rename"), onclick: async () => {
          const name = await Dialogs.ask(t("playlist.name"), data.name);
          if (!name) return;
          try { await App.api.post("/api/playlist/rename", {id: data.id, name}); reload(); }
          catch (error) { App.toast(App.errorText(error), "error"); }
        }}),
        el("button.danger", {type: "button", text: t("playlist.delete"), onclick: async () => {
          if (!await Dialogs.confirm(t("playlist.delete_confirm", {name: data.name}))) return;
          try {
            await App.api.post("/api/playlist/delete", {id: data.id});
            await App.playlists.load();
            location.hash = "#/";
          } catch (error) { App.toast(App.errorText(error), "error"); }
        }})];
    },

    stop() { if (this.off) this.off(); this.off = null; if (this.table && this.table.destroy) this.table.destroy(); this.table = null; },
    destroy() { this.stop(); },
  };
})();
