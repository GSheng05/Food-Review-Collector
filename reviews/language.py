"""Provisional Malay/English word labels using Malaya's dictionary and model."""
import re
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=128)
def name_pattern(source_name):
    rules = json.loads(Path(__file__).with_name('language_names.json').read_text(encoding='utf-8'))
    food_names = rules['food_names']
    source_aliases = rules['source_aliases']
    if (not isinstance(food_names, list) or not isinstance(source_aliases, dict)
            or any(not isinstance(name, str) or not name.strip() for name in food_names)
            or any(not isinstance(key, str) or not isinstance(aliases, list)
                   or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
                   for key, aliases in source_aliases.items())):
        raise ValueError('Invalid food names or source aliases in language_names.json.')
    names = list(food_names)
    if source_name.strip():
        names.append(source_name)
        # A title such as "Gepuklah by mingchuun" also identifies "Gepuklah".
        base_name = re.split(r'\s+by\s+|\s*\(', source_name, maxsplit=1, flags=re.I)[0].strip()
        if base_name:
            names.append(base_name)
        for title, aliases in source_aliases.items():
            if title.casefold() == source_name.casefold():
                names.extend(aliases)
    expressions = []
    for name in names:
        parts = re.split(r'\s+', name.strip())
        expressions.append(r'(?<!\w)' + r'[\s-]+'.join(re.escape(part) for part in parts) + r'(?!\w)')
    return re.compile('|'.join(sorted(expressions, key=len, reverse=True)) or r'(?!)', re.I)


def text_without_names(text, source_name=''):
    """Mask complete names for detection only. Never alter the exported review."""
    return name_pattern(source_name).sub(' ', text)


class MalayClassifier:
    def __init__(self):
        name_pattern("")
        try:
            import malaya
            import enchant
            self.english = enchant.Dict("en_US")
            model = malaya.language_detection.fasttext(
                model='mesolitica/fasttext-language-detection-v1')
            self.detector = malaya.language_detection.substring_rules(model=model)
        except Exception as exc:
            raise RuntimeError(
                'Could not load Malaya. Install requirements-language.txt and allow the '
                'first-run model download. Details: ' + type(exc).__name__
            ) from exc

    def classify(self, text, source_name=""):
        text = text_without_names(text, source_name)
        words = re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)*", text.casefold())
        if not words:
            return None
        labels = self.detector.predict(
            words, acceptable_ms_label=['malay'],
            acceptable_en_label=['eng', 'manglish'])
        # Shared entries (for example English "was") are ambiguous evidence.
        # Prefer English for dictionary overlap; require an unambiguous MS token.
        labels = [
            'EN' if label == 'MS' and self.english.check(word) else label
            for word, label in zip(words, labels)
        ]
        has_malay = 'MS' in labels
        has_english = 'EN' in labels
        if has_malay and has_english:
            return 'Code-switched'
        if has_malay:
            return 'Malay'
        if has_english:
            return 'English'
        return None
