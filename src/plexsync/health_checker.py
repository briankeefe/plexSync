"""
System health checker for PlexSync.

This module provides comprehensive system health diagnostics, including
connectivity checks, filesystem validation, configuration verification,
and dependency analysis. It leverages existing environment and mount
management systems while adding health monitoring capabilities.
"""

import os
import sys
import subprocess
import time
import socket
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

from .environment import EnvironmentValidator, CheckStatus, EnvironmentCheck
from .mount import get_mount_manager, MountStatus
from .config import get_config_manager
from .settings_manager import get_settings_manager

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    """Health check status levels."""
    HEALTHY = "healthy"
    WARNING = "warning"  
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class HealthCategory(Enum):
    """Health check categories."""
    CONNECTIVITY = "connectivity"
    FILESYSTEM = "filesystem"
    CONFIGURATION = "configuration"
    DEPENDENCIES = "dependencies"
    PERFORMANCE = "performance"


@dataclass
class HealthResult:
    """Individual health check result."""
    name: str
    category: HealthCategory
    status: HealthStatus
    message: str
    details: Optional[str] = None
    fix_suggestion: Optional[str] = None
    check_duration_ms: Optional[float] = None
    severity: int = 1  # 1=low, 2=medium, 3=high, 4=critical
    
    @property
    def is_healthy(self) -> bool:
        """Check if result indicates healthy status."""
        return self.status == HealthStatus.HEALTHY
    
    @property
    def needs_attention(self) -> bool:
        """Check if result needs user attention."""
        return self.status in [HealthStatus.WARNING, HealthStatus.CRITICAL]


@dataclass
class HealthReport:
    """Complete system health report."""
    results: List[HealthResult] = field(default_factory=list)
    total_checks: int = 0
    healthy_count: int = 0
    warning_count: int = 0
    critical_count: int = 0
    unknown_count: int = 0
    total_duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    
    def add_result(self, result: HealthResult):
        """Add a health check result to the report."""
        self.results.append(result)
        self.total_checks += 1
        
        if result.status == HealthStatus.HEALTHY:
            self.healthy_count += 1
        elif result.status == HealthStatus.WARNING:
            self.warning_count += 1
        elif result.status == HealthStatus.CRITICAL:
            self.critical_count += 1
        else:
            self.unknown_count += 1
        
        if result.check_duration_ms:
            self.total_duration_ms += result.check_duration_ms
    
    @property
    def overall_health(self) -> HealthStatus:
        """Get overall system health status."""
        if self.critical_count > 0:
            return HealthStatus.CRITICAL
        elif self.warning_count > 0:
            return HealthStatus.WARNING
        elif self.healthy_count > 0:
            return HealthStatus.HEALTHY
        else:
            return HealthStatus.UNKNOWN
    
    @property
    def health_percentage(self) -> float:
        """Get health percentage (0-100)."""
        if self.total_checks == 0:
            return 0.0
        return (self.healthy_count / self.total_checks) * 100.0


class HealthChecker:
    """Comprehensive system health checker for PlexSync."""
    
    def __init__(self):
        self.settings = get_settings_manager().settings
        self.config_manager = get_config_manager()
        self.mount_manager = get_mount_manager()
        self.env_validator = EnvironmentValidator()
    
    def run_all_checks(self, categories: Optional[List[HealthCategory]] = None, 
                      parallel: bool = None) -> HealthReport:
        """Run all health checks and return comprehensive report."""
        if parallel is None:
            parallel = self.settings.performance.parallel_health_checks
        
        if categories is None:
            categories = list(HealthCategory)
        
        report = HealthReport()
        start_time = time.time()
        
        logger.info(f"Starting health checks for categories: {[c.value for c in categories]}")
        
        # Collect all check functions
        check_functions = []
        
        if HealthCategory.CONNECTIVITY in categories:
            check_functions.extend(self._get_connectivity_checks())
        if HealthCategory.FILESYSTEM in categories:
            check_functions.extend(self._get_filesystem_checks())
        if HealthCategory.CONFIGURATION in categories:
            check_functions.extend(self._get_configuration_checks())
        if HealthCategory.DEPENDENCIES in categories:
            check_functions.extend(self._get_dependency_checks())
        if HealthCategory.PERFORMANCE in categories:
            check_functions.extend(self._get_performance_checks())
        
        # Run checks (parallel or sequential)
        if parallel and len(check_functions) > 1:
            results = self._run_checks_parallel(check_functions)
        else:
            results = self._run_checks_sequential(check_functions)
        
        # Add results to report
        for result in results:
            report.add_result(result)
        
        # Calculate total duration
        report.total_duration_ms = (time.time() - start_time) * 1000
        
        logger.info(f"Health check completed: {report.healthy_count}/{report.total_checks} healthy "
                   f"({report.health_percentage:.1f}%) in {report.total_duration_ms:.1f}ms")
        
        return report
    
    def _run_checks_parallel(self, check_functions: List[callable]) -> List[HealthResult]:
        """Run health checks in parallel."""
        results = []
        max_workers = min(self.settings.performance.max_workers, len(check_functions))
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_check = {executor.submit(check_func): check_func for check_func in check_functions}
            
            for future in as_completed(future_to_check):
                try:
                    result = future.result(timeout=self.settings.performance.health_check_timeout)
                    results.append(result)
                except Exception as e:
                    check_func = future_to_check[future]
                    error_result = HealthResult(
                        name=f"{check_func.__name__}",
                        category=HealthCategory.UNKNOWN,
                        status=HealthStatus.CRITICAL,
                        message=f"Check failed with error: {e}",
                        fix_suggestion="Check system logs for more details"
                    )
                    results.append(error_result)
        
        return results
    
    def _run_checks_sequential(self, check_functions: List[callable]) -> List[HealthResult]:
        """Run health checks sequentially."""
        results = []
        
        for check_func in check_functions:
            try:
                result = check_func()
                results.append(result)
            except Exception as e:
                error_result = HealthResult(
                    name=f"{check_func.__name__}",
                    category=HealthCategory.UNKNOWN,
                    status=HealthStatus.CRITICAL,
                    message=f"Check failed with error: {e}",
                    fix_suggestion="Check system logs for more details"
                )
                results.append(error_result)
        
        return results
    
    def _get_connectivity_checks(self) -> List[callable]:
        """Get connectivity check functions."""
        return [
            self._check_network_connectivity,
            self._check_dns_resolution,
            self._check_mount_connectivity
        ]
    
    def _get_filesystem_checks(self) -> List[callable]:
        """Get filesystem check functions."""
        return [
            self._check_mount_points,
            self._check_disk_space,
            self._check_permissions,
            self._check_path_accessibility
        ]
    
    def _get_configuration_checks(self) -> List[callable]:
        """Get configuration check functions."""
        return [
            self._check_config_validity,
            self._check_settings_validity,
            self._check_required_paths,
            self._check_credential_access
        ]
    
    def _get_dependency_checks(self) -> List[callable]:
        """Get dependency check functions."""
        return [
            self._check_python_version,
            self._check_required_binaries,
            self._check_python_packages,
            self._check_system_capabilities
        ]
    
    def _get_performance_checks(self) -> List[callable]:
        """Get performance check functions."""
        return [
            self._check_system_resources,
            self._check_io_performance,
            self._check_network_performance
        ]
    
    # Connectivity Checks
    
    def _check_network_connectivity(self) -> HealthResult:
        """Check basic network connectivity."""
        start_time = time.time()
        
        try:
            # Test connectivity to a reliable host
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Network Connectivity",
                category=HealthCategory.CONNECTIVITY,
                status=HealthStatus.HEALTHY,
                message="Network connectivity is working",
                details=f"Connection test successful in {duration_ms:.1f}ms",
                check_duration_ms=duration_ms
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Network Connectivity",
                category=HealthCategory.CONNECTIVITY,
                status=HealthStatus.CRITICAL,
                message="Network connectivity failed",
                details=str(e),
                fix_suggestion="Check network connection and firewall settings",
                check_duration_ms=duration_ms,
                severity=4
            )
    
    def _check_dns_resolution(self) -> HealthResult:
        """Check DNS resolution."""
        start_time = time.time()
        
        try:
            socket.gethostbyname("google.com")
            
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="DNS Resolution",
                category=HealthCategory.CONNECTIVITY,
                status=HealthStatus.HEALTHY,
                message="DNS resolution is working",
                details=f"DNS lookup successful in {duration_ms:.1f}ms",
                check_duration_ms=duration_ms
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="DNS Resolution",
                category=HealthCategory.CONNECTIVITY,
                status=HealthStatus.CRITICAL,
                message="DNS resolution failed",
                details=str(e),
                fix_suggestion="Check DNS server configuration",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_mount_connectivity(self) -> HealthResult:
        """Check mount point connectivity."""
        start_time = time.time()
        
        try:
            # Discover and check mount points
            mount_points = self.mount_manager.discover_mounts()
            
            # Filter to network mounts
            network_mounts = [mp for mp in mount_points if mp.is_network_mount]
            
            if not network_mounts:
                duration_ms = (time.time() - start_time) * 1000
                return HealthResult(
                    name="Mount Connectivity",
                    category=HealthCategory.CONNECTIVITY,
                    status=HealthStatus.HEALTHY,
                    message="No network mounts configured",
                    details="Only local mounts found",
                    check_duration_ms=duration_ms
                )
            
            # Check health of network mounts
            unhealthy_mounts = [mp for mp in network_mounts if not mp.is_healthy]
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not unhealthy_mounts:
                return HealthResult(
                    name="Mount Connectivity",
                    category=HealthCategory.CONNECTIVITY,
                    status=HealthStatus.HEALTHY,
                    message=f"All {len(network_mounts)} network mounts are healthy",
                    details=f"Checked {len(network_mounts)} network mount points",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Mount Connectivity",
                    category=HealthCategory.CONNECTIVITY,
                    status=HealthStatus.WARNING,
                    message=f"{len(unhealthy_mounts)}/{len(network_mounts)} network mounts have issues",
                    details=f"Unhealthy mounts: {[mp.path for mp in unhealthy_mounts]}",
                    fix_suggestion="Check network mount configuration and connectivity",
                    check_duration_ms=duration_ms,
                    severity=2
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Mount Connectivity",
                category=HealthCategory.CONNECTIVITY,
                status=HealthStatus.CRITICAL,
                message="Mount connectivity check failed",
                details=str(e),
                fix_suggestion="Check mount manager configuration",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    # Filesystem Checks
    
    def _check_mount_points(self) -> HealthResult:
        """Check mount point status."""
        start_time = time.time()
        
        try:
            # Get active configuration
            config = self.config_manager.get_active_profile()
            if not config:
                duration_ms = (time.time() - start_time) * 1000
                return HealthResult(
                    name="Mount Points",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.WARNING,
                    message="No active configuration profile",
                    fix_suggestion="Configure a profile with media sources",
                    check_duration_ms=duration_ms,
                    severity=2
                )
            
            # Check media source paths
            source_paths = [source.base_path for source in config.sources]
            missing_paths = []
            accessible_paths = []
            
            for path in source_paths:
                if os.path.exists(path) and os.access(path, os.R_OK):
                    accessible_paths.append(path)
                else:
                    missing_paths.append(path)
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not missing_paths:
                return HealthResult(
                    name="Mount Points",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.HEALTHY,
                    message=f"All {len(accessible_paths)} media source paths are accessible",
                    details=f"Checked paths: {accessible_paths}",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Mount Points",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.CRITICAL,
                    message=f"{len(missing_paths)}/{len(source_paths)} media source paths are inaccessible",
                    details=f"Missing paths: {missing_paths}",
                    fix_suggestion="Check that media source paths are mounted and accessible",
                    check_duration_ms=duration_ms,
                    severity=4
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Mount Points",
                category=HealthCategory.FILESYSTEM,
                status=HealthStatus.CRITICAL,
                message="Mount point check failed",
                details=str(e),
                fix_suggestion="Check configuration and mount status",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_disk_space(self) -> HealthResult:
        """Check available disk space."""
        start_time = time.time()
        
        try:
            # Check space on important directories
            paths_to_check = [
                self.settings.paths.config_dir,
                self.settings.paths.cache_dir,
                self.settings.paths.log_dir,
                self.settings.paths.backup_dir,
                self.settings.paths.temp_dir
            ]
            
            low_space_paths = []
            space_info = {}
            
            for path in paths_to_check:
                try:
                    if os.path.exists(path):
                        statvfs = os.statvfs(path)
                        free_bytes = statvfs.f_frsize * statvfs.f_bavail
                        free_gb = free_bytes / (1024**3)
                        space_info[path] = free_gb
                        
                        # Consider less than 1GB as low space
                        if free_gb < 1.0:
                            low_space_paths.append((path, free_gb))
                    
                except Exception:
                    # Skip paths that can't be checked
                    continue
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not low_space_paths:
                min_space = min(space_info.values()) if space_info else 0
                return HealthResult(
                    name="Disk Space",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.HEALTHY,
                    message=f"Sufficient disk space available (minimum: {min_space:.1f}GB)",
                    details=f"Checked {len(space_info)} directories",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Disk Space",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.WARNING,
                    message=f"{len(low_space_paths)} directories have low disk space",
                    details=f"Low space paths: {[(p, f'{s:.1f}GB') for p, s in low_space_paths]}",
                    fix_suggestion="Free up disk space or clean up old files",
                    check_duration_ms=duration_ms,
                    severity=2
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Disk Space",
                category=HealthCategory.FILESYSTEM,
                status=HealthStatus.CRITICAL,
                message="Disk space check failed",
                details=str(e),
                fix_suggestion="Check filesystem permissions and availability",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_permissions(self) -> HealthResult:
        """Check directory permissions."""
        start_time = time.time()
        
        try:
            # Check permissions on critical directories
            dirs_to_check = [
                (self.settings.paths.config_dir, "read/write"),
                (self.settings.paths.cache_dir, "read/write"),
                (self.settings.paths.log_dir, "read/write"),
                (self.settings.paths.backup_dir, "read/write"),
                (self.settings.paths.temp_dir, "read/write")
            ]
            
            permission_issues = []
            
            for dir_path, required_perms in dirs_to_check:
                try:
                    # Create directory if it doesn't exist
                    os.makedirs(dir_path, exist_ok=True)
                    
                    # Test read permission
                    if not os.access(dir_path, os.R_OK):
                        permission_issues.append(f"{dir_path}: no read access")
                        continue
                    
                    # Test write permission
                    if not os.access(dir_path, os.W_OK):
                        permission_issues.append(f"{dir_path}: no write access")
                        continue
                    
                    # Test by creating a temp file
                    test_file = os.path.join(dir_path, ".plexsync_permission_test")
                    try:
                        with open(test_file, 'w') as f:
                            f.write("test")
                        os.remove(test_file)
                    except Exception:
                        permission_issues.append(f"{dir_path}: cannot create files")
                        
                except Exception as e:
                    permission_issues.append(f"{dir_path}: {e}")
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not permission_issues:
                return HealthResult(
                    name="Permissions",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.HEALTHY,
                    message=f"All {len(dirs_to_check)} directories have correct permissions",
                    details="Read/write access verified",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Permissions",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.CRITICAL,
                    message=f"{len(permission_issues)} permission issues found",
                    details="; ".join(permission_issues),
                    fix_suggestion="Check directory ownership and permissions (chmod/chown)",
                    check_duration_ms=duration_ms,
                    severity=4
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Permissions",
                category=HealthCategory.FILESYSTEM,
                status=HealthStatus.CRITICAL,
                message="Permission check failed",
                details=str(e),
                fix_suggestion="Check filesystem access and user permissions",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_path_accessibility(self) -> HealthResult:
        """Check accessibility of configured paths."""
        start_time = time.time()
        
        try:
            config = self.config_manager.get_active_profile()
            if not config:
                duration_ms = (time.time() - start_time) * 1000
                return HealthResult(
                    name="Path Accessibility",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.WARNING,
                    message="No active configuration to check",
                    fix_suggestion="Configure media sources and destinations",
                    check_duration_ms=duration_ms,
                    severity=2
                )
            
            # Check destination paths
            dest_issues = []
            if not os.path.exists(config.destinations.movies):
                dest_issues.append(f"Movies destination: {config.destinations.movies}")
            if not os.path.exists(config.destinations.tv):
                dest_issues.append(f"TV destination: {config.destinations.tv}")
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not dest_issues:
                return HealthResult(
                    name="Path Accessibility",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.HEALTHY,
                    message="All configured paths are accessible",
                    details="Destination paths verified",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Path Accessibility",
                    category=HealthCategory.FILESYSTEM,
                    status=HealthStatus.WARNING,
                    message=f"{len(dest_issues)} destination paths not found",
                    details="; ".join(dest_issues),
                    fix_suggestion="Create missing destination directories or update configuration",
                    check_duration_ms=duration_ms,
                    severity=2
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Path Accessibility",
                category=HealthCategory.FILESYSTEM,
                status=HealthStatus.CRITICAL,
                message="Path accessibility check failed",
                details=str(e),
                fix_suggestion="Check configuration and path settings",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    # Configuration Checks
    
    def _check_config_validity(self) -> HealthResult:
        """Check configuration validity."""
        start_time = time.time()
        
        try:
            errors = self.config_manager.validate_active_profile()
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not errors:
                return HealthResult(
                    name="Configuration Validity",
                    category=HealthCategory.CONFIGURATION,
                    status=HealthStatus.HEALTHY,
                    message="Configuration is valid",
                    details="All profile settings validated successfully",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Configuration Validity",
                    category=HealthCategory.CONFIGURATION,
                    status=HealthStatus.CRITICAL,
                    message=f"{len(errors)} configuration errors found",
                    details="; ".join(errors),
                    fix_suggestion="Fix configuration errors using 'plexsync config --validate'",
                    check_duration_ms=duration_ms,
                    severity=4
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Configuration Validity",
                category=HealthCategory.CONFIGURATION,
                status=HealthStatus.CRITICAL,
                message="Configuration validation failed",
                details=str(e),
                fix_suggestion="Check configuration file format and content",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_settings_validity(self) -> HealthResult:
        """Check system settings validity."""
        start_time = time.time()
        
        try:
            errors = self.settings.validate()
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not errors:
                return HealthResult(
                    name="Settings Validity",
                    category=HealthCategory.CONFIGURATION,
                    status=HealthStatus.HEALTHY,
                    message="System settings are valid",
                    details="All settings validated successfully",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Settings Validity",
                    category=HealthCategory.CONFIGURATION,
                    status=HealthStatus.WARNING,
                    message=f"{len(errors)} settings validation issues",
                    details="; ".join(errors),
                    fix_suggestion="Review and fix settings using 'plexsync system settings'",
                    check_duration_ms=duration_ms,
                    severity=2
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Settings Validity",
                category=HealthCategory.CONFIGURATION,
                status=HealthStatus.CRITICAL,
                message="Settings validation failed",
                details=str(e),
                fix_suggestion="Check system settings configuration",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_required_paths(self) -> HealthResult:
        """Check that required paths exist."""
        start_time = time.time()
        
        try:
            required_paths = [
                self.settings.paths.config_dir,
                self.settings.paths.cache_dir,
                self.settings.paths.log_dir
            ]
            
            missing_paths = []
            for path in required_paths:
                if not os.path.exists(path):
                    missing_paths.append(path)
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not missing_paths:
                return HealthResult(
                    name="Required Paths",
                    category=HealthCategory.CONFIGURATION,
                    status=HealthStatus.HEALTHY,
                    message="All required paths exist",
                    details=f"Checked {len(required_paths)} paths",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Required Paths",
                    category=HealthCategory.CONFIGURATION,
                    status=HealthStatus.WARNING,
                    message=f"{len(missing_paths)} required paths are missing",
                    details=f"Missing: {missing_paths}",
                    fix_suggestion="Paths will be created automatically when needed",
                    check_duration_ms=duration_ms,
                    severity=1
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Required Paths",
                category=HealthCategory.CONFIGURATION,
                status=HealthStatus.CRITICAL,
                message="Required paths check failed",
                details=str(e),
                fix_suggestion="Check path configuration and filesystem access",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_credential_access(self) -> HealthResult:
        """Check credential storage access."""
        start_time = time.time()
        
        try:
            # Test keyring access if secure credential storage is enabled
            if self.settings.security.secure_credential_storage:
                try:
                    import keyring
                    # Test with a dummy credential
                    test_key = "plexsync_health_test"
                    keyring.set_password("plexsync_test", test_key, "test_value")
                    retrieved = keyring.get_password("plexsync_test", test_key)
                    keyring.delete_password("plexsync_test", test_key)
                    
                    if retrieved == "test_value":
                        credential_status = "Secure credential storage working"
                    else:
                        credential_status = "Credential storage test failed"
                        
                except Exception as e:
                    credential_status = f"Credential storage error: {e}"
            else:
                credential_status = "Secure credential storage disabled"
            
            duration_ms = (time.time() - start_time) * 1000
            
            if "working" in credential_status or "disabled" in credential_status:
                return HealthResult(
                    name="Credential Access",
                    category=HealthCategory.CONFIGURATION,
                    status=HealthStatus.HEALTHY,
                    message=credential_status,
                    details="Credential storage configuration validated",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Credential Access",
                    category=HealthCategory.CONFIGURATION,
                    status=HealthStatus.WARNING,
                    message="Credential storage issues detected",
                    details=credential_status,
                    fix_suggestion="Check keyring installation and configuration",
                    check_duration_ms=duration_ms,
                    severity=2
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Credential Access",
                category=HealthCategory.CONFIGURATION,
                status=HealthStatus.WARNING,
                message="Credential access check failed",
                details=str(e),
                fix_suggestion="Check keyring and credential storage setup",
                check_duration_ms=duration_ms,
                severity=2
            )
    
    # Dependency Checks
    
    def _check_python_version(self) -> HealthResult:
        """Check Python version compatibility."""
        start_time = time.time()
        
        try:
            version_info = sys.version_info
            version_str = f"{version_info.major}.{version_info.minor}.{version_info.micro}"
            
            # PlexSync requires Python 3.8+
            if version_info >= (3, 8):
                status = HealthStatus.HEALTHY
                message = f"Python version {version_str} is supported"
                severity = 0
                fix_suggestion = None
            elif version_info >= (3, 6):
                status = HealthStatus.WARNING
                message = f"Python version {version_str} is deprecated"
                severity = 2
                fix_suggestion = "Consider upgrading to Python 3.8 or higher"
            else:
                status = HealthStatus.CRITICAL
                message = f"Python version {version_str} is not supported"
                severity = 4
                fix_suggestion = "Upgrade to Python 3.8 or higher"
            
            duration_ms = (time.time() - start_time) * 1000
            
            return HealthResult(
                name="Python Version",
                category=HealthCategory.DEPENDENCIES,
                status=status,
                message=message,
                details=f"Running on Python {version_str}",
                fix_suggestion=fix_suggestion,
                check_duration_ms=duration_ms,
                severity=severity
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Python Version",
                category=HealthCategory.DEPENDENCIES,
                status=HealthStatus.CRITICAL,
                message="Python version check failed",
                details=str(e),
                fix_suggestion="Check Python installation",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_required_binaries(self) -> HealthResult:
        """Check required system binaries."""
        start_time = time.time()
        
        try:
            # Required binaries
            required_binaries = ["rsync"]
            optional_binaries = ["ssh", "scp"]
            
            missing_required = []
            missing_optional = []
            found_binaries = []
            
            # Check required binaries
            for binary in required_binaries:
                if self._check_binary_exists(binary):
                    found_binaries.append(binary)
                else:
                    missing_required.append(binary)
            
            # Check optional binaries
            for binary in optional_binaries:
                if self._check_binary_exists(binary):
                    found_binaries.append(binary)
                else:
                    missing_optional.append(binary)
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not missing_required:
                if not missing_optional:
                    return HealthResult(
                        name="Required Binaries",
                        category=HealthCategory.DEPENDENCIES,
                        status=HealthStatus.HEALTHY,
                        message=f"All required and optional binaries available",
                        details=f"Found: {', '.join(found_binaries)}",
                        check_duration_ms=duration_ms
                    )
                else:
                    return HealthResult(
                        name="Required Binaries",
                        category=HealthCategory.DEPENDENCIES,
                        status=HealthStatus.HEALTHY,
                        message="All required binaries available",
                        details=f"Found: {', '.join(found_binaries)}, Missing optional: {', '.join(missing_optional)}",
                        fix_suggestion=f"Consider installing optional binaries: {', '.join(missing_optional)}",
                        check_duration_ms=duration_ms,
                        severity=1
                    )
            else:
                return HealthResult(
                    name="Required Binaries",
                    category=HealthCategory.DEPENDENCIES,
                    status=HealthStatus.CRITICAL,
                    message=f"Missing required binaries: {', '.join(missing_required)}",
                    details=f"Found: {', '.join(found_binaries)}",
                    fix_suggestion=f"Install missing binaries: {', '.join(missing_required)}",
                    check_duration_ms=duration_ms,
                    severity=4
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Required Binaries",
                category=HealthCategory.DEPENDENCIES,
                status=HealthStatus.CRITICAL,
                message="Binary check failed",
                details=str(e),
                fix_suggestion="Check system PATH and binary installations",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_binary_exists(self, binary_name: str) -> bool:
        """Check if a binary exists in PATH."""
        try:
            result = subprocess.run(['which', binary_name], 
                                 capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except Exception:
            return False
    
    def _check_python_packages(self) -> HealthResult:
        """Check required Python packages."""
        start_time = time.time()
        
        try:
            required_packages = [
                "click", "rich", "pyyaml", "psutil", "keyring", "cryptography"
            ]
            
            missing_packages = []
            found_packages = []
            
            for package in required_packages:
                try:
                    __import__(package)
                    found_packages.append(package)
                except ImportError:
                    missing_packages.append(package)
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not missing_packages:
                return HealthResult(
                    name="Python Packages",
                    category=HealthCategory.DEPENDENCIES,
                    status=HealthStatus.HEALTHY,
                    message=f"All {len(required_packages)} required packages available",
                    details=f"Found: {', '.join(found_packages)}",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="Python Packages",
                    category=HealthCategory.DEPENDENCIES,
                    status=HealthStatus.CRITICAL,
                    message=f"Missing required packages: {', '.join(missing_packages)}",
                    details=f"Found: {', '.join(found_packages)}",
                    fix_suggestion=f"Install missing packages: pip install {' '.join(missing_packages)}",
                    check_duration_ms=duration_ms,
                    severity=4
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Python Packages",
                category=HealthCategory.DEPENDENCIES,
                status=HealthStatus.CRITICAL,
                message="Package check failed",
                details=str(e),
                fix_suggestion="Check Python package installation",
                check_duration_ms=duration_ms,
                severity=3
            )
    
    def _check_system_capabilities(self) -> HealthResult:
        """Check system capabilities."""
        start_time = time.time()
        
        try:
            capabilities = []
            issues = []
            
            # Check terminal capabilities  
            if os.isatty(sys.stdout.fileno()):
                capabilities.append("Interactive terminal")
            else:
                capabilities.append("Non-interactive mode")
            
            # Check color support
            if os.environ.get('TERM') in ['xterm-256color', 'screen-256color']:
                capabilities.append("256-color support")
            elif os.environ.get('TERM'):
                capabilities.append(f"Terminal: {os.environ['TERM']}")
            
            # Check environment variables
            if os.environ.get('HOME') or os.environ.get('USERPROFILE'):
                capabilities.append("Home directory available")
            else:
                issues.append("Home directory not detected")
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not issues:
                return HealthResult(
                    name="System Capabilities",
                    category=HealthCategory.DEPENDENCIES,
                    status=HealthStatus.HEALTHY,
                    message="System capabilities are adequate",
                    details="; ".join(capabilities),
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="System Capabilities",
                    category=HealthCategory.DEPENDENCIES,
                    status=HealthStatus.WARNING,
                    message=f"{len(issues)} capability issues detected",
                    details=f"Issues: {'; '.join(issues)}; Capabilities: {'; '.join(capabilities)}",
                    fix_suggestion="Check system environment and terminal configuration",
                    check_duration_ms=duration_ms,
                    severity=2
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="System Capabilities",
                category=HealthCategory.DEPENDENCIES,
                status=HealthStatus.WARNING,
                message="Capability check encountered issues",
                details=str(e),
                fix_suggestion="Check system configuration",
                check_duration_ms=duration_ms,
                severity=2
            )
    
    # Performance Checks
    
    def _check_system_resources(self) -> HealthResult:
        """Check system resource availability."""
        start_time = time.time()
        
        try:
            import psutil
            
            # Get system stats
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            disk = psutil.disk_usage('/')
            
            issues = []
            
            # Check CPU usage
            if cpu_percent > 90:
                issues.append(f"High CPU usage: {cpu_percent:.1f}%")
            
            # Check memory usage
            if memory.percent > 90:
                issues.append(f"High memory usage: {memory.percent:.1f}%")
            
            # Check disk usage
            if disk.percent > 90:
                issues.append(f"High disk usage: {disk.percent:.1f}%")
            
            duration_ms = (time.time() - start_time) * 1000
            
            if not issues:
                return HealthResult(
                    name="System Resources",
                    category=HealthCategory.PERFORMANCE,
                    status=HealthStatus.HEALTHY,
                    message="System resources are healthy",
                    details=f"CPU: {cpu_percent:.1f}%, Memory: {memory.percent:.1f}%, Disk: {disk.percent:.1f}%",
                    check_duration_ms=duration_ms
                )
            else:
                return HealthResult(
                    name="System Resources",
                    category=HealthCategory.PERFORMANCE,
                    status=HealthStatus.WARNING,
                    message="System resource issues detected",
                    details="; ".join(issues),
                    fix_suggestion="Check system load and free up resources if needed",
                    check_duration_ms=duration_ms,
                    severity=2
                )
                
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="System Resources",
                category=HealthCategory.PERFORMANCE,
                status=HealthStatus.WARNING,
                message="Resource check failed",
                details=str(e),
                fix_suggestion="Check psutil installation and system access",
                check_duration_ms=duration_ms,
                severity=2
            )
    
    def _check_io_performance(self) -> HealthResult:
        """Check I/O performance."""
        start_time = time.time()
        
        try:
            # Test write/read performance on temp directory
            test_file = os.path.join(self.settings.paths.temp_dir, ".plexsync_io_test")
            os.makedirs(self.settings.paths.temp_dir, exist_ok=True)
            
            # Write test (1MB)
            test_data = b"x" * (1024 * 1024)  # 1MB
            
            write_start = time.time()
            with open(test_file, 'wb') as f:
                f.write(test_data)
                f.flush()
                os.fsync(f.fileno())
            write_duration = time.time() - write_start
            
            # Read test
            read_start = time.time()
            with open(test_file, 'rb') as f:
                read_data = f.read()
            read_duration = time.time() - read_start
            
            # Cleanup
            os.remove(test_file)
            
            # Calculate performance metrics
            write_speed_mb_s = 1.0 / write_duration  # MB/s
            read_speed_mb_s = 1.0 / read_duration    # MB/s
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Evaluate performance (basic thresholds)
            if write_speed_mb_s > 10 and read_speed_mb_s > 20:
                status = HealthStatus.HEALTHY
                message = "I/O performance is good"
                severity = 0
                fix_suggestion = None
            elif write_speed_mb_s > 5 and read_speed_mb_s > 10:
                status = HealthStatus.WARNING
                message = "I/O performance is moderate"
                severity = 1
                fix_suggestion = "Consider using faster storage for better performance"
            else:
                status = HealthStatus.WARNING
                message = "I/O performance is slow"
                severity = 2
                fix_suggestion = "Check disk performance and consider faster storage"
            
            return HealthResult(
                name="I/O Performance",
                category=HealthCategory.PERFORMANCE,
                status=status,
                message=message,
                details=f"Write: {write_speed_mb_s:.1f} MB/s, Read: {read_speed_mb_s:.1f} MB/s",
                fix_suggestion=fix_suggestion,
                check_duration_ms=duration_ms,
                severity=severity
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="I/O Performance",
                category=HealthCategory.PERFORMANCE,
                status=HealthStatus.WARNING,
                message="I/O performance test failed",
                details=str(e),
                fix_suggestion="Check filesystem access and permissions",
                check_duration_ms=duration_ms,
                severity=2
            )
    
    def _check_network_performance(self) -> HealthResult:
        """Check network performance."""
        start_time = time.time()
        
        try:
            # Simple latency test to a reliable host
            latency_start = time.time()
            sock = socket.create_connection(("8.8.8.8", 53), timeout=5)
            latency = (time.time() - latency_start) * 1000  # ms
            sock.close()
            
            duration_ms = (time.time() - start_time) * 1000
            
            # Evaluate network latency
            if latency < 50:
                status = HealthStatus.HEALTHY
                message = "Network performance is excellent"
                severity = 0
                fix_suggestion = None
            elif latency < 100:
                status = HealthStatus.HEALTHY
                message = "Network performance is good"
                severity = 0
                fix_suggestion = None
            elif latency < 200:
                status = HealthStatus.WARNING
                message = "Network performance is moderate"
                severity = 1
                fix_suggestion = "Check network configuration for optimal performance"
            else:
                status = HealthStatus.WARNING
                message = "Network performance is slow"
                severity = 2
                fix_suggestion = "Check network connection and configuration"
            
            return HealthResult(
                name="Network Performance",
                category=HealthCategory.PERFORMANCE,
                status=status,
                message=message,
                details=f"Latency: {latency:.1f}ms",
                fix_suggestion=fix_suggestion,
                check_duration_ms=duration_ms,
                severity=severity
            )
            
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            return HealthResult(
                name="Network Performance",
                category=HealthCategory.PERFORMANCE,
                status=HealthStatus.WARNING,
                message="Network performance test failed",
                details=str(e),
                fix_suggestion="Check network connectivity",
                check_duration_ms=duration_ms,
                severity=2
            )


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get the global health checker instance."""
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker