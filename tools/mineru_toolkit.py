# @ wangpei
import json
import os
from pathlib import Path
from storage_paths import STORED_FILES_DIR

absolute_path = Path(__file__).absolute().parent.parent
mineru_path = absolute_path / "config" / "mineru.json"


def _resolve_path_value(value: str) -> str:
    """Resolve a path against project root when it is not absolute."""
    candidate = Path(value)
    if candidate.is_absolute():
        return str(candidate)
    return str((absolute_path / candidate).resolve())


def _resolve_mineru_config_paths(config_path: Path) -> Path:
    """Resolve MinerU model paths against project root and allow env overrides."""
    with config_path.open("r", encoding="utf-8") as f:
        config = json.load(f)

    models_dir = config.get("models-dir", {})
    changed = False
    env_overrides = {
        "pipeline": os.getenv("MINERU_MODELS_DIR_PIPELINE", "").strip(),
        "vlm": os.getenv("MINERU_MODELS_DIR_VLM", "").strip(),
    }

    for key, env_value in env_overrides.items():
        if not env_value:
            continue
        resolved_env_value = _resolve_path_value(env_value)
        if models_dir.get(key) != resolved_env_value:
            models_dir[key] = resolved_env_value
            changed = True

    for key, value in list(models_dir.items()):
        if not value:
            continue
        resolved_value = _resolve_path_value(value)
        if value != resolved_value:
            models_dir[key] = resolved_value
            changed = True

    if not changed:
        return config_path

    resolved_path = config_path.with_name("mineru.resolved.json")
    with resolved_path.open("w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
    return resolved_path


resolved_mineru_path = _resolve_mineru_config_paths(mineru_path)

os.environ["MINERU_TOOLS_CONFIG_JSON"] = str(resolved_mineru_path)
print("mineru:", resolved_mineru_path)
# os.environ['MODELSCOPE_USE_CACHE'] = "1"
# os.environ['MODELSCOPE_HUB_CHECK'] = "0"
# os.environ['HF_HUB_OFFLINE'] = "1"
# os.environ['TRANSFORMERS_OFFLINE'] = "1" # 强制 transformers 也不许联网
import copy
from pathlib import Path
from typing import Dict, Any, Optional
from mineru.cli.common import (
    convert_pdf_bytes_to_bytes_by_pypdfium2,
    prepare_env,
    read_fn
)
from mineru.data.data_reader_writer import FileBasedDataWriter
from mineru.utils.draw_bbox import draw_layout_bbox, draw_span_bbox
from mineru.backend.pipeline.pipeline_analyze import doc_analyze as pipeline_doc_analyze
from mineru.backend.pipeline.pipeline_middle_json_mkcontent import \
    union_make as pipeline_union_make
from mineru.backend.pipeline.model_json_to_middle_json import \
    result_to_middle_json as pipeline_result_to_middle_json
from mineru.utils.enum_class import MakeMode
from mineru.backend.vlm.vlm_analyze import doc_analyze as vlm_doc_analyze
from mineru.backend.vlm.vlm_middle_json_mkcontent import union_make as vlm_union_make

# """如果您由于网络问题无法下载模型，可以设置环境变量MINERU_MODEL_SOURCE为modelscope使用免代理仓库下载模型"""
# @qiaoyu：20260303修改：使用本地 VLM 模型（已下载到 models/mineru2.5/）
os.environ['MINERU_MODEL_SOURCE'] = "local"

# 跨平台兼容：使用 Path.home() 代替 ~
cache_dir = Path.home() / ".cache" / "modelscope" / "hub" / "models" / "OpenDataLab" / "PDF-Extract-Kit-1." / "models"
os.environ['MODELSCOPE_CACHE'] = str(cache_dir)
# 添加这行来使用本地缓存
os.environ['MODELSCOPE_USE_CACHE'] = "1"

class MineruPathManager:
    """MinerU路径管理器

    统一管理所有MinerU组件相关的文件路径，包括输出目录、图片目录、Excel目录和临时目录等。
    提供了一系列方法来获取这些目录的路径，并确保它们存在。
    """

    def __init__(self, base_dir=None):
        """初始化路径管理器

        Args:
            base_dir (str, optional): 基础输出目录，如果为None则使用默认位置
        """
        self._base_dir = base_dir or self._get_default_base_dir()
        self._ensure_dir_exists(self._base_dir)

    @staticmethod
    def _get_default_base_dir():
        """获取默认的基础输出目录

        Returns:
            str: 默认基础目录的路径字符串
        """
        return str(STORED_FILES_DIR)

    @staticmethod
    def _ensure_dir_exists(dir_path):
        """确保目录存在，不存在则创建

        Args:
            dir_path (str): 需要确保存在的目录路径
        """
        os.makedirs(dir_path, exist_ok=True)

    def get_mineru_output_dir(self):
        """获取MinerU输出目录

        Returns:
            str: MinerU输出目录的路径
        """
        path = os.path.join(self._base_dir, "mineru_output")
        self._ensure_dir_exists(path)
        return path

    def get_mineru_image_output_dir(self, pdf_file_name: str, parse_method: str) -> str:
        """获取MinerU图片输出目录

        Args:
            pdf_file_name (str): PDF文件名称不含后缀
            parse_method (str): 解析方式，不同解析模式可能对应不同的子目录
        Returns:
            str: 图片输出目录路径
        """
        output_dir = self.get_mineru_output_dir()
        local_image_dir, _ = prepare_env(output_dir, pdf_file_name, parse_method)
        return local_image_dir

    def get_excel_output_dir(self):
        """获取Excel输出目录

        Returns:
            str: Excel输出目录的路径
        """
        path = os.path.join(self._base_dir, "excel")
        self._ensure_dir_exists(path)
        return path

    def get_temp_dir(self):
        """获取临时文件目录

        Returns:
            str: 临时文件目录的路径
        """
        path = os.path.join(self._base_dir, "temp")
        self._ensure_dir_exists(path)
        return path


class MineruComponentInitParams:
    """MinerU组件初始化参数类

    用于初始化MinerU组件的参数集合，目前包含路径管理器实例。
    """
    mineru_path_manager: MineruPathManager = MineruPathManager()


class MineruResponse:
    """MinerU组件响应类

    用于封装MinerU组件处理结果的标准响应格式，包含状态、数据和错误信息。
    """

    def __init__(self, status: str, data: Optional[list[str, Any]], error: Optional[str] = None):
        """初始化响应对象

        Args:
            status (str): 响应状态，通常为"success"或"error"
            data (Optional[list[str, Any]]): 响应数据，成功时包含处理结果
            error (Optional[str], optional): 错误信息，失败时包含错误描述
        """
        self.status = status
        self.data = data
        self.error = error


class MineruComponent:
    """MinerU文档分析组件

    提供PDF文档分析功能，能够解析PDF文档结构，提取内容，并生成多种格式的输出文件。

    支持两种后端：
      - pipeline模式（默认）：通用的文档分析
      - VLM模式：通过VLM模型进行分析，backend参数需传入类似"vlm-transformers"、"vlm-sglang-engine"或"vlm-sglang-client"，同时在VLM模式下可选传入server_url
    """

    def __init__(self, init_params: MineruComponentInitParams = MineruComponentInitParams()):
        """初始化MinerU组件

        Args:
            init_params (MineruComponentInitParams, optional): 初始化参数，默认创建新实例
        """
        self.init_params = init_params
        self.mineru_path_manager = init_params.mineru_path_manager

    def run(self, pdf_file_path: str, parse_method: str = "auto", backend: str = "pipeline",
            server_url: Optional[str] = None) -> MineruResponse:
        """运行MinerU文档分析

        处理指定的PDF文件，根据backend调用pipeline或VLM模式进行文档分析，
        并生成多种格式的输出文件。

        Args:
            pdf_file_path (str): PDF文件的路径
            parse_method (str, optional): 解析方法，可选值包括"auto"、"ocr"等，默认为"auto"
            backend (str, optional): 后端解析方式。默认为"pipeline"；如果需要使用VLM模式，可传入"vlm-transformers"、"vlm-sglang-engine"或"vlm-sglang-client"等。
            server_url (Optional[str], optional): 当backend为VLM模式中客户端模式时需要指定服务端URL。

        Returns:
            MineruResponse: 包含处理结果或错误信息的响应对象
        """
        # try:
        file_path = Path(pdf_file_path)
        if not file_path.exists():
            print("pdf路径不存在")
            return MineruResponse("error", None, f"File not found: {pdf_file_path}")
        if file_path.suffix.lower() != ".pdf":
            return MineruResponse("error", None, "Only PDF files are supported")

        file_name = file_path.stem
        pdf_bytes = read_fn(file_path)
        pdf_bytes = convert_pdf_bytes_to_bytes_by_pypdfium2(pdf_bytes)

        output_dir = self.mineru_path_manager.get_mineru_output_dir()
        image_writer = FileBasedDataWriter(output_dir)
        md_writer = FileBasedDataWriter(output_dir)

        if backend == "pipeline":
            infer_results, all_image_lists, all_pdf_docs, lang_list, ocr_enabled_list = pipeline_doc_analyze(
                [pdf_bytes], ["ch"], parse_method=parse_method
            )
            model_result = infer_results[0]
            image_list = all_image_lists[0]
            pdf_doc = all_pdf_docs[0]
            lang = lang_list[0]
            ocr_enable = ocr_enabled_list[0]

            middle_json = pipeline_result_to_middle_json(model_result, image_list, pdf_doc, image_writer, lang,
                                                         ocr_enable)
            middle_json["_backend"] = "pipeline"
            pdf_info = middle_json["pdf_info"]

            image_dir = os.path.basename(output_dir)
            content_list = pipeline_union_make(pdf_info, MakeMode.CONTENT_LIST, image_dir)
            # md_writer.write_string(f"{file_name}.json",
            #                        json.dumps(content_list, ensure_ascii=False, indent=4))

        elif backend.startswith("vlm"):
            backend_short = backend[4:] if backend.startswith("vlm-") else backend
            middle_json, infer_result = vlm_doc_analyze(
                pdf_bytes, image_writer=image_writer, backend=backend_short, server_url=server_url
            )
            for page in middle_json.get("pdf_info", []):
                if "preproc_blocks" not in page:
                    page["preproc_blocks"] = []
            middle_json["_backend"] = backend
            pdf_info = middle_json["pdf_info"]

            image_dir = os.path.basename(output_dir)
            content_list = vlm_union_make(pdf_info, MakeMode.CONTENT_LIST, image_dir)
            # md_writer.write_string(f"{file_name}_content_list.json",
            #                        json.dumps(content_list, ensure_ascii=False, indent=4))
        else:
            return MineruResponse("error", None, f"Unsupported backend type: {backend}")

        # output_files = {"content_list": os.path.join(output_dir, f"{file_name}_content_list.json")}

        return MineruResponse("success", content_list, None)

        # except Exception as e:
        #     print(e)
        #     return MineruResponse("error", None, str(e))
