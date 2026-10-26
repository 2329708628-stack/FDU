import argparse
from pathlib import Path
from 管线公共 import read_json,atomic_json,config,locked_inputs,tree_file
from _整树LLM对齐 import load_tree
from measurement import frequency

def main():
    ap=argparse.ArgumentParser();ap.add_argument('run');ap.add_argument('--human',help='参考 run，默认同目录 A_human_baseline')
    ap.add_argument('--ks',help='要另存为独立结果的投票阈值 n（逗号分隔，如 6,4,3）；缺省只写全档汇总表');a=ap.parse_args()
    run=Path(a.run);human=Path(a.human) if a.human else run.parent/'A_human_baseline'
    d=read_json(run/'整树_LLM对齐.json');lock=read_json(run/'对齐输入锁.json')
    if d.get('settings',{}).get('protocol')!=config():raise ValueError('计分设置已经变更，不可混用结果')
    actual=locked_inputs(human,run,d['settings'])['fingerprint']
    if actual!=d.get('fingerprint') or actual!=lock['fingerprint']:raise ValueError('输入树已变更，请重新对齐')
    # Identity matching is exact; no stripping suffixes or borrowing another paper's mapping.
    def roster(path):return {m['id']:m for m in read_json(tree_file(path))['encoding_table']['M_level']}
    h,m=roster(human),roster(run)
    if set(h)!=set(m):raise ValueError('两侧史料名册不一致；请先手工确认统一 ID')
    for mid in h:
        if h[mid].get('source_full','')!=m[mid].get('source_full',''):
            raise ValueError('同编号出处不一致，需确认身份：'+mid)
    r=frequency(load_tree(human),load_tree(run),d)
    atomic_json(run/'频次聚合.json',r)
    scan=r['threshold_scan']
    # 按投票阈值 n 的汇总表：每档一行，便于直接取用不同 n 的结果
    rows=['n,ACI,SCI,model_precision,covered_human_nodes,n_human_nodes,n_edges']
    for k in sorted(scan,key=int):
        e=scan[k];o=e['overall']
        rows.append('%s,%s,%s,%s,%s,%s,%s'%(k,o['ACI'],e['SCI'],o['model_precision_binary'],
            o['covered_human_nodes'],o['n_human_nodes'],e['n_edges']))
    (run/'频次聚合_按门限.csv').write_text('\n'.join(rows)+'\n',encoding='utf-8')
    # --ks 指定的 n 值各写一份自洽结果（指标 + 该档边表）
    if a.ks:
        for k in [x.strip() for x in a.ks.split(',') if x.strip()]:
            if k not in scan:raise ValueError('n 超出 1..%d 范围：%s'%(r['n_rounds'],k))
            atomic_json(run/('频次聚合_n%s.json'%k),
                dict(threshold=int(k),metrics=scan[k],edges=r['edges_scan'][k],
                     settings=r['settings'],input_fingerprint=r['input_fingerprint']))
    print('n=%d ACI=%.3f SCI=%.3f | 全档 ACI: %s'%(r['main_threshold'],r['main']['overall']['ACI'],r['main']['SCI'],
        ' '.join('%s=%.3f'%(k,scan[k]['overall']['ACI']) for k in sorted(scan,key=int))))
if __name__=='__main__':main()
