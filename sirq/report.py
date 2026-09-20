from __future__ import annotations

import html
import json
from collections import Counter
from pathlib import Path
from typing import Iterable

from .policy import PolicyDecision


def _bar(value: float, color: str = "#7dd3fc") -> str:
    width = max(0, min(100, round(value * 100)))
    return f'<div class="bar"><span style="width:{width}%;background:{color}"></span></div>'


def render_html(decisions: Iterable[PolicyDecision], title: str = "SIRQ semantic replay") -> str:
    decisions = list(decisions)
    kinds = Counter(d.event.kind for d in decisions)
    handlers = Counter(d.handler for d in decisions if d.allowed)
    cards = []
    for decision in decisions:
        event = decision.event
        evidence = []
        observations = event.observation.get("observations", {})
        if observations.get("failures_5m") is not None:
            evidence.append(f"failures_5m={observations['failures_5m']}")
        if observations.get("latency_p95_ms") is not None:
            evidence.append(f"latency_p95_ms={observations['latency_p95_ms']}")
        if observations.get("message"):
            evidence.append(str(observations["message"]))
        cards.append(f"""
        <article class="event {'hot' if event.priority >= 5 else ''}">
          <div class="event-head"><strong>{html.escape(event.kind)}</strong><span>P{event.priority}</span></div>
          <div class="source">{html.escape(event.source)} · {html.escape(decision.reason)}</div>
          <div class="metric"><label>confidence</label><b>{event.confidence:.2f}</b>{_bar(event.confidence)}</div>
          <div class="metric"><label>human attention</label><b>{event.human_attention:.2f}</b>{_bar(event.human_attention, '#fb7185')}</div>
          <div class="evidence">{' · '.join(html.escape(x) for x in evidence) or 'no special evidence'}</div>
          <div class="decision">{html.escape(decision.handler)} {'allowed' if decision.allowed else 'suppressed'}</div>
        </article>""")
    summary = "".join(f"<li><b>{html.escape(k)}</b><span>{v}</span></li>" for k, v in kinds.items())
    actions = "".join(f"<li><b>{html.escape(k)}</b><span>{v}</span></li>" for k, v in handlers.items()) or "<li><b>none</b><span>0</span></li>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
:root {{ color-scheme: dark; --bg:#08111f; --panel:#101d30; --muted:#91a4bc; --text:#e5eef9; --line:#22344d; --accent:#7dd3fc; }}
* {{ box-sizing:border-box }} body {{ margin:0; font:15px system-ui,sans-serif; background:linear-gradient(135deg,#08111f,#0d1727); color:var(--text) }}
main {{ max-width:1100px; margin:auto; padding:48px 22px }} h1 {{ font-size:42px; margin:0 0 8px }} h2 {{ margin-top:0 }} .lede {{ color:var(--muted); font-size:18px; max-width:720px }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin:28px 0 }} .panel,.event {{ background:rgba(16,29,48,.92); border:1px solid var(--line); border-radius:14px; padding:18px }}
.stat b {{ display:block; font-size:30px; color:var(--accent) }} .stat span,.source,label,.evidence {{ color:var(--muted) }} ul {{ list-style:none; padding:0; margin:10px 0 0 }} li {{ display:flex; justify-content:space-between; padding:7px 0; border-bottom:1px solid var(--line) }}
.events {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:14px }} .event.hot {{ border-color:#fb7185; box-shadow:0 0 24px #fb718522 }} .event-head,.metric,.decision {{ display:flex; justify-content:space-between; gap:12px; align-items:center }} .source {{ margin:8px 0 16px; font-size:13px }} .metric {{ margin:9px 0 }} .metric label {{ min-width:120px }} .bar {{ height:7px; flex:1; background:#1d2d43; border-radius:8px; overflow:hidden }} .bar span {{ display:block; height:100% }} .evidence {{ min-height:35px; margin:16px 0; font-family:ui-monospace,monospace; font-size:12px }} .decision {{ border-top:1px solid var(--line); padding-top:12px; color:var(--accent); font-weight:600 }}
</style></head><body><main><h1>Semantic replay report</h1><p class="lede">AI interprets system state. Deterministic policy decides what is allowed to matter.</p>
<div class="grid"><div class="panel stat"><span>observations</span><b>{len(decisions)}</b></div><div class="panel stat"><span>high priority</span><b>{sum(d.event.priority >= 5 for d in decisions)}</b></div><div class="panel stat"><span>allowed actions</span><b>{sum(d.allowed for d in decisions)}</b></div><div class="panel stat"><span>suppressed</span><b>{sum(not d.allowed for d in decisions)}</b></div></div>
<div class="grid"><section class="panel"><h2>Semantic events</h2><ul>{summary}</ul></section><section class="panel"><h2>Policy outcomes</h2><ul>{actions}</ul></section></div>
<h2>Event stream</h2><section class="events">{''.join(cards)}</section></main></body></html>"""


def write_report(decisions: Iterable[PolicyDecision], path: str | Path, title: str = "SIRQ semantic replay") -> Path:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_html(decisions, title), encoding="utf-8")
    return destination
