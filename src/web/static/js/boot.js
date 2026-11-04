"use strict";
// Démarrage de l'application

/* ---------- Démarrage ---------- */
(async () => {
  try { const j = await (await fetch("/settings")).json(); browseMode = j.browse_mode || browseMode; } catch (e) {}
  try { await api("ping"); tab("home"); }
  catch (e) {
    stack.push({title: "Subsonic", build: c => {}});
    $("#title").textContent = "Subsonic";
    main.innerHTML = '<div class="msg">' + esc(e.message) +
      "<br><br>Pour configurer : <b>~/.local/share/pi-media/set-subsonic.sh URL UTILISATEUR MOTDEPASSE</b></div>";
  }
})();
