from pathlib import Path
from pypdf import PdfReader
import pandas as pd
import re

ROOT = Path(r"D:\mg\collect\441")
CSV_OUT = ROOT / "pdf_metadata.csv"
DRY_RUN = False  # 改成 False 才真正重命名

def sanitize(s: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', s.strip())
    s = re.sub(r'[^\x00-\x7F]', '_', s)  # 替换所有非 ASCII（含中文）
    s = re.sub(r'_+', '_', s).strip('_')  # 合并连续下划线
    return s[:50] if s else ""

def first_author(s: str) -> str:
    if not s:
        return ""
    return sanitize(s.split(",")[0].strip())

pdfs = sorted(ROOT.glob("*.pdf"))
print(f"共找到 {len(pdfs)} 个 PDF")

seen_names = {}
fallback_idx = 1
rows = []

for pdf in pdfs:
    try:
        reader = PdfReader(str(pdf))
        meta = reader.metadata or {}
    except Exception as e:
        print(f"[读取失败] {pdf.name}: {e}")
        meta = {}

    author = first_author(meta.get("/Author", ""))
    year   = sanitize(meta.get("/Copyright Year", ""))
    title  = sanitize(meta.get("/Title", ""))
    doi    = meta.get("/doi", meta.get("/DOI", ""))

    if author and year:
        base = f"{author}_{year}"
    elif author:
        base = author
    else:
        base = f"unknown_{fallback_idx:03d}"
        fallback_idx += 1

    count = seen_names.get(base, 0)
    seen_names[base] = count + 1
    new_name = f"{base}.pdf" if count == 0 else f"{base}_{count}.pdf"
    new_path = pdf.parent / new_name

    rows.append({
        "old_name": pdf.name,
        "new_name": new_name,
        "author": author,
        "year": year,
        "title": title,
        "doi": doi,
        "status": "skip(same)" if pdf.name == new_name else "rename"
    })

    if not DRY_RUN and pdf.name != new_name:
        pdf.rename(new_path)

df = pd.DataFrame(rows)
df.to_csv(CSV_OUT, index=False, encoding="utf-8-sig")
print(df[["old_name", "new_name", "status"]].to_string())
print(f"\n[{'DRY RUN' if DRY_RUN else '已执行'}] CSV 已保存到 {CSV_OUT}")
