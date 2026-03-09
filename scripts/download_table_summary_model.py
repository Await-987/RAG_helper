#!/usr/bin/env python3
"""
下载表格摘要小模型 (Qwen2.5-1.5B-Instruct)

使用方法:
    python scripts/download_table_summary_model.py              # 自动选择镜像
    python scripts/download_table_summary_model.py --source hf   # HuggingFace 官方
    python scripts/download_table_summary_model.py --source hf-mirror  # HF 镜像
    python scripts/download_table_summary_model.py --source modelscope  # ModelScope

模型大小: 约 3GB
"""
import os
import sys
from pathlib import Path
import argparse

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def download_from_huggingface(model_dir: Path, use_mirror: bool = False):
    """从 HuggingFace 下载"""
    from huggingface_hub import snapshot_download

    if use_mirror:
        # 使用 HF-Mirror
        os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
        print("使用镜像: https://hf-mirror.com")

    print("开始下载...")
    snapshot_download(
        repo_id="Qwen/Qwen2.5-1.5B-Instruct",
        local_dir=str(model_dir),
    )


def download_from_modelscope(model_dir: Path):
    """从 ModelScope 下载（国内推荐）"""
    try:
        from modelscope import snapshot_download as ms_snapshot_download
    except ImportError:
        print("❌ 未安装 modelscope，请先安装: pip install modelscope")
        return False

    print("使用 ModelScope 下载（国内镜像）...")
    ms_snapshot_download(
        model_id="Qwen/Qwen2.5-1.5B-Instruct",
        local_dir=str(model_dir),
    )
    return True


def download_model(source: str = "auto"):
    """下载 Qwen2.5-1.5B-Instruct 模型"""

    # 模型保存路径
    model_dir = project_root / "models" / "Qwen2.5-1.5B-Instruct"

    if model_dir.exists():
        print(f"✅ 模型已存在: {model_dir}")
        response = input("是否重新下载？(y/N): ").strip().lower()
        if response != 'y':
            print("跳过下载")
            return True

    print("=" * 60)
    print("下载 Qwen2.5-1.5B-Instruct 模型")
    print("=" * 60)
    print(f"目标路径: {model_dir}")
    print(f"模型大小: 约 3GB")
    print()

    success = False

    if source == "auto":
        # 自动尝试：先 ModelScope，再 HF-Mirror
        print("[自动模式] 尝试 ModelScope...")
        try:
            success = download_from_modelscope(model_dir)
        except Exception as e:
            print(f"ModelScope 失败: {e}")
            print("\n[自动模式] 尝试 HuggingFace 镜像...")
            try:
                download_from_huggingface(model_dir, use_mirror=True)
                success = True
            except Exception as e2:
                print(f"HF-Mirror 失败: {e2}")

    elif source == "modelscope":
        try:
            success = download_from_modelscope(model_dir)
        except Exception as e:
            print(f"❌ 下载失败: {e}")

    elif source == "hf-mirror":
        try:
            download_from_huggingface(model_dir, use_mirror=True)
            success = True
        except Exception as e:
            print(f"❌ 下载失败: {e}")

    elif source == "hf":
        try:
            download_from_huggingface(model_dir, use_mirror=False)
            success = True
        except Exception as e:
            print(f"❌ 下载失败: {e}")

    if success:
        print()
        print("=" * 60)
        print("✅ 模型下载完成!")
        print("=" * 60)
        print(f"路径: {model_dir}")
        return True
    else:
        print()
        print("=" * 60)
        print("❌ 自动下载失败，请手动下载")
        print("=" * 60)
        print("\n方案1: ModelScope（国内推荐）")
        print("  1. 访问 https://modelscope.cn/models/Qwen/Qwen2.5-1.5B-Instruct")
        print("  2. 点击「文件」下载所有文件到 models/Qwen2.5-1.5B-Instruct/")
        print("\n方案2: HuggingFace 镜像")
        print("  1. 访问 https://hf-mirror.com/Qwen/Qwen2.5-1.5B-Instruct")
        print("  2. 下载所有文件到 models/Qwen2.5-1.5B-Instruct/")
        print("\n方案3: 安装 modelscope 后重试")
        print("  pip install modelscope")
        print("  python scripts/download_table_summary_model.py --source modelscope")
        return False


def test_model():
    """测试模型是否能正常加载"""
    print()
    print("=" * 60)
    print("测试模型加载...")
    print("=" * 60)

    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        model_dir = project_root / "models" / "Qwen2.5-1.5B-Instruct"

        if not model_dir.exists():
            print(f"❌ 模型不存在: {model_dir}")
            return False

        print(f"加载 tokenizer...")
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)

        print(f"加载模型...")
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        print(f"  使用设备: {device}")

        model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            torch_dtype=torch.float16 if device == 'cuda' else torch.float32,
            device_map=device,
            trust_remote_code=True
        )

        # 测试生成
        print("测试生成...")
        messages = [
            {"role": "system", "content": "你是一个助手。"},
            {"role": "user", "content": "请用一句话介绍自己。"}
        ]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer([text], return_tensors="pt")
        inputs = {k: v.to(model.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model.generate(**inputs, max_new_tokens=50, pad_token_id=tokenizer.eos_token_id)

        response = tokenizer.decode(outputs[0][inputs["input_ids"].shape[1]:], skip_special_tokens=True)
        print(f"模型回复: {response}")

        print()
        print("✅ 模型测试通过!")
        return True

    except Exception as e:
        print(f"❌ 模型测试失败: {e}")
        return False


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="下载/测试表格摘要模型")
    parser.add_argument("--test-only", action="store_true", help="仅测试模型，不下载")
    parser.add_argument("--source", choices=["auto", "hf", "hf-mirror", "modelscope"],
                        default="auto", help="下载源 (默认: auto 自动选择)")
    args = parser.parse_args()

    if not args.test_only:
        download_model(source=args.source)

    test_model()
