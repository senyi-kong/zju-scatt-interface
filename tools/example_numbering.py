"""Release numbering for the maintained research workflow collection."""
import re

NUMBERS = {f"{old:02}": f"{old if old < 5 else old-3:02}" for old in range(1,31)
           if old not in (5,6,7)}


def release_name(name):
    return NUMBERS.get(name[:2], name[:2]) + name[2:]


def release_text(text, filenames):
    """Rewrite references once; never replace scientific numeric values."""
    names = {name: release_name(name) for name in filenames}
    pattern = '|'.join(re.escape(name) for name in sorted(names, key=len, reverse=True))
    text = re.sub(pattern, lambda m: names[m[0]], text)
    # Human references are explicit, so wavelengths and model versions stay intact.
    text = re.sub(r'(?i)\b(example[- ]|script |configuration |shapes )(\d{2})\b',
                  lambda m: m[1] + NUMBERS.get(m[2],m[2]), text)
    text = text.replace('examples 14-16', 'examples 11-13')
    text = text.replace('example 11, 15 or 16', 'example 11, 12 or 13')
    text = re.sub(r'(EXAMPLES\[[\x22\x27])(15|16)', lambda m: m[1]+NUMBERS[m[2]],text)
    text = re.sub(r'([\x22\x27])(15|16)([\x22\x27]: dict)',lambda m: m[1]+NUMBERS[m[2]]+m[3],text)
    return text
