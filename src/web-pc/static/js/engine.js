"use strict";
/* Moteur de lecture : l'élément <audio> (Subsonic, Jamendo), le lecteur officiel YouTube ou celui de SoundCloud
   (son « widget »), dans une petite fenêtre visible (exigé par YouTube, demandé par SoundCloud). Il se comporte comme un élément audio (paused, currentTime,
   duration, volume, play(), pause() et les mêmes événements) : le lecteur n'a pas à savoir qui joue.
   Aucun contournement : ni bloqueur de publicité, ni téléchargement. */

const YT_STATE = {ENDED: 0, PLAYING: 1, PAUSED: 2, BUFFERING: 3};
const AUDIO_EVENTS = ["play", "pause", "timeupdate", "durationchange", "volumechange", "ended", "error"];

/** Charge l'API YouTube une seule fois, au premier titre YouTube. */
class YouTubeLoader {
  constructor() { this.promise = null; }
  load() {
    if (this.promise) return this.promise;
    this.promise = new Promise((resolve, reject) => {
      if (window.YT && window.YT.Player) { resolve(window.YT); return; }
      window.onYouTubeIframeAPIReady = () => resolve(window.YT);
      const script = document.createElement("script");
      script.src = "https://www.youtube.com/iframe_api";
      script.onerror = () => { this.promise = null; reject(new Error("youtube")); };
      document.head.appendChild(script);
    });
    return this.promise;
  }
}

/** Charge l'API du lecteur SoundCloud une seule fois, au premier titre SoundCloud. */
class SoundCloudLoader {
  constructor() { this.promise = null; }
  load() {
    if (this.promise) return this.promise;
    this.promise = new Promise((resolve, reject) => {
      if (window.SC && window.SC.Widget) { resolve(window.SC); return; }
      const script = document.createElement("script");
      script.src = "https://w.soundcloud.com/player/api.js";
      script.onload = () => (window.SC && window.SC.Widget ? resolve(window.SC) : reject(new Error("soundcloud")));
      script.onerror = () => { this.promise = null; reject(new Error("soundcloud")); };
      document.head.appendChild(script);
    });
    return this.promise;
  }
}

const SOUNDCLOUD_PLAYER = "https://w.soundcloud.com/player/?";
const SOUNDCLOUD_OPTIONS = {auto_play: "true", visual: "true", show_comments: "false", hide_related: "true",
                            show_reposts: "false", show_teaser: "false", buying: "false", sharing: "false", download: "false"};

class PlaybackEngine extends EventTarget {
  constructor(audio, videoBox) {
    super();
    this.audio = audio;
    this.videoBox = videoBox;
    this.videoWindow = videoBox.parentNode;    // le lecteur YouTube remplace videoBox : la fenêtre, elle, reste
    this.loader = new YouTubeLoader();
    this.soundLoader = new SoundCloudLoader();
    this.sound = null;                 // titre SoundCloud en cours : {url, frame, widget, playing, position, duration, error}
    this.youtube = null;               // lecteur YouTube, créé au premier titre YouTube
    this.videoId = "";
    this.state = -1;
    this.youtubeError = null;
    this.level = audio.volume;
    for (const kind of AUDIO_EVENTS) {
      audio.addEventListener(kind, () => { if (!this.videoId && !this.sound) this.emit(kind); });
    }
    setInterval(() => { if (this.videoId && this.state === YT_STATE.PLAYING) this.emit("timeupdate"); }, 500);
  }

  emit(kind) { this.dispatchEvent(new Event(kind)); }
  get isYouTube() { return !!this.videoId; }
  get isSoundCloud() { return !!this.sound; }

  /* --- comme un élément audio --- */
  get paused() {
    if (this.sound) return !this.sound.playing;
    return this.isYouTube ? ![YT_STATE.PLAYING, YT_STATE.BUFFERING].includes(this.state) : this.audio.paused;
  }
  get src() { return this.sound ? "soundcloud:" + this.sound.url : this.isYouTube ? "youtube:" + this.videoId : this.audio.src; }
  get currentTime() {
    if (this.sound) return this.sound.position;
    return this.isYouTube ? this.call("getCurrentTime", 0) : this.audio.currentTime;
  }
  set currentTime(seconds) {
    if (this.sound) { this.sound.position = seconds; this.soundCall("seekTo", Math.round(seconds * 1000)); }
    else if (this.isYouTube) this.call("seekTo", null, seconds, true);
    else this.audio.currentTime = seconds;
  }
  get duration() {
    if (this.sound) return this.sound.duration;
    return this.isYouTube ? this.call("getDuration", NaN) : this.audio.duration;
  }
  get error() { return this.sound ? this.sound.error : this.isYouTube ? this.youtubeError : this.audio.error; }
  get volume() { return this.level; }
  set volume(value) {
    this.level = Math.min(1, Math.max(0, value));
    this.audio.volume = this.level;
    this.call("setVolume", null, Math.round(this.level * 100));
    this.soundCall("setVolume", Math.round(this.level * 100));
    this.emit("volumechange");
  }
  play() {
    if (this.sound) { this.soundCall("play"); return Promise.resolve(); }
    if (this.isYouTube) { this.call("playVideo"); return Promise.resolve(); }
    return this.audio.play();
  }
  pause() {
    if (this.sound) this.soundCall("pause");
    else if (this.isYouTube) this.call("pauseVideo");
    else this.audio.pause();
  }

  /* --- sources --- */
  playUrl(url) {
    this.leaveYouTube();
    this.leaveSoundCloud();
    this.audio.src = url;
    return this.audio.play();
  }

  playYouTube(videoId) {
    this.leaveSoundCloud();
    this.audio.pause();
    this.audio.removeAttribute("src");
    this.videoId = videoId;
    this.state = -1;
    this.youtubeError = null;
    document.body.dataset.video = "on";
    document.body.dataset.videoSource = "youtube";
    this.loader.load().then(YT => this.start(YT, videoId)).catch(() => this.fail("youtube-unreachable"));
    return Promise.resolve();
  }

  start(YT, videoId) {
    if (this.videoId !== videoId) return;            // un autre titre a été choisi entre-temps
    if (this.youtube) { this.youtube.loadVideoById(videoId); return; }
    this.youtube = new YT.Player(this.videoBox, {
      width: "100%", height: "100%", videoId, host: "https://www.youtube-nocookie.com",
      playerVars: {autoplay: 1, controls: 0, playsinline: 1, rel: 0, iv_load_policy: 3, disablekb: 1, fs: 0},
      events: {
        onReady: () => this.call("setVolume", null, Math.round(this.level * 100)),
        onStateChange: event => this.changed(event.data),
        onError: event => this.fail(event.data)}});
  }

  changed(state) {
    this.state = state;
    if (state === YT_STATE.PLAYING) { this.emit("durationchange"); this.emit("play"); }
    else if (state === YT_STATE.PAUSED) this.emit("pause");
    else if (state === YT_STATE.ENDED) this.emit("ended");
  }

  fail(code) {
    this.youtubeError = {code};
    this.emit("error");
  }

  call(method, fallback, ...args) {
    try {
      if (this.youtube && this.youtube[method]) {
        const result = this.youtube[method](...args);
        return result === undefined ? fallback : result;
      }
    } catch (error) { /* lecteur pas encore prêt */ }
    return fallback;
  }

  leaveYouTube() {
    if (!this.isYouTube) return;
    this.call("stopVideo");
    this.videoId = "";
    this.state = -1;
    delete document.body.dataset.video;
    delete document.body.dataset.videoSource;
  }

  /** Titre SoundCloud (url : « https://api.soundcloud.com/tracks/<n> ») : un nouveau lecteur officiel par titre,
      dans la fenêtre vidéo. Son API répond par événements : position et durée sont gardées au fil de l'eau. */
  playSoundCloud(url) {
    this.leaveYouTube();
    this.leaveSoundCloud();
    this.audio.pause();
    this.audio.removeAttribute("src");
    const frame = document.createElement("iframe");
    frame.className = "soundcloud-frame";
    frame.title = "SoundCloud";
    frame.allow = "autoplay; encrypted-media";            // comme le code d'intégration de SoundCloud
    frame.src = SOUNDCLOUD_PLAYER + new URLSearchParams(Object.assign({url}, SOUNDCLOUD_OPTIONS));
    this.videoWindow.appendChild(frame);
    const sound = {url, frame, widget: null, playing: false, position: 0, duration: NaN, error: null};
    this.sound = sound;
    document.body.dataset.video = "on";
    document.body.dataset.videoSource = "soundcloud";
    this.soundLoader.load().then(SC => this.bindSound(SC, sound)).catch(() => this.failSound(sound, "soundcloud-unreachable"));
    return Promise.resolve();
  }

  bindSound(SC, sound) {
    if (this.sound !== sound) return;                // un autre titre a été choisi entre-temps
    const widget = sound.widget = SC.Widget(sound.frame);
    const events = SC.Widget.Events;
    const on = (kind, handler) => widget.bind(kind, event => { if (this.sound === sound) handler(event || {}); });
    const readDuration = () => widget.getDuration(ms => {
      if (this.sound === sound && ms > 0) { sound.duration = ms / 1000; this.emit("durationchange"); }
    });
    on(events.READY, () => { widget.setVolume(Math.round(this.level * 100)); readDuration(); });
    on(events.PLAY, () => { sound.playing = true; readDuration(); this.emit("play"); });
    on(events.PAUSE, () => { sound.playing = false; this.emit("pause"); });
    on(events.FINISH, () => { sound.playing = false; this.emit("ended"); });
    on(events.PLAY_PROGRESS, event => { sound.position = (event.currentPosition || 0) / 1000; this.emit("timeupdate"); });
    on(events.ERROR, () => this.failSound(sound, "soundcloud-error"));
  }

  failSound(sound, code) {
    if (this.sound !== sound) return;
    sound.error = {code};
    this.emit("error");
  }

  soundCall(method, ...args) {
    try { if (this.sound && this.sound.widget) this.sound.widget[method](...args); } catch (error) { /* pas encore prêt */ }
  }

  leaveSoundCloud() {
    if (!this.sound) return;
    this.soundCall("pause");
    this.sound.frame.remove();
    this.sound = null;
    delete document.body.dataset.video;
    delete document.body.dataset.videoSource;
  }
}
