#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Web crawl-speed dashboard built on the monitor base.

A background thread samples :class:`CrawlStatsCollector` on a fixed cadence and
caches the latest serialized stats plus a bounded rate history. HTTP clients
only ever read the cache, so any number of browser tabs add zero extra load on
MySQL. The page polls ``/api/stats`` and draws a self-contained canvas chart
(no external CDN).

Run::

    uv run python -m ai_conference_paper_crawler.monitor.web --port 8787
"""

import argparse
import threading
import time
from collections import deque

from flask import Flask, jsonify, render_template_string

from .collector import CrawlStatsCollector


class StatsSampler:
    """Owns the collector and samples it on a background daemon thread."""

    def __init__(self, interval=5.0, target=None, window=12, history=180, persist=True):
        self.interval = interval
        self.target = target
        self.window = window
        self.persist = persist
        self._history = deque(maxlen=history)
        self._latest = {}
        self._lock = threading.Lock()
        self._thread = None
        self._stop = threading.Event()

    def start(self):
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        with CrawlStatsCollector(
            target=self.target, window=self.window, persist=self.persist
        ) as col:
            # Seed the chart with persisted history so a fresh page already
            # shows the speed curve from previous samples/runs.
            past = col.load_history(limit=self._history.maxlen)
            with self._lock:
                self._history.extend(past)
            while not self._stop.is_set():
                try:
                    col.poll()
                    stats = col.stats()
                    with self._lock:
                        self._latest = stats.to_dict()
                        self._history.append(
                            {
                                "t": stats.ts,
                                "instant": stats.rate_instant,
                                "avg": stats.rate_avg,
                                "ema": stats.rate_ema,
                                "total": stats.total,
                            }
                        )
                except Exception as exc:  # keep sampling despite transient errors
                    with self._lock:
                        self._latest = {"error": str(exc)}
                self._stop.wait(self.interval)

    def snapshot(self):
        with self._lock:
            return {
                "stats": dict(self._latest),
                "history": list(self._history),
                "interval": self.interval,
            }

    def stop(self):
        self._stop.set()


_PAGE = """<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Crawl Monitor</title>
<style>
  :root { color-scheme: dark; }
  body { margin:0; font-family: system-ui, sans-serif; background:#0f1115; color:#e6e6e6; }
  header { padding:16px 24px; border-bottom:1px solid #222; display:flex;
           justify-content:space-between; align-items:center; }
  h1 { font-size:16px; margin:0; color:#5bc0eb; }
  #updated { color:#888; font-size:12px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr));
          gap:12px; padding:24px; }
  .card { background:#171a21; border:1px solid #222; border-radius:10px; padding:16px; }
  .card .label { color:#9aa4b2; font-size:12px; }
  .card .value { font-size:26px; font-weight:700; margin-top:6px; }
  .value.green { color:#3ddc84; } .value.yellow { color:#f5c542; }
  .wrap { padding:0 24px 24px; }
  canvas { width:100%; height:240px; background:#171a21; border:1px solid #222; border-radius:10px; }
  table { width:100%; border-collapse:collapse; margin-top:12px; }
  td, th { text-align:left; padding:6px 10px; border-bottom:1px solid #222; font-size:13px; }
  th { color:#9aa4b2; } td.n { text-align:right; font-variant-numeric:tabular-nums; }
</style>
</head>
<body>
<header>
  <h1>AI Conference Paper Crawler — 实时爬取速度</h1>
  <span id="updated">连接中…</span>
</header>
<div class="grid" id="cards"></div>
<div class="wrap"><canvas id="chart" width="1200" height="240"></canvas></div>
<div class="wrap"><table id="groups"><thead><tr><th>会议 / 年份</th><th class="n">数量</th></tr></thead><tbody></tbody></table></div>
<script>
const REFRESH = {{ interval }} * 1000;
function fmtDur(s){ if(s==null) return '—'; s=Math.floor(s); const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;
  return h? `${h}:${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}` : `${String(m).padStart(2,'0')}:${String(x).padStart(2,'0')}`; }
function card(label,value,cls){ return `<div class="card"><div class="label">${label}</div><div class="value ${cls||''}">${value}</div></div>`; }
function drawChart(hist){
  const c=document.getElementById('chart'), ctx=c.getContext('2d');
  const W=c.width,H=c.height,P=30; ctx.clearRect(0,0,W,H);
  if(!hist.length) return;
  const vals=hist.map(h=>h.ema), max=Math.max(1,...vals);
  ctx.strokeStyle='#2a2f3a'; ctx.lineWidth=1;
  for(let i=0;i<=4;i++){ const y=P+(H-2*P)*i/4; ctx.beginPath(); ctx.moveTo(P,y); ctx.lineTo(W-P,y); ctx.stroke();
    ctx.fillStyle='#666'; ctx.font='11px sans-serif'; ctx.fillText(Math.round(max*(1-i/4)),4,y+3); }
  function line(key,color){ ctx.strokeStyle=color; ctx.lineWidth=2; ctx.beginPath();
    hist.forEach((h,i)=>{ const x=P+(W-2*P)*i/Math.max(1,hist.length-1), y=P+(H-2*P)*(1-h[key]/max);
      i?ctx.lineTo(x,y):ctx.moveTo(x,y); }); ctx.stroke(); }
  line('avg','#5bc0eb'); line('ema','#3ddc84');
  ctx.fillStyle='#5bc0eb'; ctx.fillText('avg',W-70,16); ctx.fillStyle='#3ddc84'; ctx.fillText('ema',W-40,16);
}
async function tick(){
  try{
    const r=await fetch('/api/stats'); const d=await r.json(); const s=d.stats||{};
    if(s.error){ document.getElementById('updated').textContent='错误: '+s.error; return; }
    const rc = s.rate_avg>0 ? 'green':'yellow';
    document.getElementById('cards').innerHTML =
      card('已抓取总数', (s.total||0).toLocaleString()) +
      card('瞬时 items/min', (s.rate_instant||0).toFixed(1), rc) +
      card('平均 items/min', (s.rate_avg||0).toFixed(1)) +
      card('EMA items/min', (s.rate_ema||0).toFixed(1)) +
      card('本轮新增', '+'+(s.delta||0)) +
      card('已运行', fmtDur(s.elapsed_s)) +
      (s.target? card('目标/进度', (s.target).toLocaleString()+' ('+(100*s.total/s.target).toFixed(1)+'%)') : '') +
      (s.eta_s!=null? card('ETA', fmtDur(s.eta_s)) : '') +
      (s.abstract_pct!=null? card('abstract 覆盖', (s.abstract_pct).toFixed(1)+'%') : '') +
      card('PDF 落地', (s.local_path_pct||0).toFixed(1)+'%');
    const tb=document.querySelector('#groups tbody'); tb.innerHTML='';
    Object.entries(s.per_group||{}).forEach(([k,v])=>{ const tr=document.createElement('tr');
      tr.innerHTML=`<td>${k}</td><td class="n">${v.toLocaleString()}</td>`; tb.appendChild(tr); });
    drawChart(d.history||[]);
    document.getElementById('updated').textContent='更新于 '+new Date().toLocaleTimeString();
  }catch(e){ document.getElementById('updated').textContent='离线，重试中…'; }
}
tick(); setInterval(tick, REFRESH);
</script>
</body>
</html>"""


def create_app(sampler):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(_PAGE, interval=sampler.interval)

    @app.route("/api/stats")
    def api_stats():
        return jsonify(sampler.snapshot())

    return app


def main(argv=None):
    parser = argparse.ArgumentParser(description="Live crawl-speed web dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--interval", type=float, default=5.0, help="sample seconds")
    parser.add_argument(
        "--target", type=int, default=None, help="expected total for ETA"
    )
    parser.add_argument("--window", type=int, default=12, help="rolling avg samples")
    parser.add_argument(
        "--history", type=int, default=180, help="chart points to keep/seed"
    )
    parser.add_argument(
        "--no-persist",
        dest="persist",
        action="store_false",
        help="do not write samples to crawl_speed_history",
    )
    parser.set_defaults(persist=True)
    args = parser.parse_args(argv)

    sampler = StatsSampler(
        interval=args.interval,
        target=args.target,
        window=args.window,
        history=args.history,
        persist=args.persist,
    )
    sampler.start()
    app = create_app(sampler)
    print(f"crawl monitor at http://{args.host}:{args.port}  (Ctrl-C to stop)")
    try:
        app.run(host=args.host, port=args.port, threaded=True)
    finally:
        sampler.stop()


if __name__ == "__main__":
    main()
