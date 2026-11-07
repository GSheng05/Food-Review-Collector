"""Command-line browser runner with incremental exports and explicit stop reasons."""
import argparse
import json
from datetime import datetime
from pathlib import Path
import time
from .core import Review, Store, platform_for


def positive_int(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError('Must be at least 1.')
    return result


def load_google_export(path):
    data = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('format') != 'google-maps-browser-export-v1':
        raise ValueError('Expected a Google Maps browser export file.')
    url, name, entries = data.get('source_url'), data.get('source_name'), data.get('reviews')
    if not isinstance(url, str) or platform_for(url) != 'google_maps':
        raise ValueError('Browser export is missing a supported Maps URL.')
    if not isinstance(name, str) or not name.strip() or not isinstance(entries, list) or not entries:
        raise ValueError('Browser export is missing the restaurant name or reviews.')
    rows = []
    for i, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict) or not isinstance(entry.get('raw_review'), str) or not entry['raw_review'].strip():
            raise ValueError(f'Browser export row {i} is missing written review text.')
        metadata = [entry.get(key) for key in ('review_date', 'price_range', 'collected_at')]
        rating = entry.get('rating')
        if (any(value is not None and not isinstance(value, str) for value in metadata)
                or (rating is not None and (type(rating) not in (int, float) or not 1 <= rating <= 5))):
            raise ValueError(f'Browser export row {i} contains invalid review metadata.')
        date, price, collected_at = metadata
        # The browser already deduplicated by source ID. Keep identical review texts.
        rows.append(Review(str(i), entry['raw_review'], url, name, 'google_maps',
                           rating, date, price, collected_at or ''))
    return data, rows


def main(argv=None):
    parser = argparse.ArgumentParser(description='Collect original Google Maps or Shopee reviews into JSON and CSV.')
    parser.add_argument('url', nargs='?', help='Google Maps place/share URL or Shopee product URL')
    parser.add_argument('--import-google', metavar='JSON', help='Convert a Google Maps browser export to CSV and JSON')
    parser.add_argument('--output', help='New/empty output folder (never overwrite an earlier run)')
    parser.add_argument('--limit', type=positive_int, help='Optional review cap. Default: collect until the visible list stalls/ends.')
    parser.add_argument('--name', help='Optional explicit restaurant/product name')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--headless', action='store_true', help='Run without a browser window (the default)')
    mode.add_argument('--interactive', action='store_true', help='Visible browser; manually handle login/verification, then press Enter')
    parser.add_argument('--provider', choices=['browser', 'serpapi'], default='browser')
    parser.add_argument('--serpapi-key-file', default='.serpapi-key', help='Local key file, ignored by Git')
    parser.add_argument('--keyword-library', choices=['food'], help='Use the bundled food-review search vocabulary')
    parser.add_argument('--review-keywords', help='Comma-separated review search terms, e.g. sedap,pedas; SerpAPI returns at most 5 per term')
    parser.add_argument('--max-pages', type=positive_int, default=10, help='Maximum SerpAPI requests per run')
    parser.add_argument('--profile', default='.browser-profile', help='Isolated browser profile directory; keep private')
    parser.add_argument('--delay', type=float, default=2.5, help='Seconds between batches (minimum 1)')
    parser.add_argument('--idle-rounds', type=positive_int, default=5)
    parser.add_argument('--max-minutes', type=positive_int, default=30)
    args = parser.parse_args(argv)
    if not 1 <= args.delay <= 60:
        parser.error('--delay must be between 1 and 60 seconds.')
    if args.name is not None and not args.name.strip():
        parser.error('--name cannot be blank.')
    if bool(args.url) == bool(args.import_google):
        parser.error('Provide either a source URL or --import-google JSON.')
    try:
        if args.import_google:
            browser_export, imported_rows = load_google_export(args.import_google)
            args.url = browser_export['source_url']
        platform = platform_for(args.url)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    if args.review_keywords is not None or args.keyword_library:
        if args.provider != 'serpapi' or args.import_google:
            parser.error('Keyword searches require a SerpAPI Google Maps URL.')
        terms = []
        if args.keyword_library:
            from .search_keywords import load_food_keywords
            try:
                terms.extend(load_food_keywords())
            except (ValueError, OSError) as exc:
                parser.error(str(exc))
        if args.review_keywords is not None:
            manual_terms = [word.strip().casefold() for word in args.review_keywords.split(',') if word.strip()]
            if not manual_terms:
                parser.error('--review-keywords requires at least one nonempty search term.')
            terms.extend(manual_terms)
        args.review_keywords = list(dict.fromkeys(terms))
        print(f'Loaded {len(args.review_keywords)} review search terms. '
              f'Request cap: {args.max_pages} (includes any restaurant-name lookup).')
    if args.provider == 'serpapi':
        if args.import_google or platform != 'google_maps':
            parser.error('SerpAPI requires a Google Maps URL and cannot be combined with --import-google.')
        from .serpapi import load_key
        try:
            api_key = load_key(args.serpapi_key_file)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        args.limit = args.limit or 50
    output = Path(args.output or ('output/' + platform + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')))
    if output.exists() and any(output.iterdir()):
        parser.error('Output directory is not empty. Choose a new folder to preserve previous data.')
    from .language import MalayClassifier
    try:
        classifier = MalayClassifier()
    except RuntimeError as exc:
        parser.error(str(exc))
    store = Store(output, args.url, platform, args.limit, classifier=classifier)
    store.manifest.update(language_filter='At least one Malaya MS word label',
                          language_labels='Provisional Malaya word-level predictions')
    if args.import_google:
        store.add(imported_rows)
        browser_reason = browser_export.get('stop_reason')
        store.manifest.update(source_url=args.url, source_name=browser_export['source_name'],
                              extraction='Google Maps reviews imported from regular Chrome',
                              browser_stop_reason=browser_reason if isinstance(browser_reason, str) else None)
        store.save('browser_import')
        print(f'Imported {len(store.rows)} written reviews to {output.resolve()}.')
        return 0
    store.save()
    reason = 'error'
    try:
        if args.provider == 'serpapi':
            from .serpapi import collect
            reason = collect(store, args, api_key)
        else:
            reason = collect_browser(store, args, platform)
    except KeyboardInterrupt:
        reason = 'interrupted'
    except Exception as exc:
        store.manifest['warnings'].append(f'{type(exc).__name__}: {exc}')
        reason = 'blocked' if type(exc).__name__ == 'CollectionBlocked' else 'error'
        print(f'Collection stopped: {exc}', flush=True)
    finally:
        store.save(reason)
    print(f'Saved {len(store.rows)} reviews to {output.resolve()}. Stop reason: {reason}.')
    print('Completeness is not guaranteed; inspect manifest.json before using the dataset.')
    return 0 if reason in {'user_limit', 'visible_pagination_end', 'api_pagination_end', 'keyword_search_end'} else 2


def collect_browser(store, args, platform):
    from playwright.sync_api import sync_playwright
    from .browser import GoogleMaps, Shopee, check_gate
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(str(Path(args.profile).resolve()),
                     headless=not args.interactive, locale='en-US', viewport={'width': 1440, 'height': 1000})
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.set_default_timeout(15000)
            adapter = (GoogleMaps if platform == 'google_maps' else Shopee)(page, store, args)
            page.goto(args.url, wait_until='domcontentloaded', timeout=60000)
            page.wait_for_timeout(args.delay * 1000)
            if args.interactive:
                input('In the browser, handle login/consent/verification and open the target place/product. Then press Enter here: ')
            check_gate(page)
            try:
                adapter.open()
            except Exception:
                check_gate(page)  # Detect redirects/gates that appeared during loading.
                raise
            idle = 0
            deadline = time.monotonic() + args.max_minutes * 60
            while True:
                check_gate(page)
                examined_before = store.manifest["examined_reviews"]
                added = store.add(adapter.harvest())
                store.save()
                print(f'Collected {len(store.rows)} reviews (+{added})', flush=True)
                idle = 0 if store.manifest["examined_reviews"] > examined_before else idle + 1
                if store.full:
                    reason = 'user_limit'
                    break
                if time.monotonic() >= deadline:
                    reason = 'time_limit'
                    break
                if idle >= args.idle_rounds:
                    reason = 'stalled_unverified'
                    break
                if not adapter.advance():
                    reason = 'visible_pagination_end' if platform == 'shopee' else 'no_scrollable_review_pane'
                    break
                page.wait_for_timeout(args.delay * 1000)
        finally:
            context.close()
    return reason
