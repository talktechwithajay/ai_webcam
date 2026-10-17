"""AI Home Visitor system backend."""
import os

# Must be set before cv2 is imported anywhere: RTSP over TCP, low-latency flags.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|fflags;nobuffer|flags;low_delay|timeout;8000000",
)

__version__ = "0.2.0"
