#!/usr/bin/env python3
"""A04 批量生成 30 篇模型论文（6 条件 × 5 轮），按 run 的档位字母读对应史料池。

2026-10-24 修正：三档取自史料总库.xlsx，同一批 20 条引文，S=引文 / M=200 字上下文 / L=400 字上下文。
QS/AS → S 档，QM/AM → M 档，QL/AL → L 档。

用法：
  python3 生成A04.py                 # 跳过已合格 run
  python3 生成A04.py --only QS_R1,AS_R3
  python3 生成A04.py --force         # 忽略已有产物，全部重生成
参数：deepseek-chat, temperature=0.7, max_tokens=32768，流式输出。
"""
import json
import os
import sys
import time
from pathlib import Path

import urllib.request

ROOT = Path(__file__).resolve().parent.parent
A04 = ROOT / 'A04_实验记录'
GEN = A04 / '生成轮次'
POC = A04 / '史料池输入'

Q_TEXT = ('唐宋时期瓷窑官（"官监"／监窑官）是何时、如何产生的？其在宋代的身份级别、'
          '差遣权力、隶属关系与职责事务如何演变？瓷窑官制度与宋代制瓷业的发展之间是什么关系？')
A_TEXT = ('宋代瓷窑官承袭中晚唐五代藩镇旧制而经中央化改造，其身份级别、差遣权力、'
          '隶属关系与职责随瓷业发展而演变，既推动制瓷业繁荣，又在南宋晚期制度废弛中阻碍瓷业发展。')

SYS = '''你是一位研究宋史/制度史与陶瓷史的学者。你将收到一份编号史料池和一项写作任务，请仅依据该史料池撰写一篇结构完整的学术论文。

规则：
1. 论证所依据的史料必须来自史料池；凡引述史料，必须在句末以 [A04-Mxx] 格式标注其编号，引文文字须取自史料池所给文本，不得改写。
2. 允许一般性学术背景表述（如研究史、常识性制度说明），但不得引入史料池之外的具体史料引文或数据。
3. 正文需分节论述，使用中文数字节标题；章节结构与展开顺序自行安排，不作规定。
4. 正文规模与一篇规范期刊论文相当（正文不少于3000汉字）。
5. 以一段以"综合史料池"开头的总括段落结束全文，给出你的最终论点。'''

API_KEY = os.environ.get('DEEPSEEK_API_KEY')
BASE = os.environ.get('DEEPSEEK_BASE_URL', 'https://api.deepseek.com/v1')

CONDS = [f'{c}{t}_R{i}' for c in 'QA' for t in 'SML' for i in range(1, 6)]


def load_pool(tier):
    f = POC / f'pool_text_{tier}.txt'
    if not f.exists():
        raise SystemExit(f'缺少 {f}；先跑 建档三档.py --id A04')
    text = f.read_text(encoding='utf-8').strip()
    return text, text.count('[A04-M')


def build_prompt(run, pool, n_pool):
    cond_text = Q_TEXT if run.startswith('Q') else A_TEXT
    return f'''写作任务：{cond_text}

史料池（共{n_pool}条，编号为条目唯一标识）：
{pool}

请依据以上史料池完成任务。'''


def generate(prompt):
    body = json.dumps({
        'model': 'deepseek-chat', 'temperature': 0.7, 'max_tokens': 32768,
        'stream': True,
        'messages': [{'role': 'system', 'content': SYS}, {'role': 'user', 'content': prompt}],
    }).encode('utf-8')
    req = urllib.request.Request(
        f'{BASE}/chat/completions', data=body,
        headers={'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'})
    t0 = time.time()
    ttft = None
    chunks, finish, usage = [], None, {}
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode('utf-8', 'ignore').strip()
            if not line.startswith('data:'):
                continue
            payload = line[5:].strip()
            if payload == '[DONE]':
                break
            d = json.loads(payload)
            if d.get('usage'):
                usage = d['usage']
            for ch in d.get('choices', []):
                delta = ch.get('delta', {}).get('content')
                if delta:
                    if ttft is None:
                        ttft = time.time() - t0
                    chunks.append(delta)
                if ch.get('finish_reason'):
                    finish = ch['finish_reason']
    return ''.join(chunks), finish, time.time() - t0, ttft, usage


def main():
    only = None
    force = '--force' in sys.argv
    if '--only' in sys.argv:
        only = set(sys.argv[sys.argv.index('--only') + 1].split(','))
    if not API_KEY:
        raise SystemExit('缺 DEEPSEEK_API_KEY；请先 source 提取与生成管线/deepseek_env.sh')

    pools = {t: load_pool(t) for t in 'SML'}
    for t in 'SML':
        print(f'{t} 档史料池 {pools[t][1]} 条')

    for run in CONDS:
        if only and run not in only:
            continue
        cond, tier = run[0], run[1]
        pool, n_pool = pools[tier]
        prompt = build_prompt(run, pool, n_pool)
        rd = GEN / run
        rd.mkdir(parents=True, exist_ok=True)
        meta_f = rd / 'meta.json'
        if meta_f.exists() and not force:
            m = json.loads(meta_f.read_text(encoding='utf-8'))
            if m.get('finish_reason') == 'stop' and m.get('source_pool_entries') == n_pool:
                print(f'{run}: 已合格（{n_pool} 条），跳过')
                continue
        text = finish = elapsed = ttft = usage = None
        for attempt, wait in enumerate((0, 15, 45), 1):
            if wait:
                print(f'{run}: 第{attempt}次重试（等 {wait}s）...', flush=True)
                time.sleep(wait)
            try:
                text, finish, elapsed, ttft, usage = generate(prompt)
                break
            except Exception as e:
                print(f'{run}: 第{attempt}次失败: {e}', flush=True)
        if text is None:
            print(f'{run}: ❌ 3 次均失败，跳过')
            continue
        (rd / '论文_模型原始输出.md').write_text(text, encoding='utf-8')
        (rd / '提示词_实例.md').write_text(
            f'## 系统指令\n\n{SYS}\n\n## 用户消息\n\n{prompt}', encoding='utf-8')
        meta = {
            'experiment': 'A04', 'condition': cond, 'tier': tier,
            'run_no': int(run.split('_R')[1]), 'model': 'deepseek-chat',
            'temperature': 0.7, 'max_tokens': 32768,
            'role': '宋史/制度史与陶瓷史学者', 'prompt_chars': len(prompt),
            'source_pool_entries': n_pool, 'output_chars': len(text),
            'elapsed_sec': round(elapsed, 2),
            'time_to_first_token_sec': round(ttft, 2) if ttft else None,
            'finish_reason': finish, 'usage': usage,
            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S'),
        }
        meta_f.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding='utf-8')
        ok = '✅' if finish == 'stop' else f'⚠️ finish={finish}'
        print(f'{run}: {ok} {len(text)} 字符, {n_pool} 条, {elapsed:.1f}s', flush=True)
        time.sleep(4)


if __name__ == '__main__':
    main()
