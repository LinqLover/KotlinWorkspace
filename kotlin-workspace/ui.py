import contextlib
import tkinter as tk
import tkinter.scrolledtext
import tkinter.ttk
import os
import Pmw
from queue import Queue
import re

import runners
import ui_helpers


SCRIPT_BASENAME = 'script'
SCRIPT_EXT = 'kts'
SCRIPT_NAME = f'{SCRIPT_BASENAME}.{SCRIPT_EXT}'
"""
If True, scripts will be run with a smaller delay, but this depends on an
undocumented feature of the compiler. See HotScriptRunner for more details.
"""
USE_HOT_SCRIPT = True


class App:
    def __init__(self):
        with open(self._resolve_asset('sample.kt'), 'r') as f:
            self.default_script = f.read()

        self._init_ui()
        self.output_queue = Queue()
        if USE_HOT_SCRIPT:
            self.script_thread = runners.HotScriptRunner(SCRIPT_NAME, self.output_queue)
            self.script_thread.start()

    name = "Kotlin Workspace"
    update_interval = 100  # ms

    file_location_pattern = re.compile(
        fr'{SCRIPT_BASENAME}(\.{SCRIPT_EXT})?:(?P<row>\d+)(?::(?P<col>\d+))?'
    )

    def _init_ui(self):
        self.root = tk.Tk()
        self.root.title(self.name)
        self.root.geometry('600x400')
        self.root.update()

        self.buttonbar = tk.Frame(self.root)
        self.buttonbar.pack(side='top', fill='x')

        self.input_pane = self._make_text_pane(self.root, width=1, height=1)
        self.input_pane.pack(side='left', fill='both', expand=True)
        self.input_pane.insert('1.0', self.default_script)

        self.output_pane = self._make_text_pane(self.root, readonly=True, width=1, height=1)
        self.output_pane.pack(side='right', fill='both', expand=True)
        self.output_pane.tag_config('stderr', foreground='red')
        self.output_pane.hyperlink_manager = ui_helpers.HyperlinkManager(self.output_pane)

        self.run_button = self._make_button(self.buttonbar, "Run script", 'icon_run.png', self.run_script)
        self.run_button.pack(side='left')

        self.stop_button = self._make_button(self.buttonbar, "Stop script", 'icon_stop.png', self.stop_script)
        self.stop_button.pack(side='left')

        self.loading_icon = self._make_animated_icon(self.buttonbar, 'loading.gif', "Running script...")
        self.loading_icon.pack(side='right')

        self.success_icon = self._make_icon(self.buttonbar, 'icon_success.png', "Finished with exit code 0")
        self.success_icon.pack(side='right')
        ui_helpers.hide_widget(self.success_icon)

        self.error_icon = self._make_icon(self.buttonbar, 'icon_error.png', "")
        self.error_icon.pack(side='right')
        ui_helpers.hide_widget(self.error_icon)

        self.set_busy(False)

    def _add_tooltip(self, widget, text=None):
        if text is None: return
        widget.balloon = Pmw.Balloon(self.root)
        widget.balloon.bind(widget, text)

    def _make_animated_icon(self, parent, icon, tooltip=None):
        label = ui_helpers.AnimatedImageLabel(parent, self._resolve_asset(icon))

        self._add_tooltip(label, tooltip)

        return label

    def _make_button(self, parent, text, icon, command):
        photo = tk.PhotoImage(file=self._resolve_asset(icon))
        photo = photo.subsample(4, 4)

        button = tk.Button(parent, image=photo, command=command)
        button.image = photo

        self._add_tooltip(button, text)

        return button

    def _make_icon(self, parent, icon, tooltip=None):
        photo = tk.PhotoImage(file=self._resolve_asset(icon))
        photo = photo.subsample(4, 4)

        label = tk.Label(parent, image=photo)
        label.image = photo

        self._add_tooltip(label, tooltip)

        return label

    def _make_text_pane(self, parent, readonly=False, **kwargs):
        text_pane = tk.scrolledtext.ScrolledText(parent, **kwargs)
        if readonly:
            @contextlib.contextmanager
            def _unlocked():
                text_pane.configure(state='normal')
                try:
                    yield
                finally:
                    text_pane.configure(state='disabled')
            text_pane.unlocked = _unlocked
            text_pane.configure(state='disabled')

        # BUG: Copy only works once (likely by design of Tkinter)
        text_pane.bind('<Control-c>', lambda e: text_pane.event_generate('<<Copy>>'))
        text_pane.bind('<Control-v>', lambda e: text_pane.event_generate('<<Paste>>'))
        text_pane.bind('<Control-x>', lambda e: text_pane.event_generate('<<Cut>>'))

        return text_pane

    def _resolve_asset(self, name):
        return f'{os.path.dirname(__file__)}/assets/{name}'

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.end_script()

    @property
    def busy(self):
        return self.loading_icon.visible

    def set_busy(self, busy):
        self.loading_icon.visible = busy

        self.run_button['state'] = 'disabled' if busy else 'normal'
        self.stop_button['state'] = 'normal' if busy else 'disabled'

    def run_script(self):
        if self.busy:
            return

        self.set_busy(True)
        ui_helpers.hide_widget(self.success_icon)
        ui_helpers.hide_widget(self.error_icon)

        script = self.input_pane.get('1.0', tk.END)

        # clear output
        with self.output_pane.unlocked():
            self.output_pane.delete('1.0', tk.END)

        # start script
        if USE_HOT_SCRIPT:
            self.script_thread.write(script)
        else:
            self.script_thread = runners.ScriptRunner(SCRIPT_NAME, self.output_queue, script)
            self.script_thread.start()

        # start output loop
        self.root.after(100, self.update_output)

    def stop_script(self):
        if not self.busy:
            return

        self.script_thread.stop()

    def end_script(self):
        if USE_HOT_SCRIPT:
            self.script_thread.end()
        else:
            self.stop_script()

    def update_output(self):
        while not self.output_queue.empty():
            item = self.output_queue.get()
            item_type = item[0]

            if item_type == 'exit':
                exit_code = item[1]
                if exit_code == 0:
                    ui_helpers.show_widget(self.success_icon)
                else:
                    self.error_icon.balloon.unbind(self.error_icon)
                    self.error_icon.balloon.bind(self.error_icon, f"Finished with exit code {exit_code}")
                    ui_helpers.show_widget(self.error_icon)
                self.set_busy(False)
                return

            chunk = item[1]
            if item_type == 'stdout':
                with self.output_pane.unlocked():
                    self.output_pane.insert(tk.END, chunk)
            elif item_type == 'stderr':
                with self.output_pane.unlocked():
                    # Scan new chunk for error messages and add all alternating
                    # matches/no-matches to the output pane with different
                    # tags. We cannot add the tags later because
                    # HyperlinkManager does not support tag_add.
                    index = 0

                    for match in self.file_location_pattern.finditer(chunk):
                        self.output_pane.insert(tk.END, chunk[index:match.start()], 'stderr')

                        row = int(match.group('row'))
                        col = int(match.group('col')) if match.group('col') else 0
                        start = f'1.0 + {match.start()} chars'
                        end = f'1.0 + {match.end()} chars'
                        self.output_pane.insert(
                            tk.END,
                            chunk[match.start():match.end()],
                            self._make_goto_hyperlink(row, col - 1)
                        )

                        index = match.end()

                    self.output_pane.insert(tk.END, chunk[index:], 'stderr')

        self.root.after(self.update_interval, self.update_output)

    def _make_goto_hyperlink(self, row, col):
        return self.output_pane.hyperlink_manager.add(
            lambda: self.goto(row, col)
        )

    def goto(self, row, col):
        self.input_pane.mark_set('insert', f'{row}.{col}')
        self.input_pane.see('insert')
        self.root.after(0, lambda: self.input_pane.focus_force())


def main():
    app = App()
    app.run()


if __name__ == '__main__':
    main()
