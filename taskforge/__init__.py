"""
TaskForge - Watch me work. Write the manual.

Capture task demonstrations with depth cameras and generate playbooks.

Supports NVIDIA Jetson (Orin Nano, Orin NX, AGX Orin) with automatic
platform detection and memory-optimized defaults.

Integrates with memoRable for salient memory storage and retrieval.
"""

__version__ = "0.1.0"

from .cameras import (
    DepthCamera,
    OakDCamera,
    RealSenseCamera,
    WebcamCamera,
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

# Memory integration (optional - requires httpx or requests)
try:
    from .memory import (
        SalientMemoryClient,
        MemoryConfig,
        get_memory_client,
        store_playbook_memory,
        search_related_playbooks,
        get_task_briefing,
    )
    _HAS_MEMORY = True
except ImportError:
    _HAS_MEMORY = False

__all__ = [
    # Cameras
    'DepthCamera',
    'OakDCamera',
    'RealSenseCamera',
    'WebcamCamera',
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

    # Memory (optional)
    'SalientMemoryClient',
    'MemoryConfig',
    'get_memory_client',
    'store_playbook_memory',
    'search_related_playbooks',
    'get_task_briefing',
]
