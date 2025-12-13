"""
TaskForge Capture Module

Records synchronized video + depth + audio streams.
Voice narration is the primary interface.

Optimized for memory-constrained devices like NVIDIA Jetson Orin Nano.
"""

import os
import gc
import time
import json
import threading
import queue
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional, List
import numpy as np
import cv2

from .cameras import DepthCamera, Frame, get_camera, CameraType
from .platform import detect_platform, is_memory_constrained


@dataclass
class CaptureSession:
    """Metadata for a capture session"""
    name: str
    started_at: float
    camera_type: str
    output_dir: Path
    frames_captured: int = 0
    audio_file: Optional[str] = None
    duration_seconds: float = 0
    

@dataclass
class CaptureConfig:
    """Configuration for capture behavior"""
    fps: int = None                    # Frame capture rate (auto-detected if None)
    save_depth_raw: bool = True        # Save .npy depth arrays
    save_depth_viz: bool = True        # Save colorized depth images
    save_video: bool = True            # Compile to MP4 at end
    keyframe_interval: int = 30        # Force keyframe every N frames
    scene_change_threshold: float = 0.3  # 0-1, sensitivity for scene detection
    audio_device: Optional[str] = None   # None = default mic
    video_chunk_size: int = None       # Frames per chunk for video compilation (auto if None)

    def __post_init__(self):
        """Apply platform-specific defaults"""
        platform_info = detect_platform()

        if self.fps is None:
            self.fps = platform_info.recommended_capture_fps

        if self.video_chunk_size is None:
            self.video_chunk_size = platform_info.max_video_frames_in_memory

        # On memory-constrained devices, skip raw depth to save disk I/O
        if is_memory_constrained() and self.save_depth_raw:
            # Keep it enabled but user can disable if needed
            pass
    

class AudioRecorder:
    """Records audio in background thread"""
    
    def __init__(self, output_path: Path, device: Optional[str] = None):
        self.output_path = output_path
        self.device = device
        self._thread = None
        self._stop_event = threading.Event()
        
    def start(self):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._record)
        self._thread.start()
        
    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            
    def _record(self):
        try:
            import sounddevice as sd
            import soundfile as sf
            
            samplerate = 16000  # Whisper prefers 16kHz
            channels = 1
            
            audio_chunks = []
            
            def callback(indata, frames, time, status):
                if not self._stop_event.is_set():
                    audio_chunks.append(indata.copy())
            
            with sd.InputStream(samplerate=samplerate, channels=channels,
                               callback=callback, device=self.device):
                while not self._stop_event.is_set():
                    sd.sleep(100)
            
            # Save audio
            if audio_chunks:
                audio_data = np.concatenate(audio_chunks, axis=0)
                sf.write(str(self.output_path), audio_data, samplerate)
                
        except Exception as e:
            print(f"Audio recording error: {e}")


class SceneChangeDetector:
    """Detects significant visual changes between frames"""
    
    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold
        self._last_hist = None
        
    def is_scene_change(self, frame: np.ndarray) -> bool:
        # Convert to grayscale and compute histogram
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        hist = cv2.calcHist([gray], [0], None, [64], [0, 256])
        hist = cv2.normalize(hist, hist).flatten()
        
        if self._last_hist is None:
            self._last_hist = hist
            return True  # First frame is always a "scene change"
        
        # Compare histograms
        correlation = cv2.compareHist(self._last_hist, hist, cv2.HISTCMP_CORREL)
        self._last_hist = hist
        
        # Low correlation = big change
        return correlation < (1 - self.threshold)


class TaskCapture:
    """
    Main capture orchestrator.
    
    Usage:
        capture = TaskCapture("assembling gripper")
        capture.start()
        # ... do the task, narrate ...
        capture.stop()
        # Output is in ./recordings/assembling-gripper/
    """
    
    def __init__(
        self,
        task_name: str,
        output_base: Path = Path("./recordings"),
        camera_type: Optional[CameraType] = None,
        config: Optional[CaptureConfig] = None
    ):
        self.task_name = task_name
        self.config = config or CaptureConfig()
        
        # Setup output directory
        safe_name = self._sanitize_name(task_name)
        timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
        self.output_dir = output_base / f"{timestamp}_{safe_name}"
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / "frames").mkdir(exist_ok=True)
        (self.output_dir / "depth").mkdir(exist_ok=True)
        
        # Initialize camera
        self.camera = get_camera(camera_type)
        
        # State
        self._running = False
        self._capture_thread = None
        self._audio_recorder = None
        self._session = None
        self._frames: List[dict] = []  # Frame metadata
        self._scene_detector = SceneChangeDetector(self.config.scene_change_threshold)
        
    def _sanitize_name(self, name: str) -> str:
        return name.lower().replace(" ", "-").replace("/", "-")[:50]
    
    def start(self) -> CaptureSession:
        """Begin capture session"""
        platform_info = detect_platform()

        print(f"🎬 Starting capture: {self.task_name}")
        print(f"   Output: {self.output_dir}")
        if platform_info.is_jetson:
            print(f"   Platform: Jetson {platform_info.jetson_model or ''} ({platform_info.total_memory_gb:.0f}GB RAM)")
        print(f"   FPS: {self.config.fps}")
        
        # Connect camera
        if not self.camera.connect():
            raise RuntimeError("Failed to connect to camera")
        
        print(f"   Camera: {self.camera.camera_type.value}")
        
        # Start audio recording
        audio_path = self.output_dir / "audio.wav"
        self._audio_recorder = AudioRecorder(audio_path, self.config.audio_device)
        self._audio_recorder.start()
        
        # Create session
        self._session = CaptureSession(
            name=self.task_name,
            started_at=time.time(),
            camera_type=self.camera.camera_type.value,
            output_dir=self.output_dir,
            audio_file=str(audio_path)
        )
        
        # Start capture loop
        self._running = True
        self._capture_thread = threading.Thread(target=self._capture_loop)
        self._capture_thread.start()
        
        print("   Recording... (Ctrl+C or call stop() to end)")
        return self._session
    
    def stop(self) -> CaptureSession:
        """End capture session"""
        print("\n🛑 Stopping capture...")
        
        self._running = False
        
        if self._capture_thread:
            self._capture_thread.join(timeout=5)
        
        if self._audio_recorder:
            self._audio_recorder.stop()
        
        if self.camera:
            self.camera.disconnect()
        
        # Update session
        self._session.duration_seconds = time.time() - self._session.started_at
        self._session.frames_captured = len(self._frames)
        
        # Save session metadata
        self._save_metadata()
        
        # Optionally compile video
        if self.config.save_video:
            self._compile_video()
        
        print(f"✅ Captured {self._session.frames_captured} frames")
        print(f"   Duration: {self._session.duration_seconds:.1f}s")
        print(f"   Output: {self.output_dir}")
        
        return self._session
    
    def _capture_loop(self):
        """Main capture loop - runs in thread"""
        frame_interval = 1.0 / self.config.fps
        last_capture = 0
        frame_idx = 0
        
        while self._running:
            now = time.time()
            
            if now - last_capture < frame_interval:
                time.sleep(0.01)
                continue
            
            frame = self.camera.get_frame()
            if frame is None:
                continue
            
            last_capture = now
            
            # Check for scene change
            is_keyframe = (
                frame_idx % self.config.keyframe_interval == 0 or
                self._scene_detector.is_scene_change(frame.rgb)
            )
            
            # Save frame
            frame_name = f"frame_{frame_idx:06d}"
            
            # Always save RGB
            rgb_path = self.output_dir / "frames" / f"{frame_name}.jpg"
            cv2.imwrite(str(rgb_path), cv2.cvtColor(frame.rgb, cv2.COLOR_RGB2BGR))
            
            # Save depth
            if self.config.save_depth_raw:
                depth_path = self.output_dir / "depth" / f"{frame_name}.npy"
                np.save(str(depth_path), frame.depth)
            
            if self.config.save_depth_viz:
                depth_viz_path = self.output_dir / "depth" / f"{frame_name}_viz.jpg"
                cv2.imwrite(str(depth_viz_path), frame.depth_colorized)
            
            # Record metadata
            self._frames.append({
                'index': frame_idx,
                'timestamp': frame.timestamp,
                'relative_time': frame.timestamp - self._session.started_at,
                'is_keyframe': is_keyframe,
                'rgb_file': str(rgb_path.name),
            })
            
            frame_idx += 1
            
    def _save_metadata(self):
        """Save session and frame metadata as JSON"""
        metadata = {
            'session': {
                'name': self._session.name,
                'started_at': self._session.started_at,
                'duration_seconds': self._session.duration_seconds,
                'camera_type': self._session.camera_type,
                'frames_captured': self._session.frames_captured,
                'audio_file': self._session.audio_file,
                'config': {
                    'fps': self.config.fps,
                    'keyframe_interval': self.config.keyframe_interval,
                    'scene_change_threshold': self.config.scene_change_threshold,
                }
            },
            'frames': self._frames,
            'camera_intrinsics': self.camera.get_intrinsics() if self.camera else {},
        }
        
        with open(self.output_dir / "metadata.json", 'w') as f:
            json.dump(metadata, f, indent=2)
    
    def _compile_video(self):
        """
        Compile frames into MP4.

        Memory-optimized: processes frames in chunks to avoid OOM on
        constrained devices like Jetson Orin Nano.
        """
        print("   Compiling video...")

        frames_dir = self.output_dir / "frames"
        frame_files = sorted(frames_dir.glob("frame_*.jpg"))

        if not frame_files:
            return

        # Read first frame to get dimensions
        first = cv2.imread(str(frame_files[0]))
        h, w = first.shape[:2]
        del first  # Free memory immediately

        output_path = self.output_dir / "recording.mp4"
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(str(output_path), fourcc, self.config.fps, (w, h))

        chunk_size = self.config.video_chunk_size
        total_frames = len(frame_files)

        # Process in chunks to manage memory
        for chunk_start in range(0, total_frames, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total_frames)
            chunk_files = frame_files[chunk_start:chunk_end]

            for frame_file in chunk_files:
                img = cv2.imread(str(frame_file))
                if img is not None:
                    out.write(img)
                # Explicitly delete to help garbage collector
                del img

            # Force garbage collection between chunks on memory-constrained devices
            if is_memory_constrained():
                gc.collect()

            # Progress indicator for long recordings
            if total_frames > 100:
                progress = (chunk_end / total_frames) * 100
                print(f"   Video progress: {progress:.0f}%", end='\r')

        out.release()
        print(f"   Video saved: {output_path}          ")  # Extra spaces to clear progress line
