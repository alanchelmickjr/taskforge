"""
TaskForge Platform Detection

Detects hardware platform and provides appropriate defaults.
Special handling for NVIDIA Jetson devices (Orin Nano, etc.)
"""

import os
import platform
from dataclasses import dataclass
from typing import Optional
from functools import lru_cache


@dataclass
class PlatformInfo:
    """Information about the current platform"""
    is_jetson: bool
    jetson_model: Optional[str]  # e.g., "Orin Nano", "Orin NX", "AGX Orin"
    total_memory_gb: float
    is_arm64: bool
    cuda_available: bool

    # Recommended settings based on platform
    recommended_whisper_model: str
    max_video_frames_in_memory: int
    recommended_capture_fps: int


@lru_cache(maxsize=1)
def detect_platform() -> PlatformInfo:
    """
    Detect current platform and return appropriate settings.
    Results are cached for performance.
    """
    is_jetson = False
    jetson_model = None
    total_memory_gb = _get_total_memory_gb()
    is_arm64 = platform.machine() in ('aarch64', 'arm64')
    cuda_available = _check_cuda()

    # Check for Jetson
    if os.path.exists('/etc/nv_tegra_release'):
        is_jetson = True
        jetson_model = _get_jetson_model()
    elif os.path.exists('/proc/device-tree/model'):
        try:
            with open('/proc/device-tree/model', 'r') as f:
                model = f.read().lower()
                if 'jetson' in model or 'orin' in model:
                    is_jetson = True
                    jetson_model = _get_jetson_model()
        except:
            pass

    # Determine recommended settings based on platform
    if is_jetson or total_memory_gb <= 8:
        # Memory-constrained device
        if total_memory_gb <= 4:
            whisper_model = "tiny"
            max_frames = 100
            fps = 5
        elif total_memory_gb <= 8:
            whisper_model = "tiny"  # 'base' might work but risky on 8GB shared
            max_frames = 200
            fps = 10
        else:
            whisper_model = "base"
            max_frames = 500
            fps = 10
    else:
        # Desktop/server with plenty of RAM
        whisper_model = "base"
        max_frames = 1000
        fps = 10

    return PlatformInfo(
        is_jetson=is_jetson,
        jetson_model=jetson_model,
        total_memory_gb=total_memory_gb,
        is_arm64=is_arm64,
        cuda_available=cuda_available,
        recommended_whisper_model=whisper_model,
        max_video_frames_in_memory=max_frames,
        recommended_capture_fps=fps,
    )


def _get_total_memory_gb() -> float:
    """Get total system memory in GB"""
    try:
        with open('/proc/meminfo', 'r') as f:
            for line in f:
                if line.startswith('MemTotal:'):
                    # Parse "MemTotal:       xxxxx kB"
                    kb = int(line.split()[1])
                    return kb / (1024 * 1024)
    except:
        pass

    # Fallback: try psutil if available
    try:
        import psutil
        return psutil.virtual_memory().total / (1024**3)
    except:
        pass

    # Conservative default
    return 8.0


def _get_jetson_model() -> Optional[str]:
    """Detect specific Jetson model"""
    # Try reading from device tree
    try:
        with open('/proc/device-tree/model', 'r') as f:
            model = f.read().strip().replace('\x00', '')
            # Parse common models
            model_lower = model.lower()
            if 'orin nano' in model_lower:
                return 'Orin Nano'
            elif 'orin nx' in model_lower:
                return 'Orin NX'
            elif 'agx orin' in model_lower:
                return 'AGX Orin'
            elif 'xavier nx' in model_lower:
                return 'Xavier NX'
            elif 'agx xavier' in model_lower:
                return 'AGX Xavier'
            elif 'nano' in model_lower:
                return 'Nano'
            return model
    except:
        pass

    # Try tegra release file
    try:
        with open('/etc/nv_tegra_release', 'r') as f:
            return "Jetson (unknown model)"
    except:
        pass

    return None


def _check_cuda() -> bool:
    """Check if CUDA is available"""
    try:
        import torch
        return torch.cuda.is_available()
    except:
        pass

    # Check for CUDA libraries
    cuda_paths = [
        '/usr/local/cuda',
        '/usr/lib/aarch64-linux-gnu/tegra',  # Jetson
    ]
    return any(os.path.exists(p) for p in cuda_paths)


def print_platform_info():
    """Print detected platform information"""
    info = detect_platform()

    print("=" * 50)
    print("TaskForge Platform Detection")
    print("=" * 50)

    if info.is_jetson:
        print(f"  Platform: NVIDIA Jetson ({info.jetson_model or 'unknown model'})")
    else:
        print(f"  Platform: {'ARM64' if info.is_arm64 else 'x86_64'} Linux")

    print(f"  Total Memory: {info.total_memory_gb:.1f} GB")
    print(f"  CUDA Available: {'Yes' if info.cuda_available else 'No'}")
    print()
    print("Recommended Settings:")
    print(f"  Whisper Model: {info.recommended_whisper_model}")
    print(f"  Capture FPS: {info.recommended_capture_fps}")
    print(f"  Max Frames in Memory: {info.max_video_frames_in_memory}")
    print("=" * 50)


# Convenience exports
def is_jetson() -> bool:
    """Quick check if running on Jetson"""
    return detect_platform().is_jetson


def is_memory_constrained() -> bool:
    """Check if platform has limited memory (<=8GB)"""
    return detect_platform().total_memory_gb <= 8
