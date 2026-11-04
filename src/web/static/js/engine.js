"use strict";
// Moteur de lecture : l'élément audio habituel, ou le lecteur officiel YouTube intégré.
// Il imite les propriétés de l'élément audio (currentTime, paused, play()…) : le reste de l'application
// n'a pas besoin de savoir quel moteur joue.

const YT_STATE = {ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3};
const HANDLER_NAMES = ["onended", "onplaying", "onplay", "onpause", "onerror", "ontimeupdate"];

class YouTubeLoader {
  /* Charge l'API YouTube une seule fois, au premier titre YouTube */
  constructor() { this.promise = null; }
  load() {
    if (this.promise) return this.promise;
    this.promise = new Promise((resolve, reject) => {
      if (window.YT && window.YT.Player) return resolve(window.YT);
      window.onYouTubeIframeAPIReady = () => resolve(window.YT);
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.onerror = () => { this.promise = null; reject(new Error("YouTube injoignable")); };
      document.head.appendChild(script);
    });
    return this.promise;
  }
}

class PlayerEngine {
  constructor() {
    this.el = new Audio();
    this.dataset = this.el.dataset;
    this.mode = "html";                 // « html » ou « youtube »
    this.handlers = {};
    this.loader = new YouTubeLoader();
    this.player = null;                 // lecteur YouTube
    this.videoId = "";
    this.ytState = -1;
    this.ytError = null;
    this.ticker = null;
    HANDLER_NAMES.forEach(name => Object.defineProperty(this, name, {
      get: () => this.handlers[name],
      set: fn => { this.handlers[name] = fn; if (this.el.handlers) this.el.handlers[name] = fn; else this.el[name] = fn; }
    }));
  }

  fire(name) { if (this.handlers[name]) this.handlers[name](); }
  get isYouTube() { return this.mode === "youtube"; }

  /* Change la sortie du son (lecture haute fidélité : MpvAudio, voir hifi.js) */
  useOutput(el) {
    this.el.pause();
    this.el = el;
    this.dataset = el.dataset;
    HANDLER_NAMES.forEach(name => { if (this.handlers[name]) el.handlers ? (el.handlers[name] = this.handlers[name]) : (el[name] = this.handlers[name]); });
  }
  queueNext(url) { if (this.el.queueNext && !this.isYouTube) this.el.queueNext(url); }

  /* ---------- propriétés imitées ---------- */
  get paused() { return this.isYouTube ? ![YT_STATE.PLAYING, YT_STATE.BUFFERING].includes(this.ytState) : this.el.paused; }
  get src() { return this.isYouTube ? "youtube:" + this.videoId : this.el.src; }
  set src(value) { this.leaveYouTube(); this.el.src = value; }
  get currentTime() { return this.isYouTube ? this.ytCall("getCurrentTime", 0) : this.el.currentTime; }
  set currentTime(t) { if (this.isYouTube) this.ytCall("seekTo", null, t, true); else this.el.currentTime = t; }
  get duration() { return this.isYouTube ? this.ytCall("getDuration", 0) : this.el.duration; }
  get readyState() { return this.isYouTube ? (this.ytState === YT_STATE.PLAYING ? 4 : 0) : this.el.readyState; }
  get error() { return this.isYouTube ? this.ytError : this.el.error; }
  get volume() { return this.isYouTube ? this.ytCall("getVolume", 100) / 100 : this.el.volume; }
  set volume(v) {
    v = Math.min(1, Math.max(0, v));
    if (this.isYouTube) this.ytCall("setVolume", null, Math.round(v * 100)); else this.el.volume = v;
  }

  /* ---------- commandes ---------- */
  play() {
    if (this.isYouTube) { this.ytCall("playVideo"); return Promise.resolve(); }
    return this.el.play();
  }
  pause() { if (this.isYouTube) this.ytCall("pauseVideo"); else this.el.pause(); }
  load() { if (!this.isYouTube) this.el.load(); }
  removeAttribute(name) { this.leaveYouTube(); this.el.removeAttribute(name); }

  /* ---------- YouTube ---------- */
  loadYouTube(videoId) {
    this.el.pause(); this.el.removeAttribute("src"); this.el.load();
    this.mode = "youtube"; this.videoId = videoId; this.ytState = -1; this.ytError = null;
    document.body.classList.add("yt");
    this.loader.load().then(YT => this.startVideo(YT, videoId)).catch(() => this.failWith({code: "yt-load"}));
  }
  startVideo(YT, videoId) {
    if (!this.isYouTube || this.videoId !== videoId) return;          // un autre titre a été choisi entre-temps
    if (this.player) { this.player.loadVideoById(videoId); return; }
    this.player = new YT.Player("ytplayer", {
      width: "100%", height: "100%", videoId,
      playerVars: {autoplay: 1, controls: 0, playsinline: 1, rel: 0, iv_load_policy: 3, disablekb: 1, fs: 0},
      events: {onStateChange: e => this.onYouTubeState(e.data), onError: e => this.failWith({code: e.data})}
    });
    this.ticker = setInterval(() => { if (this.isYouTube && this.ytState === YT_STATE.PLAYING) this.fire("ontimeupdate"); }, 500);
  }
  onYouTubeState(state) {
    this.ytState = state;
    if (state === YT_STATE.PLAYING) { this.fire("onplay"); this.fire("onplaying"); }
    else if (state === YT_STATE.PAUSED) this.fire("onpause");
    else if (state === YT_STATE.ENDED) this.fire("onended");
  }
  failWith(error) { this.ytError = error; this.fire("onerror"); }
  ytCall(method, fallback, ...args) {
    try { if (this.player && this.player[method]) { const r = this.player[method](...args); return r === undefined ? fallback : r; } }
    catch (e) { /* lecteur pas encore prêt */ }
    return fallback;
  }
  leaveYouTube() {
    if (!this.isYouTube) return;
    this.ytCall("stopVideo");
    this.mode = "html"; this.videoId = ""; this.ytState = -1;
    document.body.classList.remove("yt");
  }
}
