"""Provisional Malay/English word labels using Malaya's dictionary and model."""
import re


class MalayClassifier:
    def __init__(self):
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

    def classify(self, text):
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
