"""
读 zotero_pdf_paths.csv，把真实存在的 PDF 按 {Author}{Year}.pdf 命名
复制到 D:\\mg\\collect\\literature\\，同时输出 literature_mapping.xlsx 对照表。

不修改 Zotero 任何文件，只读 + 复制。
"""
import re
import shutil
import sys
from pathlib import Path

import pandas as pd
from unidecode import unidecode

CSV_IN = Path(r"D:\mg\collect\zotero_pdf_paths.csv")
DEST_DIR = Path(r"D:\mg\collect\literature")
MAPPING_XLSX = Path(r"D:\mg\collect\literature_mapping.xlsx")


def extract_author(pdf_filename: str) -> tuple[str, str]:
    """
    从 PDF 文件名提第一作者。返回 (作者ASCII, status)。
    文件名规则:
      'Matsunaga 等 - 2005 - ...pdf'        -> ('Matsunaga', 'ok')
      'Bazylinski和Frankel - 2004 - ...pdf' -> ('Bazylinski', 'ok')
      'Lefèvre 等 - 2011 - ...pdf'           -> ('Lefevre', 'ok')
      'Smith - 2020 - ...pdf'               -> ('Smith', 'ok')
    解析失败返回 ('UNKNOWN', 'manual_check')
    """
    stem = Path(pdf_filename).stem
    # 取第一个 ' - ' 之前的部分作为作者块
    head = stem.split(" - ", 1)[0].strip()
    if not head:
        return "UNKNOWN", "manual_check"

    # 去掉中文连接词后的内容
    #   "Matsunaga 等" -> "Matsunaga"
    #   "Bazylinski和Frankel" -> "Bazylinski"
    head = re.split(r"等|和|与", head, maxsplit=1)[0].strip()
    # 去掉末尾英文 "et al." / 逗号
    head = re.sub(r"\s*,?\s*(et\s+al\.?|and\s+others)\s*$", "", head, flags=re.I).strip()
    head = head.rstrip(",")

    if not head:
        return "UNKNOWN", "manual_check"

    # ASCII 化 + 只保留字母数字
    ascii_name = unidecode(head)
    ascii_name = re.sub(r"[^A-Za-z0-9]", "", ascii_name)
    if not ascii_name:
        return "UNKNOWN", "manual_check"
    return ascii_name, "ok"


def extract_year(year_field, pdf_filename: str, doi: str) -> str:
    """三级 fallback 提 4 位年份: csv year -> 文件名 -> doi -> XXXX。"""
    for src in [year_field, pdf_filename, doi]:
        if pd.notna(src) and str(src).strip():
            m = re.search(r"(19|20)\d{2}", str(src))
            if m:
                return m.group()
    return "XXXX"


def build_new_name(author: str, year_str: str, used_names: set) -> str:
    """生成 {Author}{Year}.pdf，重名加 _v2/_v3。"""
    base = f"{author}{year_str}"
    name = f"{base}.pdf"
    v = 2
    while name.lower() in used_names:
        name = f"{base}_v{v}.pdf"
        v += 1
    used_names.add(name.lower())
    return name


def main():
    if not CSV_IN.exists():
        sys.exit(f"找不到 {CSV_IN}")

    df = pd.read_csv(CSV_IN, encoding="utf-8-sig")
    df = df[df["pdf_path"].fillna("").str.strip() != ""].copy()
    df = df.drop_duplicates(subset=["pdf_path"])
    df["exists"] = df["pdf_path"].apply(lambda p: Path(p).exists())
    df = df[df["exists"]].reset_index(drop=True)
    print(f"真实可用 PDF（去 ghost 路径前）: {len(df)} 篇")

    # 按 DOI 去重：同 DOI 保留文件最大的一份，其他标 dedup_by_doi
    df["pdf_size"] = df["pdf_path"].apply(lambda p: Path(p).stat().st_size)
    df["doi_norm"] = df["doi"].fillna("").str.strip().str.lower()
    keep_mask = pd.Series(True, index=df.index)
    for doi, grp in df[df["doi_norm"] != ""].groupby("doi_norm"):
        if len(grp) > 1:
            keeper = grp["pdf_size"].idxmax()
            for idx in grp.index:
                if idx != keeper:
                    keep_mask.loc[idx] = False
    dedup_count = (~keep_mask).sum()
    print(f"DOI 去重: 标 {dedup_count} 条为 dedup_by_doi（不复制）")

    DEST_DIR.mkdir(parents=True, exist_ok=True)

    used = set()
    rows = []
    for idx, r in df.iterrows():
        src = Path(r["pdf_path"])
        author, status = extract_author(src.name)
        year_str = extract_year(r["year"], src.name, r["doi"])

        if not keep_mask.loc[idx]:
            # 被去重的不复制，但记入 mapping
            rows.append({
                "new_name": "",
                "first_author": author,
                "year": year_str,
                "title": r["title"],
                "doi": r["doi"],
                "old_path": str(src),
                "status": "dedup_by_doi",
            })
            continue

        new_name = build_new_name(author, year_str, used)
        dst = DEST_DIR / new_name

        copy_status = status
        try:
            if dst.exists() and dst.stat().st_size == src.stat().st_size:
                copy_status = (status + "; already_exists") if status != "ok" else "already_exists"
            else:
                shutil.copy2(src, dst)
        except Exception as e:
            copy_status = f"copy_failed: {e}"

        rows.append({
            "new_name": new_name,
            "first_author": author,
            "year": year_str,
            "title": r["title"],
            "doi": r["doi"],
            "old_path": str(src),
            "status": copy_status,
        })

    out_df = pd.DataFrame(rows)
    out_df.to_excel(MAPPING_XLSX, index=False)

    print(f"\n复制完成:")
    print(f"  literature 目录: {DEST_DIR}")
    print(f"  对照表: {MAPPING_XLSX}")
    print(f"\n状态分布:")
    print(out_df["status"].value_counts().to_string())
    need_check = out_df[out_df["status"].str.contains("manual_check|copy_failed", na=False)]
    if len(need_check):
        print(f"\n需人工核查 {len(need_check)} 条，已标注在 status 列")


if __name__ == "__main__":
    main()
