"""Doublure de tkinter : assez pour construire le menu, appuyer sur ses boutons et faire tourner ses boucles,
sans écran (tkinter n'est pas installé partout). Les widgets retiennent leurs options et leurs liaisons."""
import types


class Widget:
    def __init__(self, master=None, **options):
        self.master = master
        self.options = dict(options)
        self.children = []
        self.bindings = {}
        self.alive = True
        self.placed = False
        if master is not None:
            master.children.append(self)

    # disposition
    def pack(self, **_):
        return None

    def grid(self, **_):
        return None

    def place(self, **_):
        self.placed = True

    def lift(self):
        root = self.root()
        root.raised = self

    def columnconfigure(self, *_a, **_k):
        return None

    rowconfigure = columnconfigure

    # état
    def config(self, **options):
        self.options.update(options)

    configure = config

    def cget(self, key):
        return self.options.get(key)

    def bind(self, event, handler):
        self.bindings[event] = handler

    def winfo_children(self):
        return list(self.children)

    def winfo_exists(self):
        return self.alive

    def destroy(self):
        self.alive = False
        for child in self.children:
            child.destroy()

    def root(self):
        node = self
        while node.master is not None:
            node = node.master
        return node

    # tests
    def find_all(self, kind=None):
        found = []
        for child in self.children:
            if kind is None or isinstance(child, kind):
                found.append(child)
            found.extend(child.find_all(kind))
        return found

    def text(self):
        if "textvariable" in self.options:
            return self.options["textvariable"].get()
        return self.options.get("text", "")


class Tk(Widget):
    def __init__(self):
        super().__init__(None)
        self.attributes_set = {}
        self.timers = []
        self.withdrawn = False
        self.raised = None
        self.global_bindings = {}

    def title(self, text):
        self.options["title"] = text

    def attributes(self, name, value):
        self.attributes_set[name] = value

    def update_idletasks(self):
        return None

    def winfo_screenwidth(self):
        return 800

    def winfo_screenheight(self):
        return 480

    def bind_all(self, event, handler):
        self.global_bindings[event] = handler

    def after(self, delay, callback):
        self.timers.append((delay, callback))

    def run_timers(self):
        pending, self.timers = self.timers, []
        for _delay, callback in pending:
            callback()

    def withdraw(self):
        self.withdrawn = True

    def deiconify(self):
        self.withdrawn = False

    def iconify(self):
        self.withdrawn = True

    def mainloop(self):
        return None


class Frame(Widget):
    pass


class Label(Widget):
    pass


class Button(Widget):
    def invoke(self):
        return self.options["command"]()


class Canvas(Widget):
    def __init__(self, master=None, **options):
        super().__init__(master, **options)
        self.items = {}

    def create_rectangle(self, *coords, **options):
        item = len(self.items) + 1
        self.items[item] = dict(options)
        return item

    def itemconfig(self, item, **options):
        self.items[item].update(options)


class StringVar:
    def __init__(self, value=""):
        self.value = value

    def set(self, value):
        self.value = value

    def get(self):
        return self.value


def module():
    return types.SimpleNamespace(Tk=Tk, Frame=Frame, Label=Label, Button=Button, Canvas=Canvas, StringVar=StringVar)
