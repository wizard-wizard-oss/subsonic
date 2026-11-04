"use strict";
/* Page « Mon compte » (#/account) : photo de profil (image envoyée, copie de Gravatar, ou celle de Subsonic),
   affichage, droits du compte Subsonic, lien vers les réglages personnels de Subsonic (Last.fm, mot de passe) et
   import d'un lien YouTube ou SoundCloud. Les réglages rapides (roue dentée en haut) restent là pour l'affichage. */

Views.account = (() => {
  const el = App.el, t = App.t;
  const SIDE = 256;                 // photo envoyée : carré de 256 px, en JPEG (bien en dessous des 300 Ko permis)

  function part(title, help, ...content) {
    return el("section.account-part", {}, el("h2", {text: title}), help ? el("p.muted", {text: help}) : null, content);
  }

  /** Image choisie, recadrée au centre en carré et réduite par le navigateur ; en « data: » (seul format permis
      par la politique de sécurité de la page). */
  function squareImage(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("read"));
      reader.onload = () => {
        const image = new Image();
        image.onerror = () => reject(new Error("image"));
        image.onload = () => {
          const side = Math.min(image.naturalWidth, image.naturalHeight);
          const canvas = el("canvas", {width: SIDE, height: SIDE});
          canvas.getContext("2d").drawImage(image, (image.naturalWidth - side) / 2, (image.naturalHeight - side) / 2,
                                            side, side, 0, 0, SIDE, SIDE);
          resolve(canvas.toDataURL("image/jpeg", 0.88));
        };
        image.src = reader.result;
      };
      reader.readAsDataURL(file);
    });
  }

  /** Après un changement de photo : nouvelles versions (toutes les pastilles de la page suivent), puis la section. */
  async function changed(box, message) {
    App.toast(message);
    await Avatars.load();
    await photo(box);
  }

  /** Section de la photo ; renvoie ce que /api/account dit du compte (null si Subsonic ne répond pas). */
  async function photo(box) {
    let account;
    try { account = await App.api.get("/api/account"); } catch (error) {
      App.clear(box).appendChild(el("p.page-error", {text: App.errorText(error)}));
      return null;
    }
    const file = el("input", {type: "file", accept: "image/*", hidden: true, onchange: async () => {
      const chosen = file.files[0];
      if (!chosen) return;
      let image;
      try { image = await squareImage(chosen); } catch (error) {
        App.toast(t("account.choose_bad"), "error");
        return;
      }
      try {
        await App.api.post("/api/avatar/upload", {image});
        await changed(box, t("account.saved"));
      } catch (error) {
        App.toast(App.errorText(error), "error");
      }
    }});
    const remove = async () => {
      try {
        await App.api.post("/api/avatar/delete", {});
        await changed(box, t("account.removed"));
      } catch (error) {
        App.toast(App.errorText(error), "error");
      }
    };
    const email = el("input.account-email", {type: "email", value: account.email || "", maxLength: 254,
                                             placeholder: t("account.gravatar_placeholder"),
                                             "aria-label": t("account.gravatar_placeholder")});
    const take = el("button", {type: "submit", text: t("account.gravatar_take")});
    const gravatar = el("form.account-gravatar", {onsubmit: async event => {
      event.preventDefault();
      take.disabled = true;
      take.textContent = t("account.gravatar_taking");
      try {
        await App.api.post("/api/avatar/gravatar", {email: email.value});
        await changed(box, t("account.saved"));
        return;
      } catch (error) {
        App.toast(App.errorText(error), "error");
      }
      take.disabled = false;
      take.textContent = t("account.gravatar_take");
    }}, email, take);

    App.append(App.clear(box), [
      el("div.account-photo", {},
        App.avatar(App.user.username, 96),
        el("div.account-photo-side", {},
          el("p", {text: t("account.source_" + (account.source || "none"))}),
          el("div.account-buttons", {},
            el("button.primary", {type: "button", text: t("account.choose"), onclick: () => file.click()}),
            account.source === "site" ? el("button", {type: "button", text: t("account.remove"), onclick: remove}) : null),
          file)),
      el("h3", {text: t("account.gravatar")}),
      gravatar,
      el("p.muted", {text: t("account.gravatar_help")})]);
    return account;
  }

  function subsonicLink(box, account) {
    App.clear(box).appendChild(account.subsonicSettings
      ? el("a.button", {href: account.subsonicSettings, target: "_blank", rel: "noopener",
                             text: t("account.subsonic_open") + " ↗"})
      : el("p.muted", {text: t("account.subsonic_unknown")}));
  }

  return {
    render(main) {
      App.clear(main);
      const photoBox = el("div.account-photo-box", {}, el("p.muted", {text: "…"}));
      const subsonicBox = el("div", {}, el("p.muted", {text: "…"}));
      App.append(main, [
        el("h1", {text: t("account.title")}),
        el("p.muted.account-intro", {text: t("account.intro") + " (" + App.user.username + ")"}),
        el("div.account-grid", {},
          part(t("account.photo"), t("account.photo_help"), photoBox),
          part(t("account.display"), t("account.display_help"), el("div.settings", {}, Dialogs.display())),
          el("section.account-part", {}, Dialogs.rights()),
          part(t("account.subsonic"), t("account.subsonic_help"), subsonicBox),
          part(t("account.import"), t("account.import_help"),
               ExtMusic.linkForm(null, {label: t("account.import_see"), run: () => { location.hash = "#/favorites"; }}),
               el("p.muted.ext-link-help", {text: t("ext.link_help")}),
               el("p.muted", {text: t("account.import_accounts")})))]);
      photo(photoBox).then(account => { if (account) subsonicLink(subsonicBox, account); });
    },
  };
})();
