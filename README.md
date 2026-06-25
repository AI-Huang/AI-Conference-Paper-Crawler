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
```

Or via the convenience runner:

```bash
python main.py --conf CVPR2017
```

Downloaded PDFs are stored under `papers/<conf>/`. Override the location with the
`CVF_FILES_STORE` environment variable.

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
