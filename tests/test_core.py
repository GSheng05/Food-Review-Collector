import csv
import json
import tempfile
import unittest
from pathlib import Path
from reviews.core import Review, Store, platform_for, shopee_ids, shopee_reviews, HEADERS

URL = 'https://shopee.com.my/Food-i.123.456'
RESPONSE = 'https://shopee.com.my/api/v2/item/get_ratings?shopid=123&itemid=456&offset=0'


class CoreTests(unittest.TestCase):
    def row(self, id='1', text='Sedap lah! Really good.\n  Mantap 😋', **kwargs):
        return Review(id, text, URL, 'Food', 'shopee', **kwargs)

    def test_platforms_and_ids(self):
        for url in ['https://share.google/example', 'https://maps.app.goo.gl/example', 'https://www.google.com/maps/place/Food']:
            self.assertEqual(platform_for(url), 'google_maps')
        self.assertEqual(platform_for(URL), 'shopee')
        self.assertEqual(platform_for('https://my.shp.ee/QejgsfVB'), 'shopee')
        self.assertEqual(shopee_ids(URL), ('123', '456'))
        self.assertEqual(shopee_ids('https://shopee.com.my/product/123/456?x=1'), ('123', '456'))

    def test_reject_deceptive_or_unsupported_urls(self):
        for url in ['https://shopee.com.my.evil.org/x', 'file:///secret', 'http://shopee.com.my/x', 'https://user:pass@shopee.com.my/x', 'https://google.com/search?q=food']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                platform_for(url)

    def test_lossless_and_distinct_reviews_with_same_words(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(d, URL, 'shopee')
            text = '  Sedap, "wow"!\nBest 😋\t'
            self.assertEqual(store.add([self.row('1', text), self.row('2', text), self.row('3', '')]), 3)
            self.assertEqual(store.add([self.row('1', text)]), 0)
            store.save('test')
            rows = json.loads((Path(d) / 'reviews.json').read_text(encoding='utf-8'))
            self.assertEqual(rows[0]['raw_review'], text)
            self.assertEqual(rows[2]['raw_review'], '')
            with (Path(d) / 'reviews.csv').open(encoding='utf-8-sig', newline='') as f:
                csvrows = list(csv.reader(f))
            self.assertEqual(csvrows[0], HEADERS)
            self.assertEqual(csvrows[1][HEADERS.index('Review Text')], text)
            self.assertEqual(csvrows[1][HEADERS.index('Language Classification')], '')
            self.assertEqual(csvrows[1][HEADERS.index('Code-Switching Type')], '')
            self.assertEqual(store.manifest['empty_reviews'], 1)
            self.assertEqual(store.manifest['repeated_text_reviews'], 1)
            self.assertFalse(store.manifest['all_reviews_verified'])

    def test_public_schema_and_price_range(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(d, URL, 'google_maps')
            store.add([self.row(price_range='RM 20–40'), self.row('2')])
            store.save('test')
            rows = json.loads((Path(d) / 'reviews.json').read_text(encoding='utf-8'))
            self.assertEqual(set(rows[0]), {'raw_review', 'source_url', 'source_name', 'platform',
                                          'rating', 'review_date', 'price_range', 'collected_at', 'language_classification'})
            self.assertEqual(rows[0]['price_range'], 'RM 20–40')
            self.assertIsNone(rows[1]['price_range'])
            with (Path(d) / 'reviews.csv').open(encoding='utf-8-sig', newline='') as f:
                exported = list(csv.DictReader(f))
            self.assertEqual(exported[0]['Price Range'], 'RM 20–40')
            self.assertEqual(exported[1]['Price Range'], '')
            for removed in ['Review ID', 'Review URL', 'Product Category']:
                self.assertNotIn(removed, exported[0])
            self.assertEqual(store.add([self.row()]), 0)  # Identity still prevents repeat ingestion.

    def test_limit_does_not_overrun_batch(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(d, URL, 'shopee', limit=1)
            self.assertEqual(store.add([self.row('1'), self.row('2')]), 1)
            self.assertTrue(store.full)

    def test_same_id_on_different_products_not_collapsed(self):
        with tempfile.TemporaryDirectory() as d:
            store = Store(d, URL, 'shopee')
            a, b = self.row(), self.row()
            b.source_url = 'https://shopee.com.my/Food-i.123.789'
            self.assertEqual(store.add([a, b]), 2)

    def test_transient_windows_save_lock_is_retried(self):
        from unittest.mock import Mock, patch
        from reviews.core import replace_export
        temporary = Mock()
        temporary.replace.side_effect = [PermissionError('locked'), None]
        with patch('reviews.core.time.sleep'):
            replace_export(temporary, 'destination')
        self.assertEqual(temporary.replace.call_count, 2)

    def test_persistent_save_lock_is_reported(self):
        from unittest.mock import Mock, patch
        from reviews.core import replace_export
        temporary = Mock()
        temporary.replace.side_effect = PermissionError('locked')
        with patch('reviews.core.time.sleep'), self.assertRaises(PermissionError):
            replace_export(temporary, 'destination')
        self.assertEqual(temporary.replace.call_count, 5)

    def test_review_dates_export_without_time(self):
        cases = [
            ('2026-11-05T15:20:30Z', '2026-11-05'),
            ('2026-11-05T00:20:30.123+08:00', '2026-11-05'),
            ('2026-11-05 23:59:59-05:00', '2026-11-05'),
            ('2026-11-05', '2026-11-05'),
            ('2 weeks ago', '2 weeks ago'),
            (None, None),
        ]
        for source, expected in cases:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as directory:
                store = Store(directory, URL, 'shopee')
                row = self.row(review_date=source, collected_at='2026-11-05T16:00:00+00:00')
                store.add([row])
                store.save('test')
                saved = json.loads((Path(directory) / 'reviews.json').read_text(encoding='utf-8'))
                self.assertEqual(saved[0]['review_date'], expected)
                self.assertEqual(saved[0]['collected_at'], '2026-11-05T16:00:00+00:00')
                with (Path(directory) / 'reviews.csv').open(encoding='utf-8-sig', newline='') as stream:
                    self.assertEqual(next(csv.DictReader(stream))['Review Date'], expected or '')

    def payload(self):
        return {'error': 0, 'data': {'ratings': [
            {'cmtid': 1, 'itemid': 456, 'shopid': 123, 'comment': 'Sedap!\n  good 😋', 'rating_star': 5, 'ctime': 1700000000},
            {'cmtid': 2, 'itemid': 456, 'shopid': 123, 'comment': '', 'rating_star': 3},
            {'cmtid': 3, 'itemid': 999, 'shopid': 123, 'comment': 'Other product', 'rating_star': 4}]}}

    def test_shopee_original_empty_metadata_and_related_exclusion(self):
        rows = shopee_reviews(self.payload(), RESPONSE, URL, 'Food')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].raw_review, 'Sedap!\n  good 😋')
        self.assertEqual(rows[0].rating, 5)
        self.assertEqual(rows[0].review_date, '2023-11-14')
        self.assertEqual(rows[1].raw_review, '')
        self.assertIsNone(rows[1].review_date)
        self.assertIsNone(rows[0].price_range)  # Product listing price is not a reviewer's spend.

    def test_ignore_other_response(self):
        self.assertEqual(shopee_reviews(self.payload(), RESPONSE.replace('itemid=456', 'itemid=999'), URL, 'Food'), [])

    def test_shopee_schema_failure_is_explicit(self):
        for payload in [{'error': 1}, {'data': {}}, {'data': {'ratings': [{'itemid': 456, 'shopid': 123}]}}]:
            with self.assertRaises(ValueError):
                shopee_reviews(payload, RESPONSE, URL, 'Food')


if __name__ == '__main__':
    unittest.main()
