import copy,importlib,json,sys,tempfile,unittest,csv
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parent;sys.path.insert(0,str(ROOT/'脚本'))
# 测试临时文件固定在项目内，避免受宿主系统临时目录权限影响。
(ROOT/'测试临时').mkdir(exist_ok=True)
tempfile.tempdir=str(ROOT/'测试临时')
import measurement as met
import _整树LLM对齐 as align
from 管线公共 import atomic_json,read_json,config
from source_binding import repair
from 校验 import validate
manual=importlib.import_module('手工整理')

def tree():
    return repair(dict(meta={},statistics={},paragraphs=[dict(id='P1',type='text',text='测试段落',material_refs=['M1'])],encoding_table={
        'A_level':[dict(id='A1',claim='测试总论点',sources=[],parent=None)],
        'B_level':[dict(id='B1',claim='测试章节论点',sources=[],parent='A1',span=['P1','P1'],depth=2)],
        'C_level':[dict(id='C1',text='测试段落论点',sources=['M1'],parent='B1',anchor='P1')],
        'M_level':[dict(id='M1',text='测试材料',source_full='测试出处')]}))
def nodes():return [dict(node_id='A1',level='A',sources=['M1'],parent=None),dict(node_id='B1',level='B',sources=['M1'],parent='A1'),dict(node_id='C1',level='C',sources=['M1'],parent='B1')]
def pair(h='C1',m='C1',label='EQUIVALENT'):return dict(human=h,model=m,label=label)
class Checks(unittest.TestCase):
    def test_cli_preview_and_argument_forwarding(self):
        cli=importlib.import_module('实验')
        with patch.object(cli.subprocess,'run') as call:
            self.assertEqual(cli.main(['--preview','生成Q','实验数据/P01','1','甲 与 乙','S']),0)
            call.assert_not_called()
            call.return_value.returncode=7
            self.assertEqual(cli.main(['校验','含 空格/run']),7)
            self.assertEqual(call.call_args.args[0][-1],'含 空格/run')
            self.assertEqual(call.call_args.kwargs['cwd'],ROOT)
    def test_cli_targets_and_migrated_files_exist(self):
        cli=importlib.import_module('实验')
        for script,_,_ in cli.COMMANDS.values():
            self.assertTrue((ROOT/script).is_file(),script)
        for old,new in read_json(ROOT/'整理备份/迁移清单.json').items():
            self.assertFalse((ROOT/old).exists(),old)
            self.assertTrue((ROOT/new).is_file(),new)
    def test_single_child_current_counting_rule(self):
        r=met.aggregate(nodes(),nodes(),[pair('B1','B1'),pair()])
        self.assertEqual(r['overall']['n_human_nodes'],1)
        self.assertEqual(r['overall']['ACI'],1)
        self.assertEqual(r['human_structure_edges'],3)
    def test_combined(self):
        r=met.aggregate(nodes(),nodes(),[pair('B1','B1'),pair()]);self.assertEqual(r['SCI'],1);self.assertEqual(r['human_structure_edges'],3)
        r=met.aggregate(nodes(),nodes(),[pair()]);self.assertAlmostEqual(r['SCI'],1/3)
    def test_a_does_not_score(self):
        r=met.aggregate(nodes(),nodes(),[pair('A1','A1'),pair('C1','A1')]);self.assertEqual(r['SCI'],0);self.assertEqual(r['overall']['ACI'],0)
    def test_direct_edges(self):
        m=nodes();m.append(dict(node_id='B2',level='B',parent='B1',sources=[]));m[2]['parent']='B2'
        r=met.aggregate(nodes(),m,[pair('B1','B1'),pair()]);self.assertEqual(r['claim_edges']['preserved'],0)
    def test_cross_and_identity(self):
        # 单直属 C 当前从 ACI 分母合并；用两个 C 单独检验跨层匹配。
        n=nodes()+[dict(node_id='C2',level='C',parent='B1',sources=[])]
        r=met.aggregate(n,n,[pair('B1','C1')]);self.assertAlmostEqual(r['overall']['ACI'],1/3)
        m=nodes();m[2]['sources']=['M1-b'];r=met.aggregate(nodes(),m,[pair()]);self.assertEqual(r['evidence_edges']['preserved'],0)
    def test_no_15_cutoff(self):
        n=nodes();n[2]['sources']=['M'+str(i) for i in range(20)];r=met.aggregate(n,n,[pair('B1','B1'),pair()]);self.assertEqual(r['SCI'],1)
    def test_votes_and_short_round_rejected(self):
        ps=[pair(label='H_ENTAILS_M')]*3+[pair(label='UNCERTAIN')]
        d=dict(pairs=ps,extra_repeats=[dict(pairs=[pair(label='M_ENTAILS_H')]) for _ in range(5)],n_repeats=6,complete=True)
        cfg=dict(config(),rounds=6,main_k=6,robust_k=4)
        r=met.frequency(nodes(),nodes(),d,cfg);self.assertEqual(r['edges_main'][0]['freq'],6)
        d['extra_repeats']=[];d['n_repeats']=1
        with self.assertRaises(ValueError):met.frequency(nodes(),nodes(),d,cfg)
    def test_negative_and_unknown(self):
        self.assertEqual(met.aggregate(nodes(),nodes(),[pair(label='CONTRADICTION')])['SCI'],0)
        with self.assertRaises(ValueError):met.aggregate(nodes(),nodes(),[pair('MISSING')])
    def test_bindings(self):
        t=tree();self.assertEqual(validate(t),[]);self.assertEqual(t['encoding_table']['A_level'][0]['sources'],['M1']);self.assertEqual(t['statistics']['source_count_by_B'],{'B1':1})
        self.assertEqual(repair(copy.deepcopy(t)),t)
    def test_manual_keeps_multiline(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);atomic_json(d/'m.json',dict(materials=tree()['encoding_table']['M_level']))
            with (d/'p.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f);w.writerow(manual.FIELDS);w.writerows([['P1','title','main','题目',''],['P2','title','1','任意章节名',''],['P3','text','','第一行\n第二行','M1'],['P4','title','0','收尾',''],['P5','text','','结语正文','']])
            manual.import_csv(d/'p.csv',d/'m.json',d/'run')
            r=read_json(d/'run/00_原文/原文_clean.json');self.assertEqual(r['paragraphs'][2]['text'],'第一行\n第二行')
            from 公共库 import derive_skeleton
            sk=derive_skeleton(r['paragraphs']);self.assertEqual(len(sk['B']),1);self.assertEqual(len(sk['A']),1)
    def test_checkpoint_resume_input_lock(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);base=root/'P/03_实验输出/Q_A_实验';h=base/'A_human_baseline';m=base/'Q_run_1_S'
            atomic_json(h/'run.json',tree());atomic_json(m/'run.json',tree())
            good=([pair('B1','B1'),pair()],dict(seed=1,swapped=False,maps={},raw='mock offline'))
            with patch.object(align,'PAPER_ROOT',root),patch.object(align,'symmetric_call',side_effect=[good,RuntimeError('断线')]) as call:
                with self.assertRaises(RuntimeError):align.run_one('P','Q_run_1_S','测试',6)
                self.assertEqual(len(list((m/'对齐轮次').glob('*.json'))),1)
            with patch.object(align,'PAPER_ROOT',root),patch.object(align,'symmetric_call',return_value=good) as call:
                align.run_one('P','Q_run_1_S','测试',6);self.assertEqual(call.call_count,5)
                align.run_one('P','Q_run_1_S','测试',6);self.assertEqual(call.call_count,5)
                d=read_json(m/'整树_LLM对齐.json');self.assertTrue(d['complete']);self.assertEqual(met.frequency(align.load_tree(h),align.load_tree(m),d,dict(config(),rounds=6,main_k=6,robust_k=4))['main']['SCI'],1)
                t=read_json(m/'run.json');t['encoding_table']['C_level'][0]['text']='修改';atomic_json(m/'run.json',t)
                with self.assertRaises(ValueError):align.run_one('P','Q_run_1_S','测试',6)
    def test_material_table_and_extraction(self):
        extractor=importlib.import_module('_论证树一次性抽取')
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);paper=root/'P01';run=paper/'03_实验输出/Q_A_实验/Q_run_1_S'
            with (root/'m.csv').open('w',encoding='utf-8-sig',newline='') as f:
                w=csv.writer(f);w.writerow(manual.MATERIAL_FIELDS);w.writerow(['M1','测试书','','','测试出处','测试材料','测试材料前后文'])
            pool=paper/'02_史料池/source_pool.json';manual.materials_csv(root/'m.csv',pool)
            paras=[dict(id='P1',type='title',heading_level=None,text='论文题目',material_refs=[]),dict(id='P2',type='title',heading_level=1,text='任意章节',material_refs=[]),dict(id='P3',type='text',heading_level=None,text='测试正文',material_refs=['M1']),dict(id='P4',type='title',heading_level=0,text='结论',material_refs=[]),dict(id='P5',type='text',heading_level=None,text='测试结论',material_refs=[])]
            atomic_json(run/'00_原文/原文_clean.json',dict(paragraphs=paras,materials=manual.load_materials(pool)))
            response=json.dumps(dict(A_claim='测试全文核心判断',B_claims=[dict(id='B1',claim='测试章节核心判断')],C_claims=[dict(anchor='P3',text='测试段落核心判断')]))
            with patch.object(sys,'argv',['extract','Q_run_1_S',str(paper)]),patch.object(extractor,'chat',return_value=(response,None,{})) as call:
                extractor.main();self.assertEqual(call.call_count,1)
            result=read_json(run/'run_论证树.json');self.assertEqual(validate(result),[]);self.assertEqual(result['encoding_table']['A_level'][0]['sources'],['M1'])
    def test_bad_source_is_not_silently_dropped(self):
        t=tree();t['encoding_table']['C_level'][0]['sources']=['M_BAD'];self.assertTrue(validate(t))
if __name__=='__main__':unittest.main()
