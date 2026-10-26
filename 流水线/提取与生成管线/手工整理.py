"""Explicit CSV paragraph annotations; no heading or citation inference."""
import argparse,csv,json
from pathlib import Path

FIELDS=['id','type','heading_level','text','material_refs']
def read_json(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def load_materials(path):
    d=read_json(path)
    if 'encoding_table' in d: materials=d['encoding_table']['M_level']
    elif 'materials' in d: materials=d['materials']
    else:
        materials=[]
        for source in d['sources']:
            for m in source['passages']:
                materials.append(dict(id=m['original_id'],text=m.get('text',''),source_full=m.get('source_full','')))
    ids=[m['id'] for m in materials]
    if len(ids)!=len(set(ids)):raise ValueError('史料身份重复；请提供去重且经确认的材料名册 JSON。')
    if not ids:raise ValueError('史料名册为空')
    return materials

def import_csv(csv_path,materials_path,run):
    materials=load_materials(materials_path); valid={m['id'] for m in materials};paras=[]
    with Path(csv_path).open(encoding='utf-8-sig',newline='') as f:
        for row in csv.DictReader(f):
            if not any(row.values()):continue
            pid=row['id'].strip();typ=row['type'].strip();txt=row['text']
            if not pid or not txt.strip() or typ not in {'title','text'}:raise ValueError('段落编号/正文/类型错误: '+pid)
            level=row['heading_level'].strip()
            refs=[x.strip() for x in row['material_refs'].split(';') if x.strip()]
            if set(refs)-valid:raise ValueError('未知史料编号 '+str(set(refs)-valid))
            if typ=='title':
                if level not in {'main','0','1','2','3'}:raise ValueError('标题层级须为 main/0/1/2/3: '+pid)
                if refs:raise ValueError('标题不要挂引用；引用放入对应正文段: '+pid)
            elif level:raise ValueError('正文的 heading_level 应留空: '+pid)
            paras.append(dict(id=pid,type=typ,text=txt,material_refs=sorted(set(refs)),page='1',heading_level=int(level) if level.isdigit() else None))
    if len({x['id'] for x in paras})!=len(paras):raise ValueError('段落编号重复')
    if not paras or paras[0]['type']!='title' or paras[0]['heading_level'] is not None:raise ValueError('首行须为 main 论文主标题')
    if sum(x['type']=='title' and x['heading_level']==0 for x in paras)!=1:raise ValueError('请标注且仅标注一个结论标题（0）；可手工给结论段补标题行')
    from 公共库 import derive_skeleton
    sk=derive_skeleton(paras)
    if not sk['B']:raise ValueError('请标注章节标题')
    for b in sk['B']:
        if not b['id'].startswith('B') or not b['span'][0]:raise ValueError('标题层级跳级或空章节: '+b['title_label'])
    out=Path(run)/'00_原文'/'原文_clean.json';out.parent.mkdir(parents=True,exist_ok=True)
    if out.exists():raise FileExistsError('已存在，不覆盖：'+str(out))
    out.write_text(json.dumps(dict(paragraphs=paras,materials=materials,meta=dict(preparation='manual_csv_v1',input_csv=str(csv_path))),ensure_ascii=False,indent=2),encoding='utf-8')
    print(out)

MATERIAL_FIELDS=['original_id','title','dynasty','volume','source_full','text','context']
def materials_csv(input_file,output_file):
    with Path(input_file).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
    sources=[];seen=set()
    for i,row in enumerate(rows,1):
        mid=row['original_id'].strip()
        if not mid or mid in seen or not row['text'].strip() or not row['source_full'].strip():
            raise ValueError('史料编号、核心文本或出处为空，或编号重复：'+mid)
        seen.add(mid);sid=f'SRC_{i:03d}'
        sources.append(dict(source_id=sid,title=row['title'],dynasty=row['dynasty'],citation_count=1,
            passages=[dict(passage_id=sid+'_P01',**{k:row[k] for k in ('original_id','volume','source_full','text','context')})]))
    out=Path(output_file)
    if out.exists():raise FileExistsError('已有史料池，不覆盖')
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(dict(metadata=dict(version='manual-source-v1',provenance='人工整理，原典核实由整理者负责'),
        statistics=dict(total_sources=len(sources),total_passages=len(rows)),sources=sources),ensure_ascii=False,indent=2),encoding='utf-8')
    print(out)

def main():
    ap=argparse.ArgumentParser();sp=ap.add_subparsers(dest='cmd',required=True)
    a=sp.add_parser('模板');a.add_argument('output')
    a=sp.add_parser('材料模板');a.add_argument('output')
    a=sp.add_parser('材料导入');a.add_argument('csv');a.add_argument('output')
    a=sp.add_parser('导入');a.add_argument('csv');a.add_argument('materials');a.add_argument('run')
    a=ap.parse_args()
    if a.cmd=='模板':
        with Path(a.output).open('x',encoding='utf-8-sig',newline='') as f:
            w=csv.writer(f);w.writerow(FIELDS);w.writerows([['P1','title','main','论文标题',''],['P2','title','1','章节标题',''],['P3','text','','粘贴完整正文；引用编号用英文分号分隔','M1'],['P4','title','0','结论',''],['P5','text','','粘贴结论正文','']])
    elif a.cmd=='材料模板':
        with Path(a.output).open('x',encoding='utf-8-sig',newline='') as f:
            csv.writer(f).writerow(MATERIAL_FIELDS)
    elif a.cmd=='材料导入':materials_csv(a.csv,a.output)
    else:import_csv(a.csv,a.materials,a.run)
if __name__=='__main__':main()
