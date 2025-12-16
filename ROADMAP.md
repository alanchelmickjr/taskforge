# TaskForge Ecosystem Roadmap

> Three tools. One system. Capture work. Remember everything. Focus on what matters.

**Note**: The CLI command is `taskforge` (lowercase), but the project name is **TaskForge** (CamelCase).

## The Ecosystem

```
                           ┌────────────────────────────┐
                           │     PROJECT TRIAGE         │
                           │   (Command Center UI)      │
                           │                            │
                           │  "Pick 3 horses to ride"   │
                           │   Drop tasks, prioritize   │
                           │   Mobile + Desktop         │
                           └────────────┬───────────────┘
                                        │
                                        │ retrieves/stores
                                        ▼
                           ┌────────────────────────────┐
                           │       memoRable            │
                           │   (Salient Memory Hub)     │
                           │                            │
                           │  Energy-aware retrieval    │
                           │  Salience scoring          │
                           │  Cross-app memory          │
                           └────────────┬───────────────┘
                                        │
                                        │ stores playbooks
                                        ▲
                           ┌────────────┴───────────────┐
                           │       TASKFORGE            │
                           │   (Capture CLI)            │
                           │                            │
                           │  Video + Audio + Depth     │
                           │  Auto-generate playbooks   │
                           │  Jetson / Mobile support   │
                           └────────────────────────────┘
```

---

## Repository Map

| Repo | Purpose | Tech Stack | Status |
|------|---------|------------|--------|
| **taskforge** | Capture demonstrations → playbooks | Python, Click, OpenCV, Whisper | v0.1 |
| **memoRable** | Salient memory storage/retrieval | TypeScript, Node, OpenAI | Branch: `claude/memory-salience-system` |
| **project-triage-app** | UI for project prioritization | Next.js 14, React, Tailwind | v1.0 |

---

## Integration Architecture

### Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   TaskForge     │     │   memoRable     │     │ Project Triage  │
│                 │     │                 │     │                 │
│  Capture task   │────▶│  Store with     │◀────│  Fetch related  │
│  demo video     │     │  salience score │     │  playbooks      │
│                 │     │                 │     │                 │
│  Generate       │     │  5-factor score:│     │  Display in     │
│  playbook       │     │  - Emotional    │     │  Horse cards    │
│                 │     │  - Novelty      │     │                 │
│  Extract:       │     │  - Relevance    │     │  Merge scores:  │
│  - Tools used   │     │  - Social       │     │  Spirit + Sal.  │
│  - Parts list   │     │  - Consequential│     │                 │
│  - Time est.    │     │                 │     │  Energy-aware   │
│                 │     │  Energy-aware   │     │  suggestions    │
│                 │     │  retrieval      │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### API Contracts

**TaskForge → memoRable** (via HTTP)
```python
POST /api/salience/enrich
{
    "memoryId": "playbook-abc123",
    "text": "Task Playbook: Assemble Gripper v2\nTools: soldering iron, multimeter\n...",
    "userId": "user-hash",
    "context": {"detectedContext": "work_meeting"},
    "metadata": {
        "type": "taskforge_playbook",
        "playbook": {
            "title": "...",
            "tools_required": [...],
            "parts_required": [...],
            "estimated_time": "45 minutes"
        }
    }
}
```

**Project Triage → memoRable** (via HTTP)
```javascript
POST /api/salience/retrieve
{
    "query": "gripper assembly motor wiring",
    "userId": "user-hash",
    "filter": {"metadata.type": "taskforge_playbook"},
    "energyContext": {
        "timeOfDay": "morning",
        "currentEnergy": "high"  // or "low", "medium"
    },
    "limit": 5
}
```

---

## Energy-Aware Task Matching

### The Problem
Traditional task managers show all tasks equally. But a 2-hour deep-focus task doesn't belong in a 15-minute energy window.

### The Solution
Combine three scoring systems:

```
Final Score = (Spirit Score × 0.4) + (Salience Score × 0.3) + (Energy Match × 0.3)
```

| Factor | Source | What It Measures |
|--------|--------|------------------|
| **Spirit Score** | Project Triage | Impact, Effort, Revenue, Excitement |
| **Salience Score** | memoRable | Emotional weight, novelty, relevance |
| **Energy Match** | Time + Context | Does this task fit current energy? |

### Energy Match Algorithm

```typescript
function calculateEnergyMatch(task: Task, currentEnergy: EnergyLevel): number {
  const effortInverted = 10 - task.effort;  // Low effort = high score when tired

  const energyWeights = {
    high:   { effort: 0.2, complexity: 0.3, impact: 0.5 },  // Tackle hard stuff
    medium: { effort: 0.4, complexity: 0.3, impact: 0.3 },  // Balanced
    low:    { effort: 0.7, complexity: 0.1, impact: 0.2 },  // Quick wins only
  };

  const weights = energyWeights[currentEnergy];
  return (
    effortInverted * weights.effort +
    task.excitement * weights.complexity +  // Excitement proxy for engagement
    task.impact * weights.impact
  ) / 10;
}
```

### Time-of-Day Defaults

| Time Block | Default Energy | Task Types |
|------------|----------------|------------|
| 6am - 10am | High | Deep work, complex problems |
| 10am - 12pm | Medium-High | Meetings, collaboration |
| 12pm - 2pm | Low | Admin, light tasks |
| 2pm - 5pm | Medium | Balanced work |
| 5pm - 8pm | Low-Medium | Wrap-up, planning |

---

## Mobile / M4 Compatibility

### Project Triage (Primary UI)
- **Already mobile-ready**: Next.js + Tailwind responsive design
- **Enhancements needed**:
  - [ ] Touch-optimized drag-and-drop for buckets
  - [ ] PWA manifest for home screen install
  - [ ] Offline support via localStorage fallback
  - [ ] Larger touch targets (48px minimum)

### TaskForge on Mobile
- **Sensor-blind mode**: Works with any webcam (no depth camera needed)
- **Usage on mobile**:
  ```bash
  # On mobile device with Termux or similar
  taskforge capture "my task" --no-depth
  ```
- **Or use Project Triage web UI** to trigger remote TaskForge capture (future)

### memoRable
- **HTTP API**: Works from any platform
- **No mobile changes needed**: It's a backend service

### M4 (Apple Silicon) Specific
- All three projects are CPU/architecture agnostic:
  - TaskForge: Pure Python + optional PyTorch
  - memoRable: Node.js
  - Project Triage: Browser-based
- No special M4 handling required

---

## Implementation Roadmap

### Phase 1: Foundation (Current)
- [x] TaskForge core capture + playbook generation
- [x] TaskForge Jetson Orin Nano support
- [x] TaskForge sensor-blind mode (webcam)
- [x] TaskForge → memoRable integration
- [x] memoRable salience scoring system
- [x] Project Triage v1.0 (local storage)

### Phase 2: Integration Bridge (Next)
- [ ] **Project Triage → memoRable connection**
  - Add `httpx` or `fetch` calls to retrieve related playbooks
  - Display playbook suggestions on Horse cards
  - "View playbook" link to TaskForge output

- [ ] **Energy-aware retrieval in memoRable**
  - Add `energyContext` parameter to retrieve endpoint
  - Implement time-of-day energy defaults
  - Weight results by energy match

- [ ] **Project Triage mobile enhancements**
  - PWA manifest + service worker
  - Touch-optimized bucket drag-drop
  - Offline queue for changes

### Phase 3: AI Ranch Hand
- [ ] Claude integration in Project Triage
  - "What should I work on?" considers:
    - Spirit Scores (local)
    - Salience scores (from memoRable)
    - Related playbooks (from TaskForge history)
    - Current energy level (user input or time-based)

- [ ] Morning briefing via n8n
  - Pull top 3 energy-appropriate tasks
  - Include related playbooks
  - Push notification

### Phase 4: Full Loop
- [ ] **Project Triage → TaskForge trigger**
  - "Record how to do this" button on tasks
  - Opens TaskForge capture (desktop) or mobile recording flow

- [ ] **Playbook completion feedback**
  - Mark playbook as "used" in memoRable
  - Boost salience of successful playbooks
  - Learn from completion time vs estimates

- [ ] **Team features**
  - Share playbooks across team via memoRable
  - Team project boards in Project Triage
  - Gun.js P2P sync

---

## Quick Start: Running All Three

### 1. Start memoRable Salience Service
```bash
cd /path/to/memoRable
git checkout claude/memory-salience-system-kh8G7
npm install
npm run dev  # Runs on :3100
```

### 2. Start Project Triage
```bash
cd /path/to/project-triage-app
npm install
npm run dev  # Runs on :3000
```

### 3. Use TaskForge
```bash
cd /path/to/taskforge
pip install -e .

# Capture a task
taskforge capture "wiring motor controller"

# Process recording → playbook (auto-stores in memoRable)
taskforge process ./recordings/2024-12-16_wiring-motor-controller/

# Get briefing before starting new task
taskforge briefing "replacing servo motor"
```

### 4. View in Project Triage
- Open http://localhost:3000
- Add projects to your Rodeo Ring
- (Future) See related playbooks from TaskForge

---

## Environment Variables

```bash
# TaskForge + memoRable connection
export MEMORABLE_URL=http://localhost:3100
export MEMORABLE_USER_ID=your-user-id  # Optional, auto-generated

# TaskForge AI
export ANTHROPIC_API_KEY=sk-ant-...

# Project Triage (future Claude integration)
export ANTHROPIC_API_KEY=sk-ant-...
```

---

## Success Metrics

| Milestone | Criteria |
|-----------|----------|
| **Integration v1** | TaskForge playbooks appear in Project Triage |
| **Energy-Aware v1** | Suggestions change based on time of day |
| **Mobile v1** | Project Triage installable as PWA, touch-friendly |
| **Full Loop v1** | Can record → store → retrieve → re-use a playbook |

---

## Contributing

Each repo accepts PRs:
- **taskforge**: Python, focus on capture + processing
- **memoRable**: TypeScript, focus on salience algorithms
- **project-triage-app**: React/Next.js, focus on UX

Branch naming: `claude/{feature-name}` or `feature/{your-name}/{description}`

---

*"Capture work. Remember everything. Focus on what matters."*
