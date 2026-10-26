"""Copy existing trees into a new measurement dataset, preserving source files."""
import argparse,shutil
from pathlib import Path
from 管线公共 import ROOT,read_json,atomic_json,tree_file
from source_binding import repair
from 校验 import validate

def main():
    ap=argparse.ArgumentParser();ap.add_argument('source_paper');ap.add_argument('paper');ap.add_argument('--runs',default='A_human_baseline,Q_run_2_S,A_run_2_S');a=ap.parse_args()
    source=Path(a.source_paper);target=ROOT/'实验数据'/a.paper
    if target.exists():raise FileExistsError('目标已存在，使用新论文目录名，避免覆盖')
    selected=[]
    for name in a.runs.split(','):
        run=source/'03_实验输出/Q_A_实验'/name.strip();f=tree_file(run)
        original=read_json(f);result=repair(read_json(f));errors=validate(result)
        if errors:raise ValueError(name+': '+'; '.join(errors))
        result['meta']['revision_provenance']=dict(source_file=str(f),purpose='已有生成文本的新测量；非重新生成论文')
        selected.append((run,original,result))
    target.mkdir(parents=True)
    if (source/'02_史料池').exists():
        dest=target/'02_史料池';dest.mkdir()
        for f in (source/'02_史料池').glob('*.json'):shutil.copy2(f,dest/f.name)
    for run,original,result in selected:
        dest=target/'03_实验输出/Q_A_实验'/run.name
        atomic_json(dest/'导入前树备份.json',original);atomic_json(dest/'run_论证树.json',result)
        if (run/'00_原文').exists():shutil.copytree(run/'00_原文',dest/'00_原文')
        for name in ('生成_论文.md','meta.json','meta_生成.json','A_H.txt'):
            if (run/name).exists():shutil.copy2(run/name,dest/name)
    print('导入完成；未复制旧对齐结果，原始目录未改动：'+str(target))
if __name__=='__main__':main()
