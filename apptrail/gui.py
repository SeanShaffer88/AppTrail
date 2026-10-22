import queue
import threading
import sqlite3
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import webbrowser

from .core import snapshot_folder, save_snapshot, compare
from .report import export_report
from .history import SnapshotHistory
from .textdiff import build_diff, diff_text, side_by_side, side_line
from .syntax import highlight_lines
from .theme import Theme
from .search import find_matches
from .folding import unchanged_ranges
from .side_report import export_side_report
from .preferences import read_preferences, write_preference, context_lines, diff_options, MAX_CONTEXT_LINES


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
        self.theme = Theme(root, self.history.directory / 'preferences.json')
        style.configure('Title.TLabel', font=('Segoe UI', 26, 'bold'))
        style.configure('Subtitle.TLabel', font=('Segoe UI', 10))
        style.configure('Treeview', rowheight=29, font=('Segoe UI', 10))
        style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill='both', expand=True)
        heading = ttk.Frame(frame)
        heading.pack(fill='x')
        ttk.Label(heading, text='AppTrail', style='Title.TLabel').pack(side='left')
        ttk.Checkbutton(heading, text='Terminal dark theme', variable=self.theme.mode,
                        onvalue='dark', offvalue='light', command=self.change_theme).pack(side='right')
        ttk.Label(frame, text='Capture a working baseline. Compare what changed. Keep the evidence.', style='Subtitle.TLabel').pack(anchor='w', pady=(0, 18))
        capture = ttk.LabelFrame(frame, text='1 · Snapshot an application folder', padding=12)
        capture.pack(fill='x')
        self.folder = tk.StringVar()
        ttk.Entry(capture, textvariable=self.folder).pack(side='left', fill='x', expand=True, padx=(0, 8))
        self.button(capture, 'Choose folder…', self.choose_folder).pack(side='left', padx=4)
        self.button(capture, 'Capture to history', self.capture).pack(side='left', padx=4)
        self.button(capture, 'Save JSON…', lambda: self.capture(save_as=True)).pack(side='left', padx=4)
        self.include_text = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, text='Capture source/config text for diffs · snapshots and reports may contain private code or secrets',
                        variable=self.include_text).pack(anchor='w', pady=(6, 0))
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
        self.button(actions, 'View text diff…', self.details).pack(side='left')
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
        ttk.Label(comparison_frame, text='Double-click a file for its saved text diff, hashes, and metadata. Older snapshots may not contain text.', style='Subtitle.TLabel').pack(anchor='w', pady=8)
        bottom = ttk.Frame(frame)
        bottom.pack(before=self.tabs, side='bottom', fill='x')
        self.status = tk.StringVar(value='Ready · Files stay on this computer')
        ttk.Label(bottom, textvariable=self.status, wraplength=930).pack(side='left', fill='x', expand=True)
        self.cancel_button = ttk.Button(bottom, text='Cancel capture', command=self.stop.set, state='disabled')
        self.cancel_button.pack(side='right')
        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.pack(before=bottom, side='bottom', fill='x', pady=(8, 0))
        root.protocol('WM_DELETE_WINDOW', self.close)
        self.refresh_history()
        self.poll_id = root.after(100, self.poll)

    def change_theme(self):
        # Checkbutton has already changed the value; toggle saves and applies it.
        self.theme.mode.set('light' if self.theme.mode.get() == 'dark' else 'dark')
        self.theme.toggle()

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
        self.show_trash = tk.BooleanVar(value=False)
        ttk.Checkbutton(toolbar, text='Show Trash', variable=self.show_trash, command=self.refresh_history).pack(side='left', padx=8)
        self.history_tree = ttk.Treeview(table, columns=('label', 'date', 'root', 'files', 'issues'),
                                        show='headings', selectmode='extended', height=5)
        for key, label, width in (('label', 'Snapshot name', 200), ('date', 'Captured (local time)', 170),
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
        self.history_tree.bind('<<TreeviewSelect>>', self.history_selection_changed)
        self.history_tree.bind('<Double-1>', lambda event: self.edit_history())
        self.history_tree.bind('<Control-a>', self.select_all_history)
        self.history_tree.bind('<Control-A>', self.select_all_history)
        actions = ttk.Frame(frame)
        actions.pack(fill='x', pady=12)
        self.button(actions, 'Compare selected (2)', self.compare_history).pack(side='left')
        self.button(actions, 'Use as Before', lambda: self.use_history(self.before)).pack(side='left', padx=8)
        self.button(actions, 'Use as After', lambda: self.use_history(self.after)).pack(side='left')
        self.button(actions, 'Mark as baseline', self.mark_baseline).pack(side='left', padx=8)
        self.button(actions, 'Compare with baseline', self.compare_baseline).pack(side='left')
        organize = ttk.Frame(frame)
        organize.pack(fill='x', pady=(0, 8))
        self.button(organize, 'Edit name & notes…', self.edit_history).pack(side='left')
        self.button(organize, 'Move to Trash…', self.trash_history).pack(side='left', padx=8)
        self.button(organize, 'Restore selected', self.restore_history).pack(side='left')
        self.button(organize, 'Delete permanently…', self.purge_history).pack(side='left', padx=8)
        self.selection_info = tk.StringVar(value='Select a snapshot to see its notes. Double-click to edit.')
        ttk.Label(frame, textvariable=self.selection_info, style='Subtitle.TLabel', wraplength=1020).pack(anchor='w', pady=(0, 8))
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
            entries = self.history.entries(self.history_filter.get(), deleted=self.show_trash.get())
        except (OSError, ValueError, sqlite3.Error) as exc:
            self.history_summary.set(f'Could not load history: {exc}')
            return
        self.history_entries = {e['id']: e for e in entries}
        self.history_tree.delete(*self.history_tree.get_children())
        for entry in entries:
            date = datetime.fromtimestamp(entry['captured_ts']).astimezone().strftime('%Y-%m-%d %H:%M:%S')
            self.history_tree.insert('', 'end', iid=entry['id'], values=(('★ ' if entry['baseline'] else '') + entry['label'], date, entry['root'],
                entry['file_count'], entry['issues'] if entry['available'] else 'Missing JSON'))
        self.history_tree.selection_set([identity for identity in selected if identity in self.history_entries])
        self.history_summary.set(f'{len(entries)} snapshot(s) in {"Trash" if self.show_trash.get() else "history"} · Stored locally and available after restart')
        self.history_selection_changed()

    def select_all_history(self, event=None):
        self.history_tree.selection_set(self.history_tree.get_children())
        return 'break'

    def history_selection_changed(self, event=None):
        selected = self.history_tree.selection()
        if len(selected) == 1 and selected[0] in self.history_entries:
            entry = self.history_entries[selected[0]]
            note = ' '.join(entry['notes'].split()) or 'No notes yet.'
            self.selection_info.set(f'{entry["label"]} · {note[:180]}' + ('…' if len(note) > 180 else ''))
        elif len(selected) > 1:
            self.selection_info.set(f'{len(selected)} snapshots selected')
        else:
            self.selection_info.set('Select a snapshot to see its notes. Double-click to edit.')

    def selected_history(self, single=False, trash=False):
        if self.busy:
            return ()
        selected = self.history_tree.selection()
        if self.show_trash.get() != trash:
            messagebox.showinfo('Choose a history view', 'Turn on Show Trash first.' if trash else 'Turn off Show Trash to use active snapshots.')
            return ()
        if not selected or (single and len(selected) != 1):
            messagebox.showinfo('Choose snapshots', 'Select one snapshot.' if single else 'Select at least one snapshot.')
            return ()
        return selected

    def edit_history(self):
        selected = self.selected_history(single=True)
        if not selected:
            return
        try:
            entry = self.history.get(selected[0])
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror('Snapshot unavailable', str(exc))
            return
        return SnapshotEditor(self.root, self.history, entry, self.metadata_saved)

    def metadata_saved(self, identity):
        self.refresh_history()
        if identity in self.history_entries:
            self.history_tree.selection_set(identity)
            self.history_tree.see(identity)
        if self.comparison:
            self.comparison['context'] = self.history.comparison_context(self.comparison_paths)
        self.status.set('Snapshot name and notes saved. Captured evidence is unchanged.')

    def mark_baseline(self):
        selected = self.selected_history(single=True)
        if not selected:
            return
        try:
            self.history.set_baseline(selected[0])
            self.refresh_history()
            if self.comparison:
                self.comparison['context'] = self.history.comparison_context(self.comparison_paths)
            self.status.set('Baseline set for this application folder. Select another capture to compare against it.')
        except (OSError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror('Cannot set baseline', str(exc))

    def compare_baseline(self):
        selected = self.selected_history(single=True)
        if not selected:
            return
        def job():
            pair = self.history.baseline_pair(selected[0])
            paths = tuple(str(self.history.path(identity)) for identity, _ in pair)
            comparison = compare(pair[0][1], pair[1][1])
            comparison['context'] = self.history.comparison_context(paths)
            return ('comparison', comparison, paths)
        self.status.set('Comparing with the baseline…')
        self.run_job(job)

    def clear_deleted_comparison(self, selected):
        paths = {self.history.path(identity) for identity in selected}
        for variable in (self.before, self.after):
            if variable.get() and Path(variable.get()).resolve() in paths:
                variable.set('')
        if any(Path(path).resolve() in paths for path in self.comparison_paths):
            self.comparison = None
            self.comparison_paths = ()
            self.tree.delete(*self.tree.get_children())
            self.summary.set('A comparison input moved to Trash. Restore it or choose another snapshot.')

    def trash_history(self):
        selected = self.selected_history()
        if not selected:
            return
        if not messagebox.askyesno('Move snapshots to Trash?', f'Move {len(selected)} snapshot(s) to Trash?\n\nYou can restore them later. Original imported JSON files are untouched.'):
            return
        try:
            self.history.trash(selected)
            self.clear_deleted_comparison(selected)
            self.refresh_history()
            self.status.set(f'Moved {len(selected)} snapshot(s) to Trash. Turn on Show Trash to restore them.')
        except (OSError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror('Could not move snapshots', str(exc))

    def restore_history(self):
        selected = self.selected_history(trash=True)
        if not selected:
            return
        try:
            self.history.restore(selected)
            self.refresh_history()
            self.status.set(f'Restored {len(selected)} snapshot(s). Turn off Show Trash to see them.')
        except (OSError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror('Could not restore snapshots', str(exc))

    def purge_history(self):
        selected = self.selected_history(trash=True)
        if not selected:
            return
        if not messagebox.askyesno('Permanently delete snapshots?', f'Permanently delete {len(selected)} trashed snapshot(s) and their notes?\n\nThis removes the library copies and cannot be undone. Original imported JSON files are untouched.', icon='warning', default='no'):
            return
        try:
            self.history.purge(selected)
            self.refresh_history()
            self.status.set(f'Permanently deleted {len(selected)} library snapshot(s).')
        except (OSError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror('Could not permanently delete snapshots', str(exc))

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
            comparison = compare(pair[0][1], pair[1][1])
            comparison['context'] = self.history.comparison_context(paths)
            return ('comparison', comparison, paths)
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
        capture_text = self.include_text.get()
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
            snapshot = snapshot_folder(folder, lambda m: self.events.put(('progress', m)), self.stop.is_set, capture_text=capture_text)
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
        def job():
            comparison = compare(self.history.load_path(before), self.history.load_path(after))
            comparison['context'] = self.history.comparison_context((before, after))
            return ('comparison', comparison, (before, after))
        self.run_job(job)

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
            self.refresh_history()
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
                self.show_trash.set(False)
                self.refresh_history()
                self.history_tree.selection_set(identity)
                self.history_tree.see(identity)
                self.tabs.select(self.history_tab)
                self.status.set(f"Saved to history · {len(snapshot['files'])} files · {count} capture issues" + (f' · JSON: {exported}' if exported else ''))
            elif payload[0] == 'imported':
                _, identities, errors = payload
                self.history_filter.set('')
                self.show_trash.set(False)
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
        return TextDiffWindow(self.root, change)

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


class TextDiffWindow(tk.Toplevel):
    def __init__(self, parent, change):
        super().__init__(parent)
        self.title(f'Text diff · {change["path"]}')
        self.geometry('1000x720')
        self.minsize(720, 500)
        self.model = build_diff(change)
        self.change = change
        theme = getattr(parent, '_apptrail_theme', None)
        self.preference_path = theme.path if theme else None
        preferences = read_preferences(self.preference_path)
        options = diff_options(preferences)
        self.aligned = side_by_side(change, options['ignore_whitespace'])
        self.syntax = {}
        for side in ('before', 'after'):
            entry = change.get(side) or {}
            self.syntax[side] = highlight_lines(change['path'], (entry.get('text') or {}).get('content', ''))
        self.change_index = -1
        self.folded = {}
        self.expanded_folds = set()
        self.collapse_unchanged = tk.BooleanVar(value=options['collapse_unchanged'])
        self.context_count = context_lines(preferences)
        self.context_value = tk.StringVar(value=str(self.context_count))
        frame = ttk.Frame(self, padding=16)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text=f'{change["status"]} · {change["path"]}', font=('Segoe UI', 14, 'bold'), wraplength=950).pack(anchor='w')
        ttk.Label(frame, text=self.model['message'], wraplength=950).pack(anchor='w', pady=(6, 10))
        ttk.Label(frame, text='Before: ' + self.model['before_summary'], wraplength=950, style='Subtitle.TLabel').pack(anchor='w')
        ttk.Label(frame, text='After: ' + self.model['after_summary'], wraplength=950, style='Subtitle.TLabel').pack(anchor='w', pady=(0, 8))
        self.show_endings = tk.BooleanVar(value=options['show_endings'])
        self.show_words = tk.BooleanVar(value=options['show_words'])
        controls = ttk.Frame(frame)
        controls.pack(fill='x', pady=(0, 8))
        ttk.Checkbutton(controls, text='Show line endings (CRLF / LF / CR / no final newline)',
                        variable=self.show_endings, command=lambda: self.save_diff_option('show_endings', self.refresh_diff)).pack(side='left')
        ttk.Checkbutton(controls, text='Highlight changed words', variable=self.show_words,
                        command=lambda: self.save_diff_option('show_words', self.refresh_diff)).pack(side='right')
        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill='both', expand=True)
        side_frame = ttk.Frame(self.tabs)
        self.tabs.add(side_frame, text='Side by side')
        toolbar = ttk.Frame(side_frame)
        toolbar.pack(fill='x', pady=(0, 6))
        self.previous_button = ttk.Button(toolbar, text='◀ Previous change', command=lambda: self.jump_change(-1))
        self.previous_button.pack(side='left')
        self.next_button = ttk.Button(toolbar, text='Next change ▶', command=lambda: self.jump_change(1))
        self.next_button.pack(side='left', padx=8)
        self.position = tk.StringVar(value=f'{len(self.aligned["changes"])} change(s)')
        ttk.Label(toolbar, textvariable=self.position).pack(side='left')
        self.ignore_whitespace = tk.BooleanVar(value=options['ignore_whitespace'])
        ttk.Checkbutton(toolbar, text='Ignore whitespace-only changes', variable=self.ignore_whitespace,
                        command=lambda: self.save_diff_option('ignore_whitespace', self.realign_diff)).pack(side='right')
        ignored = sum(row['ignored_whitespace'] for row in self.aligned['rows'])
        self.whitespace_status = tk.StringVar(value=(f'{ignored} whitespace-only row(s) ignored · saved text stays visible; unified diff stays exact'
                                                    if options['ignore_whitespace'] else ''))
        ttk.Label(side_frame, textvariable=self.whitespace_status, style='Subtitle.TLabel').pack(anchor='w')
        foldbar = ttk.Frame(side_frame)
        foldbar.pack(fill='x', pady=(0, 6))
        ttk.Checkbutton(foldbar, text='Collapse unchanged lines', variable=self.collapse_unchanged,
                        command=lambda: self.save_diff_option('collapse_unchanged', self.reset_folds)).pack(side='left')
        ttk.Label(foldbar, text='Context lines:').pack(side='left', padx=(12, 4))
        self.context_spin = ttk.Spinbox(foldbar, from_=0, to=MAX_CONTEXT_LINES, width=4,
                                       textvariable=self.context_value, command=self.set_context_lines)
        self.context_spin.pack(side='left')
        self.context_spin.bind('<Return>', self.set_context_lines)
        self.context_spin.bind('<FocusOut>', self.set_context_lines)
        ttk.Button(foldbar, text='Expand all', command=self.expand_all_folds).pack(side='left', padx=8)
        ttk.Button(foldbar, text='Collapse again', command=self.collapse_all_folds).pack(side='left')
        ttk.Button(foldbar, text='Export side-by-side HTML…', command=self.export_side_html).pack(side='right')
        searchbar = ttk.Frame(side_frame)
        searchbar.pack(fill='x', pady=(0, 6))
        ttk.Label(searchbar, text='Find:').pack(side='left')
        self.search_query = tk.StringVar()
        self.match_case = tk.BooleanVar(value=options['match_case'])
        self.search_entry = ttk.Entry(searchbar, textvariable=self.search_query, width=24)
        self.search_entry.pack(side='left', fill='x', expand=True, padx=6)
        ttk.Checkbutton(searchbar, text='Match case', variable=self.match_case,
                        command=lambda: self.save_diff_option('match_case', self.schedule_search)).pack(side='left', padx=4)
        self.previous_match = ttk.Button(searchbar, text='◀ Match', command=lambda: self.jump_match(-1), state='disabled')
        self.previous_match.pack(side='left')
        self.next_match = ttk.Button(searchbar, text='Match ▶', command=lambda: self.jump_match(1), state='disabled')
        self.next_match.pack(side='left', padx=6)
        ttk.Button(searchbar, text='Clear', command=self.clear_search).pack(side='left')
        self.search_status = tk.StringVar(value='Search both snapshots · Ctrl+F · F3 / Shift+F3')
        ttk.Label(side_frame, textvariable=self.search_status, style='Subtitle.TLabel').pack(anchor='w', pady=(0, 6))
        self.search_matches = []
        self.match_index = -1
        self.search_pending = None
        self.search_query.trace_add('write', lambda *_: self.schedule_search())
        self.search_entry.bind('<Return>', lambda event: self.jump_match(1))
        self.search_entry.bind('<Shift-Return>', lambda event: self.jump_match(-1))
        self.search_entry.bind('<Escape>', lambda event: self.clear_search())
        self.bind('<Control-f>', self.focus_search)
        self.bind('<Control-F>', self.focus_search)
        self.bind('<F3>', lambda event: self.jump_match(1))
        self.bind('<Shift-F3>', lambda event: self.jump_match(-1))
        self.bind('<Destroy>', self.cancel_search)
        panes = ttk.Frame(side_frame)
        panes.pack(fill='both', expand=True)
        self.side_texts = []
        for column, label in enumerate(('Before', 'After')):
            ttk.Label(panes, text=label, font=('Segoe UI', 10, 'bold')).grid(row=0, column=column, sticky='w')
            widget = tk.Text(panes, wrap='none', height=14, width=30, font=('Consolas', 10),
                             padx=6, pady=12, background='white', foreground='#17263b', exportselection=False)
            widget.grid(row=1, column=column, sticky='nsew')
            scroll = ttk.Scrollbar(panes, orient='horizontal', command=widget.xview)
            scroll.grid(row=2, column=column, sticky='ew')
            widget.configure(xscrollcommand=scroll.set)
            widget.tag_configure('changed', background='#ffeef0' if column == 0 else '#e6ffed')
            widget.tag_configure('spacer', background='#eef1f5')
            widget.tag_configure('current', borderwidth=1, relief='solid')
            widget._diff_side = 'remove' if column == 0 else 'add'
            self.side_texts.append(widget)
            panes.columnconfigure(column, weight=1, uniform='diff')
        self.side_scroll = ttk.Scrollbar(panes, orient='vertical', command=self.scroll_sides)
        self.side_scroll.grid(row=1, column=2, sticky='ns')
        panes.rowconfigure(1, weight=1)
        for widget in self.side_texts:
            widget.configure(yscrollcommand=lambda first, last, source=widget: self.sync_sides(source, first, last))
        self.bind('<F7>', lambda event: self.jump_change(1))
        self.bind('<Shift-F7>', lambda event: self.jump_change(-1))
        diff_frame = ttk.Frame(self.tabs)
        metadata_frame = ttk.Frame(self.tabs)
        self.tabs.add(diff_frame, text='Text diff')
        self.tabs.add(metadata_frame, text='Captured metadata')
        self.text = tk.Text(diff_frame, wrap='none', height=14, font=('Consolas', 10), padx=12, pady=12, background='white', foreground='#17263b')
        vertical = ttk.Scrollbar(diff_frame, orient='vertical', command=self.text.yview)
        horizontal = ttk.Scrollbar(diff_frame, orient='horizontal', command=self.text.xview)
        self.text.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.text.grid(row=0, column=0, sticky='nsew')
        vertical.grid(row=0, column=1, sticky='ns')
        horizontal.grid(row=1, column=0, sticky='ew')
        diff_frame.rowconfigure(0, weight=1)
        diff_frame.columnconfigure(0, weight=1)
        for kind, options in {'add': {'background': '#e6ffed', 'foreground': '#14532d'},
                              'remove': {'background': '#ffeef0', 'foreground': '#8b1a2b'},
                              'header': {'foreground': '#245d9e'}, 'hunk': {'background': '#eaf0fa', 'foreground': '#245d9e'},
                              'meta': {'foreground': '#785200'}}.items():
            self.text.tag_configure(kind, **options)
        from tkinter.scrolledtext import ScrolledText
        import json
        metadata = dict(change)
        for side in ('before', 'after'):
            if change.get(side) is not None:
                metadata[side] = dict(change[side])
                if metadata[side].get('text'):
                    metadata[side]['text'] = {'encoding': metadata[side]['text']['encoding'], 'content': '(saved content shown in Text diff tab)'}
        details = ScrolledText(metadata_frame, wrap='word', font=('Consolas', 10), padx=12, pady=12)
        details.pack(fill='both', expand=True)
        details.insert('1.0', json.dumps(metadata, indent=2, ensure_ascii=False))
        details.configure(state='disabled')
        ttk.Label(frame, text='Saved evidence only · stronger color = changed words · F7 / Shift+F7 jump between changes',
                  style='Subtitle.TLabel', wraplength=950).pack(before=self.tabs, side='bottom', anchor='w', pady=(8, 0))
        self.refresh_diff()
        theme = getattr(parent, '_apptrail_theme', None)
        if theme:
            theme.paint(self)

    def focus_search(self, event=None):
        self.tabs.select(0)
        self.search_entry.focus_set()
        self.search_entry.selection_range(0, 'end')
        return 'break'

    def save_diff_option(self, key, action):
        action()
        if self.preference_path is not None:
            try:
                write_preference(self.preference_path, key, bool(getattr(self, key).get()))
            except OSError:
                messagebox.showwarning('Diff preference', 'The diff option changed for this window, but the preference could not be saved.', parent=self)

    def export_side_html(self):
        path = filedialog.asksaveasfilename(parent=self, title='Export side-by-side HTML report',
                                          defaultextension='.html', filetypes=[('HTML report', '*.html')],
                                          initialfile='AppTrail-side-by-side.html')
        if not path:
            return
        self.set_context_lines()
        if self.search_pending is not None:
            self.update_search(preserve=True)
        theme = getattr(self.master, '_apptrail_theme', None)
        settings = {key: bool(getattr(self, key).get()) for key in
                    ('collapse_unchanged', 'ignore_whitespace', 'show_endings', 'show_words', 'match_case')}
        settings.update(context_lines=self.context_count, theme=theme.mode.get() if theme else 'dark')
        active = self.search_matches[self.match_index] if self.match_index >= 0 and self.search_matches else None
        try:
            export_side_report(self.change, settings, path,
                               folded_ranges=[(start, end) for start, (end, _) in self.folded.items()],
                               query=self.search_query.get(), active_match=active)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Cannot export side-by-side report', str(exc), parent=self)
            return
        messagebox.showinfo('Report exported', f'Side-by-side report saved to:\n{path}\n\nThe report includes saved source text, including collapsed sections. Review before sharing.', parent=self)

    def realign_diff(self):
        active = self.search_matches[self.match_index] if self.match_index >= 0 and self.search_matches else None
        self.aligned = side_by_side(self.change, self.ignore_whitespace.get())
        self.expanded_folds.clear()
        self.change_index = -1
        self.position.set(f'{len(self.aligned["changes"])} change(s)')
        ignored = sum(row['ignored_whitespace'] for row in self.aligned['rows'])
        self.whitespace_status.set(f'{ignored} whitespace-only row(s) ignored · saved text stays visible; unified diff stays exact'
                                   if self.ignore_whitespace.get() else '')
        for widget in self.side_texts:
            widget.tag_remove('current', '1.0', 'end')
        self.refresh_diff()
        if active:
            for index, match in enumerate(self.search_matches):
                if all(match[key] == active[key] for key in ('side', 'line', 'start', 'end')):
                    self.show_match(index)
                    break

    def cancel_search(self, event=None):
        if event is not None and event.widget is not self:
            return
        if self.search_pending is not None:
            self.after_cancel(self.search_pending)
            self.search_pending = None

    def schedule_search(self):
        self.cancel_search()
        self.search_matches = []
        self.match_index = -1
        for widget in self.side_texts:
            widget.tag_remove('search_match', '1.0', 'end')
            widget.tag_remove('search_current', '1.0', 'end')
        self.previous_match.configure(state='disabled')
        self.next_match.configure(state='disabled')
        self.search_status.set('Searching…' if self.search_query.get() else 'Search both snapshots · Ctrl+F · F3 / Shift+F3')
        self.search_pending = self.after(180, self.update_search)

    def update_search(self, preserve=False):
        self.cancel_search()
        old_index = self.match_index if preserve else 0
        self.search_matches, self.search_limited = find_matches(self.aligned['rows'], self.search_query.get(), self.match_case.get())
        for widget in self.side_texts:
            widget.tag_remove('search_match', '1.0', 'end')
            widget.tag_remove('search_current', '1.0', 'end')
        for match in self.search_matches:
            widget, start, end = self.match_range(match)
            widget.tag_add('search_match', start, end)
        state = 'normal' if self.search_matches else 'disabled'
        self.previous_match.configure(state=state)
        self.next_match.configure(state=state)
        if self.search_matches:
            self.show_match(max(0, min(old_index, len(self.search_matches) - 1)), reveal=not preserve)
        else:
            self.match_index = -1
            self.search_status.set('No matches in saved text' if self.search_query.get() else 'Search both snapshots · Ctrl+F · F3 / Shift+F3')

    def match_range(self, match):
        widget = self.side_texts[0 if match['side'] == 'before' else 1]
        content = self.aligned['rows'][match['row'] - 1][match['side']].rstrip('\r\n')
        offset = 1 if match['row'] in self.folded else 0
        start = int(widget.tk.call('string', 'length', content[:match['start']])) + 7 + offset
        end = int(widget.tk.call('string', 'length', content[:match['end']])) + 7 + offset
        return widget, f'{match["row"]}.{start}', f'{match["row"]}.{end}'

    def show_match(self, index, reveal=True):
        self.match_index = index
        match = self.search_matches[index]
        self.reveal_row(match['row'])
        for widget in self.side_texts:
            widget.tag_remove('search_current', '1.0', 'end')
        widget, start, end = self.match_range(match)
        widget.tag_add('search_current', start, end)
        widget.tag_raise('search_match')
        widget.tag_raise('search_current')
        if reveal:
            self.tabs.select(0)
            widget.see(start)
        total = str(len(self.search_matches)) + ('+' if self.search_limited else '')
        suffix = ' · limit reached; refine search' if self.search_limited else ''
        self.search_status.set(f'Match {index + 1} of {total} · {match["side"].title()} line {match["line"]}{suffix}')

    def jump_match(self, direction):
        if self.search_pending is not None:
            self.update_search()
            if direction < 0 and self.search_matches:
                self.show_match(len(self.search_matches) - 1)
        elif self.search_matches:
            self.show_match((self.match_index + direction) % len(self.search_matches))
        return 'break'

    def clear_search(self):
        self.search_query.set('')
        self.update_search()
        return 'break'

    def scroll_sides(self, *args):
        for widget in self.side_texts:
            widget.yview(*args)

    def clear_folds(self):
        for start in list(self.folded):
            self.expand_fold(start, remember=False)

    def expand_fold(self, start, remember=True):
        end, buttons = self.folded.pop(start)
        for widget, button in zip(self.side_texts, buttons):
            widget.configure(state='normal')
            widget.tag_delete(f'fold_{start}')
            widget.delete(f'{start}.0', f'{start}.1')
            widget.configure(state='disabled')
            button.destroy()
        if remember:
            self.expanded_folds.add((start, end))

    def reveal_row(self, row):
        for start, (end, _) in list(self.folded.items()):
            if start <= row < end:
                self.expand_fold(start)
                break

    def apply_folds(self):
        if not self.collapse_unchanged.get():
            return
        for start, end in unchanged_ranges(self.aligned['rows'], self.context_count):
            if (start, end) in self.expanded_folds:
                continue
            buttons = []
            for widget in self.side_texts:
                widget.configure(state='normal')
                button = ttk.Button(widget, text=f'▶ {end - start} unchanged rows · expand',
                                    command=lambda row=start: self.expand_fold(row))
                widget.window_create(f'{start}.0', window=button)
                widget.tag_configure(f'fold_{start}', elide=True)
                widget.tag_add(f'fold_{start}', f'{start}.1', f'{start}.end')
                widget.tag_add(f'fold_{start}', f'{start + 1}.0', f'{end}.0')
                widget.configure(state='disabled')
                buttons.append(button)
            self.folded[start] = (end, buttons)

    def expand_all_folds(self):
        for start in list(self.folded):
            self.expand_fold(start)

    def reset_folds(self):
        self.expanded_folds.clear()
        self.refresh_diff()

    def set_context_lines(self, event=None):
        try:
            value = int(self.context_value.get())
            if not 0 <= value <= MAX_CONTEXT_LINES:
                raise ValueError
        except ValueError:
            self.context_value.set(str(self.context_count))
            self.bell()
            return 'break'
        self.context_value.set(str(value))
        if value != self.context_count:
            self.context_count = value
            self.reset_folds()
            if self.preference_path is not None:
                try:
                    write_preference(self.preference_path, 'context_lines', value)
                except OSError:
                    messagebox.showwarning('Context preference', 'Context lines changed for this window, but the preference could not be saved.', parent=self)
        return 'break'

    def collapse_all_folds(self):
        self.collapse_unchanged.set(True)
        self.save_diff_option('collapse_unchanged', self.reset_folds)

    def sync_sides(self, source, first, last):
        if getattr(self, '_syncing', False):
            return
        self._syncing = True
        try:
            self.side_scroll.set(first, last)
            for widget in self.side_texts:
                if widget is not source and abs(widget.yview()[0] - float(first)) > .00001:
                    widget.yview_moveto(first)
        finally:
            self._syncing = False

    def jump_change(self, direction):
        changes = self.aligned['changes']
        if not changes:
            return
        if self.change_index < 0:
            self.change_index = 0 if direction > 0 else len(changes) - 1
        else:
            self.change_index = (self.change_index + direction) % len(changes)
        row = changes[self.change_index]
        self.reveal_row(row)
        self.tabs.select(0)
        for widget in self.side_texts:
            widget.tag_remove('current', '1.0', 'end')
            widget.tag_add('current', f'{row}.0', f'{row}.end')
            widget.yview(f'{max(1, row - 3)}.0')
        self.position.set(f'Change {self.change_index + 1} of {len(changes)}')

    def refresh_diff(self):
        self.clear_folds()
        for side, widget in zip(('before', 'after'), self.side_texts):
            widget.configure(state='normal')
            widget.delete('1.0', 'end')
            if not self.aligned['rows']:
                widget.insert('1.0', self.model['message'])
            for display_row, row in enumerate(self.aligned['rows'], 1):
                tag = 'spacer' if row[side] is None else 'changed' if row['kind'] != 'equal' else 'context'
                widget.insert('end', side_line(row[side + '_number'], row[side], self.show_endings.get()), (tag,))
                number = row[side + '_number']
                if number is not None:
                    widget.tag_add('line_number', f'{display_row}.0', f'{display_row}.7')
                    content = row[side].rstrip('\r\n')
                    for start, end, category in self.syntax[side][1][number - 1]:
                        # Tcl 8.6 counts supplementary Unicode as surrogate pairs.
                        a = int(widget.tk.call('string', 'length', content[:start])) + 7
                        b = int(widget.tk.call('string', 'length', content[:end])) + 7
                        widget.tag_add('syntax_' + category, f'{display_row}.{a}', f'{display_row}.{b}')
                    if self.show_words.get():
                        for start, end in row[side + '_words']:
                            a = int(widget.tk.call('string', 'length', content[:start])) + 7
                            b = int(widget.tk.call('string', 'length', content[:end])) + 7
                            widget.tag_add('word_change', f'{display_row}.{a}', f'{display_row}.{b}')
                        if row['ending_changed'] and self.show_endings.get():
                            start = int(widget.tk.call('string', 'length', content)) + 7
                            widget.tag_add('word_change', f'{display_row}.{start}', f'{display_row}.end')
            widget.configure(state='disabled')
        state = 'normal' if self.aligned['changes'] else 'disabled'
        self.previous_button.configure(state=state)
        self.next_button.configure(state=state)
        if self.change_index >= 0:
            self.change_index -= 1
            self.jump_change(1)
        self.text.configure(state='normal')
        self.text.delete('1.0', 'end')
        if not self.model['lines']:
            self.text.insert('1.0', self.model['message'])
        else:
            for line in self.model['lines']:
                rendered = diff_text({'lines': [line]}, self.show_endings.get())
                self.text.insert('end', rendered, (line['kind'],))
        self.text.configure(state='disabled')
        self.apply_folds()
        self.update_search(preserve=True)


class SnapshotEditor(tk.Toplevel):
    def __init__(self, parent, history, entry, on_saved):
        super().__init__(parent)
        self.history, self.identity, self.on_saved = history, entry['id'], on_saved
        self.title('Edit snapshot name and notes')
        self.geometry('640x440')
        self.minsize(480, 340)
        self.transient(parent)
        frame = ttk.Frame(self, padding=20)
        frame.pack(fill='both', expand=True)
        ttk.Label(frame, text='Snapshot name (up to 120 characters)').pack(anchor='w')
        self.name = tk.StringVar(value=entry['label'])
        name_entry = ttk.Entry(frame, textvariable=self.name)
        name_entry.pack(fill='x', pady=(6, 14))
        ttk.Label(frame, text='Notes · build, commit, test result, or reason for capture').pack(anchor='w')
        from tkinter.scrolledtext import ScrolledText
        self.notes = ScrolledText(frame, wrap='word', height=8, font=('Segoe UI', 10))
        self.notes.pack(fill='both', expand=True, pady=6)
        self.notes.insert('1.0', entry['notes'])
        ttk.Label(frame, text='Names and notes are stored separately from immutable snapshot evidence.',
                  style='Subtitle.TLabel', wraplength=580).pack(anchor='w', pady=8)
        buttons = ttk.Frame(frame)
        buttons.pack(fill='x')
        ttk.Button(buttons, text='Save changes', command=self.save).pack(side='right')
        ttk.Button(buttons, text='Cancel', command=self.destroy).pack(side='right', padx=8)
        self.bind('<Escape>', lambda event: self.destroy())
        self.grab_set()
        name_entry.focus_set()
        name_entry.selection_range(0, 'end')
        theme = getattr(parent, '_apptrail_theme', None)
        if theme:
            theme.paint(self)

    def save(self):
        try:
            self.history.update_metadata(self.identity, self.name.get(), self.notes.get('1.0', 'end-1c'))
        except (OSError, ValueError, sqlite3.Error) as exc:
            messagebox.showerror('Cannot save snapshot details', str(exc), parent=self)
            return
        self.on_saved(self.identity)
        self.destroy()


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
