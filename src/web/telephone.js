"use strict";
// Page du téléphone : recherche dans la bibliothèque du Pi, ajout à la file commune, aperçu de la file.
// Le code (dans l'adresse du QR code) accompagne chaque demande.

const code = new URLSearchParams(location.search).get("c") || "";
const $ = id => document.getElementById(id);
const field = $("q"), state = $("state");
let typingTimer = null, sent = null;

function show(message, isError) { state.textContent = message; state.className = isError ? "err" : ""; }

async function post(path, body) {
  const r = await fetch(path, {method: "POST", headers: {"Content-Type": "application/json"},
                               body: JSON.stringify(Object.assign({code}, body))});
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || "Erreur " + r.status);
  return j;
}
const failed = e => show(e.message === "Failed to fetch" ? "Pi injoignable : êtes-vous sur le même Wi-Fi ?" : e.message, true);

function button(label, cls, onClick) {
  const b = document.createElement("button"); b.type = "button"; b.textContent = label;
  if (cls) b.className = cls;
  b.onclick = onClick;
  return b;
}

/* ---------- saisie : texte envoyé à l'écran, artistes suggérés, titres trouvés ---------- */
async function sendText(text) {
  if (text === sent) return;
  sent = text;
  try {
    const [typed, found] = await Promise.all([post("/tel/text", {text}), text.trim().length >= 2 ? post("/tel/search", {text}) : {songs: []}]);
    if (field.value !== text) return;
    showArtists(typed.suggestions || []);
    showSongs(found.songs || []);
    show("");
  } catch (e) { sent = null; failed(e); }
}

function showArtists(artists) {
  $("sug").innerHTML = "";
  artists.forEach(artist => $("sug").appendChild(button(artist.name, "", async () => {
    try { await post("/tel/pick", {id: artist.id}); show("« " + artist.name + " » ouvert sur le Pi ✓"); } catch (e) { failed(e); }
  })));
}

function showSongs(songs) {
  const box = $("songs");
  box.innerHTML = "";
  songs.forEach(song => {
    const line = document.createElement("div"); line.className = "song";
    const text = document.createElement("div"); text.className = "t";
    const title = document.createElement("b"); title.textContent = song.title;
    const meta = document.createElement("small"); meta.textContent = [song.artist, song.album].filter(Boolean).join(" · ");
    text.appendChild(title); text.appendChild(meta);
    line.appendChild(text);
    line.appendChild(button("Après ce titre", "next", () => addToQueue(song, "next")));
    line.appendChild(button("À la fin", "", () => addToQueue(song, "end")));
    box.appendChild(line);
  });
}

async function addToQueue(song, mode) {
  try {
    await post("/tel/queue/add", {id: song.id, mode});
    show("« " + song.title + " » ajouté " + (mode === "next" ? "après le titre en cours" : "à la fin de la file") + " ✓");
    refreshQueue();
  } catch (e) { failed(e); }
}

/* ---------- lien partagé ---------- */
async function addLink(mode) {
  const url = $("link").value.trim();
  if (!url) return show("Collez d’abord un lien", true);
  show("Recherche du titre…");
  try {
    const r = await post("/tel/link", {url, mode});
    show("« " + r.added + " » ajouté" + (r.source === "library" ? " (depuis la bibliothèque)" : " (YouTube)") + " ✓");
    $("link").value = "";
    refreshQueue();
  } catch (e) { failed(e); }
}
$("linkNext").onclick = () => addLink("next");
$("linkEnd").onclick = () => addLink("end");

/* ---------- fichier envoyé du téléphone ---------- */
$("file").onchange = () => {
  const file = $("file").files[0];
  if (!file) return;
  const request = new XMLHttpRequest();
  request.open("POST", "/tel/upload");
  request.setRequestHeader("X-Code", code);
  request.setRequestHeader("X-File-Name", encodeURIComponent(file.name));
  request.setRequestHeader("X-Mode", $("fileMode").value);
  request.upload.onprogress = e => { if (e.lengthComputable) show("Envoi… " + Math.round(e.loaded / e.total * 100) + " %"); };
  request.onload = () => {
    let j = {};
    try { j = JSON.parse(request.responseText); } catch (e) { /* réponse vide */ }
    if (request.status === 200) { show("« " + j.added + " » envoyé et ajouté à la file ✓"); refreshQueue(); }
    else show(j.error || "Erreur " + request.status, true);
    $("file").value = "";
  };
  request.onerror = () => show("Pi injoignable : êtes-vous sur le même Wi-Fi ?", true);
  request.send(file);
};

/* ---------- aperçu de la file ---------- */
async function refreshQueue() {
  let view;
  try { view = await post("/tel/queue", {}); } catch (e) { return; }
  const box = $("queue");
  box.innerHTML = "";
  const line = (text, cls, note) => {
    const d = document.createElement("div"); d.className = "q" + (cls ? " " + cls : ""); d.textContent = text;
    if (note) { const s = document.createElement("small"); s.textContent = " · " + note; d.appendChild(s); }
    box.appendChild(d);
  };
  const label = t => t.title + (t.artist ? " — " + t.artist : "");
  if (view.current) line("▶ " + label(view.current), "now");
  view.pending.forEach(t => line(label(t), "", "en cours d’ajout"));
  view.upcoming.forEach(t => line(label(t), "", t.addedBy === "phone" ? "ajouté par téléphone" : ""));
  if (!view.current && !view.upcoming.length && !view.pending.length) box.innerHTML = "<p>La file est vide : ajoutez le premier titre !</p>";
}

field.addEventListener("input", () => { clearTimeout(typingTimer); typingTimer = setTimeout(() => sendText(field.value), 300); });
field.addEventListener("keydown", e => { if (e.key === "Enter") { clearTimeout(typingTimer); sendText(field.value); field.blur(); } });
if (!code) show("Adresse incomplète : scannez le QR code affiché sur le Pi", true);
else { refreshQueue(); setInterval(refreshQueue, 4000); }
