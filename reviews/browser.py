"""Browser adapters. Selectors are deliberately isolated because websites change."""
import re
from urllib.parse import urlsplit
from .core import Review, platform_for, shopee_ids, shopee_reviews


class CollectionBlocked(RuntimeError):
    pass


def check_gate(page):
    url = page.url.lower()
    if '/sorry/' in url or '/captcha' in url or '/verify/' in url or '/buyer/login' in url:
        raise CollectionBlocked('Login or verification required. Run with --interactive and complete it yourself.')
    if page.get_by_text(re.compile(r"You.re seeing a limited view of Google Maps", re.I)).count():
        raise CollectionBlocked('Google Maps is showing a limited view without reviews. Run with --interactive and sign in if requested.')
    if page.get_by_text('Page Unavailable', exact=True).count():
        raise CollectionBlocked('The source page is unavailable. Open --interactive to handle login or check access.')
    if page.locator('iframe[src*="recaptcha"], iframe[src*="hcaptcha"], #captcha').count():
        raise CollectionBlocked('Verification required. Run with --interactive.')


def text_or_none(locator):
    return locator.first.inner_text() if locator.count() else None


class GoogleMaps:
    card_selector = '.jftiEf[data-review-id]'

    def __init__(self, page, store, args):
        self.page, self.store, self.args = page, store, args
        self.source_url = ''
        self.name = ''

    def open(self):
        page = self.page
        # Google share links sometimes resolve to Search, not Maps. Follow an actual
        # Maps link from that page, never guess a restaurant identity from its name.
        if urlsplit(page.url).path.startswith('/search'):
            link = page.locator('a[href*="google.com/maps/place/"], a[href*="maps.google.com/"]').first
            if not link.count():
                raise ValueError('This Google share link opened Search. Copy the restaurant link from Google Maps instead.')
            link.click()
            page.wait_for_load_state('domcontentloaded')
        check_gate(page)
        if platform_for(page.url) != 'google_maps' or '/maps' not in urlsplit(page.url).path:
            raise ValueError('Open a single restaurant in Google Maps and use its full place link.')
        page.locator('h1.DUwDvf').wait_for(timeout=20000)
        self.name = self.args.name or page.locator('h1.DUwDvf').inner_text()
        self.source_url = page.url
        if not page.locator(self.card_selector).count():
            tab = page.get_by_role('tab', name=re.compile(r'Reviews|Ulasan', re.I)).first
            if tab.count():
                tab.click()
            else:
                page.get_by_role('button', name=re.compile(r'\d[\d,.]*\s+(reviews|ulasan)', re.I)).first.click()
        page.locator(self.card_selector).first.wait_for(timeout=20000)
        # Leave filters at their default; sorting alone does not filter review text.
        self.store.manifest.update(source_url=self.source_url, source_name=self.name,
                                   extraction='Google Maps rendered original review text')

    def harvest(self):
        results = []
        for card in self.page.locator(self.card_selector).all():
            original = card.get_by_role('button', name=re.compile(r'^(See original|Show original|Lihat asal|Lihat yang asal)$', re.I))
            if original.count():
                original.first.click()
                original.first.wait_for(state='hidden', timeout=8000)
            # If Google still labels this as translated, do not silently save a translation.
            if card.get_by_text(re.compile(r'^\(?Translated by Google\)?$', re.I)).count():
                raise ValueError('Original review text could not be selected; refusing to export translated text.')
            more = card.locator('button.w8nwRe')
            if more.count() and more.first.is_visible():
                more.first.click()
                more.first.wait_for(state='hidden', timeout=8000)
            text = card.locator('.wiI7pd')
            if text.count() > 1:
                raise ValueError('Ambiguous Google review text nodes; selectors need updating.')
            raw = text.first.inner_text() if text.count() else ''
            stars = card.locator('[role="img"][aria-label*="star"], [role="img"][aria-label*="bintang"]')
            rating_label = stars.first.get_attribute('aria-label') if stars.count() else ''
            match = re.search(r'\d+(?:[.,]\d+)?', rating_label or '')
            rating = float(match.group().replace(',', '.')) if match else None
            results.append(Review(card.get_attribute('data-review-id'), raw, self.source_url, self.name,
                                  'google_maps', rating, text_or_none(card.locator('.rsqaWe')),
                                  product_category=self.args.category))
        return results

    def advance(self):
        # Scroll the actual review pane, not the entire page or the map canvas.
        card = self.page.locator(self.card_selector).last
        return card.evaluate('''el => {
            let p = el.parentElement;
            while (p) {
                const style = getComputedStyle(p);
                if (/(auto|scroll)/.test(style.overflowY) && p.scrollHeight > p.clientHeight) {
                    p.scrollTop += Math.max(500, p.clientHeight * 0.8);
                    return true;
                }
                p = p.parentElement;
            }
            return false;
        }''')


class Shopee:
    def __init__(self, page, store, args):
        self.page, self.store, self.args = page, store, args
        self.pending = []
        self.errors = []
        self.batches = 0
        self.source_url = ''
        self.name = ''
        self.page.on('response', self._response)

    def _response(self, response):
        # Observe only requests made by the ordinary product page. No private API
        # calls, token extraction, CAPTCHA bypass or synthetic pagination requests.
        host = urlsplit(response.url).hostname
        if '/item/get_ratings' not in urlsplit(response.url).path or host != urlsplit(self.page.url).hostname:
            return
        if response.status != 200:
            self.errors.append(f'Shopee ratings request returned HTTP {response.status}.')
            return
        try:
            self.pending.append((response.url, response.json()))
        except Exception as exc:
            self.errors.append(f'Could not read Shopee ratings response: {type(exc).__name__}')

    def open(self):
        check_gate(self.page)
        if platform_for(self.page.url) != 'shopee':
            raise ValueError('Shopee link redirected outside a supported product page.')
        shopee_ids(self.page.url)
        self.source_url = self.page.url.split('?')[0]
        self.page.locator('h1').first.wait_for(timeout=20000)
        self.name = self.args.name or self.page.locator('h1').first.inner_text()
        self.page.locator('.product-ratings').wait_for(timeout=20000)
        self.page.locator('.product-ratings').scroll_into_view_if_needed()
        self.page.wait_for_timeout(self.args.delay * 1000)
        self.store.manifest.update(source_url=self.source_url, source_name=self.name,
                                   extraction='Shopee original comment from browser ratings responses')

    def harvest(self):
        if self.errors:
            raise CollectionBlocked(self.errors[0])
        result = []
        while self.pending:
            url, payload = self.pending.pop(0)
            rows = shopee_reviews(payload, url, self.source_url, self.name, self.args.category)
            result.extend(rows)
            # Count only responses for this product, not recommendation widgets.
            from urllib.parse import parse_qs
            query = parse_qs(urlsplit(url).query)
            shop, item = shopee_ids(self.source_url)
            if query.get('shopid') == [shop] and query.get('itemid') == [item]:
                self.batches += 1
        return result

    def advance(self):
        if not self.batches:
            raise ValueError('No matching Shopee ratings response observed. Login may be needed or the site schema changed.')
        next_button = self.page.locator('.product-ratings .shopee-icon-button--right').first
        if not next_button.count():
            raise ValueError('Shopee next-page control not found; pagination selectors need checking.')
        disabled = next_button.is_disabled() or next_button.get_attribute('aria-disabled') == 'true' or 'disabled' in (next_button.get_attribute('class') or '')
        if disabled:
            return False
        pending_before = len(self.pending)
        next_button.click()
        # Wait for a response before another click; never skip pages on a slow load.
        for _ in range(30):
            self.page.wait_for_timeout(500)
            if len(self.pending) > pending_before or self.errors:
                return True
        raise ValueError('Shopee next page did not load a ratings response within 15 seconds.')
