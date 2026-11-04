"use strict";
/* Mise en forme des messages : **gras**, *italique*, `code`, liens, @mentions, retours à la ligne.
   Construit des nœuds DOM (jamais d'innerHTML) : un message ne peut pas injecter de code dans la page. */

const MessageFormat = (() => {
  // ordre = priorité : le code d'abord (rien n'est interprété dedans), puis les liens, etc.
  const RULES = [
    {name: "code", re: /`([^`\n]{1,500})`/y},
    {name: "link", re: /(https?:\/\/[^\s<>"]{2,500}[^\s<>".,;:!?)\]}'])/y},
    {name: "bold", re: /\*\*([^*\n]{1,500})\*\*/y},
    {name: "italic", re: /\*([^*\n]{1,500})\*/y},
    {name: "mention", re: /@([\w.+-]{1,64})/y},
  ];

  /** Découpe un texte en morceaux {type, text}. Testable sans DOM. */
  function tokenize(text) {
    const tokens = [];
    let plain = "", i = 0;
    const flush = () => { if (plain) { tokens.push({type: "text", text: plain}); plain = ""; } };
    while (i < text.length) {
      const c = text[i];
      if (c === "\n") { flush(); tokens.push({type: "break"}); i++; continue; }
      let matched = null;
      if ("`h*@".includes(c) && (c !== "@" || i === 0 || !/[\w@]/.test(text[i - 1]))) {
        for (const rule of RULES) {
          rule.re.lastIndex = i;
          const m = rule.re.exec(text);
          if (m) { matched = {type: rule.name, text: m[1], length: m[0].length}; break; }
        }
      }
      if (matched) { flush(); tokens.push(matched); i += matched.length; }
      else { plain += c; i++; }
    }
    flush();
    return tokens;
  }

  function render(text, options) {
    const me = (options && options.me || "").toLowerCase();
    const known = new Set((options && options.usernames || []).map(n => n.toLowerCase()));
    const fragment = document.createDocumentFragment();
    for (const token of tokenize(text || "")) {
      if (token.type === "text") fragment.appendChild(document.createTextNode(token.text));
      else if (token.type === "break") fragment.appendChild(document.createElement("br"));
      else if (token.type === "code") fragment.appendChild(App.el("code", {text: token.text}));
      else if (token.type === "bold") fragment.appendChild(App.el("strong", {text: token.text}));
      else if (token.type === "italic") fragment.appendChild(App.el("em", {text: token.text}));
      else if (token.type === "link") {
        fragment.appendChild(App.el("a", {href: token.text, text: token.text, target: "_blank", rel: "noopener noreferrer nofollow"}));
      } else if (token.type === "mention") {
        const name = token.text.replace(/\.$/, "").toLowerCase();
        if (known.has(name)) {
          fragment.appendChild(App.el("span.mention" + (name === me ? ".me" : ""), {text: "@" + token.text}));
        } else {
          fragment.appendChild(document.createTextNode("@" + token.text));
        }
      }
    }
    return fragment;
  }

  return {tokenize, render};
})();
