"""
Smart Organization Module for Automatic File Structure Optimization

This module provides intelligent organization of downloaded media files with
automatic folder structure optimization, smart naming, and efficient organization.
"""

import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
import shutil

from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from rich.prompt import Confirm, Prompt
from rich.panel import Panel
from rich.text import Text

from .downloaded import DownloadedFile, DownloadedMediaManager
from .datasets import MediaLibrary
from .file_operations import FileOperationsManager


class OrganizationStrategy(Enum):
    """Organization strategies for file structure."""
    BY_TYPE = "by_type"                    # Movies/TV Shows
    BY_GENRE = "by_genre"                  # Action/Comedy/Drama
    BY_YEAR = "by_year"                    # 2023/2024
    BY_QUALITY = "by_quality"              # 1080p/720p/4K
    BY_SIZE = "by_size"                    # Large/Medium/Small
    BY_SERIES = "by_series"                # TV Series organization
    CUSTOM = "custom"                      # User-defined structure


class OrganizationPriority(Enum):
    """Priority levels for organization operations."""
    HIGH = "high"      # Immediate organization needed
    MEDIUM = "medium"  # Should be organized
    LOW = "low"        # Optional organization
    NONE = "none"      # No organization needed


@dataclass
class OrganizationRule:
    """Rule for organizing files."""
    name: str
    description: str
    pattern: str  # Regex pattern for matching files
    target_structure: str  # Target folder structure
    priority: OrganizationPriority = OrganizationPriority.MEDIUM
    enabled: bool = True
    
    def matches(self, file: DownloadedFile) -> bool:
        """Check if rule matches the file."""
        return re.search(self.pattern, str(file.file_path), re.IGNORECASE) is not None


@dataclass
class OrganizationPlan:
    """Plan for organizing files."""
    file: DownloadedFile
    current_path: Path
    target_path: Path
    rule: OrganizationRule
    reason: str
    estimated_time: float = 0.0  # seconds
    
    @property
    def needs_move(self) -> bool:
        """Check if file needs to be moved."""
        return self.current_path != self.target_path
    
    @property
    def directory_change(self) -> bool:
        """Check if directory changes."""
        return self.current_path.parent != self.target_path.parent


@dataclass
class OrganizationResult:
    """Result of organization operation."""
    plan: OrganizationPlan
    success: bool
    error_message: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
    @property
    def duration(self) -> float:
        """Duration of operation in seconds."""
        if self.start_time and self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0


class SmartOrganizer:
    """Smart file organization system."""
    
    def __init__(self, console: Console, manager: DownloadedMediaManager, 
                 file_operations: FileOperationsManager):
        self.console = console
        self.manager = manager
        self.file_operations = file_operations
        
        # Default organization rules
        self.rules = self._create_default_rules()
        
        # Configuration
        self.dry_run = False
        self.backup_before_move = True
        self.create_missing_directories = True
        self.skip_existing_files = True
        
    def _create_default_rules(self) -> List[OrganizationRule]:
        """Create default organization rules."""
        rules = []
        
        # Movie organization rules
        rules.append(OrganizationRule(
            name="Movies by Year",
            description="Organize movies by release year",
            pattern=r'.*\b(\d{4})\b.*\.(mp4|mkv|avi|mov)$',
            target_structure="Movies/{year}/{title}",
            priority=OrganizationPriority.HIGH
        ))
        
        rules.append(OrganizationRule(
            name="Movies by Quality",
            description="Organize movies by video quality",
            pattern=r'.*\b(1080p|720p|4K|UHD|HDR)\b.*\.(mp4|mkv|avi|mov)$',
            target_structure="Movies/{quality}/{title}",
            priority=OrganizationPriority.MEDIUM
        ))
        
        # TV Show organization rules
        rules.append(OrganizationRule(
            name="TV Shows by Series",
            description="Organize TV episodes by series and season",
            pattern=r'.*[Ss](\d+)[Ee](\d+).*\.(mp4|mkv|avi|mov)$',
            target_structure="TV Shows/{series}/Season {season}/{episode}",
            priority=OrganizationPriority.HIGH
        ))
        
        rules.append(OrganizationRule(
            name="TV Shows Alternative Format",
            description="Organize TV episodes in alternative format",
            pattern=r'.*(\d+)x(\d+).*\.(mp4|mkv|avi|mov)$',
            target_structure="TV Shows/{series}/Season {season}/{episode}",
            priority=OrganizationPriority.HIGH
        ))
        
        # Quality-based organization
        rules.append(OrganizationRule(
            name="4K Content",
            description="Separate 4K/UHD content",
            pattern=r'.*\b(4K|UHD|2160p)\b.*\.(mp4|mkv|avi|mov)$',
            target_structure="4K/{type}/{title}",
            priority=OrganizationPriority.MEDIUM
        ))
        
        # Size-based organization
        rules.append(OrganizationRule(
            name="Large Files",
            description="Organize files larger than 5GB",
            pattern=r'.*\.(mp4|mkv|avi|mov)$',
            target_structure="Large Files/{type}/{title}",
            priority=OrganizationPriority.LOW
        ))
        
        return rules
    
    def analyze_organization(self, library: MediaLibrary) -> List[OrganizationPlan]:
        """Analyze current organization and create improvement plans."""
        summary = self.manager.get_summary(library)
        all_files = summary.movies + summary.episodes + summary.orphaned
        
        if not all_files:
            return []
        
        self.console.print("📁 Analyzing File Organization", style="bold blue")
        self.console.print(f"Analyzing {len(all_files)} files...")
        
        plans = []
        
        with Progress(console=self.console) as progress:
            task = progress.add_task("Analyzing organization...", total=len(all_files))
            
            for file in all_files:
                plan = self._create_organization_plan(file)
                if plan and plan.needs_move:
                    plans.append(plan)
                
                progress.update(task, advance=1)
        
        # Sort plans by priority
        plans.sort(key=lambda p: (p.rule.priority.value, p.file.file_size), reverse=True)
        
        return plans
    
    def _create_organization_plan(self, file: DownloadedFile) -> Optional[OrganizationPlan]:
        """Create organization plan for a file."""
        # Find the best matching rule
        best_rule = None
        best_priority = None
        
        for rule in self.rules:
            if rule.enabled and rule.matches(file):
                if best_rule is None or rule.priority.value > best_priority:
                    best_rule = rule
                    best_priority = rule.priority.value
        
        if not best_rule:
            return None
        
        # Generate target path
        target_path = self._generate_target_path(file, best_rule)
        
        if target_path == file.file_path:
            return None  # Already in correct location
        
        # Create plan
        plan = OrganizationPlan(
            file=file,
            current_path=file.file_path,
            target_path=target_path,
            rule=best_rule,
            reason=f"Applying rule: {best_rule.name}",
            estimated_time=self._estimate_move_time(file)
        )
        
        return plan
    
    def _generate_target_path(self, file: DownloadedFile, rule: OrganizationRule) -> Path:
        """Generate target path based on rule."""
        # Extract file information
        file_info = self._extract_file_info(file)
        
        # Apply rule template
        target_structure = rule.target_structure
        
        # Replace placeholders
        replacements = {
            '{title}': file_info.get('title', file.file_path.stem),
            '{series}': file_info.get('series', 'Unknown Series'),
            '{season}': file_info.get('season', '01'),
            '{episode}': file_info.get('episode', file.file_path.stem),
            '{year}': file_info.get('year', 'Unknown Year'),
            '{quality}': file_info.get('quality', 'Standard'),
            '{type}': file_info.get('type', 'Other'),
            '{genre}': file_info.get('genre', 'Unknown'),
            '{size}': file_info.get('size_category', 'Medium')
        }
        
        for placeholder, value in replacements.items():
            target_structure = target_structure.replace(placeholder, str(value))
        
        # Create full path
        base_dir = file.file_path.parent.parent  # Go up to base directory
        target_path = base_dir / target_structure
        
        # Ensure proper file extension
        if not target_path.suffix:
            target_path = target_path.with_suffix(file.file_path.suffix)
        
        return target_path
    
    def _extract_file_info(self, file: DownloadedFile) -> Dict[str, Any]:
        """Extract information from file for organization."""
        filename = file.file_path.stem
        info = {}
        
        # Extract title (clean up filename)
        title = re.sub(r'\b\d{4}\b', '', filename)  # Remove year
        title = re.sub(r'\b(1080p|720p|480p|4K|UHD|HDR)\b', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\b(x264|x265|HEVC|H264|H265)\b', '', title, flags=re.IGNORECASE)
        title = re.sub(r'\b(BluRay|BRRip|DVDRip|WEBRip|HDTV)\b', '', title, flags=re.IGNORECASE)
        title = re.sub(r'[\[\](){}]', '', title)
        title = re.sub(r'[._-]', ' ', title)
        title = re.sub(r'\s+', ' ', title).strip()
        info['title'] = title
        
        # Extract year
        year_match = re.search(r'\b(\d{4})\b', filename)
        if year_match:
            info['year'] = year_match.group(1)
        
        # Extract quality
        quality_match = re.search(r'\b(1080p|720p|480p|4K|UHD|HDR|2160p)\b', filename, re.IGNORECASE)
        if quality_match:
            info['quality'] = quality_match.group(1)
        
        # Extract TV series info
        series_match = re.search(r'(.+?)\s*[Ss](\d+)[Ee](\d+)', filename)
        if series_match:
            info['series'] = series_match.group(1).strip()
            info['season'] = f"{int(series_match.group(2)):02d}"
            info['episode'] = f"S{int(series_match.group(2)):02d}E{int(series_match.group(3)):02d}"
            info['type'] = 'TV Shows'
        else:
            # Try alternative format
            alt_match = re.search(r'(.+?)\s*(\d+)x(\d+)', filename)
            if alt_match:
                info['series'] = alt_match.group(1).strip()
                info['season'] = f"{int(alt_match.group(2)):02d}"
                info['episode'] = f"{int(alt_match.group(2)):02d}x{int(alt_match.group(3)):02d}"
                info['type'] = 'TV Shows'
            else:
                info['type'] = 'Movies'
        
        # Size category
        size_gb = file.file_size / (1024**3)
        if size_gb > 5:
            info['size_category'] = 'Large'
        elif size_gb > 2:
            info['size_category'] = 'Medium'
        else:
            info['size_category'] = 'Small'
        
        return info
    
    def _estimate_move_time(self, file: DownloadedFile) -> float:
        """Estimate time to move file."""
        # Rough estimate: 100 MB/s for local moves
        size_gb = file.file_size / (1024**3)
        return size_gb * 10  # 10 seconds per GB
    
    def execute_organization_plans(self, plans: List[OrganizationPlan]) -> List[OrganizationResult]:
        """Execute organization plans."""
        if not plans:
            return []
        
        results = []
        
        self.console.print()
        self.console.print(f"📁 Executing Organization Plans", style="bold green")
        self.console.print(f"Moving {len(plans)} files...")
        
        if self.dry_run:
            self.console.print("🔍 DRY RUN MODE - No files will be moved", style="yellow")
        
        self.console.print()
        
        with Progress(console=self.console) as progress:
            task = progress.add_task("Organizing files...", total=len(plans))
            
            for plan in plans:
                result = self._execute_single_plan(plan)
                results.append(result)
                
                # Show progress
                if result.success:
                    progress.console.print(f"✅ {plan.file.display_name}")
                else:
                    progress.console.print(f"❌ {plan.file.display_name}: {result.error_message}")
                
                progress.update(task, advance=1)
        
        # Show summary
        self._show_organization_summary(results)
        
        return results
    
    def _execute_single_plan(self, plan: OrganizationPlan) -> OrganizationResult:
        """Execute a single organization plan."""
        result = OrganizationResult(plan=plan, success=False, start_time=datetime.now())
        
        try:
            if self.dry_run:
                # Simulate the move
                result.success = True
                result.end_time = datetime.now()
                return result
            
            # Create target directory
            if self.create_missing_directories:
                plan.target_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Check if target exists
            if plan.target_path.exists() and self.skip_existing_files:
                result.error_message = "Target file already exists"
                result.end_time = datetime.now()
                return result
            
            # Create backup if needed
            backup_path = None
            if self.backup_before_move and plan.file.file_path.exists():
                backup_path = plan.file.file_path.with_suffix(f"{plan.file.file_path.suffix}.backup")
                shutil.copy2(plan.file.file_path, backup_path)
            
            # Move the file
            shutil.move(str(plan.file.file_path), str(plan.target_path))
            
            # Update file object
            plan.file.file_path = plan.target_path
            
            # Remove backup if successful
            if backup_path and backup_path.exists():
                backup_path.unlink()
            
            result.success = True
            
        except Exception as e:
            result.error_message = str(e)
            # Try to restore backup if move failed
            if backup_path and backup_path.exists():
                try:
                    shutil.move(str(backup_path), str(plan.file.file_path))
                except:
                    pass
        
        finally:
            result.end_time = datetime.now()
        
        return result
    
    def _show_organization_summary(self, results: List[OrganizationResult]):
        """Show summary of organization results."""
        if not results:
            return
        
        successful = sum(1 for r in results if r.success)
        failed = len(results) - successful
        total_time = sum(r.duration for r in results)
        
        self.console.print()
        self.console.print("📁 Organization Complete", style="bold green")
        self.console.print(f"✅ Successfully organized: {successful} files")
        self.console.print(f"❌ Failed: {failed} files")
        self.console.print(f"⏱️  Total time: {total_time:.1f} seconds")
        
        if failed > 0:
            self.console.print()
            self.console.print("❌ Failed Organization:")
            for result in results:
                if not result.success:
                    self.console.print(f"  • {result.plan.file.display_name}: {result.error_message}")
    
    def show_organization_preview(self, library: MediaLibrary):
        """Show preview of organization changes."""
        plans = self.analyze_organization(library)
        
        if not plans:
            self.console.print("✅ Files are already well-organized!", style="green")
            return
        
        self.console.print()
        self.console.print(f"📁 Organization Preview", style="bold blue")
        self.console.print(f"Found {len(plans)} files that could be better organized")
        self.console.print()
        
        # Group by rule
        by_rule = {}
        for plan in plans:
            rule_name = plan.rule.name
            if rule_name not in by_rule:
                by_rule[rule_name] = []
            by_rule[rule_name].append(plan)
        
        # Show grouped results
        for rule_name, rule_plans in by_rule.items():
            self.console.print(f"📋 {rule_name}: {len(rule_plans)} files", style="bold")
            
            for plan in rule_plans[:5]:  # Show first 5 files
                self.console.print(f"  📄 {plan.file.display_name}")
                self.console.print(f"    From: {plan.current_path}")
                self.console.print(f"    To:   {plan.target_path}")
                self.console.print()
            
            if len(rule_plans) > 5:
                self.console.print(f"  ... and {len(rule_plans) - 5} more files")
                self.console.print()
    
    def suggest_organization_improvements(self, library: MediaLibrary) -> List[str]:
        """Suggest improvements to organization."""
        plans = self.analyze_organization(library)
        suggestions = []
        
        if not plans:
            suggestions.append("✅ Your files are already well-organized!")
            return suggestions
        
        # Analyze organization issues
        by_priority = {}
        for plan in plans:
            priority = plan.rule.priority.value
            if priority not in by_priority:
                by_priority[priority] = []
            by_priority[priority].append(plan)
        
        # Generate suggestions
        if OrganizationPriority.HIGH.value in by_priority:
            high_priority = by_priority[OrganizationPriority.HIGH.value]
            suggestions.append(f"🔴 High Priority: {len(high_priority)} files need immediate organization")
        
        if OrganizationPriority.MEDIUM.value in by_priority:
            medium_priority = by_priority[OrganizationPriority.MEDIUM.value]
            suggestions.append(f"🟡 Medium Priority: {len(medium_priority)} files should be organized")
        
        if OrganizationPriority.LOW.value in by_priority:
            low_priority = by_priority[OrganizationPriority.LOW.value]
            suggestions.append(f"🟢 Low Priority: {len(low_priority)} files could benefit from organization")
        
        # Specific suggestions
        summary = self.manager.get_summary(library)
        
        # Check for scattered files
        all_files = summary.movies + summary.episodes
        directories = set(f.file_path.parent for f in all_files)
        
        if len(directories) > len(all_files) * 0.5:
            suggestions.append("📁 Consider consolidating files - many are in separate directories")
        
        # Check for mixed content
        mixed_dirs = []
        for directory in directories:
            files_in_dir = [f for f in all_files if f.file_path.parent == directory]
            if len(files_in_dir) > 1:
                types = set()
                for f in files_in_dir:
                    if self._is_likely_movie(f):
                        types.add('movie')
                    elif self._is_likely_episode(f):
                        types.add('episode')
                
                if len(types) > 1:
                    mixed_dirs.append(directory)
        
        if mixed_dirs:
            suggestions.append(f"🔀 {len(mixed_dirs)} directories contain mixed content (movies and TV shows)")
        
        return suggestions
    
    def _is_likely_movie(self, file: DownloadedFile) -> bool:
        """Check if file is likely a movie."""
        filename = file.file_path.stem.lower()
        
        # Look for movie indicators
        movie_patterns = [
            r'\b\d{4}\b',  # Year
            r'\b(bluray|brrip|dvdrip|webrip)\b',  # Release types
            r'\b(1080p|720p|480p|4k|uhd)\b',  # Quality
        ]
        
        for pattern in movie_patterns:
            if re.search(pattern, filename):
                return True
        
        return False
    
    def _is_likely_episode(self, file: DownloadedFile) -> bool:
        """Check if file is likely a TV episode."""
        filename = file.file_path.stem.lower()
        
        # Look for episode patterns
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
    
    def create_custom_rule(self, name: str, description: str, pattern: str, 
                          target_structure: str, priority: OrganizationPriority = OrganizationPriority.MEDIUM) -> OrganizationRule:
        """Create a custom organization rule."""
        rule = OrganizationRule(
            name=name,
            description=description,
            pattern=pattern,
            target_structure=target_structure,
            priority=priority
        )
        
        self.rules.append(rule)
        return rule
    
    def export_organization_plan(self, library: MediaLibrary, output_file: Path):
        """Export organization plan to JSON."""
        plans = self.analyze_organization(library)
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'total_files_to_organize': len(plans),
            'dry_run': self.dry_run,
            'rules': [
                {
                    'name': rule.name,
                    'description': rule.description,
                    'pattern': rule.pattern,
                    'target_structure': rule.target_structure,
                    'priority': rule.priority.value,
                    'enabled': rule.enabled
                }
                for rule in self.rules
            ],
            'plans': [
                {
                    'file_path': str(plan.file.file_path),
                    'current_path': str(plan.current_path),
                    'target_path': str(plan.target_path),
                    'rule_name': plan.rule.name,
                    'reason': plan.reason,
                    'estimated_time': plan.estimated_time,
                    'needs_move': plan.needs_move,
                    'directory_change': plan.directory_change
                }
                for plan in plans
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.console.print(f"✅ Organization plan exported to: {output_file}")
    
    def enable_rule(self, rule_name: str):
        """Enable an organization rule."""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                self.console.print(f"✅ Rule '{rule_name}' enabled")
                return
        
        self.console.print(f"❌ Rule '{rule_name}' not found")
    
    def disable_rule(self, rule_name: str):
        """Disable an organization rule."""
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                self.console.print(f"✅ Rule '{rule_name}' disabled")
                return
        
        self.console.print(f"❌ Rule '{rule_name}' not found")
    
    def show_rules(self):
        """Show all organization rules."""
        self.console.print()
        self.console.print("📋 Organization Rules", style="bold blue")
        self.console.print()
        
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Name", style="bold")
        table.add_column("Description")
        table.add_column("Priority", justify="center")
        table.add_column("Enabled", justify="center")
        
        for rule in self.rules:
            enabled_text = "✅" if rule.enabled else "❌"
            priority_color = {
                OrganizationPriority.HIGH: "red",
                OrganizationPriority.MEDIUM: "yellow",
                OrganizationPriority.LOW: "green"
            }.get(rule.priority, "white")
            
            table.add_row(
                rule.name,
                rule.description,
                Text(rule.priority.value.title(), style=priority_color),
                enabled_text
            )
        
        self.console.print(table) 