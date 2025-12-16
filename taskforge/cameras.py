"""
TaskForge Camera Abstraction Layer

Unified interface for depth cameras and webcams.
Supports sensor-blind mode for mobile/basic devices without depth cameras.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Tuple
import numpy as np
from enum import Enum


class CameraType(Enum):
    OAK_D_S2 = "oak-d-s2"
    OAK_D_PRO = "oak-d-pro"
    REALSENSE_D455 = "realsense-d455"
    WEBCAM = "webcam"  # Sensor-blind mode - any USB webcam
    

@dataclass
class Frame:
    """Single synchronized capture from depth camera"""
    timestamp: float          # Unix timestamp
    rgb: np.ndarray          # HxWx3 uint8
    depth: np.ndarray        # HxW float32 (meters)
    depth_colorized: np.ndarray  # HxWx3 uint8 (for visualization)
    
    # Optional extras
    ir_left: Optional[np.ndarray] = None
    ir_right: Optional[np.ndarray] = None
    
    def depth_at(self, x: int, y: int) -> float:
        """Get depth in meters at pixel coordinate"""
        return self.depth[y, x]
    
    def region_depth(self, x1: int, y1: int, x2: int, y2: int) -> Tuple[float, float, float]:
        """Get min, max, mean depth in region (meters)"""
        region = self.depth[y1:y2, x1:x2]
        valid = region[region > 0]  # Filter invalid
        if len(valid) == 0:
            return (0, 0, 0)
        return (float(np.min(valid)), float(np.max(valid)), float(np.mean(valid)))


class DepthCamera(ABC):
    """Abstract base class for depth cameras"""
    
    @abstractmethod
    def connect(self) -> bool:
        """Initialize camera connection. Returns True on success."""
        pass
    
    @abstractmethod
    def disconnect(self) -> None:
        """Clean shutdown"""
        pass
    
    @abstractmethod
    def get_frame(self) -> Optional[Frame]:
        """Capture single synchronized frame. Returns None if unavailable."""
        pass
    
    @abstractmethod
    def get_intrinsics(self) -> dict:
        """Return camera intrinsics for 3D reconstruction"""
        pass
    
    @property
    @abstractmethod
    def camera_type(self) -> CameraType:
        pass
    
    @property
    @abstractmethod
    def resolution(self) -> Tuple[int, int]:
        """Returns (width, height)"""
        pass


# === OAK-D Implementation ===

class OakDCamera(DepthCamera):
    """
    Luxonis OAK-D camera family
    Supports: OAK-D S2, OAK-D Pro, OAK-D Pro W
    """
    
    def __init__(self, camera_type: CameraType = CameraType.OAK_D_PRO):
        self._type = camera_type
        self._pipeline = None
        self._device = None
        self._queues = {}
        
    @property
    def camera_type(self) -> CameraType:
        return self._type
    
    @property
    def resolution(self) -> Tuple[int, int]:
        return (1920, 1080)  # RGB resolution
    
    def connect(self) -> bool:
        try:
            import depthai as dai
            
            pipeline = dai.Pipeline()
            
            # RGB Camera
            cam_rgb = pipeline.create(dai.node.ColorCamera)
            cam_rgb.setResolution(dai.ColorCameraProperties.SensorResolution.THE_1080_P)
            cam_rgb.setInterleaved(False)
            cam_rgb.setColorOrder(dai.ColorCameraProperties.ColorOrder.RGB)
            cam_rgb.setFps(30)
            
            # Stereo Depth
            mono_left = pipeline.create(dai.node.MonoCamera)
            mono_right = pipeline.create(dai.node.MonoCamera)
            stereo = pipeline.create(dai.node.StereoDepth)
            
            mono_left.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
            mono_left.setBoardSocket(dai.CameraBoardSocket.CAM_B)
            mono_right.setResolution(dai.MonoCameraProperties.SensorResolution.THE_400_P)
            mono_right.setBoardSocket(dai.CameraBoardSocket.CAM_C)
            
            stereo.setDefaultProfilePreset(dai.node.StereoDepth.PresetMode.HIGH_DENSITY)
            stereo.setDepthAlign(dai.CameraBoardSocket.CAM_A)  # Align to RGB
            stereo.setOutputSize(640, 400)
            
            mono_left.out.link(stereo.left)
            mono_right.out.link(stereo.right)
            
            # Outputs
            xout_rgb = pipeline.create(dai.node.XLinkOut)
            xout_depth = pipeline.create(dai.node.XLinkOut)
            xout_rgb.setStreamName("rgb")
            xout_depth.setStreamName("depth")
            
            cam_rgb.video.link(xout_rgb.input)
            stereo.depth.link(xout_depth.input)
            
            # Connect
            self._device = dai.Device(pipeline)
            self._queues['rgb'] = self._device.getOutputQueue(name="rgb", maxSize=4, blocking=False)
            self._queues['depth'] = self._device.getOutputQueue(name="depth", maxSize=4, blocking=False)
            self._pipeline = pipeline
            
            return True
            
        except Exception as e:
            print(f"OAK-D connection failed: {e}")
            return False
    
    def disconnect(self) -> None:
        if self._device:
            self._device.close()
            self._device = None
    
    def get_frame(self) -> Optional[Frame]:
        import time
        import cv2
        
        rgb_frame = self._queues['rgb'].tryGet()
        depth_frame = self._queues['depth'].tryGet()
        
        if rgb_frame is None or depth_frame is None:
            return None
        
        rgb = rgb_frame.getCvFrame()
        depth_raw = depth_frame.getFrame()
        
        # Convert depth to meters
        depth_m = depth_raw.astype(np.float32) / 1000.0
        
        # Colorize depth for visualization
        depth_colorized = cv2.applyColorMap(
            cv2.convertScaleAbs(depth_raw, alpha=0.03),
            cv2.COLORMAP_JET
        )
        
        return Frame(
            timestamp=time.time(),
            rgb=rgb,
            depth=depth_m,
            depth_colorized=depth_colorized
        )
    
    def get_intrinsics(self) -> dict:
        if self._device:
            calib = self._device.readCalibration()
            intrinsics = calib.getCameraIntrinsics(
                dai.CameraBoardSocket.CAM_A,
                resizeWidth=1920,
                resizeHeight=1080
            )
            return {
                'fx': intrinsics[0][0],
                'fy': intrinsics[1][1],
                'cx': intrinsics[0][2],
                'cy': intrinsics[1][2],
            }
        return {}


# === RealSense Implementation ===

class RealSenseCamera(DepthCamera):
    """
    Intel RealSense D400 series
    Supports: D435, D455
    """
    
    def __init__(self, camera_type: CameraType = CameraType.REALSENSE_D455):
        self._type = camera_type
        self._pipeline = None
        self._config = None
        self._align = None
        
    @property
    def camera_type(self) -> CameraType:
        return self._type
    
    @property
    def resolution(self) -> Tuple[int, int]:
        return (1280, 720)
    
    def connect(self) -> bool:
        try:
            import pyrealsense2 as rs
            
            self._pipeline = rs.pipeline()
            self._config = rs.config()
            
            # Enable streams
            self._config.enable_stream(rs.stream.depth, 1280, 720, rs.format.z16, 30)
            self._config.enable_stream(rs.stream.color, 1280, 720, rs.format.rgb8, 30)
            
            # Start pipeline
            profile = self._pipeline.start(self._config)
            
            # Get depth scale
            depth_sensor = profile.get_device().first_depth_sensor()
            self._depth_scale = depth_sensor.get_depth_scale()
            
            # Align depth to color
            self._align = rs.align(rs.stream.color)
            
            # Let auto-exposure settle
            for _ in range(30):
                self._pipeline.wait_for_frames()
            
            return True
            
        except Exception as e:
            print(f"RealSense connection failed: {e}")
            return False
    
    def disconnect(self) -> None:
        if self._pipeline:
            self._pipeline.stop()
            self._pipeline = None
    
    def get_frame(self) -> Optional[Frame]:
        import time
        import cv2
        import pyrealsense2 as rs
        
        frames = self._pipeline.wait_for_frames()
        aligned = self._align.process(frames)
        
        depth_frame = aligned.get_depth_frame()
        color_frame = aligned.get_color_frame()
        
        if not depth_frame or not color_frame:
            return None
        
        # Convert to numpy
        rgb = np.asanyarray(color_frame.get_data())
        depth_raw = np.asanyarray(depth_frame.get_data())
        
        # Convert depth to meters
        depth_m = depth_raw.astype(np.float32) * self._depth_scale
        
        # Colorize
        colorizer = rs.colorizer()
        depth_colorized = np.asanyarray(
            colorizer.colorize(depth_frame).get_data()
        )
        
        return Frame(
            timestamp=time.time(),
            rgb=rgb,
            depth=depth_m,
            depth_colorized=depth_colorized
        )
    
    def get_intrinsics(self) -> dict:
        import pyrealsense2 as rs
        
        if self._pipeline:
            profile = self._pipeline.get_active_profile()
            color_stream = profile.get_stream(rs.stream.color)
            intrinsics = color_stream.as_video_stream_profile().get_intrinsics()
            return {
                'fx': intrinsics.fx,
                'fy': intrinsics.fy,
                'cx': intrinsics.ppx,
                'cy': intrinsics.ppy,
            }
        return {}


# === Webcam Implementation (Sensor-Blind Mode) ===

class WebcamCamera(DepthCamera):
    """
    Standard USB webcam - no depth sensor required.

    Use this for:
    - Mobile devices
    - Laptops without depth cameras
    - Any basic RGB capture

    Depth data will be empty (zeros), but RGB capture works normally.
    Playbooks can still be generated from video + audio narration.
    """

    def __init__(self, device_id: int = 0, resolution: Tuple[int, int] = (1280, 720)):
        self._device_id = device_id
        self._resolution = resolution
        self._cap = None

    @property
    def camera_type(self) -> CameraType:
        return CameraType.WEBCAM

    @property
    def resolution(self) -> Tuple[int, int]:
        return self._resolution

    def connect(self) -> bool:
        try:
            import cv2
            self._cap = cv2.VideoCapture(self._device_id)

            if not self._cap.isOpened():
                return False

            # Set resolution
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._resolution[0])
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._resolution[1])

            # Read a test frame
            ret, _ = self._cap.read()
            if not ret:
                self._cap.release()
                return False

            return True

        except Exception as e:
            print(f"Webcam connection failed: {e}")
            return False

    def disconnect(self) -> None:
        if self._cap:
            self._cap.release()
            self._cap = None

    def get_frame(self) -> Optional[Frame]:
        import time
        import cv2

        if self._cap is None:
            return None

        ret, frame = self._cap.read()
        if not ret:
            return None

        # Convert BGR to RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]

        # Create empty depth arrays (sensor-blind mode)
        depth = np.zeros((h, w), dtype=np.float32)
        depth_colorized = np.zeros((h, w, 3), dtype=np.uint8)

        return Frame(
            timestamp=time.time(),
            rgb=rgb,
            depth=depth,
            depth_colorized=depth_colorized
        )

    def get_intrinsics(self) -> dict:
        # Approximate intrinsics for standard webcam
        w, h = self._resolution
        # Assume ~60 degree FOV
        fx = fy = w * 0.9  # Rough estimate
        cx, cy = w / 2, h / 2
        return {
            'fx': fx,
            'fy': fy,
            'cx': cx,
            'cy': cy,
            'sensor_blind': True,  # Flag indicating no real depth
        }


# === Factory ===

def get_camera(camera_type: CameraType = None, fallback_to_webcam: bool = True) -> DepthCamera:
    """
    Auto-detect or create specific camera.

    Args:
        camera_type: Specific camera type to use, or None for auto-detect
        fallback_to_webcam: If True, fall back to webcam if no depth camera found

    Returns first available if camera_type is None.
    Falls back to webcam (sensor-blind mode) if no depth camera found and fallback enabled.
    """
    # Explicit webcam request
    if camera_type == CameraType.WEBCAM:
        return WebcamCamera()

    if camera_type in [CameraType.OAK_D_S2, CameraType.OAK_D_PRO]:
        return OakDCamera(camera_type)
    elif camera_type == CameraType.REALSENSE_D455:
        return RealSenseCamera(camera_type)

    # Auto-detect depth cameras first
    cameras = [
        OakDCamera(CameraType.OAK_D_PRO),
        RealSenseCamera(CameraType.REALSENSE_D455),
    ]

    for cam in cameras:
        if cam.connect():
            return cam
        cam.disconnect()

    # Fallback to webcam if enabled
    if fallback_to_webcam:
        print("   ⚠️  No depth camera found, using webcam (sensor-blind mode)")
        webcam = WebcamCamera()
        if webcam.connect():
            return webcam
        webcam.disconnect()

    raise RuntimeError("No supported camera found")


def list_cameras() -> list:
    """List available cameras including webcams"""
    available = []

    # Check OAK-D
    try:
        import depthai as dai
        devices = dai.Device.getAllAvailableDevices()
        for d in devices:
            available.append({
                'type': 'oak-d',
                'id': d.getMxId(),
                'state': str(d.state)
            })
    except:
        pass

    # Check RealSense
    try:
        import pyrealsense2 as rs
        ctx = rs.context()
        for d in ctx.devices:
            available.append({
                'type': 'realsense',
                'id': d.get_info(rs.camera_info.serial_number),
                'name': d.get_info(rs.camera_info.name)
            })
    except:
        pass

    # Check for webcams
    try:
        import cv2
        for i in range(4):  # Check first 4 device indices
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                # Try to get camera name (platform-dependent)
                available.append({
                    'type': 'webcam',
                    'id': str(i),
                    'name': f'Webcam {i} (sensor-blind)',
                    'has_depth': False
                })
                cap.release()
    except:
        pass

    return available
