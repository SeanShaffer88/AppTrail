"""Bounded source/config text capture and diffs of saved evidence, never live files."""
import difflib
import hashlib
from pathlib import PurePosixPath

MAX_TEXT_BYTES = 256 * 1024
MAX_TOTAL_TEXT_BYTES = 8 * 1024 * 1024
MAX_TEXT_LINES = 3000
POLICY = 'source-config-v1'
ENCODINGS = ('utf-8', 'utf-16-le', 'utf-16-be', 'utf-32-le', 'utf-32-be')
EXTENSIONS = set('''.py .pyw .pyi .js .jsx .mjs .cjs .ts .tsx .json .jsonc .yaml .yml .toml
.ini .cfg .conf .config .xml .cs .csproj .fs .fsproj .vb .vbproj .sln .slnx .props .targets .resx
.c .cpp .cc .cxx .h .hpp .hxx .rs .go .java .kt .kts .sh .ps1 .psm1 .psd1 .bat .cmd .sql
.html .htm .css .scss .less .md .rst .txt .vue .svelte .rb .php .swift .cmake .gradle .proto
.graphql .gql .gitignore .gitattributes .editorconfig .dockerignore'''.split())
FILENAMES = {'makefile', 'dockerfile', 'cmakelists.txt', '.gitignore', '.gitattributes', '.editorconfig', '.dockerignore'}
STATUS_MESSAGES = {
    'legacy': 'This older snapshot did not capture text. Take new snapshots with text capture enabled.',
    'disabled': 'Text capture was disabled for this snapshot.',
    'excluded': 'Text was excluded by the credential/private-directory policy.',
    'not_eligible': 'This file type is outside the source/config text capture policy.',
    'too_large': 'The file exceeded the 256 KiB text capture limit.',
    'line_limit': 'The file exceeded the 3,000-line text capture limit.',
    'budget_exceeded': 'The snapshot reached its 8 MiB total text capture budget.',
    'unsupported': 'The file was binary or not valid UTF-8 / BOM-marked UTF-16 / UTF-32 text.',
    'unstable': 'The file changed during capture; its text was discarded.',
    'read_error': 'The file could not be read reliably.',
    'captured': 'Text captured.',
}


def eligibility(path):
    path = PurePosixPath(path)
    name = path.name.casefold()
    if '.git' in {part.casefold() for part in path.parts} or name.startswith(('.env', 'secrets.', 'credentials.')) or name in {'.npmrc', '.pypirc', '.netrc'}:
        return 'excluded'
    if path.suffix.casefold() not in EXTENSIONS and name not in FILENAMES:
        return 'not_eligible'
    return 'eligible'


def decode_text(raw):
    if raw.startswith(b'\xff\xfe\0\0'):
        encoding = 'utf-32-le'
    elif raw.startswith(b'\0\0\xfe\xff'):
        encoding = 'utf-32-be'
    elif raw.startswith(b'\xff\xfe'):
        encoding = 'utf-16-le'
    elif raw.startswith(b'\xfe\xff'):
        encoding = 'utf-16-be'
    else:
        encoding = 'utf-8'
    try:
        content = raw.decode(encoding, errors='strict')
    except UnicodeError:
        return None, 'unsupported'
    if any(ord(char) < 32 and char not in '\t\r\n\f' for char in content):
        return None, 'unsupported'
    if len(content.splitlines()) > MAX_TEXT_LINES:
        return None, 'line_limit'
    return {'encoding': encoding, 'content': content}, 'captured'


def validate_text(entry):
    payload = entry.get('text')
    status = entry.get('text_status')
    if status is not None and status not in STATUS_MESSAGES:
        raise ValueError('Invalid text capture status.')
    if payload is None:
        if status == 'captured':
            raise ValueError('Captured text is missing.')
        return 0
    if not isinstance(payload, dict) or payload.get('encoding') not in ENCODINGS or not isinstance(payload.get('content'), str):
        raise ValueError('Invalid captured text payload.')
    content = payload['content']
    if len(content) > MAX_TEXT_BYTES:
        raise ValueError('Captured text exceeds the file limit.')
    try:
        raw = content.encode(payload['encoding'], errors='strict')
    except UnicodeError:
        raise ValueError('Invalid captured text encoding.') from None
    if len(raw) > MAX_TEXT_BYTES or len(content.splitlines()) > MAX_TEXT_LINES:
        raise ValueError('Captured text exceeds size or line limits.')
    if status != 'captured' or entry.get('error') or entry.get('size') != len(raw) or hashlib.sha256(raw).hexdigest() != entry.get('sha256'):
        raise ValueError('Captured text does not match the file evidence.')
    decoded, expected_status = decode_text(raw)
    if expected_status != 'captured' or decoded != payload:
        raise ValueError('Captured text is not supported text evidence.')
    return len(raw)


def text_summary(entry):
    if entry is None:
        return 'Absent from this capture'
    payload = entry.get('text')
    if payload is None:
        return STATUS_MESSAGES.get(entry.get('text_status', 'legacy'), STATUS_MESSAGES['legacy'])
    content = payload['content']
    crlf = content.count('\r\n')
    lf = content.count('\n') - crlf
    cr = content.count('\r') - crlf
    endings = ', '.join(f'{name}: {count}' for name, count in (('CRLF', crlf), ('LF', lf), ('CR', cr)) if count) or 'no line endings'
    final = 'final newline' if content.endswith(('\n', '\r')) else 'no final newline'
    bom = ' · BOM' if content.startswith('\ufeff') else ''
    return f'{payload["encoding"]}{bom} · {entry["size"]} bytes · {endings} · {final}'


def build_diff(change):
    before, after = change.get('before'), change.get('after')
    result = {'state': 'unavailable', 'message': '', 'lines': [], 'added': 0, 'removed': 0,
              'before_summary': text_summary(before), 'after_summary': text_summary(after)}
    if before is not None and after is not None and before.get('sha256') and before['sha256'] == after.get('sha256') and not before.get('error') and not after.get('error'):
        result.update(state='unchanged', message='The captured file bytes are identical. There is no content diff.')
        return result
    missing = []
    for side, entry in (('Before', before), ('After', after)):
        if entry is not None and (entry.get('text') is None or entry.get('error') or not entry.get('sha256')):
            reason = STATUS_MESSAGES.get(entry.get('text_status', 'legacy'), STATUS_MESSAGES['legacy'])
            missing.append(f'{side}: {reason}')
    if missing:
        result['message'] = '\n'.join(missing) + '\nDiffs use saved text only; current files are never read to fill missing evidence.'
        return result
    if before is None and after is None:
        result['message'] = 'Neither capture contains this file.'
        return result
    def saved_lines(entry):
        content = entry['text']['content'] if entry is not None else ''
        if content.startswith('\ufeff'):
            content = content[1:]
        return content.splitlines(keepends=True)
    lines = difflib.unified_diff(saved_lines(before), saved_lines(after),
        fromfile='before/' + change['path'] if before is not None else '/dev/null',
        tofile='after/' + change['path'] if after is not None else '/dev/null', n=3)
    for index, line in enumerate(lines):
        kind = ('header' if index < 2 else 'hunk' if line.startswith('@@')
                else 'add' if line.startswith('+') else 'remove' if line.startswith('-') else 'context')
        result['lines'].append({'kind': kind, 'text': line})
        if kind in ('add', 'remove'):
            result['added' if kind == 'add' else 'removed'] += 1
        if kind in ('add', 'remove', 'context') and not line.endswith(('\r', '\n')):
            result['lines'].append({'kind': 'meta', 'text': '\\ No newline at end of file\n'})
    result['state'] = 'available'
    if result['lines']:
        result['message'] = f'{result["added"]} added line(s), {result["removed"]} removed line(s). Unified diff with 3 lines of context.'
    elif before is None or after is None:
        result['message'] = f'An empty text file is present only in the {"After" if before is None else "Before"} capture.'
    else:
        result['message'] = 'Decoded text is identical. The byte change is in encoding or the byte-order mark; see capture details above.'
    if before is None or after is None:
        result['message'] += ' Absence from one capture is not proof of deletion if that capture had read warnings.'
    return result


def diff_text(model, show_endings=False):
    output = []
    for line in model['lines']:
        text = line['text']
        if line['kind'] in ('add', 'remove', 'context') and show_endings:
            ending = 'CRLF' if text.endswith('\r\n') else 'LF' if text.endswith('\n') else 'CR' if text.endswith('\r') else 'no final newline'
            output.append(text.rstrip('\r\n') + f'  ⟦{ending}⟧\n')
        else:
            output.append(text.rstrip('\r\n') + '\n')
    return ''.join(output)
