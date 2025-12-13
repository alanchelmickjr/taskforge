"""
TaskForge - Watch me work. Write the manual.

Capture task demonstrations with depth cameras and generate playbooks.
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
]
