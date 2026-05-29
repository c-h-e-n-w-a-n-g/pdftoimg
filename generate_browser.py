"""
读 dataset_meta.csv 生成单文件 dataset_browser.html，浏览器双击打开即用。
功能：缩略图墙 + 筛选（论文/菌种/疑似TEM）+ 复选框打 is_real_tem 标签 +
      localStorage 保存 + 导出 selected_tem.csv
"""
import json
from pathlib import Path
import pandas as pd

CSV_IN = Path(r"D:\mg\collect\dataset_meta.csv")
HTML_OUT = Path(r"D:\mg\collect\dataset_browser.html")


def main():
    df = pd.read_csv(CSV_IN, encoding="utf-8-sig").fillna("")
    # 转 file:// URL，处理反斜杠
    df["image_url"] = df["image_abspath"].apply(
        lambda p: "file:///" + p.replace("\\", "/")
    )
    records = df.to_dict(orient="records")

    papers = sorted(df["paper_id"].unique().tolist())
    species = sorted({s for s in df["species_paper_top1"].unique() if s})

    html = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>TEM 数据集筛选 - Tyr</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;margin:0;padding:0;background:#f5f5f5}
.toolbar{position:sticky;top:0;background:#fff;border-bottom:1px solid #ddd;padding:12px 20px;
  display:flex;flex-wrap:wrap;gap:12px;align-items:center;z-index:100;box-shadow:0 2px 4px rgba(0,0,0,.05)}
.toolbar select,.toolbar input{padding:6px;font-size:13px;border:1px solid #ccc;border-radius:4px}
.toolbar button{padding:6px 12px;font-size:13px;background:#2563eb;color:#fff;border:none;border-radius:4px;cursor:pointer}
.toolbar button:hover{background:#1d4ed8}
.counts{margin-left:auto;font-size:13px;color:#555}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px;padding:14px}
.card{background:#fff;border:1px solid #e5e5e5;border-radius:6px;overflow:hidden;display:flex;flex-direction:column;
  transition:transform .1s,border-color .15s}
.card.selected{border:2px solid #16a34a;background:#f0fdf4}
.card.likely-tem{border-left:4px solid #f59e0b}
.card img{width:100%;height:200px;object-fit:contain;background:#000;cursor:zoom-in}
.card .meta{padding:8px 10px;font-size:12px;line-height:1.4}
.card .pid{font-weight:600;color:#1e40af}
.card .figno{color:#6b7280;font-size:11px}
.card .caption{margin:4px 0;max-height:55px;overflow:hidden;color:#374151}
.card .species{color:#059669;font-size:11px;margin-top:4px}
.card .footer{padding:6px 10px;background:#fafafa;display:flex;justify-content:space-between;align-items:center;border-top:1px solid #eee}
.card .footer label{font-size:12px;cursor:pointer;display:flex;align-items:center;gap:4px}
.tem-badge{font-size:10px;background:#f59e0b;color:#fff;padding:2px 6px;border-radius:3px}
.modal{display:none;position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,.85);z-index:200;
  align-items:center;justify-content:center;cursor:zoom-out}
.modal.show{display:flex}
.modal img{max-width:95%;max-height:95%}
</style>
</head>
<body>
<div class="toolbar">
  <label>论文: <select id="fPaper"><option value="">全部 (__PAPER_COUNT__)</option></select></label>
  <label>菌种: <select id="fSpecies"><option value="">全部</option></select></label>
  <label>疑似TEM:
    <select id="fTem">
      <option value="">全部</option>
      <option value="true">是</option>
      <option value="false">否</option>
    </select>
  </label>
  <label>已勾选:
    <select id="fSel">
      <option value="">全部</option>
      <option value="true">仅已勾选</option>
      <option value="false">未勾选</option>
    </select>
  </label>
  <button id="exportBtn">导出已勾选 CSV</button>
  <button id="clearBtn" style="background:#dc2626">清空勾选</button>
  <span class="counts" id="counts"></span>
</div>
<div class="grid" id="grid"></div>
<div class="modal" id="modal"><img id="modalImg"></div>

<script>
const DATA = __DATA_JSON__;
const PAPERS = __PAPERS_JSON__;
const SPECIES = __SPECIES_JSON__;
const LS_KEY = "tyr_tem_selected_v1";

let selected = new Set(JSON.parse(localStorage.getItem(LS_KEY) || "[]"));

// 填筛选下拉
const fPaper = document.getElementById("fPaper");
PAPERS.forEach(p => fPaper.add(new Option(p, p)));
const fSpecies = document.getElementById("fSpecies");
SPECIES.forEach(s => fSpecies.add(new Option(s, s)));

const fTem = document.getElementById("fTem");
const fSel = document.getElementById("fSel");
const grid = document.getElementById("grid");
const countsEl = document.getElementById("counts");
const modal = document.getElementById("modal");
const modalImg = document.getElementById("modalImg");

function key(r){ return r.paper_id + "/" + r.image_file; }

function render(){
  const pVal = fPaper.value, sVal = fSpecies.value, tVal = fTem.value, selVal = fSel.value;
  let filtered = DATA.filter(r => {
    if (pVal && r.paper_id !== pVal) return false;
    if (sVal && r.species_paper_top1 !== sVal) return false;
    if (tVal === "true" && !r.is_likely_tem) return false;
    if (tVal === "false" && r.is_likely_tem) return false;
    const isSel = selected.has(key(r));
    if (selVal === "true" && !isSel) return false;
    if (selVal === "false" && isSel) return false;
    return true;
  });
  grid.innerHTML = "";
  filtered.forEach(r => {
    const k = key(r);
    const isSel = selected.has(k);
    const tem = String(r.is_likely_tem).toLowerCase() === "true";
    const card = document.createElement("div");
    card.className = "card" + (isSel ? " selected" : "") + (tem ? " likely-tem" : "");
    card.innerHTML = `
      <img loading="lazy" src="${r.image_url}" alt="${r.image_file}">
      <div class="meta">
        <div><span class="pid">${r.paper_id}</span>
             ${r.figure_number ? `<span class="figno"> · Fig ${r.figure_number}</span>` : ""}
             ${tem ? `<span class="tem-badge">疑似TEM</span>` : ""}</div>
        <div class="caption" title="${(r.caption_text||'').replace(/"/g,'&quot;')}">${r.caption_text || "<i>(无 caption)</i>"}</div>
        <div class="species">${r.species_in_caption || r.species_paper_top1 || ""}</div>
      </div>
      <div class="footer">
        <label><input type="checkbox" data-key="${k}" ${isSel ? "checked" : ""}> 标为真TEM</label>
        <a href="${r.image_url}" target="_blank" style="font-size:11px">原图</a>
      </div>`;
    card.querySelector("img").onclick = (e) => {
      e.stopPropagation();
      modalImg.src = r.image_url;
      modal.classList.add("show");
    };
    card.querySelector("input").onchange = (e) => {
      if (e.target.checked) selected.add(k); else selected.delete(k);
      localStorage.setItem(LS_KEY, JSON.stringify([...selected]));
      card.classList.toggle("selected", e.target.checked);
      updateCounts();
    };
    grid.appendChild(card);
  });
  updateCounts(filtered.length);
}

function updateCounts(shown){
  if (shown === undefined) shown = grid.children.length;
  countsEl.textContent = `显示 ${shown} / 全部 ${DATA.length} 张 · 已勾选 ${selected.size}`;
}

[fPaper, fSpecies, fTem, fSel].forEach(el => el.onchange = render);

modal.onclick = () => modal.classList.remove("show");

document.getElementById("exportBtn").onclick = () => {
  const sel = DATA.filter(r => selected.has(key(r)));
  if (!sel.length) { alert("没勾选任何图"); return; }
  const cols = ["paper_id","image_file","image_abspath","figure_number","caption_text",
                "species_in_caption","species_paper_top1","paper_doi","paper_title"];
  const csv = [cols.join(",")].concat(
    sel.map(r => cols.map(c => {
      let v = String(r[c] ?? "");
      if (v.includes(",") || v.includes('"') || v.includes("\\n")) v = '"' + v.replace(/"/g,'""') + '"';
      return v;
    }).join(","))
  ).join("\\n");
  // 加 BOM 让 Excel 正确识别 UTF-8
  const blob = new Blob(["\\uFEFF" + csv], {type:"text/csv;charset=utf-8"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "selected_tem.csv";
  a.click();
};

document.getElementById("clearBtn").onclick = () => {
  if (!confirm("确认清空所有勾选？")) return;
  selected.clear();
  localStorage.removeItem(LS_KEY);
  render();
};

render();
</script>
</body>
</html>
"""

    html = (html
            .replace("__DATA_JSON__", json.dumps(records, ensure_ascii=False))
            .replace("__PAPERS_JSON__", json.dumps(papers, ensure_ascii=False))
            .replace("__SPECIES_JSON__", json.dumps(species, ensure_ascii=False))
            .replace("__PAPER_COUNT__", str(len(papers))))

    HTML_OUT.write_text(html, encoding="utf-8")
    print(f"生成: {HTML_OUT}")
    print(f"  数据: {len(records)} 张图, {len(papers)} 篇论文, {len(species)} 个菌种")
    print(f"\n双击 {HTML_OUT.name} 用浏览器打开即可。")


if __name__ == "__main__":
    main()
