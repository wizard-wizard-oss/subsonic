"use strict";
/* Page « Envoyer » (#/upload) : des fichiers audio (ou des albums en zip) glissés ou choisis sont envoyés un par un au site,
   qui les range dans le dossier Incoming de Subsonic (un zip y est décompressé) ; à la fin, Subsonic est invité à scanner.
   Droit Subsonic « upload » requis. */

Views.upload = (() => {
  const el = App.el, t = App.t;
  const EXTENSIONS = ["mp3", "flac", "m4a", "aac", "ogg", "oga", "opus", "wav", "aiff", "aif"];
  const ZIP = "zip";
  const MAX_BYTES = 300 * 1024 * 1024;
  const MAX_ZIP_BYTES = 2000 * 1024 * 1024;

  /** Envoie un fichier (corps brut) avec sa progression ; erreur : l'Error porte la clé de texte du serveur. */
  function send(file, onProgress) {
    return new Promise((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", "/api/upload?" + new URLSearchParams({name: file.name}));
      request.setRequestHeader("X-Requested-With", "pmw");        // protection CSRF : demandé par le serveur
      request.upload.onprogress = e => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
      request.upload.onload = () => onProgress(1);                 // tout est parti : le serveur traite
      request.onerror = () => reject(new Error("upload.network"));
      request.onload = () => {
        let data = {};
        try { data = JSON.parse(request.responseText); } catch (e) { /* réponse vide */ }
        if (request.status === 401) App.onSessionLost();
        if (request.status >= 200 && request.status < 300) resolve(data);
        else reject(new Error(data.error || "server.error"));
      };
      request.send(file);
    });
  }

  /** « Décompressé : 12 fichiers — rangé dans Converge/Jane Doe — à ranger à la main dans Incoming : … » */
  function outcome(file, saved) {
    const parts = [file.name.toLowerCase().endsWith("." + ZIP) ? App.plural("upload.unzipped", saved.files) : t("upload.done")];
    if (saved.placed.length) parts.push(t("upload.placed", {where: saved.placed.join(", ")}));
    if (saved.waiting.length) parts.push(t("upload.left", {what: saved.waiting.join(", ")}));
    return parts.join(" — ");
  }

  function problem(file) {
    const extension = (file.name.split(".").pop() || "").toLowerCase();
    if (!EXTENSIONS.includes(extension) && extension !== ZIP) return "upload.bad_type";
    if (!file.size || file.size > (extension === ZIP ? MAX_ZIP_BYTES : MAX_BYTES)) return "upload.bad_size";
    return "";
  }

  /** Historique partagé, paginé sans perdre les anciens envois quand de nouveaux arrivent. */
  function history(main) {
    const body = el("tbody"), message = el("p.muted");
    const more = el("button", {text: t("upload.history_more"), hidden: true, onclick: () => load(false)});
    const headings = ["date", "person", "file", "count", "result"];
    const section = el("section.upload-history", {}, el("h2", {text: t("upload.history")}),
      el("div.upload-history-scroll", {}, el("table", {},
        el("thead", {}, el("tr", {}, ...headings.map(key => el("th", {scope: "col", text: t("upload.history_" + key)})))), body)),
      message, more);
    let before = null, generation = 0;
    async function load(reset) {
      const current = reset ? ++generation : generation;
      more.disabled = true;
      try {
        const data = await App.api.get("/api/upload/history" + (!reset && before ? "?before=" + before : ""));
        if (current !== generation || !section.isConnected) return;
        if (reset) App.clear(body);
        for (const entry of data.entries) {
          body.appendChild(el("tr", {},
            el("td", {text: App.fullDate(entry.uploadedAt)}), el("td", {text: entry.username}),
            el("td", {text: entry.filename}), el("td", {text: String(entry.files)}),
            el("td", {text: outcome({name: entry.filename}, entry)})));
        }
        before = data.before;
        more.hidden = !before;
        message.textContent = body.children.length ? "" : t("upload.history_empty");
      } catch (error) {
        if (current === generation && section.isConnected) message.textContent = App.errorText(error);
      } finally { if (current === generation) more.disabled = false; }
    }
    main.appendChild(section);
    load(true);
    return () => load(true);
  }

  return {
    async render(main, route) {
      if (!App.can("upload")) {
        App.clear(main).appendChild(el("h1", {text: t("upload.activity")}));
        this.refreshHistory = history(main);
        return;
      }
      let status;
      try {
        status = await App.api.get("/api/upload/status");
      } catch (error) {
        App.clear(main).appendChild(el("p.page-error", {text: App.errorText(error)}));
        return;
      }
      if (route.stale) return;
      App.clear(main);
      main.appendChild(el("h1", {text: t("upload.title")}));
      if (!status.enabled) {
        this.refreshHistory = history(main);
        main.appendChild(el("p.page-error", {text: t("upload." + status.reason)}));
        return;
      }
      this.rows = el("ul.upload-list");
      this.totalBar = el("progress", {max: 1, value: 0});
      this.totalLabel = el("span.upload-state");
      this.total = el("div.upload-total", {hidden: true}, el("strong", {text: t("upload.total")}), this.totalBar, this.totalLabel);
      this.summary = el("p.muted.upload-summary");
      this.input = el("input", {type: "file", multiple: true, hidden: true, accept: EXTENSIONS.concat(ZIP).map(e => "." + e).join(","),
                                onchange: () => { this.add(Array.from(this.input.files)); this.input.value = ""; }});
      const zone = el("div.upload-zone", {tabIndex: 0, role: "button", onclick: () => this.input.click(),
                                          onkeydown: e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); this.input.click(); } }},
        el("strong", {text: t("upload.drop")}), el("span.muted", {text: t("upload.formats")}));
      zone.addEventListener("dragover", e => { e.preventDefault(); zone.classList.add("drop-over"); });
      zone.addEventListener("dragleave", () => zone.classList.remove("drop-over"));
      zone.addEventListener("drop", e => {
        e.preventDefault();
        zone.classList.remove("drop-over");
        this.add(Array.from((e.dataTransfer && e.dataTransfer.files) || []));
      });
      this.queue = [];
      this.busy = false;
      this.batch = {files: 0, bytes: 0, doneFiles: 0, doneBytes: 0};
      App.append(main, [el("p.muted", {text: t("upload.intro", {folder: status.folder})}), zone, this.input, this.total,
                        this.rows, this.summary]);
      this.refreshHistory = history(main);
    },

    add(files) {
      for (const file of files) {
        const bad = problem(file);
        const bar = el("progress", {max: 1, value: 0});
        const state = el("span.upload-state", {text: bad ? t(bad) : t("upload.waiting")});
        const row = el("li.upload-row" + (bad ? ".failed" : ""), {}, el("span.upload-name", {text: file.name}), bar, state);
        this.rows.appendChild(row);
        if (bad) continue;
        this.queue.push({file, bar, state, row});
        this.batch.files++;
        this.batch.bytes += file.size;
      }
      this.run();
    },

    /** Barre du lot entier : octets envoyés sur le total, et « fichier 2 sur 5 ». */
    showTotal(currentBytes) {
      const {files, bytes, doneFiles, doneBytes} = this.batch;
      this.total.hidden = !files;
      this.totalBar.value = bytes ? (doneBytes + currentBytes) / bytes : 0;
      this.totalLabel.textContent = t("upload.total_state", {current: Math.min(doneFiles + 1, files), count: files,
                                                             percent: Math.floor(this.totalBar.value * 100)});
    },

    /** Un fichier à la fois (le serveur écrit sur disque), puis un seul scan pour tout le lot. Chaque fichier : barre de
        l'envoi, puis barre animée pendant que le serveur décompresse et range (il ne dit pas où il en est). */
    async run() {
      if (this.busy) return;
      this.busy = true;
      let sent = 0;
      while (this.queue.length) {
        const {file, bar, state, row} = this.queue.shift();
        state.textContent = t("upload.sending");
        this.showTotal(0);
        try {
          const saved = await send(file, ratio => {
            bar.value = ratio;
            this.showTotal(ratio * file.size);
            if (ratio >= 1) {
              bar.removeAttribute("value");                          // barre animée : le serveur travaille
              state.textContent = t(file.name.toLowerCase().endsWith("." + ZIP) ? "upload.unpacking" : "upload.saving");
            }
          });
          bar.value = 1;
          state.textContent = outcome(file, saved);
          row.classList.add("done");
          sent += saved.files;
        } catch (error) {
          bar.value = 0;
          row.classList.add("failed");
          state.textContent = t(error.message);
        }
        this.batch.doneFiles++;
        this.batch.doneBytes += file.size;
        this.showTotal(0);
      }
      this.busy = false;
      this.totalLabel.textContent = t("upload.total_done");
      if (!sent) return;
      await this.refreshHistory();
      try {
        const scanning = (await App.api.post("/api/upload/finish", {})).scanning;
        this.summary.textContent = App.plural("upload.summary", sent) + ". " + t(scanning ? "upload.scanning" : "upload.not_scanning");
      } catch (error) { this.summary.textContent = App.errorText(error); }
    },
  };
})();
