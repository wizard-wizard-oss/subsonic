"use strict";
// Podcasts : éléments d'affichage (cartes, rangées, tuiles, épisodes)

function el(tag, cls, html) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (html != null) e.innerHTML = html;
  return e;
}

/* Pochette : image, ou pastille colorée avec l'initiale si elle manque ou ne charge pas */
function artwork(url, title, cls) {
  const box = el("div", "art " + (cls || ""));
  const hue = [...(title || "?")].reduce((h, c) => (h * 31 + c.charCodeAt(0)) % 360, 7);
  box.style.setProperty("--h", hue);
  box.innerHTML = '<span>' + esc((title || "?").trim().charAt(0).toUpperCase()) + '</span>';
  if (url) {
    const img = new Image();
    img.loading = "lazy"; img.alt = "";
    img.onload = () => { box.innerHTML = ""; box.appendChild(img); };
    img.src = url;
  }
  return box;
}

function podcastCard(p) {
  const card = el("button", "pcard");
  card.appendChild(artwork(p.image, p.title));
  card.appendChild(el("b", "", esc(p.title)));
  card.appendChild(el("small", "", esc(p.author || p.genre || "")));
  if (p.subscribed) card.appendChild(el("i", "badge", ic("check", 14)));
  card.onclick = () => openShow(p.feed, p);
  return card;
}

function heading(text) { return el("div", "ph", esc(text)); }

function shelf(title, items, build) {
  const wrap = el("section", "psection");
  wrap.appendChild(heading(title));
  const row = el("div", "pshelf");
  items.forEach(i => row.appendChild(build(i)));
  wrap.appendChild(row);
  return wrap;
}

function cardGrid(items) {
  const g = el("div", "pgrid");
  items.forEach(p => g.appendChild(podcastCard(p)));
  return g;
}

function themeTile(t) {
  const tile = el("button", "ptile", "<span>" + esc(t.label) + "</span>");
  tile.style.setProperty("--h", t.hue);
  tile.onclick = () => openTheme(t);
  return tile;
}

/* Épisode commencé : carte avec barre de progression, et une croix pour le retirer de la liste */
function resumeCard(e) {
  const card = el("div", "pcard resume");
  card.appendChild(artwork(e.image, e.podcast));
  card.appendChild(el("b", "", esc(e.title)));
  card.appendChild(el("small", "", esc(e.podcast) + " · reste " + fmtLength(e.dur - e.pos)));
  const bar = el("div", "mini", "<i></i>");
  bar.firstChild.style.width = Math.min(100, e.dur ? e.pos / e.dur * 100 : 0) + "%";
  card.appendChild(bar);
  card.onclick = () => player.play({id: e.id, feed: e.feed, title: e.title, podcast: e.podcast, image: e.image,
                                    audio: e.audio, duration: e.dur, pos: e.pos});
  const remove = el("button", "forget", "✕");
  remove.setAttribute("aria-label", "Retirer « " + e.title + " » de la liste");
  remove.onclick = async ev => {
    ev.stopPropagation();
    try {
      await ppost("forget", {id: e.id});
      const shelfEl = card.closest(".psection");
      card.remove();
      if (shelfEl && !shelfEl.querySelector(".pcard")) shelfEl.remove();     // plus rien à reprendre : la rangée disparaît
    } catch (err) { toast(err.message); }
  };
  card.appendChild(remove);
  return card;
}

/* Une ligne d'épisode. context : {feed, podcast, image} du podcast affiché */
function episodeRow(ep, context) {
  const row = el("div", "pep" + (ep.played ? " done" : "") + (player.isCurrent(ep.id) ? " cur" : ""));
  const play = el("button", "go", ic("play", 26));
  const info = el("div", "t");
  info.appendChild(el("b", "", esc(ep.title)));
  const meta = [fmtDate(ep.date), fmtLength(ep.duration)].filter(Boolean).join(" · ");
  info.appendChild(el("small", "", esc(meta) + (ep.pos > 10 ? " · repris à " + fmtTime(ep.pos) : "")));
  if (ep.desc) info.appendChild(el("p", "", esc(ep.desc)));
  if (ep.pos > 10 && ep.duration) {
    const bar = el("div", "mini", "<i></i>"); bar.firstChild.style.width = Math.min(100, ep.pos / ep.duration * 100) + "%";
    info.appendChild(bar);
  }
  row.appendChild(play); row.appendChild(info);
  row.onclick = () => player.play({id: ep.id, feed: context.feed, title: ep.title, podcast: context.podcast,
                                   image: ep.image || context.image, audio: ep.audio, duration: ep.duration,
                                   pos: ep.pos, desc: ep.desc});
  return row;
}

function latestRow(ep) {
  const row = episodeRow(ep, {feed: ep.feed, podcast: ep.podcast, image: ep.image});
  row.insertBefore(artwork(ep.image, ep.podcast, "small"), row.firstChild);
  const meta = row.querySelector("small");
  meta.textContent = ep.podcast + " · " + meta.textContent;
  return row;
}

function emptyMessage(text) { return el("div", "pmsg", esc(text)); }
function loadingMessage() { return el("div", "pmsg", "Chargement…"); }

/* Filtre « français uniquement » : puce à placer en tête des écrans qui listent des podcasts */
function frenchChip(onChange) {
  const chip = el("button", "pchip");
  const paint = () => { chip.classList.toggle("on", french); chip.textContent = french ? "Français uniquement : oui" : "Toutes les langues"; };
  paint();
  chip.onclick = async () => {
    try {
      const r = await ppost("language", {french: !french});
      french = r.french; paint(); onChange();
    } catch (e) { toast(e.message); }
  };
  return chip;
}
