"""
解析 mineru_out 下每篇的 markdown，提取：
  - 每张图（按 markdown 中 ![](images/xxx) 标记）
  - 关联的 figure caption（图片之后最近一个 "Figure N. ..." 段落）
  - caption 区域附近的菌种
  - 论文全文 top 菌种

输出 dataset_meta.csv：每张图一行
"""
import re
import sys
from pathlib import Path
from collections import Counter

import pandas as pd

MINERU_OUT = Path(r"D:\mg\collect\mineru_out")
MAPPING_XLSX = Path(r"D:\mg\collect\literature_mapping.xlsx")
OUT_CSV = Path(r"D:\mg\collect\441\pdf_metadata.csv")

# 菌种词表：(canonical_name, 正则模式列表)。
# 都按 IGNORECASE 匹配。strain code 用单词边界避免误伤
SPECIES = [
    ("Magnetospirillum gryphiswaldense (MSR-1)", [
        r"magnetospirillum\s+gryphiswaldense",
        r"\bMSR[\s\-]?1\b",
    ]),
    ("Magnetospirillum magneticum (AMB-1)", [
        r"magnetospirillum\s+magneticum",
        r"\bAMB[\s\-]?1\b",
    ]),
    ("Magnetospirillum magnetotacticum (MS-1)", [
        r"magnetospirillum\s+magnetotacticum",
        r"\bMS[\s\-]?1\b",
    ]),
    ("Magnetospirillum moscoviense", [r"magnetospirillum\s+moscoviense"]),
    ("Magnetospirillum caucaseum", [r"magnetospirillum\s+caucaseum"]),
    ("Magnetospirillum marisnigri", [r"magnetospirillum\s+marisnigri"]),
    ("Magnetospirillum sulfuroxidans", [r"magnetospirillum\s+sulfuroxidans"]),
    ("Magnetospirillum (other species)", [r"magnetospirillum\s+sp\."]),
    ("Aquaspirillum magnetotacticum (old name of MS-1)", [r"aquaspirillum\s+magnetotacticum"]),
    ("Desulfovibrio magneticus (RS-1)", [
        r"desulfovibrio\s+magneticus",
        r"\bRS[\s\-]?1\b",
    ]),
    ("Desulfamplus magnetovallimortis (BW-1)", [
        r"desulfamplus\s+magnetovallimortis",
        r"\bBW[\s\-]?1\b",
    ]),
    ("Magnetococcus marinus (MC-1)", [
        r"magnetococcus\s+marinus",
        r"\bMC[\s\-]?1\b",
    ]),
    ("Magnetovibrio blakemorei (MV-1)", [
        r"magnetovibrio\s+blakemorei",
        r"\bMV[\s\-]?[12]\b",
    ]),
    ("Candidatus Magnetobacterium bavaricum (MBav)", [
        r"(?:candidatus\s+)?magnetobacterium\s+bavaricum",
        r"\bMBav\b",
    ]),
    ("Candidatus Magnetoglobus multicellularis", [
        r"(?:candidatus\s+)?magnetoglobus\s+multicellularis",
    ]),
    ("Candidatus Magnetomorum", [r"(?:candidatus\s+)?magnetomorum"]),
    ("Candidatus Magnetaquicoccus", [r"(?:candidatus\s+)?magnetaquicoccus"]),
    ("Magnetofaba australis (IT-1)", [
        r"magnetofaba\s+australis",
        r"\bIT[\s\-]?1\b",
    ]),
    ("Magnetospira thiophila (MMS-1)", [
        r"magnetospira\s+thiophila",
        r"\bMMS[\s\-]?1\b",
    ]),
    ("multicellular magnetotactic prokaryote (MMP)", [
        r"multicellular\s+magnetotactic\s+(?:prokaryote|bacteri)",
        r"\bMMP\b",
    ]),
    # 描述性（兜底）
    ("magnetotactic coccus (descriptive)", [r"magnetotactic\s+coccus", r"magnetotactic\s+cocci"]),
    ("magnetotactic vibrio (descriptive)", [r"magnetotactic\s+vibrio"]),
    ("magnetotactic spirilla (descriptive)", [r"magnetotactic\s+spiril"]),
    ("magnetotactic rod (descriptive)", [r"magnetotactic\s+rod"]),
]

# TEM 关键词（caption 中出现即标 likely_tem）
TEM_PATTERNS = [
    r"\bTEM\b",
    r"transmission\s+electron",
    r"electron\s+micrograph",
    r"\bHRTEM\b",
    r"\bHAADF\b",
    r"cryo[\s\-]?electron",
    r"electron\s+tomograph",
    r"\bSTEM\b",
]
TEM_RE = re.compile("|".join(TEM_PATTERNS), re.IGNORECASE)

# 图片 marker（markdown 内嵌）
IMG_MARKER_RE = re.compile(r'!\[\]\((images/[^)]+)\)')

# Figure caption 起始：覆盖 Figure / Fig. / FIG / FIGURE 等多种版式
# 例:
#   "Figure 1. Transmission electron micrographs..."  (PLOS/Nature 风格)
#   "Fig. 2A. Magnetic..."                            (Springer 风格)
#   "FIG 2 Total iron concentration..."               (ASM 风格，无句点)
#   "FIGURE 1 Factors influencing..."                 (Frontiers/Wiley 风格)
CAPTION_START_RE = re.compile(
    r'^(Fig(?:ure)?\.?\s*\d+[A-Za-z]?[\.\:\,]?\s+[A-Z][^\n]{20,})',
    re.MULTILINE | re.IGNORECASE
)


def scan_species(text: str) -> Counter:
    """统计文本中每个菌种出现次数。"""
    text_l = text.lower()
    cnt = Counter()
    for canonical, patterns in SPECIES:
        for pat in patterns:
            n = len(re.findall(pat, text_l, re.IGNORECASE))
            if n:
                cnt[canonical] += n
    return cnt


def find_caption_near(md: str, img_start: int, img_end: int, window: int = 2000) -> tuple[str, int]:
    """在图片 marker 前后 window 字符内找最近的 caption（部分论文 caption 在图前）。
    优先后方，前方仅当后方没找到时再试。
    返回 (caption_text, figure_number) 或 ("", -1)。"""
    def _clean(cap: str) -> tuple[str, int]:
        nb = cap.find("\n\n")
        if nb > 0:
            cap = cap[:nb]
        n_m = re.match(r'Fig(?:ure)?\.?\s*(\d+)', cap, re.IGNORECASE)
        fn = int(n_m.group(1)) if n_m else -1
        return cap.strip()[:500], fn

    # 1. 后方 window 内
    chunk_after = md[img_end:img_end + window]
    m = CAPTION_START_RE.search(chunk_after)
    if m:
        return _clean(m.group(1))

    # 2. 前方 window 内（取最后一个匹配，离图最近）
    chunk_before = md[max(0, img_start - window):img_start]
    matches = list(CAPTION_START_RE.finditer(chunk_before))
    if matches:
        return _clean(matches[-1].group(1))

    return "", -1


def parse_one_paper(paper_dir: Path) -> list[dict]:
    """解析一篇论文，返回每张图一行的 dict 列表。"""
    paper_id = paper_dir.name
    auto = paper_dir / "auto"
    md_path = auto / f"{paper_id}.md"
    if not md_path.exists():
        return []
    md = md_path.read_text(encoding="utf-8", errors="ignore")

    # 全文菌种统计 → top3
    paper_species = scan_species(md)
    top_species = paper_species.most_common(3)
    top1 = top_species[0][0] if len(top_species) >= 1 else ""
    top2 = top_species[1][0] if len(top_species) >= 2 else ""
    top3 = top_species[2][0] if len(top_species) >= 3 else ""

    rows = []
    for m in IMG_MARKER_RE.finditer(md):
        rel_path = m.group(1)  # "images/xxx.jpg"
        img_abspath = auto / rel_path
        if not img_abspath.exists():
            continue

        caption, fig_num = find_caption_near(md, m.start(), m.end())
        # caption 区域附近扫菌种（caption + 后续 300 字符）
        ctx_start = m.end()
        ctx = md[ctx_start:ctx_start + 1500]
        ctx_species = scan_species(ctx)
        species_in_caption = "; ".join(s for s, _ in ctx_species.most_common(3))

        is_tem = bool(TEM_RE.search(caption)) if caption else False

        rows.append({
            "paper_id": paper_id,
            "image_file": Path(rel_path).name,
            "image_abspath": str(img_abspath),
            "figure_number": fig_num if fig_num > 0 else "",
            "caption_text": caption,
            "is_likely_tem": is_tem,
            "species_in_caption": species_in_caption,
            "species_paper_top1": top1,
            "species_paper_top2": top2,
            "species_paper_top3": top3,
        })
    return rows


def main():
    if not MINERU_OUT.exists():
        sys.exit(f"找不到 {MINERU_OUT}")

    # 论文 metadata（DOI + title）
    meta = {}
    if MAPPING_XLSX.exists():
        mdf = pd.read_csv(MAPPING_XLSX, encoding="utf-8-sig")
        for _, r in mdf.iterrows():
            pid = Path(str(r["new_name"])).stem if r["new_name"] else ""
            if pid:
                meta[pid] = {"doi": r.get("doi", ""), "title": r.get("title", "")}

    all_rows = []
    paper_dirs = [d for d in MINERU_OUT.iterdir() if d.is_dir()]
    print(f"找到 {len(paper_dirs)} 个 paper 目录")
    for pd_dir in sorted(paper_dirs):
        rows = parse_one_paper(pd_dir)
        for r in rows:
            r["paper_doi"] = meta.get(r["paper_id"], {}).get("doi", "")
            r["paper_title"] = meta.get(r["paper_id"], {}).get("title", "")
        all_rows.extend(rows)
        if rows:
            tem_count = sum(1 for r in rows if r["is_likely_tem"])
            print(f"  {pd_dir.name}: {len(rows)} 图, {tem_count} 疑似 TEM")

    if not all_rows:
        sys.exit("没解析出任何图")

    df = pd.DataFrame(all_rows)
    df = df[[
        "paper_id", "image_file", "image_abspath", "figure_number",
        "caption_text", "is_likely_tem",
        "species_in_caption", "species_paper_top1", "species_paper_top2", "species_paper_top3",
        "paper_doi", "paper_title",
    ]]
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    print(f"\n总图数: {len(df)}")
    print(f"疑似 TEM: {df['is_likely_tem'].sum()}")
    print(f"有 caption: {(df['caption_text'].fillna('').str.len() > 0).sum()}")
    print(f"有菌种识别: {(df['species_in_caption'].fillna('').str.len() > 0).sum()}")
    print(f"\n论文 top 菌种分布:")
    print(df["species_paper_top1"].value_counts().head(10).to_string())
    print(f"\n输出: {OUT_CSV}")


if __name__ == "__main__":
    main()
