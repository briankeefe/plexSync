"""
Usage Analytics Module for Intelligent Media Management

This module tracks usage patterns, access frequency, and provides intelligent
recommendations for media management based on user behavior.
"""

import os
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns

from .downloaded import DownloadedFile, DownloadedMediaManager
from .datasets import MediaLibrary


class AccessType(Enum):
    """Types of file access."""
    VIEWED = "viewed"         # File was opened/played
    ACCESSED = "accessed"     # File was accessed in file browser
    MANAGED = "managed"       # File was managed (moved, deleted, etc.)
    SYNCED = "synced"         # File was downloaded/synced


class RecommendationType(Enum):
    """Types of recommendations."""
    DELETE_UNUSED = "delete_unused"
    ARCHIVE_OLD = "archive_old"
    PRIORITIZE_POPULAR = "prioritize_popular"
    ORGANIZE_FREQUENT = "organize_frequent"
    CLEANUP_NEVER_ACCESSED = "cleanup_never_accessed"


@dataclass
class AccessRecord:
    """Record of file access."""
    file_path: str
    access_type: AccessType
    timestamp: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class UsageStats:
    """Usage statistics for a file."""
    file_path: str
    total_accesses: int = 0
    last_access: Optional[datetime] = None
    first_access: Optional[datetime] = None
    access_frequency: float = 0.0  # accesses per day
    days_since_last_access: float = 0.0
    view_count: int = 0
    management_count: int = 0
    
    @property
    def usage_score(self) -> float:
        """Calculate usage score (0-100)."""
        if self.total_accesses == 0:
            return 0.0
        
        # Base score from frequency
        frequency_score = min(self.access_frequency * 10, 50)
        
        # Recency bonus
        if self.days_since_last_access <= 7:
            recency_score = 30
        elif self.days_since_last_access <= 30:
            recency_score = 20
        elif self.days_since_last_access <= 90:
            recency_score = 10
        else:
            recency_score = 0
        
        # View bonus
        view_score = min(self.view_count * 5, 20)
        
        return min(frequency_score + recency_score + view_score, 100)
    
    @property
    def usage_category(self) -> str:
        """Get usage category."""
        score = self.usage_score
        if score >= 80:
            return "Very High"
        elif score >= 60:
            return "High"
        elif score >= 40:
            return "Medium"
        elif score >= 20:
            return "Low"
        else:
            return "Very Low"


@dataclass
class Recommendation:
    """Usage-based recommendation."""
    type: RecommendationType
    title: str
    description: str
    files: List[str] = field(default_factory=list)
    confidence: float = 0.0
    potential_savings_gb: float = 0.0
    
    @property
    def confidence_text(self) -> str:
        """Get confidence as text."""
        if self.confidence >= 0.9:
            return "Very High"
        elif self.confidence >= 0.7:
            return "High"
        elif self.confidence >= 0.5:
            return "Medium"
        else:
            return "Low"


class UsageAnalytics:
    """Analytics engine for media usage patterns."""
    
    def __init__(self, console: Console, manager: DownloadedMediaManager, 
                 database_path: Optional[Path] = None):
        self.console = console
        self.manager = manager
        
        # Database setup
        if database_path is None:
            database_path = Path.home() / ".plexsync" / "usage.db"
        
        self.database_path = database_path
        self._init_database()
        
        # Configuration
        self.track_file_system_access = True
        self.retention_days = 365  # Keep records for 1 year
        
    def _init_database(self):
        """Initialize the usage tracking database."""
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            
            # Create access records table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_records (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    file_path TEXT NOT NULL,
                    access_type TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    metadata TEXT
                )
            ''')
            
            # Create index for efficient queries
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_file_path ON access_records(file_path)
            ''')
            
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_timestamp ON access_records(timestamp)
            ''')
            
            conn.commit()
    
    def record_access(self, file: DownloadedFile, access_type: AccessType, 
                     metadata: Optional[Dict[str, Any]] = None):
        """Record file access."""
        if metadata is None:
            metadata = {}
        
        record = AccessRecord(
            file_path=str(file.file_path),
            access_type=access_type,
            timestamp=datetime.now(),
            metadata=metadata
        )
        
        self._store_access_record(record)
    
    def _store_access_record(self, record: AccessRecord):
        """Store access record in database."""
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO access_records (file_path, access_type, timestamp, metadata)
                VALUES (?, ?, ?, ?)
            ''', (
                record.file_path,
                record.access_type.value,
                record.timestamp.isoformat(),
                json.dumps(record.metadata)
            ))
            
            conn.commit()
    
    def get_usage_stats(self, file: DownloadedFile) -> UsageStats:
        """Get usage statistics for a file."""
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT access_type, timestamp FROM access_records 
                WHERE file_path = ? 
                ORDER BY timestamp
            ''', (str(file.file_path),))
            
            records = cursor.fetchall()
        
        if not records:
            return UsageStats(file_path=str(file.file_path))
        
        # Calculate statistics
        stats = UsageStats(file_path=str(file.file_path))
        stats.total_accesses = len(records)
        
        # Parse timestamps and calculate stats
        timestamps = []
        for access_type, timestamp_str in records:
            timestamp = datetime.fromisoformat(timestamp_str)
            timestamps.append(timestamp)
            
            if access_type == AccessType.VIEWED.value:
                stats.view_count += 1
            elif access_type == AccessType.MANAGED.value:
                stats.management_count += 1
        
        stats.first_access = min(timestamps)
        stats.last_access = max(timestamps)
        
        # Calculate frequency (accesses per day)
        if stats.first_access and stats.last_access:
            days_span = (stats.last_access - stats.first_access).days + 1
            stats.access_frequency = stats.total_accesses / days_span
        
        # Calculate days since last access
        if stats.last_access:
            stats.days_since_last_access = (datetime.now() - stats.last_access).days
        
        return stats
    
    def get_global_usage_stats(self, library: MediaLibrary) -> Dict[str, Any]:
        """Get global usage statistics."""
        summary = self.manager.get_summary(library)
        all_files = summary.movies + summary.episodes + summary.orphaned
        
        total_files = len(all_files)
        accessed_files = 0
        never_accessed = 0
        high_usage_files = 0
        
        total_accesses = 0
        file_stats = []
        
        for file in all_files:
            stats = self.get_usage_stats(file)
            file_stats.append(stats)
            
            if stats.total_accesses > 0:
                accessed_files += 1
                total_accesses += stats.total_accesses
                
                if stats.usage_score >= 60:
                    high_usage_files += 1
            else:
                never_accessed += 1
        
        # Calculate averages
        avg_accesses = total_accesses / total_files if total_files > 0 else 0
        access_rate = accessed_files / total_files if total_files > 0 else 0
        
        return {
            'total_files': total_files,
            'accessed_files': accessed_files,
            'never_accessed': never_accessed,
            'high_usage_files': high_usage_files,
            'total_accesses': total_accesses,
            'average_accesses_per_file': avg_accesses,
            'access_rate': access_rate,
            'file_stats': file_stats
        }
    
    def generate_recommendations(self, library: MediaLibrary) -> List[Recommendation]:
        """Generate usage-based recommendations."""
        global_stats = self.get_global_usage_stats(library)
        recommendations = []
        
        # Get file stats
        file_stats = global_stats['file_stats']
        
        # Find never accessed files older than 30 days
        never_accessed_files = []
        for stats in file_stats:
            if stats.total_accesses == 0:
                # Check file age
                file_path = Path(stats.file_path)
                if file_path.exists():
                    file_age = (datetime.now() - datetime.fromtimestamp(file_path.stat().st_mtime)).days
                    if file_age > 30:
                        never_accessed_files.append(stats.file_path)
        
        if never_accessed_files:
            # Calculate potential savings
            total_size = 0
            for file_path in never_accessed_files:
                path = Path(file_path)
                if path.exists():
                    total_size += path.stat().st_size
            
            recommendations.append(Recommendation(
                type=RecommendationType.CLEANUP_NEVER_ACCESSED,
                title="Remove Never-Accessed Files",
                description=f"Delete {len(never_accessed_files)} files that have never been accessed",
                files=never_accessed_files,
                confidence=0.8,
                potential_savings_gb=total_size / (1024**3)
            ))
        
        # Find rarely used files older than 90 days
        rarely_used_files = []
        for stats in file_stats:
            if (stats.total_accesses > 0 and 
                stats.usage_score < 20 and 
                stats.days_since_last_access > 90):
                rarely_used_files.append(stats.file_path)
        
        if rarely_used_files:
            total_size = 0
            for file_path in rarely_used_files:
                path = Path(file_path)
                if path.exists():
                    total_size += path.stat().st_size
            
            recommendations.append(Recommendation(
                type=RecommendationType.DELETE_UNUSED,
                title="Archive Rarely Used Files",
                description=f"Archive {len(rarely_used_files)} rarely used files",
                files=rarely_used_files,
                confidence=0.6,
                potential_savings_gb=total_size / (1024**3)
            ))
        
        # Find files accessed frequently but poorly organized
        frequently_accessed = []
        for stats in file_stats:
            if stats.usage_score >= 60:
                frequently_accessed.append(stats.file_path)
        
        if frequently_accessed:
            recommendations.append(Recommendation(
                type=RecommendationType.ORGANIZE_FREQUENT,
                title="Organize Frequently Accessed Files",
                description=f"Optimize organization for {len(frequently_accessed)} frequently used files",
                files=frequently_accessed,
                confidence=0.7,
                potential_savings_gb=0.0
            ))
        
        # Find very old files
        old_files = []
        cutoff_date = datetime.now() - timedelta(days=365)
        
        for stats in file_stats:
            if (stats.last_access and 
                stats.last_access < cutoff_date and 
                stats.usage_score < 40):
                old_files.append(stats.file_path)
        
        if old_files:
            total_size = 0
            for file_path in old_files:
                path = Path(file_path)
                if path.exists():
                    total_size += path.stat().st_size
            
            recommendations.append(Recommendation(
                type=RecommendationType.ARCHIVE_OLD,
                title="Archive Old Files",
                description=f"Archive {len(old_files)} files not accessed in over a year",
                files=old_files,
                confidence=0.5,
                potential_savings_gb=total_size / (1024**3)
            ))
        
        # Sort by confidence and potential savings
        recommendations.sort(key=lambda r: (r.confidence, r.potential_savings_gb), reverse=True)
        
        return recommendations
    
    def show_usage_dashboard(self, library: MediaLibrary):
        """Show comprehensive usage dashboard."""
        self.console.clear()
        self.console.print()
        self.console.print("📊 Usage Analytics Dashboard", style="bold blue")
        self.console.print()
        
        # Get global stats
        global_stats = self.get_global_usage_stats(library)
        
        # Overview panel
        overview = f"""
📊 Total Files: {global_stats['total_files']}
✅ Accessed Files: {global_stats['accessed_files']} ({global_stats['access_rate']:.1%})
❌ Never Accessed: {global_stats['never_accessed']}
🔥 High Usage Files: {global_stats['high_usage_files']}
📈 Total Accesses: {global_stats['total_accesses']}
📊 Avg Accesses/File: {global_stats['average_accesses_per_file']:.1f}
"""
        
        self.console.print(Panel(overview.strip(), title="Usage Overview", 
                                title_align="left", border_style="blue"))
        
        # Top accessed files
        file_stats = global_stats['file_stats']
        top_files = sorted([s for s in file_stats if s.total_accesses > 0], 
                          key=lambda s: s.usage_score, reverse=True)[:10]
        
        if top_files:
            self.console.print("\n🏆 Most Used Files:")
            
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("File", style="dim")
            table.add_column("Usage Score", justify="right")
            table.add_column("Accesses", justify="right")
            table.add_column("Last Access", justify="right")
            table.add_column("Category", justify="center")
            
            for stats in top_files:
                file_name = Path(stats.file_path).name
                last_access = stats.last_access.strftime("%Y-%m-%d") if stats.last_access else "Never"
                
                # Color code usage category
                category_colors = {
                    "Very High": "green",
                    "High": "green",
                    "Medium": "yellow",
                    "Low": "red",
                    "Very Low": "dim"
                }
                category_color = category_colors.get(stats.usage_category, "white")
                
                table.add_row(
                    file_name,
                    f"{stats.usage_score:.0f}",
                    str(stats.total_accesses),
                    last_access,
                    Text(stats.usage_category, style=category_color)
                )
            
            self.console.print(table)
        
        # Never accessed files
        never_accessed = [s for s in file_stats if s.total_accesses == 0]
        if never_accessed:
            self.console.print(f"\n👻 Never Accessed Files: {len(never_accessed)}")
            for stats in never_accessed[:5]:
                file_name = Path(stats.file_path).name
                self.console.print(f"  • {file_name}")
            
            if len(never_accessed) > 5:
                self.console.print(f"  ... and {len(never_accessed) - 5} more files")
        
        # Usage recommendations
        recommendations = self.generate_recommendations(library)
        if recommendations:
            self.console.print("\n💡 Smart Recommendations:")
            for i, rec in enumerate(recommendations[:5], 1):
                confidence_color = "green" if rec.confidence >= 0.7 else "yellow" if rec.confidence >= 0.5 else "red"
                self.console.print(f"  {i}. {rec.title}", style=f"bold {confidence_color}")
                self.console.print(f"     {rec.description}")
                if rec.potential_savings_gb > 0:
                    self.console.print(f"     💾 Potential savings: {rec.potential_savings_gb:.2f} GB")
                self.console.print(f"     🎯 Confidence: {rec.confidence_text}")
                self.console.print()
        
        self.console.print()
        input("Press Enter to continue...")
    
    def show_file_usage_details(self, file: DownloadedFile):
        """Show detailed usage information for a specific file."""
        stats = self.get_usage_stats(file)
        
        self.console.print()
        self.console.print(f"📊 Usage Details: {file.display_name}", style="bold blue")
        self.console.print()
        
        # Basic stats
        self.console.print("📈 Usage Statistics:")
        self.console.print(f"  Total Accesses: {stats.total_accesses}")
        self.console.print(f"  View Count: {stats.view_count}")
        self.console.print(f"  Management Actions: {stats.management_count}")
        self.console.print(f"  Usage Score: {stats.usage_score:.0f}/100")
        self.console.print(f"  Usage Category: {stats.usage_category}")
        
        if stats.first_access:
            self.console.print(f"  First Access: {stats.first_access.strftime('%Y-%m-%d %H:%M')}")
        
        if stats.last_access:
            self.console.print(f"  Last Access: {stats.last_access.strftime('%Y-%m-%d %H:%M')}")
            self.console.print(f"  Days Since Last Access: {stats.days_since_last_access:.0f}")
        
        self.console.print(f"  Access Frequency: {stats.access_frequency:.2f} accesses/day")
        
        # Recent access history
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT access_type, timestamp FROM access_records 
                WHERE file_path = ? 
                ORDER BY timestamp DESC 
                LIMIT 10
            ''', (str(file.file_path),))
            
            recent_records = cursor.fetchall()
        
        if recent_records:
            self.console.print()
            self.console.print("🕒 Recent Access History:")
            
            for access_type, timestamp_str in recent_records:
                timestamp = datetime.fromisoformat(timestamp_str)
                self.console.print(f"  • {access_type.title()}: {timestamp.strftime('%Y-%m-%d %H:%M')}")
        
        self.console.print()
        input("Press Enter to continue...")
    
    def cleanup_old_records(self):
        """Clean up old access records."""
        cutoff_date = datetime.now() - timedelta(days=self.retention_days)
        
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            
            cursor.execute('''
                DELETE FROM access_records 
                WHERE timestamp < ?
            ''', (cutoff_date.isoformat(),))
            
            deleted_count = cursor.rowcount
            conn.commit()
        
        self.console.print(f"🧹 Cleaned up {deleted_count} old access records")
    
    def export_usage_report(self, library: MediaLibrary, output_file: Path):
        """Export comprehensive usage report."""
        global_stats = self.get_global_usage_stats(library)
        recommendations = self.generate_recommendations(library)
        
        # Prepare file stats for export
        file_stats_export = []
        for stats in global_stats['file_stats']:
            file_stats_export.append({
                'file_path': stats.file_path,
                'total_accesses': stats.total_accesses,
                'view_count': stats.view_count,
                'management_count': stats.management_count,
                'usage_score': stats.usage_score,
                'usage_category': stats.usage_category,
                'access_frequency': stats.access_frequency,
                'days_since_last_access': stats.days_since_last_access,
                'first_access': stats.first_access.isoformat() if stats.first_access else None,
                'last_access': stats.last_access.isoformat() if stats.last_access else None
            })
        
        report = {
            'generated_at': datetime.now().isoformat(),
            'global_stats': {
                'total_files': global_stats['total_files'],
                'accessed_files': global_stats['accessed_files'],
                'never_accessed': global_stats['never_accessed'],
                'high_usage_files': global_stats['high_usage_files'],
                'total_accesses': global_stats['total_accesses'],
                'average_accesses_per_file': global_stats['average_accesses_per_file'],
                'access_rate': global_stats['access_rate']
            },
            'file_stats': file_stats_export,
            'recommendations': [
                {
                    'type': rec.type.value,
                    'title': rec.title,
                    'description': rec.description,
                    'file_count': len(rec.files),
                    'confidence': rec.confidence,
                    'confidence_text': rec.confidence_text,
                    'potential_savings_gb': rec.potential_savings_gb
                }
                for rec in recommendations
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.console.print(f"✅ Usage report exported to: {output_file}")
    
    def reset_usage_data(self):
        """Reset all usage data."""
        with sqlite3.connect(self.database_path) as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM access_records')
            conn.commit()
        
        self.console.print("🔄 All usage data has been reset")
    
    def get_database_size(self) -> float:
        """Get size of usage database in MB."""
        if self.database_path.exists():
            return self.database_path.stat().st_size / (1024 * 1024)
        return 0.0 