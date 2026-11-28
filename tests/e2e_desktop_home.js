// Accueil ordinateur : vrais composants, données personnelles et radar existant simulés.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {JSDOM} = require(process.argv[2] || "jsdom");
const directory = path.join(__dirname, "../src/web-pc");
const dom = new JSDOM('<main></main>', {url:"https://music.example/", runScripts:"outside-only", pretendToBeVisual:true});
const w = dom.window, d = w.document;
const run = source => vm.runInContext(source, dom.getInternalVMContext());
const load = name => run(fs.readFileSync(path.join(directory,"static/js/" + name + ".js"),"utf8"));
const tick = () => new Promise(resolve => setTimeout(resolve,0));
const settle = async () => { for (let i=0;i<8;i++) await tick(); };
const calls = [], writes = [];
const album = (id,name) => ({id,name,artist:"Artist",coverId:"cover",artistId:"artist"});
let releaseRadar;
w.get = async (url,params) => {
  calls.push({url,params});
  if (url === "/api/home") return {newest:[album("new","Newest")],mostPlayed:[],topRated:[],discussed:[]};
  if (url === "/api/home/personal") return {basis:"history",seed:{artist:"Joy Division"},recent:[album("old","Recent")],
    suggestions:[album("similar","Suggested")],nextBefore:null};
  if (url === "/api/news/releases/radar") return new Promise(resolve => {releaseRadar=resolve;});
  if (url === "/api/album") return {id:params.id,coverId:"cover",songs:[{id:"s1",title:"Song"}]};
  throw new Error("Unexpected request " + url);
};
w.post = async (url,body) => {writes.push({url,body});return {};};
try {
  for (const file of ["core","icons","album-rail","home-resume","weekly-releases","weekly-radar"]) load(file);
  run(`
    const Views={listen:{link:(artist,title)=>"#/listen/"+encodeURIComponent(artist)+"/"+encodeURIComponent(title)}};
    App.user={id:1,roles:["stream"]}; App.preferences={}; App.texts={
      "home.resume":"Reprendre l’écoute","home.continue":"Reprendre à {position}","home.personal_recent":"Écoutés récemment",
      "home.because":"Parce que vous avez écouté {artist}","home.recommendations":"Recommandations reçues",
      "weekly.title":"Sorties de la semaine","home.newest":"Derniers albums ajoutés","home.see_all":"Tout voir"};
    App.api.get=window.get;App.api.post=window.post;App.live={on(){return ()=>{};}};
    App.player={current:{id:"s1",title:"Song",artist:"Daft Punk",coverId:"c"},position:42,playing:false,toggle(){this.playing=!this.playing;App.bus.emit("player");}};
    App.music={queueMemory:{ready:Promise.resolve()}};
    App.layout="desktop";
    const ListenLaterUI={load:async()=>({recommendations:window.noAdvice?[]:[{target:{title:"Received"}}]}),
      preview:group=>App.el("article.listen-later-card",{text:group.target.title})};
    Views.albumGrid=albums=>App.el("div.album-grid",{},albums.map(album=>App.el("article.album-card",{},App.el("strong",{text:album.name}))));
  `);
  load("desktop-home");
} catch(error) { console.error(error);w.close();process.exit(1); }
(async () => {
  run('window.route={};DesktopHome.render(document.querySelector("main"),window.route)');
  await settle();
  assert.ok(d.querySelector(".desktop-home"));
  assert.equal(d.querySelector(".home-rail-all"),null);
  assert.equal(d.querySelector('.home-newest h2 a').getAttribute("href"),"#/albums/newest");
  assert.equal(d.querySelector(".library-collection"),null);
  assert.ok(d.querySelector(".home-rail").textContent.includes("Recommandations reçues"));
  assert.ok(d.querySelector("main").textContent.includes("Parce que vous avez écouté Joy Division"));
  assert.ok(d.querySelector("main").textContent.includes("Recent"));
  assert.ok(releaseRadar);
  releaseRadar({monday:"2026-11-23",cards:[{id:"release",title:"Radar album",artist:"Musician",date:"2026-11-27",type:"Album",reasons:[]}],next:48});
  await settle();
  const release = d.querySelector(".home-releases .weekly-card");
  assert.ok(release);
  assert.equal(release.querySelector(".weekly-actions a").getAttribute("href"),"#/listen/Musician/Radar%20album");
  const request = calls.find(c=>c.url==="/api/news/releases/radar");
  assert.equal(request.params.filter,"all");
  assert.equal(request.params.offset,0);
  assert.equal(new Date(request.params.monday+"T00:00:00Z").getUTCDay(),1);
  assert.equal(writes.length,0); // Les aperçus ne marquent pas les conseils comme lus.
  d.querySelector(".personal-resume button").click();
  assert.ok(d.querySelector(".personal-resume button").getAttribute("aria-label").length);

  // Les boutons défilent uniquement leur rangée et chargent la suite à son extrémité.
  run('window.rail=new AlbumRail("Test");document.querySelector("main").append(rail.root);rail.append([App.el("article",{text:"First"})]);');
  const track = w.eval("rail.track");
  Object.defineProperties(track,{clientWidth:{value:500},scrollWidth:{get(){return this.children.length*500;}}});
  track.scrollBy = ({left}) => {track.scrollLeft+=left;track.dispatchEvent(new w.Event("scroll"));};
  run('rail.more(async()=>{rail.append([App.el("article",{text:"Second"})]);rail.more(null);});rail.update();');
  const previous = w.eval("rail.previous"), next = w.eval("rail.next");
  assert.equal(previous.disabled,true);
  next.click();await settle();
  assert.equal(track.children.length,2);
  assert.ok(track.scrollLeft>0);
  assert.equal(previous.disabled,false);
  const heading = d.querySelector(".desktop-home h2");
  const offset = track.scrollLeft;
  assert.equal(heading,d.querySelector(".desktop-home h2"));

  // Une réponse du radar d’un ancien compte est ignorée.
  run('DesktopHome.destroy();window.otherRoute={};DesktopHome.render(document.querySelector("main"),otherRoute)');
  await settle();
  run('App.user={id:2,roles:["stream"]};otherRoute.stale=true;DesktopHome.destroy();');
  releaseRadar({cards:[{id:"private",title:"Private album",artist:"Private",date:"2026-11-27",type:"Album",reasons:[]}],next:null});
  await settle();
  assert.equal(d.querySelector("main").textContent.includes("Private album"),false);
  assert.ok(offset>0);

  // Le défilement natif charge la suite sans clic sur les flèches.
  run('window.swipeRail=new AlbumRail("Swipe");document.querySelector("main").append(swipeRail.root);swipeRail.append([App.el("article"),App.el("article")]);');
  const swipe=w.eval("swipeRail.track");
  Object.defineProperties(swipe,{clientWidth:{value:500},scrollWidth:{get(){return this.children.length*500;}}});
  run('swipeRail.more(async()=>{swipeRail.append([App.el("article")]);swipeRail.more(null);})');
  swipe.scrollLeft=500;swipe.dispatchEvent(new w.Event("scroll"));await settle();
  assert.equal(swipe.children.length,3);

  run('DesktopHome.destroy();window.noAdvice=true;DesktopHome.render(document.querySelector("main"),{});');
  await settle();
  assert.equal(d.querySelector('.home-received').hidden,true);
  run('window.noAdvice=false;');

  // Détruire la page suffit à ignorer ses réponses, même si son nœud est encore attaché.
  run('App.user={id:1,roles:["stream"]};DesktopHome.render(document.querySelector("main"),{});');
  await settle();
  run('DesktopHome.destroy()');
  releaseRadar({cards:[{id:"late",title:"Late album",artist:"Late",date:"2026-11-27",type:"Album",reasons:[]}],next:null});
  await settle();
  assert.equal(d.querySelector("main").textContent.includes("Late album"),false);

  // La restauration de file ne réveille pas un point de reprise déjà détruit.
  run('App.music.queueMemory.ready=new Promise(resolve=>window.restoreQueue=resolve);window.oldResume=new HomeResume({});oldResume.destroy();restoreQueue();');
  await settle();
  assert.equal(w.eval('oldResume.root.hidden'),true);
  w.close();console.log("OK accueil ordinateur : rangées, radar réutilisé, reprise, pagination et isolation des comptes");
})().catch(error=>{console.error(error);w.close();process.exitCode=1;});
