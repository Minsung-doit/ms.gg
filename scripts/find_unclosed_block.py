with open('static/js/app.js', 'r', encoding='utf-8') as f:
    code = f.read()

pos = 0
n = len(code)
stack = [] # (type, pos, line_no, col_no)
line_no = 1
col_no = 1

while pos < n:
    c = code[pos]
    
    # Handle newlines
    if c == '\n':
        line_no += 1
        col_no = 1
        pos += 1
        continue
    elif c == '\r':
        pos += 1
        continue

    # 1. Single-line comment
    if c == '/' and pos + 1 < n and code[pos+1] == '/':
        pos += 2
        col_no += 2
        while pos < n and code[pos] != '\n':
            pos += 1
            col_no += 1
        continue

    # 2. Multi-line comment
    if c == '/' and pos + 1 < n and code[pos+1] == '*':
        pos += 2
        col_no += 2
        while pos + 1 < n and not (code[pos] == '*' and code[pos+1] == '/'):
            if code[pos] == '\n':
                line_no += 1
                col_no = 1
            else:
                col_no += 1
            pos += 1
        pos += 2
        col_no += 2
        continue

    # 3. Regular strings ' or "
    if c in ("'", '"'):
        quote = c
        start_line = line_no
        pos += 1
        col_no += 1
        while pos < n and code[pos] != quote:
            if code[pos] == '\\':
                pos += 2
                col_no += 2
            elif code[pos] == '\n':
                line_no += 1
                col_no = 1
                pos += 1
            else:
                pos += 1
                col_no += 1
        pos += 1 # skip closing quote
        col_no += 1
        continue

    # 4. Template literals `
    if c == '`':
        start_line = line_no
        pos += 1
        col_no += 1
        while pos < n and code[pos] != '`':
            if code[pos] == '\\':
                pos += 2
                col_no += 2
            elif code[pos] == '$' and pos + 1 < n and code[pos+1] == '{':
                # Expression inside template literal!
                stack.append(('`_expr', pos, line_no, col_no))
                pos += 2
                col_no += 2
                # We break out of template string mode and enter code mode until matching }
                break
            elif code[pos] == '\n':
                line_no += 1
                col_no = 1
                pos += 1
            else:
                pos += 1
                col_no += 1
        else:
            # ended normally with `
            if pos < n and code[pos] == '`':
                pos += 1
                col_no += 1
        continue

    # 5. Regex literal /.../
    # A slash is a regex if previous non-whitespace token is operator or keyword like (, =, :, [, ,, !, ;, return
    if c == '/':
        # simple heuristic: check previous char
        k = pos - 1
        while k >= 0 and code[k] in (' ', '\t', '\n', '\r'):
            k -= 1
        prev_char = code[k] if k >= 0 else ''
        if prev_char in ('(', '=', ':', '[', ',', '!', ';', '{', '&', '|', '?'):
            # regex literal
            pos += 1
            col_no += 1
            while pos < n and code[pos] != '/':
                if code[pos] == '\\':
                    pos += 2
                    col_no += 2
                elif code[pos] == '[':
                    # character class inside regex
                    while pos < n and code[pos] != ']':
                        if code[pos] == '\\': pos += 2
                        else: pos += 1
                    pos += 1
                else:
                    pos += 1
                    col_no += 1
            pos += 1 # skip /
            col_no += 1
            # flags like g, i, m
            while pos < n and code[pos] in ('g', 'i', 'm', 's', 'u', 'y'):
                pos += 1
                col_no += 1
            continue

    # 6. Braces
    if c in ('{', '(', '['):
        stack.append((c, pos, line_no, col_no))
    elif c in ('}', ')', ']'):
        if not stack:
            print(f"UNEXPECTED EXTRA CLOSING '{c}' at Line {line_no}:{col_no}")
        else:
            top = stack[-1]
            if top[0] == '`_expr' and c == '}':
                stack.pop()
                # Resume inside template literal
                # continue parsing template literal until next ` or ${
                while pos + 1 < n and code[pos+1] != '`':
                    pos += 1
                    col_no += 1
                    if code[pos] == '\\':
                        pos += 1
                        col_no += 1
                    elif code[pos] == '$' and pos + 1 < n and code[pos+1] == '{':
                        stack.append(('`_expr', pos, line_no, col_no))
                        pos += 1 # skip $
                        break
                    elif code[pos] == '\n':
                        line_no += 1
                        col_no = 1
                else:
                    if pos + 1 < n and code[pos+1] == '`':
                        pos += 1
                        col_no += 1
            else:
                expected = {'{': '}', '(': ')', '[': ']'}.get(top[0])
                if c == expected:
                    stack.pop()
                else:
                    print(f"MISMATCH: Expected '{expected}' (opened at Line {top[2]}:{top[3]}), got '{c}' at Line {line_no}:{col_no}")

    pos += 1
    col_no += 1

print(f"Done! Remaining items on stack: {len(stack)}")
for item in stack:
    # Print lines around the opening
    line_idx = item[2] - 1
    snippet = code.splitlines()[line_idx] if line_idx < len(code.splitlines()) else ""
    print(f"Unclosed '{item[0]}' opened at Line {item[2]}:{item[3]} -> {snippet.strip()[:80]}")
