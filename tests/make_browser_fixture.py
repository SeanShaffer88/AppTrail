"""Generate synthetic offline reports for the browser regression checks."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from apptrail.side_report import export_side_report
from tests.test_side_diff import change

output = Path(sys.argv[1])
before = ''.join(f'value_{i:03d} = {i}\n' if i != 5 else 'value_005 = "😀 café [a.*] needle"\n' for i in range(120))
after = before.replace('value_020 = 20', 'value_020 = 200').replace('value_100 = 100', 'value_100 = 1000')
export_side_report(change(before, after), {'collapse_unchanged': True, 'context_lines': 3,
                   'show_words': True, 'show_endings': True}, output)
legacy = change('old', 'new')
legacy['before'].pop('text')
legacy['before']['text_status'] = 'legacy'
export_side_report(legacy, {}, output.with_suffix('.empty.html'))
export_side_report(change('a' * 10001, 'a' * 10002), {}, output.with_suffix('.limit.html'))
