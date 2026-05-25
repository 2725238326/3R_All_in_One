"""
Metrics Calculator - 深度图/点云评估指标自动计算
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

LOGGER = logging.getLogger("kykt.metrics")


@dataclass
class DepthMetrics:
    """深度图评估指标"""
    rmse: float  # Root Mean Square Error
    abs_rel: float  # Absolute Relative Error
    sq_rel: float  # Squared Relative Error
    delta_1: float  # δ < 1.25
    delta_2: float  # δ < 1.25²
    delta_3: float  # δ < 1.25³
    valid_pixels: int
    total_pixels: int
    
    def to_dict(self) -> dict:
        return {
            "rmse": round(self.rmse, 4),
            "abs_rel": round(self.abs_rel, 4),
            "sq_rel": round(self.sq_rel, 4),
            "delta_1": round(self.delta_1, 4),
            "delta_2": round(self.delta_2, 4),
            "delta_3": round(self.delta_3, 4),
            "valid_ratio": round(self.valid_pixels / max(self.total_pixels, 1), 4),
        }


@dataclass
class PointCloudMetrics:
    """点云评估指标"""
    point_count: int
    density: float  # points per unit volume
    coverage_ratio: float  # estimated scene coverage
    bbox_min: tuple[float, float, float]
    bbox_max: tuple[float, float, float]
    centroid: tuple[float, float, float]
    
    def to_dict(self) -> dict:
        return {
            "point_count": self.point_count,
            "density": round(self.density, 2),
            "coverage_ratio": round(self.coverage_ratio, 4),
            "bbox": {
                "min": [round(v, 3) for v in self.bbox_min],
                "max": [round(v, 3) for v in self.bbox_max],
            },
            "centroid": [round(v, 3) for v in self.centroid],
        }


@dataclass  
class TrajectoryMetrics:
    """相机轨迹评估指标"""
    ate: float  # Absolute Trajectory Error
    rpe_trans: float  # Relative Pose Error (translation)
    rpe_rot: float  # Relative Pose Error (rotation, degrees)
    frame_count: int
    path_length: float
    
    def to_dict(self) -> dict:
        return {
            "ate": round(self.ate, 4),
            "rpe_trans": round(self.rpe_trans, 4),
            "rpe_rot_deg": round(self.rpe_rot, 2),
            "frame_count": self.frame_count,
            "path_length": round(self.path_length, 3),
        }


def compute_depth_metrics(
    pred: np.ndarray,
    gt: np.ndarray,
    min_depth: float = 0.001,
    max_depth: float = 80.0,
) -> DepthMetrics:
    """
    计算深度图评估指标
    
    Args:
        pred: 预测深度图 (H, W)
        gt: 真值深度图 (H, W)
        min_depth: 最小有效深度
        max_depth: 最大有效深度
    """
    mask = (gt > min_depth) & (gt < max_depth) & (pred > min_depth) & (pred < max_depth)
    valid_pixels = mask.sum()
    total_pixels = gt.size
    
    if valid_pixels == 0:
        return DepthMetrics(
            rmse=float("inf"),
            abs_rel=float("inf"),
            sq_rel=float("inf"),
            delta_1=0.0,
            delta_2=0.0,
            delta_3=0.0,
            valid_pixels=0,
            total_pixels=total_pixels,
        )
    
    pred_valid = pred[mask]
    gt_valid = gt[mask]
    
    # RMSE
    rmse = np.sqrt(np.mean((pred_valid - gt_valid) ** 2))
    
    # Absolute Relative Error
    abs_rel = np.mean(np.abs(pred_valid - gt_valid) / gt_valid)
    
    # Squared Relative Error
    sq_rel = np.mean(((pred_valid - gt_valid) ** 2) / gt_valid)
    
    # Threshold accuracies (δ < threshold)
    ratio = np.maximum(pred_valid / gt_valid, gt_valid / pred_valid)
    delta_1 = np.mean(ratio < 1.25)
    delta_2 = np.mean(ratio < 1.25 ** 2)
    delta_3 = np.mean(ratio < 1.25 ** 3)
    
    return DepthMetrics(
        rmse=float(rmse),
        abs_rel=float(abs_rel),
        sq_rel=float(sq_rel),
        delta_1=float(delta_1),
        delta_2=float(delta_2),
        delta_3=float(delta_3),
        valid_pixels=int(valid_pixels),
        total_pixels=int(total_pixels),
    )


def compute_pointcloud_metrics(
    points: np.ndarray,
    expected_bbox: Optional[tuple[np.ndarray, np.ndarray]] = None,
) -> PointCloudMetrics:
    """
    计算点云评估指标
    
    Args:
        points: 点云数组 (N, 3) 或 (N, 6) 含颜色
        expected_bbox: 期望的边界框 (min, max)，用于计算覆盖率
    """
    if points.shape[0] == 0:
        return PointCloudMetrics(
            point_count=0,
            density=0.0,
            coverage_ratio=0.0,
            bbox_min=(0, 0, 0),
            bbox_max=(0, 0, 0),
            centroid=(0, 0, 0),
        )
    
    xyz = points[:, :3]
    point_count = xyz.shape[0]
    
    bbox_min = xyz.min(axis=0)
    bbox_max = xyz.max(axis=0)
    centroid = xyz.mean(axis=0)
    
    # Volume and density
    bbox_size = bbox_max - bbox_min
    volume = max(np.prod(bbox_size), 1e-6)
    density = point_count / volume
    
    # Coverage ratio
    if expected_bbox is not None:
        exp_min, exp_max = expected_bbox
        exp_size = exp_max - exp_min
        exp_volume = max(np.prod(exp_size), 1e-6)
        coverage_ratio = min(volume / exp_volume, 1.0)
    else:
        coverage_ratio = 1.0  # No reference
    
    return PointCloudMetrics(
        point_count=point_count,
        density=float(density),
        coverage_ratio=float(coverage_ratio),
        bbox_min=tuple(bbox_min.tolist()),
        bbox_max=tuple(bbox_max.tolist()),
        centroid=tuple(centroid.tolist()),
    )


def compute_trajectory_metrics(
    pred_poses: np.ndarray,
    gt_poses: Optional[np.ndarray] = None,
) -> TrajectoryMetrics:
    """
    计算相机轨迹评估指标
    
    Args:
        pred_poses: 预测位姿 (N, 4, 4) 或 (N, 7) [x,y,z,qw,qx,qy,qz]
        gt_poses: 真值位姿，格式同上
    """
    if pred_poses.ndim == 2 and pred_poses.shape[1] == 7:
        positions = pred_poses[:, :3]
    elif pred_poses.ndim == 3 and pred_poses.shape[1:] == (4, 4):
        positions = pred_poses[:, :3, 3]
    else:
        positions = pred_poses[:, :3] if pred_poses.shape[1] >= 3 else pred_poses
    
    frame_count = positions.shape[0]
    
    # Path length
    if frame_count > 1:
        diffs = np.diff(positions, axis=0)
        path_length = np.sum(np.linalg.norm(diffs, axis=1))
    else:
        path_length = 0.0
    
    # ATE and RPE (if ground truth available)
    if gt_poses is not None:
        if gt_poses.ndim == 2 and gt_poses.shape[1] == 7:
            gt_positions = gt_poses[:, :3]
        elif gt_poses.ndim == 3 and gt_poses.shape[1:] == (4, 4):
            gt_positions = gt_poses[:, :3, 3]
        else:
            gt_positions = gt_poses[:, :3] if gt_poses.shape[1] >= 3 else gt_poses
        
        # Align trajectory (simple translation alignment)
        offset = gt_positions.mean(axis=0) - positions.mean(axis=0)
        aligned = positions + offset
        
        # ATE
        errors = np.linalg.norm(aligned - gt_positions, axis=1)
        ate = float(np.sqrt(np.mean(errors ** 2)))
        
        # RPE (simplified - translation only)
        if frame_count > 1:
            pred_rel = np.diff(aligned, axis=0)
            gt_rel = np.diff(gt_positions, axis=0)
            rpe_errors = np.linalg.norm(pred_rel - gt_rel, axis=1)
            rpe_trans = float(np.mean(rpe_errors))
        else:
            rpe_trans = 0.0
        
        rpe_rot = 0.0  # TODO: Implement rotation RPE
    else:
        ate = 0.0
        rpe_trans = 0.0
        rpe_rot = 0.0
    
    return TrajectoryMetrics(
        ate=ate,
        rpe_trans=rpe_trans,
        rpe_rot=rpe_rot,
        frame_count=frame_count,
        path_length=float(path_length),
    )


def load_depth_map(path: Path) -> Optional[np.ndarray]:
    """Load depth map from file."""
    try:
        if path.suffix == ".npy":
            return np.load(path)
        elif path.suffix == ".npz":
            data = np.load(path)
            for key in ["depth", "pred", "arr_0"]:
                if key in data:
                    return data[key]
            return None
        elif path.suffix in (".png", ".jpg", ".jpeg"):
            from PIL import Image
            img = Image.open(path)
            return np.array(img).astype(np.float32)
        else:
            return None
    except Exception as e:
        LOGGER.warning(f"Failed to load depth map {path}: {e}")
        return None


def load_pointcloud(path: Path) -> Optional[np.ndarray]:
    """Load point cloud from file."""
    try:
        if path.suffix == ".npy":
            return np.load(path)
        elif path.suffix == ".npz":
            data = np.load(path)
            for key in ["points", "pts", "xyz", "arr_0"]:
                if key in data:
                    return data[key]
            return None
        elif path.suffix == ".ply":
            # Simple PLY loader
            with open(path, "rb") as f:
                header_lines = []
                while True:
                    line = f.readline().decode("utf-8", errors="ignore").strip()
                    header_lines.append(line)
                    if line == "end_header":
                        break
                
                vertex_count = 0
                for line in header_lines:
                    if line.startswith("element vertex"):
                        vertex_count = int(line.split()[-1])
                        break
                
                if vertex_count == 0:
                    return None
                
                # Read binary or ASCII
                if any("binary" in line for line in header_lines):
                    data = np.frombuffer(f.read(), dtype=np.float32)
                    data = data[:vertex_count * 3].reshape(-1, 3)
                else:
                    lines = f.read().decode("utf-8", errors="ignore").strip().split("\n")
                    data = np.array([[float(v) for v in line.split()[:3]] for line in lines[:vertex_count]])
                return data
        else:
            return None
    except Exception as e:
        LOGGER.warning(f"Failed to load point cloud {path}: {e}")
        return None


def compute_job_metrics(job_dir: Path) -> dict:
    """
    计算任务的所有可用指标
    
    Args:
        job_dir: 任务目录
    
    Returns:
        包含各类指标的字典
    """
    results = {}
    output_dir = job_dir / "output"
    
    if not output_dir.exists():
        return {"error": "No output directory"}
    
    # Find depth maps
    depth_files = list(output_dir.glob("**/depth*.npy")) + list(output_dir.glob("**/depth*.npz"))
    if depth_files:
        depth = load_depth_map(depth_files[0])
        if depth is not None:
            # Self-consistency check (no GT available)
            metrics = DepthMetrics(
                rmse=0,
                abs_rel=0,
                sq_rel=0,
                delta_1=1.0,
                delta_2=1.0,
                delta_3=1.0,
                valid_pixels=int((depth > 0).sum()),
                total_pixels=depth.size,
            )
            results["depth"] = {
                "file": depth_files[0].name,
                "shape": list(depth.shape),
                "min": float(depth[depth > 0].min()) if (depth > 0).any() else 0,
                "max": float(depth.max()),
                "metrics": metrics.to_dict(),
            }
    
    # Find point clouds
    pc_files = list(output_dir.glob("**/*.ply")) + list(output_dir.glob("**/points*.npy"))
    if pc_files:
        points = load_pointcloud(pc_files[0])
        if points is not None:
            metrics = compute_pointcloud_metrics(points)
            results["pointcloud"] = {
                "file": pc_files[0].name,
                "metrics": metrics.to_dict(),
            }
    
    # Find trajectory/poses
    pose_files = list(output_dir.glob("**/poses*.npy")) + list(output_dir.glob("**/trajectory*.npy"))
    if pose_files:
        try:
            poses = np.load(pose_files[0])
            metrics = compute_trajectory_metrics(poses)
            results["trajectory"] = {
                "file": pose_files[0].name,
                "metrics": metrics.to_dict(),
            }
        except Exception as e:
            LOGGER.warning(f"Failed to compute trajectory metrics: {e}")
    
    return results
