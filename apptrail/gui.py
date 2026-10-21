import queue
import threading
import sqlite3
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

from .core import snapshot_folder, save_snapshot, load_snapshot, compare
from .report import export_report
from .history import SnapshotHistory


class AppTrail:
    def __init__(self, root, history=None):
        self.root = root
        self.root.title('AppTrail — Application folder history')
        self.root.geometry('1160x820')
        self.root.minsize(950, 700)
        self.history = history if history is not None else SnapshotHistory()
        self.history_entries = {}
        self.comparison_paths = ()
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
        self.button(capture, 'Capture to history', self.capture).pack(side='left', padx=4)
        self.button(capture, 'Save JSON…', lambda: self.capture(save_as=True)).pack(side='left', padx=4)
        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill='both', expand=True, pady=(12, 0))
        history_frame = ttk.Frame(self.tabs, padding=12)
        comparison_frame = ttk.Frame(self.tabs, padding=12)
        self.tabs.add(history_frame, text='Snapshot history')
        self.tabs.add(comparison_frame, text='Comparison')
        self.history_tab = history_frame
        self.comparison_tab = comparison_frame
        self.build_history(history_frame)
        compare_frame = ttk.LabelFrame(comparison_frame, text='Compare snapshots · choose from history or browse JSON', padding=12)
        compare_frame.pack(fill='x', pady=12)
        compare_frame.columnconfigure(1, weight=1)
        self.before = tk.StringVar()
        self.after = tk.StringVar()
        for row, (label, variable) in enumerate((('Before', self.before), ('After', self.after))):
            ttk.Label(compare_frame, text=label, width=8).grid(row=row, column=0, sticky='w', pady=4)
            ttk.Entry(compare_frame, textvariable=variable).grid(row=row, column=1, sticky='ew', padx=8)
            self.button(compare_frame, 'Browse…', lambda v=variable: self.choose_snapshot(v)).grid(row=row, column=2)
        actions = ttk.Frame(comparison_frame)
        actions.pack(fill='x', pady=(0, 12))
        self.button(actions, 'Compare snapshots', self.compare_snapshots).pack(side='left')
        self.button(actions, 'Export HTML report…', self.export).pack(side='left', padx=8)
        self.show_unchanged = tk.BooleanVar(value=False)
        ttk.Checkbutton(actions, text='Show unchanged', variable=self.show_unchanged, command=self.refresh).pack(side='right')
        self.summary = tk.StringVar(value='Save two snapshots to see added, removed, and changed files.')
        ttk.Label(comparison_frame, textvariable=self.summary, style='Subtitle.TLabel', wraplength=1040).pack(anchor='w', pady=(0, 8))
        table = ttk.Frame(comparison_frame)
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
        ttk.Label(comparison_frame, text='Double-click a file for hashes and metadata. Warnings and full evidence are included in the report.', style='Subtitle.TLabel').pack(anchor='w', pady=8)
        bottom = ttk.Frame(frame)
        bottom.pack(fill='x')
        self.status = tk.StringVar(value='Ready · Files stay on this computer')
        ttk.Label(bottom, textvariable=self.status, wraplength=930).pack(side='left', fill='x', expand=True)
        self.cancel_button = ttk.Button(bottom, text='Cancel capture', command=self.stop.set, state='disabled')
        self.cancel_button.pack(side='right')
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(fill='x', pady=(8, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh_history()
        self.poll_id = root.after(100, self.poll)

    def build_history(self, frame):
        ttk.Label(frame, text='Saved snapshots', font=('Segoe UI', 16, 'bold')).pack(anchor='w')
        ttk.Label(frame, text='New captures are saved here automatically. Select two rows to compare; the older capture becomes Before.',
                  style='Subtitle.TLabel', wraplength=1020).pack(anchor='w', pady=(4, 12))
        toolbar = ttk.Frame(frame)
        toolbar.pack(fill='x', pady=(0, 10))
        ttk.Label(toolbar, text='Filter:').pack(side='left')
        self.history_filter = tk.StringVar()
        ttk.Entry(toolbar, textvariable=self.history_filter, width=35).pack(side='left', padx=8)
        self.history_filter.trace_add('write', lambda *_: self.refresh_history())
        self.button(toolbar, 'Import JSON…', self.import_history).pack(side='left', padx=4)
        self.button(toolbar, 'Refresh', self.refresh_history).pack(side='left', padx=4)
        self.button(toolbar, 'Storage location…', lambda: messagebox.showinfo('Snapshot history location',
            f'Your snapshots and catalog are stored in:\n\n{self.history.directory}\n\nThis library stays available when you update or move AppTrail.')).pack(side='left', padx=4)
        table = ttk.Frame(frame)
        table.pack(fill='both', expand=True)
        self.history_tree = ttk.Treeview(table, columns=('label', 'date', 'root', 'files', 'issues'),
                                        show='headings', selectmode='extended', height=8)
        for key, label, width in (('label', 'Application', 160), ('date', 'Captured (local time)', 170),
                                  ('root', 'Application folder', 430), ('files', 'Files', 65), ('issues', 'Issues / state', 110)):
            self.history_tree.heading(key, text=label)
            self.history_tree.column(key, width=width, minwidth=60)
        vertical = ttk.Scrollbar(table, orient='vertical', command=self.history_tree.yview)
        horizontal = ttk.Scrollbar(table, orient='horizontal', command=self.history_tree.xview)
        self.history_tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.history_tree.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        table.rowconfigure(0, weight=1)
        table.columnconfigure(0, weight=1)
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=12)
        self.button(actions, 'Compare selected (2)', self.compare_history).pack(side='left')
        self.button(actions, 'Use as Before', lambda: self.use_history(self.before)).pack(side='left', padx=8)
        self.button(actions, 'Use as After', lambda: self.use_history(self.after)).pack(side='left')
        self.history_summary = tk.StringVar()
        ttk.Label(frame, textvariable=self.history_summary, style='Subtitle.TLabel', wraplength=1020).pack(anchor='w')
        ttk.Label(frame, text='Use Ctrl-click or Shift-click to select two snapshots. Import keeps a local copy, so moving the original JSON will not break history.',
                  style='Subtitle.TLabel', wraplength=1020).pack(anchor='w', pady=(6, 0))

    def refresh_history(self):
        if self.busy:
            return
        from datetime import datetime
        selected = self.history_tree.selection()
        try:
            entries = self.history.entries(self.history_filter.get())
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.history_summary.set(f'Could not load history: {exc}')
            return
        self.history_entries = {e['id']: e for e in entries}
        self.history_tree.delete(*self.history_tree.get_children())
        for entry in entries:
            date = datetime.fromtimestamp(entry['captured_ts']).astimezone().strftime('%Y-%m-%d %H:%M:%S')
            self.history_tree.insert('', 'end', iid=entry['id'], values=(entry['label'], date, entry['root'],
                entry['file_count'], entry['issues'] if entry['available'] else 'Missing JSON'))
        self.history_tree.selection_set([identity for identity in selected if identity in self.history_entries])
        self.history_summary.set(f'{len(entries)} snapshot(s) · Stored locally and available after restart')

    def import_history(self):
        paths = filedialog.askopenfilenames(title='Import saved snapshots into history', filetypes=[('AppTrail JSON', '*.json')])
        if not paths:
            return
        def job():
            imported, errors = [], []
            for path in paths:
                try:
                    imported.append(self.history.import_file(path))
                except (OSError, ValueError, sqlite3.Error) as exc:
                    errors.append(f'{Path(path).name}: {exc}')
            return ('imported', imported, errors)
        self.status.set('Importing saved snapshots…')
        self.run_job(job)

    def use_history(self, variable):
        if self.busy:
            return
        selected = self.history_tree.selection()
        if len(selected) != 1:
            messagebox.showinfo('Choose a snapshot', 'Select one history row, then choose Before or After.')
            return
        try:
            self.history.load(selected[0])
        except (OSError, ValueError) as exc:
            messagebox.showerror('Snapshot unavailable', str(exc))
            return
        variable.set(str(self.history.path(selected[0])))
        self.status.set(f"Selected {'Before' if variable is self.before else 'After'}: {self.history_entries[selected[0]]['label']}")

    def compare_history(self):
        if self.busy:
            return
        selected = self.history_tree.selection()
        if len(selected) != 2:
            messagebox.showinfo('Choose two snapshots', 'Select exactly two history rows using Ctrl-click or Shift-click.')
            return
        def job():
            pair = self.history.compare_pair(selected)
            paths = tuple(str(self.history.path(identity)) for identity, _ in pair)
            return ('comparison', compare(pair[0][1], pair[1][1]), paths)
        self.status.set('Comparing snapshots from history…')
        self.run_job(job)

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

    def capture(self, save_as=False):
        if self.busy:
            return
        folder = self.folder.get()
        if not Path(folder).is_dir() or not folder:
            messagebox.showerror('Choose a folder', 'Select an application folder first.')
            return
        resolved = Path(folder).resolve()
        if resolved == self.history.directory or resolved in self.history.directory.parents or self.history.directory in resolved.parents:
            messagebox.showerror('Choose an application folder', 'This folder contains AppTrail history. Choose a narrower application folder to avoid capturing the history itself.')
            return
        output = None
        if save_as:
            output = filedialog.asksaveasfilename(title='Save snapshot outside the application folder',
                        defaultextension='.json', initialfile='application.apptrail.json', filetypes=[('AppTrail snapshot', '*.json')])
            if not output:
                return
            target = Path(output).resolve()
            if resolved == target or resolved in target.parents or self.history.directory == target or self.history.directory in target.parents:
                messagebox.showerror('Choose another location', 'Save exported JSON outside the application folder and the managed history directory.')
                return
        def job():
            snapshot = snapshot_folder(folder, lambda m: self.events.put(('progress', m)), self.stop.is_set)
            if self.stop.is_set():
                raise InterruptedError('Snapshot cancelled.')
            if output:
                save_snapshot(snapshot, output)
            try:
                identity = self.history.add(snapshot)
            except (OSError, ValueError, sqlite3.Error) as exc:
                if output:
                    raise ValueError(f'JSON saved to {output}, but adding it to history failed: {exc}') from exc
                raise
            return ('snapshot', str(self.history.path(identity)), snapshot, identity, output)
        self.status.set('Starting capture…')
        self.run_job(job, cancellable=True)

    def compare_snapshots(self):
        if self.busy:
            return
        before, after = self.before.get(), self.after.get()
        if not before or not after:
            messagebox.showerror('Choose snapshots', 'Choose both the before and after snapshot.')
            return
        self.run_job(lambda: ('comparison', compare(self.history.load_path(before), self.history.load_path(after)), (before, after)))

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
                _, output, snapshot, identity, exported = payload
                if not self.before.get():
                    self.before.set(output)
                else:
                    self.after.set(output)
                count = len(snapshot['warnings']) + sum(bool(e.get('error')) for e in snapshot['files'])
                self.history_filter.set('')
                self.refresh_history()
                self.history_tree.selection_set(identity)
                self.history_tree.see(identity)
                self.tabs.select(self.history_tab)
                self.status.set(f"Saved to history · {len(snapshot['files'])} files · {count} capture issues" + (f' · JSON: {exported}' if exported else ''))
            elif payload[0] == 'imported':
                _, identities, errors = payload
                self.history_filter.set('')
                self.refresh_history()
                self.history_tree.selection_set(list(dict.fromkeys(identities)))
                self.status.set(f'Imported {len(identities)} snapshot(s) · {len(errors)} failed')
                if errors:
                    messagebox.showwarning('Some imports failed', '\n'.join(errors))
            else:
                self.comparison = payload[1]
                self.comparison_paths = payload[2]
                self.before.set(self.comparison_paths[0])
                self.after.set(self.comparison_paths[1])
                self.refresh()
                self.tabs.select(self.comparison_tab)
                self.status.set('Comparison ready · Export a report to preserve the evidence')
        if latest:
            self.status.set(latest[:150])
        self.poll_id = self.root.after(100, self.poll)

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
            target = Path(path).resolve()
            if self.history.directory == target or self.history.directory in target.parents or target in tuple(Path(p).resolve() for p in self.comparison_paths):
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
        self.root.after_cancel(self.poll_id)
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        AppTrail(root)
    except (OSError, sqlite3.Error) as exc:
        root.withdraw()
        messagebox.showerror('AppTrail history unavailable', f'Cannot open the local snapshot library. No saved history was removed.\n\n{exc}', parent=root)
        root.destroy()
        return
    root.mainloop()
