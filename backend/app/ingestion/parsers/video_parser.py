import re
import os
import logging
import tempfile
from typing import List, Dict, Any, Optional

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None
    np = None
    CV2_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None
    Image = None
    TESSERACT_AVAILABLE = False

logger = logging.getLogger("edupath.ingestion.video")

class VideoParser:
    """
    True Multimodal Video Ingestion Parser.
    Features:
    1. OpenCV Scene-Change Detection: Samples video frames and detects visual transitions
       (slides, blackboard steps, code changes) via downscaled normalized pixel diffs.
    2. Visual Keyframe OCR: Extracts on-screen text, equations, and code from keyframes.
    3. Multimodal Fusion: Fuses visual OCR keyframes with audio transcripts into unified
       timestamped knowledge segments for RAG retrieval and vector embedding.
    """

    # Scene change threshold: normalized delta between consecutive sampled frames (0.0 to 1.0)
    DEFAULT_SCENE_THRESHOLD = 0.32
    # Minimum time between keyframe captures (seconds) to prevent redundant bursts
    MIN_KEYFRAME_INTERVAL_SECONDS = 2.0

    @staticmethod
    def format_timestamp(seconds: int) -> str:
        """Converts integer seconds into MM:SS or HH:MM:SS formatted string."""
        hrs = seconds // 3600
        mins = (seconds % 3600) // 60
        secs = seconds % 60
        if hrs > 0:
            return f"{hrs:02d}:{mins:02d}:{secs:02d}"
        return f"{mins:02d}:{secs:02d}"

    @classmethod
    def is_binary_mp4(cls, file_bytes: bytes) -> bool:
        """Checks if byte payload is a binary MP4 container rather than raw text."""
        if len(file_bytes) < 12:
            return False
        # Check standard ISO Base Media File Format (MP4) box headers
        if b"ftyp" in file_bytes[:32] or b"moov" in file_bytes[:64]:
            return True
        # Check for null bytes indicative of binary media
        null_count = file_bytes[:512].count(b"\x00")
        return null_count > 10

    @classmethod
    def extract_keyframes_and_ocr(
        cls,
        file_bytes: bytes,
        filename: str,
        sample_interval_sec: float = 1.0,
        scene_threshold: float = DEFAULT_SCENE_THRESHOLD
    ) -> List[Dict[str, Any]]:
        """
        Extracts visual keyframes using OpenCV scene change detection and runs OCR.
        
        Scene Detection Algorithm:
        - Downscale frame to 64x64 grayscale (filters noise, accelerates computation).
        - Compute normalized absolute difference: Delta = mean(|Frame_t - Frame_prev|) / 255.0.
        - If Delta > scene_threshold and (t - last_keyframe_t) >= min_interval:
          Capture keyframe, apply adaptive contrast stretching, and run OCR.
        """
        if not CV2_AVAILABLE:
            logger.warning("OpenCV (cv2) is not installed; skipping computer-vision keyframe extraction.")
            return []

        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as temp_video:
            temp_video.write(file_bytes)
            temp_video_path = temp_video.name

        keyframes = []
        try:
            cap = cv2.VideoCapture(temp_video_path)
            if not cap.isOpened():
                logger.warning(f"Failed to open video file {filename} via OpenCV.")
                return []

            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration_sec = total_frames / fps if fps > 0 else 0
            
            logger.info(f"Analyzing {filename}: {total_frames} frames, {fps:.1f} FPS, ~{duration_sec:.1f}s duration.")

            frame_step = max(1, int(fps * sample_interval_sec))
            prev_gray_thumb = None
            last_keyframe_time = -999.0
            frame_idx = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                if frame_idx % frame_step == 0:
                    current_time_sec = frame_idx / fps
                    
                    # 1. Downscale to 64x64 grayscale for fast scene comparison
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    gray_thumb = cv2.resize(gray, (64, 64), interpolation=cv2.INTER_AREA)

                    is_scene_change = False
                    delta = 0.0

                    if prev_gray_thumb is None:
                        # Always capture the initial title slide / introductory scene
                        is_scene_change = True
                        delta = 1.0
                    else:
                        # Normalized mean absolute difference
                        diff = cv2.absdiff(gray_thumb, prev_gray_thumb)
                        delta = float(np.mean(diff)) / 255.0
                        
                        if delta >= scene_threshold and (current_time_sec - last_keyframe_time) >= cls.MIN_KEYFRAME_INTERVAL_SECONDS:
                            is_scene_change = True

                    if is_scene_change:
                        last_keyframe_time = current_time_sec
                        prev_gray_thumb = gray_thumb

                        # 2. Extract OCR text from the keyframe
                        ocr_text = cls._extract_text_from_frame(frame)
                        timestamp_label = cls.format_timestamp(int(current_time_sec))

                        keyframes.append({
                            "timestamp_seconds": int(current_time_sec),
                            "timestamp_formatted": timestamp_label,
                            "delta_score": round(delta, 3),
                            "ocr_text": ocr_text,
                            "has_visual_text": bool(ocr_text and len(ocr_text.strip()) > 5)
                        })

                frame_idx += 1

            cap.release()
            logger.info(f"Extracted {len(keyframes)} visual scene keyframes from {filename}.")
            return keyframes

        except Exception as e:
            logger.error(f"Error during video keyframe extraction on {filename}: {e}", exc_info=True)
            return []
        finally:
            try:
                os.remove(temp_video_path)
            except OSError:
                pass

    @classmethod
    def _extract_text_from_frame(cls, frame_bgr) -> str:
        """Applies adaptive image pre-processing and OCR to extract slide/blackboard text."""
        if not TESSERACT_AVAILABLE or pytesseract is None:
            return ""

        try:
            # Preprocessing: Convert to grayscale and apply contrast enhancement
            gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
            # Contrast Limited Adaptive Histogram Equalization (CLAHE)
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            
            pil_img = Image.fromarray(enhanced)
            raw_text = pytesseract.image_to_string(pil_img, config="--psm 6")
            
            # Clean OCR artifacts
            cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\xff]', '', raw_text).strip()
            return cleaned
        except Exception as e:
            logger.debug(f"OCR extraction on video frame skipped: {e}")
            return ""

    @classmethod
    def parse_transcript_text(cls, transcript_text: str, filename: str) -> List[Dict[str, Any]]:
        """Parses structured transcript text with embedded timestamps into discrete segments."""
        segments = []
        lines = transcript_text.strip().split("\n")
        ts_pattern = re.compile(r'(?:\[|\b)(\d{1,2}:\d{2}(?::\d{2})?)(?:\]|\b)?(?:\s*(?:-|–|-->)\s*(?:\[|\b)?(\d{1,2}:\d{2}(?::\d{2})?)(?:\]|\b)?)?')
        
        current_start = 0
        current_text = []
        
        for line in lines:
            line_str = line.strip()
            if not line_str:
                continue
                
            match = ts_pattern.search(line_str)
            if match:
                if current_text:
                    seg_text = " ".join(current_text).strip()
                    end_sec = current_start + max(30, len(seg_text) // 5)
                    segments.append(cls._build_segment(
                        filename=filename,
                        segment_idx=len(segments) + 1,
                        start_sec=current_start,
                        end_sec=end_sec,
                        text=seg_text
                    ))
                    current_text = []
                    
                ts_str = match.group(1)
                current_start = cls._parse_seconds(ts_str)
                cleaned_line = ts_pattern.sub('', line_str).strip(" :-")
                if cleaned_line:
                    current_text.append(cleaned_line)
            else:
                current_text.append(line_str)
                
        if current_text:
            seg_text = " ".join(current_text).strip()
            end_sec = current_start + max(30, len(seg_text) // 5)
            segments.append(cls._build_segment(
                filename=filename,
                segment_idx=len(segments) + 1,
                start_sec=current_start,
                end_sec=end_sec,
                text=seg_text
            ))
            
        return segments

    @classmethod
    def parse_multimodal_video(
        cls,
        file_bytes: bytes,
        filename: str,
        transcript_override: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Unified Multimodal Video Ingestion Entrypoint:
        1. If transcript text is available, parse timestamped audio stream.
        2. If binary MP4, execute OpenCV scene-detection and OCR keyframe extraction.
        3. Fuse visual and audio representations into rich, searchable multimodal knowledge units.
        """
        is_binary = cls.is_binary_mp4(file_bytes)
        
        # 1. Parse Audio Transcript stream
        transcript_text = transcript_override
        if not transcript_text:
            if not is_binary:
                transcript_text = file_bytes.decode("utf-8", errors="replace")
            else:
                transcript_text = ""

        audio_segments = cls.parse_transcript_text(transcript_text, filename) if transcript_text else []

        # 2. Extract Visual Keyframes via OpenCV & OCR
        visual_keyframes = []
        if is_binary and CV2_AVAILABLE:
            visual_keyframes = cls.extract_keyframes_and_ocr(file_bytes, filename)

        # 3. Multimodal Fusion
        if not audio_segments and not visual_keyframes:
            # Fallback segment if empty video
            return [cls._build_segment(
                filename=filename,
                segment_idx=1,
                start_sec=0,
                end_sec=60,
                text=f"Lecture recording: {filename}"
            )]

        if visual_keyframes and not audio_segments:
            # Construct segments purely from visual keyframes
            fused_segments = []
            for idx, kf in enumerate(visual_keyframes):
                start_s = kf["timestamp_seconds"]
                end_s = start_s + 30
                content = f"[Visual Keyframe Scene at {kf['timestamp_formatted']}]\n{kf['ocr_text']}" if kf.get("ocr_text") else f"Visual slide transition at {kf['timestamp_formatted']}"
                fused_segments.append(cls._build_segment(
                    filename=filename,
                    segment_idx=idx + 1,
                    start_sec=start_s,
                    end_sec=end_s,
                    text=content,
                    has_visual=True,
                    ocr_text=kf.get("ocr_text")
                ))
            return fused_segments

        # Merge visual OCR text into corresponding transcript timestamps
        fused = []
        for seg in audio_segments:
            seg_start = seg["start_seconds"]
            seg_end = seg["end_seconds"]

            # Find keyframes that occurred in this timestamp range
            matching_kfs = [
                kf for kf in visual_keyframes
                if seg_start <= kf["timestamp_seconds"] <= seg_end and kf.get("ocr_text")
            ]

            fused_text = seg["text"]
            if matching_kfs:
                ocr_snippets = "\n".join([f"[Visual On-Screen Text at {kf['timestamp_formatted']}]: {kf['ocr_text']}" for kf in matching_kfs])
                fused_text += f"\n\n{ocr_snippets}"

            fused.append(cls._build_segment(
                filename=filename,
                segment_idx=seg["segment_index"],
                start_sec=seg_start,
                end_sec=seg_end,
                text=fused_text,
                has_visual=len(matching_kfs) > 0,
                ocr_text=matching_kfs[0].get("ocr_text") if matching_kfs else None
            ))

        return fused

    @classmethod
    def _parse_seconds(cls, ts_str: str) -> int:
        parts = [int(p) for p in ts_str.split(":")]
        if len(parts) == 3:
            return parts[0] * 3600 + parts[1] * 60 + parts[2]
        elif len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return 0

    @classmethod
    def _build_segment(
        cls,
        filename: str,
        segment_idx: int,
        start_sec: int,
        end_sec: int,
        text: str,
        has_visual: bool = False,
        ocr_text: Optional[str] = None
    ) -> Dict[str, Any]:
        formatted_start = cls.format_timestamp(start_sec)
        formatted_end = cls.format_timestamp(end_sec)
        label = f"{formatted_start} - {formatted_end}"
        
        return {
            "segment_index": segment_idx,
            "start_seconds": start_sec,
            "end_seconds": end_sec,
            "timestamp_formatted": label,
            "text": text,
            "has_visual_keyframe": has_visual,
            "visual_ocr_text": ocr_text,
            "source": {
                "type": "video",
                "file": filename,
                "timestamp_start": start_sec,
                "timestamp_end": end_sec,
                "timestamp_formatted": label,
                "has_visual_keyframe": has_visual,
                "citation_label": f"Lecture Video — {formatted_start}"
            }
        }

