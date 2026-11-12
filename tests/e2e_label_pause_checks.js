/* Arrêt entre deux lots : aperçu immédiat et progressif, écoute/sauvegarde partielles, reprise et réponses tardives. */
module.exports = async (w, app, check, until, wait) => {
  const d = w.document, ui = w.eval("LabelDiscoveryUI"), dialogs = w.eval("Dialogs");
  const beforeGet = app.api.get, beforePost = app.api.post, beforePlay = app.player.playList, beforeAsk = dialogs.ask;
  const a = {id: "m11", title: "Arrival", artist: "ABBA", year: 1976, editions: ["101"]};
  const b = {id: "m12", title: "Discovery", artist: "Daft Punk", year: 2001, editions: ["103"]};
  const ranking = (albums, analyzed = 5, total = 12) => ({scores: albums.map(album => ({album, source: "discogs",
    value: 4, votes: 20, edition: album.editions[0]})), analyzed, total, complete: analyzed >= total, source: "discogs", excluded: 0});
  const tracks = (album, id, title) => ({album, tracks: [{edition: album.editions[0], album,
    track: {title, artist: album.artist, album: album.title}, choices: [{id, title, artist: album.artist}], status: "found"}]});
  let rankCalls = [], trackCalls = [], lateRanking, laterTrack, finishSave, submitted, played, createdPlaylist;
  let firstBatch, scenario = "between";
  const firstResult = tracks(a, "s1", "Dancing Queen"), secondResult = tracks(b, "s2", "Knowing Me");
  const secondTrack = new Promise(resolve => { laterTrack = resolve; });
  const roots = [];
  const panel = async () => {
    const root = ui.panel("Polar", {}, {id: "7", name: "Polar", companyOnly: false});
    d.body.appendChild(root);
    roots.push(root);
    await until(() => root.querySelector('.discovery-mode[data-mode="top"]'));
    return root;
  };
  app.api.get = (path, params) => {
    if (path === "/api/discogs/status") return Promise.resolve({sources: ["discogs"]});
    if (path === "/api/discogs/catalog") return Promise.resolve({complete: true, page: 1, pages: 1, albums: [a, b]});
    if (path === "/api/labels/ranking") {
      rankCalls.push(params.offset);
      if (scenario !== "between") return new Promise(resolve => { firstBatch = resolve; });
      if (rankCalls.length === 1) return Promise.resolve(ranking([a, b]));
      if (rankCalls.length === 2) return new Promise(resolve => { lateRanking = resolve; });
      return Promise.resolve(ranking([b, a], 12, 12));
    }
    if (path === "/api/labels/tracks") {
      trackCalls.push(params.album);
      return params.album === a.id ? Promise.resolve(firstResult) : secondTrack;
    }
    return beforeGet.call(app.api, path, params);
  };
  app.api.post = (path, body) => {
    if (path !== "/api/import/create") return beforePost.call(app.api, path, body);
    submitted = body;
    return new Promise((resolve, reject) => { finishSave = () => beforePost.call(app.api, path, body).then(data => {
      createdPlaylist = data.playlist.id;
      resolve(data);
    }, reject); });
  };
  app.player.playList = songs => { played = songs; };
  dialogs.ask = async () => "Label interrompu";
  try {
    const root = await panel();
    root.querySelector('.discovery-mode[data-mode="top"]').click();
    check("label : deuxième lot en attente après cinq disques analysés", await until(() => !!lateRanking) && trackCalls.length === 0);
    root.querySelector(".discovery-stop").click();
    check("label : arrêter prépare le classement disponible sans attendre le lot suivant", await until(() => !!root.querySelector(".discovery-play") &&
      !root.querySelector(".discovery-play").disabled) && trackCalls.join(",") === "m11,m12" &&
      root.querySelector(".discovery-scope").textContent.includes("5 disques analysés sur 12"));
    check("label : préparation annoncée et sélection rendue visible", root.querySelector(".discovery-preparation").textContent.includes("1 sur 2") &&
      root.querySelector(".discovery-preview") === d.activeElement);
    root.querySelector(".discovery-play").click();
    check("label : écoute possible avec le premier disque prêt", played.length === 1 && played[0].id === "s1");
    root.querySelector(".discovery-save").click();
    check("label : sauvegarde possible pendant la préparation", await until(() => !!submitted) && submitted.entries.length === 1 &&
      submitted.entries[0].songId === "s1");
    laterTrack(secondResult);
    check("label : les pistes suivantes complètent l’aperçu sans changer la lecture lancée", await until(() =>
      root.querySelector(".discovery-chosen").textContent === "2 titres choisis sur 2 proposés" &&
      !root.querySelector('.discovery-mode[data-mode="top"]').disabled) && played.length === 1);
    check("label : préparation terminée, sauvegarde en cours toujours protégée", root.querySelector(".discovery-save").disabled &&
      root.querySelector(".discovery-preparation").hidden && !root.querySelector(".discovery-resume").hidden);
    finishSave();
    check("label : playlist partielle enregistrée avec les seuls titres choisis au clic", await until(() =>
      w.location.hash.startsWith("#/playlist/") && d.querySelector("#main h1")?.textContent === "Label interrompu") &&
      d.querySelectorAll("#main tr.song").length === 1 && !!d.querySelector('#main tr.song[data-id="s1"]'));
    lateRanking(ranking([b], 12, 12));
    await wait(30);
    check("label : réponse tardive du lot abandonné ignorée", root.querySelector(".discovery-scope").textContent.includes("5 disques analysés sur 12") &&
      root.querySelectorAll(".discovery-track").length === 2 && rankCalls.length === 2);
    root.querySelector(".discovery-resume").click();
    check("label : reprise au bon offset puis sélection du classement complété", await until(() =>
      root.querySelector(".discovery-scope").textContent.includes("Catalogue analysé : 12") &&
      root.querySelectorAll(".discovery-track").length === 2 && !root.querySelector('.discovery-mode[data-mode="top"]').disabled) &&
      rankCalls.join(",") === "0,5,5");
    root.remove();

    for (const empty of [false, true]) {
      scenario = "first";
      firstBatch = null;
      rankCalls = [];
      const early = await panel();
      early.querySelector('.discovery-mode[data-mode="top"]').click();
      await until(() => !!firstBatch);
      early.querySelector(".discovery-stop").click();
      check("label : arrêt avant le premier résultat annoncé sans relancer de lot", early.querySelector(".discovery-progress").textContent.includes("Arrêt demandé") &&
        early.querySelector(".discovery-stop").disabled && rankCalls.length === 1);
      firstBatch(ranking(empty ? [] : [a]));
      if (empty) {
        check("label : arrêt sans disque classable expliqué, poursuite disponible", await until(() =>
          early.querySelector(".discovery-progress").textContent.includes("aucun disque classable")) &&
          !early.querySelector(".discovery-play") && !early.querySelector(".discovery-resume").hidden);
      } else {
        check("label : premier lot arrêté transformé en sélection écoutable", await until(() =>
          early.querySelector(".discovery-play") && !early.querySelector(".discovery-play").disabled) && rankCalls.length === 1);
      }
      early.remove();
    }
  } finally {
    roots.forEach(root => root.remove());
    app.api.get = beforeGet;
    app.api.post = beforePost;
    app.player.playList = beforePlay;
    dialogs.ask = beforeAsk;
    if (createdPlaylist) {
      w.location.hash = "#/";
      await beforePost.call(app.api, "/api/playlist/delete", {id: createdPlaylist});
      await app.playlists.load();
    }
  }
};
