"""Validate catalogues and regenerate the complete embedded English fallback."""
import argparse
import json
import pprint
from pathlib import Path
from package_release import validate_all
from psrtty.i18n import LANGUAGES

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--generate', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    count = validate_all(root / 'language')
    if args.generate:
        strings = json.loads((root / 'language/en.json').read_text(encoding='utf-8'))['strings']
        (root / 'psrtty/english_fallback.py').write_text(
            '\"\"\"Generated from language/en.json; run validate_languages.py --generate.\"\"\"\nSTRINGS = '
            + pprint.pformat(strings, sort_dicts=False, width=120) + '\n', encoding='utf-8')
    print(f'OK: {len(LANGUAGES)} languages, {count} entries each')
