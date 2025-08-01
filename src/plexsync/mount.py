"""
Mount point management and monitoring for PlexSync.

This module handles detection, validation, and health monitoring of network
mount points, ensuring reliable access to media sources.
"""

import os
import subprocess
import time
import logging
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from enum import Enum
from pathlib import Path
import psutil
import threading
from concurrent.futures import ThreadPoolExecutor


logger = logging.getLogger(__name__)


class MountType(Enum):
    """Types of mount points supported."""
    NFS = "nfs"
    CIFS = "cifs"
    SSHFS = "sshfs"
    LOCAL = "local"
    UNKNOWN = "unknown"


class MountStatus(Enum):
    """Mount point status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


@dataclass
class MountPoint:
    """Information about a mount point."""
    path: str
    mount_type: MountType
    device: str
    filesystem: str
    options: List[str]
    status: MountStatus
    last_check: float
    response_time_ms: Optional[float] = None
    error_message: Optional[str] = None
    
    @property
    def is_network_mount(self) -> bool:
        """Check if this is a network mount."""
        return self.mount_type in [MountType.NFS, MountType.CIFS, MountType.SSHFS]
    
    @property
    def is_healthy(self) -> bool:
        """Check if mount is healthy."""
        return self.status == MountStatus.HEALTHY


class MountManager:
    """Manages and monitors mount points."""
    
    def __init__(self, check_interval: int = 30):
        self.check_interval = check_interval
        self.mount_points: Dict[str, MountPoint] = {}
        self.monitoring_active = False
        self.monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
    def discover_mounts(self) -> List[MountPoint]:
        """Discover all mount points on the system."""
        logger.info("Discovering mount points...")
        
        mount_points = []
        
        try:
            # Get mount information from psutil
            for partition in psutil.disk_partitions():
                mount_point = self._create_mount_point(partition)
                if mount_point:
                    mount_points.append(mount_point)
            
            # Update internal registry
            self.mount_points = {mp.path: mp for mp in mount_points}
            
            logger.info(f"Discovered {len(mount_points)} mount points")
            
        except Exception as e:
            logger.error(f"Error discovering mounts: {e}")
            
        return mount_points
    
    def _create_mount_point(self, partition) -> Optional[MountPoint]:
        """Create MountPoint from psutil partition info."""
        try:
            # Determine mount type
            mount_type = self._detect_mount_type(partition.fstype, partition.device)
            
            # Initial health check
            status = MountStatus.UNKNOWN
            response_time = None
            error_message = None
            
            if os.path.exists(partition.mountpoint):
                status, response_time, error_message = self._check_mount_health(partition.mountpoint)
            else:
                status = MountStatus.UNAVAILABLE
                error_message = "Mount point does not exist"
            
            return MountPoint(
                path=partition.mountpoint,
                mount_type=mount_type,
                device=partition.device,
                filesystem=partition.fstype,
                options=partition.opts.split(',') if partition.opts else [],
                status=status,
                last_check=time.time(),
                response_time_ms=response_time,
                error_message=error_message
            )
            
        except Exception as e:
            logger.warning(f"Error creating mount point for {partition.mountpoint}: {e}")
            return None
    
    def _detect_mount_type(self, fstype: str, device: str) -> MountType:
        """Detect mount type from filesystem and device info."""
        fstype_lower = fstype.lower()
        device_lower = device.lower()
        
        if fstype_lower == "nfs" or "nfs" in fstype_lower:
            return MountType.NFS
        elif fstype_lower in ["cifs", "smb", "smbfs"]:
            return MountType.CIFS
        elif fstype_lower == "fuse.sshfs" or "sshfs" in device_lower:
            return MountType.SSHFS
        elif ":" in device and not device.startswith("/"):
            # Network device format (host:path)
            return MountType.NFS  # Default assumption
        elif device.startswith("/dev/"):
            return MountType.LOCAL
        else:
            return MountType.UNKNOWN
    
    def _check_mount_health(self, mount_path: str) -> Tuple[MountStatus, Optional[float], Optional[str]]:
        """Check health of a mount point."""
        start_time = time.time()
        
        try:
            # Test basic directory access
            if not os.path.exists(mount_path):
                return MountStatus.UNAVAILABLE, None, "Mount point does not exist"
            
            if not os.access(mount_path, os.R_OK):
                return MountStatus.UNAVAILABLE, None, "Mount point not readable"
            
            # Test directory listing (lightweight operation)
            try:
                os.listdir(mount_path)
                response_time = (time.time() - start_time) * 1000  # Convert to ms
                
                # Classify response time
                if response_time < 100:
                    return MountStatus.HEALTHY, response_time, None
                elif response_time < 1000:
                    return MountStatus.DEGRADED, response_time, f"Slow response: {response_time:.1f}ms"
                else:
                    return MountStatus.DEGRADED, response_time, f"Very slow response: {response_time:.1f}ms"
                    
            except PermissionError:
                return MountStatus.DEGRADED, None, "Permission denied"
            except OSError as e:
                if "Transport endpoint is not connected" in str(e):
                    return MountStatus.UNAVAILABLE, None, "Network mount disconnected"
                elif "Host is down" in str(e):
                    return MountStatus.UNAVAILABLE, None, "Network host unreachable"
                else:
                    return MountStatus.UNAVAILABLE, None, f"I/O error: {e}"
                    
        except Exception as e:
            return MountStatus.UNAVAILABLE, None, f"Health check failed: {e}"
    
    def check_mount_health(self, mount_path: str) -> MountPoint:
        """Check health of specific mount point."""
        if mount_path not in self.mount_points:
            # Try to discover this mount
            self.discover_mounts()
        
        if mount_path in self.mount_points:
            mount_point = self.mount_points[mount_path]
            status, response_time, error_message = self._check_mount_health(mount_path)
            
            # Update mount point status
            mount_point.status = status
            mount_point.response_time_ms = response_time
            mount_point.error_message = error_message
            mount_point.last_check = time.time()
            
            return mount_point
        else:
            # Create a basic mount point for unknown paths
            return MountPoint(
                path=mount_path,
                mount_type=MountType.UNKNOWN,
                device="unknown",
                filesystem="unknown",
                options=[],
                status=MountStatus.UNAVAILABLE,
                last_check=time.time(),
                error_message="Mount point not found"
            )
    
    def get_media_mounts(self, media_paths: List[str]) -> List[MountPoint]:
        """Get mount points for specific media paths."""
        media_mounts = []
        
        for path in media_paths:
            # Find the mount point that contains this path
            mount_path = self._find_mount_for_path(path)
            if mount_path:
                mount_point = self.check_mount_health(mount_path)
                media_mounts.append(mount_point)
        
        return media_mounts
    
    def _find_mount_for_path(self, path: str) -> Optional[str]:
        """Find the mount point that contains the given path."""
        path = os.path.abspath(path)
        
        # Check known mount points first
        for mount_path in self.mount_points:
            if path.startswith(mount_path):
                return mount_path
        
        # Find mount point using system calls
        try:
            # Use stat to find the device
            path_stat = os.stat(path)
            
            for partition in psutil.disk_partitions():
                try:
                    mount_stat = os.stat(partition.mountpoint)
                    if path_stat.st_dev == mount_stat.st_dev:
                        return partition.mountpoint
                except OSError:
                    continue
                    
        except OSError:
            pass
        
        return None
    
    def start_monitoring(self):
        """Start background monitoring of mount points."""
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self._stop_event.clear()
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        logger.info("Mount monitoring started")
    
    def stop_monitoring(self):
        """Stop background monitoring."""
        if not self.monitoring_active:
            return
        
        self.monitoring_active = False
        self._stop_event.set()
        
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)
        
        logger.info("Mount monitoring stopped")
    
    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.monitoring_active and not self._stop_event.is_set():
            try:
                # Check all known mount points
                with ThreadPoolExecutor(max_workers=4) as executor:
                    futures = []
                    
                    for mount_path in list(self.mount_points.keys()):
                        future = executor.submit(self._check_mount_health, mount_path)
                        futures.append((mount_path, future))
                    
                    # Collect results
                    for mount_path, future in futures:
                        try:
                            status, response_time, error_message = future.result(timeout=30)
                            
                            if mount_path in self.mount_points:
                                mount_point = self.mount_points[mount_path]
                                old_status = mount_point.status
                                
                                # Update status
                                mount_point.status = status
                                mount_point.response_time_ms = response_time
                                mount_point.error_message = error_message
                                mount_point.last_check = time.time()
                                
                                # Log status changes
                                if old_status != status:
                                    logger.info(f"Mount {mount_path} status changed: {old_status.value} → {status.value}")
                                    
                        except Exception as e:
                            logger.warning(f"Error monitoring mount {mount_path}: {e}")
                
            except Exception as e:
                logger.error(f"Error in mount monitoring loop: {e}")
            
            # Wait for next check
            self._stop_event.wait(self.check_interval)
    
    def get_mount_report(self) -> Dict:
        """Get comprehensive mount status report."""
        report = {
            "total_mounts": len(self.mount_points),
            "healthy_mounts": 0,
            "degraded_mounts": 0,
            "unavailable_mounts": 0,
            "network_mounts": 0,
            "local_mounts": 0,
            "mounts": []
        }
        
        for mount_point in self.mount_points.values():
            # Update counters
            if mount_point.status == MountStatus.HEALTHY:
                report["healthy_mounts"] += 1
            elif mount_point.status == MountStatus.DEGRADED:
                report["degraded_mounts"] += 1
            elif mount_point.status == MountStatus.UNAVAILABLE:
                report["unavailable_mounts"] += 1
            
            if mount_point.is_network_mount:
                report["network_mounts"] += 1
            else:
                report["local_mounts"] += 1
            
            # Add mount info
            mount_info = {
                "path": mount_point.path,
                "type": mount_point.mount_type.value,
                "device": mount_point.device,
                "filesystem": mount_point.filesystem,
                "status": mount_point.status.value,
                "response_time_ms": mount_point.response_time_ms,
                "last_check": mount_point.last_check,
                "error_message": mount_point.error_message,
                "is_network": mount_point.is_network_mount
            }
            
            report["mounts"].append(mount_info)
        
        return report


class AutoMounter:
    """Automatic mount management for known media sources."""
    
    def __init__(self, mount_manager: MountManager):
        self.mount_manager = mount_manager
        self.auto_mount_configs: Dict[str, Dict] = {}
    
    def add_auto_mount(self, path: str, config: Dict):
        """Add auto-mount configuration for a path."""
        self.auto_mount_configs[path] = config
        logger.info(f"Added auto-mount config for {path}")
    
    def attempt_auto_mount(self, path: str) -> bool:
        """Attempt to automatically mount a path."""
        if path not in self.auto_mount_configs:
            return False
        
        config = self.auto_mount_configs[path]
        
        try:
            # Build mount command based on config
            mount_cmd = self._build_mount_command(path, config)
            
            logger.info(f"Attempting auto-mount: {' '.join(mount_cmd)}")
            
            # Execute mount command
            result = subprocess.run(
                mount_cmd,
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                logger.info(f"Successfully auto-mounted {path}")
                
                # Refresh mount discovery
                self.mount_manager.discover_mounts()
                
                return True
            else:
                logger.error(f"Auto-mount failed for {path}: {result.stderr}")
                return False
                
        except Exception as e:
            logger.error(f"Error during auto-mount of {path}: {e}")
            return False
    
    def _build_mount_command(self, path: str, config: Dict) -> List[str]:
        """Build mount command from configuration."""
        mount_type = config.get("type", "nfs")
        device = config["device"]
        options = config.get("options", [])
        
        cmd = ["mount"]
        
        if mount_type == "nfs":
            cmd.extend(["-t", "nfs"])
        elif mount_type == "cifs":
            cmd.extend(["-t", "cifs"])
        elif mount_type == "sshfs":
            cmd = ["sshfs"]
        
        if options:
            cmd.extend(["-o", ",".join(options)])
        
        cmd.extend([device, path])
        
        return cmd


def get_mount_manager() -> MountManager:
    """Get singleton mount manager instance."""
    if not hasattr(get_mount_manager, '_instance'):
        get_mount_manager._instance = MountManager()
    return get_mount_manager._instance 