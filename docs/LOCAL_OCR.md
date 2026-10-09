# 本地 CPU OCR

启动器通过 `backend/.env.ocr` 加载 PaddleOCR，扫描 PDF 和不可读文本层按现有策略回退识别。与 LLM、BGE 分别配置。

## 首次准备

在 Windows Python 3.12 的项目环境中执行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-ocr-local.txt
.\.venv\Scripts\python.exe scripts/download-ocr-models.py
.\.venv\Scripts\python.exe scripts/configure-local-ocr.py
.\.venv\Scripts\python.exe scripts/verify-local-ocr.py
```

固定 PaddlePaddle/PaddleOCR 3.2.0、PaddleX 3.2.1、PyMuPDF 1.24.14、NumPy 1.26.4，使用 CPU，无需 CUDA。

脚本固定官方 [检测模型](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_det) 和 [识别模型](https://huggingface.co/PaddlePaddle/PP-OCRv5_mobile_rec) 的 revision，校验权重 SHA-256、配置 Git blob SHA-1，记录清单。目录为 `data/models/ocr/paddleocr/PP-OCRv5_mobile_det/` 和 `PP-OCRv5_mobile_rec/`。

配置脚本仅新建 `.env.ocr`，已有文件保留并提示检查，不改写原 `.env`。模型校验通过时复用，不匹配时保留并报错，日常无需下载。

## 默认行为与验证

默认不启用方向分类、文档旋转和矫正。复杂表格、低清晰度或旋转扫描件需要单独验收，不能用合成样例推算业务准确率。

验证脚本生成无文本层的合成 PDF，检查探测、策略、OCR、来源页码与切块，不调用外部 LLM。报告和样例在忽略的 `.runtime_reports/`、`.codex_smoke/`。

Windows 下已复现 Torch/Paddle 加载顺序导致 `torch/lib/shm.dll` WinError 127。项目统一先加载 Torch 原生库再加载 Paddle，预加载不读取模型权重；它不是所有 DLL 错误的通用修复，依赖仍须匹配。

检索配置见 [LOCAL_RAG.md](LOCAL_RAG.md)，生成模型开关见 [LOCAL_LLM.md](LOCAL_LLM.md)。
