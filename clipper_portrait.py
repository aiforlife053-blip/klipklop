import os
import sys
import tempfile
import time

import cv2
import numpy as np

from clipper_base import ClipperBase
from utils.logger import debug_log


class PortraitMixin(ClipperBase):
    def _get_target_portrait_dims(self, orig_w: int, orig_h: int) -> tuple[int, int]:
        """Get target (out_w, out_h) dynamically from self.output_resolution or source video dimensions."""
        res_str = getattr(self, "output_resolution", None)
        if res_str and ":" in str(res_str):
            try:
                parts = [int(p) for p in str(res_str).split(":")]
                if len(parts) == 2:
                    w, h = (parts[0], parts[1]) if parts[0] < parts[1] else (parts[1], parts[0])
                    return w, h
            except Exception:
                pass
        crop_w = int(orig_h * (9 / 16))
        return crop_w, orig_h

    def stabilize_positions(self, positions: list) -> list:
        """Stabilize crop positions - reduce jitter and sudden movements"""
        if not positions:
            return positions

        # Use longer window for smoother movement
        window_size = 60  # ~2 seconds at 30fps - longer window = smoother
        stabilized = []

        for i in range(len(positions)):
            # Get window around current position
            start = max(0, i - window_size // 2)
            end = min(len(positions), i + window_size // 2)
            window = positions[start:end]

            # Use median for stability (resistant to outliers)
            avg = int(np.median(window))
            stabilized.append(avg)

        # Second pass: detect shot changes and lock position per shot
        # A shot change is when position jumps significantly
        # Use very high threshold to minimize scene switches
        final = []
        shot_start = 0
        threshold = 250  # pixels - very high threshold = less scene switches
        min_shot_duration = 90  # minimum frames (~3 seconds) before allowing switch

        for i in range(len(stabilized)):
            frames_since_last_switch = i - shot_start

            # Only allow switch if enough time has passed AND position changed significantly
            if i > 0 and frames_since_last_switch >= min_shot_duration:
                if abs(stabilized[i] - stabilized[shot_start]) > threshold:
                    # Shot change detected - lock previous shot to median
                    shot_positions = stabilized[shot_start:i]
                    if shot_positions:
                        shot_median = int(np.median(shot_positions))
                        final.extend([shot_median] * len(shot_positions))
                    shot_start = i

        # Handle last shot
        shot_positions = stabilized[shot_start:]
        if shot_positions:
            shot_median = int(np.median(shot_positions))
            final.extend([shot_median] * len(shot_positions))

        return final if final else stabilized

    def convert_to_portrait_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Convert landscape to 9:16 portrait with speaker tracking and progress (router method)"""
        if getattr(self, "landscape_blur", False) and self._is_landscape(input_path):
            self.log("  Using moving blur background")
            return self.convert_to_portrait_blur_with_progress(input_path, output_path, progress_callback)
        if self.face_tracking_mode == "center":
            self.log("  Using explicit black background")
            return self.convert_to_portrait_center(input_path, output_path, progress_callback)
        self.log("  Using OpenCV (Fast Mode)")
        return self.convert_to_portrait_opencv_with_progress(input_path, output_path, progress_callback)

    def _is_landscape(self, input_path: str) -> bool:
        cap = cv2.VideoCapture(input_path)
        try:
            return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) > int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        finally:
            cap.release()

    def _video_duration(self, input_path: str) -> float:
        cap = cv2.VideoCapture(input_path)
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) or 0
            frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            return max(1.0, frames / fps) if fps > 0 else 60.0
        finally:
            cap.release()

    def _portrait_filter(self, width: int, height: int, blur_enabled: bool) -> tuple[list[str], str]:
        if not blur_enabled:
            return ([f"color=c=black:s={width}x{height}[bg]", f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,setsar=1[fg]", "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]"], "v0")
        blur_settings = getattr(self, "blur_background_settings", {}) or {}
        zoom = max(1.0, min(3.0, float(blur_settings.get("zoom", 1.08) or 1.08)))
        strength = max(0, min(100, int(blur_settings.get("strength", 30))))
        scale = max(1.0, min(2.0, float(blur_settings.get("scale", 1.6) or 1.6)))
        foreground_width, foreground_height = int(round(width * scale)), int(round(width * 9 / 16 * scale))
        blur_radius = int(round((strength / 340 * width) * 0.75))
        blur_filter = f"boxblur={blur_radius}:{blur_radius}," if blur_radius else ""
        return ([f"[0:v]scale=320:{int(round(320 * height / width))}:force_original_aspect_ratio=increase,{blur_filter}scale={int(round(width * zoom))}:{int(round(height * zoom))}:force_original_aspect_ratio=increase,crop={width}:{height},setsar=1,colorchannelmixer=rr=0.6:gg=0.6:bb=0.6[bg]", f"[0:v]scale={foreground_width}:{foreground_height}:force_original_aspect_ratio=increase,crop={foreground_width}:{foreground_height},setsar=1[fg]", "[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1[v0]"], "v0")

    def _preview_blur_filter(self, width: int, height: int) -> str:
        blur_settings = getattr(self, "blur_background_settings", {}) or {}
        zoom = max(1.0, min(3.0, float(blur_settings.get("zoom", 1.08) or 1.08)))
        strength = max(0, min(100, int(blur_settings.get("strength", 30))))
        scale = max(1.0, min(2.0, float(blur_settings.get("scale", 1.6) or 1.6)))
        foreground_width = int(round(width * scale))
        foreground_height = int(round(width * 9 / 16 * scale))
        bg_width = int(round(width * zoom))
        bg_height = int(round(height * zoom))
        blur_width = 320
        blur_height = int(round(blur_width * height / width))
        blur_sigma = strength / 340 * width
        blur_radius = int(round(blur_sigma * 0.75))
        blur_filter = f"boxblur={blur_radius}:{blur_radius}," if blur_radius else ""
        return (
            f"[0:v]scale={blur_width}:{blur_height}:force_original_aspect_ratio=increase,"
            f"{blur_filter}scale={bg_width}:{bg_height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1,colorchannelmixer=rr=0.6:gg=0.6:bb=0.6[bg];"
            f"[0:v]scale={foreground_width}:{foreground_height}:force_original_aspect_ratio=increase,"
            f"crop={foreground_width}:{foreground_height},setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )

    def convert_to_portrait_blur_with_progress(self, input_path: str, output_path: str, progress_callback):
        width, height = (int(part) for part in getattr(self, "output_resolution", "720:1280").split(":"))
        filter_complex = self._preview_blur_filter(width, height)
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-filter_complex", filter_complex,
            *self.get_video_encoder_args(),
            "-c:a", "aac",
            "-b:a", "192k",
            "-progress", "pipe:1",
            output_path,
        ]
        self.log(f"  Reframe filter [blur=on]: {filter_complex}")
        self.run_ffmpeg_with_progress(cmd, self._video_duration(input_path), progress_callback, timeout=getattr(self, "render_timeout", None))
        if not os.path.exists(output_path):
            raise Exception("Blur portrait failed: output file not found")

    def convert_to_portrait_center(self, input_path: str, output_path: str, progress_callback):
        width, height = (int(part) for part in getattr(self, "output_resolution", "720:1280").split(":"))
        filter_complex = (
            f"color=c=black:s={width}x{height}[bg];"
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease,setsar=1[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1"
        )
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-filter_complex", filter_complex,
            *self.get_video_encoder_args(),
            "-c:a", "aac",
            "-b:a", "192k",
            "-progress", "pipe:1",
            output_path,
        ]
        self.log(f"  Reframe filter [blur=off]: {filter_complex}")
        self.run_ffmpeg_with_progress(cmd, self._video_duration(input_path), progress_callback, timeout=getattr(self, "render_timeout", None))
        if not os.path.exists(output_path):
            raise Exception("Black background portrait failed: output file not found")

    def convert_to_portrait_opencv_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Convert landscape to 9:16 portrait with active-speaker tracking (OpenCV)."""

        debug_log("Starting portrait conversion...")
        debug_log(f"Input: {input_path}")
        debug_log(f"Output: {output_path}")
        sys.stdout.flush()

        from speaker_tracking import track_crop_positions

        try:
            tracking = track_crop_positions(input_path)
        except Exception as exc:
            raise Exception(f"Speaker tracking failed: {exc}") from exc

        crop_positions = tracking["crop_positions"]
        crop_w = int(tracking["crop_width"])
        orig_w = int(tracking["source_width"])
        orig_h = int(tracking["source_height"])
        fps = float(tracking["fps"] or 30.0)
        total_frames = len(crop_positions)
        out_w, out_h = self._get_target_portrait_dims(orig_w, orig_h)
        crop_h = orig_h

        if total_frames == 0 or fps == 0:
            raise Exception(f"Invalid video properties: {total_frames} frames, {fps} fps")

        progress_callback(0.45)
        debug_log(f"Tracking mode={tracking.get('mode')} frames={total_frames}")
        sys.stdout.flush()

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise Exception(f"Failed to open video: {input_path}")

        temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_video, fourcc, fps, (out_w, out_h))
        if not out.isOpened():
            cap.release()
            raise Exception(f"Failed to create VideoWriter: {temp_video}")

        frame_idx = 0
        last_log_time = 0
        last_frame_time = time.time()

        while True:
            if self.is_cancelled():
                cap.release()
                out.release()
                try:
                    os.unlink(temp_video)
                except OSError:
                    pass
                raise Exception("Cancelled by user")

            current_time = time.time()
            if current_time - last_frame_time > 30:
                cap.release()
                out.release()
                raise Exception(f"Portrait conversion timeout: stuck at frame {frame_idx}/{total_frames}")

            ret, frame = cap.read()
            if not ret:
                break

            last_frame_time = current_time
            crop_x = crop_positions[frame_idx] if frame_idx < len(crop_positions) else crop_positions[-1]
            crop_x = max(0, min(int(crop_x), max(0, orig_w - crop_w)))
            cropped = frame[0:crop_h, crop_x:crop_x + crop_w]
            resized = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
            success = out.write(resized)
            if not success:
                print(f"[WARNING] Failed to write frame {frame_idx}")
                sys.stdout.flush()

            frame_idx += 1
            if frame_idx % 30 == 0 or (current_time - last_log_time) > 2:
                progress = 0.45 + (frame_idx / max(1, total_frames)) * 0.4
                debug_log(f"Pass 2 progress: {progress*100:.1f}% ({frame_idx}/{total_frames} frames)")
                sys.stdout.flush()
                progress_callback(progress)
                last_log_time = current_time

        debug_log(f"Created {frame_idx} frames")
        sys.stdout.flush()
        cap.release()
        out.release()

        if not os.path.exists(temp_video) or os.path.getsize(temp_video) < 1000:
            raise Exception(f"Failed to create temp video: {temp_video}")

        progress_callback(0.85)
        debug_log("Pass 3: Merging audio...")
        sys.stdout.flush()

        encoder_args = self.get_video_encoder_args()
        cmd = [
            self.ffmpeg_path, "-y",
            "-i", temp_video,
            "-i", input_path,
            *encoder_args,
            "-c:a", "aac", "-b:a", "192k",
            "-map", "0:v:0", "-map", "1:a:0",
            "-shortest",
            output_path
        ]
        self.log_ffmpeg_command(cmd, "Portrait Merge Audio (with progress)")
        result = self._run_ffmpeg_subprocess(cmd)
        if result.returncode != 0:
            print(f"[FFMPEG ERROR] {result.stderr}")
            sys.stdout.flush()
            raise Exception("Audio merge failed")

        progress_callback(1.0)
        debug_log("Portrait conversion complete")
        sys.stdout.flush()
        try:
            os.unlink(temp_video)
        except Exception as e:
            print(f"[WARNING] Failed to cleanup temp video: {e}")
            sys.stdout.flush()
