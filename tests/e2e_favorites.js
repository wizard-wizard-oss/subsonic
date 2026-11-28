// Favoris : artistes, suite des albums et conservation des nœuds lors du chargement suivant.
const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const {JSDOM} = require(process.argv[2] || "jsdom");
const dom = new JSDOM('<main></main>', {url: "https://music.example/", runScripts: "outside-only"});
const d = dom.window.document, run = code => vm.runInContext(code, dom.getInternalVMContext());
const load = file => run(fs.readFileSync(path.join(__dirname, "../src/web-pc/static/js/" + file + ".js"), "utf8"));
(async () => { try {
  load("core"); load("icons");
  run(`App.user={id:1,roles:[]};App.preferences={};App.texts["favorites.count"]="{shown} sur {total}";
    const ExtMusic={favoritesSection:()=>App.el("section.ext-favorites")};
    window.asked=[];window.route={};window.observers=[];window.photos=[];
    window.IntersectionObserver=class{
      constructor(callback){this.callback=callback;this.nodes=[];observers.push(this);}
      observe(node){this.nodes.push(node);}unobserve(){}disconnect(){this.disconnected=true;}
    };
    App.api.get=async(url,params)=>{
      if(url==="/api/artist/image")return new Promise(resolve=>photos.push({id:params.id,resolve}));
      asked.push(params?.page || 0);return params?.page ?
      {artists:[{id:"f126",name:"Suite"}],albums:Array.from({length:40},(_,i)=>({id:"album"+(params.page*40+i),name:"Album suivant"})),
        songs:Array.from({length:40},(_,i)=>({id:"song"+(i+40),title:"Titre suivant"})),hasMore:true,
        pagination:{artists:{total:4,hasMore:false},albums:{total:225,hasMore:true},songs:{total:794,hasMore:true}}} :
      {artists:[{id:"f123",name:"<ABBA>"},{id:"f124",name:"Sans photo"},{id:"f125",name:"Image absente"}],
        albums:Array.from({length:40},(_,i)=>({id:"album"+i,name:"Album "+i})),songs:Array.from({length:40},(_,i)=>({id:"song"+i,title:"Titre"})),hasMore:true,
        pagination:{artists:{total:4,hasMore:true},albums:{total:225,hasMore:true},songs:{total:794,hasMore:true}}};};`);
  load("views");
  run('Views.songTable=songs=>App.el("div.test-song-table",{},songs.map(song=>App.el("span.test-song",{text:song.title})));');
  if (fs.existsSync(path.join(__dirname, "../src/web-pc/static/js/favorites.js"))) load("favorites");
  await run('Views.favorites.render(document.querySelector("main"),route)');
  const artist = d.querySelector('a[href="#/artist/f123"]');
  assert.ok(artist, "les artistes favoris sont affichés");
  const albumSection=d.querySelector('.favorites-section[data-kind="albums"]');
  assert.equal(albumSection.querySelector('.favorites-count').textContent,'40 sur 225');
  assert.ok(albumSection.querySelector('.favorites-more'),"la suite des albums est directement sous les albums");
  assert.equal(d.querySelector('.favorites-section[data-kind="songs"] .favorites-count').textContent,'40 sur 794');
  assert.equal(artist.querySelector('.favorite-artist-name').textContent, "<ABBA>");
  assert.equal(artist.querySelector('abba'),null,"les noms ne deviennent pas du HTML");
  assert.ok(artist.querySelector('.favorite-artist-portrait'));
  assert.equal(run('photos.length'),0,"pas de requête portrait avant visibilité");
  run('observers[0].callback(observers[0].nodes.map(target=>({target,isIntersecting:true})))');
  assert.equal(run('photos.length'),1,"une seule recherche de portrait en vol");
  run('photos[0].resolve({imageUrl:"https://images.example/abba.jpg",source:"subsonic"})');
  await new Promise(resolve=>setImmediate(resolve));
  const image=artist.querySelector('img');
  assert.equal(image.getAttribute('src'),"https://images.example/abba.jpg");
  assert.equal(image.getAttribute('loading'),"lazy");
  assert.equal(run('photos.length'),2);
  run('photos[1].resolve({imageUrl:""})');await new Promise(resolve=>setImmediate(resolve));
  const fallback=d.querySelector('a[href="#/artist/f124"]');
  assert.equal(fallback.querySelector('img'),null);
  assert.equal(fallback.querySelector('.favorite-artist-initials').textContent,'SP');
  run('photos[2].resolve({imageUrl:"https://images.example/broken.jpg"})');await new Promise(resolve=>setImmediate(resolve));
  const broken=d.querySelector('a[href="#/artist/f125"]');
  broken.querySelector('img').dispatchEvent(new dom.window.Event('error'));
  assert.equal(broken.querySelector('img'),null);
  assert.equal(broken.querySelector('.favorite-artist-initials').hidden,false);
  const first = d.querySelector('.album-card'), elsewhere = d.querySelector('.ext-favorites');
  const songs=d.querySelector('.test-song-table');
  albumSection.querySelector('.favorites-more').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(d.querySelectorAll('.album-card').length, 80);
  assert.equal(d.querySelector('.album-card'), first);
  assert.equal(d.querySelector('.ext-favorites'), elsewhere);
  assert.equal(d.querySelector('a[href="#/artist/f123"]'),artist,"la pagination conserve les portraits existants");
  assert.equal(d.querySelector('.test-song-table'),songs);
  assert.equal(d.querySelectorAll('.test-song').length,40,"charger les albums ne charge pas les titres");
  assert.equal(d.querySelectorAll('.favorite-artist').length,3,"charger les albums ne charge pas les artistes");
  assert.equal(albumSection.querySelector('.favorites-count').textContent,'80 sur 225');
  assert.equal(albumSection.querySelector('.favorites-more').hidden,false);
  d.querySelector('.favorites-section[data-kind="artists"] .favorites-more').click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(d.querySelectorAll('.favorite-artist').length,4);
  assert.equal(d.querySelectorAll('.album-card').length,80);
  d.querySelector('.favorites-section[data-kind="songs"] .favorites-more').click();
  await new Promise(resolve=>setImmediate(resolve));
  assert.equal(d.querySelectorAll('.test-song').length,80);
  assert.equal(d.querySelector('.favorites-section[data-kind="songs"] .favorites-count').textContent,'80 sur 794');
  assert.equal(d.querySelectorAll('.album-card').length,80);
  assert.equal(run('asked.join(",")'), "0,1,1,1","chaque section garde sa pagination propre");
  run('observers[0].callback([{target:observers[0].nodes.at(-1),isIntersecting:true}]);Views.favorites.destroy();App.user={id:2,roles:[]}');
  run('photos[3].resolve({imageUrl:"https://images.example/late.jpg"})');await new Promise(resolve=>setImmediate(resolve));
  assert.equal(d.querySelector('a[href="#/artist/f126"] img'),null,"réponse portrait ignorée après changement de compte");
  assert.equal(run('observers[0].disconnected'),true);
  run('window.nextRoute={};App.api.get=()=>new Promise(resolve=>window.lateFavorites=resolve);');
  const rendering=run('Views.favorites.render(document.querySelector("main"),nextRoute)');
  run('App.user={id:3,roles:[]};lateFavorites({artists:[{id:"old",name:"Ancien compte"}],albums:[],songs:[],hasMore:false})');
  await rendering;
  assert.equal(d.querySelector('a[href="#/artist/old"]'),null,"favoris tardifs d’un ancien compte ignorés");
  run('Views.favorites.destroy()');
  dom.window.close(); console.log("OK favoris : artistes, pagination et mise à jour locale");
} catch(error) {console.error(error);dom.window.close();process.exitCode=1;} })();
