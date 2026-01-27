## 📝 PR 描述：修复 preprocess 函数处理未知数据类型时的 KeyError 崩溃

### 1. 简要描述 (Summary)
修复了 `preprocess` 函数在处理 MinerU 解析结果时，因遇到未在 `type2key` 字典中定义的 `discarded` 类型而导致系统抛出 `KeyError` 异常并中断运行的问题。
**业务影响**：入库链路中断会导致文档未写入向量库，后续对该文档提问时只能返回“不知道”。

### 2. 问题定位 (Root Cause)
在对复杂 PDF 进行集成测试时，上游解析工具 MinerU 会输出名为 `discarded` 的内容类型（可能对应文档中的页眉、页脚、水印或杂质内容）。
* **风险点**：当前 `preprocess` 函数中的 `type2key` 映射字典仅定义了 `text`, `equation`, `image`, `table` 四种类型。
* **崩溃原因**：当程序遍历到 `discarded` 项时，通过 `type2key[chunk_type]` 取值会因键不存在而立刻抛出 `KeyError`，导致整个文件入库任务失败。

### 3. 测试与复现证明 (Evidence)
使用冒烟测试脚本 `tests/smoke_mineru_debug_and_retrieve.py` 成功稳定复现。

**测试环境数据分布：**
根据脚本的 Debug 模式取证，在测试集中多个 PDF 均包含大量 `discarded` 类型数据：
- **《电网运行规则.pdf》**: 包含 **53个** `discarded` 项。
- **《GB20052-2020 电力变压器能效限定值及能效等级.pdf》**: 包含 **43个** `discarded` 项。

**报错堆栈回溯 (Traceback)：**
```text
File "tools\load_files.py", line 27, in preprocess
    chunk_key = type2key[chunk_type]
KeyError: 'discarded'

### 5. 回归验证 (Verification)
修复后使用相同数据集与脚本进行回归验证，确保问题彻底消除且链路可用：

**运行命令：**
```powershell
python tests\smoke_mineru_debug_and_retrieve.py `
  "C:\Users\LI\Desktop\run\data\stored_files\电网运行规则.pdf" `
  "C:\Users\LI\Desktop\run\data\stored_files\GB20052-2020 电力变压器能效限定值及能效等级.pdf" `
  "C:\Users\LI\Desktop\run\data\stored_files\国网上海电力3-电网工程系统设计智能助手系统V1.0-电子证书.pdf" `
  "C:\Users\LI\Desktop\run\data\stored_files\1F13220202F49AA3701DF3E826373C9E.pdf"