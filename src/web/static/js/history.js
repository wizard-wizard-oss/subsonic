"use strict";
// Historique des recherches de l'écran du Pi : partagé par la page Musique et la page Podcasts

class SearchHistoryList {
  constructor(kind) { this.kind = kind; }

  async entries() {
    try { return (await (await fetch("/ext/history?kind=" + this.kind)).json()).entries || []; }
    catch (e) { return []; }                   // sans historique, la recherche reste utilisable
  }

  async change(action, text) {
    try {
      const r = await fetch("/ext/history", {method: "POST", body: JSON.stringify({kind: this.kind, action, text}),
        headers: {"Content-Type": "application/json", "X-Requested-With": "pm"}});
      return (await r.json()).entries || [];
    } catch (e) { return []; }
  }

  remember(text) {
    if ((text || "").trim().length >= 2) this.change("add", text.trim());
  }

  /* Affiche les recherches récentes dans container ; onPick(texte) relance la recherche */
  async show(container, onPick) {
    const list = await this.entries();
    if (!list.length || !container.isConnected) return;
    const box = document.createElement("div"); box.className = "hist";
    const paint = entries => {
      box.innerHTML = '<div class="histhead">Recherches récentes</div>';
      if (!entries.length) { box.remove(); return; }
      entries.forEach(text => box.appendChild(this.item(text, onPick, paint)));
      const clear = document.createElement("button"); clear.className = "histclear"; clear.textContent = "Effacer l’historique";
      clear.onclick = async () => paint(await this.change("clear"));
      box.appendChild(clear);
    };
    paint(list);
    container.appendChild(box);
  }

  item(text, onPick, repaint) {
    const line = document.createElement("div"); line.className = "histitem";
    const pick = document.createElement("button"); pick.className = "histtext"; pick.textContent = text;
    pick.onclick = () => onPick(text);
    const remove = document.createElement("button"); remove.className = "histdel"; remove.textContent = "✕";
    remove.setAttribute("aria-label", "Retirer « " + text + " »");
    remove.onclick = async e => { e.stopPropagation(); repaint(await this.change("remove", text)); };
    line.appendChild(pick); line.appendChild(remove);
    return line;
  }
}
