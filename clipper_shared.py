import subprocess
import sys

SUBPROCESS_FLAGS = 0
if sys.platform == "win32":
    SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW

try:
    import yt_dlp
    YTDLP_MODULE_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_MODULE_AVAILABLE = False


class SubtitleNotFoundError(Exception):
    def __init__(self, message: str, video_path: str = None, video_info: dict = None, session_dir: str = None):
        super().__init__(message)
        self.video_path = video_path
        self.video_info = video_info or {}
        self.session_dir = session_dir


def _hex_to_rgb(hex_color: str):
    if not isinstance(hex_color, str):
        return (255, 255, 255)
    value = hex_color.strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        return (255, 255, 255)
    try:
        return (int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16))
    except ValueError:
        return (255, 255, 255)
