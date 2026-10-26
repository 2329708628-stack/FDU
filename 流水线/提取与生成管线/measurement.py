"""ACI binary coverage; SCI combined claim-material and direct claim-claim edges."""
from collections import Counter,defaultdict
from 管线公共 import config
RELATED={'EQUIVALENT','H_ENTAILS_M','M_ENTAILS_H'}
def merged_into_parent(nodes):
    """返回应与其父合并计数的 C 节点：某父节点若只有 1 条直属 C 子主张，
    该 C 与父实为同一命题（父子近重复，见 A01 核验报告§四.1），
    只在父节点计一次，避免同一命题在 ACI 分母中被重复计权。"""
    kids=Counter(n.get('parent') for n in nodes if n['level']=='C')
    return {n['node_id'] for n in nodes if n['level']=='C' and kids.get(n.get('parent'),0)==1}
def aggregate(human,model,pairs,cfg=None):
    cfg=cfg or config();hs={n['node_id']:n for n in human};ms={n['node_id']:n for n in model}
    drop_h=merged_into_parent(human);drop_m=merged_into_parent(model)
    links=defaultdict(set);excluded=[]
    for p in pairs:
        h,m=hs.get(p['human']),ms.get(p['model'])
        if h is None or m is None:raise ValueError('未知对齐节点: '+str(p))
        eligible=h['level'] in {'B','C'} and m['level'] in {'B','C'} and (cfg['cross_level'] or h['level']==m['level'])
        if not eligible:excluded.append(p);continue
        if p['label'] in RELATED or (p['label']=='RELATED' and p.get('relation_present')==1):links[h['node_id']].add(m['node_id'])
    def metrics(level=None):
        h=[n for n in human if n['level'] in {'B','C'} and n['node_id'] not in drop_h and (level is None or n['level']==level)]
        m=[n for n in model if n['level'] in {'B','C'} and n['node_id'] not in drop_m and (level is None or n['level']==level)]
        covered=sum(bool(links[n['node_id']]) for n in h);mi=set().union(*links.values()) if links else set()
        aci=covered/len(h) if h else None;precision=sum(n['node_id'] in mi for n in m)/len(m) if m else None
        return dict(ACI=aci,n_human_nodes=len(h),n_model_nodes=len(m),covered_human_nodes=covered,
            human_coverage_binary=aci,human_coverage_weighted=aci,model_precision_binary=precision,model_precision_weighted=precision,
            merged_into_parent=sorted(drop_h|drop_m))
    def edges(nodes):
        ids={n['node_id'] for n in nodes if n['level'] in {'B','C'}}
        evidence={(n['node_id'],mid) for n in nodes if n['node_id'] in ids for mid in n.get('sources',[])}
        claims={(n['parent'],n['node_id']) for n in nodes if n['node_id'] in ids and n.get('parent') in ids}
        return evidence,claims
    he,hc=edges(human);me,mc=edges(model)
    pe=sorted((h,mid) for h,mid in he if any((m,mid) in me for m in links[h]))
    pc=sorted((a,b) for a,b in hc if any((x,y) in mc for x in links[a] for y in links[b]))
    total=len(he)+len(hc);preserved=len(pe)+len(pc)
    return dict(overall=metrics(),by_level={lv:metrics(lv) for lv in ('B','C')},
        SCI=preserved/total if total else None,human_structure_edges=total,preserved_structure_edges=preserved,
        evidence_edges=dict(total=len(he),preserved=len(pe),coverage=len(pe)/len(he) if he else None,matched=pe),
        claim_edges=dict(total=len(hc),preserved=len(pc),coverage=len(pc)/len(hc) if hc else None,matched=pc),
        excluded_pairs=excluded,metric_version=cfg['version'])
def frequency(human,model,data,cfg=None):
    cfg=cfg or config();rounds=[data['pairs']]+[r['pairs'] for r in data.get('extra_repeats',[])]
    if data.get('n_repeats')!=len(rounds):raise ValueError('声明轮数与实际轮数不一致')
    if len(rounds)!=cfg['rounds'] or data.get('complete') is not True:raise ValueError('预定轮数未完成，不输出正式主结果')
    if not 1<=cfg['robust_k']<=cfg['main_k']<=cfg['rounds']:raise ValueError('投票阈值不合法')
    votes=Counter()
    hs={n['node_id']:n for n in human};ms={n['node_id']:n for n in model}
    def eligible(h,m):
        hn,mn=hs.get(h),ms.get(m)
        return bool(hn and mn and hn['level'] in {'B','C'} and mn['level'] in {'B','C'}
            and (cfg['cross_level'] or hn['level']==mn['level']))
    for ps in rounds:
        aggregate(human,model,ps,cfg) # all node IDs checked, even filtered pairs
        votes.update({(p['human'],p['model']) for p in ps
            if p['label'] in RELATED and eligible(p['human'],p['model'])})
    def selected(k):return [dict(human=h,model=m,label='RELATED',relation_present=1,freq=n)
        for (h,m),n in sorted(votes.items()) if n>=k]
    # 每一档投票阈值 n 都保存自洽结果：指标 + 该档选出的边表
    edges_by_n={k:selected(k) for k in range(1,len(rounds)+1)}
    scan={str(k):dict(aggregate(human,model,edges_by_n[k],cfg),threshold=k,n_edges=len(edges_by_n[k]))
          for k in edges_by_n}
    return dict(n_rounds=len(rounds),main_threshold=cfg['main_k'],main=scan[str(cfg['main_k'])],
        robustness_threshold=cfg['robust_k'],robustness=scan[str(cfg['robust_k'])],threshold_scan=scan,
        edges_main=edges_by_n[cfg['main_k']],edges_robustness=edges_by_n[cfg['robust_k']],
        edges_scan={str(k):edges_by_n[k] for k in edges_by_n},settings=cfg,
        input_fingerprint=data.get('fingerprint'))
