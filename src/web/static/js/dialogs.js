"use strict";
// Feuille d'actions et saisie de texte

/* ---------- Feuille d'actions et saisie de texte ---------- */
function openSheet(title, items) {
  $("#sheettitle").textContent = title;
  const l = $("#sheetlist"); l.innerHTML = "";
  items.forEach(it => {
    const b = document.createElement("button"); b.className = "si";
    b.innerHTML = (it.icon ? ic(it.icon, 22) : "") + "<span>" + esc(it.label) + "</span>";
    b.onclick = () => { closeSheet(); it.fn(); };
    l.appendChild(b);
  });
  $("#sheet").hidden = false;
}
const closeSheet = () => { $("#sheet").hidden = true; };
$("#sheetbg").onclick = closeSheet;

let askResolve = null, askVal = "";
const showAsk = () => { $("#askin").textContent = askVal + "▌"; };
new TouchKeyboard($("#askkb"), async k => {
  if (k === KEY.ENTER) return askDone(askVal.trim() || null);
  askVal = k === KEY.PASTE ? askVal + await clipboardText(toast) : applyKey(askVal, k);
  showAsk();
});
document.addEventListener("paste", e => {                    // Ctrl+V avec un clavier physique
  if ($("#ask").hidden) return;
  askVal += (e.clipboardData.getData("text") || "").trim(); showAsk();
});
function askText(title, initial) {
  return new Promise(res => {
    askResolve = res; askVal = initial || "";
    $("#asktitle").textContent = title; $("#askin").textContent = askVal + "▌";
    $("#ask").hidden = false;
  });
}
const askDone = v => { $("#ask").hidden = true; if (askResolve) { const r = askResolve; askResolve = null; r(v); } };
$("#askok").onclick = () => askDone(askVal.trim() || null);
$("#askcancel").onclick = () => askDone(null);
