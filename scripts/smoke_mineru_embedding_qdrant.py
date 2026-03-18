#!/usr/bin/env python
"""
MinerU + Embedding + Qdrant 三合一 Smoke Test

依次验证三个核心组件：
  1. MinerU  - 解析指定 PDF，打印所有 content_list 元素预览
  2. Embedding - 加载本地 embedding 模型，验证向量维度与 NaN
  3. Qdrant  - 将解析结果入库，执行关键词检索验证

用法:
    python scripts/smoke_mineru_embedding_qdrant.py
    SMOKE_PDF=data/stored_files/your.pdf python scripts/smoke_mineru_embedding_qdrant.py

环境变量:
    SMOKE_PDF    指定测试 PDF 路径（默认使用内置示例路径）
    conan_path   embedding 模型路径（同 .env 配置）
"""
import os
import re
import sys
import time
import math
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

DEFAULT_PDF = PROJECT_ROOT / "data" / "stored_files" / "GB20052-2020 电力变压器能效限定值及能效等级.pdf"


def clean_text(s: str) -> str:
    if any(m in s for m in ("Ã", "Â", "â€")):
        try:
            s = s.encode("latin1").decode("utf-8")
        except Exception:
            pass
    s = re.sub(r"<[^>]+>", " ", s)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u2014", "-").replace("\u2013", "-")
    return re.sub(r"\s+", " ", s).strip()


def contains_keyword(chunks, keyword: str) -> bool:
    kw = keyword.strip()
    return any(kw in clean_text(c) for c in chunks)


def section(title: str):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


# ---------------------------------------------------------------------------
# Step 1: MinerU
# ---------------------------------------------------------------------------
def test_mineru(pdf_path: Path):
    section("1) MinerU 解析测试")
    try:
        import mineru
        print("mineru version:", getattr(mineru, "__version__", "unknown"))
    except Exception as e:
        print("mineru import failed:", e)
        return None

    from tools.mineru_toolkit import MineruComponent

    t0 = time.time()
    resp = MineruComponent().run(str(pdf_path))
    dt = time.time() - t0

    if getattr(resp, "status", None) != "success":
        print("status:", getattr(resp, "status", None))
        print("error:",  getattr(resp, "error", None))
        return None

    content_list = resp.data or []
    print(f"pdf:    {pdf_path}")
    print(f"items:  {len(content_list)}")
    print(f"time:   {dt:.2f}s")

    print("\n--- content_list preview ---")
    for idx, item in enumerate(content_list, 1):
        t = item.get("type")
        if t in ("text", "equation"):
            raw = str(item.get("text", ""))
        elif t == "image":
            raw = str(item.get("image_caption", ""))
        elif t == "table":
            raw = str(item.get("table_caption", "")) + " " + str(item.get("table_body", ""))
        else:
            raw = str(item)
        print(f"[{idx:04d}] type={t} len={len(raw)} :: {clean_text(raw)[:200]}")

    chunks = []
    for item in content_list:
        t = item.get("type")
        if t in ("text", "equation"):
            chunks.append(str(item.get("text", "")))
        elif t == "image":
            chunks.append(str(item.get("image_caption", "")))
        elif t == "table":
            chunks.append(str(item.get("table_caption", "")) + " " + str(item.get("table_body", "")))

    print("\n关键词检查:")
    for kw in ["前言", "GB 20052", "本标准"]:
        print(f"  contains '{kw}': {contains_keyword(chunks, kw)}")

    return chunks


# ---------------------------------------------------------------------------
# Step 2: Embedding
# ---------------------------------------------------------------------------
def test_embedding():
    section("2) Embedding 自检（本地模型）")
    from camel.embeddings import SentenceTransformerEncoder

    rel_path = os.getenv("conan_path", "")
    model_path = (PROJECT_ROOT / rel_path).resolve()
    print(f"conan_path: {rel_path}")
    print(f"model_path: {model_path}")

    model = SentenceTransformerEncoder(model_name=str(model_path))

    samples = [
        "前言",
        "本标准规定了三相电力变压器的能效限定值、能效等级和试验方法。",
        "hello world",
    ]
    for s in samples:
        t0 = time.time()
        vec = model.embed(s)
        dt = time.time() - t0
        has_nan = any(v is None or (isinstance(v, float) and math.isnan(v)) for v in vec)
        print(f"  text={s[:30]!r}  dim={len(vec)}  nan={has_nan}  time={int(dt*1000)}ms")


# ---------------------------------------------------------------------------
# Step 3: Qdrant
# ---------------------------------------------------------------------------
def test_qdrant(chunks):
    section("3) Qdrant 入库 + 检索测试")
    from tools.qdrant import QdrantDB, QdrantDB_Init, save2Qdrant_Input

    db = QdrantDB(QdrantDB_Init(collection_name="database"))

    cleaned = [clean_text(c) for c in chunks if len(clean_text(c)) >= 20]
    print(f"chunks_in={len(chunks)}  chunks_cleaned={len(cleaned)}")

    t0 = time.time()
    db.save2Qdrant(save2Qdrant_Input(text=cleaned, origin_file="smoke_test"))
    print(f"index_time: {time.time() - t0:.2f}s")

    for q in ["前言", "本标准", "能效等级"]:
        hits = db.search(q, top_k=5)
        print(f"\nquery={q!r}  hits={len(hits)}")
        for i, h in enumerate(hits, 1):
            content = (h.get("payload") or {}).get("Content", "")
            print(f"  {i}. {clean_text(content)[:160]}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    pdf = Path(os.getenv("SMOKE_PDF", str(DEFAULT_PDF)))
    if not pdf.exists():
        print(f"PDF not found: {pdf}")
        print("Set env SMOKE_PDF to point to an existing PDF.")
        sys.exit(1)

    chunks = test_mineru(pdf)
    test_embedding()
    if chunks:
        test_qdrant(chunks)
    else:
        print("\nSkipping Qdrant test (MinerU returned no chunks).")

    print("\nDone.")


if __name__ == "__main__":
    main()
