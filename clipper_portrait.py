import os
import sys
import tempfile
import time

import cv2
import numpy as np

from clipper_base import ClipperBase
from utils.logger import debug_log


def hold_render_frame(current, previous, hold: bool):
    """Never freeze video; camera stability comes from crop positions."""
    return current, current.copy()


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
        """V3 Vertical Full: active-speaker crop with stable hard cuts."""
        self.log("  Using active-speaker face crop")
        return self.convert_to_portrait_opencv_with_progress(input_path, output_path, progress_callback)

    def convert_to_portrait_static_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Convert landscape to fixed 9:16 center crop without per-frame tracking."""
        cap = cv2.VideoCapture(input_path)
        try:
            if not cap.isOpened():
                raise Exception(f"Failed to open video: {input_path}")
            orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            if orig_w <= 0 or orig_h <= 0:
                raise Exception("Invalid video dimensions")
        finally:
            cap.release()

        crop_w = min(orig_w, int(orig_h * 9 / 16))
        crop_w = max(2, crop_w - crop_w % 2)
        crop_x = max(0, (orig_w - crop_w) // 2)
        out_w, out_h = self._get_target_portrait_dims(orig_w, orig_h)
        duration = self._video_duration(input_path)
        command = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-vf", f"crop={crop_w}:{orig_h}:{crop_x}:0,scale={out_w}:{out_h}:flags=lanczos,setsar=1",
            *self.get_video_encoder_args(),
            "-an",
            output_path,
        ]
        self.run_ffmpeg_with_progress(command, duration, progress_callback)
        return output_path

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

    def convert_to_portrait_opencv_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Convert landscape to 9:16 portrait with active-speaker crop (OpenCV)."""

        debug_log("Starting portrait conversion...")
        debug_log(f"Input: {input_path}")
        debug_log(f"Output: {output_path}")
        sys.stdout.flush()

        from speaker_tracking import tracking_strategy

        try:
            tracker, supports_layouts = tracking_strategy()
            tracking = tracker(input_path)
        except Exception as exc:
            raise Exception(f"Active-speaker crop failed: {exc}") from exc

        crop_positions = tracking["crop_positions"]
        hold_frames = tracking.get("hold_frames") or [False] * len(crop_positions)
        layouts = tracking.get("layouts") if supports_layouts else None
        layouts = layouts or ["crop"] * len(crop_positions)
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
        last_visible_frame = None

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
            layout = layouts[frame_idx] if frame_idx < len(layouts) else layouts[-1]
            if layout == "contain_blur":
                bg_scale = max(out_w / orig_w, out_h / orig_h)
                bg_w, bg_h = int(round(orig_w * bg_scale)), int(round(orig_h * bg_scale))
                background = cv2.resize(frame, (bg_w, bg_h), interpolation=cv2.INTER_LINEAR)
                bg_x, bg_y = (bg_w - out_w) // 2, (bg_h - out_h) // 2
                resized = cv2.GaussianBlur(background[bg_y:bg_y + out_h, bg_x:bg_x + out_w], (0, 0), 24)
                fg_scale = min(out_w / orig_w, out_h / orig_h)
                fg_w, fg_h = int(round(orig_w * fg_scale)), int(round(orig_h * fg_scale))
                foreground = cv2.resize(frame, (fg_w, fg_h), interpolation=cv2.INTER_LANCZOS4)
                fg_x, fg_y = (out_w - fg_w) // 2, (out_h - fg_h) // 2
                resized[fg_y:fg_y + fg_h, fg_x:fg_x + fg_w] = foreground
            else:
                crop_x = crop_positions[frame_idx] if frame_idx < len(crop_positions) else crop_positions[-1]
                crop_x = max(0, min(int(crop_x), max(0, orig_w - crop_w)))
                cropped = frame[0:crop_h, crop_x:crop_x + crop_w]
                resized = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
            hold = hold_frames[frame_idx] if frame_idx < len(hold_frames) else False
            resized, last_visible_frame = hold_render_frame(resized, last_visible_frame, hold)
            out.write(resized)

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
