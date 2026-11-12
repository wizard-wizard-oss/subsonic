/* Réponses différées : progression, petite file automatique, choix conservés et abandon du panneau précédent. */
module.exports = async (w, app, check, until, wait) => {
  const d = w.document, Playlist = w.eval("DiscoveryTracks.Playlist");
  const beforeGet = app.api.get, beforePost = app.api.post;
  const pending = [], calls = [];
  let generation = 1, youtube = true;
  const root = d.createElement("div");
  d.body.appendChild(root);
  const track = (title, status = "missing", choices = []) => ({edition: "103", track: {title, artist: "Artist"}, status, choices});
  const item = id => ({id: "yt-" + id, youtubeId: id, ext: "youtube", title: "Artist - Song", artist: "Artist", duration: 240});
  app.api.get = (path, params) => path === "/api/ext/status" ? Promise.resolve({youtube}) : beforeGet.call(app.api, path, params);
  app.api.post = (path, body) => {
    if (path !== "/api/labels/versions") return beforePost.call(app.api, path, body);
    calls.push(body.track.title);
    return new Promise((resolve, reject) => pending.push({resolve, reject}));
  };
  try {
    const local = {id: "s1", title: "Local", artist: "Artist"};
    const playlist = new Playlist(root, {}, "Playlist", () => generation === 1);
    playlist.show([track("Local", "found", [local]), track("Missing"), track("Doubt", "doubt", [local]), track("Last")]);
    check("YouTube : recherche automatique limitée à deux demandes, bibliothèque sûre épargnée", await until(() => pending.length === 2) &&
      !calls.includes("Local") && calls.length === 2);
    const missing = playlist.rows[1], doubt = playlist.rows[2];
    check("YouTube : attente visible immédiatement et bouton désactivé", missing.versions.root.getAttribute("aria-busy") === "true" &&
      missing.versions.status.textContent.includes("Recherche") && missing.versions.button.disabled);
    missing.versions.find();
    check("YouTube : clic et recherche automatique partagent la même demande", calls.length === 2);
    doubt.select.value = "0";
    doubt.select.dispatchEvent(new w.Event("change"));
    missing.select.value = "-1";
    missing.select.dispatchEvent(new w.Event("change"));
    pending[0].resolve({items: [item("chosen12345")]});
    pending[1].resolve({items: [item("another1234")]});
    check("YouTube : choix local et titre ignoré conservés à l’arrivée des résultats", await until(() => calls.length === 3) &&
      doubt.item.id === "s1" && missing.item === null && missing.versions.results.querySelectorAll(".discovery-video").length === 1);
    missing.versions.results.querySelector(".discovery-video").click();
    check("YouTube : version visible sélectionnable sans lancer la lecture", missing.item.youtubeId === "chosen12345" &&
      missing.versions.results.querySelector(".discovery-video").getAttribute("aria-pressed") === "true");
    pending[2].reject(new (w.eval("ApiError"))(400, "ext.too_many_searches"));
    check("YouTube : erreur lisible et bouton pour réessayer", await until(() => playlist.rows[3].versions.status.classList.contains("page-error")) &&
      !playlist.rows[3].versions.button.disabled && playlist.rows[3].versions.button.textContent.includes("Réessayer"));
    playlist.rows[3].versions.button.click();
    check("YouTube : nouvelle recherche annoncée pendant la relance", await until(() => pending.length === 4) &&
      playlist.rows[3].versions.root.getAttribute("aria-busy") === "true");
    pending[3].resolve({items: []});
    check("YouTube : absence de correspondance expliquée", await until(() => playlist.rows[3].versions.loaded) &&
      playlist.rows[3].versions.status.textContent.includes("suffisamment proche"));

    const start = calls.length;
    const previous = new Playlist(root, {}, "Previous", () => generation === 1);
    previous.show([track("Old A"), track("Old B"), track("Old C")]);
    await until(() => calls.length === start + 2);
    generation++;
    pending[4].resolve({items: [item("late1234567")]});
    pending[5].resolve({items: [item("late7654321")]});
    await wait(30);
    check("YouTube : changer de sélection abandonne les réponses et la file précédentes", calls.length === start + 2 &&
      root.querySelectorAll(".discovery-video").length === 0);

    youtube = false;
    new Playlist(root, {}, "Disabled").show([track("Disabled")]);
    check("YouTube : source désactivée expliquée sans lancer de recherche", await until(() => root.textContent.includes(app.t("ext.disabled"))) &&
      calls.length === start + 2);
  } finally {
    root.remove();
    app.api.get = beforeGet;
    app.api.post = beforePost;
  }
};
