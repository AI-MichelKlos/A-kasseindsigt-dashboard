from pathlib import Path

p = Path('scripts/jobindsats_patch.py')
text = p.read_text(encoding='utf-8')
old = '    q = re.fullmatch(r"(\\d{4})Q(\\d)", text)\n'
new = '    q = re.fullmatch(r"(\\d{4})Q0?([1-4])", text)\n'
if text.count(old) != 1:
    raise RuntimeError(f'Forventede én kvartalsparser, fandt {text.count(old)}')
text = text.replace(old, new, 1)
p.write_text(text, encoding='utf-8')
