"""Command-line browser runner with incremental exports and explicit stop reasons."""
import argparse
from datetime import datetime
from pathlib import Path
import time
from .core import Store, platform_for


def positive_int(value):
    result = int(value)
    if result < 1:
        raise argparse.ArgumentTypeError('Must be at least 1.')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Collect original Google Maps or Shopee reviews into JSON and CSV.')
    parser.add_argument('url', help='Google Maps place/share URL or Shopee product URL')
    parser.add_argument('--output', help='New/empty output folder (never overwrite an earlier run)')
    parser.add_argument('--limit', type=positive_int, help='Optional review cap. Default: collect until the visible list stalls/ends.')
    parser.add_argument('--name', help='Optional explicit restaurant/product name')
    parser.add_argument('--interactive', action='store_true', help='Visible browser; manually handle login/verification, then press Enter')
    parser.add_argument('--profile', default='.browser-profile', help='Isolated browser profile directory; keep private')
    parser.add_argument('--delay', type=float, default=2.0, help='Seconds between batches (minimum 1)')
    parser.add_argument('--idle-rounds', type=positive_int, default=5)
    parser.add_argument('--max-minutes', type=positive_int, default=30)
    args = parser.parse_args(argv)
    if not 1 <= args.delay <= 60:
        parser.error('--delay must be between 1 and 60 seconds.')
    if args.name is not None and not args.name.strip():
        parser.error('--name cannot be blank.')
    try:
        platform = platform_for(args.url)
    except ValueError as exc:
        parser.error(str(exc))
    output = Path(args.output or ('output/' + platform + '-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f')))
    if output.exists() and any(output.iterdir()):
        parser.error('Output directory is not empty. Choose a new folder to preserve previous data.')
    store = Store(output, args.url, platform, args.limit)
    store.save()
    reason = 'error'
    try:
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
                    added = store.add(adapter.harvest())
                    store.save()
                    print(f'Collected {len(store.rows)} reviews (+{added})', flush=True)
                    idle = 0 if added else idle + 1
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
    return 0 if reason in {'user_limit', 'visible_pagination_end'} else 2
