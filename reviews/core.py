"""Models, URL validation and lossless collection exports (no browser required)."""
import csv
import json
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


def platform_for(url):
    parsed = urlsplit(url)
    host = (parsed.hostname or '').lower()
    if parsed.scheme != 'https' or parsed.username or parsed.password:
        raise ValueError('Use a public HTTPS Google Maps or Shopee link.')
    if host in {'share.google', 'maps.app.goo.gl', 'maps.google.com', 'maps.google.com.my'}:
        return 'google_maps'
    if host in {'google.com', 'www.google.com', 'google.com.my', 'www.google.com.my'} and parsed.path.startswith('/maps'):
        return 'google_maps'
    if host == 'goo.gl' and parsed.path.startswith('/maps'):
        return 'google_maps'
    if host in {'shopee.com.my', 'www.shopee.com.my', 'shopee.sg', 'www.shopee.sg', 'shopee.co.id', 'www.shopee.co.id', 'shopee.ph', 'www.shopee.ph', 'shopee.co.th', 'www.shopee.co.th', 'shopee.vn', 'www.shopee.vn', 'shopee.tw', 'www.shopee.tw', 's.shopee.com.my', 's.shopee.sg', 'my.shp.ee'}:
        return 'shopee'
    raise ValueError('Unsupported source URL. Use a Google Maps place or Shopee product link.')


def shopee_ids(url):
    path = urlsplit(url).path
    m = re.search(r'-i\.(\d+)\.(\d+)', path) or re.search(r'/product/(\d+)/(\d+)', path)
    if not m:
        raise ValueError('Could not resolve shop/item IDs. Use the full Shopee product URL.')
    return m.group(1), m.group(2)


@dataclass
class Review:
    _review_id: str  # In-memory identity only; never exported.
    raw_review: str
    source_url: str
    source_name: str
    platform: str
    rating: float | None = None
    review_date: str | None = None
    price_range: str | None = None
    collected_at: str = ''
    language_classification: str = ''

    def __post_init__(self):
        if not self._review_id or not self.source_name or not isinstance(self.raw_review, str):
            raise ValueError('A source name, review ID and text string (possibly empty) are required.')
        if self.review_date:
            try:
                self.review_date = datetime.fromisoformat(
                    self.review_date.replace('Z', '+00:00')
                ).date().isoformat()
            except ValueError:
                pass  # Keep source-relative dates such as "2 weeks ago".
        if not self.collected_at:
            self.collected_at = datetime.now(timezone.utc).isoformat()


def shopee_reviews(payload, response_url, source_url, source_name):
    """Parse only ratings delivered to the browser for the requested item/shop."""
    shop, item = shopee_ids(source_url)
    query = parse_qs(urlsplit(response_url).query)
    if query.get('itemid') != [item] or query.get('shopid') != [shop]:
        return []
    if payload.get('error') not in (None, 0):
        raise ValueError('Shopee returned an error instead of ratings.')
    data = payload.get('data')
    if not isinstance(data, dict) or not isinstance(data.get('ratings'), list):
        raise ValueError('Shopee ratings response schema changed.')
    result = []
    for row in data['ratings']:
        if str(row.get('itemid', '')) != item or str(row.get('shopid', '')) != shop:
            continue  # Never mix similar-product reviews into the requested product.
        if row.get('cmtid') is None or not isinstance(row.get('comment'), str):
            raise ValueError('Shopee rating is missing its ID or original comment.')
        timestamp = row.get('ctime')
        date = datetime.fromtimestamp(timestamp, timezone.utc).isoformat() if isinstance(timestamp, (int, float)) else None
        result.append(Review(str(row['cmtid']), row['comment'], source_url, source_name,
                             'shopee', row.get('rating_star'), date))
    return result


HEADERS = ['Data Origin', 'Product / Eatery Name',
           'Source Platform', 'Source URL', 'Rating (1-5)', 'Review Date', 'Price Range', 'Review Text',
           'Language Classification', 'Code-Switching Type', 'Notes / Annotator Comments']


def replace_export(temporary, destination):
    # Windows indexers/readers may briefly hold the destination open after a save.
    for attempt in range(5):
        try:
            temporary.replace(destination)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2)



class Store:
    def __init__(self, directory, input_url, platform, limit=None, classifier=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.rows = {}
        self.seen = set()
        self.classifier = classifier
        self.limit = limit
        self.manifest = {'input_url': input_url, 'platform': platform, 'status': 'running',
                         'all_reviews_verified': False, 'started_at': datetime.now(timezone.utc).isoformat(),
                         'stop_reason': None, 'warnings': [], 'repeat_observations': 0,
                         'examined_reviews': 0, 'skipped_without_malay': 0}

    def add(self, rows):
        count = 0
        for row in rows:
            key = (row.platform, row.source_url, row._review_id)
            if key in self.seen:
                self.manifest['repeat_observations'] += 1
                continue
            if self.full:
                break
            self.seen.add(key)
            self.manifest['examined_reviews'] += 1
            if self.classifier:
                row.language_classification = self.classifier.classify(row.raw_review, source_name=row.source_name) or ''
                if row.language_classification not in {'Malay', 'Code-switched'}:
                    self.manifest['skipped_without_malay'] += 1
                    continue
            self.rows[key] = row
            count += 1
        return count

    @property
    def full(self):
        return self.limit is not None and len(self.rows) >= self.limit

    def save(self, reason=None):
        if reason:
            self.manifest.update(status='stopped', stop_reason=reason,
                                 finished_at=datetime.now(timezone.utc).isoformat())
        texts = [r.raw_review for r in self.rows.values()]
        self.manifest.update(collected_reviews=len(texts), empty_reviews=sum(not t.strip() for t in texts),
                             repeated_text_reviews=len(texts) - len(set(texts)))
        for name, value in [('reviews.json', [{k: v for k, v in asdict(r).items() if not k.startswith('_')} for r in self.rows.values()]), ('manifest.json', self.manifest)]:
            tmp = self.directory / (name + '.tmp')
            tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
            replace_export(tmp, self.directory / name)
        tmp = self.directory / 'reviews.csv.tmp'
        with tmp.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADERS)
            for r in self.rows.values():
                writer.writerow(['Self-Collected (Real)', r.source_name,
                                 'Google Reviews' if r.platform == 'google_maps' else 'Shopee', r.source_url,
                                 r.rating, r.review_date, r.price_range, r.raw_review, r.language_classification, '', ''])
        replace_export(tmp, self.directory / 'reviews.csv')
