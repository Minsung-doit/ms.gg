with open('static/js/app.js', 'r', encoding='utf-8') as f:
    lines = f.readlines()

brace_stack = [] # (char, line_no, col)
in_string = False
string_char = ''
in_line_comment = False
in_block_comment = False

for line_no, line in enumerate(lines, start=1):
    col = 0
    in_line_comment = False
    while col < len(line):
        c = line[col]
        
        # Check block comments
        if not in_string and not in_line_comment:
            if not in_block_comment and c == '/' and col + 1 < len(line) and line[col+1] == '*':
                in_block_comment = True
                col += 2
                continue
            elif in_block_comment and c == '*' and col + 1 < len(line) and line[col+1] == '/':
                in_block_comment = False
                col += 2
                continue

        if in_block_comment:
            col += 1
            continue

        # Check line comments
        if not in_string and c == '/' and col + 1 < len(line) and line[col+1] == '/':
            break

        # Check strings
        if c in ['"', "'", '`']:
            if not in_string:
                in_string = True
                string_char = c
            elif c == string_char:
                # check for escape
                escapes = 0
                k = col - 1
                while k >= 0 and line[k] == '\\':
                    escapes += 1
                    k -= 1
                if escapes % 2 == 0:
                    in_string = False
                    string_char = ''
            col += 1
            continue

        if in_string:
            col += 1
            continue

        # Braces
        if c in ['{', '(', '[']:
            brace_stack.append((c, line_no, col + 1))
        elif c in ['}', ')', ']']:
            if not brace_stack:
                print(f"[ERROR] Unmatched closing '{c}' at line {line_no}, col {col+1}")
            else:
                last_char, last_line, last_col = brace_stack.pop()
                expected = {'{': '}', '(': ')', '[': ']'}[last_char]
                if c != expected:
                    print(f"[MISMATCH] Opened '{last_char}' at line {last_line}:{last_col}, but closed with '{c}' at line {line_no}:{col+1}")

        col += 1

print(f"Parsing complete. Remaining unclosed in stack: {len(brace_stack)}")
if in_string:
    print(f"[UNCLOSED STRING] String char: {string_char}")
if in_block_comment:
    print("[UNCLOSED BLOCK COMMENT]")

if brace_stack:
    print("Unclosed elements (last 10):")
    for item in brace_stack[-10:]:
        print(f"  - '{item[0]}' opened at line {item[1]}, col {item[2]}: {lines[item[1]-1].strip()[:80]}")
