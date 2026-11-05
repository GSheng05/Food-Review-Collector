# Food Review Collector

A separate, history-preserving derivative of [GSheng05/Web-Scrapper](https://github.com/GSheng05/Web-Scrapper).
The original crawler modules (`crawl.py`, `main.py`, `json_report.py`) remain unchanged.
Their usage is in [README-crawler.md](README-crawler.md).

Give the new collector a Google Maps restaurant URL or Shopee food-product URL. It attempts to walk the reviews exposed by the website and exports:

- `raw_review`: original review text, without language filtering, cleaning, spelling correction or translation.
- `source_url`: restaurant/product page URL.
- `source_name`: restaurant/product name.
- `price_range`: the reviewer's structured price-per-person range when available.
- Platform, rating, review date and collection timestamp when available.

Review ID, review URL and product category are not exported. Source IDs are held only in memory to avoid collecting the same card twice. Source URL remains in the exports.

**Status: framework with passing offline extraction tests. Live testing of the supplied Google Maps link showed a limited view without reviews; the Shopee product link redirected to a login/traffic error. Five full Gepuklah reviews were later collected through the visible browser; bulk CLI extraction and Shopee extraction still need live validation. Do not assume all reviews were collected.**

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

Without `--interactive`, the browser runs headlessly and stops if a login/verification gate is detected. The tool does not solve CAPTCHAs or bypass access controls. Use sources you are permitted to collect from and review platform collection conditions before running a large collection.

Omit `--limit` to collect until the exposed list ends, stalls or reaches the safety time limit. Defaults: 2 seconds between batches, 5 idle rounds and 30 minutes maximum after source setup. Change these with `--delay`, `--idle-rounds`, `--max-minutes`. `--name` explicitly overrides the page name if necessary.

Each run gets a new folder under `output/`. `--output PATH` chooses a new/empty folder. Existing nonempty folders are rejected to prevent overwrites. This version checkpoints results after each batch but does not resume browser pagination after an interrupted run.

## Output

Price Range preserves the source currency and range, for example `RM 20–40`. It is the reviewer's stated spend per person, not a restaurant-wide estimate or a number inferred from their prose. Shopee reviews currently have no equivalent verified field in this adapter, so their price range is blank; a current listing price is not substituted for historical reviewer spending.

`reviews.json` is the authoritative UTF-8 raw dataset. Empty text reviews and identical text from different review IDs remain in the file. Only repeated observations of the **same source review ID on the same page** are suppressed during scrolling. Text is preserved as returned by the browser DOM (Maps) or the original comment response (Shopee); DOM text is not byte-for-byte original submission HTML.

`reviews.csv` uses the revised collection columns requested by the user (the original assignment template is not modified):

| Column | Value |
|---|---|
| Data Origin | Self-Collected (Real) |
| Product / Eatery Name | `source_name` |
| Source Platform | Google Reviews or Shopee |
| Source URL | `source_url` |
| Rating (1-5) | Source value, otherwise blank |
| Review Date | Source date; Google may expose a relative date such as `2 weeks ago` |
| Price Range | Structured Price per person from the review, otherwise blank |
| Review Text | Original `raw_review` |
| Language Classification | Blank for later annotation |
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
