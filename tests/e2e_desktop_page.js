// Vraie page ordinateur : navigation, reprise, conseils privés, playlists et ressources locales.
const assert = require("node:assert/strict");
const {JSDOM} = require(process.argv[3] || "jsdom");
const base = "http://127.0.0.1:" + process.argv[2];
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));

async function session(username, password) {
  const login = await fetch(base + "/api/login", {method:"POST", headers:{"Content-Type":"application/json", "X-Requested-With":"pmw"},
    body:JSON.stringify({username,password})});
  assert.equal(login.status,200);
  const cookie=login.headers.get("set-cookie").split(";")[0];
  return async (url,body) => {
    const response=await fetch(base+url, {method:body?"POST":"GET",headers:{Cookie:cookie,"Content-Type":"application/json","X-Requested-With":"pmw"},
      body:body?JSON.stringify(body):undefined});
    assert.equal(response.status,200, url);
    return response.json();
  };
}

(async()=>{
  const alice=await session("alice","secret"), bob=await session("bob","pw2");
  await alice("/api/play-queue/save",{ids:["s1","s4"],current:"s4",position:42});
  await alice("/api/listening/history",{id:"s1",requestId:"a".repeat(32)});
  await bob("/api/recommendation/send",{recipient:"alice",kind:"album",source:"subsonic",sourceId:"al1"});
  let cookie="", changeScreen;
  const requests=[], errors=[], screen={matches:false,addEventListener(kind,callback){changeScreen=callback;}};
  const dom=await JSDOM.fromURL(base+"/", {runScripts:"dangerously",resources:"usable",pretendToBeVisual:true,
    beforeParse(window){
      window.matchMedia=query=>query.includes("max-width")?screen:{matches:false};
      window.CSS={escape:value=>String(value)};
      window.fetch=async(url,options={})=>{
        requests.push({url:String(url),method:options.method||"GET",body:options.body});
        const response=await fetch(new URL(url,base),{...options,headers:{...options.headers,Cookie:cookie}});
        if(response.headers.get("set-cookie")) cookie=response.headers.get("set-cookie").split(";")[0];
        return response;
      };
      window.EventSource=class{addEventListener(){}close(){}};
      window.Element.prototype.scrollIntoView=function(){};
      window.HTMLMediaElement.prototype.play=()=>Promise.resolve();
      window.HTMLMediaElement.prototype.pause=function(){};
      window.HTMLMediaElement.prototype.load=function(){};
      window.addEventListener("error",event=>errors.push(event.message));
    }});
  const w=dom.window, d=w.document, $=selector=>d.querySelector(selector);
  const until=async(test,label)=>{
    for(let i=0;i<400;i++){if(test())return;await delay(20);}
    throw new Error("Attente dépassée : "+label);
  };
  try{
    await until(()=>!$("#login").hidden,"connexion");
    $('#login-form input[name="username"]').value="alice";
    $('#login-form input[name="password"]').value="secret";
    $('#login-form button[type="submit"]').click();
    await until(()=>$(".desktop-home .home-recent .album-card") && $(".home-received .listen-later-tile") && !$(".personal-resume").hidden,"accueil complet");
    assert.equal(d.body.dataset.chat,"closed");
    assert.equal(d.documentElement.dataset.theme,"dark");
    assert.equal(w.eval("App.player.playing"),false);
    assert.equal($(".home-received .listen-later-kind"),null);
    assert.equal($(".home-received .recommendation-advisers"),null);
    assert.ok($(".home-received .home-card-context").textContent.includes("bob"));
    assert.equal($(".home-rail-all"),null);
    assert.ok($(".personal-resume").textContent.includes("0:42"));
    assert.ok($("#sidebar>.topnav"));
    assert.ok($(".topbar .desktop-guide svg"));
    assert.ok($(".desktop-top-start .desktop-brand-icon"));
    assert.equal($(".desktop-top-start .brand").closest("a,button"),null);
    assert.ok($(".account-menu-panel #version-tag"));
    assert.equal($(".topbar>.version-tag"),null);
    assert.equal($("#sidebar a[href='#/albums/newest']").textContent,"Bibliothèque");
    assert.ok(requests.some(request=>request.url.startsWith("/api/news/releases/radar?")));
    assert.equal((await alice("/api/recommendation/status")).unread,true);
    assert.ok(!requests.some(request=>request.url==="/api/recommendation/read"));
    await until(()=>$('#sidebar a[href="#/listen-later/bookmarks"]').classList.contains("recommendations-unread"),"pastille des conseils reçus");
    $('#sidebar a[href="#/albums/newest"]').click();
    await until(()=>$(".library-shortcuts button"),"réessayer les collections de Bibliothèque");
    $(".library-shortcuts button").click();
    await until(()=>!$(".library-shortcuts button") && $("#artist-list a.artist"),"raccourcis rechargés");
    $('#sidebar a[href="#/"]').click();
    await until(()=>$(".desktop-home .home-received .listen-later-tile"),"retour à l’accueil");
    console.log("OK ordinateur : rangées personnelles, file restaurée sans lecture, conseils non lus et radar existant");

    const home=$(".desktop-home");
    $("#toggle-sidebar").click();assert.equal(d.body.dataset.desktopMenu,"closed");
    $("#toggle-sidebar").click();assert.equal(d.body.dataset.desktopMenu,"open");
    assert.equal($(".desktop-home"),home);
    $("#account-menu").open=true;$("#open-settings").click();
    await until(()=>$(".dialog"),"réglages");
    assert.equal($('.dialog select[name="sidebar"]'),null);
    assert.equal($('.dialog select[name="chat_panel"]'),null);
    const theme=[...d.querySelectorAll("label.setting")].find(label=>label.textContent.includes("Thème")).querySelector("select");
    assert.deepEqual([...theme.options].map(option=>option.value),["dark","light"]);
    theme.value="light";theme.dispatchEvent(new w.Event("change"));
    await until(()=>d.documentElement.dataset.theme==="light","mode clair conservé");
    assert.equal((await alice("/api/me")).preferences.theme,"light");
    theme.value="dark";theme.dispatchEvent(new w.Event("change"));
    await until(()=>d.documentElement.dataset.theme==="dark","retour au sombre");
    w.eval("Dialogs.close()");
    assert.equal($("#account-menu").open,false);
    $('#sidebar a[href="#/news"]').click();
    await until(()=>$(".news-press .news-list"),"Webzines");
    assert.equal(w.getComputedStyle($(".news-sections")).display,"none");
    assert.ok($('#sidebar a[href="#/news"]').classList.contains("active"));
    assert.ok(!$('#sidebar a[href="#/news/releases"]').classList.contains("active"));
    $('#sidebar a[href="#/news/releases"]').click();
    await until(()=>$(".weekly-toolbar"),"Sorties");
    assert.equal(w.getComputedStyle($(".news-sections")).display,"none");
    assert.ok($('#sidebar a[href="#/news/releases"]').classList.contains("active"));
    assert.ok(!$('#sidebar a[href="#/news"]').classList.contains("active"));
    $("#toggle-chat").click();assert.equal(d.body.dataset.chat,"open");
    $("#toggle-chat").click();assert.equal(d.body.dataset.chat,"closed");
    $("#sidebar a[href='#/listen-later/bookmarks']").click();
    await until(()=>$('.listen-later-tabs button[aria-selected="true"]'),"marque-pages");
    assert.equal($('.listen-later-tabs button[aria-selected="true"]').dataset.tab,"bookmarks");
    assert.equal((await alice("/api/recommendation/status")).unread,true);
    $("#listen-later-tab-received").click();
    await until(()=>!$('#sidebar a[href="#/listen-later/bookmarks"]').classList.contains("recommendations-unread"),"pastille de recommandation retirée après lecture");
    console.log("OK ordinateur : menu et salon repliables, réglages dans le compte, accès direct aux marque-pages");

    $("#playlist-new").click();await until(()=>$(".dialog-input"),"nouvelle playlist");
    $(".dialog-input").value="Playlist de bureau";$(".dialog button.primary").click();
    await until(()=>$("#playlist-list .playlist-row") && w.eval("App.music.route.view")==="playlist","playlist créée");
    const playlistId=w.eval("App.music.route.id");
    await alice("/api/playlist/add",{id:playlistId,songIds:["s1","s2","s4"]});
    $('.desktop-playlist-heading .playlist-see-all').click();
    await until(()=>$(".playlist-card"),"galerie dédiée");
    assert.equal(w.eval("App.music.route.view"),"playlists");
    assert.equal($(".playlist-card-name").textContent,"Playlist de bureau");
    assert.equal(d.querySelectorAll(".playlist-card .playlist-artwork img").length,4);
    const covers=[...d.querySelectorAll(".playlist-card .playlist-artwork img")].map(img=>img.src);
    $(".playlist-card-name").click();
    await until(()=>$(".playlist-detail-head .playlist-artwork img"),"même mosaïque dans la playlist");
    assert.deepEqual([...d.querySelectorAll(".playlist-detail-head .playlist-artwork img")].map(img=>img.src),covers);
    $(".desktop-guide").click();await until(()=>$(".help-hero"),"page Help existante");
    assert.ok($(".help-hero").textContent.length);
    screen.matches=true;changeScreen();
    assert.ok($(".mobile-menu-tools"));assert.equal(d.body.hasAttribute("data-desktop-layout"),false);
    assert.equal($("#sidebar a[href='#/listen-later/bookmarks']"),null);
    screen.matches=false;changeScreen();
    assert.ok($("#sidebar>.topnav"));assert.equal($(".mobile-menu-tools"),null);
    assert.equal(d.querySelectorAll("#playlist-list .playlist-row").length,1);
    assert.equal(d.querySelectorAll("#version-tag").length,1);
    console.log("OK ordinateur : playlists, Help et changements de taille sans duplication");

    const fontCss=await (await fetch(base+"/static/css/fonts.css")).text();
    for(const resource of fontCss.matchAll(/url\("(.+?)"\)/g)){
      const response=await fetch(new URL(resource[1],base+"/static/css/fonts.css"));
      assert.equal(response.status,200);assert.equal(response.headers.get("content-type"),"font/woff2");
      assert.equal(Buffer.from(await response.arrayBuffer()).subarray(0,4).toString(),"wOF2");
    }
    assert.equal(errors.length,0,errors.join("\n"));
    console.log("OK police : IBM Plex Mono locale, fichiers WOFF2 servis et aucune erreur JavaScript");
  }finally{w.close();}
})().then(()=>process.exit(0)).catch(error=>{console.error(error);process.exit(1);});
