import os
import sys

# ✅ 把项目根目录加入 sys.path，保证能 import 到 tools 目录下的模块
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from tools.load_files import preprocess  # 现在能找到

def main():
    data = [{"type": "discarded", "text": "x"}]
    out = preprocess(data=data, chunk_min_size=400, overlap_size=50)
    print("preprocess output:", out)
    print("is None?", out is None)

if __name__ == "__main__":
    main()