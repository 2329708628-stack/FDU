"""Validate graph identities, parents, evidence sets and complete A roster."""
import argparse
from 管线公共 import read_json,tree_file

def validate(run):
    et=run['encoding_table'];errors=[]
    groups={lv:et.get(lv+'_level',[]) for lv in ('A','B','C','M')}
    nodes=sum([groups[x] for x in ('A','B','C')],[]);ids=[n['id'] for n in nodes]
    roster=[m['id'] for m in groups['M']];valid=set(roster);byid={n['id']:n for n in nodes}
    if len(ids)!=len(set(ids)):errors.append('论点编号重复')
    if len(roster)!=len(valid):errors.append('史料编号重复')
    if not valid:errors.append('缺少史料名册')
    if len(groups['A'])!=1:errors.append('须有且仅有一个全文 A 节点')
    for lv in ('A','B','C'):
        for n in groups[lv]:
            nid=n['id'];src=n.get('sources',[])
            if not (n.get('text') if lv=='C' else n.get('claim')):errors.append(nid+'缺少论点文本')
            if len(src)!=len(set(src)):errors.append(nid+'史料重复')
            if set(src)-valid:errors.append(nid+'含未知史料')
            if lv=='A' and set(src)!=valid:errors.append(nid+'必须绑定完整史料名册')
            if n.get('source_count',len(src))!=len(src):errors.append(nid+' source_count不一致')
            parent=n.get('parent')
            if parent is not None and parent not in byid:errors.append(nid+'父节点不存在')
            seen={nid}
            while parent in byid:
                if parent in seen:errors.append(nid+'出现父链环');break
                seen.add(parent);parent=byid[parent].get('parent')
    def descendants(nid):
        todo=[nid];seen=set();found=set()
        while todo:
            x=todo.pop()
            if x in seen:continue
            seen.add(x)
            for c in groups['C']:
                if c.get('parent')==x:found.update(c.get('sources',[]))
            todo.extend(b['id'] for b in groups['B'] if b.get('parent')==x)
        return found
    for b in groups['B']:
        if set(b.get('sources',[]))!=descendants(b['id']):errors.append(b['id']+'史料与子树 C 并集不一致')
    paras=run.get('paragraphs',[]);pids={p['id'] for p in paras}
    for p in paras:
        if set(p.get('material_refs',[]))-valid:errors.append(p['id']+'含未知引用')
    for c in groups['C']:
        if c.get('anchor') not in pids:errors.append(c['id']+'锚点段落不存在')
    st=run.get('statistics',{})
    for lv in ('A','B'):
        actual={n['id']:len(set(n.get('sources',[]))) for n in groups[lv]}
        if st.get('source_count_by_'+lv)!=actual:errors.append('statistics.source_count_by_'+lv+'不一致')
    return errors

def main():
    ap=argparse.ArgumentParser();ap.add_argument('run');args=ap.parse_args();errors=validate(read_json(tree_file(args.run)))
    if errors:raise SystemExit('\n'.join(errors))
    print('校验通过')
if __name__=='__main__':main()
