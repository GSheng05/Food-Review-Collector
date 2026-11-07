"""Food-review search vocabulary. These terms never assign sentiment labels."""
import json
from pathlib import Path


def load_food_keywords():
    data = json.loads(Path(__file__).with_name('food_search_keywords.json').read_text(encoding='utf-8'))
    terms = []
    for group in ('keywords', 'supplemental_keywords'):
        values = data.get(group)
        if not isinstance(values, list) or not values:
            raise ValueError('Keyword library must contain nonempty keyword lists.')
        for word in values:
            if not isinstance(word, str) or not word.strip() or ',' in word:
                raise ValueError('Keyword library terms must be nonempty strings without commas.')
            terms.append(word.strip().casefold())
    return list(dict.fromkeys(terms))
