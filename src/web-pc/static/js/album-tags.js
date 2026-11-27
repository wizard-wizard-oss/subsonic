"use strict";
/* Édition des tags : brouillon local, comparaison validée par le serveur, puis écriture et suivi séparé du scan. */
const AlbumTagsEditor = (() => {
  const el = App.el, t = (key, params) => App.t("tags." + key, params);
  let FIELDS = [];   // liste des champs envoyée par le serveur (/api/tags/status), jamais recopiée ici
  const COMMON = ["albumArtist", "artist", "album", "year"];
  const TRACK_FIELDS = ["disc", "track", "title", "artist", "genre"];
  const SOURCE_TRACK_FIELDS = new Set(["title", "artist", "track", "disc"]);
  const POLL_INTERVAL = 1000;
  let current = null;

  const button = (text, run, className = "") => el("button" + (className ? "." + className : ""),
    {type: "button", text, onclick: run});
  const copyTags = tags => Object.fromEntries(FIELDS.map(key => [key, String(tags[key] ?? "")]));
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
      this.keyHandler = event => this.keydown(event);
      this.unloadHandler = event => {
        if (this.dirty() || this.saving || this.operationId && !this.operationComplete) {
          event.preventDefault(); event.returnValue = "";
        }
      };
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
        FIELDS = capabilities.fields;
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
      if (current === this) current = null;
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
          return {id: track.id, changes: Object.fromEntries(FIELDS.filter(key => track.tags[key] !== before[key])
            .map(key => [key, track.tags[key]]))};
        }).filter(track => Object.keys(track.changes).length)};
    }

    render() {
      this.scope = el("select.tags-scope", {"aria-label": t("scope_ui")},
        [["all", "scope_all_ui"], ["selection", "scope_selection_ui"], ["missing", "scope_missing_ui"]]
          .map(([value, key]) => el("option", {value, text: t(key)})));
      this.count = el("strong.tags-change-count");
      this.selectionCount = el("span.tags-caption");
      this.styleScope = el("span.tags-caption.tags-style-scope");
      this.scope.addEventListener("change", () => this.updateStyleScope());
      this.review = button(t("review_ui"), () => this.preview(), "primary.tags-review");
      this.resetButton = button(t("reset_ui"), () => this.reset(), "link-button.tags-reset");
      this.draftHelp = el("p.tags-caption.tags-draft-help", {text: t("draft_help_ui")});
      this.diff = el("section.tags-preview", {hidden: true, "aria-label": t("review_title_ui")});
      const advanced = el("details.tags-advanced", {}, el("summary", {text: t("advanced_ui")}),
        el("div.tags-section-heading", {}, el("h3", {text: t("common_ui")}),
          el("label.tags-scope-label", {}, el("span", {text: t("scope_ui")}), this.scope)),
        el("div.tags-common", {}, COMMON.map(key => this.renderCommon(key))),
        el("p.tags-caption", {text: t("artists_help_ui")}),
        el("div.tags-section-heading", {}, el("h3", {text: t("tracks_ui")}), this.selectionCount), this.renderTracks());
      this.form = el("fieldset.tags-edit-fields", {},
        el("section.tags-primary-style", {"aria-label": t("album_style_ui")},
          el("div.tags-section-heading", {}, el("h3", {text: t("album_style_ui")}), this.styleScope),
          this.renderCommon("genre")), this.renderSource(), advanced,
        el("div.tags-footer", {}, el("div.tags-draft-summary", {}, this.count, this.draftHelp),
          el("div.tags-actions", {}, this.resetButton, this.review)));
      App.append(App.clear(this.body), [el("p.tags-caption", {text: t("folders_help_ui")}),
        ...(this.snapshot.warnings || []).map(key => el("p.tags-caption", {text: App.t(key)})), this.form, this.diff]);
      this.update();
      if (!this.capabilities.writable || !this.tracks.some(track => track.editable)) {
        this.form.disabled = true; this.message(t("readonly_ui"));
      }
    }

    renderCommon(key) {
      const input = el("input.tags-common-input", {type: "text", maxLength: this.textLimit,
        id: "tags-common-" + key,
        dataset: {field: key}, "aria-label": fieldLabel(key),
        oninput: () => { this.commonTouched.add(key); this.confirmClose.hidden = true; }});
      this.commonInputs.set(key, input);
      const state = el("span.tags-caption", {dataset: {commonState: key}});
      return el("div.tags-common-field", {},
        el("div.tags-field-heading", {}, el("label", {htmlFor: input.id,
          text: key === "artist" ? t("track_artists_ui") : fieldLabel(key)}), state),
        el("div.tags-common-controls", {}, input,
          button(t("apply_ui"), () => this.applyCommon(key), "tags-apply"),
          button(t("clear_ui"), () => this.applyCommon(key, true), "link-button.tags-clear")));
    }

    renderTracks() {
      this.selectAll = el("input", {type: "checkbox", "aria-label": t("select_all_ui"), onchange: () => {
        this.selected = new Set(this.selectAll.checked ? this.tracks.filter(track => track.editable).map(track => track.id) : []);
        this.rowInputs.filter(item => item.key === "selected").forEach(({track, input}) => { input.checked = this.selected.has(track.id); });
        this.update();
      }});
      return el("div.tags-table-wrap", {}, el("table.tags-table", {},
        el("thead", {}, el("tr", {}, el("th.tags-select", {scope: "col"}, this.selectAll),
          TRACK_FIELDS.map(key => el("th" + (["disc", "track"].includes(key) ? ".tags-number" : ""),
            {scope: "col", text: fieldLabel(key)})))),
        el("tbody", {}, this.tracks.map((track, index) => {
          const selected = el("input", {type: "checkbox", disabled: !track.editable,
            "aria-label": t("select_track_ui", {number: index + 1}), onchange: () => {
              if (selected.checked) this.selected.add(track.id); else this.selected.delete(track.id); this.update();
            }});
          this.rowInputs.push({track, key: "selected", input: selected});
          return el("tr", {dataset: {trackId: track.id}}, el("td", {}, selected), TRACK_FIELDS.map(key => {
            const input = el("input", {type: "text", value: track.tags[key], disabled: !track.editable,
              maxLength: this.textLimit, inputMode: ["disc", "track"].includes(key) ? "numeric" : "text",
              "aria-label": t("track_field_ui", {field: fieldLabel(key), number: index + 1}),
              dataset: {field: key}, oninput: () => { track.tags[key] = input.value; this.changed(); }});
            this.rowInputs.push({track, key, input});
            return el("td", {}, input, key === "title" && !track.editable ?
              el("small.tags-caption", {text: track.reason ? App.t(track.reason) : t("unsupported_ui", {format: track.format})}) : null);
          }));
        }))));
    }

    refreshCommon(force = false) {
      for (const [key, input] of this.commonInputs) {
        const values = [...new Set(this.tracks.filter(track => track.editable).map(track => track.tags[key]))];
        const mixed = values.length > 1;
        this.body.querySelector('[data-common-state="' + key + '"]').textContent = t(mixed ? "mixed_ui" : "common_value_ui");
        input.placeholder = t(mixed ? "mixed_ui" : "empty_ui");
        if (force || !this.commonTouched.has(key)) input.value = mixed ? "" : values[0] || "";
      }
    }

    update() {
      const tracks = this.patch().tracks;
      const fields = tracks.reduce((count, track) => count + Object.keys(track.changes).length, 0);
      this.count.textContent = tracks.length ? App.plural("tags.changed_tracks_ui", tracks.length) + " · " +
        App.plural("tags.changed_fields_ui", fields) : t("unchanged_ui");
      this.selectionCount.textContent = App.plural("tags.selection_ui", this.selected.size);
      this.updateStyleScope();
      const editableCount = this.tracks.filter(track => track.editable).length;
      this.selectAll.checked = editableCount > 0 && this.selected.size === editableCount;
      this.selectAll.indeterminate = this.selected.size > 0 && this.selected.size < editableCount;
      this.review.disabled = !tracks.length;
      this.draftHelp.hidden = !tracks.length;
      this.rowInputs.filter(item => item.key !== "selected").forEach(({track, key, input}) => {
        input.classList.toggle("tags-changed", track.tags[key] !== this.original.get(track.id)[key]);
      });
      this.refreshCommon();
    }

    updateStyleScope() {
      const labels = {all: "scope_all_ui", selection: "scope_selection_ui", missing: "scope_missing_ui"};
      this.styleScope.textContent = t(labels[this.scope.value]);
    }

    syncInputs() {
      this.rowInputs.filter(item => item.key !== "selected").forEach(({track, key, input}) => { input.value = track.tags[key]; });
    }

    changed() {
      this.generation++; this.previewBody = null; this.diff.hidden = true;
      this.confirmClose.hidden = true; this.message(""); this.update();
    }

    applyCommon(key, clear = false) {
      const value = clear ? "" : this.commonInputs.get(key).value.trim();
      if (!clear && !value) { this.message(t("value_required_ui"), true); return; }
      this.applyValue(key, value, this.scope.value);
    }

    applyValue(key, value, scope) {
      if (scope === "selection" && !this.selected.size) { this.message(t("select_first_ui"), true); return; }
      this.tracks.filter(track => track.editable).forEach(track => {
        if (scope === "selection" && !this.selected.has(track.id)) return;
        if (scope === "missing" && track.tags[key].trim()) return;
        track.tags[key] = value;
      });
      this.commonTouched.delete(key); this.syncInputs(); this.changed();
    }

    reset() {
      this.tracks.forEach(track => { track.tags = copyTags(this.original.get(track.id)); });
      this.commonTouched.clear(); this.syncInputs(); this.refreshCommon(true); this.changed();
    }

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
    }

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
    }

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
    }

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

    renderSource() {
      this.searchPanel = el("section.tags-search", {hidden: true, "aria-label": t("search_title_ui")});
      this.sourceResults = el("div.tags-source-results");
      this.sourceStatus = el("p.tags-caption", {role: "status", "aria-live": "polite"});
      this.source = el("select.tags-source", {"aria-label": t("source_ui")},
        [["discogs", "Discogs"], ["musicbrainz", "MusicBrainz"]].map(([value, name]) =>
          el("option", {value, text: name, disabled: !this.capabilities.providers[value]})));
      this.source.value = this.capabilities.providers.discogs ? "discogs" : "musicbrainz";
      const first = this.tracks.find(track => track.editable) || this.tracks[0];
      const initialTags = first ? first.tags : {};
      this.searchArtist = el("input.tags-search-artist", {value: initialTags.albumArtist || initialTags.artist || this.snapshot.artist || "",
        maxLength: 300, "aria-label": t("search_artist_ui")});
      this.searchAlbum = el("input.tags-search-album", {value: initialTags.album || this.snapshot.name || "",
        maxLength: 300, "aria-label": t("album_label_ui")});
      const enabled = Object.values(this.capabilities.providers).some(Boolean);
      this.searchButton = button(t("search_ui"), () => this.search(), "tags-search-submit");
      this.searchButton.disabled = !enabled;
      this.source.addEventListener("change", () => {
        this.sourceGeneration++; this.sourceResults.replaceChildren(); this.sourceStatus.textContent = "";
      });
      [this.searchArtist, this.searchAlbum].forEach(input => input.addEventListener("keydown", event => {
        if (event.key === "Enter") { event.preventDefault(); this.search(); }
      }));
      this.searchPanel.append(el("div.tags-search-controls", {},
        el("label", {}, el("span", {text: t("source_ui")}), this.source),
        el("label", {}, el("span", {text: t("search_artist_ui")}), this.searchArtist),
        el("label", {}, el("span", {text: t("album_label_ui")}), this.searchAlbum), this.searchButton),
        this.sourceStatus, this.sourceResults);
      return el("div", {}, el("div.tags-section-heading", {},
        button(t("find_style_ui"), () => {
          this.searchPanel.hidden = !this.searchPanel.hidden;
          if (!this.searchPanel.hidden) this.searchArtist.focus();
        }, "tags-source-toggle")), this.searchPanel,
        !enabled ? el("p.tags-caption", {text: t("sources_off_ui")}) : null);
    }

    async search() {
      if (!this.searchArtist.value.trim() || !this.searchAlbum.value.trim()) {
        this.sourceStatus.textContent = t("search_terms_ui"); return;
      }
      const generation = ++this.sourceGeneration, source = this.source.value;
      this.sourceResults.replaceChildren(); this.sourceStatus.textContent = t("searching_ui");
      this.searchButton.disabled = true;
      try {
        const result = await App.api.get("/api/tags/search", {id: this.snapshot.albumId, source,
          artist: this.searchArtist.value.trim(), album: this.searchAlbum.value.trim()});
        if (!this.alive() || generation !== this.sourceGeneration) return;
        this.sourceStatus.textContent = result.candidates.length ? t("choose_edition_ui") : t("no_candidates_ui");
        const releasePanel = el("div.tags-release");
        const candidates = el("div.tags-edition-results", {role: "group", "aria-label": t("edition_ui")},
          result.candidates.map(candidate => {
            const coverUrl = typeof candidate.coverUrl === "string" &&
              /^https:\/\/i\.discogs\.com\//.test(candidate.coverUrl) ? candidate.coverUrl : "";
            const metadata = [candidate.artist, candidate.date, candidate.country, candidate.format,
              Number(candidate.trackCount) > 0 ? App.plural("tags.source_track_count_ui", candidate.trackCount) : ""];
            const styles = sourceStyles(candidate);
            return el("button.tags-edition-result", {type: "button", "aria-pressed": "false", dataset: {releaseId: candidate.id},
              onclick: event => {
                candidates.querySelectorAll("button").forEach(node => node.setAttribute("aria-pressed", String(node === event.currentTarget)));
                this.loadRelease(source, candidate.id, releasePanel);
              }},
              coverUrl ? el("img.tags-edition-cover", {src: coverUrl, alt: "", loading: "lazy", referrerPolicy: "no-referrer",
                onerror: event => { event.currentTarget.hidden = true; }}) : null,
              el("span.tags-edition-copy", {}, el("strong", {text: candidate.title}),
                el("span.tags-caption", {text: metadata.filter(Boolean).join(" · ")}),
                styles.length ? el("span.tags-edition-styles", {text: styles.join(" · ")}) : null));
          }));
        this.sourceResults.append(candidates, releasePanel);
      } catch (error) {
        if (this.alive() && generation === this.sourceGeneration) this.sourceStatus.textContent = App.errorText(error);
      } finally { if (this.alive()) this.searchButton.disabled = false; }
    }

    async loadRelease(source, id, panel) {
      const generation = ++this.sourceGeneration;
      panel.replaceChildren(el("p.tags-caption", {text: t("loading_release_ui")}));
      try {
        const release = await App.api.get("/api/tags/release", {id: this.snapshot.albumId, source, release: id});
        if (!this.alive() || generation !== this.sourceGeneration) return;
        this.renderRelease(release, panel);
        this.sourceStatus.textContent = t("edition_selected_ui", {title: release.title});
        panel.scrollIntoView({block: "nearest"});
      } catch (error) {
        if (this.alive() && generation === this.sourceGeneration) panel.replaceChildren(el("p.page-error", {text: App.errorText(error)}));
      }
    }

    renderRelease(release, panel) {
      const tracks = this.tracks.filter(track => track.editable), mapping = new Map(), checks = new Map();
      const sameCount = tracks.length === release.tracks.length;
      const styles = this.renderSourceStyles(release);
      const selectedFields = () => [...checks].filter(([, input]) => input.checked).map(([key]) => key);
      const needsMapping = () => selectedFields().some(key => SOURCE_TRACK_FIELDS.has(key));
      const validMapping = () => {
        const values = [...mapping.values()].map(select => select.value);
        return !values.some(value => value === "") && new Set(values).size === values.length;
      };
      const importButton = button(t("import_ui"), () => {
        if (needsMapping() && !validMapping()) {
          this.sourceStatus.textContent = t("mapping_required_ui"); return;
        }
        const fields = selectedFields();
        if (!fields.length) { this.sourceStatus.textContent = t("choose_fields_ui"); return; }
        tracks.forEach(track => {
          const proposed = needsMapping() ? release.tracks[Number(mapping.get(track.id).value)] : {};
          const values = {title: proposed.title, artist: proposed.artist, albumArtist: release.artist, album: release.title,
            year: release.year, genre: styles.selected(), track: proposed.track, disc: proposed.disc};
          fields.forEach(key => {
            // Une donnée absente chez le fournisseur ne doit pas effacer les tags existants.
            if (values[key] !== undefined && values[key] !== null && String(values[key]).trim()) track.tags[key] = String(values[key]);
          });
        });
        this.syncInputs(); this.changed(); this.sourceStatus.textContent = t("imported_ui");
      }, "tags-import");
      const updateMapping = () => {
        importButton.disabled = !selectedFields().length || needsMapping() && !validMapping();
        mappingPanel.hidden = !needsMapping();
      };
      const suggestions = Array.isArray(release.mapping) ? release.mapping : [];
      const localIndexes = new Map(this.tracks.map((track, index) => [track.id, index]));
      const occurrences = new Map();
      suggestions.forEach(index => {
        if (Number.isInteger(index) && index >= 0 && index < release.tracks.length) {
          occurrences.set(index, (occurrences.get(index) || 0) + 1);
        }
      });
      const rows = tracks.map(track => {
        const select = el("select", {"aria-label": t("mapping_track_ui", {title: track.tags.title}), onchange: updateMapping},
          el("option", {value: "", text: t("mapping_choose_ui")}), release.tracks.map((proposed, position) =>
            el("option", {value: String(position), text: [proposed.position || proposed.track, proposed.title,
              proposed.artist, proposed.duration ? App.duration(proposed.duration) : ""].filter(Boolean).join(" · ")})));
        const proposedIndex = suggestions[localIndexes.get(track.id)];
        if (Number.isInteger(proposedIndex) && proposedIndex >= 0 && proposedIndex < release.tracks.length &&
            occurrences.get(proposedIndex) === 1) select.value = String(proposedIndex);
        mapping.set(track.id, select);
        return el("tr", {}, el("td", {}, el("strong", {text: track.tags.title}),
          el("small.tags-caption", {text: [track.tags.disc, track.tags.track, track.duration ? App.duration(track.duration) : ""].filter(Boolean).join(" · ")})),
          el("td", {}, select));
      });
      const choices = FIELDS.map(key => {
        const input = el("input", {type: "checkbox", checked: ["title", "track", "disc", "year"].includes(key),
          disabled: key === "genre" && !styles.selected(), dataset: {importField: key}, onchange: updateMapping});
        checks.set(key, input);
        return el("label", {}, input, fieldLabel(key));
      });
      const mappingPanel = el("div.tags-mapping-panel", {},
        el("p.tags-caption", {text: t(sameCount ? "mapping_check_ui" : "mapping_mismatch_ui",
        {local: tracks.length, proposed: release.tracks.length})}),
        el("div.tags-table-wrap", {}, el("table.tags-mapping", {},
          el("thead", {}, el("tr", {}, el("th", {scope: "col", text: t("local_track_ui")}),
            el("th", {scope: "col", text: t("proposed_track_ui")}))), el("tbody", {}, rows))));
      panel.replaceChildren(el("div.tags-chosen-edition", {}, el("strong", {text: release.title}),
        el("p.tags-caption", {text: [release.artist, release.date || release.year, release.country, release.format].filter(Boolean).join(" · ")})),
        styles.element,
        el("details.tags-source-advanced", {}, el("summary", {text: t("source_advanced_ui")}),
          el("fieldset.tags-import-fields", {}, el("legend", {text: t("import_fields_ui")}), choices), mappingPanel, importButton));
      updateMapping();
    }

    renderSourceStyles(release) {
      const suggestions = sourceStyles(release);
      const source = release.source === "discogs" ? "Discogs" : "MusicBrainz";
      if (!suggestions.length) return {
        element: el("section.tags-source-styles", {}, el("h3", {text: t("source_styles_ui", {source})}),
          el("p.tags-no-styles", {text: t("no_styles_ui", {source})})), selected: () => ""};
      const radios = suggestions.map((value, index) => el("input", {
        type: "radio", name: "tags-source-style", value, checked: index === 0}));
      const selected = () => radios.find(input => input.checked).value;
      const useStyle = button(t("use_style_ui"), () => {
        this.scope.value = "all";
        this.applyValue("genre", selected(), "all");
        this.sourceStatus.textContent = t("style_imported_ui", {style: selected()});
      }, "tags-use-style");
      return {element: el("section.tags-source-styles", {}, el("h3", {text: t("source_styles_ui", {source})}),
        el("fieldset.tags-style-options", {}, el("legend", {text: t("choose_style_ui")}),
          suggestions.map((value, index) => el("label", {}, radios[index], value))), useStyle), selected};
    }
  }

  function open(album, onSaved) {
    if (!App.can("coverArt")) return;
    if (current) { current.requestClose(); return; }
    current = new Editor(album, onSaved); current.mount();
  }

  return {open, destroy: () => { if (current) current.close(); }};
})();
