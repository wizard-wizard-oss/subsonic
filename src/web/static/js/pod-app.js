"use strict";
// Podcasts : démarrage et onglets

const TABS = {
  home: ["Podcasts", pageHome], themes: ["Thèmes", pageThemes], search: ["Recherche", pageSearch],
  mine: ["Ma liste", pageMine], settings: ["Réglages", pageSettings]
};

function selectTab(name) {
  document.querySelectorAll("nav button[data-t]").forEach(b => b.classList.toggle("on", b.dataset.t === name));
  const [title, build] = TABS[name];
  showScreen(title, build, {root: true});
}

async function boot() {
  $("#back").innerHTML = ic("left", 22);
  $("#back").onclick = goBack;
  $("#quit").onclick = () => { player.saveNow(); fetch("/control/quit").catch(() => {}); };
  document.querySelectorAll("nav button[data-t]").forEach(b => { b.onclick = () => selectTab(b.dataset.t); });
  try {
    const status = await pget("status");
    sources = status.sources; themeList = status.themes; french = status.french !== false;
  } catch (e) { toast("Serveur indisponible : " + e.message); }
  selectTab("home");
}
boot();
