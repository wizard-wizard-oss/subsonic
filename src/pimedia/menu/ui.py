"""Interface Tk du menu : accueil, radios, écran de veille, confirmation. Aucune logique métier ici :
tout passe par les services reçus (voir main.py). Couleurs et polices viennent du thème."""
import time


class Scale:
    """Tailles pensées pour l'écran officiel 800x480, ajustées à l'écran réel."""

    def __init__(self, width, height, fonts):
        self.factor = min(max(width, 320) / 800.0, max(height, 240) / 480.0)
        self.fonts = fonts

    def px(self, value):
        return max(1, int(round(value * self.factor)))

    def font(self, size, bold=True, mono=True):
        """Police en PIXELS (taille négative en Tk) : indépendante du réglage DPI."""
        return (self.fonts.mono if mono else self.fonts.sans, -self.px(size), "bold" if bold else "normal")


class Equalizer:
    """Égaliseur à segments façon chaîne hi-fi ; seuls les segments qui changent sont redessinés."""

    def __init__(self, tk, parent, width, height, background, theme_eq):
        self.theme = theme_eq
        self.rows = len(theme_eq.segments)
        self.canvas = tk.Canvas(parent, width=width, height=height, bg=background, highlightthickness=0)
        column_w, row_h = width / theme_eq.columns, height / self.rows
        self.segments = []
        for i in range(theme_eq.columns):
            column = []
            for s in range(self.rows):
                y1 = height - s * row_h
                column.append(self.canvas.create_rectangle(i * column_w + 1, y1 - row_h + 1, (i + 1) * column_w - 1,
                                                           y1, fill=theme_eq.off, outline=""))
            self.segments.append(column)
        self.lit = [0] * theme_eq.columns

    def draw(self, lit):
        for i, count in enumerate(lit[:len(self.lit)]):
            old = self.lit[i]
            for s in range(min(count, old), max(count, old)):
                self.canvas.itemconfig(self.segments[i][s], fill=self.theme.segments[s] if s < count else self.theme.off)
            self.lit[i] = count


class MenuUI:
    def __init__(self, tk, services):
        self.tk = tk
        self.s = services
        self.t = services.texts.t
        self.colors = services.theme.colors
        self.saver_visible = False
        self.ticks = 0

        self.root = tk.Tk()
        self.root.title(self.t("launcher.title"))
        self.root.configure(bg=self.colors.background)
        self.root.attributes("-fullscreen", True)
        self.root.update_idletasks()
        self.scale = Scale(self.root.winfo_screenwidth(), self.root.winfo_screenheight(), services.theme.fonts)
        self.status = tk.StringVar()
        self.nowplaying = tk.StringVar()
        self.volume_text = tk.StringVar(value=self.t("launcher.volume", value="--"))

        self.root.bind_all("<Motion>", services.idle.touch)
        self.root.bind_all("<Button>", services.idle.touch)
        self.root.bind("<Map>", self._on_map)
        self.home = self._build_home()
        self.radio = self._build_radio()
        self.saver = self._build_saver()

    # ---------- briques ----------
    def px(self, value):
        return self.scale.px(value)

    def font(self, *args):
        return self.scale.font(*args)

    def big_button(self, parent, text, command, size=18, **grid):
        c = self.colors
        label = text.upper() if self.s.theme.fonts.uppercase_buttons else text
        button = self.tk.Button(parent, text=label, font=self.font(size), bg=c.panel, fg=c.text,
                                activebackground=c.panel_pressed, activeforeground=c.text, bd=0, relief="flat",
                                highlightthickness=2, highlightbackground=c.edge, highlightcolor=c.text,
                                command=command)
        button.grid(sticky="nsew", padx=self.px(5), pady=self.px(5), **grid)
        return button

    def small_button(self, parent, text, command, bg=None, **pack):
        c = self.colors
        button = self.tk.Button(parent, text=text, font=self.font(13), bg=bg or c.panel, fg=c.text,
                                activebackground=c.panel_pressed, activeforeground=c.text, bd=0,
                                highlightthickness=1, highlightbackground=c.edge, padx=self.px(12), pady=self.px(4),
                                command=command)
        button.pack(**pack)
        return button

    def label(self, parent, size, color, bg=None, bold=False, mono=False, **options):
        return self.tk.Label(parent, fg=color, bg=bg or self.colors.background, font=self.font(size, bold, mono),
                             **options)

    def show(self, frame):
        frame.place(x=0, y=0, relwidth=1, relheight=1)
        frame.lift()

    def grid_frame(self, rows):
        frame = self.tk.Frame(self.root, bg=self.colors.background)
        frame.columnconfigure((0, 1, 2), weight=1, uniform="c")
        for row in rows:
            frame.rowconfigure(row, weight=1, uniform="r")
        return frame

    def footer(self, parent):
        bar = self.tk.Frame(parent, bg=self.colors.background)
        bar.grid(row=3, column=0, columnspan=3, sticky="ew", padx=self.px(8), pady=(0, self.px(6)))
        return bar

    # ---------- accueil ----------
    def _build_home(self):
        c = self.colors
        home = self.grid_frame((1, 2))
        head = self.tk.Frame(home, bg=c.background)
        head.grid(row=0, column=0, columnspan=3, sticky="ew", padx=self.px(10), pady=(self.px(6), 0))
        self.home_clock = self.label(head, 34, c.text, bold=True, mono=True, text="--:--")
        self.home_clock.pack(side="left")
        info = self.tk.Frame(head, bg=c.background)
        info.pack(side="left", padx=self.px(14))
        self.home_date = self.label(info, 14, c.text_soft, text="")
        self.home_date.pack(anchor="w")
        self.home_weather = self.label(info, 12, c.text_dim, text="")
        self.home_weather.pack(anchor="w")
        self.home_eq = Equalizer(self.tk, head, self.px(200), self.px(40), c.background, self.s.theme.equalizer)
        self.home_eq.canvas.pack(side="right")

        tiles = (("launcher.home.music", self.open_music), ("launcher.home.youtube", self.open_freetube),
                 ("launcher.home.radio", lambda: self.show(self.radio)),
                 ("launcher.home.podcasts", lambda: self.open_web("/podcasts")),
                 ("launcher.home.bluetooth", self.bluetooth), ("launcher.home.clock", self.show_saver))
        for i, (key, command) in enumerate(tiles):
            self.big_button(home, self.t(key), command, size=18, row=1 + i // 3, column=i % 3)

        foot = self.footer(home)
        self.label(foot, 12, c.text, textvariable=self.nowplaying, anchor="w").pack(side="left")
        self.label(foot, 11, c.warning, textvariable=self.status, anchor="w").pack(side="left", padx=(self.px(10), 0))
        for key, action in (("launcher.home.poweroff", "poweroff"), ("launcher.home.reboot", "reboot")):
            text = self.t(key)
            self.small_button(foot, text, lambda a=action, l=text: self.power(a, l), side="right", padx=self.px(2))
        self.small_button(foot, self.t("launcher.home.desktop"), self.to_desktop, side="right", padx=self.px(2))
        return home

    # ---------- radios ----------
    def _build_radio(self):
        c = self.colors
        radio = self.grid_frame((0, 1, 2))
        for i, station in enumerate(self.s.stations[:9]):
            self.big_button(radio, station.name, lambda st=station: self.play_radio(st), size=15,
                            row=i // 3, column=i % 3)
        bar = self.footer(radio)
        self.label(bar, 13, c.text, textvariable=self.nowplaying).pack(side="left")
        self.small_button(bar, self.t("launcher.radio.back"), lambda: self.show(self.home), side="right",
                          padx=self.px(2))
        self.small_button(bar, self.t("launcher.radio.stop"), self.s.radio.stop, bg=c.danger, side="right",
                          padx=self.px(2))
        return radio

    # ---------- veille : horloge + météo + volume ----------
    def _build_saver(self):
        c, black = self.colors, self.colors.saver_background
        saver = self.tk.Frame(self.root, bg=black)
        self.saver_clock = self.label(saver, 72, c.text, bg=black, bold=True, mono=True, text="")
        self.saver_date = self.label(saver, 20, c.text_soft, bg=black, text="")
        self.saver_weather = self.label(saver, 24, c.text, bg=black, text="")
        self.saver_weather_sub = self.label(saver, 14, c.text_dim, bg=black, text="")
        playing = self.label(saver, 14, c.text_soft, bg=black, textvariable=self.nowplaying)
        for widget, pad in ((self.saver_clock, (self.px(16), 0)), (self.saver_date, (0, self.px(8))),
                            (self.saver_weather, (self.px(4), 0)), (self.saver_weather_sub, (0, self.px(8))),
                            (playing, (self.px(4), 0))):
            widget.pack(pady=pad)
        self.saver_eq = Equalizer(self.tk, saver, self.px(440), self.px(80), black, self.s.theme.equalizer)
        self.saver_eq.canvas.pack(pady=(self.px(12), 0))

        volume_row = self.tk.Frame(saver, bg=black)       # un toucher ailleurs ramène à l'appli / au menu
        for text, delta in (("−", -5), ("+", 5)):
            self.tk.Button(volume_row, text=text, font=self.font(22), bg=c.panel, fg=c.text,
                           activebackground=c.panel_pressed, activeforeground=c.text, bd=0, highlightthickness=1,
                           highlightbackground=c.edge, width=3,
                           command=lambda d=delta: self.change_volume(d)).pack(side="left")
            if delta < 0:
                self.label(volume_row, 18, c.text_soft, bg=black, bold=True, mono=True, width=10,
                           textvariable=self.volume_text).pack(side="left", padx=self.px(8))
        volume_row.pack(pady=(self.px(12), 0))

        saver.bind("<Button-1>", self.hide_saver)
        for widget in saver.winfo_children():
            if widget is not volume_row:
                widget.bind("<Button-1>", self.hide_saver)
        return saver

    # ---------- actions ----------
    def launch(self, command):
        try:
            if not self.s.apps.launch(command):
                return
        except FileNotFoundError as missing:
            self.status.set(self.t("launcher.status.not_found", name=str(missing)))
            return
        self.status.set("")
        self.s.radio.stop()          # pas deux sons en même temps
        self.s.idle.touch()
        self.root.withdraw()

    def open_web(self, path=""):
        command = self.s.web_command(path)
        if command is None:
            self.status.set(self.t("launcher.status.not_found", name="Chromium"))
            return
        self.launch(command)

    def open_music(self):
        self.open_web("/")

    def open_freetube(self):
        self.launch(self.s.freetube_command)

    def bluetooth(self):
        self.s.start_bluetooth()
        self.status.set(self.t("launcher.status.bluetooth", name=self.s.config.device_name))

    def play_radio(self, station):
        self.s.pause_other_players()
        if not self.s.radio.play(station):
            self.status.set(self.t("launcher.status.not_found", name="mpv"))

    def change_volume(self, delta):
        value = self.s.pulse.change_volume(delta)
        if value is None:
            self.status.set(self.t("launcher.status.volume_unavailable"))
        else:
            self.volume_text.set(self.t("launcher.volume", value="%d%%" % value))

    def confirm(self, question, on_yes):
        """Confirmation affichée DANS la fenêtre du menu. La boîte de dialogue système passait derrière
        le plein écran et ne recevait plus le toucher : le Pi restait bloqué."""
        c = self.colors
        veil = self.tk.Frame(self.root, bg=c.background)
        veil.place(x=0, y=0, relwidth=1, relheight=1)
        veil.lift()
        box = self.tk.Frame(veil, bg=c.panel, highlightthickness=2, highlightbackground=c.edge)
        box.place(relx=0.5, rely=0.5, anchor="center")
        self.label(box, 20, c.text, bg=c.panel, bold=True, mono=True, text=question,
                   padx=self.px(30), pady=self.px(24)).pack()
        buttons = self.tk.Frame(box, bg=c.panel)
        buttons.pack(pady=(0, self.px(20)))

        def answer(yes):
            if not veil.winfo_exists():
                return
            veil.destroy()
            if yes:
                on_yes()

        # Des étiquettes qui réagissent dès l'appui, et non des tk.Button : au toucher, un bouton Tk qui vient
        # d'apparaître ne voit pas le pointeur « entrer » et ignore le relâchement (le menu semblait figé).
        for key, yes in (("launcher.confirm.no", False), ("launcher.confirm.yes", True)):
            choice = self.label(buttons, 20, c.text, bg=c.panel_pressed, bold=True, mono=True, text=self.t(key),
                                highlightthickness=1, highlightbackground=c.edge, padx=self.px(40),
                                pady=self.px(12), cursor="hand2")
            choice.bind("<ButtonPress-1>", lambda _e, y=yes: answer(y))
            choice.pack(side="left", padx=self.px(14))
        veil.bind("<ButtonPress-1>", lambda _e: answer(False))       # toucher à côté = « Non »
        self.root.after(20000, lambda: answer(False))                 # sans réponse : on n'insiste pas
        return veil

    def power(self, action, label):
        def start():
            self.status.set(self.t("launcher.status.power_running", label=label))
            self.s.power.execute_in_background(action, lambda: self.root.after(
                0, lambda: self.status.set(self.t("launcher.status.power_refused", label=label))))
        self.confirm(self.t("launcher.confirm.power", label=label), start)

    def to_desktop(self):
        """Réduit le menu : la barre du bureau redevient accessible (retour : icône dans la barre des tâches)."""
        self.root.attributes("-fullscreen", False)
        self.root.iconify()

    def refullscreen(self):
        """Le compositeur rend parfois la fenêtre « agrandie » mais pas en vrai plein écran : on rebascule."""
        self.root.attributes("-fullscreen", False)
        self.root.update_idletasks()
        self.root.after(150, lambda: self.root.attributes("-fullscreen", True))

    def _on_map(self, event):
        if event.widget is self.root:
            self.root.after(200, self.refullscreen)

    # ---------- veille ----------
    def refresh_clock(self):
        now = time.localtime()
        hhmm = time.strftime("%H:%M", now)
        days, months = self.s.texts.words("launcher.days"), self.s.texts.words("launcher.months")
        date = "%s %d %s" % (days[now.tm_wday] if len(days) == 7 else "", now.tm_mday,
                             months[now.tm_mon - 1] if len(months) == 12 else now.tm_mon)
        report = self.s.weather.report
        self.saver_clock.config(text=hhmm)
        self.saver_date.config(text=date.strip())
        self.saver_weather.config(text=report.main)
        self.saver_weather_sub.config(text=report.sub)
        self.home_clock.config(text=hhmm)
        self.home_date.config(text=date.strip())
        self.home_weather.config(text=report.main)

    def show_saver(self):
        self.saver_visible = True
        self.refresh_clock()
        self.show(self.saver)

    def hide_saver(self, _event=None):
        self.saver_visible = False
        self.s.idle.touch()
        if self.s.apps.running:
            self.root.withdraw()      # retour à l'appli qui joue
        else:
            self.show(self.home)

    # ---------- boucles de l'interface ----------
    def playing_text(self):
        radio = self.s.radio
        if radio.station is not None:
            return self.t("launcher.radio.listening", name=radio.station.name)
        if radio.interrupted:
            return self.t("launcher.radio.interrupted")
        title = self.s.now_playing()
        return "♪ " + title if title else ""

    def tick(self):
        self.ticks += 1
        if self.s.apps.finished():
            self.saver_visible = False
            self.root.deiconify()
            self.root.attributes("-fullscreen", True)
            self.show(self.home)
            self.s.idle.touch()
        self.s.radio.check()
        self.nowplaying.set(self.playing_text())
        self.refresh_clock()
        if self.ticks % 5 == 1:
            volume = self.s.pulse.volume()
            if volume is not None:
                self.volume_text.set(self.t("launcher.volume", value="%d%%" % volume))
        decision = self.s.saver_decision(self.saver_visible)
        if decision == "over_app":       # appli musique au premier plan : l'horloge passe dessus
            self.root.deiconify()
            self.root.attributes("-fullscreen", True)
        if decision:
            self.show_saver()
        self.root.after(1000, self.tick)

    def animate(self):
        """Rafraîchit l'égaliseur (~12 images/s) sur l'écran visible uniquement."""
        lit = self.s.spectrum.lit(len(self.s.theme.equalizer.segments))
        if self.saver_visible:
            self.saver_eq.draw(lit)
        elif not self.s.apps.running:
            self.home_eq.draw(lit)
        self.root.after(80, self.animate)

    def run(self):
        self.show(self.home)
        self.root.after(500, self.tick)
        self.root.after(700, self.animate)
        self.root.mainloop()
