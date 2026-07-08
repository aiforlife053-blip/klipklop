import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
from openai import APIConnectionError, APIError, APIStatusError, RateLimitError

from clipper_shared import SUBPROCESS_FLAGS, SubtitleNotFoundError, YTDLP_MODULE_AVAILABLE, _hex_to_rgb, yt_dlp
from utils.helpers import get_deno_path, get_ffmpeg_path, is_ytdlp_module_available
from utils.logger import debug_log


class PortraitMixin:
    def convert_to_portrait(self, input_path: str, output_path: str):
        """Convert landscape to 9:16 portrait with speaker tracking (router method)"""
        try:
            if self.face_tracking_mode == "mediapipe":
                self.log("  Using MediaPipe (Active Speaker Detection)")
                return self.convert_to_portrait_mediapipe(input_path, output_path)
            else:
                self.log("  Using OpenCV (Fast Mode)")
                return self.convert_to_portrait_opencv(input_path, output_path)
        except Exception as e:
            # Fallback to OpenCV if MediaPipe fails
            if self.face_tracking_mode == "mediapipe":
                self.log(f"  ⚠ MediaPipe failed: {e}")
                self.log("  Falling back to OpenCV mode...")
                return self.convert_to_portrait_opencv(input_path, output_path)
            else:
                raise

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
        out_w, out_h = 1080, 1920
        
        # Face detector
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        use_faces = not face_cascade.empty()
        
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
        
        cap.release()
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

    def _init_mediapipe(self):
        """Initialize MediaPipe Face Mesh (lazy loading)"""
        if self.mp_face_mesh is None:
            try:
                import mediapipe as mp
                self.mp_face_mesh = mp.solutions.face_mesh
                self.mp_drawing = mp.solutions.drawing_utils
                self.log("  MediaPipe initialized successfully")
            except ImportError:
                raise Exception("MediaPipe not installed. Run: pip install mediapipe")

    def convert_to_portrait_mediapipe(self, input_path: str, output_path: str):
        """Convert landscape to 9:16 portrait with active speaker detection (MediaPipe)"""
        
        # Initialize MediaPipe
        self._init_mediapipe()
        
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise Exception(f"Failed to open video: {input_path}")
        
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        if total_frames == 0 or fps == 0:
            cap.release()
            raise Exception(f"Invalid video properties: {total_frames} frames, {fps} fps")
        
        # Calculate crop dimensions
        target_ratio = 9 / 16
        crop_w = int(orig_h * target_ratio)
        crop_h = orig_h
        out_w, out_h = 1080, 1920
        
        # MediaPipe Face Mesh settings
        lip_threshold = self.mediapipe_settings.get("lip_activity_threshold", 0.15)
        switch_threshold = self.mediapipe_settings.get("switch_threshold", 0.3)
        min_shot_duration = self.mediapipe_settings.get("min_shot_duration", 90)
        center_weight = self.mediapipe_settings.get("center_weight", 0.3)
        
        # First pass: analyze frames with MediaPipe
        self.log("  Pass 1: Analyzing lip movements...")
        crop_positions = []
        face_activities = []  # Store activity scores per frame
        
        with self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=3,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as face_mesh:
            
            frame_count = 0
            prev_lip_distances = {}  # Track previous lip distances per face
            
            while True:
                if self.is_cancelled():
                    cap.release()
                    raise Exception("Cancelled by user")
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Convert to RGB for MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb_frame)
                
                best_face_x = orig_w / 2  # Default to center
                max_activity = 0
                
                if results.multi_face_landmarks:
                    faces_data = []
                    
                    for face_id, face_landmarks in enumerate(results.multi_face_landmarks):
                        # Calculate lip activity
                        activity = self._calculate_lip_activity(
                            face_landmarks, 
                            orig_w, 
                            orig_h,
                            prev_lip_distances.get(face_id, None)
                        )
                        
                        # Get face center position
                        face_x = face_landmarks.landmark[1].x * orig_w  # Nose tip
                        
                        # Calculate combined score (activity + center position)
                        center_score = 1.0 - abs(face_x - orig_w / 2) / (orig_w / 2)
                        combined_score = (activity * (1 - center_weight)) + (center_score * center_weight)
                        
                        faces_data.append({
                            'x': face_x,
                            'activity': activity,
                            'combined_score': combined_score
                        })
                        
                        # Update previous lip distance
                        upper_lip = face_landmarks.landmark[13]  # Upper lip center
                        lower_lip = face_landmarks.landmark[14]  # Lower lip center
                        lip_distance = abs(upper_lip.y - lower_lip.y)
                        prev_lip_distances[face_id] = lip_distance
                    
                    # Select face with highest combined score
                    if faces_data:
                        best_face = max(faces_data, key=lambda f: f['combined_score'])
                        best_face_x = best_face['x']
                        max_activity = best_face['activity']
                
                # Calculate crop position
                crop_x = int(best_face_x - crop_w / 2)
                crop_x = max(0, min(crop_x, orig_w - crop_w))
                crop_positions.append(crop_x)
                face_activities.append(max_activity)
                
                frame_count += 1
                
                if frame_count % 30 == 0:
                    self.log(f"    Analyzed {frame_count}/{total_frames} frames...")
        
        self.log(f"  Analyzed {frame_count} frames with MediaPipe")
        
        # Stabilize positions with shot-based switching
        crop_positions = self._stabilize_positions_with_activity(
            crop_positions, 
            face_activities,
            min_shot_duration,
            switch_threshold
        )
        
        # Second pass: create video
        self.log("  Pass 2: Creating portrait video...")
        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        temp_video = tempfile.NamedTemporaryFile(suffix='.mp4', delete=False).name
        
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(temp_video, fourcc, fps, (out_w, out_h))
        
        if not out.isOpened():
            cap.release()
            raise Exception(f"Failed to create VideoWriter: {temp_video}")
        
        frame_idx = 0
        while True:
            if self.is_cancelled():
                cap.release()
                out.release()
                try:
                    os.unlink(temp_video)
                except:
                    pass
                raise Exception("Cancelled by user")
            
            ret, frame = cap.read()
            if not ret:
                break
            
            crop_x = crop_positions[frame_idx] if frame_idx < len(crop_positions) else crop_positions[-1]
            cropped = frame[0:crop_h, crop_x:crop_x+crop_w]
            resized = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
            out.write(resized)
            
            frame_idx += 1
            
            if frame_idx % 30 == 0:
                self.log(f"    Created {frame_idx}/{total_frames} frames...")
        
        cap.release()
        out.release()
        
        # Verify temp video was created
        if not os.path.exists(temp_video) or os.path.getsize(temp_video) < 1000:
            raise Exception(f"Failed to create temp video: {temp_video}")
        
        # Merge with audio using GPU/CPU encoder
        self.log("  Pass 3: Merging audio...")
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
        self.log_ffmpeg_command(cmd, "Portrait Merge Audio (MediaPipe)")
        self._run_ffmpeg_subprocess(cmd)
        
        # Cleanup
        try:
            os.unlink(temp_video)
        except:
            pass

    def _calculate_lip_activity(self, face_landmarks, frame_width, frame_height, prev_lip_distance=None):
        """Calculate lip movement activity score"""
        
        # Key lip landmarks (MediaPipe Face Mesh indices)
        # Upper lip: 13, Lower lip: 14
        upper_lip = face_landmarks.landmark[13]
        lower_lip = face_landmarks.landmark[14]
        
        # Mouth corners: 61 (left), 291 (right)
        mouth_left = face_landmarks.landmark[61]
        mouth_right = face_landmarks.landmark[291]
        
        # Calculate mouth openness (vertical distance)
        mouth_height = abs(upper_lip.y - lower_lip.y)
        
        # Calculate mouth width (horizontal distance)
        mouth_width = abs(mouth_left.x - mouth_right.x)
        
        # Aspect ratio (height/width) - higher when mouth is open
        if mouth_width > 0:
            aspect_ratio = mouth_height / mouth_width
        else:
            aspect_ratio = 0
        
        # Calculate movement delta (change from previous frame)
        delta = 0
        if prev_lip_distance is not None:
            delta = abs(mouth_height - prev_lip_distance)
        
        # Activity score: combination of openness and movement
        # Weight movement more heavily (0.6) than static openness (0.4)
        activity_score = (aspect_ratio * 0.4) + (delta * 0.6)
        
        return activity_score

    def _stabilize_positions_with_activity(self, positions, activities, min_shot_duration, switch_threshold):
        """Stabilize crop positions based on activity scores"""
        if not positions:
            return positions
        
        # First pass: smooth positions with moving median
        window_size = 30
        smoothed = []
        
        for i in range(len(positions)):
            start = max(0, i - window_size // 2)
            end = min(len(positions), i + window_size // 2)
            window = positions[start:end]
            smoothed.append(int(np.median(window)))
        
        # Second pass: lock positions per shot based on activity
        final = []
        shot_start = 0
        current_position = smoothed[0] if smoothed else 0
        
        for i in range(len(smoothed)):
            frames_since_switch = i - shot_start
            
            # Only allow switch if:
            # 1. Minimum shot duration has passed
            # 2. Position changed significantly
            # 3. Activity is high enough (speaker is talking)
            if frames_since_switch >= min_shot_duration:
                position_diff = abs(smoothed[i] - current_position)
                activity = activities[i] if i < len(activities) else 0
                
                # Switch if position changed significantly AND there's activity
                if position_diff > 200 and activity > switch_threshold:
                    # Lock previous shot
                    shot_positions = smoothed[shot_start:i]
                    if shot_positions:
                        shot_median = int(np.median(shot_positions))
                        final.extend([shot_median] * len(shot_positions))
                    
                    shot_start = i
                    current_position = smoothed[i]
        
        # Handle last shot
        shot_positions = smoothed[shot_start:]
        if shot_positions:
            shot_median = int(np.median(shot_positions))
            final.extend([shot_median] * len(shot_positions))
        
        return final if final else smoothed

    def convert_to_portrait_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Convert landscape to 9:16 portrait with speaker tracking and progress (router method)"""
        try:
            if getattr(self, "landscape_blur", False) and self._is_landscape(input_path):
                self.log("  Using moving blur background")
                return self.convert_to_portrait_blur_with_progress(input_path, output_path, progress_callback)
            if self.face_tracking_mode == "mediapipe":
                self.log("  Using MediaPipe (Active Speaker Detection)")
                return self.convert_to_portrait_mediapipe_with_progress(input_path, output_path, progress_callback)
            if self.face_tracking_mode == "center":
                self.log("  Using fast center crop")
                return self.convert_to_portrait_center(input_path, output_path, progress_callback)
            self.log("  Using OpenCV (Fast Mode)")
            return self.convert_to_portrait_opencv_with_progress(input_path, output_path, progress_callback)
        except Exception as e:
            # Fallback to OpenCV if MediaPipe fails
            if self.face_tracking_mode == "mediapipe":
                self.log(f"  ⚠ MediaPipe failed: {e}")
                self.log("  Falling back to OpenCV mode...")
                return self.convert_to_portrait_opencv_with_progress(input_path, output_path, progress_callback)
            else:
                raise

    def _is_landscape(self, input_path: str) -> bool:
        cap = cv2.VideoCapture(input_path)
        try:
            return int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) > int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        finally:
            cap.release()

    def convert_to_portrait_blur_with_progress(self, input_path: str, output_path: str, progress_callback):
        width, height = (int(part) for part in getattr(self, "output_resolution", "720:1280").split(":"))
        blur_settings = getattr(self, "blur_background_settings", {}) or {}
        zoom = max(1.0, min(1.4, float(blur_settings.get("zoom", 1.08) or 1.08)))
        strength = max(10, min(60, int(blur_settings.get("strength", 30) or 30)))
        foreground_width = int(width * zoom)
        filter_complex = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},boxblur={strength}:3[bg];"
            f"[0:v]scale={foreground_width}:-2[fg];"
            f"[bg][fg]overlay=(W-w)/2:(H-h)/2"
        )
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-filter_complex", filter_complex,
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "copy",
            output_path,
        ]
        result = self._run_ffmpeg_subprocess(cmd)
        if result.returncode != 0:
            raise Exception(f"Blur portrait failed: {result.stderr}")
        progress_callback(1.0)

    def convert_to_portrait_center(self, input_path: str, output_path: str, progress_callback):
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", input_path,
            "-vf", f"crop=ih*9/16:ih:(iw-ih*9/16)/2:0,scale={getattr(self, 'output_resolution', '720:1280')}",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "23",
            "-c:a", "copy",
            output_path,
        ]
        result = self._run_ffmpeg_subprocess(cmd)
        if result.returncode != 0:
            raise Exception(f"Center crop failed: {result.stderr}")
        progress_callback(1.0)

    def convert_to_portrait_opencv_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Convert landscape to 9:16 portrait with speaker tracking and progress (OpenCV)"""
        
        self.log("[DEBUG] Starting portrait conversion...")
        print("[DEBUG] Starting portrait conversion...")
        print(f"[DEBUG] Input: {input_path}")
        print(f"[DEBUG] Output: {output_path}")
        sys.stdout.flush()
        
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise Exception(f"Failed to open video: {input_path}")
        
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        self.log(f"[DEBUG] Video: {orig_w}x{orig_h}, {fps}fps, {total_frames} frames")
        print(f"[DEBUG] Video: {orig_w}x{orig_h}, {fps}fps, {total_frames} frames")
        sys.stdout.flush()
        
        if total_frames == 0 or fps == 0:
            cap.release()
            raise Exception(f"Invalid video properties: {total_frames} frames, {fps} fps")
        
        # Calculate crop dimensions
        target_ratio = 9 / 16
        crop_w = int(orig_h * target_ratio)
        crop_h = orig_h
        out_w, out_h = 1080, 1920
        
        # Face detector
        face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + 'haarcascade_frontalface_default.xml'
        )
        use_faces = not face_cascade.empty()
        
        # First pass: analyze frames (0-40%)
        print("[DEBUG] Pass 1: Analyzing frames...")
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
                print(f"[DEBUG] Pass 1 progress: {progress*100:.1f}% ({frame_count}/{total_frames} frames)")
                sys.stdout.flush()
                progress_callback(progress)
                last_log_time = current_time
        
        print(f"[DEBUG] Analyzed {frame_count} frames")
        
        # Stabilize positions
        crop_positions = self.stabilize_positions(crop_positions)
        progress_callback(0.45)
        
        # Second pass: create video (45-85%)
        print("[DEBUG] Pass 2: Creating portrait video...")
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
                print(f"[DEBUG] Pass 2 progress: {progress*100:.1f}% ({frame_idx}/{total_frames} frames)")
                sys.stdout.flush()
                progress_callback(progress)
                last_log_time = current_time
        
        print(f"[DEBUG] Created {frame_idx} frames")
        sys.stdout.flush()
        
        cap.release()
        print("[DEBUG] Released VideoCapture")
        sys.stdout.flush()
        
        out.release()
        print("[DEBUG] Released VideoWriter")
        sys.stdout.flush()
        
        # Verify temp video was created
        if not os.path.exists(temp_video) or os.path.getsize(temp_video) < 1000:
            raise Exception(f"Failed to create temp video: {temp_video}")
        
        print(f"[DEBUG] Temp video size: {os.path.getsize(temp_video)} bytes")
        sys.stdout.flush()
        
        progress_callback(0.85)
        
        # Merge with audio (85-100%) using GPU/CPU encoder
        print("[DEBUG] Pass 3: Merging audio...")
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
        print(f"[DEBUG] Running audio merge command...")
        sys.stdout.flush()
        
        self.log_ffmpeg_command(cmd, "Portrait Merge Audio (with progress)")
        result = self._run_ffmpeg_subprocess(cmd)
        
        if result.returncode != 0:
            print(f"[FFMPEG ERROR] {result.stderr}")
            sys.stdout.flush()
            raise Exception("Audio merge failed")
        
        print("[DEBUG] Audio merge complete")
        sys.stdout.flush()
        
        progress_callback(1.0)
        print("[DEBUG] Portrait conversion complete")
        sys.stdout.flush()
        
        # Cleanup temp video
        try:
            os.unlink(temp_video)
            print("[DEBUG] Cleaned up temp video")
            sys.stdout.flush()
        except Exception as e:
            print(f"[WARNING] Failed to cleanup temp video: {e}")
            sys.stdout.flush()

    def convert_to_portrait_mediapipe_with_progress(self, input_path: str, output_path: str, progress_callback):
        """Convert landscape to 9:16 portrait with active speaker detection and progress (MediaPipe)"""
        
        # Initialize MediaPipe
        self._init_mediapipe()
        
        self.log("[DEBUG] Starting MediaPipe portrait conversion...")
        print("[DEBUG] Starting MediaPipe portrait conversion...")
        sys.stdout.flush()
        
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise Exception(f"Failed to open video: {input_path}")
        
        orig_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        orig_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        self.log(f"[DEBUG] Video: {orig_w}x{orig_h}, {fps}fps, {total_frames} frames")
        print(f"[DEBUG] Video: {orig_w}x{orig_h}, {fps}fps, {total_frames} frames")
        sys.stdout.flush()
        
        if total_frames == 0 or fps == 0:
            cap.release()
            raise Exception(f"Invalid video properties: {total_frames} frames, {fps} fps")
        
        # Calculate crop dimensions
        target_ratio = 9 / 16
        crop_w = int(orig_h * target_ratio)
        crop_h = orig_h
        out_w, out_h = 1080, 1920
        
        # MediaPipe settings
        lip_threshold = self.mediapipe_settings.get("lip_activity_threshold", 0.15)
        switch_threshold = self.mediapipe_settings.get("switch_threshold", 0.3)
        min_shot_duration = self.mediapipe_settings.get("min_shot_duration", 90)
        center_weight = self.mediapipe_settings.get("center_weight", 0.3)
        
        # First pass: analyze frames with MediaPipe (0-40%)
        print("[DEBUG] Pass 1: Analyzing lip movements with MediaPipe...")
        sys.stdout.flush()
        
        crop_positions = []
        face_activities = []
        frame_count = 0
        last_log_time = 0
        import time
        
        with self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=3,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5
        ) as face_mesh:
            
            prev_lip_distances = {}
            
            while True:
                if self.is_cancelled():
                    cap.release()
                    raise Exception("Cancelled by user")
                
                ret, frame = cap.read()
                if not ret:
                    break
                
                # Convert to RGB for MediaPipe
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb_frame)
                
                best_face_x = orig_w / 2
                max_activity = 0
                
                if results.multi_face_landmarks:
                    faces_data = []
                    
                    for face_id, face_landmarks in enumerate(results.multi_face_landmarks):
                        # Calculate lip activity
                        activity = self._calculate_lip_activity(
                            face_landmarks,
                            orig_w,
                            orig_h,
                            prev_lip_distances.get(face_id, None)
                        )
                        
                        # Get face center position
                        face_x = face_landmarks.landmark[1].x * orig_w
                        
                        # Combined score
                        center_score = 1.0 - abs(face_x - orig_w / 2) / (orig_w / 2)
                        combined_score = (activity * (1 - center_weight)) + (center_score * center_weight)
                        
                        faces_data.append({
                            'x': face_x,
                            'activity': activity,
                            'combined_score': combined_score
                        })
                        
                        # Update previous lip distance
                        upper_lip = face_landmarks.landmark[13]
                        lower_lip = face_landmarks.landmark[14]
                        lip_distance = abs(upper_lip.y - lower_lip.y)
                        prev_lip_distances[face_id] = lip_distance
                    
                    if faces_data:
                        best_face = max(faces_data, key=lambda f: f['combined_score'])
                        best_face_x = best_face['x']
                        max_activity = best_face['activity']
                
                crop_x = int(best_face_x - crop_w / 2)
                crop_x = max(0, min(crop_x, orig_w - crop_w))
                crop_positions.append(crop_x)
                face_activities.append(max_activity)
                
                frame_count += 1
                
                current_time = time.time()
                if frame_count % 30 == 0 or (current_time - last_log_time) > 2:
                    progress = (frame_count / total_frames) * 0.4
                    print(f"[DEBUG] Pass 1 progress: {progress*100:.1f}% ({frame_count}/{total_frames} frames)")
                    sys.stdout.flush()
                    progress_callback(progress)
                    last_log_time = current_time
        
        print(f"[DEBUG] Analyzed {frame_count} frames with MediaPipe")
        sys.stdout.flush()
        
        # Stabilize positions (40-45%)
        progress_callback(0.4)
        crop_positions = self._stabilize_positions_with_activity(
            crop_positions,
            face_activities,
            min_shot_duration,
            switch_threshold
        )
        progress_callback(0.45)
        
        # Second pass: create video (45-85%)
        print("[DEBUG] Pass 2: Creating portrait video...")
        sys.stdout.flush()
        
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
        
        while True:
            if self.is_cancelled():
                cap.release()
                out.release()
                try:
                    os.unlink(temp_video)
                except:
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
            cropped = frame[0:crop_h, crop_x:crop_x+crop_w]
            resized = cv2.resize(cropped, (out_w, out_h), interpolation=cv2.INTER_LANCZOS4)
            
            success = out.write(resized)
            if not success:
                print(f"[WARNING] Failed to write frame {frame_idx}")
                sys.stdout.flush()
            
            frame_idx += 1
            
            if frame_idx % 30 == 0 or (current_time - last_log_time) > 2:
                progress = 0.45 + (frame_idx / total_frames) * 0.4
                print(f"[DEBUG] Pass 2 progress: {progress*100:.1f}% ({frame_idx}/{total_frames} frames)")
                sys.stdout.flush()
                progress_callback(progress)
                last_log_time = current_time
        
        print(f"[DEBUG] Created {frame_idx} frames")
        sys.stdout.flush()
        
        cap.release()
        out.release()
        
        if not os.path.exists(temp_video) or os.path.getsize(temp_video) < 1000:
            raise Exception(f"Failed to create temp video: {temp_video}")
        
        print(f"[DEBUG] Temp video size: {os.path.getsize(temp_video)} bytes")
        sys.stdout.flush()
        
        progress_callback(0.85)
        
        # Merge with audio (85-100%) using GPU/CPU encoder
        print("[DEBUG] Pass 3: Merging audio...")
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
        
        self.log_ffmpeg_command(cmd, "MediaPipe Portrait Merge Audio")
        result = self._run_ffmpeg_subprocess(cmd)
        
        if result.returncode != 0:
            print(f"[FFMPEG ERROR] {result.stderr}")
            sys.stdout.flush()
            raise Exception("Audio merge failed")
        
        print("[DEBUG] Audio merge complete")
        sys.stdout.flush()
        
        progress_callback(1.0)
        print("[DEBUG] MediaPipe portrait conversion complete")
        sys.stdout.flush()
        
        # Cleanup
        try:
            os.unlink(temp_video)
            print("[DEBUG] Cleaned up temp video")
            sys.stdout.flush()
        except Exception as e:
            print(f"[WARNING] Failed to cleanup temp video: {e}")
            sys.stdout.flush()
