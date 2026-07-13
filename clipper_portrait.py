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

    def convert_to_portrait(self, input_path: str, output_path: str):
        """Convert landscape to 9:16 portrait with speaker tracking (router method)"""
        if self.face_tracking_mode == "center":
            self.log("  Using fast center crop")
            return self.convert_to_portrait_center(input_path, output_path, lambda _: None)
        self.log("  Using OpenCV (Fast Mode)")
        return self.convert_to_portrait_opencv(input_path, output_path)

    def convert_to_portrait_opencv(self, input_path: str, output_path: str):
        """Convert landscape to 9:16 portrait with speaker tracking (OpenCV Haar Cascade)"""

        cap = cv2.VideoCapture(input_path)
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Calculate crop dimensions
        target_ratio = 9 / 16
        crop_w = int(orig_h * target_ratio)
        crop_h = orig_h
        out_w, out_h = self._get_target_portrait_dims(orig_w, orig_h)

        # Face detector
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        use_faces = not face_cascade.empty()

        try:
            # First pass: analyze frames
            crop_positions = []
            current_target = orig_w / 2

            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                if use_faces:
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))

                    if len(faces) > 0:
                        # Find largest face
                        largest = max(faces, key=lambda f: f[2] * f[3])
                        current_target = largest[0] + largest[2] / 2

                crop_x = int(current_target - crop_w / 2)
                crop_x = max(0, min(crop_x, orig_w - crop_w))
                crop_positions.append(crop_x)

            # Stabilize positions
            crop_positions = self.stabilize_positions(crop_positions)

            # Second pass: create video
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name

            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(temp_video, fourcc, fps, (out_w, out_h))

            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                crop_x = crop_positions[frame_idx] if frame_idx < len(crop_positions) else crop_positions[-1]
                cropped = frame[0:crop_h, crop_x:crop_x+crop_w]
                resized = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
                out.write(resized)
                frame_idx += 1
        finally:
            cap.release()
            if 'out' in locals():
                out.release()

        # Merge with audio using GPU/CPU encoder
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
        self.log_ffmpeg_command(cmd, "Portrait Merge Audio (OpenCV)")
        self._run_ffmpeg_subprocess(cmd)
        os.unlink(temp_video)

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
            self.log("  Using fast center crop")
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

    def _preview_blur_filter(self, width: int, height: int) -> str:
        blur_settings = getattr(self, "blur_background_settings", {}) or {}
        zoom = max(1.0, min(3.0, float(blur_settings.get("zoom", 1.08) or 1.08)))
        strength = max(0, min(100, int(blur_settings.get("strength", 30))))
        scale = max(0.5, min(1.5, float(blur_settings.get("scale", 1.0) or 1.0)))
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
            "-an",
            "-progress", "pipe:1",
            output_path,
        ]
        self.run_ffmpeg_with_progress(cmd, self._video_duration(input_path), progress_callback)
        if not os.path.exists(output_path):
            raise Exception("Blur portrait failed: output file not found")

    def convert_to_portrait_center(self, input_path: str, output_path: str, progress_callback):
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-vf", f"scale={getattr(self, 'output_resolution', '720:1280')}:force_original_aspect_ratio=increase,crop={getattr(self, 'output_resolution', '720:1280')},setsar=1",
            *self.get_video_encoder_args(),
            "-an",
            "-progress", "pipe:1",
            output_path,
        ]
        self.run_ffmpeg_with_progress(cmd, self._video_duration(input_path), progress_callback)
        if not os.path.exists(output_path):
            raise Exception("Center crop failed: output file not found")

    def convert_to_portrait_opencv_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Convert landscape to 9:16 portrait with speaker tracking and progress (OpenCV)"""

        debug_log("Starting portrait conversion...")
        debug_log("Starting portrait conversion...")
        debug_log(f"Input: {input_path}")
        debug_log(f"Output: {output_path}")
        sys.stdout.flush()

        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise Exception(f"Failed to open video: {input_path}")

        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        debug_log(f"Video: {orig_w}x{orig_h}, {fps}fps, {total_frames} frames")
        debug_log(f"Video: {orig_w}x{orig_h}, {fps}fps, {total_frames} frames")
        sys.stdout.flush()

        if total_frames == 0 or fps == 0:
            cap.release()
            raise Exception(f"Invalid video properties: {total_frames} frames, {fps} fps")

        # Calculate crop dimensions
        target_ratio = 9 / 16
        crop_w = int(orig_h * target_ratio)
        crop_h = orig_h
        out_w, out_h = self._get_target_portrait_dims(orig_w, orig_h)

        # Face detector
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        use_faces = not face_cascade.empty()

        # First pass: analyze frames (0-40%)
        debug_log("Pass 1: Analyzing frames...")
        sys.stdout.flush()

        crop_positions = []
        current_target = orig_w / 2
        frame_count = 0
        last_log_time = 0
        import time

        while True:
            # Check for cancellation
            if self.is_cancelled():
                cap.release()
                raise Exception("Cancelled by user")

            ret, frame = cap.read()
            if not ret:
                break

            if use_faces:
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                faces = face_cascade.detectMultiScale(gray, 1.1, 5, minSize=(50, 50))

                if len(faces) > 0:
                    # Find largest face
                    largest = max(faces, key=lambda f: f[2] * f[3])
                    current_target = largest[0] + largest[2] / 2

            crop_x = int(current_target - crop_w / 2)
            crop_x = max(0, min(crop_x, orig_w - crop_w))
            crop_positions.append(crop_x)

            frame_count += 1

            # Update progress more frequently with time-based logging
            current_time = time.time()
            if frame_count % 30 == 0 or (current_time - last_log_time) > 2:  # Every 30 frames or 2 seconds
                progress = (frame_count / total_frames) * 0.4  # 0-40%
                debug_log(f"Pass 1 progress: {progress*100:.1f}% ({frame_count}/{total_frames} frames)")
                sys.stdout.flush()
                progress_callback(progress)
                last_log_time = current_time

        debug_log(f"Analyzed {frame_count} frames")

        # Stabilize positions
        crop_positions = self.stabilize_positions(crop_positions)
        progress_callback(0.45)

        # Second pass: create video (45-85%)
        debug_log("Pass 2: Creating portrait video...")
        sys.stdout.flush()  # Force output

        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_video, fourcc, fps, (out_w, out_h))

        if not out.isOpened():
            cap.release()
            raise Exception(f"Failed to create VideoWriter: {temp_video}")

        frame_idx = 0
        last_log_time = 0
        last_frame_time = time.time()
        import time

        while True:
            # Check for cancellation
            if self.is_cancelled():
                cap.release()
                out.release()
                try:
                    os.unlink(temp_video)
                except:
                    pass
                raise Exception("Cancelled by user")

            # Watchdog: check if we're stuck (no frame processed in 30 seconds)
            current_time = time.time()
            if current_time - last_frame_time > 30:
                cap.release()
                out.release()
                raise Exception(f"Portrait conversion timeout: stuck at frame {frame_idx}/{total_frames}")

            ret, frame = cap.read()
            if not ret:
                break

            last_frame_time = current_time  # Update watchdog timer

            crop_x = crop_positions[frame_idx] if frame_idx < len(crop_positions) else crop_positions[-1]
            cropped = frame[0:crop_h, crop_x:crop_x+crop_w]
            resized = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)

            # Write frame with error checking
            success = out.write(resized)
            if not success:
                print(f"[WARNING] Failed to write frame {frame_idx}")
                sys.stdout.flush()

            frame_idx += 1

            # Update progress more frequently and with time-based logging
            if frame_idx % 30 == 0 or (current_time - last_log_time) > 2:  # Every 30 frames or 2 seconds
                progress = 0.45 + (frame_idx / total_frames) * 0.4  # 45-85%
                debug_log(f"Pass 2 progress: {progress*100:.1f}% ({frame_idx}/{total_frames} frames)")
                sys.stdout.flush()
                progress_callback(progress)
                last_log_time = current_time

        debug_log(f"Created {frame_idx} frames")
        sys.stdout.flush()

        cap.release()
        debug_log("Released VideoCapture")
        sys.stdout.flush()

        out.release()
        debug_log("Released VideoWriter")
        sys.stdout.flush()

        # Verify temp video was created
        if not os.path.exists(temp_video) or os.path.getsize(temp_video) < 1000:
            raise Exception(f"Failed to create temp video: {temp_video}")

        debug_log(f"Temp video size: {os.path.getsize(temp_video)} bytes")
        sys.stdout.flush()

        progress_callback(0.85)

        # Merge with audio (85-100%) using GPU/CPU encoder
        debug_log("Pass 3: Merging audio...")
        sys.stdout.flush()

        duration = total_frames / fps if fps > 0 else 60
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

        # Run without progress parsing for audio merge (quick operation)
        debug_log(f"Running audio merge command...")
        sys.stdout.flush()

        self.log_ffmpeg_command(cmd, "Portrait Merge Audio (with progress)")
        result = self._run_ffmpeg_subprocess(cmd)

        if result.returncode != 0:
            print(f"[FFMPEG ERROR] {result.stderr}")
            sys.stdout.flush()
            raise Exception("Audio merge failed")

        debug_log("Audio merge complete")
        sys.stdout.flush()

        progress_callback(1.0)
        debug_log("Portrait conversion complete")
        sys.stdout.flush()

        # Cleanup temp video
        try:
            os.unlink(temp_video)
            debug_log("Cleaned up temp video")
            sys.stdout.flush()
        except Exception as e:
            print(f"[WARNING] Failed to cleanup temp video: {e}")
            sys.stdout.flush()

