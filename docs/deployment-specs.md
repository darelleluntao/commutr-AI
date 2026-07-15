# Commutr AI Agent — Deployment Specs

## Development machine (Apple Silicon)

| Component | Detail |
|---|---|
| Chip | Apple M5 Pro |
| Architecture | arm64 |
| CPU cores | 6 performance + 12 efficiency (18 total) |
| GPU | Integrated (Metal accelerated) |
| Unified memory | 24 GB |
| Storage | Internal SSD |
| OS | macOS (Darwin) |
| Inference backend | Ollama with Metal (GPU) acceleration |

### Supported models

| Model | Size | RAM needed | Speed (est.) | Status |
|---|---|---|---|---|
| qwen2.5:7b | 4.7 GB | ~6 GB | ~30-40 tok/s | Installed |
| qwen2.5:14b | ~9 GB | ~11 GB | ~15-25 tok/s | Pulling |
| qwen2.5:32b | ~19 GB | ~21 GB | ~8-12 tok/s | Pulling |
| llama3.2 | ~2 GB | ~3 GB | ~40+ tok/s | Not installed |

### Notes

- 24 GB unified memory is sufficient for qwen2.5:32b with ~3 GB headroom for OS/apps.
- Metal GPU acceleration gives 10-20x speedup vs CPU-only inference.
- Best experience: close memory-heavy apps (browser, IDE) before running 32B.
- For daily interactive use, qwen2.5:14b provides the best speed/smarts balance.

---

## VPS (Hostinger)

| Component | Detail |
|---|---|
| CPU | 4 vCPU (AMD EPYC 9354P 32-Core @ 2.0 GHz) |
| Architecture | x86_64 |
| GPU | None |
| RAM | 15 GB |
| Swap | 0 B |
| Storage | SSD |
| OS | Ubuntu 24.04 LTS |
| Inference backend | Ollama (CPU only) |

### Supported models

| Model | Size | RAM needed | Speed (est.) | Status |
|---|---|---|---|---|
| qwen2.5:7b | 4.7 GB | ~6 GB | ~3-6 tok/s | Not installed |
| qwen2.5:14b | ~9 GB | ~11 GB | ~1-3 tok/s | Not installed |
| qwen2.5:32b | ~19 GB | ~21 GB | Won't fit | N/A |

### Notes

- CPU-only inference — 10-20x slower than Apple Silicon with GPU.
- 15 GB RAM fits 7B comfortably, fits 14B with no swap margin.
- Best use: automated/background one-shot queries, scheduled reports.
- Not suitable for interactive chat due to latency.
- 32B won't fit — requires ~21 GB RAM, only 15 GB available.

---

## Inference comparison

| Metric | Mac M5 Pro | VPS (Hostinger) |
|---|---|---|
| qwen2.5:7b inference | 30-40 tok/s | 3-6 tok/s |
| qwen2.5:14b inference | 15-25 tok/s | 1-3 tok/s |
| qwen2.5:32b inference | 8-12 tok/s | N/A (OOM) |
| Interactive use | Yes | No |
| Batch/reports | Yes | Yes (slow) |
| Energy cost | Local, zero cloud | VPS electricity (minimal) |
| Data privacy | Fully local | VPS network |
