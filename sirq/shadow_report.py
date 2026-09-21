from __future__ import annotations

import html
from collections import Counter
from pathlib import Path
from typing import Iterable

from .oncall import Recommendation, ShadowRecord


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def _time_label(value: str) -> str:
    try:
        return value.split("T", 1)[1][:5]
    except IndexError:
        return value[-8:]


def render_shadow_html(records: Iterable[ShadowRecord], title: str = "SIRQ shadow mode") -> str:
    records = list(records)
    total = len(records)
    existing_interruptions = sum(r.alert.existing_outcome.paged_human for r in records)
    sirq_interruptions = sum(r.recommendation == Recommendation.INTERRUPT for r in records)
    reduction = (existing_interruptions - sirq_interruptions) / existing_interruptions if existing_interruptions else 0.0
    reviewed = [r for r in records if r.alert.review]
    correct = sum(r.alert.review.value == "correct" for r in reviewed)
    incorrect = sum(r.alert.review.value == "incorrect" for r in reviewed)
    unsure = sum(r.alert.review.value == "unsure" for r in reviewed)
    accuracy = correct / len(reviewed) if reviewed else 0.0
    recommendation_counts = Counter(r.recommendation.value for r in records)
    rows = []
    for record in records:
        outcome = record.alert.existing_outcome
        rows.append(f"""
        <article class="alert-row {'interrupt' if record.recommendation == Recommendation.INTERRUPT else ''}">
          <div class="time">{html.escape(_time_label(record.alert.observed_at))}</div>
          <div class="alert-main"><strong>{html.escape(record.alert.service)}</strong><span>{html.escape(record.event.kind)}</span><small>{html.escape(record.reason)}</small></div>
          <div class="existing"><span>{'🔔 paged' if outcome.paged_human else 'logged'}</span><small>{html.escape(outcome.destination)}</small></div>
          <div class="recommendation {record.recommendation.value.lower()}"><b>{record.recommendation.value.replace('_', ' ')}</b><small>confidence {record.event.confidence:.2f}</small></div>
        </article>""")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root {{ color-scheme:dark; --bg:#070d18; --panel:#101b2b; --panel2:#15253a; --text:#edf5ff; --muted:#91a5bd; --line:#263b56; --cyan:#7dd3fc; --green:#4ade80; --amber:#fbbf24; --red:#fb7185; }}
* {{ box-sizing:border-box }} body {{ margin:0; background:radial-gradient(circle at 80% 0%,#123050 0,#070d18 44%); color:var(--text); font:15px system-ui,sans-serif }} main {{ max-width:1180px; margin:auto; padding:42px 22px 70px }} h1 {{ margin:0; font-size:clamp(32px,5vw,56px) }} h2 {{ margin:0 0 12px }} .lede {{ color:var(--muted); font-size:18px; max-width:720px; line-height:1.55 }} .eyebrow {{ color:var(--cyan); font:600 12px ui-monospace,monospace; letter-spacing:.12em; text-transform:uppercase }}
.grid {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:30px 0 }} .card,.alert-row {{ background:rgba(16,27,43,.94); border:1px solid var(--line); border-radius:14px }} .card {{ padding:18px }} .card span {{ color:var(--muted); display:block }} .card b {{ color:var(--cyan); display:block; font-size:34px; margin-top:7px }} .card.good b {{ color:var(--green) }} .card.warn b {{ color:var(--amber) }} .card.hot b {{ color:var(--red) }} .card small {{ color:var(--muted) }}
.proof {{ display:grid; grid-template-columns:1fr 1fr; gap:14px; margin:22px 0 30px }} .proof .card {{ min-height:120px }} .bar {{ height:10px; border-radius:9px; background:#20334b; overflow:hidden; margin-top:14px }} .bar span {{ display:block; height:100%; background:linear-gradient(90deg,var(--green),var(--cyan)) }} .alert-list {{ display:grid; gap:8px }} .alert-row {{ display:grid; grid-template-columns:90px 1.7fr 1fr 1fr; align-items:center; gap:14px; padding:15px 18px }} .alert-row.interrupt {{ border-color:var(--red); box-shadow:0 0 24px #fb718522 }} .time {{ color:var(--cyan); font:600 15px ui-monospace,monospace }} .alert-main strong,.alert-main span,.alert-main small,.existing span,.existing small,.recommendation b,.recommendation small {{ display:block }} .alert-main span,.existing span {{ margin-top:3px }} .alert-main small,.existing small,.recommendation small {{ color:var(--muted); margin-top:4px }} .existing span {{ color:var(--amber) }} .recommendation b {{ color:var(--green) }} .recommendation.notify b {{ color:var(--amber) }} .recommendation.interrupt b {{ color:var(--red) }} .footer-note {{ color:var(--muted); margin-top:26px; line-height:1.55 }}
@media(max-width:800px) {{ .grid,.proof {{ grid-template-columns:repeat(2,1fr) }} .alert-row {{ grid-template-columns:70px 1fr 1fr }} .recommendation {{ grid-column:2 / -1 }} }} @media(max-width:520px) {{ .grid,.proof {{ grid-template-columns:1fr 1fr }} .alert-row {{ grid-template-columns:1fr 1fr }} .time {{ grid-column:1 / -1 }} }}
</style></head><body><main>
<div class="eyebrow">SIRQ · shadow mode · no production actions</div><h1>One bad night on call</h1><p class="lede">SIRQ watches the existing alert stream and records what it would have done. PagerDuty, Slack, Discord, and humans remain untouched.</p>
<section class="grid"><div class="card"><span>alerts observed</span><b>{total}</b><small>incoming production alerts</small></div><div class="card warn"><span>existing interruptions</span><b>{existing_interruptions}</b><small>what the current path delivered</small></div><div class="card good"><span>SIRQ interruptions</span><b>{sirq_interruptions}</b><small>what SIRQ would wake a human for</small></div><div class="card good"><span>potential reduction</span><b>{_pct(reduction)}</b><small>shadow-mode estimate</small></div></section>
<section class="proof"><div class="card"><h2>Would SIRQ have been right?</h2><span>{len(reviewed)} reviewed · {correct} correct · {incorrect} incorrect · {unsure} unsure</span><div class="bar"><span style="width:{round(accuracy*100)}%"></span></div><small>reviewed accuracy: {_pct(accuracy) if reviewed else 'not reviewed yet'}</small></div><div class="card"><h2>Production actions taken</h2><b style="color:var(--green);font-size:42px">ZERO</b><small>The first version only observes, recommends, and learns.</small></div></section>
<h2>Alert timeline</h2><section class="alert-list">{''.join(rows)}</section>
<p class="footer-note">The business question is simple: how many times did the existing system wake a human, and how many of those interruptions were actually necessary? Shadow mode answers that without changing the production alert path.</p>
</main></body></html>"""


def write_shadow_report(records: Iterable[ShadowRecord], path: str | Path, title: str = "SIRQ shadow mode") -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_shadow_html(records, title), encoding="utf-8")
    return destination
