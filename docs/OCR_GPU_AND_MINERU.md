# OCR GPU 与 MinerU 评估

## PaddleOCR GPU 切换

当前项目通过 `PADDLEOCR_DEVICE` 控制 PaddleOCR 推理设备：

```env
PADDLEOCR_DEVICE=cpu
```

安装 GPU 版 PaddlePaddle 并验证成功后，可改为：

```env
PADDLEOCR_DEVICE=gpu:0
```

你的环境当前是 Python 3.11，显卡是 RTX 5070 Ti，NVIDIA 驱动版本 591.86。官方文档说明 Windows 上 50 系显卡可能需要专门适配 wheel；如果普通 `cu126` wheel 验证失败，应优先尝试 50 系专用 wheel。

## 推荐安装顺序

先在 `rag-agent` 环境里卸载 CPU 版：

```powershell
conda activate rag-agent
python -m pip uninstall -y paddlepaddle paddlepaddle-gpu
```

普通 CUDA 12.6 wheel：

```powershell
python -m pip install paddlepaddle-gpu==3.2.2 -i https://www.paddlepaddle.org.cn/packages/stable/cu126/
python -m pip install -U paddleocr
```

验证：

```powershell
python -c "import paddle; print(paddle.__version__); print(paddle.device.is_compiled_with_cuda()); print(paddle.device.get_device()); paddle.utils.run_check()"
```

如果出现 `Mismatched GPU Architecture` / `Unsupported GPU architecture`，说明普通 `cu126` wheel 不包含 RTX 50 系 `sm_120` 内核。此时卸载后安装 PaddleOCR 官方文档中的 50 系 Python 3.11 专用 wheel：

```powershell
python -m pip uninstall -y paddlepaddle paddlepaddle-gpu
python -m pip install https://paddle-qa.bj.bcebos.com/paddle-pipeline/Develop-TagBuild-Training-Windows-Gpu-Cuda12.9-Cudnn9.9-Trt10.5-Mkl-Avx-VS2019-SelfBuiltPypiUse/86d658f56ebf3a5a7b2b33ace48f22d10680d311/paddlepaddle_gpu-3.0.0.dev20250717-cp311-cp311-win_amd64.whl
python -m pip install -U paddleocr
```

验证通过后再把 `.env` 改成：

```env
PADDLEOCR_DEVICE=gpu:0
PADDLEOCR_USE_SUBPROCESS=true
```

Windows 下建议保持 `PADDLEOCR_USE_SUBPROCESS=true`。当前项目的 Embedding/Reranker 使用 PyTorch，而 PaddleOCR GPU 使用 PaddlePaddle。两套 GPU 运行时在同一个 Python 进程里容易出现 cuDNN DLL 冲突，所以项目默认把 PaddleOCR 放到独立子进程执行，主后端进程只接收 OCR JSON 结果。

## MinerU 初步判断

MinerU 是 OpenDataLab 开源的文档解析工具，目标是把 PDF、图片、DOCX、PPTX、XLSX 转成 Markdown/JSON，适合给 RAG 和 Agent 工作流使用。它内置版面分析、OCR、公式识别、表格识别、阅读顺序恢复、可视化结果等能力。

适合本项目的点：

- 对复杂 PDF、表格、扫描件、版面顺序的支持比单独 PaddleOCR 更完整。
- 输出 Markdown/JSON，更接近当前 RAG 入库需要的结构化中间结果。
- 支持 CPU、GPU、NPU、MPS，也支持 CLI、FastAPI、Gradio。

需要注意：

- 依赖更重，部署复杂度明显高于 PaddleOCR。
- 对你的食品国标这类表格型 PDF，最终效果需要用 5-10 个样本文档实测。
- License 不是纯 Apache 2.0，而是基于 Apache 2.0 的 MinerU Open Source License，带商业阈值和在线服务署名要求。
- 不建议马上替换主流程。更稳妥做法是把 MinerU 作为第二个解析工具接入 Agent：PaddleOCR 保留为轻量 fallback，MinerU 用于复杂表格/扫描 PDF。
