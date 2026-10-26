#!/usr/bin/env python3
"""生成 A03 最终汇总报告 HTML。2026-10-23 版：三档真实分档，重跑覆盖旧口径。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
S = json.loads((ROOT / 'A03_实验记录' / '对齐汇总_A03.json').read_text(encoding='utf-8'))
OUT_DIR = ROOT / 'A03_实验记录' / 'A03_最终汇总报告'
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONDS = ['QS', 'QM', 'QL', 'AS', 'AM', 'AL']
COND_LABEL = {'QS': 'Q·S（引文）', 'QM': 'Q·M（200字上下文）', 'QL': 'Q·L（400字上下文）',
              'AS': 'A·S（引文）', 'AM': 'A·M（200字上下文）', 'AL': 'A·L（400字上下文）'}
cm, br, ov = S['condition_means'], S['by_run'], S['overall']
sens = S['sensitivity']
tiers = S['tiers']


def f(x, nd=3):
    return f'{x:.{nd}f}' if isinstance(x, (int, float)) else '—'


# ---------- 逐 run 表 ----------
run_rows = []
for run in sorted(br):
    v = br[run]
    c = run[:2]
    cond_short = c[0] + '·' + c[1]
    run_rows.append(
        f'<tr><td>{cond_short}</td><td>{run}</td>'
        f'<td>{f(v["ACI_n6"])}</td><td>{f(v.get("SCI_n6"))}</td>'
        f'<td>{f(v["ACI_n4"])}</td><td>{f(v.get("SCI_n4"))}</td>'
        f'<td>{f(v["ACI_n4"]-v["ACI_n6"])}</td>'
        f'<td>{f(v.get("ACI_a7_top2_n6"))}</td>'
        f'<td>{f(v.get("ACI_a7_top3_n6"))}</td>'
        f'<td>{f(v.get("ACI_a7_top4_n6"))}</td></tr>')

# ---------- 条件级表 ----------
cond_rows = []
for c in CONDS:
    m = cm.get(c, {})
    if not m: continue
    cond_rows.append(
        f'<tr><td><b>{COND_LABEL[c]}</b></td><td>{m.get("count",0)}</td>'
        f'<td>{f(m["ACI_n6"])}</td><td>{f(m["ACI_n4"])}</td>'
        f'<td>{f(m["ACI_n4"]-m["ACI_n6"])}</td>'
        f'<td>{f(m.get("ACI_a7_top2_n6"))}</td>'
        f'<td>{f(m.get("ACI_a7_top3_n6"))}</td>'
        f'<td>{f(m.get("ACI_a7_top4_n6"))}</td>'
        f'<td>{f(m.get("ACI_a7_top2_n4"))}</td></tr>')

# ---------- 图表数据 ----------
chart_conds = [COND_LABEL[c] for c in CONDS]
orig_n6 = [cm[c]['ACI_n6'] for c in CONDS if c in cm]
orig_n4 = [cm[c]['ACI_n4'] for c in CONDS if c in cm]
a7t2_n6 = [cm[c].get('ACI_a7_top2_n6') for c in CONDS if c in cm]
a7t3_n6 = [cm[c].get('ACI_a7_top3_n6') for c in CONDS if c in cm]
a7t4_n6 = [cm[c].get('ACI_a7_top4_n6') for c in CONDS if c in cm]

scatter_orig = [[br[r]['ACI_n6'], br[r]['ACI_n4'], r] for r in sorted(br)]
scatter_a7 = [[br[r].get('ACI_a7_top2_n6'), br[r].get('ACI_a7_top2_n4'), r]
              for r in sorted(br) if br[r].get('ACI_a7_top2_n4') is not None]

te = S.get('tier_effect', {'Q': {}, 'A': {}})
def tv(group, key): return te.get(group, {}).get(key) or 0
qS, qM, qL = tv('Q','S'), tv('Q','M'), tv('Q','L')
aS, aM, aL = tv('A','S'), tv('A','M'), tv('A','L')
TC = tiers if isinstance(tiers, dict) else {}

def trend(s, m, l):
    if s < m < l: return '单调递增'
    if s > m > l: return '单调递减'
    if m < s and m < l: return 'V 型（中档最低）'
    if m > s and m > l: return '倒 U 型（中档最高）'
    return '无单调趋势'

q_trend, a_trend = trend(qS, qM, qL), trend(aS, aM, aL)

html = f'''<!DOCTYPE html><html><head><meta charset="utf-8">
<title>A03 最终汇总报告（史料总库三档版）</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
body{{font-family:-apple-system,Segoe UI,"PingFang SC",sans-serif;max-width:980px;margin:0 auto;padding:28px 20px;color:#222}}
h1{{margin-top:0;font-size:28px}}
h2{{border-bottom:2px solid #1e3a8a;padding-bottom:4px;margin-top:28px;font-size:20px}}
.card{{background:#fafbfc;border:1px solid #e5e7eb;border-radius:8px;padding:14px 18px;margin:10px 0}}
table{{width:100%;border-collapse:collapse;margin-top:6px;font-size:14px}}
th,td{{padding:6px 9px;border-bottom:1px solid #e5e7eb;text-align:center}}
th{{background:#f1f5f9;font-weight:600}}
tr:hover td{{background:#f8fafc}}
.chart{{width:100%;height:380px;margin:12px 0}}
.insight{{background:#eff6ff;border-left:4px solid #1e3a8a;padding:10px 14px;border-radius:0 6px 6px 0;margin:8px 0;font-size:14px}}
.note{{color:#555;font-size:13px;margin-top:6px}}
.tag-a7{{background:#2d7d46;color:#fff;padding:1px 6px;border-radius:3px;font-size:12px}}
.a7-badge{{color:#2d7d46;font-weight:600}}
.diag{{background:#fffbeb;border:1px solid #fcd34d;border-radius:8px;padding:14px 18px}}
code{{background:#f1f5f9;padding:1px 5px;border-radius:3px;font-size:12px}}
.tier-q{{background:#dbeafe}}
.tier-a{{background:#fee2e2}}
footer{{margin-top:40px;padding-top:12px;border-top:1px solid #ddd;color:#777;font-size:12px}}
</style></head>
<body>

<h1>A03 最终汇总报告</h1>

<div class="card">
<b>主题</b>：10—13 世纪苏州地区（吴江、嘉定两县）的水利开发与新县增设<br>
<b>人类参考树</b>：A=1 / B=9 / C=14（计分 21 节点）｜<b>共享史料名册</b>：80 条（三档入池 45 条）<br>
<b>实验设计</b>：2 条件（Q 中性提问 / A 给定观点）× 3 档史料池（<b>同一批 45 条引文，只扩展上下文长度：S={TC.get('S','?')}字 / M={TC.get('M','?')}字 / L={TC.get('L','?')}字</b>，源=史料总库.xlsx）× 5 轮 = 30 篇<br>
<b>管线</b>：抽取 → 绑定 → 校验 → 10 轮整树 LLM 对齐 → 频次聚合｜主阈值 n=6，稳健阈值 n=4<br>
<b>完成情况</b>：{len(S['complete_runs'])}/30 run 完整
</div>

<h2>一、条件级汇总（真实三档）</h2>
<div class="card">
<table>
<thead>
<tr><th rowspan="2">条件</th><th rowspan="2">n</th>
<th colspan="3">原始口径</th>
<th colspan="4">A-7 top-N（主口径）</th></tr>
<tr><th>ACI(n=6)</th><th>ACI(n=4)</th><th>ΔACI</th>
<th>top-2 (n=6)</th><th>top-3 (n=6)</th><th>top-4 (n=6)</th><th>top-2 (n=4)</th></tr>
</thead>
<tbody>{''.join(cond_rows)}</tbody>
</table>
<p class="note">ΔACI = ACI(n=4) − ACI(n=6)，衡量对投票阈值的敏感程度。A-7 合并 = 同一人类节点的 top-N 候选模型节点票逐轮合并后再卡阈值（后处理，无 API 调用），消除"票被摊薄"假阴性。</p>
</div>

<h2>二、档位效应（同一批引文 × 不同上下文长度）</h2>
<div class="card">
<table>
<thead><tr><th>条件</th><th>S 档（引文 {TC.get('S','?')} 字）</th><th>M 档（200字上下文 {TC.get('M','?')} 字）</th><th>L 档（400字上下文 {TC.get('L','?')} 字）</th><th>走势</th></tr></thead>
<tbody>
<tr class="tier-q"><td><b>Q（中性提问）</b></td><td><b>{f(cm['QS']['ACI_n6']) if 'QS' in cm else '—'}</b></td><td>{f(cm['QM']['ACI_n6']) if 'QM' in cm else '—'}</td><td>{f(cm['QL']['ACI_n6']) if 'QL' in cm else '—'}</td><td>{q_trend}</td></tr>
<tr class="tier-a"><td><b>A（给定观点）</b></td><td><b>{f(cm['AS']['ACI_n6']) if 'AS' in cm else '—'}</b></td><td>{f(cm['AM']['ACI_n6']) if 'AM' in cm else '—'}</td><td>{f(cm['AL']['ACI_n6']) if 'AL' in cm else '—'}</td><td>{a_trend}</td></tr>
</tbody></table>
<div class="insight">
<b>Q 条件：{q_trend}</b>（S={f(qS)} → M={f(qM)} → L={f(qL)}）。<br>
<b>A 条件：{a_trend}</b>（S={f(aS)} → M={f(aM)} → L={f(aL)}）。<br>
三档引文集合完全相同，只有给模型的上下文长度递增，因此档间差异全部归因于<b>上下文长度</b>，不含史料数量效应。
</div>
</div>
<div id="chart-cond" class="chart"></div>

<h2>三、门限敏感性分析</h2>
<div class="card">
<p>ΔACI = ACI(n=4) − ACI(n=6) &gt; 0.15 的 run 占比：<b>原始 {sens['orig']['pct']}%（{sens['orig']['n_sensitive']}/{len(S['complete_runs'])}）</b> → A-7 top-2 后 <b>{sens['a7_top2']['pct']}%（{sens['a7_top2']['n_sensitive']}/{len(S['complete_runs'])}）</b>。</p>
<div id="chart-scatter" class="chart"></div>
</div>

<h2>四、逐 Run 明细（{len(S['complete_runs'])} run）</h2>
<div class="card">
<table>
<thead>
<tr><th rowspan="2">条件</th><th rowspan="2">Run</th>
<th colspan="2">严格 n=6</th><th colspan="2">稳健 n=4</th><th rowspan="2">ΔACI</th>
<th colspan="3">A-7 合并 ACI (n=6)</th></tr>
<tr><th>ACI</th><th>SCI</th><th>ACI</th><th>SCI</th>
<th>top-2</th><th>top-3</th><th>top-4</th></tr>
</thead>
<tbody>{''.join(run_rows)}</tbody>
</table>
</div>

<h2>五、结论（史料总库三档版）</h2>
<div class="card">
<div class="insight"><b>1. Q vs A 总体。</b>Q 总体 ACI(n=6)={f(ov['Q']['ACI_n6'])} vs A 总体 {f(ov['A']['ACI_n6'])}（差 {f(ov['Q']['ACI_n6']-ov['A']['ACI_n6'])}）。</div>
<div class="insight"><b>2. 档位效应：Q {q_trend}、A {a_trend}。</b>Q 三档 S={f(qS)} / M={f(qM)} / L={f(qL)}；A 三档 S={f(aS)} / M={f(aM)} / L={f(aL)}。三档为同一批 45 条引文，只改上下文长度（S={TC.get('S','?')}字 / M={TC.get('M','?')}字 / L={TC.get('L','?')}字），档间差异可归因于上下文长度，而非史料数量或题材偏斜。</div>
<div class="insight"><b>3. A-7 修复力 {sens['orig']['pct']}% → {sens['a7_top2']['pct']}%。</b>ΔACI&gt;0.15 的 run 占比在 top-2 合并后下降，说明部分低分来自"票被摊薄"而非真实错配。</div>
<div class="insight"><b>4. 上下文长度不是单调增益。</b>三档走势为 Q {q_trend}、A {a_trend}，即"给更多上下文"既未稳定提升也未稳定降低 ACI，S/M/L 差异需结合逐 run 明细（第四节）判断是否超出采样波动。</div>
</div>

<script>
const chartCond = echarts.init(document.getElementById('chart-cond'));
chartCond.setOption({{
  title: {{ text: 'A03 六条件 ACI(n=6)：原始 vs A-7 top-N', left: 'center' }},
  tooltip: {{ trigger: 'axis' }}, legend: {{ bottom: 0 }},
  grid: {{ left: 60, right: 30, top: 50, bottom: 60 }},
  xAxis: {{ type: 'category', data: {json.dumps(chart_conds)} }},
  yAxis: {{ type: 'value', min: 0, max: 1, name: 'ACI' }},
  series: [
    {{ name: '原始 n=6', type: 'bar', data: {json.dumps(orig_n6)}, itemStyle: {{ color: '#94a3b8' }} }},
    {{ name: 'A-7 top-2', type: 'bar', data: {json.dumps(a7t2_n6)}, itemStyle: {{ color: '#2d7d46' }} }},
    {{ name: 'A-7 top-3', type: 'bar', data: {json.dumps(a7t3_n6)}, itemStyle: {{ color: '#65a30d' }} }},
    {{ name: 'A-7 top-4', type: 'bar', data: {json.dumps(a7t4_n6)}, itemStyle: {{ color: '#a3e635' }} }},
    {{ name: '原始 n=4（稳健）', type: 'bar', data: {json.dumps(orig_n4)}, itemStyle: {{ color: '#cbd5e1' }} }}
  ]
}});

const scatter = echarts.init(document.getElementById('chart-scatter'));
scatter.setOption({{
  title: {{ text: 'ACI(n=6) vs ACI(n=4) 逐 run：原始（灰）与 A-7 top-2（绿）', left: 'center' }},
  tooltip: {{ trigger: 'item', formatter: p => p.data[2] + '<br>n=6: ' + p.data[0].toFixed(3) + '<br>n=4: ' + p.data[1].toFixed(3) }},
  legend: {{ bottom: 0 }},
  grid: {{ left: 60, right: 30, top: 50, bottom: 60 }},
  xAxis: {{ type: 'value', min: 0, max: 1, name: 'ACI (n=6)' }},
  yAxis: {{ type: 'value', min: 0, max: 1, name: 'ACI (n=4)' }},
  series: [
    {{ name: '原始口径', type: 'scatter', data: {json.dumps(scatter_orig)}, itemStyle: {{ color: '#94a3b8' }}, symbolSize: 11 }},
    {{ name: 'A-7 top-2', type: 'scatter', data: {json.dumps(scatter_a7)}, itemStyle: {{ color: '#2d7d46' }}, symbolSize: 11 }},
    {{ name: 'y=x', type: 'line', data: [[0,0],[1,1]], lineStyle: {{ type: 'dashed', color: '#ccc' }}, symbol: 'none', silent: true }}
  ]
}});
</script>

<footer>生成时间 2026-10-24｜三档规则：同一批 45 条引文 × 不同上下文长度（S=引用片段 {TC.get('S','?')} 字 / M=史料原文_200字 {TC.get('M','?')} 字 / L=史料原文_400字 {TC.get('L','?')} 字），源=史料总库.xlsx，覆盖率≥0.7｜主阈值 n=6，稳健阈值 n=4，10 轮 LLM 对齐</footer>
</body></html>'''

out = OUT_DIR / 'A03_最终汇总报告.html'
out.write_text(html, encoding='utf-8')
print(f'已生成 {out}')
print(f'大小 {out.stat().st_size} bytes')
