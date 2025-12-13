"""
TaskForge - Watch me work. Write the manual.

Capture task demonstrations with depth cameras and generate playbooks.

Supports NVIDIA Jetson (Orin Nano, Orin NX, AGX Orin) with automatic
platform detection and memory-optimized defaults.
"""

__version__ = "0.1.0"

from .cameras import (
    DepthCamera,
    OakDCamera,
    RealSenseCamera,
    CameraType,
    Frame,
    get_camera,
    list_cameras
)

from .capture import (
    TaskCapture,
    CaptureConfig,
    CaptureSession
)

from .process import (
    TaskProcessor,
    Playbook,
    PlaybookStep
)

from .platform import (
    detect_platform,
    is_jetson,
    is_memory_constrained,
    PlatformInfo,
    print_platform_info
)

__all__ = [
    # Cameras
    'DepthCamera',
    'OakDCamera',
    'RealSenseCamera',
    'CameraType',
    'Frame',
    'get_camera',
    'list_cameras',

    # Capture
    'TaskCapture',
    'CaptureConfig',
    'CaptureSession',

    # Processing
    'TaskProcessor',
    'Playbook',
    'PlaybookStep',

    # Platform
    'detect_platform',
    'is_jetson',
    'is_memory_constrained',
    'PlatformInfo',
    'print_platform_info',
]
