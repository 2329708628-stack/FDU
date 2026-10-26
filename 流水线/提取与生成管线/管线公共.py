import hashlib,json,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def read_json(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def atomic_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as f:
            json.dump(obj,f,ensure_ascii=False,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):os.unlink(name)
def config():return read_json(Path(__file__).resolve().parent/'实验设置.json')
def tree_file(run):
    path=Path(run)/'run_论证树.json'
    return path if path.exists() else Path(run)/'run.json'
def locked_inputs(human,model,settings):
    h=tree_file(human);m=tree_file(model)
    obj={'human':read_json(h),'model':read_json(m),'settings':settings}
    return dict(fingerprint=digest(obj),human_file=h.name,model_file=m.name,settings=settings)
