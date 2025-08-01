"""
Settings management for PlexSync system configuration.

This module provides centralized settings management for application-level
configuration separate from profile-specific settings. It handles UI preferences,
logging configuration, performance settings, and system defaults.
"""

import os
import sys
import yaml
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class SettingsValidationError(Exception):
    """Settings validation error."""
    pass


class UITheme(Enum):
    """UI theme options."""
    AUTO = "auto"
    LIGHT = "light"
    DARK = "dark"


class LogLevel(Enum):
    """Log level options."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


@dataclass
class UISettings:
    """User interface settings."""
    theme: UITheme = UITheme.AUTO
    color_output: bool = True
    progress_bars: bool = True
    banner_display: bool = True
    table_style: str = "default"
    confirmation_prompts: bool = True
    
    def __post_init__(self):
        if isinstance(self.theme, str):
            self.theme = UITheme(self.theme)


@dataclass
class PerformanceSettings:
    """Performance and optimization settings."""
    max_workers: int = 4
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600
    health_check_timeout: int = 10
    mount_check_timeout: int = 5
    default_bandwidth_limit: int = 0  # 0 = unlimited
    parallel_health_checks: bool = True
    
    def __post_init__(self):
        if self.max_workers < 1:
            raise SettingsValidationError("max_workers must be >= 1")
        if self.cache_ttl_seconds < 0:
            raise SettingsValidationError("cache_ttl_seconds must be >= 0")


@dataclass
class PathSettings:
    """Default paths and directories."""
    config_dir: str = ""
    cache_dir: str = ""
    log_dir: str = ""
    backup_dir: str = ""
    temp_dir: str = ""
    
    def __post_init__(self):
        # Set defaults if empty
        if not self.config_dir:
            self.config_dir = self._get_default_config_dir()
        if not self.cache_dir:
            self.cache_dir = os.path.join(self.config_dir, "cache")
        if not self.log_dir:
            self.log_dir = os.path.join(self.config_dir, "logs")  
        if not self.backup_dir:
            self.backup_dir = os.path.join(self.config_dir, "backups")
        if not self.temp_dir:
            self.temp_dir = os.path.join(self.config_dir, "temp")
        
        # Expand paths
        self.config_dir = os.path.expanduser(self.config_dir)
        self.cache_dir = os.path.expanduser(self.cache_dir)
        self.log_dir = os.path.expanduser(self.log_dir)
        self.backup_dir = os.path.expanduser(self.backup_dir)
        self.temp_dir = os.path.expanduser(self.temp_dir)
    
    def _get_default_config_dir(self) -> str:
        """Get default configuration directory."""
        if sys.platform == "win32":
            return os.path.expandvars(r"%APPDATA%\plexsync")
        else:
            return "~/.config/plexsync"


@dataclass
class LoggingSettings:
    """Logging configuration settings."""
    level: LogLevel = LogLevel.INFO
    file_logging: bool = True
    console_logging: bool = True
    max_file_size_mb: int = 10
    backup_count: int = 5
    format_string: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    def __post_init__(self):
        if isinstance(self.level, str):
            self.level = LogLevel(self.level)
        if self.max_file_size_mb < 1:
            raise SettingsValidationError("max_file_size_mb must be >= 1")
        if self.backup_count < 0:
            raise SettingsValidationError("backup_count must be >= 0")


@dataclass
class SecuritySettings:
    """Security and privacy settings."""
    path_redaction: bool = True
    encrypt_backups: bool = False
    secure_credential_storage: bool = True
    auto_update_checks: bool = True
    anonymous_usage_stats: bool = False


@dataclass
class QuickStartPreferences:
    """Quick start mode preferences and learned behavior."""
    last_source_path: Optional[str] = None
    last_destination_path: Optional[str] = None
    last_success_timestamp: Optional[float] = None
    preferred_media_type: Optional[str] = None
    successful_completion_count: int = 0
    average_completion_time_seconds: Optional[float] = None
    last_mount_point: Optional[str] = None
    skip_plex_validation: bool = False
    
    def record_success(self, source_path: str, destination_path: str, 
                      completion_time_seconds: float, media_type: Optional[str] = None):
        """Record a successful quick start completion."""
        import time
        
        self.last_source_path = source_path
        self.last_destination_path = destination_path
        self.last_success_timestamp = time.time()
        self.successful_completion_count += 1
        
        if media_type:
            self.preferred_media_type = media_type
            
        # Update average completion time
        if self.average_completion_time_seconds is None:
            self.average_completion_time_seconds = completion_time_seconds
        else:
            # Weighted average favoring recent completions
            weight = 0.3
            self.average_completion_time_seconds = (
                (1 - weight) * self.average_completion_time_seconds + 
                weight * completion_time_seconds
            )
    
    def get_success_rate_estimate(self) -> float:
        """Get estimated success rate based on completion history."""
        if self.successful_completion_count == 0:
            return 0.0
        # Simple heuristic - more completions = higher confidence
        return min(0.95, 0.5 + (self.successful_completion_count * 0.1))
    
    
@dataclass
class SystemSettings:
    """Complete system settings configuration."""
    ui: UISettings = field(default_factory=UISettings)
    performance: PerformanceSettings = field(default_factory=PerformanceSettings)
    paths: PathSettings = field(default_factory=PathSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    quick_start: QuickStartPreferences = field(default_factory=QuickStartPreferences)
    
    def validate(self) -> List[str]:
        """Validate the settings and return any errors."""
        errors = []
        
        # Validate UI settings
        if not isinstance(self.ui.theme, UITheme):
            errors.append("Invalid UI theme")
        
        # Validate performance settings
        if self.performance.max_workers < 1:
            errors.append("max_workers must be >= 1")
        if self.performance.health_check_timeout < 1:
            errors.append("health_check_timeout must be >= 1")
        
        # Validate logging settings
        if not isinstance(self.logging.level, LogLevel):
            errors.append("Invalid logging level")
        
        return errors


class SettingsManager:
    """Manages PlexSync system settings."""
    
    def __init__(self, settings_file: Optional[str] = None):
        self.settings_file = settings_file or self._get_default_settings_file()
        self.settings: SystemSettings = SystemSettings()
        self._ensure_settings_dir()
    
    def _get_default_settings_file(self) -> str:
        """Get default settings file path."""
        paths = PathSettings()
        return os.path.join(paths.config_dir, "settings.yaml")
    
    def _ensure_settings_dir(self):
        """Ensure settings directory exists."""
        settings_dir = os.path.dirname(self.settings_file)
        os.makedirs(settings_dir, exist_ok=True)
    
    def load_settings(self) -> bool:
        """Load settings from file."""
        try:
            if not os.path.exists(self.settings_file):
                logger.info("No settings file found, creating default settings")
                self._create_default_settings()
                return True
            
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                settings_data = yaml.safe_load(f)
            
            if not settings_data:
                logger.warning("Empty settings file, using defaults")
                self._create_default_settings()
                return True
            
            # Deserialize settings
            self.settings = self._deserialize_settings(settings_data)
            
            # Validate settings
            errors = self.settings.validate()
            if errors:
                logger.warning(f"Settings validation errors: {errors}")
                # Continue with potentially invalid settings rather than fail
            
            logger.info(f"Settings loaded from {self.settings_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            logger.info("Using default settings")
            self.settings = SystemSettings()
            return False
    
    def save_settings(self) -> bool:
        """Save settings to file."""
        try:
            # Validate before saving
            errors = self.settings.validate()
            if errors:
                raise SettingsValidationError(f"Settings validation failed: {errors}")
            
            settings_data = self._serialize_settings(self.settings)
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(settings_data, f, default_flow_style=False, indent=2)
            
            logger.info(f"Settings saved to {self.settings_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return False
    
    def _create_default_settings(self):
        """Create default settings."""
        self.settings = SystemSettings()
        self.save_settings()
    
    def _serialize_settings(self, settings: SystemSettings) -> Dict[str, Any]:
        """Serialize settings to dictionary."""
        return {
            'ui': {
                **asdict(settings.ui),
                'theme': settings.ui.theme.value
            },
            'performance': asdict(settings.performance),
            'paths': asdict(settings.paths),
            'logging': {
                **asdict(settings.logging),
                'level': settings.logging.level.value
            },
            'security': asdict(settings.security)
        }
    
    def _deserialize_settings(self, data: Dict[str, Any]) -> SystemSettings:
        """Deserialize settings from dictionary."""
        # UI settings
        ui_data = data.get('ui', {})
        ui = UISettings(**ui_data)
        
        # Performance settings
        performance_data = data.get('performance', {})
        performance = PerformanceSettings(**performance_data)
        
        # Path settings
        paths_data = data.get('paths', {})
        paths = PathSettings(**paths_data)
        
        # Logging settings
        logging_data = data.get('logging', {})
        logging_settings = LoggingSettings(**logging_data)
        
        # Security settings
        security_data = data.get('security', {})
        security = SecuritySettings(**security_data)
        
        return SystemSettings(
            ui=ui,
            performance=performance,
            paths=paths,
            logging=logging_settings,
            security=security
        )
    
    def get_setting(self, key: str) -> Any:
        """Get a setting value by dot-notation key."""
        try:
            parts = key.split('.')
            value = self.settings
            
            for part in parts:
                if hasattr(value, part):
                    value = getattr(value, part)
                else:
                    raise KeyError(f"Setting key not found: {key}")
            
            return value
            
        except Exception as e:
            logger.error(f"Error getting setting '{key}': {e}")
            return None
    
    def set_setting(self, key: str, value: Any) -> bool:
        """Set a setting value by dot-notation key."""
        try:
            parts = key.split('.')
            if len(parts) < 2:
                raise ValueError("Setting key must have at least two parts (category.setting)")
            
            # Navigate to the parent object
            obj = self.settings
            for part in parts[:-1]:
                if hasattr(obj, part):
                    obj = getattr(obj, part)
                else:
                    raise KeyError(f"Setting category not found: {'.'.join(parts[:-1])}")
            
            # Set the final value
            final_key = parts[-1]
            if hasattr(obj, final_key):
                # Handle enum conversions
                if final_key == 'theme' and isinstance(obj, UISettings):
                    if isinstance(value, str):
                        value = UITheme(value)
                elif final_key == 'level' and isinstance(obj, LoggingSettings):
                    if isinstance(value, str):
                        value = LogLevel(value)
                
                setattr(obj, final_key, value)
                logger.info(f"Setting '{key}' updated to: {value}")
                return True
            else:
                raise KeyError(f"Setting not found: {key}")
            
        except Exception as e:
            logger.error(f"Error setting '{key}' to '{value}': {e}")
            return False
    
    def reset_settings(self) -> bool:
        """Reset all settings to defaults."""
        try:
            self.settings = SystemSettings()
            return self.save_settings()
        except Exception as e:
            logger.error(f"Error resetting settings: {e}")
            return False
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all settings as a flat dictionary."""
        result = {}
        
        # UI settings
        for key, value in asdict(self.settings.ui).items():
            if isinstance(value, Enum):
                value = value.value
            result[f"ui.{key}"] = value
        
        # Performance settings
        for key, value in asdict(self.settings.performance).items():
            result[f"performance.{key}"] = value
        
        # Path settings
        for key, value in asdict(self.settings.paths).items():
            result[f"paths.{key}"] = value
        
        # Logging settings
        for key, value in asdict(self.settings.logging).items():
            if isinstance(value, Enum):
                value = value.value
            result[f"logging.{key}"] = value
        
        # Security settings
        for key, value in asdict(self.settings.security).items():
            result[f"security.{key}"] = value
        
        return result
    
    def export_settings(self, file_path: str) -> bool:
        """Export settings to a file."""
        try:
            settings_data = self._serialize_settings(self.settings)
            export_data = {
                'settings': settings_data,
                'exported_at': __import__('time').time(),
                'version': "1.0"
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(export_data, f, default_flow_style=False, indent=2)
            
            logger.info(f"Settings exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting settings: {e}")
            return False
    
    def import_settings(self, file_path: str) -> bool:
        """Import settings from a file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                import_data = yaml.safe_load(f)
            
            if 'settings' not in import_data:
                raise ValueError("Invalid settings file format")
            
            # Deserialize and validate imported settings
            imported_settings = self._deserialize_settings(import_data['settings'])
            errors = imported_settings.validate()
            
            if errors:
                raise SettingsValidationError(f"Imported settings validation failed: {errors}")
            
            # Apply imported settings
            self.settings = imported_settings
            success = self.save_settings()
            
            if success:
                logger.info(f"Settings imported from {file_path}")
            
            return success
            
        except Exception as e:
            logger.error(f"Error importing settings: {e}")
            return False


# Global settings manager instance
_settings_manager: Optional[SettingsManager] = None


def get_settings_manager() -> SettingsManager:
    """Get the global settings manager instance."""
    global _settings_manager
    if _settings_manager is None:
        _settings_manager = SettingsManager()
        _settings_manager.load_settings()
    return _settings_manager


def get_settings() -> SystemSettings:
    """Get the current system settings."""
    return get_settings_manager().settings