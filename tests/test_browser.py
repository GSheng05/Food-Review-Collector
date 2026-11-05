"""Offline browser fixtures test extraction, not current production-site availability."""
import tempfile
import unittest
from types import SimpleNamespace
from playwright.sync_api import sync_playwright
from reviews.browser import GoogleMaps, Shopee, check_gate, CollectionBlocked, google_price_range
from reviews.core import Store


class BrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = sync_playwright().start()
        cls.browser = cls.p.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.p.stop()

    def setUp(self):
        self.page = self.browser.new_page()
        self.temp = tempfile.TemporaryDirectory()
        self.args = SimpleNamespace(name=None, delay=1)
        self.store = Store(self.temp.name, 'https://www.google.com/maps/place/Food', 'google_maps')

    def tearDown(self):
        self.page.close()
        self.temp.cleanup()

    def google(self):
        adapter = GoogleMaps(self.page, self.store, self.args)
        adapter.name = 'Food Court'
        adapter.source_url = 'https://www.google.com/maps/place/Food'
        return adapter

    def test_expand_original_exclude_owner_response_and_empty_review(self):
        self.page.set_content('''<div style="height:150px;overflow-y:auto"><div style="height:800px">
          <div class="jftiEf" data-review-id="abc">
            <span class="wiI7pd" style="white-space:pre-wrap">Translated preview</span>
            <button onclick="this.previousElementSibling.textContent='Sedap lah!\\nBest 😋';this.remove()">See original</button>
            <button class="w8nwRe" onclick="this.remove()">More</button>
            <span role="img" aria-label="5 stars"></span><span class="rsqaWe">2 weeks ago</span>
            <div class="PBK6be"><div>Meal type</div><div>Lunch</div></div>
            <div class="PBK6be"><div>Price per person</div><div>RM 20–40</div></div>
            <div class="owner-reply">Thank you from owner</div>
          </div>
          <div class="jftiEf" data-review-id="empty"><span role="img" aria-label="3 stars"></span></div>
        </div></div>''')
        adapter = self.google()
        rows = list(adapter.harvest())
        self.assertEqual(rows[0].raw_review, 'Sedap lah!\nBest 😋')
        self.assertEqual(rows[0].rating, 5)
        self.assertEqual(rows[0].review_date, '2 weeks ago')
        self.assertEqual(rows[1].raw_review, '')
        self.assertEqual(rows[0].price_range, 'RM 20–40')
        self.assertIsNone(rows[1].price_range)
        self.assertTrue(adapter.advance())
        self.store.add(rows)
        self.assertEqual(self.store.add(adapter.harvest()), 0)

    def test_price_range_uses_structured_review_metadata_only(self):
        self.page.set_content('<div class="jftiEf"><span class="wiI7pd">Paid RM 19.90</span><div class="PBK6be"><div>Meal type</div><div>Lunch</div></div></div>')
        self.assertIsNone(google_price_range(self.page.locator('.jftiEf')))
        self.page.set_content('<div class="jftiEf"><div class="PBK6be"><div>Harga setiap orang</div><div>RM 40–60</div></div></div>')
        self.assertEqual(google_price_range(self.page.locator('.jftiEf')), 'RM 40–60')

    def test_unresolved_translation_is_not_exported(self):
        self.page.set_content('<div class="jftiEf" data-review-id="x"><span class="wiI7pd">Translated text</span><span>Translated by Google</span></div>')
        with self.assertRaises(ValueError):
            list(self.google().harvest())

    def test_completed_cards_survive_later_extraction_failure(self):
        self.page.set_content("""
            <div class="jftiEf" data-review-id="good"><span class="wiI7pd">Original review</span></div>
            <div class="jftiEf" data-review-id="bad"><span class="wiI7pd">A</span><span class="wiI7pd">B</span></div>
        """)
        with self.assertRaises(ValueError):
            self.store.add(self.google().harvest())
        self.store.save('error')
        import json
        from pathlib import Path
        saved = json.loads((Path(self.temp.name) / 'reviews.json').read_text(encoding='utf-8'))
        self.assertEqual([row['raw_review'] for row in saved], ['Original review'])

    def test_gate_detected(self):
        self.page.set_content('<div id="captcha">Please verify</div>')
        with self.assertRaises(CollectionBlocked):
            check_gate(self.page)

    def test_limited_maps_and_unavailable_shopee(self):
        for html in ["<div>You're seeing a limited view of Google Maps. See more</div>", '<h2>Page Unavailable</h2>']:
            self.page.set_content(html)
            with self.assertRaises(CollectionBlocked):
                check_gate(self.page)

    def test_limited_maps_with_reviews_tab_open(self):
        url = 'https://www.google.com/maps/place/Food'
        self.page.route(url, lambda route: route.fulfill(content_type='text/html', body="""
            <main aria-label="Food Court">
                <button role="tab" aria-selected="true">Reviews</button>
                <div class="jftiEf" data-review-id="abc"><span class="wiI7pd">Sedap!</span></div>
                <div>You're seeing a limited view of Google Maps.</div>
            </main>
        """))
        self.page.goto(url)
        adapter = self.google()
        adapter.open()
        self.assertEqual(adapter.name, 'Food Court')
        self.assertEqual(list(adapter.harvest())[0].raw_review, 'Sedap!')

    def test_shopee_pagination_end_and_schema_error(self):
        adapter = Shopee(self.page, self.store, self.args)
        adapter.batches = 1
        self.page.set_content('<div class="product-ratings"><button class="shopee-icon-button--right" disabled>Next</button></div>')
        self.assertFalse(adapter.advance())
        adapter.errors.append('HTTP 403')
        with self.assertRaises(CollectionBlocked):
            adapter.harvest()


if __name__ == '__main__':
    unittest.main()
