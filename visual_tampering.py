"""
visual_tampering.py
Universal Visual Tampering Detector for Company OCR Service.

Detects image-level visual anomalies using OpenCV, PIL, and NumPy:
- Pasted white patches / masking boxes (sharp uniform rectangular patches on textured backgrounds).
- Cloned stamps or duplicate circular/rectangular seals.
- Font inconsistencies (abnormal font size or stroke variations across lines).
- Compression artifacts (Error Level Analysis heuristic for JPEG re-save discrepancies).
- Blurred edited regions (localized Laplacian variance drops indicating smoothing/erasure).
- Cut-and-paste edge discontinuities.

Zero LLM dependency. 100% local computer vision execution.
Objective Terminology Invariant:
Never use the words "Fake", "Forged", or "Fraudulent".
Use objective phrasing: "Review Required", "Visible inconsistencies detected".
"""

import io
import logging
from typing import Any, Dict, List, Optional
from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageStat

logger = logging.getLogger("company_ocr.visual_tampering")

try:
    import numpy as np
except ImportError:
    np = None

try:
    import cv2
except ImportError:
    cv2 = None


class VisualTamperingChecker:
    """Universal visual tampering detector using computer vision heuristics."""

    @classmethod
    def check_visual(
        cls,
        image: Optional[Image.Image],
        ocr_lines: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Runs all local visual tampering checks on a PIL Image.
        Returns a list of structured signal dictionaries:
        [{"signal": str, "category": "visual", "score": int, "description": str}]
        """
        findings: List[Dict[str, Any]] = []
        if image is None:
            return findings

        try:
            # 1. Pasted white patches / masking boxes
            cls._check_pasted_white_patches(image, findings)

            # 2. Font size / height inconsistencies from OCR lines
            if ocr_lines:
                cls._check_font_consistency(ocr_lines, findings)

            # 3. Compression artifacts (ELA heuristic)
            cls._check_compression_artifacts(image, findings)

            # 4. Cloned stamps / duplicate elements
            cls._check_cloned_stamps(image, findings)

            # 5. Localized blurred edited regions (Laplacian variance)
            cls._check_blurred_regions(image, findings)

            # 6. Cut-and-paste edge discontinuities
            cls._check_cut_and_paste_edges(image, findings)
        except Exception as ex:
            logger.warning("Visual tampering check encountered non-fatal error: %s", ex)

        return findings

    @classmethod
    def _check_pasted_white_patches(cls, image: Image.Image, findings: List[Dict[str, Any]]) -> None:
        """
        Detects sharp rectangular white patches placed over text or backgrounds.
        Calibrated to avoid false positives on natural white margins or unprinted borders.
        """
        if np is None or cv2 is None:
            return

        try:
            # Convert to OpenCV grayscale
            img_rgb = np.array(image.convert("RGB"))
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape

            # Ignore margins (outer 5%)
            margin_y = int(h * 0.05)
            margin_x = int(w * 0.05)
            inner = gray[margin_y:h - margin_y, margin_x:w - margin_x]
            if inner.size == 0:
                return

            inner_mean = float(np.mean(inner))
            inner_std = float(np.std(inner))

            # Only check if page itself has texture/content (not a completely blank digital page)
            if inner_std < 8.0 or inner_mean > 252.0:
                return

            # Threshold for pure/near-pure white regions (>= 245)
            _, white_mask = cv2.threshold(inner, 245, 255, cv2.THRESH_BINARY)
            contours, _ = cv2.findContours(white_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            patch_detected = False
            for c in contours:
                area = cv2.contourArea(c)
                # Looking for small-to-medium rectangular patches (typical for masked text: 250px to 40000px)
                if 250 < area < 40000:
                    x, y, cw, ch = cv2.boundingRect(c)
                    aspect_ratio = float(cw) / max(1, ch)
                    # Rectangular box typical of text masking (width > height)
                    if 1.2 <= aspect_ratio <= 20.0:
                        patch_roi = inner[y:y + ch, x:x + cw]
                        patch_variance = float(np.var(patch_roi))
                        patch_mean = float(np.mean(patch_roi))
                        # A digitally pasted white box has near-zero variance and high brightness amidst texture
                        if patch_variance < 8.0 and patch_mean >= 248.0 and inner_std > 10.0:
                            patch_detected = True
                            break

            if patch_detected:
                findings.append({
                    "signal": "pasted_white_patch",
                    "category": "visual",
                    "score": 20,
                    "description": "Possible pasted text region or white patch detected.",
                })
        except Exception as ex:
            logger.debug("Pasted patch detection skipped: %s", ex)

    @classmethod
    def _check_font_consistency(cls, ocr_lines: List[Any], findings: List[Dict[str, Any]]) -> None:
        """
        Analyzes line bounding boxes to detect abrupt font size or line height inconsistencies.
        """
        if len(ocr_lines) < 5:
            return

        heights = []
        for line in ocr_lines:
            bbox = getattr(line, "bbox", None) or getattr(line, "box", None) if hasattr(line, "__dict__") or hasattr(line, "bbox") or hasattr(line, "box") else (line.get("bbox") or line.get("box") if isinstance(line, dict) else None)
            if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
                try:
                    if isinstance(bbox[0], (list, tuple)):
                        ys = [float(pt[1]) for pt in bbox]
                        h = max(ys) - min(ys)
                    else:
                        h = float(bbox[3]) - float(bbox[1])
                    if h > 5:
                        heights.append(h)
                except Exception:
                    pass

        if len(heights) >= 5:
            sorted_h = sorted(heights)
            median_h = sorted_h[len(sorted_h) // 2]
            # Detect outlier lines whose height is drastically different (>2.5x or <0.4x) from typical body text
            outliers = [h for h in heights if h > (median_h * 2.5) or h < (median_h * 0.4)]
            if len(outliers) >= 2 and median_h > 10:
                findings.append({
                    "signal": "font_size_inconsistency",
                    "category": "visual",
                    "score": 15,
                    "description": "Font size inconsistency detected across text fields.",
                })

    @classmethod
    def _check_compression_artifacts(cls, image: Image.Image, findings: List[Dict[str, Any]]) -> None:
        """
        Error Level Analysis (ELA) heuristic: re-saves the image at 90% JPEG quality
        and computes the pixel difference to detect non-uniform compression levels.
        """
        try:
            # Downscale large images for fast local analysis
            img_copy = image.copy()
            if img_copy.width > 1200 or img_copy.height > 1200:
                img_copy.thumbnail((1200, 1200), Image.Resampling.BILINEAR)

            buf = io.BytesIO()
            img_copy.convert("RGB").save(buf, format="JPEG", quality=90)
            buf.seek(0)
            resaved = Image.open(buf)

            diff = ImageChops.difference(img_copy.convert("RGB"), resaved)
            stat = ImageStat.Stat(diff)
            mean_diff = max(stat.mean)
            std_diff = max(stat.stddev)

            # High localized variance in re-save differences indicates spliced compression layers
            if mean_diff > 12.0 and std_diff > 14.0:
                findings.append({
                    "signal": "compression_artifact",
                    "category": "visual",
                    "score": 10,
                    "description": "Inconsistent compression artifacts detected across image regions.",
                })
        except Exception as ex:
            logger.debug("ELA check skipped: %s", ex)

    @classmethod
    def _check_cloned_stamps(cls, image: Image.Image, findings: List[Dict[str, Any]]) -> None:
        """
        Detects duplicated circular/oval ink stamps or signatures using color/template correlation.
        """
        if np is None or cv2 is None:
            return

        try:
            img_rgb = np.array(image.convert("RGB"))
            h, w, _ = img_rgb.shape
            if h < 300 or w < 300:
                return

            # Convert to HSV to detect colored ink (blue/purple/red stamps)
            hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)
            # Blue ink stamp mask: Hue 100-140
            mask_blue = cv2.inRange(hsv, np.array([95, 50, 50]), np.array([135, 255, 255]))
            # Purple ink stamp mask: Hue 135-165
            mask_purple = cv2.inRange(hsv, np.array([135, 40, 40]), np.array([165, 255, 255]))
            ink_mask = cv2.bitwise_or(mask_blue, mask_purple)

            contours, _ = cv2.findContours(ink_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            stamp_candidates = []
            for c in contours:
                area = cv2.contourArea(c)
                if 2000 < area < 40000:
                    x, y, cw, ch = cv2.boundingRect(c)
                    ratio = float(cw) / max(1, ch)
                    if 0.7 <= ratio <= 1.4:  # roughly round or square
                        stamp_candidates.append(ink_mask[y:y + ch, x:x + cw])

            # If two distinct stamps exist, check template correlation
            if len(stamp_candidates) >= 2:
                for i in range(len(stamp_candidates)):
                    for j in range(i + 1, min(len(stamp_candidates), i + 3)):
                        s1 = cv2.resize(stamp_candidates[i], (100, 100))
                        s2 = cv2.resize(stamp_candidates[j], (100, 100))
                        res = cv2.matchTemplate(s1, s2, cv2.TM_CCOEFF_NORMED)
                        if res[0][0] > 0.88:
                            findings.append({
                                "signal": "cloned_stamp",
                                "category": "visual",
                                "score": 25,
                                "description": "Duplicated stamp or seal pattern detected.",
                            })
                            return
        except Exception as ex:
            logger.debug("Cloned stamp check skipped: %s", ex)

    @classmethod
    def _check_blurred_regions(cls, image: Image.Image, findings: List[Dict[str, Any]]) -> None:
        """
        Detects localized blurry patches (Laplacian variance drop) indicating selective erasure.
        """
        if np is None or cv2 is None:
            return

        try:
            img_rgb = np.array(image.convert("RGB"))
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
            h, w = gray.shape
            if h < 200 or w < 200:
                return

            overall_var = cv2.Laplacian(gray, cv2.CV_64F).var()
            if overall_var < 80.0:  # already uniformly soft scan, avoid false positives
                return

            # Grid analysis (4x4 blocks)
            step_y = h // 4
            step_x = w // 4
            block_vars = []

            for r in range(4):
                for c in range(4):
                    block = gray[r * step_y:(r + 1) * step_y, c * step_x:(c + 1) * step_x]
                    # Exclude empty white blocks
                    if np.mean(block) < 240 and np.std(block) > 15:
                        b_var = cv2.Laplacian(block, cv2.CV_64F).var()
                        block_vars.append(b_var)

            if len(block_vars) >= 6:
                median_var = float(np.median(block_vars))
                # If an active block has > 4x drop in variance compared to active page median
                anomalous_blurs = [bv for bv in block_vars if bv < (median_var / 4.0) and median_var > 150]
                if len(anomalous_blurs) >= 1:
                    findings.append({
                        "signal": "blurred_edited_region",
                        "category": "visual",
                        "score": 10,
                        "description": "Blurred edited region detected.",
                    })
        except Exception as ex:
            logger.debug("Blur check skipped: %s", ex)

    @classmethod
    def _check_cut_and_paste_edges(cls, image: Image.Image, findings: List[Dict[str, Any]]) -> None:
        """
        Detects sharp high-frequency artificial boundary lines characteristic of digital paste-overs.
        """
        if np is None or cv2 is None:
            return

        try:
            img_rgb = np.array(image.convert("RGB"))
            gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
            edges = cv2.Canny(gray, 100, 200)

            # Detect straight horizontal and vertical edge lines (cut boundaries)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=120, minLineLength=80, maxLineGap=5)
            if lines is not None and len(lines) > 25:
                # Many perfectly sharp collinear horizontal/vertical cuts in the middle of a scan
                h_lines = 0
                v_lines = 0
                for line in lines:
                    x1, y1, x2, y2 = line[0]
                    if abs(y2 - y1) <= 2:
                        h_lines += 1
                    elif abs(x2 - x1) <= 2:
                        v_lines += 1

                if h_lines >= 8 and v_lines >= 8:
                    findings.append({
                        "signal": "cut_and_paste_edges",
                        "category": "visual",
                        "score": 10,
                        "description": "Artificial cut-and-paste boundary edges detected.",
                    })
        except Exception as ex:
            logger.debug("Cut-and-paste edge check skipped: %s", ex)
