"""
Configuration management for PlexSync.

This module handles loading, validating, and managing configuration
for media sources, sync settings, and user preferences.
"""

import os
import sys
import yaml
import logging
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field, asdict
from pathlib import Path
from enum import Enum
import keyring
from cryptography.fernet import Fernet
import base64

logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Configuration validation error."""
    pass


class SyncMode(Enum):
    """Sync mode options."""
    INCREMENTAL = "incremental"
    FULL = "full"
    MIRROR = "mirror"


class RetryBackoff(Enum):
    """Retry backoff strategies."""
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIXED = "fixed"


@dataclass
class MediaSourceConfig:
    """Configuration for a media source."""
    name: str
    base_path: str
    media_type: str  # "movie" or "tv_show"
    enabled: bool = True
    scan_depth: int = 5
    auto_mount: Optional[Dict[str, Any]] = None
    
    def __post_init__(self):
        if self.media_type not in ["movie", "tv_show"]:
            raise ConfigValidationError(f"Invalid media_type: {self.media_type}")


@dataclass
class DestinationConfig:
    """Configuration for sync destinations."""
    movies: str = "~/Media/Movies"
    tv: str = "~/Media/TV"
    create_directories: bool = True
    preserve_permissions: bool = True
    
    def __post_init__(self):
        # Expand paths
        self.movies = os.path.expanduser(self.movies)
        self.tv = os.path.expanduser(self.tv)


@dataclass
class DiscoveryConfig:
    """Media discovery configuration."""
    video_extensions: List[str] = field(default_factory=lambda: [
        ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm", 
        ".m4v", ".mpg", ".mpeg", ".3gp", ".ogv"
    ])
    ignore_patterns: List[str] = field(default_factory=lambda: [
        "sample", "trailer", "extras", "behind-the-scenes", 
        "deleted-scenes", "featurettes", ".DS_Store", "Thumbs.db"
    ])
    scan_depth: int = 5
    title_cleanup: bool = True
    extract_metadata: bool = True
    cache_results: bool = True
    cache_ttl: int = 3600  # 1 hour


@dataclass
class SyncConfig:
    """Sync engine configuration."""
    mode: SyncMode = SyncMode.INCREMENTAL
    checksum_validation: bool = True
    retry_attempts: int = 3
    retry_backoff: RetryBackoff = RetryBackoff.EXPONENTIAL
    retry_backoff_base: int = 2
    retry_backoff_max: int = 300
    bandwidth_limit: int = 0  # 0 = unlimited
    parallel_workers: int = 1
    resume_threshold: int = 1048576  # 1MB
    rsync_flags: List[str] = field(default_factory=lambda: [
        "-aAXH", "--info=progress2", "--partial"
    ])
    
    def __post_init__(self):
        if self.retry_attempts < 1:
            raise ConfigValidationError("retry_attempts must be >= 1")
        if self.parallel_workers < 1:
            raise ConfigValidationError("parallel_workers must be >= 1")


@dataclass
class SecurityConfig:
    """Security configuration."""
    ssh_key_path: str = "~/.ssh/id_rsa"
    path_redaction: bool = True
    encrypt_logs: bool = False
    keyring_service: str = "plexsync"
    
    def __post_init__(self):
        self.ssh_key_path = os.path.expanduser(self.ssh_key_path)


@dataclass
class LoggingConfig:
    """Logging configuration."""
    level: str = "INFO"
    file: str = "~/.local/share/plexsync/logs/plexsync.log"
    max_size: str = "10MB"
    backup_count: int = 5
    format: str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    def __post_init__(self):
        self.file = os.path.expanduser(self.file)
        
        # Create log directory if it doesn't exist
        log_dir = os.path.dirname(self.file)
        os.makedirs(log_dir, exist_ok=True)


@dataclass
class ProfileConfig:
    """Complete configuration profile."""
    name: str
    sources: List[MediaSourceConfig] = field(default_factory=list)
    destinations: DestinationConfig = field(default_factory=DestinationConfig)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    
    def validate(self) -> List[str]:
        """Validate the configuration and return any errors."""
        errors = []
        
        # Validate sources
        if not self.sources:
            errors.append("At least one media source must be configured")
        
        for source in self.sources:
            if not source.name:
                errors.append("Media source name cannot be empty")
            if not source.base_path:
                errors.append(f"Media source '{source.name}' base_path cannot be empty")
        
        # Validate destinations
        if not self.destinations.movies:
            errors.append("Movies destination path cannot be empty")
        if not self.destinations.tv:
            errors.append("TV shows destination path cannot be empty")
        
        # Validate discovery
        if not self.discovery.video_extensions:
            errors.append("At least one video extension must be configured")
        
        # Validate logging level
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self.logging.level not in valid_levels:
            errors.append(f"Invalid logging level: {self.logging.level}")
        
        return errors


class ConfigManager:
    """Manages PlexSync configuration."""
    
    def __init__(self, config_dir: Optional[str] = None):
        self.config_dir = config_dir or self._get_default_config_dir()
        self.config_file = os.path.join(self.config_dir, "config.yaml")
        self.profiles: Dict[str, ProfileConfig] = {}
        self.active_profile_name: Optional[str] = None
        self._encryption_key: Optional[bytes] = None
        
        # Ensure config directory exists
        os.makedirs(self.config_dir, exist_ok=True)
    
    def _get_default_config_dir(self) -> str:
        """Get default configuration directory."""
        if sys.platform == "win32":
            config_dir = os.path.expandvars(r"%APPDATA%\plexsync")
        else:
            config_dir = os.path.expanduser("~/.config/plexsync")
        
        return config_dir
    
    def load_config(self) -> bool:
        """Load configuration from file."""
        try:
            if not os.path.exists(self.config_file):
                logger.info("No configuration file found, creating default configuration")
                self._create_default_config()
                return True
            
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config_data = yaml.safe_load(f)
            
            # Load profiles
            self.profiles = {}
            profiles_data = config_data.get('profiles', {})
            
            for profile_name, profile_data in profiles_data.items():
                try:
                    profile = self._deserialize_profile(profile_name, profile_data)
                    self.profiles[profile_name] = profile
                except Exception as e:
                    logger.error(f"Error loading profile '{profile_name}': {e}")
                    continue
            
            # Set active profile
            self.active_profile_name = config_data.get('active_profile', 'default')
            
            if self.active_profile_name not in self.profiles:
                if self.profiles:
                    self.active_profile_name = next(iter(self.profiles.keys()))
                else:
                    logger.warning("No valid profiles found, creating default")
                    self._create_default_config()
            
            logger.info(f"Loaded {len(self.profiles)} profiles, active: {self.active_profile_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            return False
    
    def save_config(self) -> bool:
        """Save configuration to file."""
        try:
            config_data = {
                'active_profile': self.active_profile_name,
                'profiles': {}
            }
            
            for profile_name, profile in self.profiles.items():
                config_data['profiles'][profile_name] = self._serialize_profile(profile)
            
            with open(self.config_file, 'w', encoding='utf-8') as f:
                yaml.safe_dump(config_data, f, default_flow_style=False, indent=2)
            
            logger.info(f"Configuration saved to {self.config_file}")
            return True
            
        except Exception as e:
            logger.error(f"Error saving configuration: {e}")
            return False
    
    def _create_default_config(self):
        """Create default configuration."""
        default_sources = [
            MediaSourceConfig(
                name="Movies Primary",
                base_path="/mnt/media/Movies",
                media_type="movie"
            ),
            MediaSourceConfig(
                name="Movies Secondary",
                base_path="/mnt/media/Movies2",
                media_type="movie"
            ),
            MediaSourceConfig(
                name="TV Shows Primary",
                base_path="/mnt/media/TV",
                media_type="tv_show"
            ),
            MediaSourceConfig(
                name="TV Shows Secondary",
                base_path="/mnt/media/TV2",
                media_type="tv_show"
            ),
        ]
        
        default_profile = ProfileConfig(
            name="default",
            sources=default_sources
        )
        
        self.profiles = {"default": default_profile}
        self.active_profile_name = "default"
        
        # Save default configuration
        self.save_config()
    
    def _serialize_profile(self, profile: ProfileConfig) -> Dict[str, Any]:
        """Serialize profile to dictionary."""
        return {
            'sources': [asdict(source) for source in profile.sources],
            'destinations': asdict(profile.destinations),
            'discovery': asdict(profile.discovery),
            'sync': {
                **asdict(profile.sync),
                'mode': profile.sync.mode.value,
                'retry_backoff': profile.sync.retry_backoff.value
            },
            'security': asdict(profile.security),
            'logging': asdict(profile.logging)
        }
    
    def _deserialize_profile(self, name: str, data: Dict[str, Any]) -> ProfileConfig:
        """Deserialize profile from dictionary."""
        # Sources
        sources = []
        for source_data in data.get('sources', []):
            sources.append(MediaSourceConfig(**source_data))
        
        # Destinations
        destinations = DestinationConfig(**data.get('destinations', {}))
        
        # Discovery
        discovery = DiscoveryConfig(**data.get('discovery', {}))
        
        # Sync
        sync_data = data.get('sync', {})
        if 'mode' in sync_data:
            sync_data['mode'] = SyncMode(sync_data['mode'])
        if 'retry_backoff' in sync_data:
            sync_data['retry_backoff'] = RetryBackoff(sync_data['retry_backoff'])
        sync = SyncConfig(**sync_data)
        
        # Security
        security = SecurityConfig(**data.get('security', {}))
        
        # Logging
        logging_config = LoggingConfig(**data.get('logging', {}))
        
        return ProfileConfig(
            name=name,
            sources=sources,
            destinations=destinations,
            discovery=discovery,
            sync=sync,
            security=security,
            logging=logging_config
        )
    
    def get_active_profile(self) -> Optional[ProfileConfig]:
        """Get the active configuration profile."""
        if self.active_profile_name and self.active_profile_name in self.profiles:
            return self.profiles[self.active_profile_name]
        return None
    
    def set_active_profile(self, profile_name: str) -> bool:
        """Set the active configuration profile."""
        if profile_name not in self.profiles:
            logger.error(f"Profile '{profile_name}' not found")
            return False
        
        self.active_profile_name = profile_name
        logger.info(f"Active profile set to '{profile_name}'")
        return True
    
    def create_profile(self, profile_name: str, base_profile: Optional[str] = None) -> bool:
        """Create a new configuration profile."""
        if profile_name in self.profiles:
            logger.error(f"Profile '{profile_name}' already exists")
            return False
        
        if base_profile and base_profile in self.profiles:
            # Copy from base profile
            base = self.profiles[base_profile]
            new_profile = ProfileConfig(
                name=profile_name,
                sources=base.sources.copy(),
                destinations=base.destinations,
                discovery=base.discovery,
                sync=base.sync,
                security=base.security,
                logging=base.logging
            )
        else:
            # Create new profile with defaults
            new_profile = ProfileConfig(name=profile_name)
        
        self.profiles[profile_name] = new_profile
        logger.info(f"Created new profile '{profile_name}'")
        return True
    
    def delete_profile(self, profile_name: str) -> bool:
        """Delete a configuration profile."""
        if profile_name not in self.profiles:
            logger.error(f"Profile '{profile_name}' not found")
            return False
        
        if profile_name == self.active_profile_name:
            logger.error("Cannot delete active profile")
            return False
        
        del self.profiles[profile_name]
        logger.info(f"Deleted profile '{profile_name}'")
        return True
    
    def validate_active_profile(self) -> List[str]:
        """Validate the active profile configuration."""
        profile = self.get_active_profile()
        if not profile:
            return ["No active profile configured"]
        
        return profile.validate()
    
    def get_media_sources(self) -> List[MediaSourceConfig]:
        """Get media sources from active profile."""
        profile = self.get_active_profile()
        if not profile:
            return []
        
        return [source for source in profile.sources if source.enabled]
    
    def store_credential(self, key: str, value: str) -> bool:
        """Store a credential securely."""
        try:
            profile = self.get_active_profile()
            if not profile:
                return False
            
            keyring.set_password(profile.security.keyring_service, key, value)
            logger.info(f"Stored credential for key: {key}")
            return True
            
        except Exception as e:
            logger.error(f"Error storing credential: {e}")
            return False
    
    def get_credential(self, key: str) -> Optional[str]:
        """Retrieve a credential securely."""
        try:
            profile = self.get_active_profile()
            if not profile:
                return None
            
            return keyring.get_password(profile.security.keyring_service, key)
            
        except Exception as e:
            logger.error(f"Error retrieving credential: {e}")
            return None
    
    def export_profile(self, profile_name: str, file_path: str) -> bool:
        """Export a profile to file."""
        if profile_name not in self.profiles:
            logger.error(f"Profile '{profile_name}' not found")
            return False
        
        try:
            profile_data = {
                'profile': self._serialize_profile(self.profiles[profile_name]),
                'exported_at': time.time(),
                'version': "1.0"
            }
            
            with open(file_path, 'w', encoding='utf-8') as f:
                yaml.safe_dump(profile_data, f, default_flow_style=False, indent=2)
            
            logger.info(f"Profile '{profile_name}' exported to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error exporting profile: {e}")
            return False
    
    def import_profile(self, file_path: str, profile_name: Optional[str] = None) -> bool:
        """Import a profile from file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                profile_data = yaml.safe_load(f)
            
            if 'profile' not in profile_data:
                logger.error("Invalid profile file format")
                return False
            
            imported_name = profile_name or f"imported_{int(time.time())}"
            
            profile = self._deserialize_profile(imported_name, profile_data['profile'])
            profile.name = imported_name
            
            self.profiles[imported_name] = profile
            logger.info(f"Profile imported as '{imported_name}'")
            return True
            
        except Exception as e:
            logger.error(f"Error importing profile: {e}")
            return False


# Global configuration manager instance
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> ConfigManager:
    """Get the global configuration manager instance."""
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager()
        _config_manager.load_config()
    return _config_manager


def get_active_config() -> Optional[ProfileConfig]:
    """Get the active configuration profile."""
    return get_config_manager().get_active_profile() 