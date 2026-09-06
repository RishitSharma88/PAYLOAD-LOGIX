# Satsearch Satellite Component Scraper — Exhaustive Dataset Edition

An asynchronous Python scraping engine built with **Playwright (async)**, **BeautifulSoup4**, **aiohttp**, **pandas** and **Wayback Machine** to extract **every satellite component** from marketplace pages structured like [satsearch.co](https://satsearch.co) for AI training.

> **Why Wayback Machine?** `satsearch.co` is protected by Cloudflare Turnstile (`Just a moment...` 403). Headless Playwright is blocked in datacenter/CI environments. The scraper now defaults to `wayback` mode which fetches archived snapshots via `web.archive.org` (bypasses Cloudflare) and still supports `live` Playwright for residential IPs.

---

## 🌟 Features

1. **Dual-mode Fetching:**
   - `wayback` (default): `aiohttp` → `web.archive.org/cdx` + `web.archive.org/web/{ts}/{url}` (no browser needed, Cloudflare bypass).
   - `live`: Async Playwright Chromium with Turnstile waiting + dynamic rendering.

2. **Exhaustive Satellite Discovery:**
   - `CDX API` discovery: `https://web.archive.org/cdx/search/cdx?url=satsearch.co/products/*` (23k unique products).
   - `Category crawl` discovery: Enumerates `Satellites and subsystems` leaf categories via Wayback (e.g. `power/solar-panels`, `payload/camera`, `orbit-determination-and-control/thruster`, `communication/transceiver|antenna`, etc.) and paginates `?page=N` to collect every product link. With `--exhaustive` discovers 250+ satellite products per run, scalable to thousands.

3. **BeautifulSoup Extraction Schema** (`satsearch_scraper.py:143`):
   - `title`: Product name (e.g. *"6U Solar Panel"*)
   - `supplier`: Manufacturer (e.g. *"EnduroSat"*)
   - `category_breadcrumbs`: Hierarchical list (e.g. `["Satellite","Power","Solar Panel"]`)
   - `key_highlights`: Paragraph under "KEY HIGHLIGHTS" or first long descriptive paragraph fallback
   - `technical_specs`: Dynamic dict from "TECHNICAL SPECS" tables / `dl` / grid (`{"width":"130 mm",...}`)
   - `downloads`: Map `Datasheet|CAD Model|ICD|User manual|Option sheet` → direct S3 PDF URL or `"Request"`/`"Available"` (Wayback-wrapped URLs are unwrapped)
   - `last_updated`: `Last updated: 2024-08-19` string
   - `source_url`: Original `https://satsearch.co/products/...` URL

4. **Automated PDF Downloader (`aiohttp`)** (`satsearch_scraper.py:350`):
   - Detects S3 PDF links (`satsearch.s3.eu-central-1.amazonaws.com`), unwraps Wayback prefix, downloads into `./datasheets/`.
   - Filename: `[Supplier]_[Product_Title]_datasheet.pdf` sanitized (`satsearch_scraper.py:168`).

5. **Structured Exports** (`satsearch_scraper.py:447`):
   - `components_dataset.jsonl`: One JSON per line (streaming ETL).
   - `components_dataset.csv`: Flattened where each `technical_specs` key becomes `spec_*` column.

6. **Production Quality & Resilience:**
   - `asyncio.Semaphore(3)` concurrency (`satsearch_scraper.py:97`)
   - Randomized 1–3s delays (`satsearch_scraper.py:108`)
   - Per-page try/except, Cloudflare `Just a moment...` waiting, Wayback fallback via CDX latest timestamp, logs to `scraper.log` without crashing.

---

## 🛠️ Setup

### Prerequisites
- Python 3.9+
- `pip`

### Installation
```bash
python3 -m venv venv
source venv/bin/activate  # Linux/macOS  |  venv\Scripts\activate (Windows)
pip install -r requirements.txt
playwright install chromium  # only needed for --mode live
```

`requirements.txt`:
```
playwright>=1.40.0
beautifulsoup4>=4.12.0
aiohttp>=3.9.0
pandas>=2.0.0
lxml>=5.0.0
```

---

## 🚀 Execution Guide — Build Your AI Dataset

### Default (Auto): Wayback exhaustive satellite crawl (50 products)
```bash
python satsearch_scraper.py
# alias for:
python satsearch_scraper.py --mode auto --limit 50 --concurrency 3
```
Discovers satellite products and writes `components_dataset.jsonl` + `components_dataset.csv`. Example run discovered 287 satellite products, scraped 12 successfully (others 404 due to outdated snapshot fallback).

### Exhaustive: Crawl every satellite component (hundreds)
```bash
python satsearch_scraper.py --mode wayback --exhaustive --concurrency 5
# or category-focused:
python satsearch_scraper.py --mode wayback --use-categories --limit 500 --concurrency 5
```
Fetches every leaf under `Satellites and subsystems` with pagination (3 pages/category). Scalable to the full 23k product corpus for large AI training sets. Use `--limit` to cap for testing.

### CDX Mode: Sample any N products (fast)
```bash
python satsearch_scraper.py --mode wayback --limit 100 --concurrency 5
```
Uses Wayback CDX `collapse=urlkey` for quick random sample across all products. Filter satellite-only afterwards via `category_breadcrumbs`.

### Live Mode: Direct Playwright (requires residential IP, bypasses Wayback)
```bash
python satsearch_scraper.py --mode live --urls \
  "https://satsearch.co/products/endurosat-6u-solar-panel" \
  "https://satsearch.co/products/aac-clyde-photon-solar-panels-3u-12u"

python satsearch_scraper.py --mode live --url-file urls.txt --concurrency 3
python satsearch_scraper.py --mode live --urls https://satsearch.co/products/xxx --no-headless  # debug
```

### Demo Mode: Synthetic 10-component dataset (no network)
```bash
python satsearch_scraper.py --demo
```

---

## 📁 Output Structure

### `components_dataset.jsonl` (real Wayback sample)
```json
{"title": "6U Solar Panel", "supplier": "EnduroSat", "category_breadcrumbs": ["Satellite", "Power", "Solar Panel", "6U Solar Panel"], "key_highlights": "", "technical_specs": {}, "downloads": {"Datasheet": "Request", "CAD Model": "Request"}, "last_updated": "2023-11-16", "source_url": "https://satsearch.co/products/endurosat-6u-solar-panel"}
{"title": "DMSA 3U/A: Deployable Multifunction Solar Array", "supplier": "Ecuadorian Space Agency (EXA)", "category_breadcrumbs": ["Satellites and subsystems", "Power solutions", "Solar panels", "DMSA 3U/A: Deployable Multifunction Solar Array"], "key_highlights": "The EXA DMSA 3U/A is a Deployable Multifunction Solar Array designed for 3U CubeSats...", "technical_specs": {}, "downloads": {"Datasheet": "https://satsearch.s3.eu-central-1.amazonaws.com/...pdf", "CAD Model": "Request"}, "last_updated": "2024-08-19", "source_url": "https://satsearch.co/products/exa-dmsa-3u-a-deployable-multifunction-solar-array"}
```

### `components_dataset.csv`
| title | supplier | category_breadcrumbs | key_highlights | downloads | last_updated | source_url | spec_width | ... |
|-------|----------|----------------------|----------------|-----------|--------------|------------|------------|-----|
| 6U Solar Panel | EnduroSat | Satellite > Power > Solar Panel | ... | {"Datasheet":"Request",...} | 2023-11-16 | https://satsearch.co/... |  |  |

### `./datasheets/`
`./datasheets/[Supplier]_[Product_Title]_datasheet.pdf` (S3 URLs expire after 24h → expect 403 if snapshot old; live mode yields fresh links).

---

## 🔍 Verification

```bash
wc -l components_dataset.jsonl && head -n 1 components_dataset.jsonl | python -m json.tool
column -t -s, components_dataset.csv | head
cat scraper.log | tail -n 30
ls -lh datasheets/
```

**Current verified run** (`--use-categories --limit 15`): 287 products discovered, 12 successfully scraped (satellite power + payload + propulsion + comms), 0 crashes. Logs in `scraper.log:1`.

---

## ⚙️ Tuning for Large AI Dataset

- Increase `--limit` or `--exhaustive` for more data (e.g. 1000).
- Increase `--concurrency` to 5–8 for speed (respect Wayback rate limits).
- Run overnight for full 23k corpus: `python satsearch_scraper.py --mode wayback --limit 5000 --concurrency 5`.
- For fresh PDFs, prefer `--mode live` on residential IP.

---

## 📝 Notes

- Wayback S3 signatures expire (403 on PDF download). Live mode gets fresh signatures.
- Some products lack `technical_specs` tables → `spec_*` columns sparse (flattened CSV handles this).
- Cloudflare Turnstile requires residential IP; CI/datacenter IPs are flagged → use `wayback` in CI.
