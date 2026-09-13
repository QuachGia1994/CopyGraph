from __future__ import annotations

from pathlib import Path
from typing import Mapping

from .htmlutil import safe_json_for_html


def render_dashboard(report: Mapping[str, object]) -> str:
    data = safe_json_for_html(report)
    return f'''<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CopyGraph Dashboard</title>
<style>
:root {{ color-scheme: dark; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
body {{ margin:0; background:#111513; color:#e9f3ee; }}
main {{ max-width:1180px; margin:0 auto; padding:28px 20px 48px; }}
h1 {{ margin:0 0 8px; font-size:30px; }}
.sub {{ color:#9db0a6; margin:0 0 22px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:12px; }}
.card, section {{ background:#171d1a; border:1px solid #2a332e; border-radius:14px; }}
.card {{ padding:16px; }} .card strong {{ display:block; font-size:24px; margin-top:5px; }}
section {{ margin-top:16px; padding:18px; overflow:auto; }}
h2 {{ font-size:17px; margin:0 0 14px; }}
table {{ width:100%; border-collapse:collapse; min-width:720px; }}
th,td {{ text-align:left; padding:10px 8px; border-bottom:1px solid #29312d; }}
th {{ color:#9db0a6; font-size:12px; text-transform:uppercase; letter-spacing:.05em; }}
.badge {{ display:inline-block; padding:3px 8px; border-radius:999px; background:#24322b; }}
#network {{ width:100%; height:440px; display:block; }}
.node circle {{ fill:#dff6e8; stroke:#1d2b24; stroke-width:2; }}
.node text {{ fill:#dff6e8; font-size:12px; }}
.edge {{ stroke:#6b8376; stroke-width:2; opacity:.75; }}
ul {{ margin:0; padding-left:20px; }}
</style>
</head>
<body>
<main>
<h1>CopyGraph</h1>
<p class="sub">Local MT5 copy-trading similarity report</p>
<div id="summary" class="grid"></div>
<section><h2>Relationships</h2><div id="relationships"></div></section>
<section><h2>Clusters</h2><div id="clusters"></div></section>
<section><h2>Network</h2><svg id="network" viewBox="0 0 900 440" role="img" aria-label="Account similarity network"></svg></section>
</main>
<script id="copygraph-data" type="application/json">{data}</script>
<script>
const report = JSON.parse(document.getElementById('copygraph-data').textContent);
const summary = document.getElementById('summary');
function card(label, value) {{
  const el = document.createElement('div'); el.className='card';
  const small = document.createElement('span'); small.textContent=label;
  const strong = document.createElement('strong'); strong.textContent=String(value);
  el.append(small,strong); summary.appendChild(el);
}}
card('Accounts', (report.accounts||[]).length);
card('Pairs', (report.pairs||[]).length);
card('Graph edges', ((report.graph||{{}}).edges||[]).length);
card('Threshold', report.min_confidence ?? '—');
const rel = document.getElementById('relationships');
const table = document.createElement('table');
const head = document.createElement('thead');
const hr = document.createElement('tr');
['Accounts','Orientation','Confidence','Lead','Delay (s)','Matched'].forEach(text => {{ const th=document.createElement('th'); th.textContent=text; hr.appendChild(th); }});
head.appendChild(hr); table.appendChild(head);
const body = document.createElement('tbody');
(report.pairs||[]).forEach(pair => {{
  const tr=document.createElement('tr');
  const values=[(pair.accounts||[]).join(' ↔ '),pair.orientation,Number(pair.confidence||0).toFixed(3),pair.lead_account||'—',pair.median_delay_s ?? '—',((pair.totals||{{}}).matched ?? 0)];
  values.forEach(value => {{ const td=document.createElement('td'); td.textContent=String(value); tr.appendChild(td); }});
  body.appendChild(tr);
}});
table.appendChild(body); rel.appendChild(table);
const clusters = document.getElementById('clusters');
const list=document.createElement('ul');
(report.clusters||[]).forEach((cluster,index) => {{ const li=document.createElement('li'); li.textContent=`Cluster ${{index+1}}: ${{cluster.join(', ')}}`; list.appendChild(li); }});
clusters.appendChild(list);
const svg=document.getElementById('network');
const ns='http:'+'//www.w3.org/2000/svg';
const nodes=((report.graph||{{}}).nodes||[]);
const edges=((report.graph||{{}}).edges||[]);
const positions={{}}; const cx=450, cy=220, radius=Math.min(160,70+nodes.length*12);
nodes.forEach((name,index) => {{ const angle=(Math.PI*2*index/Math.max(1,nodes.length))-Math.PI/2; positions[name]=[cx+Math.cos(angle)*radius,cy+Math.sin(angle)*radius]; }});
edges.forEach(edge => {{
  const a=positions[edge.account_a], b=positions[edge.account_b]; if(!a||!b) return;
  const line=document.createElementNS(ns,'line'); line.setAttribute('x1',a[0]); line.setAttribute('y1',a[1]); line.setAttribute('x2',b[0]); line.setAttribute('y2',b[1]); line.setAttribute('class','edge'); svg.appendChild(line);
}});
nodes.forEach(name => {{
  const p=positions[name]; const g=document.createElementNS(ns,'g'); g.setAttribute('class','node');
  const c=document.createElementNS(ns,'circle'); c.setAttribute('cx',p[0]); c.setAttribute('cy',p[1]); c.setAttribute('r',8);
  const t=document.createElementNS(ns,'text'); t.setAttribute('x',p[0]+12); t.setAttribute('y',p[1]+4); t.textContent=name;
  g.append(c,t); svg.appendChild(g);
}});
</script>
</body>
</html>
'''


def write_dashboard(report: Mapping[str, object], output: str | Path) -> Path:
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_dashboard(report), encoding="utf-8")
    return path
