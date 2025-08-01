"""
Downloaded Media Management Module

This module provides functionality for discovering, cataloging, and managing
already-downloaded media files. It scans the sync directory and matches files
back to their original library entries without maintaining persistent state.

Core principle: File System is Truth - always derive state from actual files.
"""

import os
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import re

from .datasets import MediaItem, MediaLibrary, MediaType


class FileStatus(Enum):
    """Status of a downloaded file."""
    COMPLETE = "complete"      # Perfect match to source
    PARTIAL = "partial"        # Incomplete transfer
    CORRUPTED = "corrupted"    # Size matches but checksum fails
    ORPHANED = "orphaned"      # No matching library entry
    MODIFIED = "modified"      # File modified after download
    UNKNOWN = "unknown"        # Unable to determine status


@dataclass
class DownloadedFile:
    """Information about a downloaded file."""
    file_path: Path
    file_size: int
    modified_time: datetime
    status: FileStatus
    matched_item: Optional[MediaItem] = None
    integrity_hash: Optional[str] = None
    source_path: Optional[Path] = None
    download_date: Optional[datetime] = None
    
    @property
    def display_name(self) -> str:
        """Get display name for the file."""
        return self.file_path.stem
    
    @property
    def file_extension(self) -> str:
        """Get file extension."""
        return self.file_path.suffix.lower()
    
    @property
    def is_video_file(self) -> bool:
        """Check if file is a video file."""
        video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        return self.file_extension in video_extensions
    
    @property
    def size_gb(self) -> float:
        """Get file size in GB."""
        return self.file_size / (1024 ** 3)
    
    @property
    def show_name(self) -> str:
        """Get show name for TV episodes."""
        if self.matched_item and hasattr(self.matched_item, 'show_name') and self.matched_item.show_name:
            return self.matched_item.show_name
        
        # Try to extract show name from filename for orphaned files
        filename = self.file_path.stem
        
        # Look for common TV show patterns
        import re
        
        # Pattern: Show Name S01E01 or Show Name 1x01
        tv_pattern = re.search(r'^(.*?)\s*(?:s\d+e\d+|\d+x\d+)', filename, re.IGNORECASE)
        if tv_pattern:
            show_name = tv_pattern.group(1).strip()
            # Clean up common separators
            show_name = re.sub(r'[._\-]+', ' ', show_name).strip()
            return show_name if show_name else "Unknown Show"
        
        return "Unknown Show"
    
    @property
    def episode_info(self) -> str:
        """Get episode information for display."""
        if self.matched_item and hasattr(self.matched_item, 'episode_title') and self.matched_item.episode_title:
            season = getattr(self.matched_item, 'season', '')
            episode = getattr(self.matched_item, 'episode', '')
            if season and episode:
                return f"S{season:02d}E{episode:02d}: {self.matched_item.episode_title}"
            else:
                return self.matched_item.episode_title
        
        # For orphaned files, just return the filename
        return self.display_name


@dataclass
class DownloadedMediaSummary:
    """Summary of downloaded media."""
    total_files: int = 0
    total_size: int = 0
    movies: List[DownloadedFile] = field(default_factory=list)
    episodes: List[DownloadedFile] = field(default_factory=list)
    orphaned: List[DownloadedFile] = field(default_factory=list)
    partial: List[DownloadedFile] = field(default_factory=list)
    corrupted: List[DownloadedFile] = field(default_factory=list)
    
    @property
    def total_size_gb(self) -> float:
        """Get total size in GB."""
        return self.total_size / (1024 ** 3)
    
    @property
    def movie_count(self) -> int:
        """Get number of movies."""
        return len(self.movies)
    
    @property
    def episode_count(self) -> int:
        """Get number of episodes."""
        return len(self.episodes)
    
    @property
    def orphaned_count(self) -> int:
        """Get number of orphaned files."""
        return len(self.orphaned)
    
    @property
    def movies_size_gb(self) -> float:
        """Get movies total size in GB."""
        return sum(f.file_size for f in self.movies) / (1024 ** 3)
    
    @property
    def episodes_size_gb(self) -> float:
        """Get episodes total size in GB."""
        return sum(f.file_size for f in self.episodes) / (1024 ** 3)


class DownloadedMediaScanner:
    """Scans sync directory and matches files to library entries."""
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize scanner with config object.
        
        Args:
            config: Config object with sync_dir attribute, or None to use default
        """
        self.config = config
        
        # Get sync directory from config or use default
        if config and hasattr(config, 'sync_dir'):
            self.sync_dir = Path(config.sync_dir)
        else:
            # Default to ~/PlexSync directory
            self.sync_dir = Path.home() / 'PlexSync'
            
        self._video_extensions = {'.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
        
    def scan_sync_directory(self) -> List[DownloadedFile]:
        """
        Scan the sync directory and catalog all downloaded files.
        
        Returns:
            List of DownloadedFile objects for all video files found
        """
        if not self.sync_dir.exists():
            return []
        
        downloaded_files = []
        
        # Walk through all files in sync directory
        for file_path in self.sync_dir.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self._video_extensions:
                try:
                    # Get file information
                    stat = file_path.stat()
                    file_size = stat.st_size
                    modified_time = datetime.fromtimestamp(stat.st_mtime)
                    
                    # Create downloaded file object
                    downloaded_file = DownloadedFile(
                        file_path=file_path,
                        file_size=file_size,
                        modified_time=modified_time,
                        status=FileStatus.UNKNOWN,
                        download_date=modified_time  # Use modified time as download date
                    )
                    
                    downloaded_files.append(downloaded_file)
                    
                except (OSError, PermissionError) as e:
                    # Skip files we can't read
                    continue
        
        return downloaded_files
    
    def match_files_to_library(self, files: List[DownloadedFile], library: MediaLibrary) -> Dict[str, Any]:
        """
        Match downloaded files back to original library entries.
        
        Args:
            files: List of downloaded files to match
            library: Media library to match against
            
        Returns:
            Dictionary with matching results and statistics
        """
        matched_files = []
        unmatched_files = []
        
        # Get all library items for matching
        all_library_items = []
        if hasattr(library, 'movies'):
            all_library_items.extend(library.movies)
        if hasattr(library, 'tv_shows'):
            # Get all episodes from all shows
            for show_episodes in library.tv_shows.values():
                all_library_items.extend(show_episodes)
        
        # Try to match each downloaded file
        for downloaded_file in files:
            matched_item = self._find_matching_library_item(downloaded_file, all_library_items)
            
            if matched_item:
                downloaded_file.matched_item = matched_item
                downloaded_file.source_path = Path(matched_item.source_path)
                downloaded_file.status = self._determine_file_status(downloaded_file, matched_item)
                matched_files.append(downloaded_file)
            else:
                downloaded_file.status = FileStatus.ORPHANED
                unmatched_files.append(downloaded_file)
        
        return {
            'matched_files': matched_files,
            'unmatched_files': unmatched_files,
            'total_files': len(files),
            'match_rate': len(matched_files) / len(files) if files else 0
        }
    
    def _find_matching_library_item(self, downloaded_file: DownloadedFile, library_items: List[MediaItem]) -> Optional[MediaItem]:
        """
        Find the library item that matches a downloaded file.
        
        Uses multiple matching strategies:
        1. Exact filename match
        2. Size-based matching
        3. Fuzzy filename matching
        """
        downloaded_name = downloaded_file.file_path.name
        downloaded_size = downloaded_file.file_size
        
        # Strategy 1: Exact filename match
        for item in library_items:
            library_filename = Path(item.source_path).name
            if downloaded_name == library_filename:
                return item
        
        # Strategy 2: Size-based matching (within 1% tolerance)
        size_candidates = []
        for item in library_items:
            if abs(item.file_size - downloaded_size) / max(item.file_size, downloaded_size) < 0.01:
                size_candidates.append(item)
        
        if len(size_candidates) == 1:
            return size_candidates[0]
        
        # Strategy 3: Fuzzy filename matching for size candidates
        if size_candidates:
            best_match = self._find_best_filename_match(downloaded_name, size_candidates)
            if best_match:
                return best_match
        
        # Strategy 4: Fuzzy filename matching for all items (fallback)
        return self._find_best_filename_match(downloaded_name, library_items)
    
    def _find_best_filename_match(self, downloaded_name: str, candidates: List[MediaItem]) -> Optional[MediaItem]:
        """Find the best filename match using fuzzy matching."""
        # Normalize names for comparison
        normalized_downloaded = self._normalize_filename(downloaded_name)
        
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            candidate_name = Path(candidate.source_path).name
            normalized_candidate = self._normalize_filename(candidate_name)
            
            # Calculate similarity score
            score = self._calculate_similarity(normalized_downloaded, normalized_candidate)
            
            if score > best_score and score > 0.7:  # Minimum 70% similarity
                best_score = score
                best_match = candidate
        
        return best_match
    
    def _normalize_filename(self, filename: str) -> str:
        """Normalize filename for comparison."""
        # Remove file extension
        name = Path(filename).stem
        
        # Convert to lowercase
        name = name.lower()
        
        # Remove common patterns
        patterns_to_remove = [
            r'\d{4}',  # Years
            r'(720p|1080p|4k|2160p)',  # Resolutions
            r'(bluray|blu-ray|webdl|web-dl|hdtv|dvdrip)',  # Sources
            r'(x264|x265|h264|h265)',  # Codecs
            r'(aac|dts|ac3)',  # Audio codecs
            r'(s\d{2}e\d{2})',  # Season/Episode patterns
            r'[\[\]()]',  # Brackets
            r'[._-]+',  # Separators
        ]
        
        for pattern in patterns_to_remove:
            name = re.sub(pattern, ' ', name, flags=re.IGNORECASE)
        
        # Clean up whitespace
        name = ' '.join(name.split())
        
        return name
    
    def _calculate_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings."""
        # Simple implementation - can be enhanced with more sophisticated algorithms
        words1 = set(str1.split())
        words2 = set(str2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union) if union else 0.0
    
    def _determine_file_status(self, downloaded_file: DownloadedFile, library_item: MediaItem) -> FileStatus:
        """Determine the status of a downloaded file."""
        # Check if sizes match
        if downloaded_file.file_size == library_item.file_size:
            return FileStatus.COMPLETE
        elif downloaded_file.file_size < library_item.file_size:
            return FileStatus.PARTIAL
        else:
            return FileStatus.MODIFIED
    
    def get_summary(self, library: MediaLibrary) -> DownloadedMediaSummary:
        """
        Get a comprehensive summary of downloaded media.
        
        Returns:
            DownloadedMediaSummary with categorized files and statistics
        """
        # Scan sync directory
        downloaded_files = self.scan_sync_directory()
        
        if not downloaded_files:
            return DownloadedMediaSummary()
        
        # Match files to library
        match_results = self.match_files_to_library(downloaded_files, library)
        
        # Create summary
        summary = DownloadedMediaSummary()
        summary.total_files = len(downloaded_files)
        summary.total_size = sum(f.file_size for f in downloaded_files)
        
        # Categorize files
        for file in downloaded_files:
            if file.status == FileStatus.ORPHANED:
                summary.orphaned.append(file)
            elif file.status == FileStatus.PARTIAL:
                summary.partial.append(file)
            elif file.status == FileStatus.CORRUPTED:
                summary.corrupted.append(file)
            elif file.matched_item:
                # Categorize by media type from matched library item
                if file.matched_item.media_type == MediaType.TV_EPISODE:
                    summary.episodes.append(file)
                else:
                    summary.movies.append(file)
            else:
                # For unmatched files, try to detect type from filename
                filename = file.file_path.name.lower()
                # Look for TV episode patterns
                tv_patterns = [
                    r's\d+e\d+',  # S01E01
                    r'season\s*\d+.*episode\s*\d+',  # Season 1 Episode 1
                    r'\d+x\d+',  # 1x01
                ]
                
                is_tv_episode = any(re.search(pattern, filename, re.IGNORECASE) for pattern in tv_patterns)
                
                if is_tv_episode:
                    summary.episodes.append(file)
                else:
                    summary.movies.append(file)
        
        return summary


class DownloadedMediaManager:
    """High-level manager for downloaded media operations."""
    
    def __init__(self, config: Optional[Any] = None):
        """
        Initialize manager with config object.
        
        Args:
            config: Config object with sync_dir attribute, or None to use default
        """
        self.config = config
        self.scanner = DownloadedMediaScanner(config)
    
    def get_status_report(self, library: MediaLibrary) -> Dict[str, Any]:
        """
        Get a comprehensive status report of downloaded media.
        
        Returns:
            Dictionary with status information for display
        """
        summary = self.scanner.get_summary(library)
        
        # Calculate percentages
        total_movies = len(library.movies) if hasattr(library, 'movies') else 0
        total_episodes = 0
        if hasattr(library, 'tv_shows'):
            # Count total episodes from all shows
            total_episodes = sum(len(episodes) for episodes in library.tv_shows.values())
        
        movie_percentage = (summary.movie_count / total_movies * 100) if total_movies > 0 else 0
        episode_percentage = (summary.episode_count / total_episodes * 100) if total_episodes > 0 else 0
        
        return {
            'summary': summary,
            'percentages': {
                'movies': movie_percentage,
                'episodes': episode_percentage
            },
            'issues': {
                'partial_count': len(summary.partial),
                'corrupted_count': len(summary.corrupted),
                'orphaned_count': len(summary.orphaned)
            },
            'library_totals': {
                'movies': total_movies,
                'episodes': total_episodes
            }
        }
    
    def get_summary(self, library: MediaLibrary) -> DownloadedMediaSummary:
        """
        Get a summary of downloaded media.
        
        Returns:
            DownloadedMediaSummary object
        """
        return self.scanner.get_summary(library)
    
    def find_files_by_status(self, library: MediaLibrary, status: FileStatus) -> List[DownloadedFile]:
        """Find all files with a specific status."""
        downloaded_files = self.scanner.scan_sync_directory()
        self.scanner.match_files_to_library(downloaded_files, library)
        
        return [f for f in downloaded_files if f.status == status]
    
    def find_orphaned_files(self, library: MediaLibrary) -> List[DownloadedFile]:
        """Find all orphaned files (not in library)."""
        return self.find_files_by_status(library, FileStatus.ORPHANED)
    
    def find_partial_files(self, library: MediaLibrary) -> List[DownloadedFile]:
        """Find all partial files (incomplete downloads)."""
        return self.find_files_by_status(library, FileStatus.PARTIAL)
    
    def find_corrupted_files(self, library: MediaLibrary) -> List[DownloadedFile]:
        """Find all corrupted files."""
        return self.find_files_by_status(library, FileStatus.CORRUPTED) 