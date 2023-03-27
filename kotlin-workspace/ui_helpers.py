import contextlib
import itertools
from PIL import Image, ImageTk
import tkinter.scrolledtext
import tkinter as tk


hidden_widget_sides = {}


def hide_widget(widget):
    try:
        hidden_widget_sides[widget] = widget.pack_info()['side']
    except Exception:
        pass
    widget.pack_forget()


def show_widget(widget):
    try:
        side = hidden_widget_sides.pop(widget)
    except KeyError:
        side = None
    widget.pack(side=side)


class AnimatedImageLabel(tk.Label):
    """
    A label that displays images, and plays them if they are gifs.

    CREDITS: https://stackoverflow.com/a/43770948/13994294
    """
    def __init__(self, master, path):
        super().__init__(master)
        self.load(path)
        self._visible = True

    def load(self, path):
        image = Image.open(path)
        self.loc = 0
        self.frames = []

        try:
            for i in itertools.count(1):
                new_image = image.copy()
                photo = ImageTk.PhotoImage(new_image)
                self.frames.append(photo)
                image.seek(i)
        except EOFError:
            pass

        try:
            self.delay = im.info['duration']
        except:
            self.delay = 100

        if len(self.frames) == 1:
            self.config(image=self.frames[0])
        else:
            self.next_frame()

    def next_frame(self):
        if self.frames:
            if True:
                self.loc += 1
                self.loc %= len(self.frames)
                self.config(image=self.frames[self.loc])
            self.after(self.delay, self.next_frame)

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = value
        if value:
            show_widget(self)
        else:
            hide_widget(self)


class HyperlinkManager:
    """
    Makes it possible to insert hyperlinks in a Tkinter Text widget.

    CREDITS: https://stackoverflow.com/a/50328110/13994294
    """
    def __init__(self, text):
        self.text = text
        self.text.tag_config("hyper", foreground="blue", underline=1)
        self.text.tag_bind("hyper", "<Enter>", self._enter)
        self.text.tag_bind("hyper", "<Leave>", self._leave)
        self.text.tag_bind("hyper", "<Button-1>", self._click)
        self.reset()

    def reset(self):
        self.links = {}

    def add(self, action):
        # add an action to the manager.  returns tags to use in
        # associated text widget
        tag = "hyper-%d" % len(self.links)
        self.links[tag] = action
        return "hyper", tag

    def _enter(self, event):
        self.text.config(cursor="hand2")

    def _leave(self, event):
        self.text.config(cursor="")

    def _click(self, event):
        for tag in self.text.tag_names(tk.CURRENT):
            if tag[:6] == "hyper-":
                self.links[tag]()
                return


class ReadOnlyText(tkinter.scrolledtext.ScrolledText):
    """
    A text widget that can be set to read-only mode.
    """
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)

        # create proxy
        self._orig = f'{self._w}_orig'
        self.tk.call('rename', self._w, self._orig)
        self.tk.createcommand(self._w, self._proxy)

        self.read_only = kwargs.get('read_only', True)

    def _proxy(self, *args):
        largs = list(args)

        if self.read_only:
            if args[0] == 'insert':
                return
            elif args[0] == "delete":
                return

        result = self.tk.call((self._orig,) + tuple(largs))
        return result

    @contextlib.contextmanager
    def unlocked(self):
        self.read_only = False
        yield
        self.read_only = True
