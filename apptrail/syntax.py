"""Offline highlighting of saved text; never import or execute reviewed code."""
from pathlib import PurePosixPath
from pygments.lexers import (PythonLexer, JavascriptLexer, TypeScriptLexer, JsonLexer,
    YamlLexer, TOMLLexer, IniLexer, XmlLexer, HtmlLexer, CssLexer, CppLexer,
    CSharpLexer, RustLexer, GoLexer, JavaLexer, BashLexer, PowerShellLexer,
    SqlLexer, MarkdownLexer, DockerLexer, MakefileLexer)
from pygments.token import Comment, Keyword, String, Number, Name, Operator

LEXERS = {}
for extensions, lexer in (
    ('py pyw pyi', PythonLexer), ('js jsx mjs cjs', JavascriptLexer), ('ts tsx', TypeScriptLexer),
    ('json jsonc', JsonLexer), ('yaml yml', YamlLexer), ('toml', TOMLLexer),
    ('ini cfg conf config editorconfig', IniLexer), ('xml csproj fsproj vbproj props targets resx slnx', XmlLexer),
    ('html htm vue svelte', HtmlLexer), ('css scss less', CssLexer), ('c cpp cc cxx h hpp hxx', CppLexer),
    ('cs', CSharpLexer), ('rs', RustLexer), ('go', GoLexer), ('java kt kts', JavaLexer),
    ('sh', BashLexer), ('ps1 psm1 psd1', PowerShellLexer), ('sql', SqlLexer), ('md', MarkdownLexer)):
    for extension in extensions.split():
        LEXERS['.' + extension] = lexer


def highlight_lines(path, content):
    """Return language and per-line (start, end, category) character spans.

    Normalize only the lexer input; line endings remain in immutable evidence.
    Lex the entire document to preserve multiline strings and comment context.
    Unknown formats stay plain text rather than guessing a language.
    """
    path = PurePosixPath(path)
    factory = {'dockerfile': DockerLexer, 'makefile': MakefileLexer, '.editorconfig': IniLexer}.get(path.name.casefold())
    factory = factory or LEXERS.get(path.suffix.casefold())
    if path.suffix.casefold() == '.config' and content.lstrip('\ufeff \t\r\n').startswith('<'):
        factory = XmlLexer
    source = content[1:] if content.startswith('\ufeff') else content
    lines = source.splitlines(keepends=True)
    spans = [[] for _ in lines]
    if factory is None:
        return 'Plain text', spans
    lexer = factory()
    normalized = ''.join(line.rstrip('\r\n') + '\n' for line in lines)
    row = column = 0
    for _, token, value in lexer.get_tokens_unprocessed(normalized):
        category = next((name for parent, name in (
            (Comment, 'comment'), (Keyword, 'keyword'), (String, 'string'), (Number, 'number'),
            (Name.Function, 'function'), (Name.Class, 'type'), (Name.Builtin, 'type'), (Name.Tag, 'keyword'),
            (Name.Attribute, 'function'), (Operator, 'operator')) if token in parent), None)
        parts = value.split('\n')
        for index, part in enumerate(parts):
            if category and part and row < len(spans):
                spans[row].append((column, column + len(part), category))
            column += len(part)
            if index < len(parts) - 1:
                row += 1
                column = 0
    return lexer.name, spans
