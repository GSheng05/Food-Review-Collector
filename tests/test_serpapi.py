import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

from reviews.cli import main
from reviews.serpapi import request_page, resolve_place

URL = 'https://www.google.com/maps/place/Test/data=!1s0x123:0x456'


def page(start, stop, token=None):
    payload = {
        'place_info': {'title': 'Test Eatery'},
        'reviews': [{
            'review_id': str(i), 'source': 'Google', 'rating': 5,
            'snippet': 'Translation that must not be exported',
            'extracted_snippet': {'original': '  Sedap lah!\nGood \U0001f60b'},
            'details': {'price_per_person': 'RM 20\u201340'},
            'response': {'snippet': 'Owner reply'}
        } for i in range(start, stop)],
    }
    if token:
        payload['serpapi_pagination'] = {'next_page_token': token}
    return payload


class SerpApiTests(unittest.TestCase):
    def test_cli_pagination_caps_at_50_and_keeps_identical_text(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output'
            first, second = page(0, 30, 'next'), page(25, 65)
            del second['place_info']
            first['reviews'].extend([
                {'source': 'Google', 'extracted_snippet': {'original': ''}},
                {'source': 'Google', 'snippet': 'Possibly translated'},
                {'source': 'Trip.com', 'extracted_snippet': {'original': 'Other source'}},
            ])
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.request_page', side_effect=[first, second]) as request, \
                 patch('reviews.serpapi.time.sleep'):
                self.assertEqual(main([URL, '--provider', 'serpapi', '--output', str(out)]), 0)
            self.assertEqual(request.call_count, 2)
            rows = json.loads((out / 'reviews.json').read_text(encoding='utf-8'))
            self.assertEqual(len(rows), 50)
            self.assertTrue(all(r['raw_review'] == '  Sedap lah!\nGood \U0001f60b' for r in rows))
            self.assertEqual(rows[0]['price_range'], 'RM 20\u201340')
            self.assertEqual(rows[-1]['source_name'], 'Test Eatery')
            self.assertNotIn('_review_id', rows[0])
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['repeat_observations'], 5)
            self.assertEqual(manifest['skipped_without_original_text'], 2)
            self.assertEqual(manifest['skipped_non_google'], 1)

    def test_partial_result_survives_api_failure(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output'
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.request_page', side_effect=[page(0, 2, 'next'), RuntimeError('API failed')]), \
                 patch('reviews.serpapi.time.sleep'):
                self.assertEqual(main([URL, '--provider', 'serpapi', '--output', str(out)]), 2)
            self.assertEqual(len(json.loads((out / 'reviews.json').read_text(encoding='utf-8'))), 2)

    def test_repeated_token_stops(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output'
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.request_page', side_effect=[page(0, 2, 'same'), page(2, 4, 'same')]) as request, \
                 patch('reviews.serpapi.time.sleep'):
                self.assertEqual(main([URL, '--provider', 'serpapi', '--output', str(out)]), 2)
            self.assertEqual(request.call_count, 2)

    def test_credentials_are_not_in_http_errors(self):
        error = HTTPError('https://serpapi.com/search?api_key=private', 401, 'private', {}, None)
        with patch('reviews.serpapi.urlopen', side_effect=error):
            with self.assertRaises(RuntimeError) as result:
                request_page('private', {})
        self.assertNotIn('private', str(result.exception))
        self.assertIn('401', str(result.exception))

    def test_url_identity(self):
        self.assertEqual(resolve_place(URL)[1], '0x123:0x456')
        self.assertEqual(resolve_place(URL.replace(':0x', '%3A0x'))[1], '0x123:0x456')
        with self.assertRaises(ValueError):
            resolve_place('https://shopee.com.my/Food-i.1.2')
