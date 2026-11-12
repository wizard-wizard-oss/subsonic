"use strict";
/* Association d'un artiste local : sélecteur ponctuel, catalogue automatique et relations sous les albums. */
class ArtistDiscography {
  constructor(data, route, onIdentity) {
    this.data = data;
    this.route = route;
    this.onIdentity = onIdentity;
    this.identity = null;
    this.revision = 0;
    const el = App.el, t = key => App.t("discovery." + key);
    this.results = el("div.discography-results");
    this.caption = el("div.discography-association", {role: "status"});
    this.change = DiscogsUI.button(t("change_identity"), "edit", () => this.open(true), ".discography-change.link-button");
    this.refresh = DiscogsUI.button(t("refresh_catalog"), "undo", () => this.refreshCatalog(), ".discography-refresh.link-button");
    this.refresh.hidden = true;
    this.openButton = DiscogsUI.button(t("open_discography"), "discogs", () => this.open(), ".discography-open");
    this.root = PageSections.section("artist-discography", ".discography.artist-discography");
    App.append(this.root, [el("div.section-head", {}, el("h2", {}, App.icon("discogs", 20), " ", t("discography")),
      el("div.discography-tools", {}, this.change, this.refresh)), this.caption, this.openButton, this.results]);
    this.relations = PageSections.section("artist-members", ".discography-relations");
    this.relationsBody = el("div");
    App.append(this.relations, [Views.heading(t("members_and_groups")), this.relationsBody]);
    this.relationsBody.textContent = t("relations_choose");
    this.catalog = new DiscogsUI.Discography(this.results, route, identity => this.describeIdentity(identity));
    this.ready = this.loadLink();
  }

  async loadLink() {
    const revision = ++this.revision;
    this.caption.textContent = App.t("discovery.loading");
    try {
      const data = await App.api.get("/api/discogs/artist-link", {id: this.data.id});
      if (this.route.stale || revision !== this.revision) return;
      if (data.link) this.showIdentity({id: data.link.discogsArtistId, name: this.data.name, kind: "artist"});
      else this.caption.textContent = App.t("discovery.association_help");
    } catch (failure) {
      if (!this.route.stale && revision === this.revision) DiscogsUI.error(this.caption, failure, () => this.loadLink());
    }
  }

  async open(force = false) {
    await this.ready;
    if (this.route.stale) return;
    if (this.identity && !force) return;
    const content = App.el("div.discography-picker");
    const status = App.el("p.page-error", {role: "status"});
    content.appendChild(DiscogsUI.picker(this.data.name, "artist", this.route, identity => this.choose(identity, status)));
    content.appendChild(status);
    this.dialog = Dialogs.open(App.t("discovery.choose_identity"), content, () => {
      if (this.root.isConnected) this.change.focus({preventScroll: true});
    });
  }

  async choose(identity, status) {
    if (this.route.stale || this.saving) return;
    this.saving = true;
    const buttons = this.dialog.querySelectorAll(".discogs-identity");
    buttons.forEach(button => { button.disabled = true; });
    status.textContent = "";
    try {
      await App.api.post("/api/discogs/artist-link", {artistId: this.data.id, discogsArtistId: identity.id});
      if (this.route.stale) return;
      ++this.revision;
      if (this.dialog.isConnected) Dialogs.close();
      this.showIdentity(identity);
      if (this.onIdentity) this.onIdentity();
    } catch (failure) { if (!this.route.stale) status.textContent = App.errorText(failure); }
    finally { this.saving = false; buttons.forEach(button => { button.disabled = false; }); }
  }

  describeIdentity(identity) {
    this.identity = identity;
    this.openButton.hidden = true;
    this.refresh.hidden = false;
    App.append(App.clear(this.caption), [App.el("span", {text: App.t("discovery.associated_identity") + " "}),
      DiscogsUI.source("artist", identity.id, identity.name + " · #" + identity.id),
      App.el("span.discography-saved", {text: App.t("discovery.choice_saved")})]);
  }

  showIdentity(identity) {
    this.describeIdentity(identity);
    App.clear(this.results);
    this.catalog.load(identity);
    DiscogsCredits.loadConnections(this.relationsBody, identity.id, this.route);
  }

  async refreshCatalog() {
    if (!this.identity || this.refresh.disabled) return;
    this.refresh.disabled = this.change.disabled = true;
    this.results.inert = true;
    this.root.setAttribute("aria-busy", "true");
    try { await this.catalog.load(this.identity, 1, this.data.id); }
    finally {
      this.refresh.disabled = this.change.disabled = false;
      this.results.inert = false;
      this.root.removeAttribute("aria-busy");
    }
  }

  destroy() { if (this.dialog && this.dialog.isConnected) Dialogs.close(); }
}
