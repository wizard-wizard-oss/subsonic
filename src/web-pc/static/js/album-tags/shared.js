"use strict";
/* Éditeur de tags : aides communes et classe de base. draft.js, save.js et sources.js ajoutent leurs méthodes ;
   editor.js ouvre l'éditeur. Brouillon local, comparaison validée par le serveur, écriture et suivi du scan. */
const AlbumTags = (() => {
  const el = App.el, t = (key, params) => App.t("tags." + key, params);
  // fields : liste envoyée par le serveur (/api/tags/status), jamais recopiée ici ; current : éditeur ouvert.
  const state = {fields: [], current: null};
  const COMMON = ["albumArtist", "artist", "album", "year"];
  const TRACK_FIELDS = ["disc", "track", "title", "artist", "genre"];
  const SOURCE_TRACK_FIELDS = new Set(["title", "artist", "track", "disc"]);
  const POLL_INTERVAL = 1000;

  const button = (text, run, className = "") => el("button" + (className ? "." + className : ""),
    {type: "button", text, onclick: run});
  const copyTags = tags => Object.fromEntries(state.fields.map(key => [key, String(tags[key] ?? "")]));
  const fieldLabel = key => t(key + "_label_ui");
  const sourceStyles = release => {
    const values = [...(Array.isArray(release.styles) ? release.styles : []),
      ...(Array.isArray(release.genres) ? release.genres : [])].filter(value => typeof value === "string" && value.trim());
    if (!values.length && typeof release.genre === "string" && release.genre.trim()) values.push(release.genre);
    return [...new Set(values)];
  };

  class Editor {
    constructor(album, onSaved) {
      this.album = album;
      this.onSaved = onSaved;
      this.selected = new Set();
      this.commonTouched = new Set();
      this.commonInputs = new Map();
      this.rowInputs = [];
      this.generation = 0;
      this.sourceGeneration = 0;
      this.busy = false;
      this.operationId = null;
      this.operationComplete = false;
      this.previouslyFocused = document.activeElement;
      this.build(album);
      this.keyHandler = event => this.keydown(event);
      this.unloadHandler = event => {
        if (this.dirty() || this.saving || this.operationId && !this.operationComplete) {
          event.preventDefault(); event.returnValue = "";
        }
      };
    }

    build(album) {
      this.status = el("p.tags-status", {role: "status", "aria-live": "polite", tabIndex: -1});
      this.progressLabel = el("strong.tags-progress-label");
      this.progressBar = el("progress.tags-progress-bar");
      this.progressHelp = el("p.tags-caption.tags-progress-help");
      this.progress = el("section.tags-progress", {hidden: true, "aria-label": t("progress_ui")},
        this.progressLabel, this.progressBar, this.progressHelp);
      this.body = el("div.tags-body", {}, el("p.muted", {text: t("loading_ui")}));
      this.closeButton = App.setIcon(button("", () => this.requestClose(), "icon-button.tags-close"), "close", 18);
      this.closeButton.title = t("close_ui");
      this.closeButton.setAttribute("aria-label", t("close_ui"));
      this.closeQuestion = el("p", {text: t("discard_question_ui")});
      this.discardButton = button(t("discard_ui"), () => this.close(), "danger.tags-discard-confirm");
      this.confirmClose = el("div.tags-discard", {hidden: true, role: "alert"},
        this.closeQuestion, el("div.tags-actions", {},
          button(t("keep_editing_ui"), () => { this.confirmClose.hidden = true; this.closeButton.focus(); }),
          this.discardButton));
      this.dialog = el("section.tags-dialog", {role: "dialog", "aria-modal": "true", "aria-label": t("title_ui")},
        el("header.tags-heading", {}, el("div", {}, el("h2", {text: t("title_ui")}),
          el("p.tags-caption", {text: [album.artist, album.name].filter(Boolean).join(" / ")})), this.closeButton),
        this.progress, this.confirmClose, this.body, this.status);
      this.veil = el("div.veil.tags-veil", {onmousedown: event => {
        if (event.target === this.veil) this.requestClose();
      }}, this.dialog);
    }

    async mount() {
      document.getElementById("dialog-root").appendChild(this.veil);
      document.addEventListener("keydown", this.keyHandler, true);
      window.addEventListener("beforeunload", this.unloadHandler);
      this.closeButton.focus();
      try {
        const [snapshot, capabilities] = await Promise.all([
          App.api.get("/api/tags/album", {id: this.album.id}), App.api.get("/api/tags/status")]);
        if (!this.alive()) return;
        this.snapshot = snapshot;
        this.capabilities = capabilities;
        state.fields = capabilities.fields;
        this.textLimit = capabilities.limits && capabilities.limits.text || 500;
        this.tracks = snapshot.tracks.map(track => ({...track, tags: copyTags(track.tags)}));
        this.original = new Map(this.tracks.map(track => [track.id, copyTags(track.tags)]));
        this.render();
      } catch (error) {
        if (!this.alive()) return;
        App.clear(this.body).appendChild(button(t("retry_ui"), () => this.loadAgain()));
        this.message(App.errorText(error), true);
      }
    }

    alive() { return this.veil.isConnected; }
    loadAgain() { this.close(); open(this.album, this.onSaved); }
    dirty() { return !!(this.tracks && this.patch().tracks.length || this.commonTouched.size); }

    requestClose() {
      if (this.saving || this.busy && this.operationId && !this.operationComplete) {
        this.message(t("saving_wait_ui")); return;
      }
      if (this.dirty() && !this.operationComplete) {
        this.closeQuestion.textContent = t(this.operationId ? "close_operation_ui" : "discard_question_ui");
        this.discardButton.textContent = t(this.operationId ? "close_ui" : "discard_ui");
        this.confirmClose.hidden = false;
        this.confirmClose.querySelector("button").focus();
      } else this.close();
    }

    close() {
      this.generation++; this.sourceGeneration++;
      clearTimeout(this.pollTimer);
      this.veil.remove();
      document.removeEventListener("keydown", this.keyHandler, true);
      window.removeEventListener("beforeunload", this.unloadHandler);
      if (state.current === this) state.current = null;
      if (this.previouslyFocused && this.previouslyFocused.isConnected) this.previouslyFocused.focus();
    }

    keydown(event) {
      if (event.key === "Escape") {
        event.preventDefault(); event.stopImmediatePropagation();
        if (!this.confirmClose.hidden) this.confirmClose.hidden = true;
        else this.requestClose();
      } else if (event.key === "Tab") {
        const focusable = [...this.dialog.querySelectorAll("button, input, select, a[href], summary")]
          .filter(node => {
            const collapsed = node.closest("details:not([open])");
            return !node.disabled && !node.closest("[hidden]") && !node.closest("fieldset:disabled") &&
              (!collapsed || collapsed.firstElementChild === node);
          });
        const first = focusable[0], last = focusable[focusable.length - 1];
        if (event.shiftKey && (document.activeElement === first || !this.dialog.contains(document.activeElement))) {
          event.preventDefault(); if (last) last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault(); if (first) first.focus();
        }
      }
    }

    message(text, error = false) {
      this.status.textContent = text;
      this.status.classList.toggle("page-error", error);
      this.status.setAttribute("role", error ? "alert" : "status");
    }

    showProgress(label, help, completed = null, total = null) {
      this.progress.hidden = false;
      this.progressLabel.textContent = label;
      this.progressHelp.textContent = help;
      this.progressBar.hidden = false;
      this.progressBar.setAttribute("aria-label", label);
      this.progressBar.setAttribute("aria-valuetext", label);
      if (Number.isInteger(completed) && Number.isInteger(total) && total > 0) {
        this.progressBar.max = total;
        this.progressBar.value = completed;
      } else this.progressBar.removeAttribute("value");
    }

    writingProgress(operation) {
      const preparing = operation.phase === "preparing";
      const label = t(preparing ? "preparing_ui" : "saving_ui", operation);
      this.showProgress(label, t(preparing ? "preparing_help_ui" : "saving_help_ui"), operation.completed, operation.total);
      this.message(label);
    }

    patch() {
      return {albumId: this.snapshot.albumId, revision: this.snapshot.revision,
        tracks: this.tracks.filter(track => track.editable).map(track => {
          const before = this.original.get(track.id);
          return {id: track.id, changes: Object.fromEntries(state.fields.filter(key => track.tags[key] !== before[key])
            .map(key => [key, track.tags[key]]))};
        }).filter(track => Object.keys(track.changes).length)};
    }
  }

  return {el, t, button, copyTags, fieldLabel, sourceStyles, COMMON, TRACK_FIELDS, SOURCE_TRACK_FIELDS, POLL_INTERVAL, state, Editor};
})();
