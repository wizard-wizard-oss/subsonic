// Une fenêtre étroite avec une souris conserve le nouveau web ; le tactile garde son adaptateur existant.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const {JSDOM} = require(process.argv[2] || "jsdom");
const root=path.join(__dirname,"../src/web-pc");
function check(width,touch,expected){
  const dom=new JSDOM(fs.readFileSync(path.join(root,"index.html"),"utf8"),{url:"https://music.example/",runScripts:"outside-only"});
  const w=dom.window,d=w.document;
  const run=code=>vm.runInContext(code,dom.getInternalVMContext());
  w.matchMedia=query=>({matches:query.split(",").some(branch=>branch.split(/\s+and\s+/).every(condition=>{
    const limit=condition.match(/max-width:\s*(\d+)px/);
    if(limit)return width<=Number(limit[1]);
    if(condition.includes("hover: none") || condition.includes("pointer: coarse"))return touch;
    throw new Error("Condition média inconnue : "+condition);
  })),addEventListener(){}});
  for(const file of ["core","icons"])run(fs.readFileSync(path.join(root,"static/js/"+file+".js"),"utf8"));
  run('App.user={id:1,roles:[]};App.preferences={};App.music={route:null};class MobileNavigation{destroy(){}}');
  d.getElementById("app").hidden=false;
  for(const file of ["desktop-playlists","desktop-navigation","mobile/bootstrap"])run(fs.readFileSync(path.join(root,"static/js/"+file+".js"),"utf8"));
  assert.equal(run("App.layout"),expected,`${width}px, tactile=${touch}`);
  if(expected==="desktop"){
    assert.ok(d.querySelector("#sidebar>.topnav"));
    assert.equal(d.querySelector(".topbar>.topnav"),null);
    assert.equal(d.querySelector("#sidebar a[href='#/news'] span").dataset.t,"nav.webzines");
  }
  w.close();
}
for(const width of [600,809,820,1024,1440])check(width,false,"desktop");
for(const width of [390,809,1024])check(width,true,"mobile");
check(1440,true,"desktop");
console.log("OK fenêtre ordinateur étroite : menu vertical conservé ; tactile isolé");
