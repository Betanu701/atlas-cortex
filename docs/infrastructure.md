# Atlas Cortex — Infrastructure

## Server Topology

```
┌──────────────────────────────────────────────────────────────────┐
│                        Home Network                               │
│                                                                    │
│  192.168.1.x — Main LAN                                          │
│    .3  NGINX Proxy Manager (Proxmox LXC 101)                     │
│    .5  MariaDB                                                    │
│    .6  Nextcloud                                                  │
│    .8  HIVE (Unraid — primary NAS)                               │
│    .12 AdGuard Home (Proxmox LXC 100)                            │
│                                                                    │
│  192.168.3.x — Compute                                            │
│    .8  Overwatch (Unraid — LLM server) ◀── Atlas Cortex lives here│
│                                                                    │
│  192.168.4.x — Management                                         │
│    .8  Observer (Proxmox — hypervisor)                            │
│         └── VM 103: Home Assistant OS                             │
└──────────────────────────────────────────────────────────────────┘
```

## Overwatch (192.168.3.8) — Container Stack

| Container | Image | Port | GPU | Status |
|-----------|-------|------|-----|--------|
| `ollama` | ollama/ollama:rocm | 11434 | RX 7900 XT | ✅ Running |
| `open-webui` | ghcr.io/open-webui/open-webui:main | 8080 | — | ✅ Running |
| `searxng` | searxng/searxng | 8888 | — | ✅ Running |
| `faster-whisper` | faster-whisper | 10300 | — | ✅ Running |
| `piper` | piper | 10200 | — | ✅ Running |
| `atlas-evolution` | *custom* (Python + cron) | — | — | 🔲 Phase C2 |
| `atlas-speaker-id` | *custom* (resemblyzer) | 8890 | — | 🔲 Phase C3 |

## Hardware: Overwatch

| Component | Spec |
|-----------|------|
| CPU | AMD Ryzen 7 5700G (8c/16t, 3.8GHz) |
| RAM | 128GB DDR4 |
| GPU (discrete) | AMD Radeon RX 7900 XT (20GB GDDR6, RDNA3) |
| GPU (integrated) | AMD Cezanne iGPU (not used) |
| Storage | 450GB cache + 7.4TB fast pool + NVMe boot |
| OS | Unraid 7.1.4 |

## Models on Ollama

| Model | Size | Speed | Used By |
|-------|------|-------|---------|
| `qwen3:30b-a3b` | 18.6GB | 75 tok/s | Atlas, Atlas Deep Thought |
| `huihui_ai/qwen2.5-abliterate:14b` | 9.0GB | 55 tok/s | Atlas Turbo |
| `qwen3-nothink:30b-a3b` | 18.6GB | 75 tok/s | *(deprecated, can delete)* |

**After Cortex deployment:**
- Atlas Turbo / Atlas / Atlas Deep Thought → replaced by Atlas Cortex
- Cortex auto-selects between qwen2.5 (fast) and qwen3 (thinking) internally

## Open WebUI Custom Models (current)

| Model | Base | Temperature | Context | Role |
|-------|------|-------------|---------|------|
| Atlas Turbo | qwen2.5-abliterate:14b | 0.7 | 8K | Quick answers (default) |
| Atlas | qwen3:30b-a3b | 0.2 | 8K | Complex questions |
| Atlas Deep Thought | qwen3:30b-a3b | 0.6 | 8K | Hard reasoning |

**After Cortex:** Single "Atlas Cortex" model replaces all three.

## Open WebUI Tools (7 custom + built-in)

| Tool | ID | Function |
|------|----|----------|
| DateTime | datetime | Current date/time (fixes "thinks it's 2023") |
| Calculator | calculator | Math with trig, stats |
| Web Scraper | web_scraper | Fetch and extract URL text |
| YouTube Transcriber | youtube_transcript | Extract video captions |
| Run Python Code | run_code | Execute Python in sandbox |
| Home Assistant | home_assistant | Control smart home (needs HA token) |
| Memory Manager | memory_manager | Persistent user memory |

## DNS & Proxy

| Domain | Target |
|--------|--------|
| chat.digitalbrainstem.com | Open WebUI (192.168.3.8:8080) via NGINX |

## Access

| Service | Auth |
|---------|------|
| SSH (all servers) | Key: `~/.ssh/unraid_hive_key` (ed25519) |
| Open WebUI | admin@example.com (see private credentials) (see private credentials store) |
| NPM | admin@example.com (see private credentials) (Proxmox LXC) |
| AdGuard | Admin account (Proxmox LXC) |
| Home Assistant | VM on Proxmox (needs long-lived access token for Cortex) |
