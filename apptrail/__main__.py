import argparse
from pathlib import Path
import sys
from .core import snapshot_folder, save_snapshot, load_snapshot, compare
from .report import export_report


def main():
    parser = argparse.ArgumentParser(description='AppTrail: local application folder history')
    sub = parser.add_subparsers(dest='command')
    snapshot = sub.add_parser('snapshot', help='Capture file hashes and binary metadata')
    snapshot.add_argument('folder')
    snapshot.add_argument('-o', '--output', required=True)
    snapshot.add_argument('--no-text', action='store_true', help='Capture hashes and metadata without saving source/config contents')
    diff = sub.add_parser('compare', help='Compare two saved snapshots and export HTML')
    diff.add_argument('before')
    diff.add_argument('after')
    diff.add_argument('-o', '--output', required=True)
    sub.add_parser('gui', help='Open desktop interface (default)')
    args = parser.parse_args()
    try:
        if args.command == 'snapshot':
            root, output = Path(args.folder).resolve(), Path(args.output).resolve()
            if root == output or root in output.parents:
                raise ValueError('Save snapshots outside the application folder.')
            result = snapshot_folder(root, capture_text=not args.no_text)
            save_snapshot(result, output)
            issues = len(result['warnings']) + sum(bool(e.get('error')) for e in result['files'])
            print(f"Saved {len(result['files'])} files; {issues} capture issues: {output}")
            return 2 if issues else 0
        if args.command == 'compare':
            if Path(args.output).resolve() in (Path(args.before).resolve(), Path(args.after).resolve()):
                raise ValueError('The report cannot replace an input snapshot.')
            comparison = compare(load_snapshot(args.before), load_snapshot(args.after))
            export_report(comparison, args.output)
            print(' | '.join(f'{key}: {value}' for key, value in comparison['counts'].items()))
            print(f'Report saved: {Path(args.output).resolve()}')
            return 0
        from .gui import main as gui
        gui()
        return 0
    except (OSError, ValueError, InterruptedError) as exc:
        print(f'AppTrail: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
