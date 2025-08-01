"""
Advanced Duplicate Detection Module

This module provides sophisticated duplicate detection beyond exact file matches,
including similarity-based detection, fuzzy matching, and intelligent grouping.
"""

import os
import hashlib
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
from collections import defaultdict
import difflib

from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from rich.text import Text
from rich.panel import Panel

from .downloaded import DownloadedFile, DownloadedMediaManager
from .datasets import MediaLibrary
from .storage_analytics import DuplicateGroup


class SimilarityType(Enum):
    """Types of similarity detection."""
    EXACT = "exact"                    # Identical files (checksum match)
    SIMILAR_NAME = "similar_name"      # Similar filenames
    SIMILAR_SIZE = "similar_size"      # Similar file sizes
    SAME_CONTENT = "same_content"      # Same media content, different quality
    DUPLICATE_EPISODE = "duplicate_episode"  # Same episode, different sources
    DUPLICATE_MOVIE = "duplicate_movie"      # Same movie, different versions


class MatchConfidence(Enum):
    """Confidence levels for similarity matches."""
    VERY_HIGH = "very_high"    # 95%+ confidence
    HIGH = "high"              # 80-95% confidence
    MEDIUM = "medium"          # 60-80% confidence
    LOW = "low"                # 40-60% confidence
    VERY_LOW = "very_low"      # <40% confidence


@dataclass
class SimilarityMatch:
    """Represents a similarity match between files."""
    file1: DownloadedFile
    file2: DownloadedFile
    similarity_type: SimilarityType
    confidence: MatchConfidence
    similarity_score: float  # 0.0 to 1.0
    details: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def confidence_percentage(self) -> int:
        """Get confidence as percentage."""
        return int(self.similarity_score * 100)
    
    @property
    def size_difference(self) -> int:
        """Get size difference in bytes."""
        return abs(self.file1.file_size - self.file2.file_size)
    
    @property
    def size_difference_gb(self) -> float:
        """Get size difference in GB."""
        return self.size_difference / (1024**3)


@dataclass
class SimilarityGroup:
    """Group of similar files."""
    files: List[DownloadedFile] = field(default_factory=list)
    similarity_type: SimilarityType = SimilarityType.EXACT
    confidence: MatchConfidence = MatchConfidence.LOW
    representative_file: Optional[DownloadedFile] = None
    matches: List[SimilarityMatch] = field(default_factory=list)
    
    @property
    def total_size(self) -> int:
        """Total size of all files in group."""
        return sum(f.file_size for f in self.files)
    
    @property
    def total_size_gb(self) -> float:
        """Total size in GB."""
        return self.total_size / (1024**3)
    
    @property
    def wasted_space(self) -> int:
        """Space wasted by keeping all files (total - best file)."""
        if not self.files:
            return 0
        
        # Keep the highest quality file (usually the largest)
        best_file = max(self.files, key=lambda f: f.file_size)
        return self.total_size - best_file.file_size
    
    @property
    def wasted_space_gb(self) -> float:
        """Wasted space in GB."""
        return self.wasted_space / (1024**3)
    
    def get_recommended_action(self) -> str:
        """Get recommended action for this group."""
        if self.confidence in [MatchConfidence.VERY_HIGH, MatchConfidence.HIGH]:
            if self.similarity_type == SimilarityType.EXACT:
                return "Delete all but one (exact duplicates)"
            elif self.similarity_type == SimilarityType.SAME_CONTENT:
                return "Keep highest quality, delete others"
            elif self.similarity_type in [SimilarityType.DUPLICATE_EPISODE, SimilarityType.DUPLICATE_MOVIE]:
                return "Review and keep best version"
        
        return "Review manually"


class AdvancedDuplicateDetector:
    """Advanced duplicate detection with similarity algorithms."""
    
    def __init__(self, console: Console, manager: DownloadedMediaManager):
        self.console = console
        self.manager = manager
        self.checksum_cache: Dict[str, str] = {}
        
        # Detection parameters
        self.name_similarity_threshold = 0.8
        self.size_similarity_threshold = 0.95  # 95% similar size
        self.partial_checksum_size = 1024 * 1024  # 1MB for partial checksums
        
    def find_advanced_duplicates(self, library: MediaLibrary) -> List[SimilarityGroup]:
        """Find duplicates using advanced similarity detection."""
        summary = self.manager.get_summary(library)
        all_files = summary.movies + summary.episodes + summary.orphaned
        
        if len(all_files) < 2:
            return []
        
        self.console.print("🔍 Advanced Duplicate Detection", style="bold blue")
        self.console.print(f"Analyzing {len(all_files)} files for similarities...")
        
        similarity_groups = []
        
        with Progress(console=self.console) as progress:
            task = progress.add_task("Detecting similarities...", total=len(all_files))
            
            # Step 1: Find exact duplicates
            exact_groups = self._find_exact_duplicates(all_files, progress, task)
            similarity_groups.extend(exact_groups)
            
            # Step 2: Find similar names
            name_groups = self._find_similar_names(all_files, progress, task)
            similarity_groups.extend(name_groups)
            
            # Step 3: Find similar sizes
            size_groups = self._find_similar_sizes(all_files, progress, task)
            similarity_groups.extend(size_groups)
            
            # Step 4: Find same content (different quality)
            content_groups = self._find_same_content(all_files, progress, task)
            similarity_groups.extend(content_groups)
            
            # Step 5: Find duplicate episodes/movies
            media_groups = self._find_duplicate_media(all_files, progress, task)
            similarity_groups.extend(media_groups)
        
        # Remove overlapping groups and merge similar ones
        similarity_groups = self._deduplicate_groups(similarity_groups)
        
        # Sort by confidence and wasted space
        similarity_groups.sort(key=lambda g: (g.confidence.value, g.wasted_space), reverse=True)
        
        return similarity_groups
    
    def _find_exact_duplicates(self, files: List[DownloadedFile], 
                              progress: Progress, task) -> List[SimilarityGroup]:
        """Find exact duplicates using checksums."""
        groups = []
        checksum_map = defaultdict(list)
        
        for file in files:
            try:
                checksum = self._get_file_checksum(file.file_path)
                if checksum:
                    checksum_map[checksum].append(file)
                progress.update(task, advance=0.2)
            except Exception:
                progress.update(task, advance=0.2)
                continue
        
        # Create groups for duplicates
        for checksum, duplicate_files in checksum_map.items():
            if len(duplicate_files) > 1:
                # Create similarity matches
                matches = []
                for i, file1 in enumerate(duplicate_files):
                    for file2 in duplicate_files[i+1:]:
                        match = SimilarityMatch(
                            file1=file1,
                            file2=file2,
                            similarity_type=SimilarityType.EXACT,
                            confidence=MatchConfidence.VERY_HIGH,
                            similarity_score=1.0,
                            details={"checksum": checksum}
                        )
                        matches.append(match)
                
                group = SimilarityGroup(
                    files=duplicate_files,
                    similarity_type=SimilarityType.EXACT,
                    confidence=MatchConfidence.VERY_HIGH,
                    representative_file=duplicate_files[0],
                    matches=matches
                )
                groups.append(group)
        
        return groups
    
    def _find_similar_names(self, files: List[DownloadedFile], 
                           progress: Progress, task) -> List[SimilarityGroup]:
        """Find files with similar names."""
        groups = []
        processed = set()
        
        for i, file1 in enumerate(files):
            if str(file1.file_path) in processed:
                continue
            
            similar_files = [file1]
            name1 = self._normalize_filename(file1.file_path.stem)
            
            for file2 in files[i+1:]:
                if str(file2.file_path) in processed:
                    continue
                
                name2 = self._normalize_filename(file2.file_path.stem)
                similarity = self._calculate_string_similarity(name1, name2)
                
                if similarity >= self.name_similarity_threshold:
                    similar_files.append(file2)
                    processed.add(str(file2.file_path))
            
            progress.update(task, advance=0.2)
            
            if len(similar_files) > 1:
                # Create matches
                matches = []
                for j, f1 in enumerate(similar_files):
                    for f2 in similar_files[j+1:]:
                        n1 = self._normalize_filename(f1.file_path.stem)
                        n2 = self._normalize_filename(f2.file_path.stem)
                        score = self._calculate_string_similarity(n1, n2)
                        
                        confidence = self._score_to_confidence(score)
                        
                        match = SimilarityMatch(
                            file1=f1,
                            file2=f2,
                            similarity_type=SimilarityType.SIMILAR_NAME,
                            confidence=confidence,
                            similarity_score=score,
                            details={"name_similarity": score}
                        )
                        matches.append(match)
                
                # Determine group confidence
                avg_confidence = sum(m.similarity_score for m in matches) / len(matches)
                group_confidence = self._score_to_confidence(avg_confidence)
                
                group = SimilarityGroup(
                    files=similar_files,
                    similarity_type=SimilarityType.SIMILAR_NAME,
                    confidence=group_confidence,
                    representative_file=similar_files[0],
                    matches=matches
                )
                groups.append(group)
            
            processed.add(str(file1.file_path))
        
        return groups
    
    def _find_similar_sizes(self, files: List[DownloadedFile], 
                           progress: Progress, task) -> List[SimilarityGroup]:
        """Find files with similar sizes."""
        groups = []
        processed = set()
        
        # Sort files by size for efficient comparison
        sorted_files = sorted(files, key=lambda f: f.file_size)
        
        for i, file1 in enumerate(sorted_files):
            if str(file1.file_path) in processed:
                continue
            
            similar_files = [file1]
            
            # Check nearby files in the sorted list
            for j in range(max(0, i-10), min(len(sorted_files), i+11)):
                if j == i:
                    continue
                
                file2 = sorted_files[j]
                if str(file2.file_path) in processed:
                    continue
                
                size_similarity = self._calculate_size_similarity(file1.file_size, file2.file_size)
                
                if size_similarity >= self.size_similarity_threshold:
                    similar_files.append(file2)
                    processed.add(str(file2.file_path))
            
            progress.update(task, advance=0.2)
            
            if len(similar_files) > 1:
                # Create matches
                matches = []
                for j, f1 in enumerate(similar_files):
                    for f2 in similar_files[j+1:]:
                        score = self._calculate_size_similarity(f1.file_size, f2.file_size)
                        confidence = self._score_to_confidence(score)
                        
                        match = SimilarityMatch(
                            file1=f1,
                            file2=f2,
                            similarity_type=SimilarityType.SIMILAR_SIZE,
                            confidence=confidence,
                            similarity_score=score,
                            details={"size_similarity": score}
                        )
                        matches.append(match)
                
                # Determine group confidence
                avg_confidence = sum(m.similarity_score for m in matches) / len(matches)
                group_confidence = self._score_to_confidence(avg_confidence)
                
                group = SimilarityGroup(
                    files=similar_files,
                    similarity_type=SimilarityType.SIMILAR_SIZE,
                    confidence=group_confidence,
                    representative_file=max(similar_files, key=lambda f: f.file_size),
                    matches=matches
                )
                groups.append(group)
            
            processed.add(str(file1.file_path))
        
        return groups
    
    def _find_same_content(self, files: List[DownloadedFile], 
                          progress: Progress, task) -> List[SimilarityGroup]:
        """Find files with same content but different quality."""
        groups = []
        processed = set()
        
        for i, file1 in enumerate(files):
            if str(file1.file_path) in processed:
                continue
            
            similar_files = [file1]
            
            for file2 in files[i+1:]:
                if str(file2.file_path) in processed:
                    continue
                
                # Check if files might be same content
                if self._might_be_same_content(file1, file2):
                    # Compare partial checksums for efficiency
                    if self._compare_partial_checksums(file1, file2):
                        similar_files.append(file2)
                        processed.add(str(file2.file_path))
            
            progress.update(task, advance=0.2)
            
            if len(similar_files) > 1:
                # Create matches
                matches = []
                for j, f1 in enumerate(similar_files):
                    for f2 in similar_files[j+1:]:
                        confidence = MatchConfidence.HIGH if self._compare_partial_checksums(f1, f2) else MatchConfidence.MEDIUM
                        score = 0.85 if confidence == MatchConfidence.HIGH else 0.65
                        
                        match = SimilarityMatch(
                            file1=f1,
                            file2=f2,
                            similarity_type=SimilarityType.SAME_CONTENT,
                            confidence=confidence,
                            similarity_score=score,
                            details={"content_match": True}
                        )
                        matches.append(match)
                
                group = SimilarityGroup(
                    files=similar_files,
                    similarity_type=SimilarityType.SAME_CONTENT,
                    confidence=MatchConfidence.HIGH,
                    representative_file=max(similar_files, key=lambda f: f.file_size),
                    matches=matches
                )
                groups.append(group)
            
            processed.add(str(file1.file_path))
        
        return groups
    
    def _find_duplicate_media(self, files: List[DownloadedFile], 
                             progress: Progress, task) -> List[SimilarityGroup]:
        """Find duplicate episodes and movies."""
        groups = []
        
        # Group files by potential media type
        movies = []
        episodes = []
        
        for file in files:
            if self._is_likely_movie(file):
                movies.append(file)
            elif self._is_likely_episode(file):
                episodes.append(file)
        
        # Find duplicate movies
        movie_groups = self._find_duplicate_movies(movies)
        groups.extend(movie_groups)
        
        # Find duplicate episodes
        episode_groups = self._find_duplicate_episodes(episodes)
        groups.extend(episode_groups)
        
        progress.update(task, advance=0.2)
        
        return groups
    
    def _find_duplicate_movies(self, movies: List[DownloadedFile]) -> List[SimilarityGroup]:
        """Find duplicate movies."""
        groups = []
        processed = set()
        
        for i, movie1 in enumerate(movies):
            if str(movie1.file_path) in processed:
                continue
            
            movie_title1 = self._extract_movie_title(movie1.file_path.stem)
            if not movie_title1:
                continue
            
            similar_movies = [movie1]
            
            for movie2 in movies[i+1:]:
                if str(movie2.file_path) in processed:
                    continue
                
                movie_title2 = self._extract_movie_title(movie2.file_path.stem)
                if not movie_title2:
                    continue
                
                # Compare movie titles
                title_similarity = self._calculate_string_similarity(movie_title1, movie_title2)
                
                if title_similarity >= 0.9:  # High threshold for movie titles
                    similar_movies.append(movie2)
                    processed.add(str(movie2.file_path))
            
            if len(similar_movies) > 1:
                # Create matches
                matches = []
                for j, m1 in enumerate(similar_movies):
                    for m2 in similar_movies[j+1:]:
                        t1 = self._extract_movie_title(m1.file_path.stem)
                        t2 = self._extract_movie_title(m2.file_path.stem)
                        score = self._calculate_string_similarity(t1, t2)
                        confidence = self._score_to_confidence(score)
                        
                        match = SimilarityMatch(
                            file1=m1,
                            file2=m2,
                            similarity_type=SimilarityType.DUPLICATE_MOVIE,
                            confidence=confidence,
                            similarity_score=score,
                            details={"movie_title_similarity": score}
                        )
                        matches.append(match)
                
                group = SimilarityGroup(
                    files=similar_movies,
                    similarity_type=SimilarityType.DUPLICATE_MOVIE,
                    confidence=MatchConfidence.HIGH,
                    representative_file=max(similar_movies, key=lambda f: f.file_size),
                    matches=matches
                )
                groups.append(group)
            
            processed.add(str(movie1.file_path))
        
        return groups
    
    def _find_duplicate_episodes(self, episodes: List[DownloadedFile]) -> List[SimilarityGroup]:
        """Find duplicate episodes."""
        groups = []
        processed = set()
        
        for i, episode1 in enumerate(episodes):
            if str(episode1.file_path) in processed:
                continue
            
            episode_info1 = self._extract_episode_info(episode1.file_path.stem)
            if not episode_info1:
                continue
            
            similar_episodes = [episode1]
            
            for episode2 in episodes[i+1:]:
                if str(episode2.file_path) in processed:
                    continue
                
                episode_info2 = self._extract_episode_info(episode2.file_path.stem)
                if not episode_info2:
                    continue
                
                # Compare episode info
                if self._episodes_match(episode_info1, episode_info2):
                    similar_episodes.append(episode2)
                    processed.add(str(episode2.file_path))
            
            if len(similar_episodes) > 1:
                # Create matches
                matches = []
                for j, e1 in enumerate(similar_episodes):
                    for e2 in similar_episodes[j+1:]:
                        match = SimilarityMatch(
                            file1=e1,
                            file2=e2,
                            similarity_type=SimilarityType.DUPLICATE_EPISODE,
                            confidence=MatchConfidence.HIGH,
                            similarity_score=0.9,
                            details={"episode_match": True}
                        )
                        matches.append(match)
                
                group = SimilarityGroup(
                    files=similar_episodes,
                    similarity_type=SimilarityType.DUPLICATE_EPISODE,
                    confidence=MatchConfidence.HIGH,
                    representative_file=max(similar_episodes, key=lambda f: f.file_size),
                    matches=matches
                )
                groups.append(group)
            
            processed.add(str(episode1.file_path))
        
        return groups
    
    def _deduplicate_groups(self, groups: List[SimilarityGroup]) -> List[SimilarityGroup]:
        """Remove overlapping groups and merge similar ones."""
        if not groups:
            return groups
        
        # Sort groups by confidence and number of files
        groups.sort(key=lambda g: (g.confidence.value, len(g.files)), reverse=True)
        
        # Track files that have been assigned to groups
        assigned_files = set()
        deduplicated_groups = []
        
        for group in groups:
            # Check if any files in this group are already assigned
            group_files = [f for f in group.files if str(f.file_path) not in assigned_files]
            
            if len(group_files) > 1:
                # Update the group with remaining files
                group.files = group_files
                deduplicated_groups.append(group)
                
                # Mark files as assigned
                for file in group_files:
                    assigned_files.add(str(file.file_path))
        
        return deduplicated_groups
    
    def _get_file_checksum(self, file_path: Path) -> Optional[str]:
        """Get file checksum with caching."""
        cache_key = f"{file_path}:{file_path.stat().st_size}"
        
        if cache_key in self.checksum_cache:
            return self.checksum_cache[cache_key]
        
        try:
            checksum = self._calculate_checksum(file_path)
            self.checksum_cache[cache_key] = checksum
            return checksum
        except Exception:
            return None
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file."""
        hash_func = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            chunk_size = 8192
            while chunk := f.read(chunk_size):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def _calculate_partial_checksum(self, file_path: Path) -> str:
        """Calculate checksum of first part of file for efficiency."""
        hash_func = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            data = f.read(self.partial_checksum_size)
            hash_func.update(data)
        
        return hash_func.hexdigest()
    
    def _normalize_filename(self, filename: str) -> str:
        """Normalize filename for comparison."""
        # Remove common patterns
        filename = re.sub(r'\b\d{4}\b', '', filename)  # Remove years
        filename = re.sub(r'\b(1080p|720p|480p|4K|UHD|HDR)\b', '', filename, flags=re.IGNORECASE)
        filename = re.sub(r'\b(x264|x265|HEVC|H264|H265)\b', '', filename, flags=re.IGNORECASE)
        filename = re.sub(r'\b(BluRay|BRRip|DVDRip|WEBRip|HDTV)\b', '', filename, flags=re.IGNORECASE)
        filename = re.sub(r'[\[\](){}]', '', filename)  # Remove brackets
        filename = re.sub(r'[._-]', ' ', filename)  # Replace separators with spaces
        filename = re.sub(r'\s+', ' ', filename)  # Normalize whitespace
        
        return filename.strip().lower()
    
    def _calculate_string_similarity(self, str1: str, str2: str) -> float:
        """Calculate similarity between two strings."""
        return difflib.SequenceMatcher(None, str1, str2).ratio()
    
    def _calculate_size_similarity(self, size1: int, size2: int) -> float:
        """Calculate similarity between two file sizes."""
        if size1 == 0 or size2 == 0:
            return 0.0
        
        smaller = min(size1, size2)
        larger = max(size1, size2)
        
        return smaller / larger
    
    def _score_to_confidence(self, score: float) -> MatchConfidence:
        """Convert similarity score to confidence level."""
        if score >= 0.95:
            return MatchConfidence.VERY_HIGH
        elif score >= 0.8:
            return MatchConfidence.HIGH
        elif score >= 0.6:
            return MatchConfidence.MEDIUM
        elif score >= 0.4:
            return MatchConfidence.LOW
        else:
            return MatchConfidence.VERY_LOW
    
    def _might_be_same_content(self, file1: DownloadedFile, file2: DownloadedFile) -> bool:
        """Check if two files might be the same content."""
        # Check if filenames are similar
        name1 = self._normalize_filename(file1.file_path.stem)
        name2 = self._normalize_filename(file2.file_path.stem)
        name_similarity = self._calculate_string_similarity(name1, name2)
        
        # Check if sizes are reasonable for same content
        size_ratio = self._calculate_size_similarity(file1.file_size, file2.file_size)
        
        return name_similarity > 0.7 and size_ratio > 0.3
    
    def _compare_partial_checksums(self, file1: DownloadedFile, file2: DownloadedFile) -> bool:
        """Compare partial checksums for efficiency."""
        try:
            checksum1 = self._calculate_partial_checksum(file1.file_path)
            checksum2 = self._calculate_partial_checksum(file2.file_path)
            return checksum1 == checksum2
        except Exception:
            return False
    
    def _is_likely_movie(self, file: DownloadedFile) -> bool:
        """Check if file is likely a movie."""
        filename = file.file_path.stem.lower()
        
        # Look for movie indicators
        movie_indicators = [
            r'\b\d{4}\b',  # Year
            r'\b(bluray|brrip|dvdrip|webrip)\b',  # Release types
            r'\b(1080p|720p|480p|4k|uhd)\b',  # Quality indicators
        ]
        
        for pattern in movie_indicators:
            if re.search(pattern, filename):
                return True
        
        return False
    
    def _is_likely_episode(self, file: DownloadedFile) -> bool:
        """Check if file is likely a TV episode."""
        filename = file.file_path.stem.lower()
        
        # Look for episode indicators
        episode_patterns = [
            r's\d+e\d+',  # S01E01
            r'season\s*\d+',  # Season 1
            r'episode\s*\d+',  # Episode 1
            r'\b\d+x\d+\b',  # 1x01
        ]
        
        for pattern in episode_patterns:
            if re.search(pattern, filename):
                return True
        
        return False
    
    def _extract_movie_title(self, filename: str) -> Optional[str]:
        """Extract movie title from filename."""
        # Remove year and quality indicators
        title = re.sub(r'\b\d{4}\b.*', '', filename)
        title = re.sub(r'\b(1080p|720p|480p|4k|uhd).*', '', title, flags=re.IGNORECASE)
        title = re.sub(r'[._-]', ' ', title)
        title = re.sub(r'\s+', ' ', title)
        
        return title.strip() if title.strip() else None
    
    def _extract_episode_info(self, filename: str) -> Optional[Dict[str, Any]]:
        """Extract episode information from filename."""
        # Try different episode patterns
        patterns = [
            r'(.+?)\s*s(\d+)e(\d+)',  # Show S01E01
            r'(.+?)\s*season\s*(\d+)\s*episode\s*(\d+)',  # Show Season 1 Episode 1
            r'(.+?)\s*(\d+)x(\d+)',  # Show 1x01
        ]
        
        for pattern in patterns:
            match = re.search(pattern, filename, re.IGNORECASE)
            if match:
                return {
                    'show': match.group(1).strip(),
                    'season': int(match.group(2)),
                    'episode': int(match.group(3))
                }
        
        return None
    
    def _episodes_match(self, info1: Dict[str, Any], info2: Dict[str, Any]) -> bool:
        """Check if two episode info dictionaries match."""
        # Compare show names
        show1 = self._normalize_filename(info1['show'])
        show2 = self._normalize_filename(info2['show'])
        show_similarity = self._calculate_string_similarity(show1, show2)
        
        # Must have same season and episode
        same_episode = (info1['season'] == info2['season'] and 
                       info1['episode'] == info2['episode'])
        
        return show_similarity > 0.8 and same_episode
    
    def show_similarity_analysis(self, library: MediaLibrary):
        """Show detailed similarity analysis."""
        groups = self.find_advanced_duplicates(library)
        
        if not groups:
            self.console.print("✅ No similar files found!", style="green")
            return
        
        self.console.print()
        self.console.print(f"🔍 Advanced Duplicate Analysis", style="bold blue")
        self.console.print(f"Found {len(groups)} similarity groups")
        self.console.print()
        
        # Show summary by type
        type_summary = defaultdict(int)
        for group in groups:
            type_summary[group.similarity_type] += 1
        
        self.console.print("📊 Summary by Type:")
        for sim_type, count in type_summary.items():
            icon = self._get_similarity_icon(sim_type)
            self.console.print(f"  {icon} {sim_type.value.replace('_', ' ').title()}: {count} groups")
        
        self.console.print()
        
        # Show detailed groups
        for i, group in enumerate(groups[:10]):  # Show first 10 groups
            self._show_similarity_group(group, i + 1)
        
        if len(groups) > 10:
            self.console.print(f"... and {len(groups) - 10} more groups")
        
        # Show total savings
        total_wasted = sum(g.wasted_space for g in groups)
        total_wasted_gb = total_wasted / (1024**3)
        self.console.print()
        self.console.print(f"💾 Total potential savings: {total_wasted_gb:.2f} GB")
    
    def _show_similarity_group(self, group: SimilarityGroup, group_number: int):
        """Show details of a similarity group."""
        icon = self._get_similarity_icon(group.similarity_type)
        confidence_color = self._get_confidence_color(group.confidence)
        
        self.console.print(f"{group_number}. {icon} {group.similarity_type.value.replace('_', ' ').title()}", 
                          style=f"bold {confidence_color}")
        self.console.print(f"   Files: {len(group.files)} • "
                          f"Total: {group.total_size_gb:.2f} GB • "
                          f"Wasted: {group.wasted_space_gb:.2f} GB")
        self.console.print(f"   Confidence: {group.confidence.value.replace('_', ' ').title()}")
        self.console.print(f"   Recommended: {group.get_recommended_action()}")
        
        # Show files in group
        for file in group.files:
            self.console.print(f"     • {file.display_name} ({file.size_gb:.2f} GB)")
        
        self.console.print()
    
    def _get_similarity_icon(self, sim_type: SimilarityType) -> str:
        """Get icon for similarity type."""
        icons = {
            SimilarityType.EXACT: "🔗",
            SimilarityType.SIMILAR_NAME: "📝",
            SimilarityType.SIMILAR_SIZE: "📏",
            SimilarityType.SAME_CONTENT: "🎬",
            SimilarityType.DUPLICATE_EPISODE: "📺",
            SimilarityType.DUPLICATE_MOVIE: "🎭"
        }
        return icons.get(sim_type, "❓")
    
    def _get_confidence_color(self, confidence: MatchConfidence) -> str:
        """Get color for confidence level."""
        colors = {
            MatchConfidence.VERY_HIGH: "green",
            MatchConfidence.HIGH: "green",
            MatchConfidence.MEDIUM: "yellow",
            MatchConfidence.LOW: "red",
            MatchConfidence.VERY_LOW: "dim"
        }
        return colors.get(confidence, "white")
    
    def export_similarity_report(self, library: MediaLibrary, output_file: Path):
        """Export similarity analysis report to JSON."""
        groups = self.find_advanced_duplicates(library)
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'total_groups': len(groups),
            'total_potential_savings_gb': sum(g.wasted_space for g in groups) / (1024**3),
            'groups': [
                {
                    'similarity_type': group.similarity_type.value,
                    'confidence': group.confidence.value,
                    'file_count': len(group.files),
                    'total_size_gb': group.total_size_gb,
                    'wasted_space_gb': group.wasted_space_gb,
                    'recommended_action': group.get_recommended_action(),
                    'files': [
                        {
                            'path': str(file.file_path),
                            'name': file.display_name,
                            'size_gb': file.size_gb
                        }
                        for file in group.files
                    ]
                }
                for group in groups
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.console.print(f"✅ Similarity report exported to: {output_file}") 