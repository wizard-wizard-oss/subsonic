// Enregistrement des écoutes : seuil effectif du serveur, sans service externe.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const {JSDOM} = require(process.argv[2] || "jsdom");
const dom = new JSDOM('<main></main>', {url:"https://example.test/", runScripts:"dangerously"});
const w = dom.window, d = w.document;
const src = name => fs.readFileSync(path.join(__dirname,"../src/web-pc/static/js",name+".js"),"utf8");
const writes = [];
w.write = async (url, body) => { writes.push({url,body}); return {}; };
const setup = d.createElement("script");
setup.textContent = src("core") + '\n' + src("player") + `
App.user = {id:1,roles:["stream"]}; App.api.post=window.write;
App.listeningPolicy={minimum_duration:30,maximum_seconds:240,fraction:0.5};
App.bus={emit(){},on(){return ()=>{};}};
`;
d.head.append(setup);
(async () => {
  w.eval(`
    window.engine={volume:1,currentTime:0,duration:200,addEventListener(){}};
    window.testPlayer=new Player(engine);
    testPlayer.startListen({id:"s1",title:"Song"});
    engine.currentTime=99; testPlayer.countListen();
  `);
  assert.equal(writes.filter(call=>call.url==="/api/listening/history").length,0);
  w.eval('for(let i=0;i<101;i++){engine.currentTime+=1;testPlayer.countListen();}');
  const history = writes.filter(call=>call.url==="/api/listening/history");
  assert.equal(history.length,1);
  assert.equal(history[0].body.id,"s1");
  assert.match(history[0].body.requestId,/^[0-9a-f]{32}$/);
  assert.equal(writes.filter(call=>call.url==="/api/scrobble").length,0);

  // Les écoutes suivantes sont distinctes ; les sources externes ne sont pas comptées.
  w.eval('testPlayer.startListen({id:"s1",title:"Song"});engine.currentTime=0;for(let i=0;i<101;i++){engine.currentTime+=1;testPlayer.countListen();}');
  assert.equal(writes.filter(call=>call.url==="/api/listening/history").length,2);
  const tokens=writes.filter(call=>call.url==="/api/listening/history").map(call=>call.body.requestId);
  assert.notEqual(tokens[0],tokens[1]);
  w.eval('testPlayer.startListen({id:"youtube",ext:true,title:"Video"});for(let i=0;i<300;i++){engine.currentTime+=1;testPlayer.countListen();}');
  assert.equal(writes.filter(call=>call.url==="/api/listening/history").length,2);
  w.close();
  console.log("OK écoute effective, avances rapides, répétitions et enregistrement sans droit scrobble");
})().catch(error=>{console.error(error); w.close(); process.exitCode=1;});
