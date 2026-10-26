"""主流程命令入口；使用子进程，避免导入旧脚本时触发执行。"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# 命令: (实现文件, 参数说明, 是否需要模型 API)
COMMANDS = {
    "测试": ("测试.py", "[-v]", False),
    "材料": ("脚本/手工整理.py", "材料模板|材料导入|模板|导入 ...（详见使用说明）", False),
    "导入": ("脚本/导入已有.py", "原论文目录 论文编号 [--runs 名称列表]", False),
    "分档": ("脚本/派生SML史料池.py", "论文目录", False),
    "生成Q": ("脚本/Q条件生成.py", '论文目录 run号 "研究问题" S|M|L [角色] [--dry-run]', True),
    "生成A": ("脚本/A条件生成.py", '论文目录 run号 S|M|L "核心观点" [角色] [--dry-run]', True),
    "抽取": ("脚本/_论证树一次性抽取.py", "run目录名 论文目录", True),
    "绑定": ("脚本/source_binding.py", "run完整路径", False),
    "校验": ("脚本/校验.py", "run完整路径", False),
    "对齐": ("脚本/_整树LLM对齐.py", "--paper 论文编号 --runs run名称列表", True),
    "聚合": ("脚本/频次聚合.py", "run完整路径 [--human 参考run完整路径]", False),
    "批量": ("批量实验.py", "--paper 论文编号 [--runs run名称列表] [--skip-extract] [--skip-align]", True),
}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in {"-h", "--help", "列表"}:
        print("用法：python 实验.py [--preview] 命令 参数...\n")
        for name, (_, usage, api) in COMMANDS.items():
            print(f"  {name}: {usage}  [{'涉及 API' if api else '本地'}]")
        print("\n--preview 只显示命令，不启动子进程、不写实验数据。")
        print("相对路径统一以 V2.0 根目录为准。辅助工具见 脚本索引.md。")
        return 0
    preview = args[0] == "--preview"
    if preview:
        args.pop(0)
    if not args or args[0] not in COMMANDS:
        print("未知命令；运行 python 实验.py --help 查看列表。", file=sys.stderr)
        return 2
    name = args.pop(0)
    script, usage, _ = COMMANDS[name]
    if args in (["--help"], ["-h"]):
        print(f"python 实验.py {name} {usage}\n实现：{script}")
        return 0
    command = [sys.executable, "-X", "utf8", str(ROOT / script), *args]
    print(f"工作目录：{ROOT}\n命令：{subprocess.list2cmdline(command)}", flush=True)
    if preview:
        return 0
    return subprocess.run(command, cwd=ROOT).returncode


if __name__ == "__main__":
    raise SystemExit(main())
