"""
MediaFinder service for Quick Start Mode.

This module provides intelligent media source detection using heuristic-based
scanning of mount points and common media directories. It ranks potential
sources by likelihood and integrates with the existing mount management system.
"""

import os
import logging
from dataclasses import dataclass
from typing import List, Optional, Set, Dict
from pathlib import Path
from enum import Enum

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .mount import get_mount_manager, MountManager, MountPoint


logger = logging.getLogger(__name__)


class MediaType(Enum):
    """Media type classifications."""
    MOVIES = "movies"
    TV_SHOWS = "tv_shows"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass
class MediaCandidate:
    """A potential media source discovered during scanning."""
    path: Path
    score: int
    reason: str
    media_type: MediaType = MediaType.UNKNOWN
    file_count: int = 0
    size_gb: Optional[float] = None
    mount_point: Optional[str] = None
    
    def __str__(self) -> str:
        """String representation for display."""
        type_str = self.media_type.value.replace('_', ' ').title()
        return f"{self.path} ({type_str}, Score: {self.score})"


class MediaFinder:
    """Service for discovering potential media sources automatically."""
    
    # Common media folder names (case-insensitive)
    COMMON_MEDIA_FOLDERS = {
        "movies", "movie", "films", "film", "cinema",
        "tv shows", "tv series", "television", "series", "shows",
        "tv", "videos", "video", "media", "content",
        "downloads", "torrents", "plex"
    }
    
    # Media file extensions for validation
    MEDIA_EXTENSIONS = {
        ".mkv", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".webm",
        ".m4v", ".3gp", ".ogv", ".ts", ".m2ts", ".mts"
    }
    
    # Minimum file count to consider a directory
    MIN_FILE_COUNT = 3
    
    def __init__(self, mount_manager: Optional[MountManager] = None, console: Optional[Console] = None):
        """Initialize MediaFinder.
        
        Args:
            mount_manager: Mount manager instance (uses default if None)
            console: Rich console for output (creates new if None)
        """
        self.mount_manager = mount_manager or get_mount_manager()
        self.console = console or Console()
        
    def find_potential_sources(self, scan_depth: int = 2) -> List[MediaCandidate]:
        """Scan for potential media sources using heuristic analysis.
        
        Args:
            scan_depth: Maximum directory depth to scan (default: 2)
            
        Returns:
            List of MediaCandidate objects sorted by score (highest first)
        """
        candidates = []
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            task = progress.add_task("Scanning for media sources...", total=None)
            
            try:
                # Get all available mount points
                mounts = self.mount_manager.discover_mounts()
                logger.info(f"Found {len(mounts)} mount points to scan")
                
                for mount in mounts:
                    if mount.is_healthy:
                        candidates.extend(self._scan_mount_for_media(mount, scan_depth))
                        
                # Also scan common local paths
                candidates.extend(self._scan_common_local_paths(scan_depth))
                
                progress.update(task, description="Ranking media sources...")
                
                # Remove duplicates and sort by score
                unique_candidates = self._deduplicate_candidates(candidates)
                sorted_candidates = sorted(unique_candidates, key=lambda x: x.score, reverse=True)
                
                logger.info(f"Found {len(sorted_candidates)} potential media sources")
                return sorted_candidates
                
            except Exception as e:
                logger.error(f"Error during media source discovery: {e}")
                return []
    
    def _scan_mount_for_media(self, mount: MountPoint, max_depth: int) -> List[MediaCandidate]:
        """Scan a specific mount point for media directories.
        
        Args:
            mount: Mount point to scan
            max_depth: Maximum scan depth
            
        Returns:
            List of MediaCandidate objects found in this mount
        """
        candidates = []
        mount_path = Path(mount.path)
        
        if not mount_path.exists() or not mount_path.is_dir():
            return candidates
            
        try:
            # Scan directories at the mount root and subdirectories
            for current_depth in range(max_depth + 1):
                for item in self._get_directories_at_depth(mount_path, current_depth):
                    candidate = self._analyze_directory(item, mount.path)
                    if candidate and candidate.score > 0:
                        candidates.append(candidate)
                        
        except PermissionError:
            logger.warning(f"Permission denied scanning mount: {mount.path}")
        except Exception as e:
            logger.warning(f"Error scanning mount {mount.path}: {e}")
            
        return candidates
    
    def _scan_common_local_paths(self, max_depth: int) -> List[MediaCandidate]:
        """Scan common local media paths.
        
        Args:
            max_depth: Maximum scan depth
            
        Returns:
            List of MediaCandidate objects from local paths
        """
        candidates = []
        
        # Common local media paths to check
        common_paths = [
            Path.home() / "Videos",
            Path.home() / "Movies", 
            Path.home() / "Downloads",
            Path("/media") if Path("/media").exists() else None,
            Path("/mnt") if Path("/mnt").exists() else None,
        ]
        
        # Filter out None and non-existent paths
        existing_paths = [p for p in common_paths if p and p.exists()]
        
        for path in existing_paths:
            try:
                for current_depth in range(max_depth + 1):
                    for item in self._get_directories_at_depth(path, current_depth):
                        candidate = self._analyze_directory(item, str(path))
                        if candidate and candidate.score > 0:
                            candidates.append(candidate)
            except Exception as e:
                logger.warning(f"Error scanning local path {path}: {e}")
                
        return candidates
    
    def _get_directories_at_depth(self, root_path: Path, depth: int) -> List[Path]:
        """Get all directories at a specific depth from root.
        
        Args:
            root_path: Root directory to scan from
            depth: Target depth (0 = root level)
            
        Returns:
            List of directory paths at the specified depth
        """
        if depth == 0:
            return [root_path] if root_path.is_dir() else []
            
        directories = []
        try:
            for item in root_path.iterdir():
                if item.is_dir():
                    if depth == 1:
                        directories.append(item)
                    else:
                        directories.extend(self._get_directories_at_depth(item, depth - 1))
        except PermissionError:
            pass  # Skip directories we can't access
            
        return directories
    
    def _analyze_directory(self, directory: Path, mount_point: str) -> Optional[MediaCandidate]:
        """Analyze a directory to determine if it's a media source.
        
        Args:
            directory: Directory path to analyze
            mount_point: Associated mount point path
            
        Returns:
            MediaCandidate if directory appears to contain media, None otherwise
        """
        try:
            if not directory.exists() or not directory.is_dir():
                return None
                
            score = 0
            reasons = []
            media_files = []
            total_size = 0
            
            # Heuristic 1: Directory name matching
            dir_name = directory.name.lower()
            for common_name in self.COMMON_MEDIA_FOLDERS:
                if common_name in dir_name:
                    score += 10
                    reasons.append(f"Name contains '{common_name}'")
                    break
                    
            # Heuristic 2: Media file analysis (sample first 100 files for performance)
            file_count = 0
            sample_limit = 100
            
            for item in directory.iterdir():
                if file_count >= sample_limit:
                    break
                    
                if item.is_file():
                    file_count += 1
                    if item.suffix.lower() in self.MEDIA_EXTENSIONS:
                        media_files.append(item)
                        try:
                            total_size += item.stat().st_size
                        except OSError:
                            pass  # Skip files we can't stat
                            
            # Score based on media file density
            if file_count > 0:
                media_ratio = len(media_files) / file_count
                if media_ratio > 0.7:
                    score += 15
                    reasons.append(f"High media density ({media_ratio:.1%})")
                elif media_ratio > 0.3:
                    score += 8
                    reasons.append(f"Medium media density ({media_ratio:.1%})")
                elif media_ratio > 0.1:
                    score += 3
                    reasons.append(f"Low media density ({media_ratio:.1%})")
                    
            # Minimum requirements
            if len(media_files) < self.MIN_FILE_COUNT:
                return None
                
            # Determine media type
            media_type = self._determine_media_type(directory, media_files)
            
            # Size bonus for larger collections
            size_gb = total_size / (1024**3) if total_size > 0 else 0
            if size_gb > 50:
                score += 5
                reasons.append(f"Large collection ({size_gb:.1f} GB)")
                
            if score > 0:
                return MediaCandidate(
                    path=directory,
                    score=score,
                    reason="; ".join(reasons),
                    media_type=media_type,
                    file_count=len(media_files),
                    size_gb=size_gb if size_gb > 0 else None,
                    mount_point=mount_point
                )
                
        except Exception as e:
            logger.debug(f"Error analyzing directory {directory}: {e}")
            
        return None
    
    def _determine_media_type(self, directory: Path, media_files: List[Path]) -> MediaType:
        """Determine the type of media in a directory.
        
        Args:
            directory: Directory being analyzed
            media_files: List of media files found
            
        Returns:
            MediaType classification
        """
        dir_name = directory.name.lower()
        
        # Check directory name patterns
        if any(pattern in dir_name for pattern in ["movie", "film", "cinema"]):
            return MediaType.MOVIES
        elif any(pattern in dir_name for pattern in ["tv", "series", "show", "television"]):
            return MediaType.TV_SHOWS
            
        # Check for TV show patterns in subdirectories or file names
        tv_patterns = ["season", "episode", "s01e", "s02e", "s1e", "s2e"]
        has_tv_patterns = False
        
        try:
            # Check subdirectories for season patterns
            for item in directory.iterdir():
                if item.is_dir() and any(pattern in item.name.lower() for pattern in tv_patterns):
                    has_tv_patterns = True
                    break
                    
            # Check file names for episode patterns
            if not has_tv_patterns:
                for media_file in media_files[:10]:  # Check first 10 files
                    if any(pattern in media_file.name.lower() for pattern in tv_patterns):
                        has_tv_patterns = True
                        break
                        
        except Exception:
            pass  # Skip if we can't analyze subdirectories
            
        if has_tv_patterns:
            return MediaType.TV_SHOWS
            
        # If we can't determine, assume mixed
        return MediaType.MIXED
    
    def _deduplicate_candidates(self, candidates: List[MediaCandidate]) -> List[MediaCandidate]:
        """Remove duplicate candidates based on path.
        
        Args:
            candidates: List of candidates that may contain duplicates
            
        Returns:
            List with duplicates removed, keeping highest-scored version
        """
        unique_candidates = {}
        
        for candidate in candidates:
            path_str = str(candidate.path.resolve())
            if path_str not in unique_candidates or candidate.score > unique_candidates[path_str].score:
                unique_candidates[path_str] = candidate
                
        return list(unique_candidates.values())


def get_media_finder(mount_manager: Optional[MountManager] = None, console: Optional[Console] = None) -> MediaFinder:
    """Get a MediaFinder instance.
    
    Args:
        mount_manager: Optional mount manager instance
        console: Optional Rich console instance
        
    Returns:
        MediaFinder instance
    """
    return MediaFinder(mount_manager, console)