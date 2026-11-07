"use strict";
/* Page « Versions » (#/versions) : ce qui a changé sur le site, version par version, la plus récente en haut (contenu
   dans i18n/versions.yaml, servi par /api/versions). Le numéro de la dernière version est affiché à côté du titre du
   site, avec une pastille tant que ce navigateur ne l'a pas vue ; ouvrir la page la marque comme vue. */

const Versions = (() => {
  const el = App.el, t = App.t;
  const SEEN = "pimedia.version_seen";
  let releases = null;

  function seen() {
    try { return localStorage.getItem(SEEN) || ""; } catch (e) { return ""; }
  }

  function remember(version) {
    try { localStorage.setItem(SEEN, version); } catch (e) { /* stockage refusé : la pastille reviendra */ }
  }

  function newer(version, than) {
    if (!than) return true;
    const [a, b] = [version, than].map(v => v.split(".").map(Number));       // « 1.5.1 » > « 1.5 » : le manque vaut 0
    for (let i = 0; i < 3; i++) if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) > (b[i] || 0);
    return false;
  }

  function day(iso) {
    const [year, month, date] = iso.split("-").map(Number);
    return new Date(year, month - 1, date).toLocaleDateString("fr-FR", {day: "numeric", month: "long", year: "numeric"});
  }

  function showTag() {
    const tag = document.getElementById("version-tag");
    if (!tag || !releases || !releases.length) return;
    const latest = releases[0], fresh = newer(latest.version, seen());
    tag.hidden = false;
    tag.textContent = t("versions.tag", {version: latest.version});
    tag.title = t(fresh ? "versions.tag_new" : "versions.tag_title", {version: latest.version, date: day(latest.date)});
    tag.classList.toggle("fresh", fresh);
  }

  async function load() {
    if (!releases) {
      try { releases = (await App.api.get("/api/versions")).releases; } catch (e) { return []; }
    }
    // Une livraison peut être renumérotée : un ancien numéro retiré ne doit pas masquer les prochaines pastilles.
    const lastSeen = seen();
    if (releases.length && lastSeen && !releases.some(item => item.version === lastSeen) &&
        newer(lastSeen, releases[0].version)) remember(releases[0].version);
    showTag();
    return releases;
  }

  function release(item, lastSeen) {
    const fresh = newer(item.version, lastSeen);
    return el("section.version" + (fresh ? ".fresh" : ""), {},
      el("h2.version-head", {},
        el("span", {text: t("versions.number", {version: item.version})}),
        el("span.muted.version-date", {text: day(item.date)}),
        fresh ? el("b.badge", {text: t("versions.new")}) : null),
      el("p.version-title", {text: item.title}),
      el("ul.version-changes", {}, item.changes.map(change => el("li", {text: change}))));
  }

  const view = {
    async render(main, route) {
      App.clear(main);
      const list = await load();
      if (route.stale) return;
      const lastSeen = seen();
      App.append(main, [
        el("h1", {text: t("versions.title")}),
        el("p.muted.version-intro", {text: t("versions.intro")}),
        list.length ? list.map(item => release(item, lastSeen)) : el("p.muted", {text: t("versions.none")})]);
      if (list.length) remember(list[0].version);
      showTag();
    },
  };

  return {load, view};
})();

Views.versions = Versions.view;
