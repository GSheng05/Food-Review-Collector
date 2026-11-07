"""SerpAPI Google Maps adapter. API credentials and raw responses stay out of exports."""
import json
import os
import re
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode, urlsplit
from urllib.request import Request, urlopen

from .core import Review, platform_for

DATA_ID = re.compile(r'0x[0-9a-fA-F]+:0x[0-9a-fA-F]+')


def load_key(path):
    key = os.environ.get('SERPAPI_API_KEY') or os.environ.get('SERPAPI_KEY')
    if not key:
        key_file = Path(path)
        if key_file.is_file():
            key = key_file.read_text(encoding='utf-8-sig')
    if not key or not key.strip():
        raise ValueError('Set SERPAPI_API_KEY or save your key in .serpapi-key in the project folder.')
    return key.strip()


def resolve_place(url):
    if platform_for(url) != 'google_maps':
        raise ValueError('SerpAPI collection requires a Google Maps restaurant URL.')
    matches = set(DATA_ID.findall(unquote(url)))
    if not matches:
        try:
            with urlopen(Request(url, headers={'User-Agent': 'FoodReviewCollector/1.0'}), timeout=30) as response:
                url = response.geturl()
        except (OSError, URLError):
            raise ValueError('Could not resolve the Maps link. Use its full restaurant URL.') from None
        if platform_for(url) != 'google_maps':
            raise ValueError('The Maps link redirected outside Google Maps.')
        matches = set(DATA_ID.findall(unquote(url)))
    if len(matches) != 1:
        raise ValueError('Use a single full Maps place URL containing its 0x...:0x... identifier.')
    return url, matches.pop()


def request_page(key, params):
    request_url = 'https://serpapi.com/search.json?' + urlencode(dict(params, api_key=key))
    try:
        with urlopen(request_url, timeout=90) as response:
            payload = json.load(response)
    except HTTPError as exc:
        # HTTPError and network exception strings can contain the API key URL.
        raise RuntimeError(f'SerpAPI HTTP {exc.code}. Check your key, credits and service status.') from None
    except (OSError, URLError):
        raise RuntimeError('SerpAPI connection failed. Check your network and try again.') from None
    except ValueError:
        raise RuntimeError('SerpAPI returned invalid JSON.') from None
    if (isinstance(payload, dict) and params.get('query')
            and payload.get('error') == "Google hasn't returned any results for this query."):
        return {'reviews': []}
    if (isinstance(payload, dict) and params.get('query') and not payload.get('error')
            and (payload.get('search_metadata') or {}).get('status') == 'Success'
            and (payload.get('search_information') or {}).get('reviews_results_state') == 'No reviews'
            and payload.get('reviews') is None):
        payload['reviews'] = []
    if not isinstance(payload, dict) or payload.get('error'):
        raise RuntimeError('SerpAPI reported an API error. Check your SerpAPI dashboard for details.')
    return payload


def parse_reviews(payload, source_url, source_name, manifest):
    entries = payload.get('reviews')
    if not isinstance(entries, list):
        raise ValueError('SerpAPI reviews response schema changed or reviews are unavailable.')
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Invalid SerpAPI review entry.')
        if entry.get('source') != 'Google':
            manifest['skipped_non_google'] += 1
            continue
        extracted = entry.get('extracted_snippet') or {}
        raw = extracted.get('original') if isinstance(extracted, dict) else None
        if not isinstance(raw, str) or not raw.strip():
            manifest['skipped_without_original_text'] += 1
            continue
        review_id = entry.get('review_id')
        if not isinstance(review_id, str) or not review_id:
            raise ValueError('SerpAPI review is missing its identity.')
        details = entry.get('details') or {}
        price = details.get('price_per_person') if isinstance(details, dict) else None
        rating = entry.get('rating')
        if rating is not None and (type(rating) not in (float, int) or not 1 <= rating <= 5):
            raise ValueError('SerpAPI review rating is invalid.')
        date = entry.get('iso_date') or entry.get('date')
        if date is not None and not isinstance(date, str):
            raise ValueError('SerpAPI review date is invalid.')
        yield Review(review_id, raw, source_url, source_name, 'google_maps',
                     rating, date, price_range=price if isinstance(price, str) else None)


def collect(store, args, key):
    source_url, data_id = resolve_place(args.url)
    store.manifest.update(provider='serpapi', source_url=source_url,
                          extraction='SerpAPI extracted_snippet.original',
                          sort_by='qualityScore', api_requests=0,
                          skipped_non_google=0, skipped_without_original_text=0)
    params = {'engine': 'google_maps_reviews', 'data_id': data_id,
              'hl': 'en', 'sort_by': 'qualityScore'}
    tokens = set()
    source_name = None
    deadline = time.monotonic() + args.max_minutes * 60
    keywords = args.review_keywords or []
    store.manifest['review_keywords'] = keywords
    store.manifest['keyword_library'] = args.keyword_library
    store.manifest['empty_keyword_searches'] = []
    for index in range(args.max_pages):
        if store.manifest['api_requests'] >= args.max_pages:
            return 'api_page_limit'
        if keywords:
            params['query'] = keywords[index]
        params['num'] = min(5 if keywords else 60, store.limit - len(store.rows))
        store.manifest['api_requests'] += 1
        payload = request_page(key, params)
        returned_id = (payload.get('search_parameters') or {}).get('data_id')
        if returned_id and returned_id.lower() != data_id.lower():
            raise ValueError('SerpAPI returned reviews for a different place.')
        if source_name is None:
            info = payload.get('place_info') or {}
            title = info.get('title')
            if not isinstance(title, str) or not title.strip():
                if args.name:
                    title = None
                else:
                    if store.manifest['api_requests'] >= args.max_pages:
                        store.manifest['warnings'].append(
                            'The keyword response omitted the restaurant name. Increase --max-pages '
                            'to allow a metadata lookup, or supply --name.')
                        return 'api_page_limit'
                    metadata_params = {'engine': 'google_maps_reviews', 'data_id': data_id,
                                       'hl': 'en', 'num': 1}
                    time.sleep(args.delay)
                    store.manifest['api_requests'] += 1
                    store.manifest['metadata_lookup_requests'] = 1
                    metadata = request_page(key, metadata_params)
                    metadata_id = (metadata.get('search_parameters') or {}).get('data_id')
                    if metadata_id and metadata_id.lower() != data_id.lower():
                        raise ValueError('SerpAPI metadata belongs to a different place.')
                    title = (metadata.get('place_info') or {}).get('title')
                    if not isinstance(title, str) or not title.strip():
                        raise ValueError('SerpAPI omitted the restaurant name even without keywords. '
                                         'Supply --name with the verified restaurant name.')
            source_name = args.name or title
            store.manifest.update(source_name=source_name, provider_place_name=title)
        if keywords and payload.get('reviews') == []:
            store.manifest['empty_keyword_searches'].append(params['query'])
            print(f'No reviews for keyword {params["query"]!r}; continuing.', flush=True)
        store.add(parse_reviews(payload, source_url, source_name, store.manifest))
        store.save()
        print(f'Collected {len(store.rows)}/{store.limit} written reviews '
              f'({store.manifest["api_requests"]} API requests)', flush=True)
        if store.full:
            return 'user_limit'
        if keywords:
            if index + 1 >= len(keywords):
                return 'keyword_search_end'
            if time.monotonic() >= deadline:
                return 'time_limit'
            time.sleep(args.delay)
            continue
        token = (payload.get('serpapi_pagination') or {}).get('next_page_token')
        if not token:
            return 'api_pagination_end'
        if not isinstance(token, str) or token in tokens:
            return 'stalled_unverified'
        tokens.add(token)
        params['next_page_token'] = token
        if time.monotonic() >= deadline:
            return 'time_limit'
        time.sleep(args.delay)
    return 'api_page_limit'
