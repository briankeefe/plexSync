"""
Storage Analytics Module for Downloaded Media

This module provides comprehensive storage analytics including breakdown by type,
duplicate detection, storage optimization suggestions, and detailed reporting.
"""

import os
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from collections import defaultdict
import json

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.columns import Columns
from rich.progress import Progress
from rich.text import Text

from .downloaded import DownloadedFile, DownloadedMediaManager, DownloadedMediaSummary
from .datasets import MediaLibrary


@dataclass
class StorageBreakdown:
    """Detailed storage breakdown."""
    total_size: int = 0
    movie_size: int = 0
    episode_size: int = 0
    orphaned_size: int = 0
    
    movie_count: int = 0
    episode_count: int = 0
    orphaned_count: int = 0
    
    by_extension: Dict[str, int] = field(default_factory=dict)
    by_size_category: Dict[str, int] = field(default_factory=dict)
    by_date: Dict[str, int] = field(default_factory=dict)
    
    largest_files: List[DownloadedFile] = field(default_factory=list)
    smallest_files: List[DownloadedFile] = field(default_factory=list)
    
    @property
    def total_size_gb(self) -> float:
        return self.total_size / (1024**3)
    
    @property
    def movie_size_gb(self) -> float:
        return self.movie_size / (1024**3)
    
    @property
    def episode_size_gb(self) -> float:
        return self.episode_size / (1024**3)
    
    @property
    def orphaned_size_gb(self) -> float:
        return self.orphaned_size / (1024**3)


@dataclass
class DuplicateGroup:
    """Group of duplicate files."""
    checksum: str
    file_size: int
    files: List[DownloadedFile] = field(default_factory=list)
    
    @property
    def size_gb(self) -> float:
        return self.file_size / (1024**3)
    
    @property
    def wasted_space(self) -> int:
        """Space wasted by duplicates (total - 1 copy)."""
        return self.file_size * (len(self.files) - 1)
    
    @property
    def wasted_space_gb(self) -> float:
        return self.wasted_space / (1024**3)


@dataclass
class OptimizationSuggestion:
    """Storage optimization suggestion."""
    type: str
    description: str
    potential_savings: int
    file_count: int
    confidence: float  # 0.0 to 1.0
    files: List[DownloadedFile] = field(default_factory=list)
    
    @property
    def potential_savings_gb(self) -> float:
        return self.potential_savings / (1024**3)


class StorageAnalytics:
    """Comprehensive storage analytics for downloaded media."""
    
    def __init__(self, console: Console, manager: DownloadedMediaManager):
        self.console = console
        self.manager = manager
        self.checksum_cache: Dict[str, str] = {}
        
    def generate_storage_breakdown(self, library: MediaLibrary) -> StorageBreakdown:
        """Generate detailed storage breakdown."""
        summary = self.manager.get_summary(library)
        breakdown = StorageBreakdown()
        
        # Basic counts and sizes
        breakdown.movie_count = summary.movie_count
        breakdown.episode_count = summary.episode_count
        breakdown.orphaned_count = len(summary.orphaned)
        
        breakdown.movie_size = sum(f.file_size for f in summary.movies)
        breakdown.episode_size = sum(f.file_size for f in summary.episodes)
        breakdown.orphaned_size = sum(f.file_size for f in summary.orphaned)
        breakdown.total_size = breakdown.movie_size + breakdown.episode_size + breakdown.orphaned_size
        
        # Breakdown by file extension
        all_files = summary.movies + summary.episodes + summary.orphaned
        
        for file in all_files:
            ext = file.file_path.suffix.lower()
            if ext not in breakdown.by_extension:
                breakdown.by_extension[ext] = 0
            breakdown.by_extension[ext] += file.file_size
        
        # Breakdown by size category
        size_categories = {
            "Small (< 500 MB)": (0, 500 * 1024 * 1024),
            "Medium (500 MB - 2 GB)": (500 * 1024 * 1024, 2 * 1024 * 1024 * 1024),
            "Large (2 GB - 5 GB)": (2 * 1024 * 1024 * 1024, 5 * 1024 * 1024 * 1024),
            "Very Large (> 5 GB)": (5 * 1024 * 1024 * 1024, float('inf'))
        }
        
        for category, (min_size, max_size) in size_categories.items():
            breakdown.by_size_category[category] = sum(
                f.file_size for f in all_files
                if min_size <= f.file_size < max_size
            )
        
        # Breakdown by date (last 30 days)
        now = datetime.now()
        for days_ago in [1, 7, 30]:
            cutoff = now - timedelta(days=days_ago)
            label = f"Last {days_ago} day{'s' if days_ago > 1 else ''}"
            breakdown.by_date[label] = sum(
                f.file_size for f in all_files
                if f.download_date and f.download_date >= cutoff
            )
        
        # Largest and smallest files
        sorted_files = sorted(all_files, key=lambda f: f.file_size, reverse=True)
        breakdown.largest_files = sorted_files[:10]
        breakdown.smallest_files = sorted_files[-10:]
        
        return breakdown
    
    def find_duplicates(self, library: MediaLibrary, 
                       use_checksum: bool = True) -> List[DuplicateGroup]:
        """Find duplicate files based on size and optionally checksum."""
        summary = self.manager.get_summary(library)
        all_files = summary.movies + summary.episodes + summary.orphaned
        
        if not all_files:
            return []
        
        self.console.print("🔍 Scanning for duplicate files...")
        
        # Group by file size first (quick check)
        size_groups: Dict[int, List[DownloadedFile]] = defaultdict(list)
        for file in all_files:
            size_groups[file.file_size].append(file)
        
        # Filter to only sizes with multiple files
        potential_duplicates = {
            size: files for size, files in size_groups.items()
            if len(files) > 1
        }
        
        if not potential_duplicates:
            return []
        
        duplicate_groups = []
        
        if use_checksum:
            # Use checksum for accurate duplicate detection
            with Progress(console=self.console) as progress:
                task = progress.add_task("Calculating checksums...", 
                                       total=sum(len(files) for files in potential_duplicates.values()))
                
                for size, files in potential_duplicates.items():
                    # Group by checksum
                    checksum_groups: Dict[str, List[DownloadedFile]] = defaultdict(list)
                    
                    for file in files:
                        checksum = self._get_file_checksum(file.file_path)
                        if checksum:
                            checksum_groups[checksum].append(file)
                        progress.update(task, advance=1)
                    
                    # Create duplicate groups
                    for checksum, dup_files in checksum_groups.items():
                        if len(dup_files) > 1:
                            duplicate_groups.append(DuplicateGroup(
                                checksum=checksum,
                                file_size=size,
                                files=dup_files
                            ))
        else:
            # Use size-only detection (faster but less accurate)
            for size, files in potential_duplicates.items():
                if len(files) > 1:
                    duplicate_groups.append(DuplicateGroup(
                        checksum="size_only",
                        file_size=size,
                        files=files
                    ))
        
        # Sort by wasted space (largest first)
        duplicate_groups.sort(key=lambda g: g.wasted_space, reverse=True)
        
        return duplicate_groups
    
    def generate_optimization_suggestions(self, library: MediaLibrary) -> List[OptimizationSuggestion]:
        """Generate storage optimization suggestions."""
        suggestions = []
        
        # Find duplicates
        duplicates = self.find_duplicates(library, use_checksum=False)  # Fast check
        if duplicates:
            total_wasted = sum(g.wasted_space for g in duplicates)
            total_files = sum(len(g.files) - 1 for g in duplicates)  # Excess files
            
            suggestions.append(OptimizationSuggestion(
                type="duplicates",
                description=f"Remove {total_files} duplicate files",
                potential_savings=total_wasted,
                file_count=total_files,
                confidence=0.8,  # High confidence for size-based detection
                files=[f for g in duplicates for f in g.files[1:]]  # Keep first, remove rest
            ))
        
        # Find orphaned files
        summary = self.manager.get_summary(library)
        if summary.orphaned:
            orphaned_size = sum(f.file_size for f in summary.orphaned)
            suggestions.append(OptimizationSuggestion(
                type="orphaned",
                description=f"Remove {len(summary.orphaned)} orphaned files not in library",
                potential_savings=orphaned_size,
                file_count=len(summary.orphaned),
                confidence=0.9,  # Very high confidence
                files=summary.orphaned
            ))
        
        # Find partial/corrupted files
        partial_files = [f for f in summary.movies + summary.episodes 
                        if f.status.value in ["partial", "corrupted"]]
        if partial_files:
            partial_size = sum(f.file_size for f in partial_files)
            suggestions.append(OptimizationSuggestion(
                type="corrupted",
                description=f"Remove {len(partial_files)} partial/corrupted files",
                potential_savings=partial_size,
                file_count=len(partial_files),
                confidence=0.7,  # Medium-high confidence
                files=partial_files
            ))
        
        # Find very old files (downloaded > 6 months ago)
        six_months_ago = datetime.now() - timedelta(days=180)
        old_files = [
            f for f in summary.movies + summary.episodes
            if f.download_date and f.download_date < six_months_ago
        ]
        if old_files:
            old_size = sum(f.file_size for f in old_files)
            suggestions.append(OptimizationSuggestion(
                type="old_files",
                description=f"Archive {len(old_files)} files older than 6 months",
                potential_savings=old_size,
                file_count=len(old_files),
                confidence=0.3,  # Low confidence - user preference
                files=old_files
            ))
        
        # Sort by potential savings
        suggestions.sort(key=lambda s: s.potential_savings, reverse=True)
        
        return suggestions
    
    def show_storage_breakdown(self, library: MediaLibrary):
        """Display comprehensive storage breakdown."""
        breakdown = self.generate_storage_breakdown(library)
        
        self.console.clear()
        self.console.print()
        self.console.print("📊 Storage Analytics - Detailed Breakdown", style="bold blue")
        self.console.print()
        
        # Overview panel
        overview_text = f"""
📊 Total Storage: {breakdown.total_size_gb:.2f} GB
🎬 Movies: {breakdown.movie_count} files • {breakdown.movie_size_gb:.2f} GB
📺 Episodes: {breakdown.episode_count} files • {breakdown.episode_size_gb:.2f} GB
👻 Orphaned: {breakdown.orphaned_count} files • {breakdown.orphaned_size_gb:.2f} GB
"""
        
        self.console.print(Panel(overview_text.strip(), title="Storage Overview", 
                                title_align="left", border_style="blue"))
        
        # Breakdown by file type
        if breakdown.by_extension:
            self.console.print("\n📁 Breakdown by File Type:")
            
            ext_table = Table(show_header=True, header_style="bold blue")
            ext_table.add_column("Extension", justify="left")
            ext_table.add_column("Size", justify="right")
            ext_table.add_column("Percentage", justify="right")
            
            # Sort by size
            sorted_extensions = sorted(breakdown.by_extension.items(), 
                                     key=lambda x: x[1], reverse=True)
            
            for ext, size in sorted_extensions:
                size_gb = size / (1024**3)
                percentage = (size / breakdown.total_size) * 100 if breakdown.total_size > 0 else 0
                ext_table.add_row(
                    ext or "No extension",
                    f"{size_gb:.2f} GB",
                    f"{percentage:.1f}%"
                )
            
            self.console.print(ext_table)
        
        # Breakdown by size category
        if breakdown.by_size_category:
            self.console.print("\n📏 Breakdown by File Size:")
            
            size_table = Table(show_header=True, header_style="bold blue")
            size_table.add_column("Size Category", justify="left")
            size_table.add_column("Total Size", justify="right")
            size_table.add_column("Percentage", justify="right")
            
            for category, size in breakdown.by_size_category.items():
                if size > 0:
                    size_gb = size / (1024**3)
                    percentage = (size / breakdown.total_size) * 100 if breakdown.total_size > 0 else 0
                    size_table.add_row(
                        category,
                        f"{size_gb:.2f} GB",
                        f"{percentage:.1f}%"
                    )
            
            self.console.print(size_table)
        
        # Recent activity
        if breakdown.by_date:
            self.console.print("\n📅 Recent Download Activity:")
            
            date_table = Table(show_header=True, header_style="bold blue")
            date_table.add_column("Time Period", justify="left")
            date_table.add_column("Downloaded", justify="right")
            
            for period, size in breakdown.by_date.items():
                if size > 0:
                    size_gb = size / (1024**3)
                    date_table.add_row(period, f"{size_gb:.2f} GB")
            
            self.console.print(date_table)
        
        # Largest files
        if breakdown.largest_files:
            self.console.print("\n🏆 Largest Files:")
            
            large_table = Table(show_header=True, header_style="bold blue")
            large_table.add_column("File", style="dim")
            large_table.add_column("Size", justify="right")
            large_table.add_column("Type", justify="center")
            
            for file in breakdown.largest_files:
                file_type = "🎬 Movie" if file in breakdown.largest_files else "📺 Episode"
                large_table.add_row(
                    file.display_name,
                    f"{file.size_gb:.2f} GB",
                    file_type
                )
            
            self.console.print(large_table)
        
        self.console.print()
        input("Press Enter to continue...")
    
    def show_duplicate_analysis(self, library: MediaLibrary):
        """Display duplicate file analysis."""
        self.console.clear()
        self.console.print()
        self.console.print("🔍 Duplicate File Analysis", style="bold blue")
        self.console.print()
        
        duplicates = self.find_duplicates(library, use_checksum=True)
        
        if not duplicates:
            self.console.print("✅ No duplicate files found!", style="green")
            self.console.print("Your media library is well-organized with no duplicates.")
            self.console.print()
            input("Press Enter to continue...")
            return
        
        # Summary
        total_duplicates = len(duplicates)
        total_wasted = sum(g.wasted_space for g in duplicates)
        total_wasted_gb = total_wasted / (1024**3)
        
        self.console.print(f"Found {total_duplicates} sets of duplicate files")
        self.console.print(f"💾 Wasted space: {total_wasted_gb:.2f} GB")
        self.console.print()
        
        # Show duplicate groups
        self.console.print("🔍 Duplicate Groups:")
        
        dup_table = Table(show_header=True, header_style="bold blue")
        dup_table.add_column("File Name", style="dim")
        dup_table.add_column("Size", justify="right")
        dup_table.add_column("Copies", justify="center")
        dup_table.add_column("Wasted Space", justify="right")
        
        for group in duplicates[:15]:  # Show first 15 groups
            representative = group.files[0]  # Use first file as representative
            dup_table.add_row(
                representative.display_name,
                f"{group.size_gb:.2f} GB",
                str(len(group.files)),
                f"{group.wasted_space_gb:.2f} GB"
            )
        
        self.console.print(dup_table)
        
        if len(duplicates) > 15:
            self.console.print(f"... and {len(duplicates) - 15} more duplicate groups")
        
        self.console.print()
        input("Press Enter to continue...")
    
    def show_optimization_suggestions(self, library: MediaLibrary):
        """Display storage optimization suggestions."""
        self.console.clear()
        self.console.print()
        self.console.print("💡 Storage Optimization Suggestions", style="bold green")
        self.console.print()
        
        suggestions = self.generate_optimization_suggestions(library)
        
        if not suggestions:
            self.console.print("✅ Your storage is well-optimized!", style="green")
            self.console.print("No significant optimization opportunities found.")
            self.console.print()
            input("Press Enter to continue...")
            return
        
        # Calculate total potential savings
        total_savings = sum(s.potential_savings for s in suggestions)
        total_savings_gb = total_savings / (1024**3)
        
        self.console.print(f"💾 Total potential savings: {total_savings_gb:.2f} GB")
        self.console.print()
        
        # Show suggestions
        for i, suggestion in enumerate(suggestions, 1):
            # Color based on confidence
            if suggestion.confidence >= 0.8:
                style = "green"
            elif suggestion.confidence >= 0.5:
                style = "yellow"
            else:
                style = "dim"
            
            self.console.print(f"{i}. {suggestion.description}", style=style)
            self.console.print(f"   💾 Potential savings: {suggestion.potential_savings_gb:.2f} GB")
            self.console.print(f"   📊 Confidence: {suggestion.confidence:.0%}")
            self.console.print()
        
        self.console.print("💡 Suggestions are ordered by potential impact")
        self.console.print("🎯 Green = High confidence, Yellow = Medium confidence, Dim = Low confidence")
        self.console.print()
        input("Press Enter to continue...")
    
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
            # Read in chunks to handle large files
            chunk_size = 8192
            while chunk := f.read(chunk_size):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def export_analytics_report(self, library: MediaLibrary, output_file: Path):
        """Export comprehensive analytics report to JSON."""
        breakdown = self.generate_storage_breakdown(library)
        duplicates = self.find_duplicates(library, use_checksum=False)
        suggestions = self.generate_optimization_suggestions(library)
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "breakdown": {
                "total_size": breakdown.total_size,
                "total_size_gb": breakdown.total_size_gb,
                "movie_count": breakdown.movie_count,
                "episode_count": breakdown.episode_count,
                "orphaned_count": breakdown.orphaned_count,
                "movie_size_gb": breakdown.movie_size_gb,
                "episode_size_gb": breakdown.episode_size_gb,
                "orphaned_size_gb": breakdown.orphaned_size_gb,
                "by_extension": {k: v / (1024**3) for k, v in breakdown.by_extension.items()},
                "by_size_category": {k: v / (1024**3) for k, v in breakdown.by_size_category.items()},
                "by_date": {k: v / (1024**3) for k, v in breakdown.by_date.items()},
            },
            "duplicates": {
                "total_groups": len(duplicates),
                "total_wasted_gb": sum(g.wasted_space for g in duplicates) / (1024**3),
                "groups": [
                    {
                        "file_size_gb": g.size_gb,
                        "copy_count": len(g.files),
                        "wasted_space_gb": g.wasted_space_gb,
                        "files": [str(f.file_path) for f in g.files]
                    } for g in duplicates
                ]
            },
            "suggestions": [
                {
                    "type": s.type,
                    "description": s.description,
                    "potential_savings_gb": s.potential_savings_gb,
                    "file_count": s.file_count,
                    "confidence": s.confidence
                } for s in suggestions
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.console.print(f"✅ Analytics report exported to: {output_file}") 