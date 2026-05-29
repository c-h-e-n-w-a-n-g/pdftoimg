"""
阶段 1 orchestrator：zotero_pdf_paths.csv -> dataset_browser.html

顺序调用 4 个脚本，任何一步失败立刻停止。
跑完打开 dataset_browser.html 人工筛 TEM，导出 selected_tem.csv 后再跑 image_copy.py。

用法：
    python run_stage1.py                  # 从第 1 步跑到第 4 步
    python run_stage1.py --from-step 3    # 从第 3 步开始（mineru 已经跑完时常用）
    python run_stage1.py --from-step 2    # 跳过 rename_and_copy，从 mineru 开始
"""
import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
ZOTERO_CSV = ROOT / "zotero_pdf_paths.csv"

STEPS = [
    ("rename_and_copy.py",              "Zotero PDF 重命名 + 复制到 literature/"),
    ("batch_mineru.py",                 "MinerU 批量解析 PDF（慢，分批 15 篇）"),
    ("extract_species_and_figures.py",  "抽 figure + caption + 菌种 -> dataset_meta.csv"),
    ("generate_browser.py",             "生成 dataset_browser.html"),
]


def run_step(idx: int, script: str, desc: str) -> None:
    n = len(STEPS)
    print(f"\n{'='*60}")
    print(f"[{idx}/{n}] {script}")
    print(f"      {desc}")
    print(f"{'='*60}")
    t0 = time.time()
    proc = subprocess.run([sys.executable, str(ROOT / script)], cwd=ROOT)
    dt = time.time() - t0
    if proc.returncode != 0:
        print(f"\n[{idx}/{n}] {script} 失败（退出码 {proc.returncode}，耗时 {dt:.1f}s）")
        print("阶段 1 中止。修好上面的错误后，用 --from-step {idx} 续跑。".format(idx=idx))
        sys.exit(proc.returncode)
    print(f"\n[{idx}/{n}] {script} 完成（耗时 {dt:.1f}s）")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-step", type=int, default=1,
                    help="从第几步开始（1-4），默认 1")
    args = ap.parse_args()

    if not (1 <= args.from_step <= len(STEPS)):
        sys.exit(f"--from-step 必须在 1-{len(STEPS)} 之间")

    if args.from_step == 1 and not ZOTERO_CSV.exists():
        sys.exit(f"前置文件不存在：{ZOTERO_CSV}\n"
                 f"请先从 Zotero 导出 PDF 路径表，或用 --from-step 2 跳过这一步")

    total_t0 = time.time()
    for i, (script, desc) in enumerate(STEPS, start=1):
        if i < args.from_step:
            print(f"[{i}/{len(STEPS)}] 跳过 {script}")
            continue
        run_step(i, script, desc)

    print(f"\n{'='*60}")
    print(f"阶段 1 全部完成，总耗时 {time.time()-total_t0:.1f}s")
    print(f"下一步：浏览器打开 {ROOT/'dataset_browser.html'} 人工筛选")
    print(f"导出 selected_tem.csv 后，跑 image_copy.py 归档图片")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
