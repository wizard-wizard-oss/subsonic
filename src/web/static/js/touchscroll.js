"use strict";
// Défilement au doigt

/* ---------- Défilement au doigt (secours si le navigateur émule la souris) ---------- */
let drag = null, suppress = false;
document.addEventListener("pointerdown", e => {
  if (e.pointerType === "touch") return;
  const h = e.target.closest(".shelf, .chips");
  const el = h || e.target.closest("#fqueue, #sheetlist") || (e.target.closest("#main") ? main : null);
  if (!el) return;
  drag = {el, horiz: !!h, x: e.clientX, y: e.clientY, sl: el.scrollLeft, st: el.scrollTop, moved: false};
});
window.addEventListener("pointermove", e => {
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  if (Math.abs(dx) > 6 || Math.abs(dy) > 6) drag.moved = true;
  if (!drag.moved) return;
  if (drag.horiz) drag.el.scrollLeft = drag.sl - dx; else drag.el.scrollTop = drag.st - dy;
});
window.addEventListener("pointerup", () => {
  if (drag && drag.moved) { suppress = true; setTimeout(() => { suppress = false; }, 60); }
  drag = null;
});
document.addEventListener("click", e => { if (suppress) { e.stopPropagation(); e.preventDefault(); } }, true);
