from tools import load_multiple_files
import os
from pathlib import Path

path = 'data/stored_files/what.pdf'
BASE_DIR = Path(__file__).resolve().parent.parent
path = os.path.join(BASE_DIR, path)
print(path)

file_paths = [path]
results = load_multiple_files(
    file_paths=file_paths,
    collection_name="database",
    dpi=200
)

print(results)
