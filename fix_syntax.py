for fname in [
    'src/backend/notes_generator.py',
    'src/backend/flashcard_generator.py',
    'src/backend/quiz_generator.py',
]:
    with open(fname, encoding='utf-8') as f:
        lines = f.readlines()

    changed = 0
    for i, line in enumerate(lines):
        if line.strip().endswith('))') and 'extractor fallback' in line:
            lines[i] = line.rstrip().rstrip(')') + ')\n'
            changed += 1
            print(f"Fixed {fname} line {i+1}")

    with open(fname, 'w', encoding='utf-8') as f:
        f.writelines(lines)

    print(f"{fname}: {changed} fixes applied")
