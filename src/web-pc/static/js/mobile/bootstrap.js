"use strict";
/* Assemblage mobile uniquement. Les composants du bureau et leurs préférences restent propriétaires de leur état. */
(() => {
  if (!window.matchMedia) return;
  const screen = window.matchMedia("(max-width: 820px), (max-width: 1100px) and (hover: none) and (pointer: coarse)");
  const app = document.getElementById("app");
  let navigation = null;
  const update = () => {
    if (screen.matches && !app.hidden && !navigation) {
      navigation = new MobileNavigation();
    } else if ((!screen.matches || app.hidden) && navigation) {
      navigation.destroy();
      navigation = null;
    }
  };
  screen.addEventListener("change", update);
  new MutationObserver(update).observe(app, {attributes: true, attributeFilter: ["hidden"]});
  update();
})();
