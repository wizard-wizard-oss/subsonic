"use strict";
// Fonctions réservées à l'écran du Raspberry Pi (volume, veille, pause à distance, menu)

const quitBtn = document.getElementById("quit");
quitBtn.hidden = false;
quitBtn.onclick = () => fetch("/control/quit").catch(() => {});
/* ---- Volume du Pi (écran local seulement) ---- */
let volTimer = null;
async function volCmd(d) {
  try {
    const j = await (await fetch("/control/volume" + (d ? "?d=" + d : ""))).json();
    if (j.volume !== undefined) $("#fvv").textContent = j.volume + " %";
    clearTimeout(volTimer); volTimer = setTimeout(() => { $("#fvol").hidden = true; }, 4000);
  } catch (e) {}
}
if (/^(127\.0\.0\.1|localhost)$/.test(location.hostname)) $("#fvbtn").hidden = false;
$("#fvbtn").onclick = () => { const v = $("#fvol"); v.hidden = !v.hidden; if (!v.hidden) volCmd(""); };
$("#fvm").onclick = () => volCmd("-5"); $("#fvp").onclick = () => volCmd("+5");
// Paroles affichées et musique en cours : on demande au menu de ne pas lancer l'écran de veille
setInterval(() => {
  if (!$("#full").hidden && !$("#flyr").hidden && !audio.paused) fetch("/control/awake?on=1").catch(() => {});
}, 15000);

/* Le menu du Pi peut demander une pause (ex. : une radio démarre ailleurs) */
setInterval(async () => {
  try {
    const j = await (await fetch("/control/poll")).json();
    if (j.cmd === "pause" && !audio.paused) audio.pause();
  } catch (e) {}
}, 1500);
