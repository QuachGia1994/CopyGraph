from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .htmlutil import safe_json_for_html


def render_forensic_dashboard(report: Mapping[str, object]) -> str:
    data = safe_json_for_html(report)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CopyGraph Forensic Report</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
body {{ margin:0; background:#111513; color:#e9f3ee; }}
main {{ max-width:1180px; margin:0 auto; padding:28px 20px 48px; }}
h1 {{ margin:0 0 8px; font-size:30px; }}
p.sub {{ color:#9db0a6; margin:0 0 20px; }}
section {{ margin-top:16px; padding:18px; border:1px solid #2a332e; border-radius:14px; background:#171d1a; overflow:auto; }}
h2 {{ margin:0 0 12px; font-size:17px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:10px; }}
.card {{ padding:12px; border:1px solid #2a332e; border-radius:10px; background:#111513; }}
.card strong {{ display:block; margin-top:4px; font-size:20px; }}
table {{ width:100%; border-collapse:collapse; min-width:760px; }}
th,td {{ padding:8px; text-align:left; border-bottom:1px solid #29312d; }}
th {{ color:#9db0a6; font-size:12px; text-transform:uppercase; }}
ul {{ margin:0; padding-left:20px; }}
.bar {{ display:flex; gap:8px; align-items:center; margin:5px 0; }}
.bar span:first-child {{ width:110px; color:#9db0a6; }}
.bar meter {{ width:240px; }}
#forensic-network svg {{ width:100%; height:180px; display:block; }}
</style>
</head>
<body>
<main>
<h1>CopyGraph Forensic Report</h1>
<p class="sub">Evidence-first local investigation</p>
<section id="forensic-summary"><h2>Summary</h2><div class="grid" data-role="summary"></div></section>
<section id="forensic-warnings"><h2>Warnings</h2><ul data-role="warnings"></ul></section>
<section id="forensic-timeline"><h2>Matched timeline</h2><div data-role="timeline"></div></section>
<section id="delay-histogram"><h2>Delay histogram</h2><div data-role="delay"></div></section>
<section id="lot-ratio-drift"><h2>Lot-ratio drift</h2><div data-role="ratio"></div></section>
<section id="symbol-breakdown"><h2>Symbol breakdown</h2><div data-role="symbols"></div></section>
<section id="supporting-evidence"><h2>Supporting evidence</h2><div data-role="supporting"></div></section>
<section id="contradictory-evidence"><h2>Contradictory evidence</h2><div data-role="contradictory"></div></section>
<section id="forensic-network"><h2>Investigated pair</h2><div data-role="network"></div></section>
</main>
<script id="copygraph-forensic-data" type="application/json">{data}</script>
<script>
const report = JSON.parse(document.getElementById('copygraph-forensic-data').textContent);
const byRole = role => document.querySelector(`[data-role="${{role}}"]`);
function text(tag, value) {{ const el=document.createElement(tag); el.textContent=String(value); return el; }}
function card(label, value) {{ const el=document.createElement('div'); el.className='card'; el.append(text('span',label), text('strong',value)); return el; }}
const summary=byRole('summary');
const accounts=report.accounts||[];
summary.append(
  card('Pair', accounts.join(' ↔ ')),
  card('Orientation', report.orientation||'—'),
  card('Raw confidence', Number(report.raw_confidence||0).toFixed(3)),
  card('Calibrated', report.calibrated_confidence==null?'—':Number(report.calibrated_confidence).toFixed(3)),
  card('Lead', report.lead_account||'—'),
  card('Median delay', report.median_delay_s==null?'—':`${{report.median_delay_s}} s`)
);
const warningList=byRole('warnings');
const warnings=report.warnings||[];
if(!warnings.length) warningList.append(text('li','No explicit uncertainty warnings'));
else warnings.forEach(item=>warningList.append(text('li',item)));
function tableInto(container, headers, rows) {{
  const table=document.createElement('table'); const head=document.createElement('thead'); const hr=document.createElement('tr');
  headers.forEach(h=>hr.append(text('th',h.label))); head.append(hr); table.append(head);
  const body=document.createElement('tbody');
  rows.forEach(row=>{{ const tr=document.createElement('tr'); headers.forEach(h=>tr.append(text('td',h.get(row)))); body.append(tr); }});
  table.append(body); container.append(table);
}}
tableInto(byRole('timeline'),[
  {{label:'A ID',get:r=>r.a_position_id}},{{label:'B ID',get:r=>r.b_position_id}},{{label:'Symbol',get:r=>r.symbol}},
  {{label:'A open',get:r=>r.a_open_time}},{{label:'B open',get:r=>r.b_open_time}},{{label:'Delay',get:r=>r.delay_s}},{{label:'Score',get:r=>Number(r.score||0).toFixed(3)}}
],report.timeline||[]);
const delay=byRole('delay');
const buckets=((report.delay_summary||{{}}).buckets)||[]; const maxCount=Math.max(1,...buckets.map(x=>Number(x.count||0)));
buckets.forEach(bucket=>{{ const row=document.createElement('div'); row.className='bar'; row.append(text('span',`${{bucket.lower_s}}..${{bucket.upper_s}}s`)); const meter=document.createElement('meter'); meter.min='0'; meter.max=String(maxCount); meter.value=String(bucket.count||0); row.append(meter,text('span',bucket.count||0)); delay.append(row); }});
const ratio=byRole('ratio');
const ratioInfo=report.lot_ratio||{{}}; ratio.append(text('p',`Median ratio: ${{ratioInfo.median ?? '—'}} | Drift factor: ${{ratioInfo.drift_factor ?? '—'}}`));
tableInto(ratio,[{{label:'A open',get:r=>r.a_open_time}},{{label:'A ID',get:r=>r.a_position_id}},{{label:'B ID',get:r=>r.b_position_id}},{{label:'Ratio',get:r=>r.ratio}}],ratioInfo.series||[]);
tableInto(byRole('symbols'),[
  {{label:'Symbol',get:r=>r.symbol}},{{label:'Matched',get:r=>r.matched_count}},{{label:'Unmatched A',get:r=>r.unmatched_a}},{{label:'Unmatched B',get:r=>r.unmatched_b}},{{label:'Mean score',get:r=>r.mean_match_score ?? '—'}},{{label:'Median delay',get:r=>r.median_delay_s ?? '—'}}
],report.symbol_breakdown||[]);
tableInto(byRole('supporting'),[{{label:'A ID',get:r=>r.a_position_id}},{{label:'B ID',get:r=>r.b_position_id}},{{label:'Score',get:r=>Number(r.score||0).toFixed(3)}}],report.supporting_matches||[]);
const contra=byRole('contradictory');
tableInto(contra,[{{label:'A ID',get:r=>r.a_position_id}},{{label:'B ID',get:r=>r.b_position_id}},{{label:'Score',get:r=>Number(r.score||0).toFixed(3)}}],report.contradictory_matches||[]);
const list=document.createElement('ul'); (report.contradictory_evidence||[]).forEach(item=>list.append(text('li',JSON.stringify(item)))); contra.append(list);
const network=byRole('network'); const ns='http:'+'//www.w3.org/2000/svg'; const svg=document.createElementNS(ns,'svg'); svg.setAttribute('viewBox','0 0 800 180');
const line=document.createElementNS(ns,'line'); line.setAttribute('x1','180'); line.setAttribute('y1','90'); line.setAttribute('x2','620'); line.setAttribute('y2','90'); line.setAttribute('stroke','currentColor'); svg.append(line);
[[180,accounts[0]||'A'],[620,accounts[1]||'B']].forEach(([x,name])=>{{ const c=document.createElementNS(ns,'circle'); c.setAttribute('cx',String(x)); c.setAttribute('cy','90'); c.setAttribute('r','12'); c.setAttribute('fill','currentColor'); const t=document.createElementNS(ns,'text'); t.setAttribute('x',String(Number(x)+18)); t.setAttribute('y','95'); t.setAttribute('fill','currentColor'); t.textContent=String(name); svg.append(c,t); }});
const label=document.createElementNS(ns,'text'); label.setAttribute('x','330'); label.setAttribute('y','75'); label.setAttribute('fill','currentColor'); label.textContent=`confidence ${{Number(report.raw_confidence||0).toFixed(3)}}${{report.calibrated_confidence==null?'':` / calibrated ${{Number(report.calibrated_confidence).toFixed(3)}}`}}`; svg.append(label); network.append(svg);
</script>
</body>
</html>
'''


def write_forensic_dashboard(report: Mapping[str, object], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_forensic_dashboard(report), encoding="utf-8")
    return path
