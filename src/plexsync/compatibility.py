"""
Compatibility matrix and environment detection for PlexSync.

This module defines the supported platforms, Python versions, and terminal
environments, along with runtime detection capabilities.
"""

import os
import sys
import platform
import shutil
import subprocess
from typing import Dict, List, Optional, Tuple, NamedTuple
from dataclasses import dataclass
from enum import Enum


class PlatformSupport(Enum):
    """Platform support levels."""
    FULL = "full"
    LIMITED = "limited"
    UNSUPPORTED = "unsupported"


class TerminalCapability(Enum):
    """Terminal capability levels."""
    TRUECOLOR = "truecolor"
    BASIC_COLOR = "basic_color"
    MONOCHROME = "monochrome"
    HEADLESS = "headless"


@dataclass
class PlatformInfo:
    """Information about the current platform."""
    os_name: str
    os_version: str
    python_version: str
    terminal_capability: TerminalCapability
    rsync_version: Optional[str]
    support_level: PlatformSupport


class CompatibilityMatrix:
    """Compatibility matrix for supported platforms and configurations."""
    
    # Supported Python versions
    SUPPORTED_PYTHON_VERSIONS = {
        "3.8": {"min_patch": 0, "status": "supported"},
        "3.9": {"min_patch": 0, "status": "supported"},
        "3.10": {"min_patch": 0, "status": "recommended"},
        "3.11": {"min_patch": 0, "status": "recommended"},
        "3.12": {"min_patch": 0, "status": "recommended"},
        "3.13": {"min_patch": 0, "status": "recommended"},
    }
    
    # Operating system support matrix
    OS_SUPPORT_MATRIX = {
        "Linux": {
            "ubuntu": {"min_version": "20.04", "support": PlatformSupport.FULL},
            "centos": {"min_version": "8", "support": PlatformSupport.FULL},
            "arch": {"min_version": "rolling", "support": PlatformSupport.FULL},
            "debian": {"min_version": "11", "support": PlatformSupport.FULL},
            "fedora": {"min_version": "35", "support": PlatformSupport.FULL},
            "default": {"support": PlatformSupport.LIMITED},
        },
        "Darwin": {  # macOS
            "min_version": "12.0",
            "support": PlatformSupport.FULL,
        },
        "Windows": {
            "min_version": "10",
            "support": PlatformSupport.LIMITED,
            "limitations": ["Limited metadata support", "No extended attributes"],
        },
    }
    
    # Rsync version requirements
    RSYNC_REQUIREMENTS = {
        "min_version": "3.1.0",
        "recommended_version": "3.2.0",
        "features": {
            "3.1.0": ["basic sync", "partial transfers"],
            "3.2.0": ["progress reporting", "better error handling"],
            "3.2.3": ["improved performance", "better compression"],
        },
    }
    
    # Terminal environment capabilities
    TERMINAL_DETECTION = {
        "truecolor_terms": ["xterm-256color", "screen-256color", "tmux-256color"],
        "color_terms": ["xterm", "screen", "tmux"],
        "env_indicators": {
            "COLORTERM": ["truecolor", "24bit"],
            "TERM_PROGRAM": ["iTerm.app", "vscode"],
        },
    }

    @classmethod
    def detect_platform_info(cls) -> PlatformInfo:
        """Detect current platform capabilities and support level."""
        os_name = platform.system()
        os_version = platform.release()
        python_version = f"{sys.version_info.major}.{sys.version_info.minor}"
        
        # Detect terminal capabilities
        terminal_capability = cls._detect_terminal_capability()
        
        # Get rsync version
        rsync_version = cls._get_rsync_version()
        
        # Determine support level
        support_level = cls._determine_support_level(
            os_name, os_version, python_version, rsync_version
        )
        
        return PlatformInfo(
            os_name=os_name,
            os_version=os_version,
            python_version=python_version,
            terminal_capability=terminal_capability,
            rsync_version=rsync_version,
            support_level=support_level,
        )

    @classmethod
    def _detect_terminal_capability(cls) -> TerminalCapability:
        """Detect terminal color and UI capabilities."""
        # Check if we're in a headless environment
        if not sys.stdout.isatty() or os.getenv("CI"):
            return TerminalCapability.HEADLESS
        
        # Check for truecolor support
        term = os.getenv("TERM", "")
        colorterm = os.getenv("COLORTERM", "")
        term_program = os.getenv("TERM_PROGRAM", "")
        
        if (
            colorterm in cls.TERMINAL_DETECTION["env_indicators"]["COLORTERM"]
            or term_program in cls.TERMINAL_DETECTION["env_indicators"]["TERM_PROGRAM"]
            or term in cls.TERMINAL_DETECTION["truecolor_terms"]
        ):
            return TerminalCapability.TRUECOLOR
        
        # Check for basic color support
        if term in cls.TERMINAL_DETECTION["color_terms"] or "color" in term:
            return TerminalCapability.BASIC_COLOR
        
        return TerminalCapability.MONOCHROME

    @classmethod
    def _get_rsync_version(cls) -> Optional[str]:
        """Get rsync version if available."""
        try:
            result = subprocess.run(
                ["rsync", "--version"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                # Parse version from output (e.g., "rsync version 3.2.3")
                lines = result.stdout.strip().split("\n")
                for line in lines:
                    if "version" in line.lower():
                        parts = line.split()
                        for part in parts:
                            if part.replace(".", "").isdigit():
                                return part
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass
        
        return None

    @classmethod
    def _determine_support_level(
        cls, os_name: str, os_version: str, python_version: str, rsync_version: Optional[str]
    ) -> PlatformSupport:
        """Determine the support level for the current platform."""
        # Check Python version support
        if python_version not in cls.SUPPORTED_PYTHON_VERSIONS:
            return PlatformSupport.UNSUPPORTED
        
        # Check OS support
        if os_name not in cls.OS_SUPPORT_MATRIX:
            return PlatformSupport.UNSUPPORTED
        
        os_config = cls.OS_SUPPORT_MATRIX[os_name]
        
        if os_name == "Windows":
            # Windows has limited support
            return PlatformSupport.LIMITED
        elif os_name == "Darwin":
            # macOS version check would go here
            return PlatformSupport.FULL
        elif os_name == "Linux":
            # Linux - check specific distributions
            os_version_lower = os_version.lower()
            
            # Check for known distributions in the version string
            for distro, config in os_config.items():
                if distro == "default":
                    continue
                if distro in os_version_lower:
                    return config.get("support", PlatformSupport.FULL)
            
            # Check for Arch Linux patterns
            if "arch" in os_version_lower or "archlinux" in os_version_lower:
                return PlatformSupport.FULL
            
            # For other Linux distributions, default to FULL support
            # Most modern Linux distributions should work fine
            return PlatformSupport.FULL
        else:
            # Other platforms - default to limited
            return os_config.get("default", {}).get("support", PlatformSupport.LIMITED)

    @classmethod
    def get_compatibility_report(cls) -> Dict:
        """Generate a comprehensive compatibility report."""
        platform_info = cls.detect_platform_info()
        
        report = {
            "platform": {
                "os": platform_info.os_name,
                "version": platform_info.os_version,
                "support_level": platform_info.support_level.value,
            },
            "python": {
                "version": platform_info.python_version,
                "supported": platform_info.python_version in cls.SUPPORTED_PYTHON_VERSIONS,
                "status": cls.SUPPORTED_PYTHON_VERSIONS.get(
                    platform_info.python_version, {}
                ).get("status", "unsupported"),
            },
            "terminal": {
                "capability": platform_info.terminal_capability.value,
                "tty": sys.stdout.isatty(),
                "columns": shutil.get_terminal_size().columns,
                "lines": shutil.get_terminal_size().lines,
            },
            "rsync": {
                "available": platform_info.rsync_version is not None,
                "version": platform_info.rsync_version,
                "meets_minimum": cls._version_meets_minimum(
                    platform_info.rsync_version, cls.RSYNC_REQUIREMENTS["min_version"]
                ),
                "recommended": cls._version_meets_minimum(
                    platform_info.rsync_version, cls.RSYNC_REQUIREMENTS["recommended_version"]
                ),
            },
        }
        
        # Add warnings and recommendations
        warnings = []
        recommendations = []
        
        if platform_info.support_level == PlatformSupport.UNSUPPORTED:
            warnings.append("Platform is not supported")
        elif platform_info.support_level == PlatformSupport.LIMITED:
            warnings.append("Platform has limited support")
        
        if not platform_info.rsync_version:
            warnings.append("rsync not found - some features may not work")
            recommendations.append("Install rsync for full functionality")
        
        if platform_info.terminal_capability == TerminalCapability.MONOCHROME:
            recommendations.append("Consider using a terminal with color support")
        
        report["warnings"] = warnings
        report["recommendations"] = recommendations
        
        return report

    @staticmethod
    def _version_meets_minimum(current: Optional[str], minimum: str) -> bool:
        """Check if current version meets minimum requirement."""
        if not current:
            return False
        
        try:
            current_parts = [int(x) for x in current.split(".")]
            minimum_parts = [int(x) for x in minimum.split(".")]
            
            # Pad shorter version with zeros
            max_len = max(len(current_parts), len(minimum_parts))
            current_parts.extend([0] * (max_len - len(current_parts)))
            minimum_parts.extend([0] * (max_len - len(minimum_parts)))
            
            return current_parts >= minimum_parts
        except (ValueError, AttributeError):
            return False

    @classmethod
    def validate_environment(cls) -> Tuple[bool, List[str]]:
        """Validate the current environment for PlexSync compatibility."""
        report = cls.get_compatibility_report()
        errors = []
        
        # Critical checks - only block execution for truly unsupported environments
        if not report["python"]["supported"]:
            errors.append(
                f"Python {report['python']['version']} is not supported. "
                f"Minimum: {min(cls.SUPPORTED_PYTHON_VERSIONS.keys())}"
            )
        
        if report["platform"]["support_level"] == "unsupported":
            errors.append(f"Platform {report['platform']['os']} is not supported")
        
        # Note: "limited" support is allowed but may show warnings
        # Only "unsupported" platforms should prevent execution
        
        return len(errors) == 0, errors 