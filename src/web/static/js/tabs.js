"use strict";
// Onglets : accueil, albums, artistes, favoris, playlists, radios

/* ---------- Onglets ---------- */
tabs.home = () => openView("Accueil", async c => {
  const tiles = document.createElement("div"); tiles.className = "tiles";
  [["shuffle", "Mix aléatoire", () => mixRandom()],
   ["heart", "Mix favoris", mixFav],
   ["disc", "Découverte", () => mixAlbums("random", 6)],
   ["radio", "Derniers ajouts", () => mixAlbums("newest", 3)],
   ["plus", "Créer un mix", () => openView("Créer un mix", mixBuilder)]].forEach(([icon, label, fn]) => {
    const b = document.createElement("button"); b.className = "tile";
    b.innerHTML = ic(icon, 28) + "<span>" + label + "</span>"; b.onclick = safe(fn); tiles.appendChild(b);
  });
  c.appendChild(tiles);
  const loaders = [["Écoutés récemment", "recent"], ["Ajoutés récemment", "newest"],
                   ["Plus écoutés", "frequent"], ["À redécouvrir", "random"]].map(([title, type]) => {
    const h = header(c, title); const sh = document.createElement("div"); sh.className = "shelf"; c.appendChild(sh);
    return async () => {
      try {
        const j = await api("getAlbumList2", {type, size: 14});
        ((j.albumList2 && j.albumList2.album) || []).forEach(al => sh.appendChild(card(al)));
        if (!sh.children.length) { h.remove(); sh.remove(); }
      } catch (e) { h.remove(); sh.remove(); }
    };
  });
  (async () => { for (const f of loaders) await f(); })();   // l'une après l'autre : ménage un serveur lent
  header(c, "Décennies"); const dc = document.createElement("div"); dc.className = "chips"; c.appendChild(dc);
  [1960, 1970, 1980, 1990, 2000, 2010, 2020].forEach(y => {
    const b = document.createElement("button"); b.textContent = "Années " + String(y).slice(2);
    b.onclick = safe(() => mixRandom({fromYear: y, toYear: y + 9})); dc.appendChild(b);
  });
  actions(c, [], [["list", "Classement : " + (browseMode === "folders" ? "dossiers" : "tags"), async () => {
    browseMode = browseMode === "folders" ? "tags" : "folders";
    try { await fetch("/settings?browse_mode=" + browseMode); toast("Classement par " + (browseMode === "folders" ? "dossiers" : "tags")); tab("home"); } catch (e) { toast(e.message); }
  }]].concat(window.HIFI && window.HIFI.available ? [["volume", "Haute fidélité : " + (window.HIFI.enabled ? "oui (mpv)" : "non (navigateur)"), toggleHifi]] : []).concat([["radio", "Sources externes (Jamendo, YouTube)", () => openView("Sources externes", externalSettingsView)], ["refresh", "Actualiser la bibliothèque", async () => {
    try { await fetch("/cache/clear"); toast("Bibliothèque actualisée"); tab("home"); } catch (e) { toast(e.message); }
  }]]));
  // appui long (1,5 s) sur « Actualiser » : tout vider, pochettes, bios et paroles compris
  const rb = Array.from(c.querySelectorAll("button")).find(b => /Actualiser/.test(b.textContent));
  if (rb) {
    let t = null;
    const start = () => { t = setTimeout(async () => {
      t = null; rb.dataset.long = "1";
      try { await fetch("/cache/clear?all=1"); bustAll = String(Date.now()); bust = {}; saveBust(); toast("Tout a été rafraîchi"); tab("home"); } catch (e) { toast(e.message); }
    }, 1500); };
    const stop = () => { if (t) { clearTimeout(t); t = null; } };
    rb.addEventListener("pointerdown", start); rb.addEventListener("pointerup", stop);
    rb.addEventListener("pointerleave", stop); rb.addEventListener("pointercancel", stop);
    rb.addEventListener("click", e => { if (rb.dataset.long) { delete rb.dataset.long; e.stopImmediatePropagation(); } }, true);
  }
});

tabs.albums = () => openView("Albums", async c => {
  const types = [["newest", "Récents"], ["recent", "Écoutés"], ["frequent", "Plus écoutés"],
                 ["random", "Aléatoire"], ["alphabeticalByName", "A-Z"], ["byYear", "Par année"]];
  const chips = document.createElement("div"); chips.className = "chips sticky";
  const grid = document.createElement("div"); grid.className = "grid";
  const note = document.createElement("div"); note.className = "msg"; note.style.color = "var(--soft)";
  note.textContent = "Chargement\u2026"; note.hidden = true;
  c.appendChild(chips); c.appendChild(note); c.appendChild(grid);
  async function load(type) {
    chips.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.t === type));
    grid.innerHTML = ""; main.scrollTop = 0;
    let offset = 0, done = false, busy = false;
    const size = 40;
    const more = async () => {
      if (done || busy) return;
      busy = true; note.hidden = false;
      try {
        const p = {type, size, offset};
        if (type === "byYear") { p.fromYear = 2030; p.toYear = 1900; }
        const a = ((await api("getAlbumList2", p)).albumList2.album) || [];
        a.forEach(al => grid.appendChild(card(al)));
        offset += a.length; if (a.length < size) done = true;
      } catch (e) { done = true; grid.insertAdjacentHTML("afterend", '<div class="msg">' + esc(e.message) + "</div>"); }
      busy = false; note.hidden = true;
    };
    main.onscroll = () => { if (main.scrollTop + main.clientHeight > main.scrollHeight - 300) more(); };
    await more();
  }
  types.forEach(([t, label]) => {
    const b = document.createElement("button"); b.textContent = label; b.dataset.t = t;
    b.onclick = () => load(t); chips.appendChild(b);
  });
  await load("newest");
});

tabs.artists = () => openView("Artistes", async c => {
  c.innerHTML = '<div class="msg" style="color:var(--soft)">Chargement des artistes\u2026<br>La première fois, avec une grande bibliothèque, cela peut prendre quelques minutes ; ensuite c\u2019est instantané.</div>';
  const idx = (await api("getArtists")).artists.index || [];
  c.innerHTML = "";
  const items = [];
  idx.forEach(g => { items.push({h: g.name}); (g.artist || []).forEach(ar => items.push({ar})); });
  if (!items.length) { c.innerHTML = '<div class="msg">Aucun artiste.</div>'; return; }
  const bar = document.createElement("div"); bar.className = "chips sticky";
  const list = document.createElement("div");
  c.appendChild(bar); c.appendChild(list);
  const heads = {};
  let shown = 0;
  const STEP = 80;     // lignes ajoutées à chaque fois : la page reste fluide même avec des milliers d'artistes
  const renderMore = upTo => {
    const end = Math.min(items.length, Math.max(shown + STEP, upTo || 0));
    for (; shown < end; shown++) {
      const it = items[shown];
      if (it.h !== undefined) heads[it.h] = header(list, it.h); else list.appendChild(artistRow(it.ar));
    }
  };
  idx.forEach(g => {
    const b = document.createElement("button"); b.textContent = g.name;
    b.onclick = () => {
      const k = items.findIndex(x => x.h === g.name);
      if (k >= shown) renderMore(k + 1);
      const el = heads[g.name];
      if (el) main.scrollTop = el.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop - 46;
    };
    bar.appendChild(b);
  });
  renderMore(0);
  main.onscroll = () => { if (shown < items.length && main.scrollTop + main.clientHeight > main.scrollHeight - 400) renderMore(0); };
});

tabs.fav = () => openView("Favoris", async c => {
  const s = (await api("getStarred2")).starred2 || {};
  const songs = (s.song || []).concat(await loadExtFavorites());       // Subsonic puis titres d'ailleurs, dans la même liste
  if (songs.length) { header(c, "Titres (" + songs.length + ")"); actions(c, songs, [["plus", "Playlist", () => addToPlaylist(songs)]]); songRows(c, songs); }
  if ((s.album || []).length) {
    header(c, "Albums"); const g = document.createElement("div"); g.className = "grid"; c.appendChild(g);
    s.album.forEach(al => g.appendChild(card(al)));
  }
  if ((s.artist || []).length) { header(c, "Artistes"); s.artist.forEach(ar => c.appendChild(artistRow(ar))); }
  if (!songs.length && !(s.album || []).length && !(s.artist || []).length)
    c.innerHTML = '<div class="msg">Aucun favori pour l’instant.</div>';
});

tabs.playlists = () => openView("Playlists", async c => {
  await localPlaylistsSection(c);
  header(c, "Playlists Subsonic");
  const ps = (await api("getPlaylists")).playlists.playlist || [];
  actions(c, [], [["plus", "Nouvelle playlist", async () => {
    const name = await askText("Nom de la nouvelle playlist", "");
    if (!name) return;
    try { await api("createPlaylist", {name}); toast("Playlist créée"); tab("playlists"); } catch (e) { toast(e.message); }
  }]]);
  if (!ps.length) { c.insertAdjacentHTML("beforeend", '<div class="msg">Aucune playlist pour l’instant.</div>'); return; }
  ps.forEach(p => c.appendChild(row(cover(p.coverArt), p.name, p.songCount + " titre(s)",
    () => openView(p.name, cc => playlistView(p.id, cc)))));
});

tabs.radios = () => openView("Radios", async c => {
  header(c, "Radios Internet");
  const holder = document.createElement("div"); c.appendChild(holder);
  api("getInternetRadioStations").then(j => {
    const st = (j.internetRadioStations && j.internetRadioStations.internetRadioStation) || [];
    if (!st.length) { holder.innerHTML = '<div class="msg">Aucune radio enregistrée sur le serveur Subsonic.</div>'; return; }
    st.forEach(r => holder.appendChild(row("", r.name, r.homePageUrl || "Radio Internet", () =>
      playQueue([{id: "radio-" + r.id, title: r.name, artist: "Radio Internet", album: "", streamUrl: r.streamUrl}], 0))));
  }).catch(() => { holder.innerHTML = '<div class="msg">Radios Internet indisponibles sur ce serveur.</div>'; });
  header(c, "Radio par genre");
  const gh = document.createElement("div"); gh.className = "tiles"; c.appendChild(gh);
  api("getGenres").then(j => {
    const gs = ((j.genres && j.genres.genre) || []).slice().sort((a, b) => (b.songCount || 0) - (a.songCount || 0)).slice(0, 30);
    if (!gs.length) { gh.innerHTML = '<div class="msg">Aucun genre trouvé.</div>'; return; }
    gs.forEach(g => {
      const b = document.createElement("button"); b.className = "tile";
      b.innerHTML = ic("radio", 26) + "<span>" + esc(g.value) + "</span>";
      b.onclick = safe(() => mixRandom({genre: g.value})); gh.appendChild(b);
    });
  }).catch(() => { gh.innerHTML = '<div class="msg">Genres indisponibles.</div>'; });
  header(c, "Radio d’artiste ou de titre");
  c.insertAdjacentHTML("beforeend", '<div class="msg" style="color:var(--soft)">Ouvrez la page d’un artiste puis « Radio de l’artiste », ou le menu « ⋯ » d’un titre puis « Radio de ce titre ». Les suggestions viennent de Last.fm via votre serveur.</div>');
});
