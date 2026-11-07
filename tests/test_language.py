import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from reviews.core import Review, Store
from reviews.language import MalayClassifier


class LanguageTests(unittest.TestCase):
    def test_word_labels_and_single_malay_word(self):
        model = MalayClassifier.__new__(MalayClassifier)
        model.detector = Mock()
        model.english = Mock()
        model.english.check.return_value = False
        for labels, expected in [(['MS'], 'Malay'), (['EN', 'MS'], 'Code-switched'),
                                 (['EN'], 'English'), (['OTHERS'], None)]:
            model.detector.predict.return_value = labels
            self.assertEqual(model.classify('test words'), expected)
        self.assertIsNone(model.classify('123 !'))

    def test_filter_before_saving_and_count_unique_rejections(self):
        model = Mock()
        model.classify.side_effect = ['English', 'Malay', 'Code-switched', None]
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory, 'https://www.google.com/maps/place/Test', 'google_maps',
                          limit=2, classifier=model)
            rows = [Review(str(i), text, 'https://www.google.com/maps/place/Test', 'Test', 'google_maps')
                    for i, text in enumerate(['Good food', 'Sedap', '  Food sedap!\\n', '123'])]
            self.assertEqual(store.add(rows), 2)
            self.assertTrue(store.full)
            store.add([rows[0]])
            self.assertEqual(store.manifest['skipped_without_malay'], 1)
            store.save('test')
            data = json.loads((Path(directory) / 'reviews.json').read_text(encoding='utf-8'))
            self.assertEqual([r['raw_review'] for r in data], ['Sedap', '  Food sedap!\\n'])
            self.assertEqual([r['language_classification'] for r in data], ['Malay', 'Code-switched'])
            with (Path(directory) / 'reviews.csv').open(encoding='utf-8-sig', newline='') as stream:
                table = list(csv.DictReader(stream))
            self.assertEqual([r['Language Classification'] for r in table], ['Malay', 'Code-switched'])
