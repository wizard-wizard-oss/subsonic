"use strict";

/* Navigation commune au radar et à la consultation par style : semaine, date et retour à aujourd'hui. */
const WeeklyWeek = (() => {
  const el = App.el, t = key => App.t("weekly." + key);

  class WeekNavigation {
    constructor(monday, onChange) {
      this.onChange = onChange;
      this.title = el("span");
      this.range = el("p.muted.weekly-date");
      this.date = el("input", {type: "date", onchange: () => this.chooseDate()});
      this.today = el("button.link-button.weekly-today", {type: "button", text: t("today"),
        onclick: () => this.choose(WeeklyReleaseView.mondayFor(new Date()))});
      this.menu = el("details.weekly-week-menu", {},
        el("summary.weekly-week-label", {}, this.title, el("span", {text: "▾", "aria-hidden": "true"})),
        el("div.weekly-popover", {}, el("label", {}, el("span", {text: t("choose_date")}), this.date), this.today));
      const arrow = (icon, label, days) => el("button.icon-button", {type: "button", title: t(label),
        "aria-label": t(label), onclick: () => this.choose(WeeklyReleaseView.shift(this.monday, days))}, App.icon(icon));
      this.node = el("div.weekly-week-control", {}, el("div.weekly-week", {},
        arrow("chevronLeft", "previous", -7), this.menu, arrow("chevronRight", "next", 7)), this.range);
      this.menu.addEventListener("keydown", event => {
        if (event.key === "Escape") { this.menu.open = false; this.menu.querySelector("summary").focus(); }
      });
      this.update(monday);
    }

    update(monday) {
      const W = WeeklyReleaseView, current = W.iso(monday) === W.iso(W.mondayFor(new Date()));
      this.monday = monday;
      const format = new Intl.DateTimeFormat("fr-FR", {day: "numeric", month: "short", timeZone: "UTC"});
      this.title.textContent = current ? t("today") : format.formatRange(monday, W.shift(monday, 6));
      this.range.textContent = new Intl.DateTimeFormat("fr-FR", {
        day: "numeric", month: "short", year: "numeric", timeZone: "UTC",
      }).formatRange(monday, W.shift(monday, 6));
      this.date.value = W.iso(monday);
      this.today.hidden = current;
    }

    chooseDate() {
      if (this.date.value) this.choose(WeeklyReleaseView.mondayFor(new Date(this.date.value + "T12:00:00")));
    }

    choose(monday) {
      this.menu.open = false;
      this.update(monday);
      this.onChange(monday);
    }
  }

  return {create: (monday, onChange) => new WeekNavigation(monday, onChange)};
})();
