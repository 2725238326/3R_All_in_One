"""
Visual Artifacts - 对比 GIF / 深度图热力图 / 点云渲染
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

LOGGER = logging.getLogger("kykt.visuals")

# Colormap for depth visualization (Turbo-like)
TURBO_COLORMAP = np.array([
    [48, 18, 59], [50, 21, 67], [51, 24, 74], [52, 27, 81], [53, 30, 88],
    [54, 33, 95], [55, 36, 102], [56, 39, 109], [57, 42, 115], [58, 45, 121],
    [59, 47, 128], [60, 50, 134], [61, 53, 139], [62, 56, 145], [63, 59, 151],
    [63, 62, 156], [64, 64, 162], [65, 67, 167], [65, 70, 172], [66, 73, 177],
    [66, 75, 181], [67, 78, 186], [68, 81, 191], [68, 84, 195], [68, 86, 199],
    [69, 89, 203], [69, 92, 207], [69, 94, 211], [70, 97, 214], [70, 100, 218],
    [70, 102, 221], [70, 105, 224], [70, 107, 227], [71, 110, 230], [71, 113, 233],
    [71, 115, 235], [71, 118, 238], [71, 120, 240], [71, 123, 242], [70, 125, 244],
    [70, 128, 246], [70, 130, 248], [70, 133, 250], [70, 135, 251], [69, 138, 252],
    [69, 140, 253], [68, 143, 254], [67, 145, 254], [66, 148, 255], [65, 150, 255],
    [64, 153, 255], [62, 155, 254], [61, 158, 254], [59, 160, 253], [58, 163, 252],
    [56, 165, 251], [55, 168, 250], [53, 171, 248], [51, 173, 247], [49, 175, 245],
    [47, 178, 244], [46, 180, 242], [44, 183, 240], [42, 185, 238], [40, 188, 235],
    [39, 190, 233], [37, 192, 231], [35, 195, 228], [34, 197, 226], [32, 199, 223],
    [31, 201, 221], [30, 203, 218], [28, 205, 216], [27, 208, 213], [26, 210, 210],
    [26, 212, 208], [25, 213, 205], [24, 215, 202], [24, 217, 200], [24, 219, 197],
    [24, 221, 194], [24, 222, 192], [24, 224, 189], [25, 226, 187], [25, 227, 185],
    [26, 228, 182], [28, 230, 180], [29, 231, 178], [31, 233, 175], [32, 234, 172],
    [34, 235, 170], [37, 236, 167], [39, 238, 164], [42, 239, 161], [44, 240, 158],
    [47, 241, 155], [50, 242, 152], [53, 243, 148], [56, 244, 145], [60, 245, 142],
    [63, 246, 138], [67, 247, 135], [70, 248, 132], [74, 248, 128], [78, 249, 125],
    [82, 250, 122], [85, 250, 118], [89, 251, 115], [93, 252, 111], [97, 252, 108],
    [101, 253, 105], [105, 253, 102], [109, 254, 98], [113, 254, 95], [117, 254, 92],
    [121, 254, 89], [125, 255, 86], [128, 255, 83], [132, 255, 81], [136, 255, 78],
    [139, 255, 75], [143, 255, 73], [146, 255, 71], [150, 254, 68], [153, 254, 66],
    [156, 254, 64], [159, 253, 63], [161, 253, 61], [164, 252, 60], [167, 252, 58],
    [169, 251, 57], [172, 251, 56], [175, 250, 55], [177, 249, 54], [180, 248, 54],
    [183, 247, 53], [185, 246, 53], [188, 245, 52], [190, 244, 52], [193, 243, 52],
    [195, 241, 52], [198, 240, 52], [200, 239, 52], [203, 237, 52], [205, 236, 52],
    [208, 234, 52], [210, 233, 53], [212, 231, 53], [215, 229, 53], [217, 228, 54],
    [219, 226, 54], [221, 224, 55], [223, 223, 55], [225, 221, 55], [227, 219, 56],
    [229, 217, 56], [231, 215, 57], [233, 213, 57], [235, 211, 57], [236, 209, 58],
    [238, 207, 58], [239, 205, 58], [241, 203, 58], [242, 200, 58], [244, 198, 58],
    [245, 196, 58], [246, 194, 58], [247, 192, 57], [248, 190, 57], [249, 188, 57],
    [250, 185, 56], [251, 183, 55], [251, 181, 55], [252, 178, 54], [252, 176, 53],
    [253, 174, 52], [253, 171, 51], [253, 169, 50], [253, 167, 48], [253, 164, 47],
    [254, 162, 46], [254, 159, 45], [254, 157, 43], [254, 154, 42], [254, 152, 41],
    [253, 150, 39], [253, 147, 38], [253, 145, 37], [253, 142, 36], [252, 140, 34],
    [252, 138, 33], [251, 135, 32], [251, 133, 31], [250, 131, 30], [250, 128, 29],
    [249, 126, 28], [249, 124, 27], [248, 121, 26], [248, 119, 25], [247, 117, 24],
    [247, 115, 23], [246, 112, 23], [246, 110, 22], [245, 108, 21], [245, 106, 21],
    [244, 104, 20], [244, 102, 20], [243, 99, 19], [243, 97, 19], [242, 95, 18],
    [242, 93, 18], [241, 91, 18], [241, 90, 17], [240, 88, 17], [240, 86, 17],
    [239, 84, 17], [239, 82, 17], [238, 80, 17], [238, 79, 17], [237, 77, 17],
    [237, 75, 17], [236, 74, 17], [236, 72, 17], [235, 71, 17], [235, 69, 18],
    [234, 68, 18], [234, 66, 18], [233, 65, 18], [233, 64, 19], [232, 62, 19],
], dtype=np.uint8)


def depth_to_colormap(
    depth: np.ndarray,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
    invalid_color: tuple[int, int, int] = (0, 0, 0),
) -> np.ndarray:
    """
    Convert depth map to colormap image.
    
    Args:
        depth: 2D depth array
        min_val: Minimum depth for normalization (auto if None)
        max_val: Maximum depth for normalization (auto if None)
        invalid_color: RGB color for invalid (<=0) pixels
    
    Returns:
        RGB image array (H, W, 3)
    """
    valid_mask = depth > 0
    
    if not valid_mask.any():
        h, w = depth.shape[:2]
        return np.full((h, w, 3), invalid_color, dtype=np.uint8)
    
    if min_val is None:
        min_val = depth[valid_mask].min()
    if max_val is None:
        max_val = depth[valid_mask].max()
    
    # Normalize to 0-255
    normalized = np.clip((depth - min_val) / (max_val - min_val + 1e-8), 0, 1)
    indices = (normalized * 255).astype(np.uint8)
    
    # Apply colormap
    colored = TURBO_COLORMAP[indices]
    
    # Set invalid pixels
    colored[~valid_mask] = invalid_color
    
    return colored


def create_depth_heatmap(
    depth: np.ndarray,
    output_path: Path,
    min_val: Optional[float] = None,
    max_val: Optional[float] = None,
) -> bool:
    """Create and save depth heatmap image."""
    try:
        from PIL import Image
        
        colored = depth_to_colormap(depth, min_val, max_val)
        img = Image.fromarray(colored)
        img.save(output_path)
        LOGGER.info(f"Saved depth heatmap to {output_path}")
        return True
    except ImportError:
        LOGGER.warning("PIL not available for heatmap generation")
        return False
    except Exception as e:
        LOGGER.error(f"Failed to create heatmap: {e}")
        return False


def create_depth_comparison_image(
    depths: Sequence[np.ndarray],
    labels: Sequence[str],
    output_path: Path,
    normalize_together: bool = True,
) -> bool:
    """
    Create side-by-side depth comparison image.
    
    Args:
        depths: List of depth maps
        labels: Labels for each depth map
        output_path: Output image path
        normalize_together: Use same min/max for all maps
    """
    try:
        from PIL import Image, ImageDraw, ImageFont
        
        if len(depths) == 0:
            return False
        
        # Find common normalization range
        if normalize_together:
            all_valid = np.concatenate([d[d > 0].flatten() for d in depths if (d > 0).any()])
            if len(all_valid) > 0:
                min_val, max_val = all_valid.min(), all_valid.max()
            else:
                min_val, max_val = 0, 1
        else:
            min_val, max_val = None, None
        
        # Convert all depth maps
        colored_maps = [depth_to_colormap(d, min_val, max_val) for d in depths]
        
        # Create combined image
        h = max(c.shape[0] for c in colored_maps)
        w_total = sum(c.shape[1] for c in colored_maps)
        label_height = 30
        
        combined = np.zeros((h + label_height, w_total, 3), dtype=np.uint8)
        combined[:label_height, :] = [40, 40, 40]  # Label background
        
        x_offset = 0
        for i, colored in enumerate(colored_maps):
            ch, cw = colored.shape[:2]
            combined[label_height:label_height + ch, x_offset:x_offset + cw] = colored
            x_offset += cw
        
        img = Image.fromarray(combined)
        
        # Add labels
        try:
            draw = ImageDraw.Draw(img)
            font = ImageFont.load_default()
            x_offset = 0
            for i, (colored, label) in enumerate(zip(colored_maps, labels)):
                cw = colored.shape[1]
                text_x = x_offset + cw // 2 - len(label) * 3
                draw.text((text_x, 8), label, fill=(255, 255, 255), font=font)
                x_offset += cw
        except Exception:
            pass  # Skip labels if font fails
        
        img.save(output_path)
        LOGGER.info(f"Saved comparison image to {output_path}")
        return True
    except ImportError:
        LOGGER.warning("PIL not available for comparison image")
        return False
    except Exception as e:
        LOGGER.error(f"Failed to create comparison image: {e}")
        return False


def create_comparison_gif(
    image_paths: Sequence[Path],
    output_path: Path,
    duration_ms: int = 500,
    loop: int = 0,
) -> bool:
    """
    Create animated GIF from multiple images.
    
    Args:
        image_paths: List of image paths
        output_path: Output GIF path
        duration_ms: Duration per frame in milliseconds
        loop: Number of loops (0 = infinite)
    """
    try:
        from PIL import Image
        
        if len(image_paths) < 2:
            LOGGER.warning("Need at least 2 images for GIF")
            return False
        
        images = []
        target_size = None
        
        for path in image_paths:
            if not path.exists():
                continue
            img = Image.open(path)
            if target_size is None:
                target_size = img.size
            else:
                img = img.resize(target_size, Image.Resampling.LANCZOS)
            images.append(img.convert("RGB"))
        
        if len(images) < 2:
            return False
        
        images[0].save(
            output_path,
            save_all=True,
            append_images=images[1:],
            duration=duration_ms,
            loop=loop,
        )
        LOGGER.info(f"Saved comparison GIF to {output_path}")
        return True
    except ImportError:
        LOGGER.warning("PIL not available for GIF generation")
        return False
    except Exception as e:
        LOGGER.error(f"Failed to create GIF: {e}")
        return False


def create_depth_diff_heatmap(
    depth_a: np.ndarray,
    depth_b: np.ndarray,
    output_path: Path,
    label_a: str = "A",
    label_b: str = "B",
) -> bool:
    """
    Create difference heatmap between two depth maps.
    Red = A > B, Blue = B > A, Green = similar
    """
    try:
        from PIL import Image
        
        # Compute valid mask
        valid = (depth_a > 0) & (depth_b > 0)
        
        if not valid.any():
            return False
        
        # Normalize both to same scale
        all_valid = np.concatenate([depth_a[valid], depth_b[valid]])
        min_val, max_val = all_valid.min(), all_valid.max()
        range_val = max_val - min_val + 1e-8
        
        norm_a = (depth_a - min_val) / range_val
        norm_b = (depth_b - min_val) / range_val
        
        # Compute difference
        diff = norm_a - norm_b  # Positive = A deeper, Negative = B deeper
        
        # Create RGB diff image
        h, w = diff.shape
        rgb = np.zeros((h, w, 3), dtype=np.uint8)
        
        # Red channel: A > B
        rgb[:, :, 0] = np.clip(diff * 500, 0, 255).astype(np.uint8)
        # Blue channel: B > A
        rgb[:, :, 2] = np.clip(-diff * 500, 0, 255).astype(np.uint8)
        # Green channel: similar (low difference)
        similarity = 1 - np.abs(diff) * 5
        rgb[:, :, 1] = np.clip(similarity * 150, 0, 255).astype(np.uint8)
        
        # Mark invalid pixels as black
        rgb[~valid] = 0
        
        img = Image.fromarray(rgb)
        img.save(output_path)
        LOGGER.info(f"Saved diff heatmap to {output_path}")
        return True
    except ImportError:
        LOGGER.warning("PIL not available for diff heatmap")
        return False
    except Exception as e:
        LOGGER.error(f"Failed to create diff heatmap: {e}")
        return False


def generate_job_visuals(job_dir: Path) -> dict:
    """
    Generate all visual artifacts for a job.
    
    Returns dict with paths to generated files.
    """
    results = {}
    output_dir = job_dir / "output"
    visuals_dir = job_dir / "visuals"
    visuals_dir.mkdir(exist_ok=True)
    
    if not output_dir.exists():
        return {"error": "No output directory"}
    
    # Find depth maps
    depth_files = list(output_dir.glob("**/depth*.npy")) + list(output_dir.glob("**/depth*.npz"))
    
    for i, depth_file in enumerate(depth_files[:3]):  # Limit to first 3
        try:
            if depth_file.suffix == ".npy":
                depth = np.load(depth_file)
            else:
                data = np.load(depth_file)
                depth = data.get("depth", data.get("arr_0", None))
                if depth is None:
                    continue
            
            heatmap_path = visuals_dir / f"depth_heatmap_{i}.png"
            if create_depth_heatmap(depth, heatmap_path):
                results[f"depth_heatmap_{i}"] = str(heatmap_path)
        except Exception as e:
            LOGGER.warning(f"Failed to process {depth_file}: {e}")
    
    # Find rendered images for GIF
    render_files = sorted(output_dir.glob("**/render*.png"))[:10]  # Limit
    if len(render_files) >= 2:
        gif_path = visuals_dir / "renders.gif"
        if create_comparison_gif(render_files, gif_path, duration_ms=300):
            results["renders_gif"] = str(gif_path)
    
    return results


def generate_compare_visuals(job_dirs: Sequence[Path], labels: Sequence[str], output_dir: Path) -> dict:
    """
    Generate comparison visuals across multiple jobs.
    """
    results = {}
    output_dir.mkdir(exist_ok=True)
    
    # Collect depth maps from all jobs
    all_depths = []
    all_labels = []
    
    for job_dir, label in zip(job_dirs, labels):
        depth_files = list((job_dir / "output").glob("**/depth*.npy"))
        if depth_files:
            try:
                depth = np.load(depth_files[0])
                all_depths.append(depth)
                all_labels.append(label)
            except Exception:
                pass
    
    # Create comparison image
    if len(all_depths) >= 2:
        comparison_path = output_dir / "depth_comparison.png"
        if create_depth_comparison_image(all_depths, all_labels, comparison_path):
            results["depth_comparison"] = str(comparison_path)
        
        # Create diff heatmap for first two
        diff_path = output_dir / "depth_diff.png"
        if create_depth_diff_heatmap(all_depths[0], all_depths[1], diff_path, all_labels[0], all_labels[1]):
            results["depth_diff"] = str(diff_path)
    
    # Collect render images
    all_renders = []
    for job_dir, label in zip(job_dirs, labels):
        renders = sorted((job_dir / "output").glob("**/render*.png"))
        if renders:
            all_renders.append((renders[0], label))
    
    if len(all_renders) >= 2:
        gif_path = output_dir / "compare_renders.gif"
        if create_comparison_gif([r[0] for r in all_renders], gif_path, duration_ms=800):
            results["compare_renders_gif"] = str(gif_path)
    
    return results
