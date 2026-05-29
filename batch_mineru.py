"""
分批跑 mineru，每批 N 篇。
mineru server 处理太多 PDF 后 RAM 堆积崩溃，分批可以让模型每批后退出释放。

已跑成功的会跳过（已有非空 markdown 的 PDF）。
"""
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd

LITERATURE = Path(r"D:\mg\collect\literature")
OUTPUT = Path(r"D:\mg\collect\mineru_out")
LOG_CSV = Path(r"D:\mg\collect\batch_log.csv")
TMP_BATCH_DIR = Path(r"D:\mg\collect\_mineru_batch_tmp")
BATCH_SIZE = 15


def find_md(paper_stem: str) -> Path | None:
    candidate = OUTPUT / paper_stem / "auto" / f"{paper_stem}.md"
    if candidate.exists() and candidate.stat().st_size > 500:
        return candidate
    paper_dir = OUTPUT / paper_stem
    if paper_dir.exists():
        mds = [m for m in paper_dir.rglob("*.md") if m.stat().st_size > 500]
        if mds:
            return mds[0]
    return None


def run_batch(batch_pdfs: list[Path], mineru_exe: str, env: dict) -> int:
    """把 batch_pdfs 拷贝到临时目录，跑 mineru，再清理。返回 mineru 退出码。"""
    if TMP_BATCH_DIR.exists():
        shutil.rmtree(TMP_BATCH_DIR)
    TMP_BATCH_DIR.mkdir(parents=True)

    for pdf in batch_pdfs:
        shutil.copy2(pdf, TMP_BATCH_DIR / pdf.name)

    cmd = [
        mineru_exe,
        "-p", str(TMP_BATCH_DIR),
        "-o", str(OUTPUT),
        "-b", "pipeline",
        "-l", "en",
    ]
    print(f"  执行: mineru -p {TMP_BATCH_DIR.name} -o mineru_out -b pipeline -l en")
    proc = subprocess.run(cmd, env=env)
    # 清理临时目录（不影响 OUTPUT 里的真实输出）
    if TMP_BATCH_DIR.exists():
        shutil.rmtree(TMP_BATCH_DIR, ignore_errors=True)
    return proc.returncode


def main():
    if not LITERATURE.exists():
        sys.exit(f"找不到目录: {LITERATURE}")
    pdfs = sorted(LITERATURE.glob("*.pdf"))
    print(f"literature 目录 PDF 数: {len(pdfs)}")

    OUTPUT.mkdir(parents=True, exist_ok=True)

    done = [pdf for pdf in pdfs if find_md(pdf.stem)]
    todo = [pdf for pdf in pdfs if pdf not in done]
    print(f"已成功: {len(done)} 篇，待跑: {len(todo)} 篇")

    if not todo:
        print("全部已跑过，直接验证。")
    else:
        mineru_exe = shutil.which("mineru")
        if not mineru_exe:
            sys.exit("找不到 mineru 命令")
        env = os.environ.copy()
        env["MINERU_MODEL_SOURCE"] = "local"
        env["NO_PROXY"] = "127.0.0.1,localhost,0.0.0.0"
        env["no_proxy"] = "127.0.0.1,localhost,0.0.0.0"

        total_batches = (len(todo) + BATCH_SIZE - 1) // BATCH_SIZE
        for i in range(0, len(todo), BATCH_SIZE):
            batch = todo[i:i + BATCH_SIZE]
            batch_no = i // BATCH_SIZE + 1
            print(f"\n=== Batch {batch_no}/{total_batches} ({len(batch)} 篇) ===")
            for p in batch:
                print(f"  - {p.name}")
            t0 = time.time()
            rc = run_batch(batch, mineru_exe, env)
            print(f"  Batch {batch_no} 耗时 {(time.time()-t0)/60:.1f} 分钟, 退出码 {rc}")

            # 每批完检查 batch 内成功率
            batch_ok = sum(1 for p in batch if find_md(p.stem))
            print(f"  Batch {batch_no} 成功: {batch_ok}/{len(batch)}")

    # 最终验证
    print("\n=== 最终验证 ===")
    rows = []
    for pdf in pdfs:
        md = find_md(pdf.stem)
        if md is None:
            rows.append({"pdf": pdf.name, "status": "missing_output", "md_path": "", "md_size_bytes": 0})
        else:
            rows.append({"pdf": pdf.name, "status": "ok", "md_path": str(md), "md_size_bytes": md.stat().st_size})

    df = pd.DataFrame(rows)
    df.to_csv(LOG_CSV, index=False, encoding="utf-8-sig")
    print(df["status"].value_counts().to_string())
    failed = df[df["status"] != "ok"]
    if len(failed):
        print(f"\n仍失败 {len(failed)} 篇:")
        for _, r in failed.iterrows():
            print(f"  {r['pdf']}")


if __name__ == "__main__":
    main()
