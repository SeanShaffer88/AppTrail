import queue
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

from .core import snapshot_folder, save_snapshot, load_snapshot, compare
from .report import export_report


class AppTrail:
    def __init__(self, root):
        self.root = root
        self.root.title('AppTrail — Application folder history')
        self.root.geometry('1100x760')
        self.root.minsize(850, 600)
        self.events = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.comparison = None
        self.buttons = []
        style = ttk.Style(root)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        style.configure('Title.TLabel', font=('Segoe UI', 26, 'bold'))
        style.configure('Subtitle.TLabel', font=('Segoe UI', 10), foreground='#51647a')
        style.configure('Treeview', rowheight=29, font=('Segoe UI', 10))
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='AppTrail', style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame, text='Capture a working baseline. Compare what changed. Keep the evidence.', style='Subtitle.TLabel').pack(anchor='w', pady=(0, 18))
        capture = ttk.LabelFrame(frame, text='1 · Snapshot an application folder', padding=12)
        capture.pack(fill='x')
        self.folder = tk.StringVar()
        ttk.Entry(capture, textvariable=self.folder).pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.button(capture, 'Choose folder…', self.choose_folder).pack(side='left', padx=4)
        self.button(capture, 'Save snapshot…', self.capture).pack(side='left', padx=4)
        compare_frame = ttk.LabelFrame(frame, text='2 · Compare saved snapshots', padding=12)
        compare_frame.pack(fill='x', pady=12)
        compare_frame.columnconfigure(1, weight=1)
        self.before = tk.StringVar()
        self.after = tk.StringVar()
        for row, (label, variable) in enumerate((('Before', self.before), ('After', self.after))):
            ttk.Label(compare_frame, text=label, width=8).grid(row=row, column=0, sticky='w', pady=4)
            ttk.Entry(compare_frame, textvariable=variable).grid(row=row, column=1, sticky='ew', padx=8)
            self.button(compare_frame, 'Browse…', lambda v=variable: self.choose_snapshot(v)).grid(row=row, column=2)
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=(0, 12))
        self.button(actions, 'Compare snapshots', self.compare_snapshots).pack(side='left')
        self.button(actions, 'Export HTML report…', self.export).pack(side='left', padx=8)
        self.show_unchanged = tk.BooleanVar(value=False)
        ttk.Checkbutton(actions, text='Show unchanged', variable=self.show_unchanged, command=self.refresh).pack(side='right')
        self.summary = tk.StringVar(value='Save two snapshots to see added, removed, and changed files.')
        ttk.Label(frame, textvariable=self.summary, style='Subtitle.TLabel').pack(anchor='w', pady=(0, 8))
        table = ttk.Frame(frame)
        table.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(table, columns=('status', 'path', 'notes'), show='headings', selectmode='browse', height=8)
        for column, width in (('status', 95), ('path', 290), ('notes', 550)):
            self.tree.heading(column, text=column.title())
            self.tree.column(column, width=width, minwidth=80)
        vertical = ttk.Scrollbar(table, orient='vertical', command=self.tree.yview)
        horizontal = ttk.Scrollbar(table, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        self.tree.bind('<Double-1>', self.details)
        ttk.Label(frame, text='Double-click a file for hashes and metadata. Warnings and full evidence are included in the report.', style='Subtitle.TLabel').pack(anchor='w', pady=8)
        bottom = ttk.Frame(frame)
        bottom.pack(fill='x')
        self.status = tk.StringVar(value='Ready · Files stay on this computer')
        ttk.Label(bottom, textvariable=self.status).pack(side='left', fill='x', expand=True)
        self.cancel_button = ttk.Button(bottom, text='Cancel capture', command=self.stop.set, state='disabled')
        self.cancel_button.pack(side='right')
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x', pady=(8, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.after(100, self.poll)

    def button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.buttons.append(button)
        return button

    def choose_folder(self):
        path = filedialog.askdirectory(title='Choose the application folder')
        if path:
            self.folder.set(path)

    def choose_snapshot(self, variable):
        path = filedialog.askopenfilename(title='Choose an AppTrail snapshot', filetypes=[('AppTrail JSON', '*.json')])
        if path:
            variable.set(path)

    def run_job(self, job, cancellable=False):
        self.busy = True
        self.stop.clear()
        for button in self.buttons:
            button.configure(state='disabled')
        self.cancel_button.configure(state='normal' if cancellable else 'disabled')
        self.progress.start(12)

        def worker():
            try:
                self.events.put(('done', job()))
            except Exception as exc:
                self.events.put(('error', str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def capture(self):
        folder = self.folder.get()
        if not Path(folder).is_dir() or not folder:
            messagebox.showerror('Choose a folder', 'Select an application folder first.')
            return
        output = filedialog.asksaveasfilename(title='Save snapshot outside the application folder',
                    defaultextension='.json', initialfile='application.apptrail.json', filetypes=[('AppTrail snapshot', '*.json')])
        if not output:
            return
        resolved, target = Path(folder).resolve(), Path(output).resolve()
        if resolved == target or resolved in target.parents:
            messagebox.showerror('Choose another location', 'Save snapshots outside the application folder.')
            return
        def job():
            snapshot = snapshot_folder(folder, lambda m: self.events.put(('progress', m)), self.stop.is_set)
            if self.stop.is_set():
                raise InterruptedError('Snapshot cancelled.')
            save_snapshot(snapshot, output)
            return ('snapshot', output, snapshot)
        self.status.set('Starting capture…')
        self.run_job(job, cancellable=True)

    def compare_snapshots(self):
        before, after = self.before.get(), self.after.get()
        if not before or not after:
            messagebox.showerror('Choose snapshots', 'Choose both the before and after snapshot.')
            return
        self.run_job(lambda: ('comparison', compare(load_snapshot(before), load_snapshot(after))))

    def poll(self):
        latest = None
        for _ in range(250):
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == 'progress':
                latest = payload
                continue
            self.busy = False
            self.progress.stop()
            self.cancel_button.configure(state='disabled')
            for button in self.buttons:
                button.configure(state='normal')
            latest = None
            if kind == 'error':
                self.status.set('Operation stopped')
                messagebox.showerror('AppTrail', payload)
            elif payload[0] == 'snapshot':
                _, output, snapshot = payload
                if not self.before.get():
                    self.before.set(output)
                else:
                    self.after.set(output)
                count = len(snapshot['warnings']) + sum(bool(e.get('error')) for e in snapshot['files'])
                self.status.set(f"Saved {len(snapshot['files'])} files · {count} capture issues · {output}")
                messagebox.showinfo('Snapshot saved', f"Captured {len(snapshot['files'])} files.\nCapture issues: {count}\n\n{output}")
            else:
                self.comparison = payload[1]
                self.refresh()
                self.status.set('Comparison ready · Export a report to preserve the evidence')
        if latest:
            self.status.set(latest[:150])
        self.root.after(100, self.poll)

    def refresh(self):
        if not self.comparison:
            return
        self.tree.delete(*self.tree.get_children())
        for index, change in enumerate(self.comparison['changes']):
            if change['status'] != 'Unchanged' or self.show_unchanged.get():
                self.tree.insert('', 'end', iid=str(index), values=(change['status'], change['path'], ' · '.join(change['notes'])))
        summary = '   |   '.join(f'{k}: {v}' for k, v in self.comparison['counts'].items())
        issues = sum(len(self.comparison[k]['warnings']) + sum(bool(e.get('error')) for e in self.comparison[k]['files']) for k in ('before', 'after'))
        self.summary.set(summary + (f'   |   Capture issues: {issues}' if issues else ''))

    def details(self, event=None):
        selection = self.tree.selection()
        if not selection or not self.comparison:
            return
        change = self.comparison['changes'][int(selection[0])]
        import json
        window = tk.Toplevel(self.root)
        window.title(change['path'])
        window.geometry('820x600')
        from tkinter.scrolledtext import ScrolledText
        text = ScrolledText(window, wrap='word', font=('Consolas', 10), padx=16, pady=16)
        text.pack(fill='both', expand=True)
        text.insert('1.0', json.dumps(change, indent=2, ensure_ascii=False))
        text.configure(state='disabled')

    def export(self):
        if not self.comparison:
            messagebox.showinfo('Compare first', 'Compare two snapshots before exporting a report.')
            return
        path = filedialog.asksaveasfilename(title='Export readable report', defaultextension='.html',
                         initialfile='AppTrail-report.html', filetypes=[('HTML report', '*.html')])
        if path:
            # Protect the input snapshots from accidental replacement.
            if Path(path).resolve() in (Path(self.before.get()).resolve(), Path(self.after.get()).resolve()):
                messagebox.showerror('Choose another path', 'The report cannot replace an input snapshot.')
                return
            try:
                export_report(self.comparison, path)
            except OSError as exc:
                messagebox.showerror('Export failed', str(exc))
                return
            self.status.set(f'Report saved · {path}')
            webbrowser.open(Path(path).resolve().as_uri())

    def close(self):
        if self.busy:
            self.stop.set()
        self.root.destroy()


def main():
    root = tk.Tk()
    AppTrail(root)
    root.mainloop()
