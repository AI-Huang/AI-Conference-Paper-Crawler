# AI-Conference-Paper-Crawler

AI-Conference-Paper-Crawler, a [Scrapy](https://scrapy.org/)-based crawler for
downloading AI conference papers (CVF/CVPR and more).

## Install

```bash
uv sync
```

## Usage

Run with the Scrapy CLI (recommended):

```bash
# Download all CVPR2017 papers into papers/CVPR2017/
scrapy crawl cvf -a conf=CVPR2017

# Multi-day conferences accept a day index
scrapy crawl cvf -a conf=CVPR2018 -a day_index=0

# IROS — requires a free IEEE Developer API key (see below)
scrapy crawl ieee -a conf=IROS -a year=2023
scrapy crawl ieee -a conf=IROS          # all supported IROS years (2013–2023)
```

Or via the convenience runner:

```bash
python main.py --conf CVPR2017
```

Downloaded PDFs are stored under `papers/<conf>/`. Override the location with the
`CVF_FILES_STORE` environment variable.

### IEEE Xplore conferences (IROS)

Papers from IEEE Xplore (e.g. IROS) are accessed through the
[IEEE Xplore Developer API](https://developer.ieee.org/).

1. Register for a **free API key** at <https://developer.ieee.org/>.
2. Add it to your `.env`:
   ```
   IEEE_API_KEY=your_key_here
   ```
3. Run the spider:
   ```bash
   scrapy crawl ieee -a conf=IROS -a year=2023
   ```

> **Note:** Paper metadata (title, authors, abstract) is always available.
> Downloading full-text PDFs requires institutional access to IEEE Xplore.

## Live speed dashboard

Watch crawl throughput in real time, headlined by **papers per second** (with
papers/min, totals, coverage and ETA as context). It polls the MySQL `papers`
table on a fixed cadence and repaints an in-place terminal board:

```bash
# 终端看板
uv run crawl-monitor --interval 5 --target 5000
# 或 uv run python -m ai_conference_paper_crawler.monitor.tui

# 网页看板 → http://127.0.0.1:8787
uv run crawl-monitor-web --port 8787 --interval 5 --target 5000
```

Press `Ctrl-C` to quit. The dashboard reads the same `MYSQL_*` env vars as the
crawler (loaded from `.env`).

### Historical speed

Each sample is persisted to the MySQL `crawl_speed_history` table, so the speed
curve survives restarts: a freshly opened dashboard is seeded with the recent
history (`--history N` points) and keeps appending new samples. Pass
`--no-persist` to run a read-only session that does not write history.

## Project layout

```text
scrapy.cfg                     # Scrapy project entrypoint
ai_conference_paper_crawler/
    settings.py                # Scrapy settings (pipelines, throttling, FILES_STORE)
    items.py                   # PaperItem definition
    pipelines.py               # CvfFilesPipeline -> papers/<conf>/<file>.pdf
    links.py                   # Conference URL / link logic
    spiders/cvf.py             # CvfSpider
    utils/dir_utils.py
main.py                        # CrawlerProcess runner
```

## Reference

[1] Computer Vision Foundation, open access,
[https://openaccess.thecvf.com/menu](https://openaccess.thecvf.com/menu)
