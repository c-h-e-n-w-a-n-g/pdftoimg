# MTB-TEM 数据集收集 Pipeline

从 Zotero 文献库到一份带 metadata 的 TEM 图片数据集的完整流程。

***

## 1. PDF图片获取

输入：你 Zotero 里收藏的文献 PDF。
输出：`image_out/` 目录下按 `{Citekey}_fig{N}.jpg` 命名的 TEM 图片 + `metadata.csv`（含 caption、菌种、DOI）。

中间会经过 PDF 解析、figure/caption 抽取、菌种识别、**人工筛选**、归档几个阶段。

***

## 2. 数据流程

```
Zotero 导出（也可以是自己的PDF的文件夹）
    │  zotero_pdf_paths.csv
    ▼
[1] rename_and_copy.py      →  literature/*.pdf + literature_mapping.xlsx
    ▼
[2] batch_mineru.py         →  mineru_out/{paper}/auto/...
    ▼
[3] extract_species_and_figures.py  →  dataset_meta.csv
    ▼
[4] generate_browser.py     →  dataset_browser.html
    ▼
🛑【人工筛选】浏览器打开 HTML，勾选真 TEM，导出 selected_tem.csv
    ▼
[5] image_copy.py           →  image_out/*.jpg + metadata.csv  ✅ 终点
```

第 1-4 步由 `run_stage1.py` 串起来，跑完会停在 HTML 等筛选。

***

## 3. 环境准备

### 3.1 Python 依赖

```bash
pip install pandas openpyxl pypdf bibtexparser unidecode requests opencv-python
```

> Python 3.10+。

### 3.2 MinerU 安装

按官方文档安装：<https://github.com/opendatalab/MinerU>

**⚠️ 我们用 pipeline backend，不是 vlm backend。**
`batch_mineru.py` 里已经硬编码了 `-b pipeline`

### 3.3 模型下载

**⚠️ 国内用户从 ModelScope 下，不要走 HuggingFace（会卡住）。**

参考 MinerU 文档的 ModelScope 下载章节。
minerU使用时需要关闭代理，否则会卡住。

***

## 4. 怎么跑

### 4.1 准备 zotero\_pdf\_paths.csv

从 Zotero 导出包含以下列的 CSV，放到 `collect/zotero_pdf_paths.csv，或者直接从你收集的文献文件夹中导出一个exccel包含以下4列`：

| 列名         | 说明          |
| ---------- | ----------- |
| `pdf_path` | PDF 文件的绝对路径 |
| `year`     | 发表年份        |
| `doi`      | DOI（用于去重）   |
| `title`    | 论文标题        |

> 同 DOI 多文件会按"保留最大体积"自动去重。

### 4.1.b 没有 Zotero、PDF 是自己下的怎么办？

`rename_and_copy.py` 是为 Zotero 用户写的，依赖 Zotero 特定的文件名格式（`"作者 等 - 年份 - ..."`）。如果你的 PDF 是自己下的、文件名各种各样，用 `rename_downloaded_pdfs.py` 代替第 1 步：

1. 配置 `rename_downloaded_pdfs.py` 里的 `ROOT` 为你的 PDF 所在目录，先 `DRY_RUN = True` 预览重命名结果，确认无误后改成 `False` 执行
   - 脚本会从 PDF metadata 读取第一作者姓氏 + 年份，读不到则用 `unknown_001` 等编号，所有文件名均为 ASCII
2. 把改好名的 PDF 全部放进 `collect/literature/` 目录
3. 跑 mineru 开始的后 3 步：

   ```bash
   python run_stage1.py --from-step 2
   ```

4. *（可选）* 想要 `dataset_meta.csv` 里带 DOI/title 两列追溯，手写一份 `literature_mapping.xlsx`，三列：

   | 列名         | 说明                |
   | ---------- | ----------------- |
   | `new_name` | 文件名（含 .pdf）       |
   | `doi`      | DOI               |
   | `title`    | 论文标题              |

   不想要就跳过这一步，对应列会留空，不影响后续流程。

### 4.2 PDF → HTML阶段

```bash
python run_stage1.py
```

中途失败可以续跑：

```bash
python run_stage1.py --from-step 3   # 从第 3 步开始
```

> **mineru 这一步会很慢** 脚本会自动按 15 篇/批跑，避免内存堆积崩溃。跑过的论文会自动跳过，所以崩了直接重跑即可。

### 4.3 人工筛选

浏览器双击打开 `dataset_browser.html`：

- 用左上角下拉筛"疑似 TEM"先过一遍
- 勾选确认是 TEM 的图（勾选状态自动存浏览器 localStorage，关掉再开还在）
- 点 **"导出已勾选 CSV"** → 下载 `selected_tem.csv`，放回 `collect/` 目录

### 4.4 归档图片

```bash
python image_copy.py
```

产出：

- `image_out/{Citekey}_fig{N}.jpg`
- `image_out/metadata.csv`（image\_filename, paper\_id, figure\_number, caption, 菌种, DOI）

***

## 5. 常见问题

**Q: mineru 跑到一半挂了？**
A: 直接 `python run_stage1.py --from-step 2` 重跑。已成功的论文（`mineru_out/{paper}/auto/{paper}.md` 存在且 > 500B）会自动跳过。

**Q: 改了 zotero 库想重跑，但 mineru 不想再跑一遍？**
A: 跑完第 1 步后用 `--from-step 3` 跳过 mineru。

**Q:** **`selected_tem.csv`** **里某些图复制时报"未找到"？**
A: 一般是 mineru 没成功解析这篇，导致 `image_abspath` 指向不存在的文件。检查 `batch_log.csv` 里对应论文的状态。

**Q: 浏览器打开 HTML 图片显示不出来？**
A: HTML 用 `file:///` 协议直引本地路径。如果你把 `mineru_out/` 移动过位置，路径会失效，需要重跑第 3 步重新生成 `dataset_meta.csv`。

**Q: Excel 打开 metadata.csv 中文乱码？**
A: 别用 Excel 编辑这些 CSV——Excel 会破坏 UTF-8 非 ASCII 字符。要看就只读打开，要改用 Python / VSCode。

***

## 6. 文件清单

| 文件                               | 用途                              |
| -------------------------------- | ------------------------------- |
| `run_stage1.py`                  | 阶段 1 orchestrator（4 步串行）        |
| `rename_and_copy.py`             | Zotero PDF 重命名 + 复制（Zotero 用户用）|
| `rename_downloaded_pdfs.py`      | 直接下载的 PDF 重命名（非 Zotero 用户用）  |
| `batch_mineru.py`                | 分批跑 MinerU                      |
| `extract_species_and_figures.py` | 抽 figure + caption + 菌种         |
| `generate_browser.py`            | 生成筛选用 HTML                      |
| `image_copy.py`                  | 归档勾选的图 + metadata               |
| `MTB reference.bib`              | Zotero 导出的文献库（DOI ↔ citekey 映射） |
| `dataset_meta.csv`               | 全量候选图元数据（自动产出）                  |
| `selected_tem.csv`               | 人工筛选结果（浏览器导出）                   |
| `image_out/`                     | 终点输出目录                          |

