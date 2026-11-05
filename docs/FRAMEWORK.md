# Source analysis and assignment mapping

## Assignment scope

Read from CPC353 Assignment 1 (2026/2027), pages 1-3, and the supplied English-Malay corpus schema.

- Approximately 100-200 real/clearly identified AI review texts; English, Malay or mixed.
- Focus on one product/category, or a coherent eatery category. Mixing food-court reviews and packaged-food reviews needs an explicit research rationale.
- Preserve original text and source URL; collect rating, date and category where available.
- Later classify English, Malay, Code-switched or Other/uncertain. Keep sufficient mixed-language examples for meaningful analysis.
- Later remove duplicate texts, identify missing/empty entries, define the analysis unit and report collected versus retained counts. Raw ingestion keeps these records and reports their counts; it does not silently clean them.
- AI generation, annotation, cleaning and NLP are outside this collection framework. The workbook's example rows are not actual collected data.
- The assignment overview says at least TWO NLP techniques, while section 4 says at least ONE. Plan for two unless the lecturer clarifies otherwise.
- Report: IEEE format, 3-6 pages excluding cover, Word and PDF submission, 13 November 2026.

The revised CSV omits Review ID and Product Category and adds Price Range, following the user's updated collection requirements. Review URL is also omitted from JSON. The original workbook is not edited. Source URL is retained. Source IDs exist only in memory for duplicate-observation detection.

## Source structure

| Detail | Google Maps | Shopee |
|---|---|---|
| Parent entity | Place/restaurant | Product listing, shop ID + item ID |
| Review identity | Per-review ID on rendered card | `cmtid` in page ratings response |
| Text | Expanded original-language card text | Original `comment` string |
| Rating | Stars on review card | `rating_star` |
| Date | Frequently relative text | `ctime` Unix timestamp, exported in UTC |
| Price Range | Structured Price per person inside the individual review | Blank: equivalent review-spend metadata not verified |
| Loading | Dynamic review pane, scroll | Dynamic ratings section, next-page control |
| Exclusions | Owner replies, machine translation, summaries | Seller replies, unrelated/similar-product ratings |
| Risks | Verification, consent, localisation, truncated/translated text, changing selectors | Login, request failures, changing response fields/pagination, recommendation reviews |

Google selector candidates: `.jftiEf[data-review-id]`, `.wiI7pd`, `.w8nwRe`, `.rsqaWe`, `h1.DUwDvf`. The main review-card, text, rating, date and `.PBK6be` price-metadata structure were observed in five expanded Gepuklah reviews in the visible browser. Full CLI pagination remains unverified.

Shopee adapter assumptions: `.product-ratings`, `.shopee-icon-button--right`, browser responses whose path contains `/item/get_ratings`, and `data.ratings` records containing `cmtid`, `comment`, `rating_star`, `ctime`, `itemid`, `shopid`. The supplied live product link resolved to Shopee but redirected to a traffic/login error, so the extraction fields and selectors remain unverified on a live product. The collector refuses schema mismatches instead of creating apparently successful empty data. The response listener sends no extra API requests.

## Official API alternatives and evidence

1. [Google Places resource](https://developers.google.com/maps/documentation/places/web-service/reference/rest/v1/places): review results are limited to a maximum of five, sorted by relevance. The Review model distinguishes original text from localised text and includes rating, publish time and a Maps review URI. This endpoint cannot implement exhaustive public-place collection.
2. [Google Business Profile review guide](https://developers.google.com/my-business/content/review-data): supports review management/listing for business-profile locations. It requires business access and is not a general review feed for arbitrary restaurants.
3. [Shopee Malaysia product-rating help](https://help.shopee.com.my/portal/4/article/78919-): product reviews/ratings can include text and media; review text must be kept separate from delivery/service ratings and platform UI content. This help article does NOT document a public arbitrary-product bulk review API.

Official documentation establishes the platform concepts, not the private website selectors. Only real browser tests can validate those selectors. Third-party claims of exhaustive review collection are not proof of completeness.

## Validation performed

- Core and local Chromium fixture tests: raw Unicode/newlines/quotes, CSV round trip, empty reviews, repeated wording with distinct IDs, same-ID deduplication, review caps, deceptive URL rejection, shop/item filtering, timestamp conversion, translated-text rejection, More expansion, owner-reply exclusion, verification detection and disabled pagination.
- Supplied Google share link resolved toward Golden Phoenix Food Court in Google Search and displayed an unusual-traffic verification page. No real reviews were obtained during that probe. No CAPTCHA bypass was attempted.
- The subsequent Maps share link resolved to Golden Phoenix Food Court but explicitly displayed a limited view without reviews.
- The supplied Shopee short link resolved to shopee.com.my and redirected to /verify/traffic/error, showing Page Unavailable and requesting login. No reviews were obtained.
- Both detected states now stop with a blocked manifest. A signed-in, user-controlled session is required for further live validation. No claim of full retrieval is made.

## Updated fields and sample

The five saved Gepuklah records were updated using the Price per person values observed on their original expanded review cards: RM 40–60, RM 20–40, RM 20–40, RM 40–60 and RM 20–40 respectively. Original review text and collection timestamps are unchanged. Price is not inferred from mentions in the text. Tests cover structured price extraction, absent prices, revised export fields and continuing internal deduplication.

## Extension points

Add a source adapter with `open()`, `harvest()` and `advance()`. Keep provenance in each Review. Keep raw data separate from a future cleaning/annotation command. Add saved, anonymised HTML/JSON fixtures whenever a website changes, and test correct source IDs, language preservation and pagination before marking the adapter validated.
