"use strict";
/* Éditeur de tags — Sources MusicBrainz et Discogs : recherche, édition choisie et import dans le brouillon. */
(() => {
  const {el, t, button, copyTags, fieldLabel, sourceStyles, COMMON, TRACK_FIELDS, SOURCE_TRACK_FIELDS, POLL_INTERVAL, state} = AlbumTags;
  Object.assign(AlbumTags.Editor.prototype, {
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
    },

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
    },

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
    },

    /* Formulaire d'import d'une édition : champs cochés et correspondance pistes locales -> pistes proposées. */
    releaseForm(release) {
      const form = {release, tracks: this.tracks.filter(track => track.editable), mapping: new Map(), checks: new Map(),
                    styles: this.renderSourceStyles(release)};
      form.selectedFields = () => [...form.checks].filter(([, input]) => input.checked).map(([key]) => key);
      form.needsMapping = () => form.selectedFields().some(key => SOURCE_TRACK_FIELDS.has(key));
      form.validMapping = () => {
        const values = [...form.mapping.values()].map(select => select.value);
        return !values.some(value => value === "") && new Set(values).size === values.length;
      };
      form.update = () => {
        form.importButton.disabled = !form.selectedFields().length || form.needsMapping() && !form.validMapping();
        form.mappingPanel.hidden = !form.needsMapping();
      };
      return form;
    },

    importRelease(form) {
      const {release, tracks, mapping, styles} = form;
      if (form.needsMapping() && !form.validMapping()) { this.sourceStatus.textContent = t("mapping_required_ui"); return; }
      const fields = form.selectedFields();
      if (!fields.length) { this.sourceStatus.textContent = t("choose_fields_ui"); return; }
      tracks.forEach(track => {
        const proposed = form.needsMapping() ? release.tracks[Number(mapping.get(track.id).value)] : {};
        const values = {title: proposed.title, artist: proposed.artist, albumArtist: release.artist, album: release.title,
          year: release.year, genre: styles.selected(), track: proposed.track, disc: proposed.disc};
        fields.forEach(key => {
          // Une donnée absente chez le fournisseur ne doit pas effacer les tags existants.
          if (values[key] !== undefined && values[key] !== null && String(values[key]).trim()) track.tags[key] = String(values[key]);
        });
      });
      this.syncInputs(); this.changed(); this.sourceStatus.textContent = t("imported_ui");
    },

    mappingRows(form) {
      const {release, tracks, mapping} = form;
      const suggestions = Array.isArray(release.mapping) ? release.mapping : [];
      const localIndexes = new Map(this.tracks.map((track, index) => [track.id, index]));
      const valid = index => Number.isInteger(index) && index >= 0 && index < release.tracks.length;
      const occurrences = new Map();
      suggestions.filter(valid).forEach(index => occurrences.set(index, (occurrences.get(index) || 0) + 1));
      return tracks.map(track => {
        const select = el("select", {"aria-label": t("mapping_track_ui", {title: track.tags.title}), onchange: form.update},
          el("option", {value: "", text: t("mapping_choose_ui")}), release.tracks.map((proposed, position) =>
            el("option", {value: String(position), text: [proposed.position || proposed.track, proposed.title,
              proposed.artist, proposed.duration ? App.duration(proposed.duration) : ""].filter(Boolean).join(" · ")})));
        const proposedIndex = suggestions[localIndexes.get(track.id)];
        if (valid(proposedIndex) && occurrences.get(proposedIndex) === 1) select.value = String(proposedIndex);
        mapping.set(track.id, select);
        return el("tr", {}, el("td", {}, el("strong", {text: track.tags.title}),
          el("small.tags-caption", {text: [track.tags.disc, track.tags.track, track.duration ? App.duration(track.duration) : ""].filter(Boolean).join(" · ")})),
          el("td", {}, select));
      });
    },

    importChoices(form) {
      return state.fields.map(key => {
        const input = el("input", {type: "checkbox", checked: ["title", "track", "disc", "year"].includes(key),
          disabled: key === "genre" && !form.styles.selected(), dataset: {importField: key}, onchange: form.update});
        form.checks.set(key, input);
        return el("label", {}, input, fieldLabel(key));
      });
    },

    renderRelease(release, panel) {
      const form = this.releaseForm(release), sameCount = form.tracks.length === release.tracks.length;
      form.importButton = button(t("import_ui"), () => this.importRelease(form), "tags-import");
      const choices = this.importChoices(form);
      form.mappingPanel = el("div.tags-mapping-panel", {},
        el("p.tags-caption", {text: t(sameCount ? "mapping_check_ui" : "mapping_mismatch_ui",
          {local: form.tracks.length, proposed: release.tracks.length})}),
        el("div.tags-table-wrap", {}, el("table.tags-mapping", {},
          el("thead", {}, el("tr", {}, el("th", {scope: "col", text: t("local_track_ui")}),
            el("th", {scope: "col", text: t("proposed_track_ui")}))), el("tbody", {}, this.mappingRows(form)))));
      panel.replaceChildren(el("div.tags-chosen-edition", {}, el("strong", {text: release.title}),
        el("p.tags-caption", {text: [release.artist, release.date || release.year, release.country, release.format].filter(Boolean).join(" · ")})),
        form.styles.element,
        el("details.tags-source-advanced", {}, el("summary", {text: t("source_advanced_ui")}),
          el("fieldset.tags-import-fields", {}, el("legend", {text: t("import_fields_ui")}), choices), form.mappingPanel,
          form.importButton));
      form.update();
    },

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
  });
})();
