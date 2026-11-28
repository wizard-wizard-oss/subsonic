// La commande de lecture reste près du numéro, même lorsque la colonne des numéros est masquée.
const assert=require("node:assert/strict"),fs=require("node:fs"),path=require("node:path"),vm=require("node:vm");
const {JSDOM}=require(process.argv[2]||"jsdom");
const dom=new JSDOM('<main></main>',{url:"https://music.example/",runScripts:"outside-only"});
const d=dom.window.document,run=code=>vm.runInContext(code,dom.getInternalVMContext());
const load=file=>run(fs.readFileSync(path.join(__dirname,"../src/web-pc/static/js/"+file+".js"),"utf8"));
try{
  for(const file of ["core","icons","song-columns"])load(file);
  run('App.user={id:1,roles:["stream"]};App.preferences={browse_track:true};App.songColumns=["track","duration"];App.player={current:null,playList(songs,i){this.current=songs[i];}};const ListenLaterUI={recommendButton:()=>App.el("button")};');
  load("views");
  const style=d.createElement("style");style.textContent=fs.readFileSync(path.join(__dirname,"../src/web-pc/static/css/views.css"),"utf8");d.head.append(style);
  run('window.table=Views.songTable([{id:"s1",title:"Premier",track:1},{id:"s2",title:"Deuxième",track:2}]);document.querySelector("main").append(table);');
  assert.equal(d.querySelector('td.title .row-play'),null);
  const second=d.querySelectorAll('tr.song')[1];
  assert.equal(second.querySelector('.row-play').parentElement.nextElementSibling.dataset.songColumn,"track");
  assert.equal(dom.window.getComputedStyle(second.querySelector('.row-play')).opacity,"1");
  second.querySelector('.row-play').click();
  assert.equal(run('App.player.current.id'),"s2");
  run('App.preferences.browse_track=false;App.bus.emit("preferences",App.preferences)');
  assert.equal(second.querySelector('[data-song-column="track"]').hidden,true);
  assert.equal(second.querySelector('.row-play').parentElement.hidden,false);
  run('table.destroy()');dom.window.close();console.log("OK pistes : lecture près du numéro et disponible lorsque le numéro est masqué");
}catch(error){console.error(error);dom.window.close();process.exitCode=1;}
