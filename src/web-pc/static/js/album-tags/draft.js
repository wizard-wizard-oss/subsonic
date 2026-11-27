"use strict";
/* Éditeur de tags — Brouillon : champs communs, pistes, application et annulation des changements. */
(() => {
  const {el, t, button, copyTags, fieldLabel, sourceStyles, COMMON, TRACK_FIELDS, SOURCE_TRACK_FIELDS, POLL_INTERVAL, state} = AlbumTags;
  Object.assign(AlbumTags.Editor.prototype, {
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
    },

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
    },

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
    },

    refreshCommon(force = false) {
      for (const [key, input] of this.commonInputs) {
        const values = [...new Set(this.tracks.filter(track => track.editable).map(track => track.tags[key]))];
        const mixed = values.length > 1;
        this.body.querySelector('[data-common-state="' + key + '"]').textContent = t(mixed ? "mixed_ui" : "common_value_ui");
        input.placeholder = t(mixed ? "mixed_ui" : "empty_ui");
        if (force || !this.commonTouched.has(key)) input.value = mixed ? "" : values[0] || "";
      }
    },

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
    },

    updateStyleScope() {
      const labels = {all: "scope_all_ui", selection: "scope_selection_ui", missing: "scope_missing_ui"};
      this.styleScope.textContent = t(labels[this.scope.value]);
    },

    syncInputs() {
      this.rowInputs.filter(item => item.key !== "selected").forEach(({track, key, input}) => { input.value = track.tags[key]; });
    },

    changed() {
      this.generation++; this.previewBody = null; this.diff.hidden = true;
      this.confirmClose.hidden = true; this.message(""); this.update();
    },

    applyCommon(key, clear = false) {
      const value = clear ? "" : this.commonInputs.get(key).value.trim();
      if (!clear && !value) { this.message(t("value_required_ui"), true); return; }
      this.applyValue(key, value, this.scope.value);
    },

    applyValue(key, value, scope) {
      if (scope === "selection" && !this.selected.size) { this.message(t("select_first_ui"), true); return; }
      this.tracks.filter(track => track.editable).forEach(track => {
        if (scope === "selection" && !this.selected.has(track.id)) return;
        if (scope === "missing" && track.tags[key].trim()) return;
        track.tags[key] = value;
      });
      this.commonTouched.delete(key); this.syncInputs(); this.changed();
    },

    reset() {
      this.tracks.forEach(track => { track.tags = copyTags(this.original.get(track.id)); });
      this.commonTouched.clear(); this.syncInputs(); this.refreshCommon(true); this.changed();
    }
  });
})();
