"use strict";
/* Choisit une disposition ; les adaptateurs rendent les mêmes nœuds lors d’un changement d’écran. */
(() => {
  if (!window.matchMedia) return;
  const screen = window.matchMedia("(max-width: 1100px) and (hover: none) and (pointer: coarse)");
  const app = document.getElementById("app");
  let navigation = null;
  let desktop = null;
  const update = () => {
    const layout = app.hidden ? null : screen.matches ? "mobile" : "desktop";
    if (navigation && layout !== "mobile") { navigation.destroy(); navigation = null; }
    if (desktop && layout !== "desktop") { desktop.destroy(); desktop = null; }
    if (layout === "mobile" && !navigation) navigation = new MobileNavigation();
    if (layout === "desktop" && !desktop && typeof DesktopNavigation !== "undefined") desktop = new DesktopNavigation();
    const active = desktop ? "desktop" : navigation ? "mobile" : null;
    if (App.layout !== active) { App.layout = active; App.bus.emit("layout", active); }
  };
  screen.addEventListener("change", update);
  new MutationObserver(update).observe(app, {attributes: true, attributeFilter: ["hidden"]});
  update();
})();
