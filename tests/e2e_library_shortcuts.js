// Les collections de Bibliothèque suivent la source des raccourcis sans changer le reste de la page.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const {JSDOM}=require(process.argv[2]||"jsdom");
const dom=new JSDOM('<main><h1>Bibliothèque</h1></main>',{url:"https://music.example/",runScripts:"outside-only"});
const d=dom.window.document,run=code=>vm.runInContext(code,dom.getInternalVMContext());
const load=file=>run(fs.readFileSync(path.join(__dirname,"../src/web-pc/static/js/"+file+".js"),"utf8"));
(async()=>{try{
  load("core");
  run('App.user={id:1};App.music={sidebar:{owner:1,shortcutItems:[],loadError:null,load(){}}};window.route={};');
  load("library-shortcuts");
  run('window.collections=new LibraryShortcuts(route);document.querySelector("main").append(collections.root)');
  assert.equal(d.querySelector(".library-shortcuts").hidden,true);
  const heading=d.querySelector("h1");
  run('App.music.sidebar.shortcutItems=[{id:"fdir-comp",name:"Compilations"}];App.bus.emit("artist-index",{});');
  assert.equal(d.querySelector(".library-shortcuts a").textContent,"Compilations");
  assert.equal(d.querySelector(".library-shortcuts a").getAttribute("href"),"#/artist/fdir-comp");
  assert.equal(d.querySelector("h1"),heading);
  run('collections.destroy();App.music.sidebar.shortcutItems=[];App.bus.emit("artist-index",{});');
  assert.ok(d.querySelector(".library-shortcuts a"));
  run('App.music.sidebar.shortcutItems=[{id:"fdir-comp",name:"Compilations"}];App.api.get=async()=>({albums:[],hasMore:false});');
  load("views");
  await run('Views.albums.render(document.querySelector("main"),{kind:"newest"})');
  assert.equal(d.querySelector('.tabs').firstElementChild.nextElementSibling.className,"library-shortcuts");
  assert.equal(d.querySelector('.library-shortcuts a').textContent,"Compilations");
  dom.window.close();console.log("OK Bibliothèque : Compilations disponible, mise à jour locale et nettoyage");
}catch(error){console.error(error);dom.window.close();process.exitCode=1;}})();
