# -*- coding: utf-8 -*-
path = r'd:\run\run\tools\database_toolkit.py'
with open(path, encoding='utf-8') as f:
    content = f.read()

original = content

# Fix 1: duplicate ordered_contents declaration
content = content.replace(
    '        ordered_contents: List[str] = []\n\n        ordered_contents: List[str] = []',
    '        ordered_contents: List[str] = []'
)

# Fix 2: f-string with nested same-quote (Python <3.12 syntax error)
# f"{"="*60}" -> use a variable instead
content = content.replace(
    '        _log_search(f"\\n{"="*60}")\n        _log_search(f"\U0001f50d [\u641c\u7d22\u5de5\u5177\u88ab\u8c03\u7528]")\n        _log_search(f"   query: \'{query[:80]}{"..." if len(query) > 80 else \'\'}\'") \n        if intent_description:\n            _log_search(f"   intent: \'{intent_description[:80]}{"..." if len(intent_description) > 80 else \'\'}\'") \n        _log_search(f"   hybrid={use_hybrid}, rerank={use_rerank}, dynamic={dynamic_topk}, alpha={alpha}")\n        _log_search(f"{"="*60}\\n")',
    '''        _sep = "=" * 60
        _log_search(f"\\n{_sep}")
        _log_search("\U0001f50d [\u641c\u7d22\u5de5\u5177\u88ab\u8c03\u7528]")
        _log_search(f"   query: \'{query[:80]}{\'...\' if len(query) > 80 else \'\'}\'") 
        if intent_description:
            _log_search(f"   intent: \'{intent_description[:80]}{\'...\' if len(intent_description) > 80 else \'\'}\'") 
        _log_search(f"   hybrid={use_hybrid}, rerank={use_rerank}, dynamic={dynamic_topk}, alpha={alpha}")
        _log_search(f"{_sep}\\n")'''
)

# Fix 3: f"{"="*60}\n" at the end of _search_database
content = content.replace(
    '        _log_search(f"{"="*60}\\n")',
    '        _log_search(f"{_sep}\\n")'
)

# Fix 4: multiline string inside f-string for formatted_results (invalid syntax)
# The content= and formatted_results lines with bare newlines inside f-string
old_fmt = '''            content = DatabaseToolkit._truncate_text(content, max_chars_per_chunk)
            formatted_results.append(
                f"File: {source}\nContent: \n---\n{content}\n---\nConfidence: {score:.4f}"
            )'''
new_fmt = '''            content = DatabaseToolkit._truncate_text(content, max_chars_per_chunk)
            result_str = (
                f"File: {source}\\n"
                f"Content: \\n---\\n{content}\\n---\\n"
                f"Confidence: {score:.4f}"
            )
            formatted_results.append(result_str)'''

if old_fmt in content:
    content = content.replace(old_fmt, new_fmt)
    print('Fixed formatted_results f-string')
else:
    print('formatted_results: checking alternate form...')
    # Try the raw form as it appears in file
    import re
    # Find and fix the append block
    pattern = r'formatted_results\.append\(\s*f"File: \{source\}[^"]*"\s*\)'
    match = re.search(pattern, content, re.DOTALL)
    if match:
        print(f'Found at: {repr(match.group()[:100])}')
    else:
        print('Not found by regex either')

# Fix 5: content join with bare newlines
old_join = 'return "\n\n".join(formatted_results)'
new_join = 'return "\\n\\n".join(formatted_results)'
# This one is fine as-is since it's a regular string not f-string, skip.

# Fix 6: content_clean replace newline
old_replace = 'content_clean = content.replace("\n", " ").strip()'
new_replace = 'content_clean = content.replace("\\n", " ").strip()'
# Also fine as regular string, skip.

if content != original:
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    print('File saved.')
else:
    print('No changes detected - checking for issues manually...')

# Syntax check
import ast
try:
    ast.parse(content)
    print('Syntax OK!')
except SyntaxError as e:
    print(f'SYNTAX ERROR: {e}')
    # Show the problematic line
    lines = content.splitlines()
    lineno = e.lineno or 0
    start = max(0, lineno - 3)
    end = min(len(lines), lineno + 3)
    for i, l in enumerate(lines[start:end], start+1):
        marker = '>>>' if i == lineno else '   '
        print(f'{marker} {i}: {repr(l)}')
