# 智能设计助手 - RAG系统

基于CAMEL框架的检索增强生成（RAG）系统，专为电力系统与国家电网业务场景设计的知识问答智能体。

## 项目结构

```
run/
├── agents/                               #agent模块
│   ├── __init__.py
│   ├── backend_model.py                  #模型配置（LLM、Embedding、OCR）
│   └── chat_agent.py                     #对话agent工厂函数
├── config/                               #minerU配置文件
│   └── mineru.json
├── data/                                 #数据目录
│   ├── storages/                         #上传的PDF文件存储目录
│   ├── stored_files/                     #数据库和存储文件
│       ├── mineru_output/
│       └── what.pdf
├── models/                               #embedding模型
│   ├── Conan-embedding-v1/
├── run/                                  #运行模块
│   ├── .streamlit/
│   │   └── config.toml                   #Streamlit主题配置
│   ├── config.py                         #UI布局配置
│   └── streamlit.py                      #Streamlit应用主文件
├── tests/                                #测试文件
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── test_backend_model.py         #后端模型测试
│   │   └── test_chat_agent.py            #agent测试 
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── test_load_files.py            #文件加载测试
│   │   └── test_qdrant.py                #向量数据库测试
│   └── __init__.py
├── tools/                                #工具模块
│   ├── __init__.py
│   ├── database_toolkit.py               #数据库工具包
│   ├── load_files.py                     #文件加载和处理
│   ├── mineru_toolkit.py                 #minerU工具
│   └── qdrant.py                         #Qdrant向量数据库接口
├── .gitignore                            #git忽略文件
├── .gitkeep                              #git保留文件
├── Dockerfile                            #docker部署脚本
└── README.md                             #项目说明文档
```

## Quick Start

### 1. 环境准备

**系统要求：**
- Python 3.10
- 建议使用虚拟环境

**创建虚拟环境：**

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖包括：
- `camel-ai` - CAMEL AI框架
- `minerU` -MinerU数据提取工具
- `streamlit` - Web界面
- `qdrant-client` - 向量数据库客户端
- `python-dotenv` - 环境变量管理
- `openai` - OpenAI API接口

### 3. 配置环境变量

复制 `example.env` 为 `.env` 并填写实际的API密钥：

```bash
cp example.env .env
```

编辑 `.env` 文件，填写你的API配置：

```env
# OpenAI兼容API配置（用于主对话模型）
OPENAI_API_KEY=your-openai-api-key-here
url=https://api.openai.com/v1

# Qwen API配置（用于Embedding和OCR）
QWEN_API_KEY=your-qwen-api-key-here
url_qwen=https://dashscope.aliyuncs.com/compatible-mode/v1
```

### 4. 启动服务

```bash
streamlit run run/streamlit.py
```

### 5. 使用docker部署

本项目中Dockerfile针对离线部署进行撰写，需提前封装所需环境镜像


## 功能特色

### 1. 本RAG系统专用于国网电力公司内部系统，支持本地化部署

### 2. 支持上传本地PDF文件并自动存储到向量数据库中自动化查询

### 3. 支持各部件单独测试


服务将在浏览器中自动打开，默认地址：`http://localhost:8501`