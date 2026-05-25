"""
Resource Monitor - GPU/CPU/磁盘监控
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Optional

LOGGER = logging.getLogger("kykt.resources")


@dataclass
class GPUInfo:
    index: int
    name: str
    memory_used_mb: float
    memory_total_mb: float
    utilization_percent: float
    temperature_c: Optional[float] = None
    
    @property
    def memory_free_mb(self) -> float:
        return self.memory_total_mb - self.memory_used_mb
    
    @property
    def memory_used_percent(self) -> float:
        if self.memory_total_mb == 0:
            return 0
        return (self.memory_used_mb / self.memory_total_mb) * 100
    
    def to_dict(self) -> dict:
        return {
            "index": self.index,
            "name": self.name,
            "memory_used_mb": round(self.memory_used_mb, 1),
            "memory_total_mb": round(self.memory_total_mb, 1),
            "memory_free_mb": round(self.memory_free_mb, 1),
            "memory_used_percent": round(self.memory_used_percent, 1),
            "utilization_percent": round(self.utilization_percent, 1),
            "temperature_c": self.temperature_c,
        }


@dataclass
class SystemResources:
    cpu_percent: float
    memory_used_mb: float
    memory_total_mb: float
    disk_used_gb: float
    disk_total_gb: float
    gpus: list[GPUInfo]
    timestamp: float
    
    @property
    def memory_free_mb(self) -> float:
        return self.memory_total_mb - self.memory_used_mb
    
    @property
    def disk_free_gb(self) -> float:
        return self.disk_total_gb - self.disk_used_gb
    
    def to_dict(self) -> dict:
        return {
            "cpu_percent": round(self.cpu_percent, 1),
            "memory": {
                "used_mb": round(self.memory_used_mb, 1),
                "total_mb": round(self.memory_total_mb, 1),
                "free_mb": round(self.memory_free_mb, 1),
                "used_percent": round((self.memory_used_mb / self.memory_total_mb) * 100, 1) if self.memory_total_mb > 0 else 0,
            },
            "disk": {
                "used_gb": round(self.disk_used_gb, 1),
                "total_gb": round(self.disk_total_gb, 1),
                "free_gb": round(self.disk_free_gb, 1),
                "used_percent": round((self.disk_used_gb / self.disk_total_gb) * 100, 1) if self.disk_total_gb > 0 else 0,
            },
            "gpus": [gpu.to_dict() for gpu in self.gpus],
            "gpu_count": len(self.gpus),
            "timestamp": self.timestamp,
        }


def _get_cpu_percent() -> float:
    try:
        import psutil
        return psutil.cpu_percent(interval=0.1)
    except ImportError:
        return 0.0


def _get_memory_info() -> tuple[float, float]:
    try:
        import psutil
        mem = psutil.virtual_memory()
        return mem.used / (1024 * 1024), mem.total / (1024 * 1024)
    except ImportError:
        return 0.0, 0.0


def _get_disk_info(path: str = ".") -> tuple[float, float]:
    try:
        usage = shutil.disk_usage(path)
        return usage.used / (1024**3), usage.total / (1024**3)
    except Exception:
        return 0.0, 0.0


def _parse_nvidia_smi() -> list[GPUInfo]:
    """Parse nvidia-smi output for GPU info."""
    gpus = []
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return gpus
        
        for line in result.stdout.strip().split("\n"):
            if not line.strip():
                continue
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 5:
                gpus.append(GPUInfo(
                    index=int(parts[0]),
                    name=parts[1],
                    memory_used_mb=float(parts[2]),
                    memory_total_mb=float(parts[3]),
                    utilization_percent=float(parts[4]),
                    temperature_c=float(parts[5]) if len(parts) > 5 and parts[5] else None,
                ))
    except FileNotFoundError:
        LOGGER.debug("nvidia-smi not found")
    except subprocess.TimeoutExpired:
        LOGGER.warning("nvidia-smi timeout")
    except Exception as e:
        LOGGER.warning(f"Failed to parse nvidia-smi: {e}")
    return gpus


def get_system_resources(disk_path: str = ".") -> SystemResources:
    """Get current system resource usage."""
    cpu = _get_cpu_percent()
    mem_used, mem_total = _get_memory_info()
    disk_used, disk_total = _get_disk_info(disk_path)
    gpus = _parse_nvidia_smi()
    
    return SystemResources(
        cpu_percent=cpu,
        memory_used_mb=mem_used,
        memory_total_mb=mem_total,
        disk_used_gb=disk_used,
        disk_total_gb=disk_total,
        gpus=gpus,
        timestamp=time.time(),
    )


class ResourceMonitor:
    """Background resource monitor with caching."""
    
    def __init__(self, poll_interval: float = 5.0, disk_path: str = "."):
        self._poll_interval = poll_interval
        self._disk_path = disk_path
        self._cache: Optional[SystemResources] = None
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self) -> None:
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(target=self._poll_loop, daemon=True)
            self._thread.start()
            LOGGER.info("Resource monitor started")
    
    def stop(self) -> None:
        with self._lock:
            self._running = False
            if self._thread:
                self._thread.join(timeout=2.0)
                self._thread = None
            LOGGER.info("Resource monitor stopped")
    
    def _poll_loop(self) -> None:
        while self._running:
            try:
                resources = get_system_resources(self._disk_path)
                with self._lock:
                    self._cache = resources
            except Exception as e:
                LOGGER.error(f"Resource poll error: {e}")
            time.sleep(self._poll_interval)
    
    def get(self) -> Optional[SystemResources]:
        with self._lock:
            return self._cache
    
    def get_dict(self) -> dict:
        resources = self.get()
        if resources:
            return resources.to_dict()
        return {"error": "No data available", "timestamp": time.time()}


# Global monitor instance
monitor = ResourceMonitor()
