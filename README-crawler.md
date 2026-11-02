# Web Crawler

A concurrent web crawler built with Python that extracts structured data from websites, including headings, paragraphs, links, and images. It uses `asyncio` and `aiohttp` to perform high-performance concurrent crawling while respecting configurable limits.

## Features

* **Concurrent crawling** with configurable concurrency limits
* **Maximum pages limit** to control the scope of the crawl
* **Same-domain restriction** to prevent crawling unrelated websites
* **URL normalization** to detect and avoid duplicate pages
* **Structured data extraction**, including:

  * Page headings (`h1`, `h2`)
  * First paragraph content
  * Outgoing links
  * Image URLs
* **JSON report generation** for easy data analysis
* **Command-line interface (CLI)** for flexible configuration
* **Unit testing** for the crawling functionality

## Installation

### Prerequisites

* Python 3.8+
* [uv](https://docs.astral.sh/uv/) package manager (recommended)

### Clone the Repository

```bash
git clone https://github.com/GSheng05/Web-Scrapper.git
cd Web-Scrapper
```

### Install Dependencies

Using `uv` (recommended):

```bash
uv sync
```

Alternatively, using `pip`:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

Run the crawler with a URL:

```bash
uv run main.py https://example.com
```

The crawler uses the following default settings:

| Setting             | Default |
| ------------------- | ------: |
| Maximum concurrency |     `5` |
| Maximum pages       |   `100` |

### Advanced Usage

The command accepts optional arguments for controlling concurrency and the maximum number of pages:

```bash
uv run main.py URL [max_concurrency] [max_pages]
```

#### Examples

Crawl with **3 concurrent requests**:

```bash
uv run main.py https://example.com 3
```

Crawl with **3 concurrent requests** and a **10-page limit**:

```bash
uv run main.py https://example.com 3 10
```

Crawl with **10 concurrent requests** and a **50-page limit**:

```bash
uv run main.py https://example.com 10 50
```

## Output

After crawling, the application generates a `report.json` file containing structured information about the pages that were successfully crawled.

The report includes:

* Page URLs
* Page headings
* First paragraph
* Outgoing links
* Image URLs

All crawled pages are sorted by URL to ensure consistent and predictable output.

### Example Output Structure

```json
{
  "https://example.com": {
    "headings": [
      "Example Domain"
    ],
    "first_paragraph": "This domain is for use in illustrative examples...",
    "links": [
      "https://example.com/about"
    ],
    "images": []
  }
}
```

> **Note:** The exact contents of `report.json` depend on the website being crawled.

## Testing

The project includes a unit test suite for validating the crawler's functionality.

Run all tests with:

```bash
uv run -m unittest
```

For more detailed test output:

```bash
uv run -m unittest -v
```

## Project Structure

```text
.
├── crawl.py          # Core crawling logic and data extraction
├── main.py           # Command-line interface entry point
├── json_report.py    # JSON report generation
├── test_crawl.py     # Unit tests
└── report.json       # Generated crawl report
```

## How It Works

The crawler follows several steps to collect and process website data.

### 1. URL Normalization

URLs are converted into a canonical format before being processed. This helps the crawler identify duplicate URLs and prevents the same page from being crawled multiple times.

### 2. HTML Parsing

The crawler retrieves the HTML content of each page and uses **BeautifulSoup** to parse the document.

It extracts:

* `h1` and `h2` headings
* The first paragraph
* Outgoing links
* Image URLs

### 3. Concurrent Crawling

The crawler uses Python's **`asyncio`** framework together with **`aiohttp`** to make multiple HTTP requests concurrently.

The number of simultaneous requests can be controlled using the `max_concurrency` setting.

### 4. Data Storage

Information collected from each page is stored in memory while the crawler is running.

The crawler continues discovering and processing pages until either:

* There are no more pages to crawl, or
* The `max_pages` limit has been reached.

### 5. Report Generation

Once crawling is complete, the collected data is passed to the JSON report generator.

The results are written to:

```text
report.json
```

The pages are sorted by URL to provide consistent output.

## Configuration

The crawler's behaviour can be configured in `crawl.py`.

### Maximum Concurrency

Controls the maximum number of requests that can be made simultaneously.

```python
max_concurrency = 5
```

A higher value can increase crawling speed, but excessive concurrency may put unnecessary load on the target website or cause requests to be blocked.

### Maximum Pages

Controls the maximum number of pages that the crawler will process.

```python
max_pages = 100
```

This prevents the crawler from continuing indefinitely on websites with a large number of pages.

### User-Agent

The HTTP `User-Agent` string can be configured in the `get_html` method.

This identifies the crawler when making HTTP requests.

## Limitations

* The crawler only processes pages belonging to the **same domain** as the starting URL.
* The number of crawled pages is restricted by the `max_pages` limit.
* Some websites may block or restrict automated crawlers.
* Websites that rely heavily on JavaScript may not expose all their content through the retrieved HTML.
* Crawling performance depends on the target website's response time and network conditions.

## Technologies Used

* **Python** — Core programming language
* **asyncio** — Asynchronous programming and concurrency
* **aiohttp** — Asynchronous HTTP requests
* **BeautifulSoup** — HTML parsing and data extraction
* **JSON** — Structured report generation
* **unittest** — Automated testing
* **uv** — Python package and project management

## License

This project is for educational purposes and was developed as part of the **Boot.dev** curriculum.

## Contributing

Contributions are welcome!

If you find a bug or have an idea for an improvement, feel free to:

1. Open an issue describing the problem or enhancement.
2. Submit a pull request with your proposed changes.

---

**Happy crawling! 🕷️**
