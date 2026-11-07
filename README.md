# Food Review Collector

A separate, history-preserving derivative of [GSheng05/Web-Scrapper](https://github.com/GSheng05/Web-Scrapper).
The original crawler modules (`crawl.py`, `main.py`, `json_report.py`) remain unchanged.
Their usage is in [README-crawler.md](README-crawler.md).

Give the new collector a Google Maps restaurant URL or Shopee food-product URL. It attempts to walk the reviews exposed by the website and exports:

- `raw_review`: original review text, preserved verbatim for reviews passing the Malay-word filter.
- `source_url`: restaurant/product page URL.
- `source_name`: restaurant/product name.
- `price_range`: the reviewer's structured price-per-person range when available.
- Platform, rating, review date and collection timestamp when available.

Review ID, review URL and product category are not exported. Source IDs are held only in memory to avoid collecting the same card twice. Source URL remains in the exports.

**Status: SerpAPI live Google Maps collection is validated. The current SerpAPI default is 50 qualifying reviews. Browser collection depends on the reviews exposed in that session. Shopee bulk collection still needs live validation.**

## Install (Python 3.10+)

The review collector has a separate environment/dependency file so the original crawler configuration is preserved. Its original `pyproject.toml` requires Python 3.14; these commands deliberately do not use that configuration.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-reviews.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python`.

## Collect

Paste a single **Google Maps place** link, preferably the full `https://www.google.com/maps/place/...` link. Short Maps links are supported. Some `share.google` links open Search instead; the collector follows a Maps place link when available, otherwise requests a Maps link instead of guessing the restaurant.

```powershell
.\.venv\Scripts\python.exe collect_reviews.py "PASTE_GOOGLE_MAPS_PLACE_URL" --limit 200 --interactive
.\.venv\Scripts\python.exe collect_reviews.py "PASTE_SHOPEE_PRODUCT_URL" --interactive
```

Replace the placeholder URL. With `--interactive`, the browser opens and waits for you to handle login, consent or verification and open the intended place/product. Press Enter **in the terminal** to begin collection. You can also open its Reviews tab while paused. The profile is isolated from your personal Chrome profile and stored in `.browser-profile/`; never share or commit it.

Without `--interactive`, the browser runs headlessly (`--headless` also selects this explicitly) and stops if a login/verification gate is detected. The tool does not solve CAPTCHAs or bypass access controls. Use sources you are permitted to collect from and review platform collection conditions before running a large collection.

Omit `--limit` to collect until the exposed list ends, stalls or reaches the safety time limit. Defaults: 2.5 seconds between batches, 5 idle rounds and 30 minutes maximum after source setup. Change these with `--delay`, `--idle-rounds`, `--max-minutes`. `--name` explicitly overrides the page name if necessary.

Each run gets a new folder under `output/`. `--output PATH` chooses a new/empty folder. Existing nonempty folders are rejected to prevent overwrites. This version checkpoints results after each batch and saves completed cards on a handled extraction error or Ctrl+C. A forcibly terminated process can lose the current batch; earlier checkpoints remain. It does not resume browser pagination after an interrupted run.

## Output

Price Range preserves the source currency and range, for example `RM 20–40`. It is the reviewer's stated spend per person, not a restaurant-wide estimate or a number inferred from their prose. Shopee reviews currently have no equivalent verified field in this adapter, so their price range is blank; a current listing price is not substituted for historical reviewer spending.

`reviews.json` is the authoritative UTF-8 raw dataset. Reviews must contain a detected Malay word. Identical text from different review IDs is retained. Only repeated observations of the **same source review ID on the same page** are suppressed during scrolling. Text is preserved as returned by the browser DOM (Maps) or the original comment response (Shopee); DOM text is not byte-for-byte original submission HTML.

`reviews.csv` uses the revised collection columns requested by the user (the original assignment template is not modified):

| Column | Value |
|---|---|
| Data Origin | Self-Collected (Real) |
| Product / Eatery Name | `source_name` |
| Source Platform | Google Reviews or Shopee |
| Source URL | `source_url` |
| Rating (1-5) | Source value, otherwise blank |
| Review Date | YYYY-MM-DD when an exact date is available; relative dates such as `2 weeks ago` are preserved |
| Price Range | Structured Price per person from the review, otherwise blank |
| Review Text | Original `raw_review` |
| Language Classification | Provisional Malay or Code-switched label |
| Code-Switching Type | Blank for later annotation |
| Notes / Annotator Comments | Blank for later annotation |

CSV text is deliberately unmodified, including values beginning with `=`, `+`, `-`, or `@`. Import with Excel **Data → From Text/CSV**, treating the review text column as **Text**, instead of double-clicking the CSV, so untrusted review text is not interpreted as a formula. The supplied workbook is not edited and its example rows are not real collected data.

`manifest.json` records counts, empty/repeated texts, repeated page observations, errors and the stop reason. `all_reviews_verified` remains **false**: neither visible pagination nor an idle panel proves that the platform exposed every review.

| Stop reason | Meaning |
|---|---|
| `user_limit` | Requested review cap reached |
| `visible_pagination_end` | Shopee disabled its Next control; only the exposed list ended |
| `stalled_unverified` | No new review IDs for the configured rounds |
| `no_scrollable_review_pane` | Maps pane could not be scrolled; inspect selectors/layout |
| `blocked` | Login/verification or failed ratings request |
| `time_limit` / `interrupted` | Safety timeout or Ctrl+C |
| `error` | Unexpected page/schema/dependency failure; see warnings |

Exit code 0 indicates the requested cap or visible pagination end; code 2 signals an incomplete/error stop. A zero exit code **does not** mean all platform reviews were retrieved. Always inspect the manifest.

## Why browser adapters?

The original crawler downloads HTML, follows links and extracts headings/first paragraphs. Reviews load dynamically inside one place/product page. Reusing its same-domain crawl loop would miss review pagination. Reusing its URL normalizer would also discard query identifiers needed by some sources.

```text
URL → source validation → Google Maps / Shopee adapter
    → original Review records → source-ID deduplication
    → checkpointed JSON + revised CSV + run manifest
```

Google Maps: open Reviews, select original-language text when translation is displayed, expand More, extract individual cards, then scroll the review pane. Never include owner replies. Relative dates are kept as supplied, not guessed as exact dates.

Shopee: observe the product page's own ratings responses while clicking its review pagination. Preserve `comment` strings. Match both shop and item IDs and exclude recommendation/similar-product reviews. No direct undocumented API requests are generated. The observed-response schema and CSS selectors are isolated in `reviews/browser.py` and `reviews/core.py`; they may require updates when Shopee changes its website. No reviewer account names or browser credentials are exported.

See [source analysis and assignment mapping](docs/FRAMEWORK.md).

## Tests

Install the original crawler dependencies if running its tests too:

```powershell
.\.venv\Scripts\python.exe -m pip install beautifulsoup4 aiohttp requests
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -m unittest test_crawl -v
```

Browser fixtures run locally with Chromium and synthetic review text. They verify extraction mechanics and failure handling, not current production-site selectors. Generated test fixtures are not assignment data. Actual review outputs and browser profiles are ignored by Git.

## Selenium snippet comparison

The collector already expands More, selects original-language text, records source metadata,
uses in-memory review IDs instead of text deduplication, and waits through several idle batches.
A single unchanged scroll height does not prove that all reviews were collected.
The supplied Selenium example targets 150 but returns only 75, silently ignores extraction errors,
and can leave Chrome running on failure. The existing Playwright adapter is retained.

For a headless attempt with a 2.5-second pause between collection batches:

```powershell
.\.venv\Scripts\python.exe collect_reviews.py "https://maps.app.goo.gl/R6RSAgnPVpPbWjtq5" --limit 150 --headless --delay 2.5
```

These pauses pace scrolling/pagination, not every network request generated by the website.
Headless mode is optional convenience, not a guarantee of faster loading or access.
The browser keeps its native user agent; automatic user-agent rotation and free-proxy rotation
are not enabled. They do not reliably resolve Google's automated-browser sign-in rejection.
If login or verification blocks collection, the run stops and saves what it collected.

## Export from regular Chrome

Use this when the full Reviews panel is available in your normal Chrome session. The helper scrolls
the panel and downloads up to 100 written reviews. Keep the Maps tab open until the download finishes.

1. Open the restaurant and click **Reviews**. Sign in directly in Chrome if needed. Scroll until
   you see more than five reviews to confirm the full panel is available.
2. In VS Code, open [export_google_reviews.js](export_google_reviews.js), select all, and copy it.
3. Back in Chrome, press **Ctrl+Shift+I** to open DevTools, then **Ctrl+Shift+P**. Type **Create new
   snippet**, select that command, paste the code in the snippet editor, and press **Ctrl+Enter**.
4. Wait for Chrome to download **google-maps-review-export.json**. The Console reports the count
   and stop reason. The helper can finish with fewer than 100 if the review list stops loading.
5. In the collector's VS Code PowerShell terminal, run:

```powershell
.\.venv\Scripts\python.exe collect_reviews.py --import-google "$env:USERPROFILE\Downloads\google-maps-review-export.json"
```

Use the downloaded file's actual path if Chrome saved it elsewhere or added a number to its name.
Open the reported output folder for **reviews.csv** and **manifest.json**. The helper skips
rating-only cards and cards whose full original text it cannot verify. It only reads review cards
shown in the open tab and saves the export locally.


## SerpAPI Google Maps collection

Store your API key in .serpapi-key in this project folder, containing only the key, or set
SERPAPI_API_KEY. The key file is ignored by Git. Install requirements-language.txt for the Malay-word filter.

~~~powershell
.\.venv\Scripts\python.exe collect_reviews.py "https://maps.app.goo.gl/R6RSAgnPVpPbWjtq5" --provider serpapi --limit 50
~~~

SerpAPI mode defaults to 50 qualifying reviews in relevance order. It follows pagination and
checkpoints CSV/JSON after each page, with at most 10 API requests per run (--max-pages).
Requests may consume API credits. The manifest records request counts and the stop reason.

Text comes from extracted_snippet.original. Non-Google sources and reviews without verified
original written text are skipped and counted. Identical text from distinct reviews is retained.
Review IDs stay in memory. Price Range uses details.price_per_person when available.
Short Maps links are resolved to a full place URL first. Outputs are under output/.

Reference: https://serpapi.com/google-maps-reviews-api

## Malay-word filtering

Install the language dependencies after pulling updates:

~~~powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-language.txt
~~~

The first run downloads Malaya's FastText model. Collection and browser imports now require at
least one word labeled MS by Malaya. MS plus EN is labeled Code-switched; MS alone is Malay.
English-only and unrecognized reviews are skipped. JSON includes language_classification and
CSV fills the existing Language Classification column. The raw review is preserved.

The limit counts saved, qualifying reviews. SerpAPI follows pages up to --max-pages (default 10).
The manifest records examined_reviews and skipped_without_malay. Model labels are provisional,
especially for shared vocabulary, names and slang. Review them for assignment annotation.

Shared Malay/English dictionary words are treated as English to avoid false matches such as "was". This conservative rule may miss Malay uses of shared words. Labels require human review.

## Food and restaurant names in language detection

The classifier masks the complete source restaurant/product name, its base name before "by"
or a parenthesized branch suffix, and listed food names before checking language. Saved
review text remains complete. A name alone does not count as Malay or English evidence.

Edit reviews/language_names.json to add food_names (complete dish/drink phrases) and
source_aliases (short names keyed by the source's full name). Matching ignores case and accepts
spaces or hyphens between words. Restart the collector after editing. For example, ayam gepuk
is ignored as a phrase while ayam in "Saya suka ayam ini" remains available for detection.
The bundled list is a starting point; add menu names and spelling variants for each source.

"The ayam gepuk was delicious" is English and skipped. "The ayam gepuk was sedap" is
Code-switched and saved. "Ayam gepuk sangat sedap" is Malay and saved. Predictions still
need annotation review.

## Search reviews for Malay adjectives

Use --review-keywords to filter at Google/SerpAPI before reviews are returned:

~~~powershell
.\.venv\Scripts\python.exe collect_reviews.py "RESTAURANT_MAPS_URL" --provider serpapi --review-keywords "sedap,pedas" --limit 50
~~~

Each comma-separated term is searched separately. This is text matching, so the words need
not be used grammatically as adjectives and spelling variants need separate terms.
SerpAPI returns at most 5 reviews per term with no pagination. Two terms yield at most 10
reviews before duplicates and the existing Malay filter. The limit is a ceiling, not a
guarantee of 50. Duplicate review IDs across searches are suppressed. The original full
text is preserved. --max-pages caps the total requests, including keyword searches.
The manifest records review_keywords and keyword_search_end when all terms were searched.
Omit --review-keywords to use normal paginated collection.

Keyword responses may omit place_info. The collector fetches the restaurant name once using
the same place ID without a keyword, then reuses it across keyword searches. This extra request
counts toward --max-pages. Use --name "Verified restaurant name" to provide the name explicitly.
For 10 keywords, --max-pages 11 permits 10 searches plus one metadata lookup.

## Food-review keyword library

~~~powershell
.\.venv\Scripts\python.exe collect_reviews.py "RESTAURANT_MAPS_URL" --provider serpapi --keyword-library food --limit 50 --max-pages 25
~~~

The food library supplies 21 query terms: 16 food/service-relevant terms selected from SentiLexM
and five manually added supplements, including mantap and negated phrases. The selection
interleaves favorable and unfavorable search words. It supplies keywords only; no sentiment
scores or positive/negative labels are assigned to reviews or added to CSV/JSON.

Edit reviews/food_search_keywords.json to customize the list. The keywords field contains
the SentiLexM selection and supplemental_keywords contains the manual additions. Source
revision is recorded there. SentiLexM is MIT licensed; its license is included in
docs/SentiLexM-LICENSE.txt. Source: https://github.com/AsyrafAzlan/SentiLexM

You can combine --keyword-library food with --review-keywords "additional,terms"; repeated
terms are removed. Searches use at most five reviews per keyword, and the existing Malay
filter, original-text preservation and review deduplication still apply. The 50-review target
is a ceiling. --max-pages 25 permits the current 21 searches plus a name lookup if required.
The program stops early on reaching the saved-review limit. Actual requests may consume credits.
It never searches the full upstream lexicon automatically. No live requests are made by tests.

Keyword selection biases sampling toward explicit opinion words; document that collection
method when building your later NLP training dataset.

Successful keyword responses marked No reviews are skipped, even when SerpAPI omits the reviews field. The manifest lists them in empty_keyword_searches. Unexpected schemas and API errors still stop the run.
