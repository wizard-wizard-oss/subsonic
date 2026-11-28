// Les mêmes playlists restent des cibles : agrandissement, annulation, défilement et retour mobile.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {JSDOM} = require(process.argv[2] || "jsdom");
const directory = path.join(__dirname, "../src/web-pc");
const dom = new JSDOM(fs.readFileSync(path.join(directory, "index.html"), "utf8"), {url: "https://music.example/", runScripts: "outside-only"});
const w = dom.window, d = w.document;
const run = code => vm.runInContext(code, dom.getInternalVMContext());
const load = name => run(fs.readFileSync(path.join(directory, "static/js/" + name + ".js"), "utf8"));
const frames = new Map(); let frameId = 0, added = 0;
w.requestAnimationFrame = callback => { frames.set(++frameId, callback); return frameId; };
w.cancelAnimationFrame = id => frames.delete(id);
const advance = time => { const batch = [...frames.values()]; frames.clear(); batch.forEach(callback => callback(time)); };
function drag(node, type, y = 200) {
  const event = new w.MouseEvent(type, {bubbles: true, cancelable: true, clientY: y});
  Object.defineProperty(event, "dataTransfer", {value: {setData(){}, effectAllowed: "", dropEffect: ""}});
  node.dispatchEvent(event);
  return event;
}
try {
  load("core"); load("icons"); load("dnd");
  run('App.user={id:1,roles:["stream","playlist"]}; App.preferences={}; App.live={on(){return ()=>{};}}; App.music={route:{}};');
  load("desktop-playlists"); load("desktop-navigation");
  run('window.desktop=new DesktopNavigation();');
  const panel = d.getElementById("panel-playlists"), list = d.getElementById("playlist-list");
  const filter = d.getElementById("playlist-filter"), nav = d.querySelector("#sidebar .topnav");
  const toggle = d.querySelector(".playlist-expand");
  assert.ok(toggle, "une petite icône agrandit les playlists");
  assert.ok(nav.querySelectorAll(".icon").length >= 7, "les icônes du menu sont conservées");
  filter.value = "Rock"; list.scrollTop = 81;
  toggle.click();
  assert.equal(toggle.getAttribute("aria-expanded"), "true");
  assert.equal(d.body.dataset.playlistFocus, "true");
  assert.equal(d.getElementById("panel-playlists"), panel);
  assert.equal(d.querySelector("#sidebar .topnav"), nav);
  assert.equal(filter.value, "Rock");
  toggle.click();
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  assert.equal(list.scrollTop, 81);

  const source = d.createElement("div"), target = d.createElement("a");
  source.id = "source"; target.className = "playlist-row"; list.append(target); d.getElementById("main").append(source);
  w.add = () => { added++; };
  run('Dnd.source(document.getElementById("source"),{songIds:["s1"]}); Dnd.target(document.querySelector(".playlist-row"),()=>true,window.add);');
  run('desktop.opened=false;desktop.applyMenu();');
  drag(source, "dragstart");
  assert.equal(d.body.dataset.playlistFocus, "true");
  assert.equal(d.body.dataset.desktopMenu, "open", "un dépôt reste possible si le menu était fermé");
  drag(target, "dragover"); drag(target, "drop");
  assert.equal(added, 1);
  assert.equal(d.body.dataset.desktopMenu, "closed", "le dépôt restaure le choix du menu");
  assert.equal(toggle.getAttribute("aria-expanded"), "false");
  assert.equal(filter.value, "Rock");

  Object.defineProperties(list, {clientHeight: {value: 300}, scrollHeight: {value: 1000}});
  list.getBoundingClientRect = () => ({top: 80, bottom: 380});
  drag(source, "dragstart");
  drag(list, "dragover", 375); advance(16); advance(32);
  assert.ok(list.scrollTop > 81, "approcher du bord fait défiler les playlists");
  drag(source, "dragend");
  assert.equal(frames.size, 0, "annuler arrête le défilement");
  assert.equal(list.scrollTop, 81, "l'agrandissement temporaire restaure la position");
  assert.equal(target.classList.contains("drop-over"), false);

  toggle.click();
  drag(source, "dragstart"); drag(source, "dragend");
  assert.equal(toggle.getAttribute("aria-expanded"), "true", "un agrandissement manuel est conservé");
  run('desktop.destroy();');
  assert.equal(d.querySelector(".playlist-expand"), null);
  assert.equal(d.body.hasAttribute("data-playlist-focus"), false);
  assert.equal(d.getElementById("playlist-list"), list);
  assert.equal(d.querySelectorAll("#playlist-new").length, 1);
  console.log("OK playlists : agrandissement, dépôt, annulation, défilement et restauration");
} catch (error) { console.error(error); process.exitCode = 1; }
finally { w.close(); }
