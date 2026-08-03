# OCR/VLM 感知 Sidecar

这是天线设计信息 MCP 的独立感知服务。它不属于 HFSS MCP，也不要求 MCP 进程安装 CUDA、PyTorch 或具体模型 SDK。

## 启动

```powershell
$env:PERCEPTION_HOST = "127.0.0.1"
$env:PERCEPTION_PORT = "8020"
python -m antenna_perception_sidecar
```

未配置模型时使用 `DemoEngine`，用于验证 sidecar 和 MCP 的完整通信链路。

## 配置真实模型

通过独立 Python 模块提供 `create_engine()`：

```powershell
$env:PERCEPTION_PLUGIN_PATH = "D:\AntennaModels\plugins"
$env:PERCEPTION_OCR_ENGINE_MODULE = "my_ocr_plugin:create_engine"
$env:PERCEPTION_VLM_ENGINE_MODULE = "my_vlm_plugin:create_engine"
```

返回的 engine 必须提供：

```python
engine_id: str
engine_version: str
capabilities: list[str]
extract(input_digest: str, suffix: str, content: bytes) -> list[dict]
```

OCR/VLM 插件可以使用自己的 Python、CUDA、PyTorch、ONNX Runtime 或 TensorRT。MCP 只通过 HTTP/JSON 与 sidecar 通信。
