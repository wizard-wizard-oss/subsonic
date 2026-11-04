"use strict";
/* Temps réel : une seule connexion EventSource pour toute la page. Les composants s'abonnent par type
   (« message », « message_updated », « mention », « typing », « presence », « artists » : la bibliothèque a changé) et à « reconnected » pour
   rattraper ce qu'ils ont manqué pendant une coupure. */

class LiveEvents {
  constructor() {
    this.source = null;
    this.handlers = {};
    this.wasConnected = false;
    this.lost = false;
  }

  on(kind, handler) {
    (this.handlers[kind] = this.handlers[kind] || []).push(handler);
    return () => { this.handlers[kind] = this.handlers[kind].filter(h => h !== handler); };
  }

  emit(kind, data) { (this.handlers[kind] || []).slice().forEach(h => h(data)); }

  start() {
    if (this.source || typeof EventSource === "undefined") return;
    this.source = new EventSource("/api/events");
    for (const kind of ["message", "message_updated", "mention", "typing", "presence", "artists"]) {
      this.source.addEventListener(kind, event => {
        let data;
        try { data = JSON.parse(event.data); } catch (e) { return; }
        this.emit(kind, data);
      });
    }
    this.source.addEventListener("open", () => {
      if (this.wasConnected && this.lost) this.emit("reconnected");
      this.wasConnected = true;
      this.lost = false;
      this.emit("status", {connected: true});
    });
    this.source.addEventListener("error", () => {   // EventSource se reconnecte tout seul
      this.lost = true;
      this.emit("status", {connected: false});
    });
  }

  stop() {
    if (this.source) this.source.close();
    this.source = null;
  }
}

App.live = new LiveEvents();
