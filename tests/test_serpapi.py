import json
import io
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
    def setUp(self):
        classifier = patch('reviews.language.MalayClassifier')
        self.mock_classifier = classifier.start().return_value
        self.mock_classifier.classify.return_value = 'Code-switched'
        self.addCleanup(classifier.stop)

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

    def test_keyword_searches_are_separate_capped_and_deduplicated(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output'
            requests = []
            def response(key, params):
                requests.append(dict(params))
                return page(0, 5, 'ignored') if params['query'] == 'sedap' else page(3, 8, 'ignored')
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.request_page', side_effect=response), \
                 patch('reviews.serpapi.time.sleep'):
                result = main([URL, '--provider', 'serpapi', '--review-keywords',
                               'sedap, pedas,sedap', '--output', str(out)])
            self.assertEqual(result, 0)
            self.assertEqual([r['query'] for r in requests], ['sedap', 'pedas'])
            self.assertTrue(all(r['num'] == 5 and 'next_page_token' not in r for r in requests))
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['collected_reviews'], 8)
            self.assertEqual(manifest['repeat_observations'], 2)
            self.assertEqual(manifest['stop_reason'], 'keyword_search_end')

    def test_keyword_response_without_place_info_looks_up_name_once(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'output'
            requests = []
            def response(key, params):
                requests.append(dict(params))
                if 'query' not in params:
                    return {'place_info': {'title': 'Verified Eatery'}}
                if params['query'] == 'sedap':
                    return {'reviews': []}
                payload = page(0, 2)
                del payload['place_info']
                return payload
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.request_page', side_effect=response), \
                 patch('reviews.serpapi.time.sleep'):
                self.assertEqual(main([URL, '--provider', 'serpapi', '--review-keywords',
                                       'sedap,pedas', '--output', str(out)]), 0)
            self.assertEqual([r.get('query') for r in requests], ['sedap', None, 'pedas'])
            rows = json.loads((out / 'reviews.json').read_text(encoding='utf-8'))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['source_name'], 'Verified Eatery')
            manifest = json.loads((out / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['api_requests'], 3)

    def test_explicit_name_works_without_place_info(self):
        with tempfile.TemporaryDirectory() as temp:
            payload = page(0, 2)
            del payload['place_info']
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.request_page', return_value=payload) as request:
                self.assertEqual(main([URL, '--provider', 'serpapi', '--review-keywords', 'sedap',
                                       '--name', 'Verified Eatery', '--output', temp]), 0)
            self.assertEqual(request.call_count, 1)

    def test_name_lookup_respects_total_request_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.request_page', return_value={'reviews': []}) as request:
                self.assertEqual(main([URL, '--provider', 'serpapi', '--review-keywords', 'sedap',
                                       '--max-pages', '1', '--output', temp]), 2)
            self.assertEqual(request.call_count, 1)

    def test_library_keyword_search_preserves_text_and_has_no_sentiment_labels(self):
        from reviews.search_keywords import load_food_keywords
        terms = load_food_keywords()
        self.assertEqual(len(terms), len(set(terms)))
        self.assertIn('mantap', terms)
        self.assertIn('kecewa', terms)
        with tempfile.TemporaryDirectory() as temp:
            requests = []
            def response(key, params):
                requests.append(dict(params))
                return page(0, 2)
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.request_page', side_effect=response), \
                 patch('reviews.serpapi.time.sleep'):
                self.assertEqual(main([URL, '--provider', 'serpapi', '--keyword-library', 'food',
                                       '--review-keywords', 'sedap,extra', '--max-pages', '2',
                                       '--output', temp]), 2)
            self.assertEqual([r['query'] for r in requests], terms[:2])
            manifest = json.loads((Path(temp) / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['review_keywords'], terms + ['extra'])
            self.assertEqual(manifest['keyword_library'], 'food')
            rows = json.loads((Path(temp) / 'reviews.json').read_text(encoding='utf-8'))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]['raw_review'], '  Sedap lah!\nGood \U0001f60b')
            self.assertFalse(any('sentiment' in key.lower() for key in rows[0]))

    def test_successful_no_reviews_keyword_response_continues_to_next_term(self):
        empty = {'search_metadata': {'status': 'Success'},
                 'search_information': {'reviews_results_state': 'No reviews'}}
        responses = [page(0, 5), empty, page(5, 7)]
        with tempfile.TemporaryDirectory() as temp:
            def response(*args, **kwargs):
                return io.BytesIO(json.dumps(responses.pop(0)).encode())
            with patch('reviews.serpapi.load_key', return_value='private'), \
                 patch('reviews.serpapi.urlopen', side_effect=response), \
                 patch('reviews.serpapi.time.sleep'):
                result = main([URL, '--provider', 'serpapi', '--review-keywords',
                               'sedap,teruk,bagus', '--output', temp])
            self.assertEqual(result, 0)
            manifest = json.loads((Path(temp) / 'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['collected_reviews'], 7)
            self.assertEqual(manifest['empty_keyword_searches'], ['teruk'])
            self.assertEqual(manifest['api_requests'], 3)

    def test_unexplained_missing_review_list_still_fails(self):
        from reviews.serpapi import parse_reviews
        with self.assertRaises(ValueError):
            list(parse_reviews({'search_metadata': {'status': 'Success'}}, URL, 'Test', {}))

    def test_no_reviews_signal_does_not_hide_api_errors(self):
        payload = {'error': 'Invalid credentials',
                   'search_metadata': {'status': 'Success'},
                   'search_information': {'reviews_results_state': 'No reviews'}}
        with patch('reviews.serpapi.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())):
            with self.assertRaises(RuntimeError):
                request_page('private', {'query': 'teruk'})

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
