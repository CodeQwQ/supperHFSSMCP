# Ollama VLM Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a dependency-free HTTP Ollama VLM adapter to the perception sidecar, expose configuration in the offline bundle, and verify MCP-to-sidecar-to-Ollama behavior.

**Architecture:** The sidecar loads an `ollama_vlm_plugin:create_engine` plugin. The plugin sends image bytes as base64 to Ollama `/api/chat`, parses strict JSON, and emits existing evidence records. MCP remains unaware of Ollama, CUDA, and model libraries.

**Tech Stack:** Python 3.12 bundled runtime, standard-library `urllib`, Ollama HTTP API, pytest, PowerShell offline packaging scripts.

---

### Task 1: Add failing provider tests

**Files:**
- Create: `perception-sidecar/tests/test_ollama_vlm_plugin.py`

- [x] **Step 1: Write tests for successful image extraction and non-image handling.**
- [x] **Step 2: Run the tests and confirm they fail because the plugin is missing.**

Run: `python -m pytest perception-sidecar/tests/test_ollama_vlm_plugin.py -q`
Expected: import failure for `ollama_vlm_plugin`.

### Task 2: Implement the Ollama HTTP plugin

**Files:**
- Create: `perception-sidecar/plugins/ollama_vlm_plugin.py`

- [x] **Step 1: Implement configurable endpoint/model/timeout using only the standard library.**
- [x] **Step 2: Parse strict JSON from Ollama and return evidence records.**
- [x] **Step 3: Return an explicit manual-review evidence record for PDF input.**
- [x] **Step 4: Run provider tests and confirm they pass.**

### Task 3: Wire configuration and documentation

**Files:**
- Modify: `dist-offline/antenna-design-intelligence-mcp-offline-win-x64/config.example.ps1`
- Modify: `dist-offline/antenna-design-intelligence-mcp-offline-win-x64/README-OFFLINE.md`
- Modify: `docs/antenna-intelligence-offline-deployment.md`

- [x] **Step 1: Add Ollama endpoint/model/timeout variables and plugin module example.**
- [x] **Step 2: Document Windows 11 VM networking and image smoke test.**

### Task 4: Verify and rebuild

**Files:**
- Modify: `dist-offline/antenna-design-intelligence-mcp-offline-win-x64/app/perception/...` via packaging script output.

- [x] **Step 1: Run sidecar and MCP unit tests.**
- [x] **Step 2: Run a local fake Ollama HTTP server smoke test.**
- [x] **Step 3: Rebuild the offline ZIP and calculate SHA256.**
- [x] **Step 4: Verify the rebuilt package contains the plugin and starts both services.**
