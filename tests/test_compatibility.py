"""
Tests for the compatibility matrix functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
import sys
import os

from plexsync.compatibility import (
    CompatibilityMatrix,
    PlatformSupport,
    TerminalCapability,
    PlatformInfo,
)


class TestCompatibilityMatrix:
    """Test the CompatibilityMatrix class."""
    
    def test_supported_python_versions(self):
        """Test Python version support detection."""
        # Test supported versions
        assert "3.8" in CompatibilityMatrix.SUPPORTED_PYTHON_VERSIONS
        assert "3.9" in CompatibilityMatrix.SUPPORTED_PYTHON_VERSIONS
        assert "3.10" in CompatibilityMatrix.SUPPORTED_PYTHON_VERSIONS
        assert "3.11" in CompatibilityMatrix.SUPPORTED_PYTHON_VERSIONS
        assert "3.12" in CompatibilityMatrix.SUPPORTED_PYTHON_VERSIONS
        
        # Test unsupported versions
        assert "3.7" not in CompatibilityMatrix.SUPPORTED_PYTHON_VERSIONS
        assert "2.7" not in CompatibilityMatrix.SUPPORTED_PYTHON_VERSIONS
    
    def test_os_support_matrix(self):
        """Test operating system support matrix."""
        assert "Linux" in CompatibilityMatrix.OS_SUPPORT_MATRIX
        assert "Darwin" in CompatibilityMatrix.OS_SUPPORT_MATRIX
        assert "Windows" in CompatibilityMatrix.OS_SUPPORT_MATRIX
        
        # Test Linux distributions
        linux_config = CompatibilityMatrix.OS_SUPPORT_MATRIX["Linux"]
        assert "ubuntu" in linux_config
        assert "centos" in linux_config
        assert "arch" in linux_config
        assert "default" in linux_config
    
    def test_rsync_requirements(self):
        """Test rsync version requirements."""
        requirements = CompatibilityMatrix.RSYNC_REQUIREMENTS
        assert "min_version" in requirements
        assert "recommended_version" in requirements
        assert "features" in requirements
        
        # Test version requirements
        assert requirements["min_version"] == "3.1.0"
        assert requirements["recommended_version"] == "3.2.0"
    
    @patch('plexsync.compatibility.platform.system')
    @patch('plexsync.compatibility.platform.release')
    @patch('plexsync.compatibility.sys.version_info')
    def test_detect_platform_info(self, mock_version_info, mock_release, mock_system):
        """Test platform info detection."""
        # Mock system information
        mock_system.return_value = "Linux"
        mock_release.return_value = "5.15.0"
        mock_version_info.major = 3
        mock_version_info.minor = 10
        
        with patch.object(CompatibilityMatrix, '_detect_terminal_capability') as mock_terminal:
            mock_terminal.return_value = TerminalCapability.TRUECOLOR
            
            with patch.object(CompatibilityMatrix, '_get_rsync_version') as mock_rsync:
                mock_rsync.return_value = "3.2.3"
                
                platform_info = CompatibilityMatrix.detect_platform_info()
                
                assert platform_info.os_name == "Linux"
                assert platform_info.os_version == "5.15.0"
                assert platform_info.python_version == "3.10"
                assert platform_info.terminal_capability == TerminalCapability.TRUECOLOR
                assert platform_info.rsync_version == "3.2.3"
    
    @patch('plexsync.compatibility.sys.stdout.isatty')
    @patch('plexsync.compatibility.os.getenv')
    def test_detect_terminal_capability(self, mock_getenv, mock_isatty):
        """Test terminal capability detection."""
        # Test headless environment
        mock_isatty.return_value = False
        capability = CompatibilityMatrix._detect_terminal_capability()
        assert capability == TerminalCapability.HEADLESS
        
        # Test truecolor support
        mock_isatty.return_value = True
        mock_getenv.side_effect = lambda key, default="": {
            "COLORTERM": "truecolor",
            "TERM": "xterm-256color",
            "TERM_PROGRAM": "",
            "CI": "",
        }.get(key, default)
        
        capability = CompatibilityMatrix._detect_terminal_capability()
        assert capability == TerminalCapability.TRUECOLOR
        
        # Test basic color support
        mock_getenv.side_effect = lambda key, default="": {
            "COLORTERM": "",
            "TERM": "xterm",
            "TERM_PROGRAM": "",
            "CI": "",
        }.get(key, default)
        
        capability = CompatibilityMatrix._detect_terminal_capability()
        assert capability == TerminalCapability.BASIC_COLOR
    
    @patch('plexsync.compatibility.subprocess.run')
    def test_get_rsync_version(self, mock_run):
        """Test rsync version detection."""
        # Test successful version detection
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "rsync version 3.2.3 protocol version 31"
        mock_run.return_value = mock_result
        
        version = CompatibilityMatrix._get_rsync_version()
        assert version == "3.2.3"
        
        # Test rsync not found
        mock_run.side_effect = FileNotFoundError()
        version = CompatibilityMatrix._get_rsync_version()
        assert version is None
        
        # Test rsync command fails
        mock_run.side_effect = None
        mock_result.returncode = 1
        mock_run.return_value = mock_result
        
        version = CompatibilityMatrix._get_rsync_version()
        assert version is None
    
    def test_version_meets_minimum(self):
        """Test version comparison logic."""
        # Test exact match
        assert CompatibilityMatrix._version_meets_minimum("3.2.0", "3.2.0")
        
        # Test higher version
        assert CompatibilityMatrix._version_meets_minimum("3.2.1", "3.2.0")
        assert CompatibilityMatrix._version_meets_minimum("3.3.0", "3.2.0")
        
        # Test lower version
        assert not CompatibilityMatrix._version_meets_minimum("3.1.9", "3.2.0")
        assert not CompatibilityMatrix._version_meets_minimum("2.9.0", "3.2.0")
        
        # Test None version
        assert not CompatibilityMatrix._version_meets_minimum(None, "3.2.0")
        
        # Test invalid version strings
        assert not CompatibilityMatrix._version_meets_minimum("invalid", "3.2.0")
        assert not CompatibilityMatrix._version_meets_minimum("3.2.x", "3.2.0")
    
    def test_determine_support_level(self):
        """Test support level determination."""
        # Test supported Python version with Linux
        support = CompatibilityMatrix._determine_support_level("Linux", "5.15.0", "3.10", "3.2.3")
        assert support == PlatformSupport.LIMITED  # Default for Linux
        
        # Test unsupported Python version
        support = CompatibilityMatrix._determine_support_level("Linux", "5.15.0", "3.7", "3.2.3")
        assert support == PlatformSupport.UNSUPPORTED
        
        # Test Windows
        support = CompatibilityMatrix._determine_support_level("Windows", "10", "3.10", "3.2.3")
        assert support == PlatformSupport.LIMITED
        
        # Test macOS
        support = CompatibilityMatrix._determine_support_level("Darwin", "21.0.0", "3.10", "3.2.3")
        assert support == PlatformSupport.FULL
        
        # Test unsupported OS
        support = CompatibilityMatrix._determine_support_level("FreeBSD", "13.0", "3.10", "3.2.3")
        assert support == PlatformSupport.UNSUPPORTED
    
    def test_get_compatibility_report(self):
        """Test compatibility report generation."""
        with patch.object(CompatibilityMatrix, 'detect_platform_info') as mock_detect:
            mock_platform_info = PlatformInfo(
                os_name="Linux",
                os_version="5.15.0",
                python_version="3.10",
                terminal_capability=TerminalCapability.TRUECOLOR,
                rsync_version="3.2.3",
                support_level=PlatformSupport.FULL,
            )
            mock_detect.return_value = mock_platform_info
            
            report = CompatibilityMatrix.get_compatibility_report()
            
            # Check report structure
            assert "platform" in report
            assert "python" in report
            assert "terminal" in report
            assert "rsync" in report
            assert "warnings" in report
            assert "recommendations" in report
            
            # Check platform info
            assert report["platform"]["os"] == "Linux"
            assert report["platform"]["version"] == "5.15.0"
            assert report["platform"]["support_level"] == "full"
            
            # Check Python info
            assert report["python"]["version"] == "3.10"
            assert report["python"]["supported"] is True
            assert report["python"]["status"] == "recommended"
            
            # Check rsync info
            assert report["rsync"]["available"] is True
            assert report["rsync"]["version"] == "3.2.3"
            assert report["rsync"]["meets_minimum"] is True
            assert report["rsync"]["recommended"] is True
    
    def test_validate_environment(self):
        """Test environment validation."""
        with patch.object(CompatibilityMatrix, 'get_compatibility_report') as mock_report:
            # Test valid environment
            mock_report.return_value = {
                "python": {"supported": True, "version": "3.10"},
                "platform": {"support_level": "full", "os": "Linux"},
                "warnings": [],
                "recommendations": [],
            }
            
            is_valid, errors = CompatibilityMatrix.validate_environment()
            assert is_valid is True
            assert len(errors) == 0
            
            # Test invalid environment - unsupported Python
            mock_report.return_value = {
                "python": {"supported": False, "version": "3.7"},
                "platform": {"support_level": "full", "os": "Linux"},
                "warnings": [],
                "recommendations": [],
            }
            
            is_valid, errors = CompatibilityMatrix.validate_environment()
            assert is_valid is False
            assert len(errors) > 0
            assert "Python 3.7 is not supported" in errors[0]
            
            # Test invalid environment - unsupported platform
            mock_report.return_value = {
                "python": {"supported": True, "version": "3.10"},
                "platform": {"support_level": "unsupported", "os": "FreeBSD"},
                "warnings": [],
                "recommendations": [],
            }
            
            is_valid, errors = CompatibilityMatrix.validate_environment()
            assert is_valid is False
            assert len(errors) > 0
            assert "FreeBSD is not supported" in errors[0]


class TestPlatformInfo:
    """Test the PlatformInfo dataclass."""
    
    def test_platform_info_creation(self):
        """Test PlatformInfo creation."""
        info = PlatformInfo(
            os_name="Linux",
            os_version="5.15.0",
            python_version="3.10",
            terminal_capability=TerminalCapability.TRUECOLOR,
            rsync_version="3.2.3",
            support_level=PlatformSupport.FULL,
        )
        
        assert info.os_name == "Linux"
        assert info.os_version == "5.15.0"
        assert info.python_version == "3.10"
        assert info.terminal_capability == TerminalCapability.TRUECOLOR
        assert info.rsync_version == "3.2.3"
        assert info.support_level == PlatformSupport.FULL
    
    def test_platform_info_with_none_rsync(self):
        """Test PlatformInfo with None rsync version."""
        info = PlatformInfo(
            os_name="Linux",
            os_version="5.15.0",
            python_version="3.10",
            terminal_capability=TerminalCapability.BASIC_COLOR,
            rsync_version=None,
            support_level=PlatformSupport.LIMITED,
        )
        
        assert info.rsync_version is None
        assert info.support_level == PlatformSupport.LIMITED 