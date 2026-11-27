"use strict";
/* Menu du compte : même composant sur ordinateur et téléphone. */
const AccountMenu = (() => {
  let started = false;
  const menu = () => document.getElementById("account-menu");
  function close(restoreFocus = false) {
    const node = menu();
    if (!node || !node.open) return;
    node.open = false;
    if (restoreFocus) document.getElementById("account-toggle").focus();
  }
  function start() {
    if (started) return;
    started = true;
    const node = menu();
    node.addEventListener("toggle", () => {
      if (node.open) App.bus.emit("account-menu-opened");
    });
    node.querySelector(".account-menu-panel").addEventListener("click", event => {
      if (event.target.closest("a, button")) close();
    });
    document.addEventListener("click", event => { if (!node.contains(event.target)) close(); });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && node.open) {
        event.preventDefault(); event.stopImmediatePropagation(); close(true);
      }
    });
    App.bus.on("route", () => close());
  }
  return {start, close};
})();
