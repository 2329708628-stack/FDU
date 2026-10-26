#!/usr/bin/env python3
"""生成 A04 最终汇总报告 HTML（史料总库三档版，2026-10-24）。

与旧版差别：
1. 三档 S/M/L 为同一批 20 条引文 × 不同上下文长度（S=引用片段 / M=史料原文_200字 /
   L=史料原文_400字，源=史料总库.xlsx，覆盖率≥0.7），档位效应是本报告的核心观察；
2. "门限敏感性"单独成节，并给出 A-7 前后对比；
3. 人类树节点口径统一：全部 A/B/C 节点减去无 sources 的 C 节点；
4. 十实验对比表由 NODES 字典驱动，预置 A01–A10，避免 sed 适配丢失历史实验。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AID = 'A04'
S = json.loads((ROOT / f'{AID}_实验记录' / f'对齐汇总_{AID}.json').read_text(encoding='utf-8'))
OUT_DIR = ROOT / f'{AID}_实验记录' / f'{AID}_最终汇总报告'
OUT_DIR.mkdir(parents=True, exist_ok=True)

CONDS = ['QS', 'QM', 'QL', 'AS', 'AM', 'AL']
TIERS = S.get('tiers', {})
TIER_NAME = {'S': '引文', 'M': '200字上下文', 'L': '400字上下文'}
COND_LABEL = {c: f'{c[0]}·{c[1]}（{TIER_NAME[c[1]]}）' for c in CONDS}
cm, br, ov = S['condition_means'], S['by_run'], S['overall']
sens, ht = S['sensitivity'], S['human_tree']

# 十实验节点数（人类树有效计分节点）：A03/A04 已于 2026-10-23 用真实三档重跑
NODES = {'A01': 21, 'A02': 6, 'A03': 21, 'A04': ht.get('total_scored', 0),
         'A05': 32, 'A06': 8, 'A07': 17, 'A08': 19, 'A09': 11, 'A10': 12}
assert len(NODES) == 10, 'NODES 字典丢失实验'


def f(x, nd=3):
    return f'{x:.{nd}f}' if isinstance(x, (int, float)) else '—'


def mean(vs):
    vs = [v for v in vs if v is not None]
    return sum(vs) / len(vs) if vs else None


# ---------- 档位趋势描述（由数据生成，不硬编码结论） ----------
q = [cm.get(f'Q{lv}', {}).get('ACI_n6') for lv in 'SML']
a = [cm.get(f'A{lv}', {}).get('ACI_n6') for lv in 'SML']
qS, qM, qL = q
aS, aM, aL = a


def trend(v):
    if any(x is None for x in v):
        return '数据不全'
    if v[0] > v[1] > v[2]:
        return '单调递减'
    if v[0] < v[1] < v[2]:
        return '单调递增'
    if v[1] < v[0] and v[1] < v[2]:
        return 'U 型（中档最低）'
    if v[1] > v[0] and v[1] > v[2]:
        return '倒 U 型（中档最高）'
    return '无单调趋势'


q_trend, a_trend = trend([qS, qM, qL]), trend([aS, aM, aL])

# ---------- 表格 ----------
run_rows = []
for run in sorted(br):
    v = br[run]
    run_rows.append(
        f'<tr><td>{run[0]}·{run[1]}</td><td>{run}</td>'
        f'<td>{f(v["ACI_n6"])}</td><td>{f(v.get("SCI_n6"))}</td>'
        f'<td>{f(v["ACI_n4"])}</td><td>{f(v.get("SCI_n4"))}</td>'
        f'<td>{f(v["ACI_n4"]-v["ACI_n6"])}</td>'
        f'<td>{f(v.get("ACI_a7_top2_n6"))}</td>'
        f'<td>{f(v.get("ACI_a7_top3_n6"))}</td>'
        f'<td>{f(v.get("ACI_a7_top4_n6"))}</td></tr>')

cond_rows = []
for c in CONDS:
    m = cm.get(c)
    if not m:
        continue
    cond_rows.append(
        f'<tr><td><b>{COND_LABEL[c]}</b></td><td>{m.get("count", 0)}</td>'
        f'<td>{f(m["ACI_n6"])}</td><td>{f(m["ACI_n4"])}</td>'
        f'<td>{f(m["ACI_n4"]-m["ACI_n6"])}</td>'
        f'<td>{f(m.get("ACI_a7_top2_n6"))}</td>'
        f'<td>{f(m.get("ACI_a7_top3_n6"))}</td>'
        f'<td>{f(m.get("ACI_a7_top4_n6"))}</td>'
        f'<td>{f(m.get("ACI_a7_top2_n4"))}</td></tr>')

chart_conds = [COND_LABEL[c] for c in CONDS if c in cm]
orig_n6 = [cm[c]['ACI_n6'] for c in CONDS if c in cm]
orig_n4 = [cm[c]['ACI_n4'] for c in CONDS if c in cm]
a7t2 = [cm[c].get('ACI_a7_top2_n6') for c in CONDS if c in cm]
a7t3 = [cm[c].get('ACI_a7_top3_n6') for c in CONDS if c in cm]
a7t4 = [cm[c].get('ACI_a7_top4_n6') for c in CONDS if c in cm]
scatter_orig = [[br[r]['ACI_n6'], br[r]['ACI_n4'], r] for r in sorted(br)]
scatter_a7 = [[br[r].get('ACI_a7_top2_n6'), br[r].get('ACI_a7_top2_n4'), r]
              for r in sorted(br) if br[r].get('ACI_a7_top2_n4') is not None]

q_a7_gain = (ov['Q'].get('ACI_a7_top2_n6') or 0) - (ov['Q']['ACI_n6'] or 0)
a_a7_gain = (ov['A'].get('ACI_a7_top2_n6') or 0) - (ov['A']['ACI_n6'] or 0)
qa_diff = (ov['Q']['ACI_n6'] or 0) - (ov['A']['ACI_n6'] or 0)

html = f'''<!DOCTYPE html><html><head><meta charset="utf-8">
<title>A04 最终汇总报告（真实三档版）</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5/dist/echarts.min.js"></script>
<style>
body{{font-family:-apple-system,Segoe UI,"PingFang SC",sans-serif;max-width:1000px;margin:0 auto;padding:28px 20px;color:#222}}
h1{{margin-top:0;font-size:28px}}
h2{{border-bottom:2px solid #7c2d12;padding-bottom:4px;margin-top:30px;font-size:20px}}
.card{{background:#fafbfc;border:1px solid #e5e7eb;border-radius:8px;padding:14px 18px;margin:10px 0}}
table{{width:100%;border-collapse:collapse;margin-top:6px;font-size:14px}}
th,td{{padding:6px 9px;border-bottom:1px solid #e5e7eb;text-align:center}}
th{{background:#f1f5f9;font-weight:600}}
tr:hover td{{background:#f8fafc}}
.chart{{width:100%;height:380px;margin:12px 0}}
.insight{{background:#fef7ed;border-left:4px solid #7c2d12;padding:10px 14px;border-radius:0 6px 6px 0;margin:8px 0;font-size:14px}}
.note{{color:#555;font-size:13px;margin-top:6px}}
.tier-q{{background:#dbeafe}}
.tier-a{{background:#fee2e2}}
footer{{margin-top:40px;padding-top:12px;border-top:1px solid #ddd;color:#777;font-size:12px}}
</style></head>
<body>

<h1>A04 最终汇总报告</h1>

<div class="card">
<b>主题</b>：{S['topic']}<br>
<b>人类参考树</b>：A={ht.get('A_nodes')} / B={ht.get('B_nodes')}（含嵌套 {', '.join(ht.get('nested_B', [])) or '无'}）/ C={ht.get('C_nodes')}（其中 {ht.get('C_zero_source')} 个无 sources）→ <b>有效计分节点 {ht.get('total_scored')}</b>｜<b>共享史料名册</b>：{ht.get('M_roster')} 条<br>
<b>实验设计</b>：2 条件（Q 中性提问 / A 给定观点）× 3 档史料池（<b>同一批 20 条引文，只扩展上下文长度：S={TIERS.get('S','?')}字 / M={TIERS.get('M','?')}字 / L={TIERS.get('L','?')}字</b>，源=史料总库.xlsx）× 5 轮 = 30 篇<br>
<b>管线</b>：抽取 → 绑定 → 校验 → 10 轮整树 LLM 对齐 → 频次聚合｜主阈值 n=6，稳健阈值 n=4<br>
<b>完成情况</b>：{len(S['complete_runs'])}/30 run 完整
</div>

<h2>一、条件级汇总</h2>
<div class="card">
<table>
<thead>
<tr><th rowspan="2">条件</th><th rowspan="2">n</th>
<th colspan="3">原始口径</th>
<th colspan="4">A-7 top-N 合并（n=6 除末列）</th></tr>
<tr><th>ACI(n=6)</th><th>ACI(n=4)</th><th>ΔACI</th>
<th>top-2</th><th>top-3</th><th>top-4</th><th>top-2 (n=4)</th></tr>
</thead>
<tbody>{''.join(cond_rows)}</tbody>
</table>
<p class="note">ΔACI = ACI(n=4) − ACI(n=6)。A-7 合并 = 同一人类节点的 top-N 模型候选票逐轮合并后再卡阈值（纯后处理，无 API 调用）。</p>
</div>

<h2>二、档位效应（同一批引文 × 不同上下文长度）</h2>
<div class="card">
<table>
<thead><tr><th>条件</th><th>S 档（引文 {TIERS.get('S','?')} 字）</th><th>M 档（200字上下文 {TIERS.get('M','?')} 字）</th><th>L 档（400字上下文 {TIERS.get('L','?')} 字）</th><th>走势</th></tr></thead>
<tbody>
<tr class="tier-q"><td><b>Q（中性提问）</b></td><td><b>{f(qS)}</b></td><td>{f(qM)}</td><td>{f(qL)}</td><td>{q_trend}</td></tr>
<tr class="tier-a"><td><b>A（给定观点）</b></td><td><b>{f(aS)}</b></td><td>{f(aM)}</td><td>{f(aL)}</td><td>{a_trend}</td></tr>
</tbody></table>
<div class="insight">
三档为<b>同一批 20 条引文</b>，只有给模型的上下文长度递增（S 引文 / M 含该引文的 200 字原文 / L 含该引文的 400 字原文，前 200 字即 M 档）。因此档间差异全部归因于上下文长度，不含史料数量效应。<br>
可与 A03（同一批 45 条引文，同一套 S/M/L 口径）对照上下文长度效应的方向是否一致。
</div>
</div>
<div id="chart-cond" class="chart"></div>

<h2>三、门限敏感性分析</h2>
<div class="card">
<p>判据：ΔACI = ACI(n=4) − ACI(n=6) &gt; 0.15。<br>
原始口径 <b>{sens['orig']['pct']}%（{sens['orig']['n_sensitive']}/{len(S['complete_runs'])}）</b>；
A-7 top-2 合并后 <b>{sens['a7_top2']['pct']}%（{sens['a7_top2']['n_sensitive']}/{len(S['complete_runs'])}）</b>。</p>
<div id="chart-scatter" class="chart"></div>
<p class="note">对角线 y=x 上方的点表示放宽阈值后得分上升，即该 run 的对位结果依赖投票阈值；A-7 合并后这些点应整体向对角线靠拢。</p>
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

<h2>五、结论</h2>
<div class="card">
<div class="insight"><b>1. Q 与 A 的总体差距 {f(qa_diff)}。</b>Q 总体 ACI(n=6)={f(ov['Q']['ACI_n6'])}，A 总体 {f(ov['A']['ACI_n6'])}。给定观点是否损害结构对位，取决于观点与人类论文 B 层结构的同构程度。</div>
<div class="insight"><b>2. 档位效应：Q {q_trend}、A {a_trend}。</b>Q 三档 S={f(qS)} / M={f(qM)} / L={f(qL)}；A 三档 S={f(aS)} / M={f(aM)} / L={f(aL)}。三档为同一批 20 条引文，只改上下文长度（S={TIERS.get('S','?')}字 / M={TIERS.get('M','?')}字 / L={TIERS.get('L','?')}字），档间差异可归因于上下文长度，而非史料数量。</div>
<div class="insight"><b>3. A-7 top-2 合并：Q {f(q_a7_gain)}、A {f(a_a7_gain)}。</b>提升幅度反映"票摊薄"程度——幅度越大，说明模型其实找对了节点，只是候选过于分散。</div>
<div class="insight"><b>4. 与 A03 对照。</b>A03（21 计分节点，同一批 45 条引文 × 上下文长度）与 A04（计分节点 {ht.get('total_scored')}，同一批 20 条引文）采用完全相同的三档口径，可对照上下文长度效应的方向与量级。</div>
</div>

<h2>六、十实验节点规模对照</h2>
<div class="card">
<table><thead><tr><th>实验</th><th>人类树计分节点</th><th>备注</th></tr></thead><tbody>
{''.join(f"<tr{' style=\'background:#fef7ed\'' if k == AID else ''}><td>{k}</td><td>{v}</td><td>{'本次重跑（真实三档）' if k in ('A03', AID) else '旧口径'}</td></tr>" for k, v in NODES.items())}
</tbody></table>
<p class="note">A04 计分节点口径：全部 A/B/C 节点减去无 sources 的 C 节点。旧报告曾出现 14 与 19 两个互相矛盾的数字（前者漏算嵌套 B，后者误把 A 层计入），本次统一。</p>
</div>

<script>
const c1 = echarts.init(document.getElementById('chart-cond'));
c1.setOption({{
  title: {{ text: 'A04 六条件 ACI(n=6)：原始 vs A-7 top-N', left: 'center' }},
  tooltip: {{ trigger: 'axis' }}, legend: {{ bottom: 0 }},
  grid: {{ left: 60, right: 30, top: 50, bottom: 60 }},
  xAxis: {{ type: 'category', data: {json.dumps(chart_conds)} }},
  yAxis: {{ type: 'value', min: 0, max: 1, name: 'ACI' }},
  series: [
    {{ name: '原始 n=6', type: 'bar', data: {json.dumps(orig_n6)}, itemStyle: {{ color: '#94a3b8' }} }},
    {{ name: 'A-7 top-2', type: 'bar', data: {json.dumps(a7t2)}, itemStyle: {{ color: '#b45309' }} }},
    {{ name: 'A-7 top-3', type: 'bar', data: {json.dumps(a7t3)}, itemStyle: {{ color: '#d97706' }} }},
    {{ name: 'A-7 top-4', type: 'bar', data: {json.dumps(a7t4)}, itemStyle: {{ color: '#f59e0b' }} }},
    {{ name: '原始 n=4（稳健）', type: 'bar', data: {json.dumps(orig_n4)}, itemStyle: {{ color: '#cbd5e1' }} }}
  ]
}});
const c2 = echarts.init(document.getElementById('chart-scatter'));
c2.setOption({{
  title: {{ text: 'ACI(n=6) vs ACI(n=4)：原始（灰）与 A-7 top-2（橙）', left: 'center' }},
  tooltip: {{ trigger: 'item', formatter: p => p.data[2] + '<br>n=6: ' + p.data[0].toFixed(3) + '<br>n=4: ' + p.data[1].toFixed(3) }},
  legend: {{ bottom: 0 }},
  grid: {{ left: 60, right: 30, top: 50, bottom: 60 }},
  xAxis: {{ type: 'value', min: 0, max: 1, name: 'ACI (n=6)' }},
  yAxis: {{ type: 'value', min: 0, max: 1, name: 'ACI (n=4)' }},
  series: [
    {{ name: '原始', type: 'scatter', data: {json.dumps(scatter_orig)}, itemStyle: {{ color: '#94a3b8' }}, symbolSize: 11 }},
    {{ name: 'A-7 top-2', type: 'scatter', data: {json.dumps(scatter_a7)}, itemStyle: {{ color: '#b45309' }}, symbolSize: 11 }},
    {{ name: 'y=x', type: 'line', data: [[0,0],[1,1]], lineStyle: {{ type: 'dashed', color: '#ccc' }}, symbol: 'none', silent: true }}
  ]
}});
</script>

<footer>生成时间 2026-10-24｜三档规则：同一批 20 条引文 × 不同上下文长度（S=引用片段 {TIERS.get('S','?')} 字 / M=史料原文_200字 {TIERS.get('M','?')} 字 / L=史料原文_400字 {TIERS.get('L','?')} 字），源=史料总库.xlsx，覆盖率≥0.7｜主阈值 n=6，稳健阈值 n=4，10 轮 LLM 对齐</footer>
</body></html>'''

out = OUT_DIR / f'{AID}_最终汇总报告.html'
out.write_text(html, encoding='utf-8')
print(f'已生成 {out}（{out.stat().st_size} bytes）')
