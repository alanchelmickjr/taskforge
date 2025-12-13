# TaskForge 🎥→📋

> Watch me work. Write the manual.

A CLI tool that captures you doing a task (video + audio + depth) and outputs a structured playbook anyone can follow.

## Supported Hardware

| Camera | SDK | Depth Range | Notes |
|--------|-----|-------------|-------|
| OAK-D S2 | DepthAI | 0.2m - 15m | Good all-rounder |
| OAK-D Pro W | DepthAI | 0.2m - 15m | IR dot projector, works in dark |
| RealSense D455 | librealsense | 0.4m - 6m | Wide FOV, good for benchtop |

## Install

```bash
git clone https://github.com/alanchelmickjr/taskforge.git
cd taskforge
pip install -e .
```

## Usage

```bash
# Start capture session
taskforge capture "assembling gripper v2"

# Process existing recording
taskforge process ./recordings/2024-12-12_assembling-gripper-v2/

# List available cameras
taskforge devices

# Configure default camera
taskforge config --camera oak-d-pro
```

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
