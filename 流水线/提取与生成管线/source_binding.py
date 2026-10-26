"""Keep evidence attached to its paragraph; propose nearby C owners without fabricating claims."""
import re

def repair(run):
    et=run['encoding_table']; paras=run['paragraphs']
    pi={p['id']:i for i,p in enumerate(paras)}
    valid={m['id'] for m in et['M_level']}
    cs=et['C_level']; bs=et['B_level']; aas=et['A_level']
    by_anchor={}
    for c in cs:
        c.pop('evidence_candidates',None)
        by_anchor.setdefault(c['anchor'],[]).append(c)
    audit=[]
    def section(pid):
        i=pi[pid]; candidates=[]
        for b in bs:
            span=b.get('span',[])
            if len(span)==2 and all(x in pi for x in span) and pi[span[0]]<=i<=pi[span[1]]:
                candidates.append(b)
        return max(candidates,key=lambda b:int(b.get('depth') or 2))['id'] if candidates else None
    # Retain earlier explicit C sources; store why any nearby assignment is only a proposal.
    for c in cs:
        direct=set(next((p.get('material_refs',[]) for p in paras if p['id']==c['anchor']),[])) & valid
        c['sources']=sorted(set(c.get('sources',[]))|direct)
        c['source_count']=len(c['sources'])
    for p in paras:
        refs=set(p.get('material_refs',[])) & valid
        if not refs:continue
        candidates=by_anchor.get(p['id'],[])
        if candidates:
            audit.append(dict(paragraph=p['id'],materials=sorted(refs),owners=[c['id'] for c in candidates],status='direct'))
            continue
        sec=section(p['id']); candidates=[c for c in cs if c.get('parent')==sec and c['anchor'] in pi]
        if candidates:
            c=min(candidates,key=lambda c:(abs(pi[c['anchor']]-pi[p['id']]),pi[c['anchor']]>pi[p['id']]))
            # A mechanical candidate does not establish semantic support. Separate from verified sources.
            c.setdefault('evidence_candidates',[]).append(dict(paragraph=p['id'],materials=sorted(refs),status='needs_semantic_review'))
            audit.append(dict(paragraph=p['id'],materials=sorted(refs),candidate_owner=c['id'],status='needs_semantic_review'))
        else:
            audit.append(dict(paragraph=p['id'],materials=sorted(refs),status='unassigned_preserved'))
    # A is the full supplied/reference material roster, not proof of actual use.
    for a in aas:
        a['sources']=sorted(valid);a['source_count']=len(valid)
    # Rebuild B evidence unions after C repair, keeping statistics consistent.
    def collect(nid, seen):
        if nid in seen: raise ValueError('Cycle in tree: '+nid)
        seen=seen|{nid}; result=set()
        for c in cs:
            if c.get('parent')==nid: result.update(c.get('sources',[]))
        for b in bs:
            if b.get('parent')==nid: result.update(collect(b['id'],seen))
        return result
    for b in bs:
        b['sources']=sorted(collect(b['id'],set())); b['source_count']=len(b['sources'])
    run['evidence_binding_audit']=audit
    st=run.setdefault('statistics',{})
    for label, nodes in [('A',aas),('B',bs),('C',cs)]:st['total_'+label+'_nodes']=len(nodes)
    st['total_unique_M']=len(valid)
    st['source_count_by_A']={a['id']:len(a['sources']) for a in aas}
    st['source_count_by_B']={b['id']:len(b['sources']) for b in bs}
    used=set(m for c in cs for m in c.get('sources',[]))
    st['M']={'total':len(valid),'used':len(used),'unused':sorted(valid-used)}
    st['C_nodes_without_sources']=sum(not c.get('sources') for c in cs)
    st['claims_total']=len(aas)+len(bs)
    st['claims_supported']=sum(n.get('supported') is True for n in aas+bs)
    st['claims_unsupported']=sum(n.get('supported') is False for n in aas+bs)
    run.setdefault('meta',{})['binding_revision']='A full roster; B descendant-C union; C direct refs plus reviewed sources'
    return run

if __name__=='__main__':
    import argparse
    from 管线公共 import read_json,atomic_json,tree_file
    from 校验 import validate
    ap=argparse.ArgumentParser();ap.add_argument('run');a=ap.parse_args()
    file=tree_file(a.run);original=read_json(file)
    backup=file.with_name(file.name+'.修订前备份.json')
    if not backup.exists():atomic_json(backup,original)
    result=repair(original)
    errors=validate(result)
    if errors:raise SystemExit('修复后仍需手工处理：'+'; '.join(errors))
    atomic_json(file,result);print('已更新A全量绑定和统计：'+str(file))
