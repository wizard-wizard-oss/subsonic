// Parcours complet de la page Podcasts dans jsdom. Usage : node tests/e2e_podcasts.js PORT [chemin vers jsdom]
const port = process.argv[2];
const {JSDOM, ResourceLoader} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + port;
const wait = ms => new Promise(r => setTimeout(r, ms));
let failures = 0;
const check = (name, ok) => { console.log((ok ? "OK   " : "FAIL ") + name); if (!ok) failures++; };

(async () => {
  const dom = await JSDOM.fromURL(base + "/podcasts", {
    runScripts: "dangerously", resources: "usable", pretendToBeVisual: true,
    beforeParse(w) {
      w.fetch = (u, o) => fetch(new URL(u, base), o);
      w.HTMLMediaElement.prototype.play = function () { this.paused_ = false; return Promise.resolve(); };
      w.HTMLMediaElement.prototype.pause = function () { this.paused_ = true; };
      w.errors = []; w.addEventListener("error", e => w.errors.push(e.message));
    }
  });
  const w = dom.window, d = w.document, $ = s => d.querySelector(s), $$ = s => [...d.querySelectorAll(s)];
  const click = e => e.dispatchEvent(new w.MouseEvent("click", {bubbles: true}));
  await wait(3500);

  check("pas d'erreur JavaScript au chargement", w.errors.length === 0);
  check("accueil : une rangée par recherche", $$(".psection").length >= 1 && $$(".pcard").length >= 2);
  check("onglets présents", $$("nav button[data-t]").length === 5);

  click($("nav button[data-t=themes]")); await wait(300);
  check("thèmes : tuiles affichées", $$(".ptile").length === 14);

  click($$(".ptile").find(t => t.textContent.includes("Histoire"))); await wait(1200);
  check("thème : titre et cartes", $("#title").textContent === "Histoire" && $$(".pcard").length === 2);
  check("thème : astuce clé affichée (pas de clé)", !!$(".phint"));

  click($$(".pcard")[0]); await wait(1500);
  check("fiche : épisodes listés", $$(".pep").length === 2);
  check("fiche : titre du podcast", $(".pinfo b").textContent === "Histoire de tout");
  check("fiche : rangée « même genre »", $$(".ph").some(h => h.textContent.includes("même genre")));

  const sub = $(".pactions button.primary");
  check("fiche : bouton S'abonner", sub.textContent.includes("abonner"));
  click(sub); await wait(500);
  check("fiche : devient Abonné", sub.textContent.includes("Abonné"));

  click($$(".pep")[0]); await wait(500);
  check("lecteur : barre visible", !$("#bar").hidden);
  check("lecteur : titre de l'épisode", $("#btitle").textContent === "Épisode 2");
  check("lecteur : source audio chargée", w.eval("player.audio.src") === "http://93.184.216.34/e2.mp3");

  click($("#bnp")); await wait(200);
  check("plein écran ouvert", !$("#np").hidden);
  click($("#npspeed")); check("vitesse 1,25×", $("#npspeed").textContent === "1.25×");
  click($("#npsleep")); check("minuteur 15 min", $("#npsleep").textContent.includes("15"));
  click($("#npsleep")); click($("#npsleep")); click($("#npsleep")); click($("#npsleep"));
  check("minuteur revient à zéro", $("#npsleep").textContent === "Minuteur");
  click($("#npclose")); check("plein écran fermé", $("#np").hidden);

  click($("#back")); await wait(300);
  click($("nav button[data-t=mine]")); await wait(1500);
  check("ma liste : abonnement présent", $$(".pcard").length === 1);

  // --- « Reprendre l'écoute » : un épisode peut être retiré de la liste ---
  await fetch(base + "/podcast-api/progress", {method: "POST", headers: {"Content-Type": "application/json", "X-Requested-With": "pm"},
    body: JSON.stringify({id: "ep-test", feed: "http://93.184.216.34/f.xml", title: "Épisode à retirer", podcast: "Test",
                          audio: "http://93.184.216.34/a.mp3", pos: 300, dur: 2000})});
  click($("nav button[data-t=home]")); await wait(1500);
  check("reprendre : l'épisode commencé est proposé", $$(".pcard.resume").some(c => c.textContent.includes("Épisode à retirer")));
  click($$(".pcard.resume").find(c => c.textContent.includes("Épisode à retirer")).querySelector(".forget")); await wait(400);
  check("reprendre : la croix retire l'épisode", !$$(".pcard.resume").some(c => c.textContent.includes("Épisode à retirer")));
  check("reprendre : la lecture n'a pas été lancée par la croix", !d.body.textContent.includes("Épisode à retirer"));

  click($("nav button[data-t=search]")); await wait(300);
  check("recherche : champ et clavier", !!$(".pfield") && !$("#kbwrap").hidden);
  for (const ch of "hist") click($$("#kb button").find(b => b.textContent === ch));
  await wait(1800);
  check("recherche : résultats automatiques", $$(".pcard").length === 2);
  click($$(".pcard")[0]); await wait(900);
  click($("#back")); await wait(300);
  check("retour : la recherche est retrouvée", $$(".pcard").length === 2);
  w.eval('searchState = {text: "", items: null}');
  click($("nav button[data-t=search]")); await wait(600);
  check("historique : la recherche utilisée est proposée", $$(".histtext").some(b => b.textContent === "hist"));
  click($$(".histtext").find(b => b.textContent === "hist")); await wait(900);
  check("historique : un toucher relance la recherche", $$(".pcard").length === 2 && $(".pfield").textContent.startsWith("hist"));

  click($("nav button[data-t=settings]")); await wait(300);
  check("réglages : deux sources", $$(".psource").length === 2 && $$(".psource.on").length === 1);
  check("réglages : champs clé et secret", $$(".pfield").length === 2);
  click($$(".pfield")[0]);
  click($$("#kb button").find(b => b.textContent === "⇧"));
  click($$("#kb button").find(b => b.textContent === "A"));
  click($$("#kb button").find(b => b.textContent === "b"));
  check("saisie : majuscule puis minuscule", $$(".pfield")[0].textContent.startsWith("Ab"));
  const del = $("#kb button.del");
  click(del);
  check("effacer : un appui court efface un seul caractère", $$(".pfield")[0].textContent.replace("▌", "") === "A");
  click($$("#kb button").find(b => b.textContent === "b"));
  ["c", "d", "e", "f"].forEach(ch => click($$("#kb button").find(b => b.textContent === ch)));
  const holdDel = $("#kb button.del");     // simple-keyboard redessine les touches : on reprend l'élément
  holdDel.dispatchEvent(new w.MouseEvent("mousedown", {bubbles: true})); await wait(1400);
  d.dispatchEvent(new w.MouseEvent("mouseup", {bubbles: true})); w.dispatchEvent(new w.MouseEvent("mouseup"));
  const afterHold = $$(".pfield")[0].textContent.replace("▌", "");
  check("effacer : un appui long efface en continu", afterHold === "");
  click($$("#kb button").find(b => b.textContent === "⇧"));
  click($$("#kb button").find(b => b.textContent === "A"));
  click($$("#kb button").find(b => b.textContent === "b"));
  check("saisie reprise après effacement", $$(".pfield")[0].textContent.replace("▌", "") === "Ab");
  click($$(".pfield")[1]);
  click($$("#kb button").find(b => b.textContent === "x"));
  check("secret masqué", $$(".pfield")[1].textContent.startsWith("•") && !$$(".pfield")[1].textContent.includes("x"));
  Object.defineProperty(w.navigator, "clipboard", {value: {readText: () => Promise.resolve("  CLE-LONGUE-123  ")}, configurable: true});
  click($$(".pfield")[0]);
  click($$("#kb button").find(b => b.textContent === "Coller")); await wait(50);
  check("coller : la clé du presse-papiers est ajoutée", $$(".pfield")[0].textContent.includes("AbCLE-LONGUE-123"));
  check("clavier : 4 rangées, sans chiffres sur la page lettres", $$("#kb .hg-row").length === 4 && !$$("#kb button").some(b => b.textContent === "1"));
  click($$("#kb button").find(b => b.textContent === "123 é"));
  check("clavier : page chiffres et accents", ["1", "0", "é", "@"].every(c => $$("#kb button").some(b => b.textContent === c)));
  click($$("#kb button").find(b => b.textContent === "#+="));
  check("clavier : page symboles", ["$", "^", "€"].every(c => $$("#kb button").some(b => b.textContent === c)));
  click($$("#kb button").find(b => b.textContent === "abc"));
  check("clavier : retour aux lettres", $$("#kb button").some(b => b.textContent === "a"));

  check("toujours aucune erreur JavaScript", w.errors.length === 0);
  console.log(failures ? "ÉCHECS : " + failures : "TOUT PASSE");
  process.exit(failures ? 1 : 0);
})().catch(e => { console.error(e); process.exit(2); });
