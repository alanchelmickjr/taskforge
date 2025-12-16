# TaskForge

> Watch me work. Write the manual.

A CLI tool that captures you doing a task (video + audio + depth) and outputs a structured playbook anyone can follow.

## Supported Hardware

### Cameras

| Camera | SDK | Depth Range | Notes |
|--------|-----|-------------|-------|
| OAK-D S2 | DepthAI | 0.2m - 15m | Good all-rounder |
| OAK-D Pro W | DepthAI | 0.2m - 15m | IR dot projector, works in dark |
| RealSense D455 | librealsense | 0.4m - 6m | Wide FOV, good for benchtop |

### Compute Platforms

| Platform | RAM | Status | Notes |
|----------|-----|--------|-------|
| Desktop/Laptop | 16GB+ | Full support | All features, larger Whisper models |
| **Jetson Orin Nano** | 8GB | Supported | Auto-tuned for shared memory |
| Jetson Orin NX | 8-16GB | Supported | Better headroom for processing |
| Jetson AGX Orin | 32-64GB | Supported | Full desktop performance |

## Install

### Desktop / Standard Linux

```bash
git clone https://github.com/alanchelmickjr/taskforge.git
cd taskforge
pip install -e .
```

### NVIDIA Jetson (Orin Nano / NX / AGX)

Jetson requires special handling because it uses shared CPU/GPU memory and ARM64 architecture.

```bash
# 1. Ensure you're running JetPack 5.x or 6.x
cat /etc/nv_tegra_release

# 2. Clone the repo
git clone https://github.com/alanchelmickjr/taskforge.git
cd taskforge

# 3. Install base dependencies (uses JetPack's OpenCV, not PyPI)
pip install click numpy anthropic

# 4. Install audio support
pip install sounddevice soundfile

# 5. Install PyTorch for Jetson (required for Whisper)
# Check https://forums.developer.nvidia.com/t/pytorch-for-jetson/ for latest
# Example for JetPack 5.x:
pip install --no-cache https://developer.download.nvidia.com/compute/redist/jp/v51/pytorch/torch-2.0.0+nv23.05-cp38-cp38-linux_aarch64.whl

# 6. Install Whisper
pip install openai-whisper

# 7. Install TaskForge (without pulling opencv-python)
pip install -e . --no-deps
pip install click numpy anthropic  # Reinstall deps without opencv

# 8. For OAK-D cameras on Jetson:
# See https://docs.luxonis.com/en/latest/pages/tutorials/first_steps/#jetson

# 9. For RealSense on Jetson:
# See https://github.com/IntelRealSense/librealsense/blob/master/doc/installation_jetson.md

# 10. Verify platform detection
taskforge platform
```

**Important Jetson Notes:**
- Do NOT install `opencv-python` from PyPI - it conflicts with JetPack's OpenCV
- TaskForge auto-detects Jetson and adjusts memory usage accordingly
- Default Whisper model on 8GB Jetson is `tiny` (use `--whisper-model base` if you have headroom)
- Video compilation is chunked to avoid OOM on long recordings

## Usage

```bash
# Check platform detection (helpful on Jetson)
taskforge platform

# Start capture session
taskforge capture "assembling gripper v2"

# Process existing recording
taskforge process ./recordings/2024-12-12_assembling-gripper-v2/

# Process with specific Whisper model (desktop with more RAM)
taskforge process ./recordings/... --whisper-model small

# List available cameras
taskforge devices

# Configure default camera
taskforge config --camera oak-d-pro

# Get a briefing before starting a new task (requires memoRable)
taskforge briefing "replacing servo motor"

# Search past playbooks by topic
taskforge recall "gripper assembly"
```

## Memory Integration (memoRable)

TaskForge integrates with [memoRable](https://github.com/alanchelmickjr/memoRable) for intelligent playbook storage and retrieval using salient memory.

### Features

- **Automatic storage**: Playbooks are stored with salience scores based on emotional impact, novelty, relevance, and more
- **Smart retrieval**: Find related playbooks by topic, tools, or parts
- **Pre-task briefings**: Get relevant context before starting a new task
- **Energy-aware surfacing**: Context-aware retrieval considers time of day and task complexity

### Setup

```bash
# Install memory dependencies
pip install httpx

# Set environment variables (optional - defaults to localhost:3100)
export MEMORABLE_URL=http://localhost:3100
export MEMORABLE_USER_ID=your-user-id  # Auto-generated if not set

# Start memoRable service (see memoRable docs)
docker-compose up -d
```

### Usage

```bash
# Before starting a task, get a briefing
taskforge briefing "wiring the motor controller"
# Output: Related playbooks, suggested tools, parts commonly used

# Search your playbook history
taskforge recall "servo calibration"
# Output: Past playbooks ranked by salience score
```

Playbooks are automatically stored in memory when processed - no extra steps needed.

## Output

```
playbooks/
└── assembling-gripper-v2/
    ├── README.md           # The playbook
    ├── steps/
    │   ├── 01-gather-parts.md
    │   ├── 02-attach-motor.md
    │   └── 03-wire-connections.md
    └── assets/
        ├── frame_001_parts-layout.jpg
        ├── frame_002_motor-position.jpg
        ├── depth_002_motor-position.png
        └── full-recording.mp4 (optional)
```

## Philosophy

- **Capture first, structure later** — Don't stop to document
- **Voice is the interface** — Narrate while you work
- **Depth adds precision** — "3cm from edge" not "roughly here"
- **Git-native output** — Playbooks are markdown, diffable, forkable

## License

MIT — Fork it, ship it, teach robots.
