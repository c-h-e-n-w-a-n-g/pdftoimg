import shutil
from pathlib import Path
import pandas as pd


root_path=Path(__file__).parent
CSV_IN= root_path/"selected_tem.csv"
OUTPUT=root_path/"image_out"
META_OUT=OUTPUT/"metadata.csv"
OUTPUT.mkdir(parents=True,exist_ok=True)

df=pd.read_csv(CSV_IN)
ok,miss=0,0
meta_rows=[]
for _,row in df.iterrows() :
    src = Path(row["image_abspath"])
    name,fig=row["paper_id"],row["figure_number"]
    if not src.exists() :
        print(f"未找到，跳过{src}")
        miss+=1
        continue
    out_name=f"{name}_fig{fig}{src.suffix}"
    shutil.copy(src,OUTPUT/out_name)
    meta_rows.append({
        "image_filename":out_name,
        "paper_id":name,
        "figure_number":fig,
        "caption_text":row["caption_text"],
        "species_in_caption":row["species_in_caption"],
        "paper_doi":row["paper_doi"],
    })
    ok+=1

pd.DataFrame(meta_rows).to_csv(META_OUT,index=False,encoding="utf-8-sig")
print(f"完成:{ok},跳过：:{miss}，总计：{len(df)}")
print(f"metadata已写入：{META_OUT}")
