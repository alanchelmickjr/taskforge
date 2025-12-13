"""
TaskForge Processor

Takes a capture session and produces a structured playbook.

Pipeline:
1. Transcribe audio (Whisper)
2. Extract keyframes
3. Correlate speech to frames
4. Send to LLM for structuring
5. Output markdown playbook

Optimized for memory-constrained devices like NVIDIA Jetson Orin Nano.
"""

import os
import gc
import json
import base64
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional, Tuple
import cv2

from .platform import detect_platform, is_memory_constrained


@dataclass
class TranscriptSegment:
    """A segment of transcribed speech"""
    start: float      # Seconds from start
    end: float
    text: str


@dataclass
class PlaybookStep:
    """A single step in the playbook"""
    number: int
    title: str
    description: str
    details: List[str]
    warnings: List[str]
    frame_refs: List[str]  # Paths to associated images
    depth_info: Optional[str] = None  # Spatial details from depth data
    time_range: Optional[Tuple[float, float]] = None


@dataclass
class Playbook:
    """Complete playbook output"""
    title: str
    summary: str
    prerequisites: List[str]
    tools_required: List[str]
    parts_required: List[str]
    estimated_time: str
    steps: List[PlaybookStep]
    tips: List[str]


class WhisperTranscriber:
    """Transcribe audio using OpenAI Whisper"""

    # Model memory requirements (approximate)
    MODEL_MEMORY_GB = {
        'tiny': 1.0,
        'base': 1.5,
        'small': 2.5,
        'medium': 5.0,
        'large': 10.0,
    }

    def __init__(self, model_size: str = None):
        """
        model_size: tiny, base, small, medium, large
                   If None, auto-selects based on available memory.

        On Jetson Orin Nano (8GB shared RAM), defaults to 'tiny'.
        Recommend 'base' for speed on desktop, 'small' for accuracy.
        """
        if model_size is None:
            model_size = detect_platform().recommended_whisper_model
        self.model_size = model_size
        self._model = None

    def _load_model(self):
        if self._model is None:
            import whisper

            platform_info = detect_platform()

            # Warn if model might not fit in memory
            required_mem = self.MODEL_MEMORY_GB.get(self.model_size, 2.0)
            available_mem = platform_info.total_memory_gb

            if platform_info.is_jetson:
                # Jetson shares RAM with GPU, so be more conservative
                available_mem *= 0.5  # Assume ~50% available for Whisper

            if required_mem > available_mem:
                print(f"   ⚠️  Warning: {self.model_size} model needs ~{required_mem:.1f}GB, "
                      f"but only ~{available_mem:.1f}GB available")
                print(f"   Consider using a smaller model (tiny, base)")

            print(f"Loading Whisper model: {self.model_size}")

            # On Jetson, explicitly use CUDA if available
            if platform_info.is_jetson and platform_info.cuda_available:
                self._model = whisper.load_model(self.model_size, device="cuda")
            else:
                self._model = whisper.load_model(self.model_size)

        return self._model
    
    def transcribe(self, audio_path: Path) -> List[TranscriptSegment]:
        """Transcribe audio file to timestamped segments"""
        model = self._load_model()

        print(f"Transcribing: {audio_path}")
        result = model.transcribe(
            str(audio_path),
            language="en",
            word_timestamps=True,
            verbose=False
        )

        segments = []
        for seg in result['segments']:
            segments.append(TranscriptSegment(
                start=seg['start'],
                end=seg['end'],
                text=seg['text'].strip()
            ))

        print(f"Transcribed {len(segments)} segments")

        # On memory-constrained devices, unload model after use
        if is_memory_constrained():
            self.unload()

        return segments

    def unload(self):
        """Unload model to free memory"""
        if self._model is not None:
            del self._model
            self._model = None
            gc.collect()

            # Try to free CUDA memory if available
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except:
                pass


class FrameAnalyzer:
    """Analyze frames for key information"""
    
    def __init__(self):
        pass
    
    def select_keyframes(
        self,
        frames_metadata: List[dict],
        max_frames: int = 20
    ) -> List[dict]:
        """
        Select most important frames for the playbook.
        Prioritizes: scene changes, even distribution, first/last
        """
        keyframes = [f for f in frames_metadata if f.get('is_keyframe', False)]
        
        if len(keyframes) <= max_frames:
            return keyframes
        
        # Evenly sample if too many
        step = len(keyframes) // max_frames
        selected = keyframes[::step][:max_frames]
        
        # Ensure first and last are included
        if keyframes[0] not in selected:
            selected[0] = keyframes[0]
        if keyframes[-1] not in selected:
            selected[-1] = keyframes[-1]
        
        return selected
    
    def get_depth_description(
        self,
        depth_path: Path,
        rgb_path: Path
    ) -> Optional[str]:
        """
        Extract spatial information from depth data.
        Returns human-readable description.
        """
        import numpy as np
        
        if not depth_path.exists():
            return None
        
        depth = np.load(depth_path)
        
        # Basic stats
        valid_depth = depth[depth > 0]
        if len(valid_depth) == 0:
            return None
        
        min_d = float(np.min(valid_depth))
        max_d = float(np.max(valid_depth))
        mean_d = float(np.mean(valid_depth))
        
        # Find closest object (likely the focus)
        h, w = depth.shape
        center_region = depth[h//3:2*h//3, w//3:2*w//3]
        center_valid = center_region[center_region > 0]
        
        if len(center_valid) > 0:
            focus_distance = float(np.median(center_valid))
            return f"Working distance: ~{focus_distance*100:.0f}cm from camera"
        
        return f"Scene depth: {min_d*100:.0f}cm to {max_d*100:.0f}cm"


class PlaybookGenerator:
    """Generate structured playbook using LLM"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        Uses Anthropic Claude by default.
        Set ANTHROPIC_API_KEY env var or pass api_key.
        """
        self.api_key = api_key or os.environ.get('ANTHROPIC_API_KEY')
        
    def generate(
        self,
        task_name: str,
        transcript: List[TranscriptSegment],
        keyframes: List[dict],
        frames_dir: Path,
        depth_descriptions: List[Optional[str]]
    ) -> Playbook:
        """Generate playbook from transcript and frames"""
        
        from anthropic import Anthropic
        
        client = Anthropic(api_key=self.api_key)
        
        # Prepare transcript text
        transcript_text = "\n".join([
            f"[{seg.start:.1f}s - {seg.end:.1f}s]: {seg.text}"
            for seg in transcript
        ])
        
        # Prepare frame descriptions with depth
        frame_descriptions = []
        for i, (frame, depth_desc) in enumerate(zip(keyframes, depth_descriptions)):
            desc = f"Frame {i+1} at {frame['relative_time']:.1f}s"
            if depth_desc:
                desc += f" ({depth_desc})"
            frame_descriptions.append(desc)
        
        # Encode keyframe images for vision
        # On memory-constrained devices, use smaller images and fewer frames
        if is_memory_constrained():
            max_images = 6
            img_size = (480, 270)
            jpeg_quality = 70
        else:
            max_images = 10
            img_size = (640, 360)
            jpeg_quality = 80

        images = []
        for frame in keyframes[:max_images]:
            img_path = frames_dir / frame['rgb_file']
            if img_path.exists():
                img = cv2.imread(str(img_path))
                img = cv2.resize(img, img_size)
                _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
                b64 = base64.b64encode(buffer).decode('utf-8')
                images.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64
                    }
                })
                del img, buffer  # Free memory immediately

        if is_memory_constrained():
            gc.collect()
        
        # Build prompt
        prompt = f"""You are creating a step-by-step playbook from a recorded task demonstration.

TASK: {task_name}

TRANSCRIPT (timestamped narration):
{transcript_text}

KEYFRAME TIMESTAMPS:
{chr(10).join(frame_descriptions)}

Based on the transcript, keyframes, and your analysis of the images, create a detailed playbook.

Output as JSON with this structure:
{{
  "title": "How to {task_name}",
  "summary": "Brief 1-2 sentence overview",
  "prerequisites": ["list of required knowledge/setup"],
  "tools_required": ["specific tools mentioned or visible"],
  "parts_required": ["components/materials needed"],
  "estimated_time": "X minutes",
  "steps": [
    {{
      "number": 1,
      "title": "Step title",
      "description": "What to do",
      "details": ["Specific sub-steps or clarifications"],
      "warnings": ["Safety notes or common mistakes"],
      "frame_refs": [1, 3],  // Which keyframes show this step
      "time_range": [0.0, 30.0]  // Seconds in recording
    }}
  ],
  "tips": ["Pro tips or efficiency suggestions"]
}}

Be specific. Extract exact details from the narration. Reference frame numbers that correspond to each step."""

        # Call Claude with vision
        content = images + [{"type": "text", "text": prompt}]
        
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=4096,
            messages=[{"role": "user", "content": content}]
        )
        
        # Parse response
        response_text = response.content[0].text
        
        # Extract JSON from response
        import re
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            data = json.loads(json_match.group())
        else:
            raise ValueError("Could not parse playbook JSON from response")
        
        # Convert to Playbook object
        steps = []
        for s in data.get('steps', []):
            steps.append(PlaybookStep(
                number=s['number'],
                title=s['title'],
                description=s['description'],
                details=s.get('details', []),
                warnings=s.get('warnings', []),
                frame_refs=[keyframes[i-1]['rgb_file'] for i in s.get('frame_refs', []) if i <= len(keyframes)],
                time_range=tuple(s['time_range']) if s.get('time_range') else None
            ))
        
        return Playbook(
            title=data.get('title', f"How to {task_name}"),
            summary=data.get('summary', ''),
            prerequisites=data.get('prerequisites', []),
            tools_required=data.get('tools_required', []),
            parts_required=data.get('parts_required', []),
            estimated_time=data.get('estimated_time', 'Unknown'),
            steps=steps,
            tips=data.get('tips', [])
        )


class MarkdownWriter:
    """Write playbook to markdown files"""
    
    def write(self, playbook: Playbook, output_dir: Path, assets_dir: Path):
        """Write playbook as markdown with linked assets"""
        
        output_dir.mkdir(parents=True, exist_ok=True)
        steps_dir = output_dir / "steps"
        steps_dir.mkdir(exist_ok=True)
        
        # Main README
        readme = f"""# {playbook.title}

{playbook.summary}

**Estimated Time:** {playbook.estimated_time}

## Prerequisites

{self._list(playbook.prerequisites)}

## Tools Required

{self._list(playbook.tools_required)}

## Parts Required

{self._list(playbook.parts_required)}

## Steps

"""
        for step in playbook.steps:
            readme += f"{step.number}. [{step.title}](steps/{step.number:02d}-{self._slug(step.title)}.md)\n"
        
        readme += f"""
## Tips

{self._list(playbook.tips)}

---
*Generated by TaskForge*
"""
        
        with open(output_dir / "README.md", 'w') as f:
            f.write(readme)
        
        # Individual step files
        for step in playbook.steps:
            step_content = f"""# Step {step.number}: {step.title}

{step.description}

"""
            if step.details:
                step_content += "## Details\n\n"
                step_content += self._list(step.details) + "\n"
            
            if step.warnings:
                step_content += "## ⚠️ Warnings\n\n"
                step_content += self._list(step.warnings) + "\n"
            
            if step.frame_refs:
                step_content += "## Reference Images\n\n"
                for ref in step.frame_refs:
                    step_content += f"![{step.title}](../assets/{ref})\n\n"
            
            if step.depth_info:
                step_content += f"\n**Spatial Note:** {step.depth_info}\n"
            
            step_content += f"\n---\n"
            if step.number > 1:
                prev = playbook.steps[step.number - 2]
                step_content += f"← [Previous: {prev.title}]({step.number-1:02d}-{self._slug(prev.title)}.md) | "
            if step.number < len(playbook.steps):
                next_step = playbook.steps[step.number]
                step_content += f"[Next: {next_step.title}]({step.number+1:02d}-{self._slug(next_step.title)}.md) →"
            
            filename = f"{step.number:02d}-{self._slug(step.title)}.md"
            with open(steps_dir / filename, 'w') as f:
                f.write(step_content)
        
        # Copy referenced assets
        assets_out = output_dir / "assets"
        assets_out.mkdir(exist_ok=True)
        
        for step in playbook.steps:
            for ref in step.frame_refs:
                src = assets_dir / ref
                if src.exists():
                    import shutil
                    shutil.copy(src, assets_out / ref)
        
        print(f"✅ Playbook written to {output_dir}")
    
    def _list(self, items: List[str]) -> str:
        if not items:
            return "*None specified*\n"
        return "\n".join(f"- {item}" for item in items) + "\n"
    
    def _slug(self, text: str) -> str:
        return text.lower().replace(" ", "-").replace("/", "-")[:30]


class TaskProcessor:
    """
    Main processor orchestrator.
    
    Usage:
        processor = TaskProcessor("./recordings/2024-12-12_assembling-gripper/")
        playbook = processor.process()
        # Output is in ./playbooks/assembling-gripper/
    """
    
    def __init__(
        self,
        recording_dir: Path,
        output_base: Path = Path("./playbooks"),
        whisper_model: str = "base"
    ):
        self.recording_dir = Path(recording_dir)
        self.output_base = output_base
        
        # Load metadata
        with open(self.recording_dir / "metadata.json") as f:
            self.metadata = json.load(f)
        
        self.task_name = self.metadata['session']['name']
        
        # Components
        self.transcriber = WhisperTranscriber(whisper_model)
        self.frame_analyzer = FrameAnalyzer()
        self.generator = PlaybookGenerator()
        self.writer = MarkdownWriter()
        
    def process(self) -> Playbook:
        """Run full processing pipeline"""
        print(f"🔧 Processing: {self.task_name}")
        
        # 1. Transcribe audio
        audio_path = self.recording_dir / "audio.wav"
        if audio_path.exists():
            transcript = self.transcriber.transcribe(audio_path)
        else:
            print("   ⚠️ No audio found, proceeding without transcript")
            transcript = []
        
        # 2. Select keyframes
        keyframes = self.frame_analyzer.select_keyframes(
            self.metadata['frames'],
            max_frames=20
        )
        print(f"   Selected {len(keyframes)} keyframes")
        
        # 3. Get depth descriptions
        depth_descriptions = []
        for frame in keyframes:
            depth_path = self.recording_dir / "depth" / f"{frame['rgb_file'].replace('.jpg', '.npy')}"
            rgb_path = self.recording_dir / "frames" / frame['rgb_file']
            desc = self.frame_analyzer.get_depth_description(depth_path, rgb_path)
            depth_descriptions.append(desc)
        
        # 4. Generate playbook via LLM
        playbook = self.generator.generate(
            task_name=self.task_name,
            transcript=transcript,
            keyframes=keyframes,
            frames_dir=self.recording_dir / "frames",
            depth_descriptions=depth_descriptions
        )
        
        # 5. Write output
        safe_name = self.task_name.lower().replace(" ", "-")[:50]
        output_dir = self.output_base / safe_name
        self.writer.write(
            playbook,
            output_dir,
            assets_dir=self.recording_dir / "frames"
        )
        
        return playbook
