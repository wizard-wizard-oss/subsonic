"use strict";
// Navigation par onglets

/* ---------- Navigation ---------- */
const stack = [];
const tabs = {};
async function render() {
  const v = stack[stack.length - 1];
  $("#title").textContent = v.title;
  $("#top").hidden = stack.length <= 1;
  setKb(false);
  main.onscroll = null; main.innerHTML = ""; main.scrollTop = 0;
  main.classList.remove("in"); void main.offsetWidth; main.classList.add("in");
  try { await v.build(main); }
  catch (e) {
    main.innerHTML = '<div class="msg">' + esc(e.message) + '</div><div class="actions"><button id="retry">Réessayer</button></div>';
    const r = $("#retry"); if (r) r.onclick = () => render();
  }
}
function openView(title, build) { stack.push({title, build}); render(); }
$("#back").innerHTML = ic("left");
$("#back").onclick = () => { if (stack.length > 1) { stack.pop(); render(); } };
function tab(name) {
  stack.length = 0;
  document.querySelectorAll("nav button[data-t]").forEach(b => b.classList.toggle("on", b.dataset.t === name));
  tabs[name]();
}
document.querySelectorAll("nav button[data-t]").forEach(b => { b.onclick = () => tab(b.dataset.t); });
const closeFull = () => { $("#full").hidden = true; };
