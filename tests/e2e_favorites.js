// Favoris : artistes, suite des albums et conservation des nœuds lors du chargement suivant.
const assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path"), vm = require("node:vm");
const {JSDOM} = require(process.argv[2] || "jsdom");
const dom = new JSDOM('<main></main>', {url: "https://music.example/", runScripts: "outside-only"});
const d = dom.window.document, run = code => vm.runInContext(code, dom.getInternalVMContext());
const load = file => run(fs.readFileSync(path.join(__dirname, "../src/web-pc/static/js/" + file + ".js"), "utf8"));
(async () => { try {
  load("core"); load("icons");
  run(`App.user={id:1,roles:[]};App.preferences={};
    const ExtMusic={favoritesSection:()=>App.el("section.ext-favorites")};
    window.asked=[];window.route={};
    App.api.get=async(url,params)=>{asked.push(params?.page || 0);return params?.page ?
      {artists:[],albums:[{id:"second",name:"Deuxième"}],songs:[],hasMore:false} :
      {artists:[{id:"f123",name:"<ABBA>"}],albums:[{id:"first",name:"Premier"}],songs:[],hasMore:true};};`);
  load("views");
  if (fs.existsSync(path.join(__dirname, "../src/web-pc/static/js/favorites.js"))) load("favorites");
  await run('Views.favorites.render(document.querySelector("main"),route)');
  const artist = d.querySelector('a[href="#/artist/f123"]');
  assert.ok(artist, "les artistes favoris sont affichés");
  assert.equal(artist.textContent, "<ABBA>"); assert.equal(artist.children.length, 0);
  const first = d.querySelector('.album-card'), elsewhere = d.querySelector('.ext-favorites');
  assert.ok(d.querySelector('.favorites-more'), "les favoris suivants sont accessibles");
  d.querySelector('.favorites-more').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(d.querySelectorAll('.album-card').length, 2);
  assert.equal(d.querySelector('.album-card'), first);
  assert.equal(d.querySelector('.ext-favorites'), elsewhere);
  assert.ok(!d.querySelector('.favorites-more'));
  assert.equal(run('asked.join(",")'), "0,1");
  run('Views.favorites.destroy()');
  dom.window.close(); console.log("OK favoris : artistes, pagination et mise à jour locale");
} catch(error) {console.error(error);dom.window.close();process.exitCode=1;} })();
