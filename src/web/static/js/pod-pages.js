"use strict";
// Podcasts : les écrans (accueil, thèmes, recherche, ma liste, réglages, fiche d'un podcast)

/* ---------- Navigation : une pile d'écrans, le bouton retour dépile ---------- */
const navStack = [];
let sources = {itunes: true, podcastindex: false}, themeList = [], french = true;
let searchState = {text: "", items: null};
const podcastHistory = new SearchHistoryList("podcasts");
let pickSearch = null;                                // relance une recherche passée (défini par l'écran Recherche)         // dernière recherche : retrouvée en revenant en arrière

function showScreen(title, build, {root = false} = {}) {
  if (navStack.length) navStack[navStack.length - 1].scroll = main.scrollTop;
  if (root) navStack.length = 0;
  navStack.push({title, build});
  renderTop();
}
function renderTop() {
  const view = navStack[navStack.length - 1];
  $("#top").hidden = navStack.length < 2;
  $("#title").textContent = view.title;
  showKeyboard(false);
  main.innerHTML = "";
  main.classList.remove("in"); void main.offsetWidth; main.classList.add("in");
  main.scrollTop = 0;
  view.build(main);
  if (view.scroll) restoreScroll(view.scroll);
}
function restoreScroll(top) {
  [0, 250, 700].forEach(delay => setTimeout(() => { if (main.scrollHeight >= top) main.scrollTop = top; }, delay));
}
function goBack() {
  if (navStack.length < 2) return;
  navStack.pop();
  renderTop();
}

/* Charge des données puis construit l'écran ; une erreur réseau s'affiche à la place du contenu */
async function withData(container, loader, build) {
  container.appendChild(loadingMessage());
  let data;
  try { data = await loader(); } catch (e) { container.innerHTML = ""; container.appendChild(emptyMessage(e.message)); return; }
  if (!container.isConnected) return;
  container.innerHTML = "";
  build(data);
}

/* ---------- Accueil ---------- */
function pageHome(root) {
  withData(root, () => pget("home"), data => {
    if (data.resume.length) root.appendChild(shelf("Reprendre l’écoute", data.resume, resumeCard));
    if (data.subs.length) root.appendChild(shelf("Mes podcasts", data.subs.map(s => Object.assign({subscribed: true}, s)), podcastCard));
    const latest = el("section", "psection"); root.appendChild(latest);
    data.rows.forEach(r => root.appendChild(shelf(r.title, r.items, podcastCard)));
    if (!data.rows.length && !data.resume.length && !data.subs.length) root.appendChild(emptyMessage("Rien à afficher : essayez l’onglet Thèmes ou la Recherche."));
    if (data.subs.length) fillLatest(latest);
  });
}
async function fillLatest(section) {
  try {
    const lib = await pget("library");
    if (!lib.latest.length || !section.isConnected) return;
    section.appendChild(heading("Nouveaux épisodes"));
    lib.latest.slice(0, 8).forEach(e => section.appendChild(latestRow(e)));
  } catch (e) { /* l'accueil reste utilisable sans cette rangée */ }
}

/* ---------- Thèmes ---------- */
function pageThemes(root) {
  root.appendChild(heading("Parcourir par thème"));
  root.appendChild(frenchChip(() => {}));
  const tiles = el("div", "ptiles");
  themeList.forEach(t => tiles.appendChild(themeTile(t)));
  root.appendChild(tiles);
}
function openTheme(theme) {
  showScreen(theme.label, root => withData(root, () => pget("theme", {id: theme.key}), data => {
    root.appendChild(frenchChip(() => renderTop()));
    if (!data.items.length) return root.appendChild(emptyMessage("Aucun podcast trouvé pour ce thème."));
    if (!sources.podcastindex) root.appendChild(el("div", "phint", "Astuce : ajoutez une clé Podcast Index (Réglages) pour des tendances par thème plus riches."));
    root.appendChild(cardGrid(data.items));
  }));
}

/* ---------- Recherche ---------- */
function pageSearch(root) {
  root.appendChild(frenchChip(() => { if (searchState.text.trim().length >= 2) runSearch(searchState.text, results); }));
  const field = el("div", "psearch"); root.appendChild(field);
  const results = el("div", "presults"); root.appendChild(results);
  let timer = null;
  const input = new TextField(field, {onEnter: t => { clearTimeout(timer); showKeyboard(false); runSearch(t, results); },
                                      onChange: t => { searchState.text = t; clearTimeout(timer); timer = setTimeout(() => runSearch(t, results), 900); }});
  field.dataset.placeholder = "Touchez ici pour chercher un podcast…";
  pickSearch = text => { input.text = text; input.paint(); showKeyboard(false); runSearch(text, results); };
  results.addEventListener("click", e => { if (e.target.closest(".pcard")) podcastHistory.remember(searchState.text); }, true);   // un podcast ouvert = recherche utile
  if (searchState.text) {                                  // retour à la recherche : on retrouve texte et résultats
    input.text = searchState.text; input.paint();
    if (searchState.items) showResults(results, searchState.items, searchState.text);
  } else { input.focus(); podcastHistory.show(results, pickSearch); }
}
function showResults(results, items, text) {
  results.innerHTML = "";
  results.appendChild(items.length ? cardGrid(items) : emptyMessage("Aucun résultat pour « " + text + " »."));
}
async function runSearch(text, results) {
  searchState = {text, items: null};
  results.innerHTML = "";
  if (text.trim().length < 2) { if (pickSearch) podcastHistory.show(results, pickSearch); return; }
  results.appendChild(loadingMessage());
  try {
    const data = await pget("search", {q: text});
    searchState.items = data.items;
    if (results.isConnected) showResults(results, data.items, text);
  } catch (e) { if (results.isConnected) { results.innerHTML = ""; results.appendChild(emptyMessage(e.message)); } }
}

/* ---------- Ma liste ---------- */
function pageMine(root) {
  withData(root, () => pget("library"), lib => {
    if (!lib.subs.length) return root.appendChild(emptyMessage("Vous n’êtes abonné à aucun podcast. Ouvrez-en un et touchez « S’abonner »."));
    root.appendChild(heading("Mes abonnements"));
    root.appendChild(cardGrid(lib.subs.map(s => Object.assign({subscribed: true}, s))));
    if (lib.latest.length) {
      const sec = el("section", "psection"); sec.appendChild(heading("Derniers épisodes"));
      lib.latest.forEach(e => sec.appendChild(latestRow(e)));
      root.appendChild(sec);
    }
  });
}

/* ---------- Fiche d'un podcast ---------- */
function openShow(feed, card) {
  showScreen((card && card.title) || "Podcast", root => withData(root, () => pget("show", {feed}), show => {
    const head = el("div", "phero");
    head.appendChild(artwork(show.image || (card && card.image), show.title, "big"));
    const info = el("div", "pinfo");
    info.appendChild(el("b", "", esc(show.title)));
    if (show.author) info.appendChild(el("small", "", esc(show.author)));
    info.appendChild(el("p", "", esc(show.desc)));
    const actions = el("div", "pactions");
    actions.appendChild(subscribeButton(show, card));
    actions.appendChild(hideButton(show));
    info.appendChild(actions);
    head.appendChild(info);
    root.appendChild(head);
    const similar = el("div"); root.appendChild(similar);
    fillSimilar(similar, show, card);
    root.appendChild(heading(show.episodes.length + " épisodes"));
    const context = {feed, podcast: show.title, image: show.image};
    show.episodes.forEach(e => root.appendChild(episodeRow(e, context)));
  }));
}
async function fillSimilar(box, show, card) {
  try {
    const data = await pget("similar", {feed: show.feed, genre: (card && card.genre) || "", title: show.title});
    if (data.items.length && box.isConnected) box.appendChild(shelf("Dans le même genre", data.items, podcastCard));
  } catch (e) { /* la fiche reste utilisable sans cette rangée */ }
}
function subscribeButton(show, card) {
  const button = el("button", "primary");
  const paint = () => { button.innerHTML = show.subscribed ? ic("check", 18) + " Abonné" : ic("plus", 18) + " S’abonner"; };
  paint();
  button.onclick = async () => {
    try {
      if (show.subscribed) await ppost("unsubscribe", {feed: show.feed});
      else await ppost("subscribe", {feed: show.feed, title: show.title, image: show.image, author: show.author});
      show.subscribed = !show.subscribed; if (card) card.subscribed = show.subscribed; paint();
    } catch (e) { toast(e.message); }
  };
  return button;
}
function hideButton(show) {
  const button = el("button", "", "Masquer");
  button.onclick = async () => {
    try { await ppost("hide", {feed: show.feed}); toast("Podcast masqué"); goBack(); } catch (e) { toast(e.message); }
  };
  return button;
}

/* ---------- Réglages : annuaires et clé Podcast Index ---------- */
function pageSettings(root) {
  root.appendChild(heading("Langue"));
  root.appendChild(frenchChip(() => {}));
  root.appendChild(heading("Annuaires"));
  root.appendChild(sourceLine("Apple Podcasts", "toujours disponible, sans clé", true));
  const index = sourceLine("Podcast Index", "tendances par thème, plus de choix", sources.podcastindex);
  root.appendChild(index);
  const form = el("div", "pform");
  form.appendChild(el("p", "", "Clé gratuite à créer sur <b>api.podcastindex.org</b>. Touchez un champ pour saisir au clavier de l’écran (touche 123# pour les symboles)."));
  const keyBox = el("div"), secretBox = el("div");
  const key = new TextField(keyBox, {onEnter: () => secret.focus()});
  const secret = new TextField(secretBox, {secret: true, onEnter: () => save()});
  keyBox.dataset.placeholder = "Clé API"; secretBox.dataset.placeholder = "Secret";
  form.appendChild(keyBox); form.appendChild(secretBox);
  const actions = el("div", "pactions");
  const saveButton = el("button", "primary", "Enregistrer"); const clearButton = el("button", "", "Désactiver");
  actions.appendChild(saveButton); actions.appendChild(clearButton); form.appendChild(actions);
  root.appendChild(form);
  const save = () => storeKey(key.text.trim(), secret.text.trim());
  saveButton.onclick = save;
  clearButton.onclick = () => storeKey("", "");
}
function sourceLine(name, detail, on) {
  return el("div", "psource" + (on ? " on" : ""), "<i></i><b>" + esc(name) + "</b><small>" + esc(detail) + "</small><em>" + (on ? "actif" : "inactif") + "</em>");
}
async function storeKey(key, secret) {
  if ((key && !secret) || (!key && secret)) return toast("Il faut la clé et le secret");
  try {
    const r = await ppost("key", {key, secret});
    sources = r.sources;
    toast(key ? "Clé enregistrée" : "Podcast Index désactivé");
    showScreen("Réglages", pageSettings, {root: true});
  } catch (e) { toast(e.message); }
}
