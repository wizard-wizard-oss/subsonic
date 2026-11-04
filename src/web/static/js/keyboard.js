"use strict";
// Clavier tactile de l'écran du Pi, commun aux pages Musique et Podcasts.
// Construit sur simple-keyboard (web/static/vendor, licence MIT) ; ici seulement la disposition et le branchement.
// Touches transmises à onKey : un caractère, ou KEY.ERASE / KEY.PASTE / KEY.ENTER.

const KEY = {ERASE: "⌫", PASTE: "⎘", ENTER: "⏎"};

const BOTTOM_ROW = "{paste} {space} . {enter}";
const KEY_LAYOUTS = {
  default: ["a z e r t y u i o p", "q s d f g h j k l m", "{shift} w x c v b n ' {bksp}", "{num} " + BOTTOM_ROW],
  shift: ["A Z E R T Y U I O P", "Q S D F G H J K L M", "{shift} W X C V B N ' {bksp}", "{num} " + BOTTOM_ROW],
  num: ["1 2 3 4 5 6 7 8 9 0", "é è ê à ç ù ô î - _", "{sym} , @ & / : ? ! {bksp}", "{abc} " + BOTTOM_ROW],
  sym: ["( ) [ ] < > | \\ = +", "$ % * ~ ^ ; \" # € £", "{num} ° § ` ¨ {bksp}", "{abc} " + BOTTOM_ROW]
};
const KEY_LABELS = {
  "{bksp}": "⌫", "{shift}": "⇧", "{num}": "123 é", "{abc}": "abc", "{sym}": "#+=",
  "{paste}": "Coller", "{space}": "Espace", "{enter}": "OK"
};
const KEY_THEMES = [
  {class: "del", buttons: "{bksp}"}, {class: "ok", buttons: "{enter}"}, {class: "space", buttons: "{space}"},
  {class: "paste", buttons: "{paste}"}, {class: "switch", buttons: "{shift} {num} {abc} {sym}"}
];
const PAGE_KEYS = {"{num}": "num", "{abc}": "default", "{sym}": "sym"};
const SPECIAL_KEYS = {"{bksp}": KEY.ERASE, "{space}": " ", "{enter}": KEY.ENTER, "{paste}": KEY.PASTE};

class TouchKeyboard {
  constructor(el, onKey) {
    this.onKey = onKey;
    el.classList.add("touch-keyboard");  // simple-keyboard exige une classe sur l'élément qui l'accueille
    this.board = new (SimpleKeyboard.default || SimpleKeyboard.SimpleKeyboard)(el, {
      layout: KEY_LAYOUTS, layoutName: "default", display: KEY_LABELS, buttonTheme: KEY_THEMES,
      theme: "hg-theme-default tkb",
      useButtonTag: true,               // de vrais boutons : accessibles et faciles à tester
      preventMouseDownDefault: true,    // le champ garde la main pendant la frappe
      onKeyPress: button => this.press(button)
      // appui long : simple-keyboard répète tout seul la touche (effacer en continu, par exemple)
    });
  }

  press(button) {
    if (button === "{shift}") return this.setPage(this.page === "shift" ? "default" : "shift");
    if (PAGE_KEYS[button]) return this.setPage(PAGE_KEYS[button]);
    this.onKey(SPECIAL_KEYS[button] || button);
    if (this.page === "shift" && !SPECIAL_KEYS[button]) this.setPage("default");     // majuscule pour une seule lettre
  }

  get page() { return this.board.options.layoutName; }

  setPage(name) {
    this.board.setOptions({layoutName: name});
    if (name === "shift") this.board.addButtonTheme("{shift}", "on");
    else this.board.removeButtonTheme("{shift}", "on");
  }
}

/* Texte du presse-papiers (une longue clé API, par exemple) */
async function clipboardText(onRefused) {
  try { return (await navigator.clipboard.readText()).trim(); }
  catch (e) { onRefused("Collage refusé : autorisez le presse-papiers dans le navigateur"); return ""; }
}

/* Applique une touche à un texte (sauf « coller », asynchrone, et « OK », propre à chaque champ) */
function applyKey(text, k) {
  return k === KEY.ERASE ? text.slice(0, -1) : text + k;
}
