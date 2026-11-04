"use strict";
// Playlists, file d'attente, menus

/* ---------- Playlists, file d'attente, menus ---------- */
function enqueue(songs, next) {
  if (!queue.length) { playQueue(songs, 0); return; }
  if (next) queue.splice(qi + 1, 0, ...songs); else queue.push(...songs);
  toast(next ? "Lecture ensuite" : "Ajouté à la file d’attente");
  if (!$("#fqueue").hidden) renderQueue();
}
async function addToPlaylist(songs) {
  if (!songs.length) return;
  const external = songs.some(isExternal);          // une playlist Subsonic ne peut contenir que des titres de la bibliothèque
  try {
    const items = [];
    if (!external) {
      const ps = (await api("getPlaylists")).playlists.playlist || [];
      const ids = songs.map(s => s.id);
      items.push({icon: "plus", label: "Nouvelle playlist…", fn: async () => {
        const name = await askText("Nom de la nouvelle playlist", "");
        if (!name) return;
        try { await api("createPlaylist", {name, songId: ids}); toast("Playlist « " + name + " » créée"); } catch (e) { toast(e.message); }
      }});
      ps.forEach(p => items.push({icon: "list", label: p.name + " (" + p.songCount + ")", fn: async () => {
        try { await api("updatePlaylist", {playlistId: p.id, songIdToAdd: ids}); toast("Ajouté à « " + p.name + " »"); } catch (e) { toast(e.message); }
      }}));
    }
    (await localPlaylistChoices(songs)).forEach(it => items.push(it));
    openSheet("Ajouter à une playlist", items);
  } catch (e) { toast(e.message); }
}
function songMenu(s, ctx) {
  const items = [
    {icon: "next", label: "Lire ensuite", fn: () => enqueue([s], true)},
    {icon: "list", label: "Ajouter à la file d’attente", fn: () => enqueue([s], false)},
    {icon: "plus", label: "Ajouter à une playlist…", fn: () => addToPlaylist([s])},
    ];
  if (!isExternal(s)) items.push({icon: "radio", label: "Radio de ce titre", fn: () => radioFromSong(s)});
  if (s.albumId) items.push({icon: "disc", label: "Voir l’album", fn: () => { closeFull(); openView(s.album || "Album", c => albumView(s.albumId, c)); }});
  if (s.artist) items.push({icon: "user", label: "Voir l’artiste", fn: async () => { const id = await artistIdOf(s); if (!id) return toast("Artiste introuvable"); closeFull(); openView(s.artist || "Artiste", c => artistView(id, c)); }});
  if (ctx && ctx.playlistId) items.push({icon: "trash", label: "Retirer de cette playlist", fn: async () => {
    try { await api("updatePlaylist", {playlistId: ctx.playlistId, songIndexToRemove: ctx.index}); toast("Retiré"); render(); } catch (e) { toast(e.message); }
  }});
  if (ctx && ctx.localPlaylistId) items.push({icon: "trash", label: "Retirer de cette playlist locale", fn: async () => {
    try { await extPost("remove", {id: ctx.localPlaylistId, index: ctx.index}); toast("Retiré"); render(); } catch (e) { toast(e.message); }
  }});
  openSheet(s.title, items);
}
