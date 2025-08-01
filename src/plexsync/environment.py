"""
Environment validation and system readiness checks for PlexSync.

This module validates the system environment, checks dependencies,
and ensures all requirements are met for reliable operation.
"""

import os
import sys
import subprocess
import shutil
import socket
import logging
import platform
import pwd
import grp
import stat
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import tempfile
import time


logger = logging.getLogger(__name__)


class CheckStatus(Enum):
    """Status of environment checks."""
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class EnvironmentCheck:
    """Individual environment check result."""
    name: str
    status: CheckStatus
    message: str
    details: Optional[str] = None
    fix_suggestion: Optional[str] = None
    required: bool = True


@dataclass
class EnvironmentReport:
    """Complete environment validation report."""
    checks: List[EnvironmentCheck] = field(default_factory=list)
    passed: int = 0
    warned: int = 0
    failed: int = 0
    skipped: int = 0
    
    @property
    def is_ready(self) -> bool:
        """Check if environment is ready for operation."""
        return self.failed == 0
    
    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings."""
        return self.warned > 0
    
    def add_check(self, check: EnvironmentCheck):
        """Add a check result to the report."""
        self.checks.append(check)
        
        if check.status == CheckStatus.PASS:
            self.passed += 1
        elif check.status == CheckStatus.WARN:
            self.warned += 1
        elif check.status == CheckStatus.FAIL:
            self.failed += 1
        elif check.status == CheckStatus.SKIP:
            self.skipped += 1


class EnvironmentValidator:
    """Validates system environment for PlexSync operation."""
    
    def __init__(self):
        self.report = EnvironmentReport()
        self.headless_mode = self._detect_headless_mode()
    
    def _detect_headless_mode(self) -> bool:
        """Detect if running in headless mode."""
        # Check for SSH session
        if os.environ.get('SSH_CLIENT') or os.environ.get('SSH_TTY'):
            return True
        
        # Check for no display
        if not os.environ.get('DISPLAY'):
            return True
        
        # Check for non-interactive shells
        if not sys.stdin.isatty():
            return True
            
        return False
    
    def run_all_checks(self) -> EnvironmentReport:
        """Run all environment validation checks."""
        logger.info("Starting environment validation...")
        
        # System checks
        self._check_python_version()
        self._check_platform_support()
        self._check_permissions()
        self._check_available_space()
        
        # Dependency checks
        self._check_rsync()
        self._check_python_dependencies()
        
        # Network checks
        self._check_network_connectivity()
        
        # File system checks
        self._check_media_paths()
        self._check_destination_paths()
        
        # Performance checks
        self._check_system_resources()
        
        # Security checks
        self._check_security_settings()
        
        # Headless mode checks
        if self.headless_mode:
            self._check_headless_compatibility()
        
        logger.info(f"Environment validation complete: {self.report.passed} passed, "
                   f"{self.report.warned} warned, {self.report.failed} failed")
        
        return self.report
    
    def _check_python_version(self):
        """Check Python version compatibility."""
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"
        
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            self.report.add_check(EnvironmentCheck(
                name="Python Version",
                status=CheckStatus.FAIL,
                message=f"Python {version_str} is not supported",
                details="PlexSync requires Python 3.8 or higher",
                fix_suggestion="Upgrade to Python 3.8+ or use a different environment"
            ))
        elif version.minor < 10:
            self.report.add_check(EnvironmentCheck(
                name="Python Version",
                status=CheckStatus.WARN,
                message=f"Python {version_str} is supported but not optimal",
                details="Python 3.10+ is recommended for best performance",
                fix_suggestion="Consider upgrading to Python 3.10+ for optimal performance"
            ))
        else:
            self.report.add_check(EnvironmentCheck(
                name="Python Version",
                status=CheckStatus.PASS,
                message=f"Python {version_str} is supported",
                details="Version is compatible and recommended"
            ))
    
    def _check_platform_support(self):
        """Check platform compatibility."""
        system = platform.system()
        release = platform.release()
        
        if system == "Linux":
            self.report.add_check(EnvironmentCheck(
                name="Platform Support",
                status=CheckStatus.PASS,
                message=f"Linux {release} is fully supported",
                details="All features available"
            ))
        elif system == "Darwin":  # macOS
            version = platform.mac_ver()[0]
            if version and float(version.split('.')[0]) >= 12:
                self.report.add_check(EnvironmentCheck(
                    name="Platform Support",
                    status=CheckStatus.PASS,
                    message=f"macOS {version} is fully supported",
                    details="All features available"
                ))
            else:
                self.report.add_check(EnvironmentCheck(
                    name="Platform Support",
                    status=CheckStatus.WARN,
                    message=f"macOS {version} may have limited support",
                    details="macOS 12+ is recommended for full compatibility"
                ))
        elif system == "Windows":
            self.report.add_check(EnvironmentCheck(
                name="Platform Support",
                status=CheckStatus.WARN,
                message=f"Windows {release} has limited support",
                details="Some features may not work correctly on Windows",
                fix_suggestion="Consider using WSL2 for better compatibility"
            ))
        else:
            self.report.add_check(EnvironmentCheck(
                name="Platform Support",
                status=CheckStatus.FAIL,
                message=f"Platform {system} is not supported",
                details="PlexSync supports Linux, macOS, and Windows",
                fix_suggestion="Use a supported platform"
            ))
    
    def _check_permissions(self):
        """Check file system permissions."""
        try:
            # Check if running as root (not recommended)
            if os.geteuid() == 0:
                self.report.add_check(EnvironmentCheck(
                    name="User Permissions",
                    status=CheckStatus.WARN,
                    message="Running as root is not recommended",
                    details="Running as root can be a security risk",
                    fix_suggestion="Run as a regular user with appropriate permissions"
                ))
            else:
                user = pwd.getpwuid(os.getuid()).pw_name
                self.report.add_check(EnvironmentCheck(
                    name="User Permissions",
                    status=CheckStatus.PASS,
                    message=f"Running as user '{user}'",
                    details="Non-root execution is recommended"
                ))
        except Exception as e:
            self.report.add_check(EnvironmentCheck(
                name="User Permissions",
                status=CheckStatus.WARN,
                message="Could not check user permissions",
                details=str(e)
            ))
    
    def _check_available_space(self):
        """Check available disk space."""
        try:
            # Check home directory space
            home_usage = shutil.disk_usage(os.path.expanduser("~"))
            home_free_gb = home_usage.free / (1024**3)
            
            if home_free_gb < 1:
                self.report.add_check(EnvironmentCheck(
                    name="Disk Space",
                    status=CheckStatus.FAIL,
                    message=f"Insufficient disk space: {home_free_gb:.1f} GB free",
                    details="At least 1 GB free space required",
                    fix_suggestion="Free up disk space before syncing"
                ))
            elif home_free_gb < 10:
                self.report.add_check(EnvironmentCheck(
                    name="Disk Space",
                    status=CheckStatus.WARN,
                    message=f"Low disk space: {home_free_gb:.1f} GB free",
                    details="Consider freeing up space for large transfers",
                    fix_suggestion="Monitor disk usage during transfers"
                ))
            else:
                self.report.add_check(EnvironmentCheck(
                    name="Disk Space",
                    status=CheckStatus.PASS,
                    message=f"Sufficient disk space: {home_free_gb:.1f} GB free",
                    details="Adequate space for typical operations"
                ))
        except Exception as e:
            self.report.add_check(EnvironmentCheck(
                name="Disk Space",
                status=CheckStatus.WARN,
                message="Could not check disk space",
                details=str(e)
            ))
    
    def _check_rsync(self):
        """Check rsync availability and version."""
        try:
            # Check if rsync is available
            rsync_path = shutil.which('rsync')
            if not rsync_path:
                self.report.add_check(EnvironmentCheck(
                    name="Rsync Availability",
                    status=CheckStatus.FAIL,
                    message="rsync not found in PATH",
                    details="rsync is required for file synchronization",
                    fix_suggestion="Install rsync: sudo apt install rsync (Ubuntu/Debian) or sudo yum install rsync (CentOS/RHEL)"
                ))
                return
            
            # Check rsync version
            result = subprocess.run([rsync_path, '--version'], 
                                  capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                self.report.add_check(EnvironmentCheck(
                    name="Rsync Version",
                    status=CheckStatus.FAIL,
                    message="Could not determine rsync version",
                    details=result.stderr,
                    fix_suggestion="Reinstall rsync"
                ))
                return
            
            # Parse version
            version_line = result.stdout.split('\n')[0]
            if 'version' in version_line:
                version = version_line.split('version')[1].split()[0]
                
                # Check minimum version (3.1.0)
                version_parts = version.split('.')
                if len(version_parts) >= 2:
                    major, minor = int(version_parts[0]), int(version_parts[1])
                    
                    if major < 3 or (major == 3 and minor < 1):
                        self.report.add_check(EnvironmentCheck(
                            name="Rsync Version",
                            status=CheckStatus.FAIL,
                            message=f"rsync {version} is too old",
                            details="rsync 3.1.0 or newer is required",
                            fix_suggestion="Update rsync to a newer version"
                        ))
                    elif major == 3 and minor < 2:
                        self.report.add_check(EnvironmentCheck(
                            name="Rsync Version",
                            status=CheckStatus.WARN,
                            message=f"rsync {version} is functional but not optimal",
                            details="rsync 3.2.0+ is recommended for best performance",
                            fix_suggestion="Consider updating to rsync 3.2.0+"
                        ))
                    else:
                        self.report.add_check(EnvironmentCheck(
                            name="Rsync Version",
                            status=CheckStatus.PASS,
                            message=f"rsync {version} is supported",
                            details="Version supports all required features"
                        ))
                else:
                    self.report.add_check(EnvironmentCheck(
                        name="Rsync Version",
                        status=CheckStatus.WARN,
                        message=f"Could not parse rsync version: {version}",
                        details="Version parsing failed but rsync is available"
                    ))
            else:
                self.report.add_check(EnvironmentCheck(
                    name="Rsync Version",
                    status=CheckStatus.WARN,
                    message="Could not parse rsync version output",
                    details="rsync is available but version is unclear"
                ))
                
        except subprocess.TimeoutExpired:
            self.report.add_check(EnvironmentCheck(
                name="Rsync Availability",
                status=CheckStatus.FAIL,
                message="rsync command timed out",
                details="rsync may be unresponsive",
                fix_suggestion="Check rsync installation"
            ))
        except Exception as e:
            self.report.add_check(EnvironmentCheck(
                name="Rsync Availability",
                status=CheckStatus.FAIL,
                message="Error checking rsync",
                details=str(e),
                fix_suggestion="Install or reinstall rsync"
            ))
    
    def _check_python_dependencies(self):
        """Check Python package dependencies."""
        required_packages = [
            ('psutil', 'System monitoring'),
            ('rich', 'Terminal formatting'),
            ('click', 'Command-line interface'),
            ('pydantic', 'Data validation'),
            ('keyring', 'Credential storage'),
            ('pyyaml', 'Configuration parsing'),
            ('cryptography', 'Security functions')
        ]
        
        missing_packages = []
        
        for package, description in required_packages:
            try:
                __import__(package)
            except ImportError:
                missing_packages.append(f"{package} ({description})")
        
        if missing_packages:
            self.report.add_check(EnvironmentCheck(
                name="Python Dependencies",
                status=CheckStatus.FAIL,
                message=f"Missing required packages: {', '.join(missing_packages)}",
                details="Some dependencies are not installed",
                fix_suggestion="Install dependencies: pip install -r requirements.txt"
            ))
        else:
            self.report.add_check(EnvironmentCheck(
                name="Python Dependencies",
                status=CheckStatus.PASS,
                message="All required Python packages are available",
                details="Dependencies are satisfied"
            ))
    
    def _check_network_connectivity(self):
        """Check basic network connectivity."""
        try:
            # Test basic connectivity
            socket.create_connection(("8.8.8.8", 53), timeout=5)
            self.report.add_check(EnvironmentCheck(
                name="Network Connectivity",
                status=CheckStatus.PASS,
                message="Basic network connectivity is available",
                details="Can reach external hosts"
            ))
        except socket.timeout:
            self.report.add_check(EnvironmentCheck(
                name="Network Connectivity",
                status=CheckStatus.WARN,
                message="Network connectivity test timed out",
                details="May indicate slow or unreliable network",
                fix_suggestion="Check network configuration"
            ))
        except Exception as e:
            self.report.add_check(EnvironmentCheck(
                name="Network Connectivity",
                status=CheckStatus.FAIL,
                message="No network connectivity",
                details=str(e),
                fix_suggestion="Check network configuration and connection"
            ))
    
    def _check_media_paths(self):
        """Check configured media source paths."""
        default_paths = [
            "/mnt/media/Movies",
            "/mnt/media/Movies2", 
            "/mnt/media/TV",
            "/mnt/media/TV2"
        ]
        
        accessible_paths = []
        inaccessible_paths = []
        
        for path in default_paths:
            if os.path.exists(path) and os.access(path, os.R_OK):
                accessible_paths.append(path)
            else:
                inaccessible_paths.append(path)
        
        if not accessible_paths:
            self.report.add_check(EnvironmentCheck(
                name="Media Source Paths",
                status=CheckStatus.FAIL,
                message="No media source paths are accessible",
                details=f"Checked paths: {', '.join(default_paths)}",
                fix_suggestion="Mount media sources or configure different paths"
            ))
        elif inaccessible_paths:
            self.report.add_check(EnvironmentCheck(
                name="Media Source Paths",
                status=CheckStatus.WARN,
                message=f"Some media paths are inaccessible: {', '.join(inaccessible_paths)}",
                details=f"Accessible paths: {', '.join(accessible_paths)}",
                fix_suggestion="Mount missing media sources or update configuration"
            ))
        else:
            self.report.add_check(EnvironmentCheck(
                name="Media Source Paths",
                status=CheckStatus.PASS,
                message="All default media source paths are accessible",
                details=f"Accessible paths: {', '.join(accessible_paths)}"
            ))
    
    def _check_destination_paths(self):
        """Check destination directory access."""
        try:
            home_dir = os.path.expanduser("~")
            media_dir = os.path.join(home_dir, "Media")
            
            # Check if we can create the destination directory
            if not os.path.exists(media_dir):
                try:
                    os.makedirs(media_dir, exist_ok=True)
                    self.report.add_check(EnvironmentCheck(
                        name="Destination Paths",
                        status=CheckStatus.PASS,
                        message="Can create destination directories",
                        details=f"Test directory: {media_dir}"
                    ))
                except PermissionError:
                    self.report.add_check(EnvironmentCheck(
                        name="Destination Paths",
                        status=CheckStatus.FAIL,
                        message="Cannot create destination directories",
                        details=f"Permission denied: {media_dir}",
                        fix_suggestion="Check directory permissions"
                    ))
            else:
                if os.access(media_dir, os.W_OK):
                    self.report.add_check(EnvironmentCheck(
                        name="Destination Paths",
                        status=CheckStatus.PASS,
                        message="Destination directory is writable",
                        details=f"Directory: {media_dir}"
                    ))
                else:
                    self.report.add_check(EnvironmentCheck(
                        name="Destination Paths",
                        status=CheckStatus.FAIL,
                        message="Destination directory is not writable",
                        details=f"Directory: {media_dir}",
                        fix_suggestion="Fix directory permissions: chmod 755 ~/Media"
                    ))
        except Exception as e:
            self.report.add_check(EnvironmentCheck(
                name="Destination Paths",
                status=CheckStatus.FAIL,
                message="Error checking destination paths",
                details=str(e),
                fix_suggestion="Check filesystem and permissions"
            ))
    
    def _check_system_resources(self):
        """Check system resource availability."""
        try:
            import psutil
            
            # Check memory
            memory = psutil.virtual_memory()
            memory_gb = memory.total / (1024**3)
            
            if memory_gb < 1:
                self.report.add_check(EnvironmentCheck(
                    name="System Memory",
                    status=CheckStatus.WARN,
                    message=f"Low system memory: {memory_gb:.1f} GB",
                    details="May impact performance with large files",
                    fix_suggestion="Consider upgrading RAM or reducing concurrent operations"
                ))
            else:
                self.report.add_check(EnvironmentCheck(
                    name="System Memory",
                    status=CheckStatus.PASS,
                    message=f"Adequate system memory: {memory_gb:.1f} GB",
                    details="Sufficient for typical operations"
                ))
            
            # Check CPU
            cpu_count = psutil.cpu_count()
            if cpu_count < 2:
                self.report.add_check(EnvironmentCheck(
                    name="CPU Resources",
                    status=CheckStatus.WARN,
                    message=f"Limited CPU cores: {cpu_count}",
                    details="May impact performance with large transfers",
                    fix_suggestion="Consider reducing concurrent operations"
                ))
            else:
                self.report.add_check(EnvironmentCheck(
                    name="CPU Resources",
                    status=CheckStatus.PASS,
                    message=f"Adequate CPU cores: {cpu_count}",
                    details="Sufficient for typical operations"
                ))
                
        except ImportError:
            self.report.add_check(EnvironmentCheck(
                name="System Resources",
                status=CheckStatus.SKIP,
                message="psutil not available for resource checking",
                details="Install psutil for resource monitoring"
            ))
    
    def _check_security_settings(self):
        """Check security-related settings."""
        try:
            # Check SSH key availability
            ssh_dir = os.path.expanduser("~/.ssh")
            if os.path.exists(ssh_dir):
                key_files = [f for f in os.listdir(ssh_dir) 
                           if f.startswith('id_') and not f.endswith('.pub')]
                
                if key_files:
                    self.report.add_check(EnvironmentCheck(
                        name="SSH Keys",
                        status=CheckStatus.PASS,
                        message="SSH keys are available",
                        details=f"Found keys: {', '.join(key_files)}"
                    ))
                else:
                    self.report.add_check(EnvironmentCheck(
                        name="SSH Keys",
                        status=CheckStatus.WARN,
                        message="No SSH keys found",
                        details="SSH keys are recommended for secure connections",
                        fix_suggestion="Generate SSH keys: ssh-keygen -t rsa -b 4096"
                    ))
            else:
                self.report.add_check(EnvironmentCheck(
                    name="SSH Keys",
                    status=CheckStatus.WARN,
                    message="SSH directory not found",
                    details="SSH keys are recommended for secure connections",
                    fix_suggestion="Create SSH directory and keys: mkdir ~/.ssh && ssh-keygen -t rsa -b 4096"
                ))
                
        except Exception as e:
            self.report.add_check(EnvironmentCheck(
                name="SSH Keys",
                status=CheckStatus.SKIP,
                message="Could not check SSH keys",
                details=str(e)
            ))
    
    def _check_headless_compatibility(self):
        """Check headless mode compatibility."""
        self.report.add_check(EnvironmentCheck(
            name="Headless Mode",
            status=CheckStatus.PASS,
            message="Headless mode detected and supported",
            details="PlexSync will use plain text output and non-interactive mode",
            required=False
        ))
        
        # Check for tmux/screen
        if os.environ.get('TMUX') or os.environ.get('STY'):
            self.report.add_check(EnvironmentCheck(
                name="Terminal Multiplexer",
                status=CheckStatus.PASS,
                message="Running in terminal multiplexer",
                details="tmux/screen detected for session persistence",
                required=False
            ))
    
    def get_fix_suggestions(self) -> List[str]:
        """Get list of fix suggestions for failed checks."""
        suggestions = []
        
        for check in self.report.checks:
            if check.status == CheckStatus.FAIL and check.fix_suggestion:
                suggestions.append(f"{check.name}: {check.fix_suggestion}")
        
        return suggestions
    
    def is_environment_ready(self) -> bool:
        """Check if environment is ready for operation."""
        return self.report.is_ready


def validate_environment() -> EnvironmentReport:
    """Validate the complete environment and return report."""
    validator = EnvironmentValidator()
    return validator.run_all_checks() 