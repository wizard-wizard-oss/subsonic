"use strict";
/* Éditeur de tags — Vérification par le serveur, enregistrement dans les fichiers et suivi de l'opération. */
(() => {
  const {el, t, button, copyTags, fieldLabel, sourceStyles, COMMON, TRACK_FIELDS, SOURCE_TRACK_FIELDS, POLL_INTERVAL, state} = AlbumTags;
  Object.assign(AlbumTags.Editor.prototype, {
    async preview() {
      if (this.busy || this.operationId) return;
      const body = this.patch();
      if (!body.tracks.length) return;
      this.busy = true; this.form.disabled = true; this.message(t("checking_ui"));
      const generation = ++this.generation;
      try {
        const result = await App.api.post("/api/tags/preview", body);
        if (!this.alive() || generation !== this.generation) return;
        this.previewBody = body;
        this.diff.replaceChildren(el("h3", {text: t("review_title_ui")}),
          el("p.tags-caption.tags-save-help", {text: t("save_help_ui")}),
          ...result.changes.map(change => el("div.tags-diff-row", {},
            el("strong", {text: t("diff_field_ui", {title: change.title, field: fieldLabel(change.field)})}),
            el("p", {}, el("del", {text: change.before || t("empty_ui")}), " → ",
              el("span", {text: change.after || t("cleared_ui")})))),
          el("div.tags-actions", {}, button(t("back_ui"), () => { this.diff.hidden = true; this.review.focus(); }),
            button(t("save_ui"), () => this.save(), "primary.tags-save")));
        this.diff.hidden = false; this.message(""); this.diff.querySelector(".tags-save").focus();
      } catch (error) { if (this.alive()) this.message(App.errorText(error), true); }
      finally { if (this.alive()) { this.busy = false; this.form.disabled = !this.capabilities.writable; } }
    },

    async save() {
      if (this.busy || !this.previewBody || this.operationId) return;
      this.busy = true; this.saving = true; this.form.disabled = true;
      this.diff.querySelectorAll("button").forEach(node => { node.disabled = true; });
      this.diff.hidden = true;
      this.showProgress(t("save_starting_ui"), t("preparing_help_ui"));
      this.message(t("save_starting_ui"));
      this.progress.scrollIntoView({block: "nearest"});
      try {
        const result = await App.api.post("/api/tags/save", this.previewBody);
        if (!this.alive()) return;
        this.operationId = result.operationId;
        this.saving = false;
        this.diff.hidden = true;
        this.pollOperation();
      } catch (error) {
        if (!this.alive()) return;
        this.busy = false; this.saving = false; this.form.disabled = false;
        this.progress.hidden = true; this.diff.hidden = false;
        this.diff.querySelectorAll("button").forEach(node => { node.disabled = false; });
        this.message(App.errorText(error), true);
        this.status.focus();
      }
    },

    async pollOperation() {
      if (!this.alive()) return;
      try {
        const operation = await App.api.get("/api/tags/operation", {id: this.operationId});
        if (!this.alive()) return;
        if (operation.state === "failed") {
          this.busy = false; this.operationId = null; this.form.disabled = false;
          this.progress.hidden = true;
          this.message(operation.error ? App.t(operation.error) : t("operation_failed_ui"), true);
          this.status.focus(); return;
        }
        if (operation.state === "saved") {
          if (!this.operationComplete) {
            this.operationComplete = true; this.busy = false; this.commonTouched.clear();
            this.tracks.forEach(track => this.original.set(track.id, copyTags(track.tags)));
            this.update();
          }
          const scanKey = {pending: "scan_pending_ui", started: "scan_started_ui", updated: "scan_updated_ui", failed: "scan_failed_ui"};
          this.showProgress(t(scanKey[operation.scan] || "scan_pending_ui"),
            t(operation.scan === "updated" || operation.scan === "failed" ? "saved_ui" : "scan_help_ui"),
            operation.scan === "updated" ? operation.total : null, operation.total);
          this.progressBar.hidden = operation.scan === "failed";
          this.message(t("saved_ui") + " " + t(scanKey[operation.scan] || "scan_pending_ui"));
          if (operation.warnings && operation.warnings.length) {
            this.message(this.status.textContent + " " + operation.warnings.map(key => App.t(key)).join(" "));
          }
          if (["updated", "failed"].includes(operation.scan)) {
            if (operation.scan === "updated" && this.onSaved) this.onSaved();
            this.closeButton.focus(); return;
          }
        } else this.writingProgress(operation);
        this.pollTimer = setTimeout(() => this.pollOperation(), POLL_INTERVAL);
      } catch (error) { if (this.alive()) this.retryOperation(App.errorText(error)); }
    },

    retryOperation(message) {
      this.busy = false;
      this.progress.hidden = true;
      this.message((this.operationComplete ? t("saved_ui") + " " + t("scan_unconfirmed_ui") + " " : "") + message);
      this.diff.replaceChildren(button(t("poll_retry_ui"), () => {
        this.busy = true; this.diff.hidden = true;
        this.showProgress(t("poll_resuming_ui"), t("poll_resuming_help_ui"));
        this.pollOperation();
      }, "tags-poll-retry"));
      this.diff.hidden = false;
      this.diff.querySelector("button").focus();
    }
  });
})();
