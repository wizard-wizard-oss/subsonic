"use strict";
/* Les listes et leurs cibles restent en place : seul l'espace réservé aux playlists change. */
class DesktopPlaylists {
  constructor(sidebar, heading, onChange) {
    this.sidebar = sidebar;
    this.list = document.getElementById("playlist-list");
    this.onChange = onChange;
    this.expanded = this.dragging = false;
    this.frame = null;
    this.direction = 0;
    this.button = App.el("button.icon-button.playlist-expand", {type: "button", "aria-controls": "panel-playlists",
      onclick: () => { this.expanded = !this.expanded; this.render(); }});
    heading.querySelector(".desktop-playlist-actions").prepend(this.button);
    this.place = document.createComment("playlist scrolling");
    this.list.before(this.place);
    this.up = this.scrollButton(-1);
    this.down = this.scrollButton(1);
    this.scroller = App.el("div.playlist-scroll", {}, this.up, this.list, this.down);
    this.place.after(this.scroller);
    this.over = event => this.dragOver(event);
    this.leave = event => { if (!this.scroller.contains(event.relatedTarget)) this.stopScroll(); };
    this.scroll = () => this.updateScroll();
    this.scroller.addEventListener("dragover", this.over);
    this.scroller.addEventListener("dragleave", this.leave);
    this.list.addEventListener("scroll", this.scroll);
    this.off = App.bus.on("dnd", active => this.setDragging(active));
    this.render();
  }

  scrollButton(direction) {
    const label = App.t(direction < 0 ? "playlist.scroll_up" : "playlist.scroll_down");
    return App.el("button.playlist-scroll-hint", {type: "button", "aria-label": label, text: label,
      onclick: () => this.list.scrollBy({top: direction * this.list.clientHeight * .75, behavior: "smooth"})});
  }

  render() {
    const active = this.expanded || this.dragging;
    document.body.dataset.playlistFocus = String(active);
    const label = App.t(active ? "playlist.collapse" : "playlist.expand");
    this.button.title = label;
    this.button.setAttribute("aria-label", label);
    this.button.setAttribute("aria-expanded", String(active));
    this.button.replaceChildren(App.icon(active ? "collapse" : "expand", 16));
    this.onChange();
    this.updateScroll();
  }

  setDragging(active) {
    if (active === this.dragging) return;
    if (active) this.position = {list: this.list.scrollTop, sidebar: this.sidebar.scrollTop};
    this.dragging = active;
    if (!active) this.stopScroll();
    this.render();
    if (!active && this.position) {
      this.list.scrollTop = this.position.list;
      this.sidebar.scrollTop = this.position.sidebar;
      this.position = null;
      this.updateScroll();
    }
  }

  updateScroll() {
    this.up.disabled = this.list.scrollTop <= 1;
    this.down.disabled = this.list.scrollTop + this.list.clientHeight >= this.list.scrollHeight - 1;
    if (this.direction < 0 && this.up.disabled || this.direction > 0 && this.down.disabled) this.stopScroll();
  }

  dragOver(event) {
    if (!this.dragging) return;
    const rect = this.list.getBoundingClientRect();
    const edge = Math.min(36, this.list.clientHeight / 4);
    this.direction = event.clientY < rect.top + edge ? -1 : event.clientY > rect.bottom - edge ? 1 : 0;
    this.updateScroll();
    if (!this.direction) { this.stopScroll(); return; }
    event.preventDefault();
    if (this.frame === null) this.frame = requestAnimationFrame(time => this.scrollFrame(time));
  }

  scrollFrame(time) {
    this.frame = null;
    if (!this.dragging || !this.direction) return;
    const elapsed = this.lastTime ? Math.min(50, time - this.lastTime) : 16;
    this.lastTime = time;
    this.list.scrollTop += this.direction * elapsed * .34;
    this.updateScroll();
    if (this.direction) this.frame = requestAnimationFrame(next => this.scrollFrame(next));
  }

  stopScroll() {
    if (this.frame !== null) cancelAnimationFrame(this.frame);
    this.frame = null;
    this.direction = 0;
    this.lastTime = 0;
  }

  reset() { this.expanded = false; this.setDragging(false); this.render(); }

  destroy() {
    this.off();
    this.stopScroll();
    this.scroller.removeEventListener("dragover", this.over);
    this.scroller.removeEventListener("dragleave", this.leave);
    this.list.removeEventListener("scroll", this.scroll);
    this.place.replaceWith(this.list);
    this.scroller.remove();
    this.button.remove();
    delete document.body.dataset.playlistFocus;
  }
}
