"use strict";
// Podcasts : champs de saisie branchés sur le clavier tactile commun (keyboard.js)

/* Un seul clavier, branché sur le champ « actif ». La touche OK valide le champ. */
let activeField = null;
const keyboard = new TouchKeyboard($("#kb"), k => { if (activeField) activeField.press(k); });
function showKeyboard(open) { $("#kbwrap").hidden = !open; $("#app").classList.toggle("kbopen", open); }
$("#kbclose").onclick = () => showKeyboard(false);

class TextField {
  /* secret : texte masqué ; onEnter(texte) à la touche OK ; onChange(texte) à chaque frappe */
  constructor(el, {secret = false, onEnter = null, onChange = null} = {}) {
    this.el = el; this.secret = secret; this.onEnter = onEnter; this.onChange = onChange; this.text = "";
    el.classList.add("pfield");
    el.onclick = () => this.focus();
    this.paint();
  }
  focus() {
    activeField = this;
    document.querySelectorAll(".pfield").forEach(f => f.classList.toggle("on", f === this.el));
    showKeyboard(true); this.paint();
  }
  async press(k) {
    if (k === KEY.PASTE) return this.insert(await clipboardText(toast));
    if (k === KEY.ENTER) { if (this.onEnter) this.onEnter(this.text); return; }
    this.text = applyKey(this.text, k);
    this.paint();
    if (this.onChange) this.onChange(this.text);
  }
  insert(text) {
    if (!text) return;
    this.text += text;
    this.paint();
    if (this.onChange) this.onChange(this.text);
  }
  paint() {
    const shown = this.secret ? "•".repeat(this.text.length) : this.text;
    this.el.textContent = shown + (activeField === this ? "▌" : "");
    this.el.dataset.empty = this.text ? "" : "1";
  }
}

document.addEventListener("paste", e => {                    // Ctrl+V avec un clavier physique
  if (activeField) activeField.insert((e.clipboardData.getData("text") || "").trim());
});
