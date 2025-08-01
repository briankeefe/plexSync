"""
File Operations Module for Downloaded Media Management

This module provides comprehensive file operations including deletion, verification,
bulk operations, and integrity checking for downloaded media files.
"""

import os
import hashlib
import shutil
import time
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import json
import tempfile

from rich.console import Console
from rich.progress import Progress, TaskID, BarColumn, TextColumn, TimeRemainingColumn
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich.panel import Panel

from .downloaded import DownloadedFile, FileStatus, DownloadedMediaManager
from .datasets import MediaLibrary


class OperationResult(Enum):
    """Results of file operations."""
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    PARTIAL = "partial"


class IntegrityStatus(Enum):
    """File integrity verification status."""
    VERIFIED = "verified"
    CORRUPTED = "corrupted"
    INCOMPLETE = "incomplete"
    MISSING = "missing"
    UNKNOWN = "unknown"


@dataclass
class FileOperation:
    """Represents a file operation to be performed."""
    operation_type: str
    file_path: Path
    target_path: Optional[Path] = None
    file_size: int = 0
    checksum: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class OperationSummary:
    """Summary of batch operations."""
    total_files: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    bytes_processed: int = 0
    time_elapsed: float = 0.0
    errors: List[str] = field(default_factory=list)


@dataclass
class IntegrityReport:
    """File integrity verification report."""
    file_path: Path
    original_size: int
    actual_size: int
    checksum_expected: Optional[str] = None
    checksum_actual: Optional[str] = None
    status: IntegrityStatus = IntegrityStatus.UNKNOWN
    verification_time: datetime = field(default_factory=datetime.now)
    error_message: Optional[str] = None


class FileOperationsManager:
    """Manages file operations for downloaded media."""
    
    def __init__(self, console: Console, manager: DownloadedMediaManager):
        self.console = console
        self.manager = manager
        self.operation_history: List[FileOperation] = []
        self.integrity_cache: Dict[str, IntegrityReport] = {}
        
    def delete_files(self, files: List[DownloadedFile], 
                    confirmation_callback: Optional[Callable] = None) -> OperationSummary:
        """
        Delete multiple files with progress tracking and safety checks.
        
        Args:
            files: List of files to delete
            confirmation_callback: Optional callback for final confirmation
            
        Returns:
            OperationSummary with results
        """
        if not files:
            return OperationSummary()
        
        # Calculate total size
        total_size = sum(f.file_size for f in files)
        total_size_gb = total_size / (1024**3)
        
        # Show deletion summary
        self.console.print()
        self.console.print("🗑️  Bulk File Deletion", style="bold red")
        self.console.print()
        
        # Group files by type
        movies = [f for f in files if 'movie' in f.display_name.lower() or f.file_path.suffix.lower() in ['.mp4', '.mkv', '.avi']]
        episodes = [f for f in files if f not in movies]
        
        self.console.print("Files to delete:")
        if movies:
            self.console.print(f"  🎬 Movies: {len(movies)} files")
        if episodes:
            self.console.print(f"  📺 Episodes: {len(episodes)} files")
        
        self.console.print()
        self.console.print(f"📊 Total: {len(files)} files • {total_size_gb:.2f} GB")
        self.console.print()
        
        # Safety warnings
        self.console.print("⚠️  WARNING: This action is permanent and cannot be undone!", style="bold red")
        self.console.print("✓ Original library files will remain safe (only sync copies deleted)")
        self.console.print("✓ Files can be re-downloaded through sync if needed")
        self.console.print()
        
        # Show sample files
        if len(files) > 5:
            self.console.print("Sample files to be deleted:")
            for i, file in enumerate(files[:5]):
                self.console.print(f"  {i+1}. {file.display_name} ({file.size_gb:.2f} GB)")
            self.console.print(f"  ... and {len(files) - 5} more files")
        else:
            self.console.print("Files to be deleted:")
            for i, file in enumerate(files):
                self.console.print(f"  {i+1}. {file.display_name} ({file.size_gb:.2f} GB)")
        
        self.console.print()
        
        # Final confirmation
        if confirmation_callback:
            if not confirmation_callback():
                return OperationSummary(total_files=len(files), skipped=len(files))
        else:
            if not Confirm.ask(f"Delete {len(files)} files and free {total_size_gb:.2f} GB [y/N]", default=False):
                return OperationSummary(total_files=len(files), skipped=len(files))
        
        # Perform deletion with progress bar
        summary = OperationSummary(total_files=len(files))
        start_time = time.time()
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            TextColumn("[progress.completed]{task.completed}/{task.total} files"),
            "•",
            TimeRemainingColumn(),
            console=self.console
        ) as progress:
            
            task = progress.add_task("Deleting files...", total=len(files))
            
            for file in files:
                try:
                    # Check if file exists
                    if not file.file_path.exists():
                        summary.skipped += 1
                        progress.console.print(f"⚠️  Skipped: {file.display_name} (file not found)")
                        continue
                    
                    # Delete the file
                    file.file_path.unlink()
                    
                    # Try to remove empty parent directories
                    try:
                        parent = file.file_path.parent
                        if parent.exists() and not any(parent.iterdir()):
                            parent.rmdir()
                    except OSError:
                        pass  # Directory not empty or permission denied
                    
                    # Record operation
                    operation = FileOperation(
                        operation_type="delete",
                        file_path=file.file_path,
                        file_size=file.file_size
                    )
                    self.operation_history.append(operation)
                    
                    summary.successful += 1
                    summary.bytes_processed += file.file_size
                    
                except Exception as e:
                    summary.failed += 1
                    error_msg = f"Failed to delete {file.display_name}: {str(e)}"
                    summary.errors.append(error_msg)
                    progress.console.print(f"❌ {error_msg}")
                
                progress.update(task, advance=1)
        
        summary.time_elapsed = time.time() - start_time
        
        # Show results
        self.console.print()
        self.console.print("🗑️  Deletion Complete", style="bold green")
        self.console.print(f"✅ Successfully deleted: {summary.successful} files")
        self.console.print(f"⚠️  Skipped: {summary.skipped} files")
        if summary.failed > 0:
            self.console.print(f"❌ Failed: {summary.failed} files")
        
        freed_gb = summary.bytes_processed / (1024**3)
        self.console.print(f"💾 Storage freed: {freed_gb:.2f} GB")
        self.console.print(f"⏱️  Time elapsed: {summary.time_elapsed:.1f} seconds")
        
        return summary
    
    def verify_file_integrity(self, files: List[DownloadedFile], 
                            force_reverify: bool = False) -> List[IntegrityReport]:
        """
        Verify integrity of multiple files with checksum validation.
        
        Args:
            files: List of files to verify
            force_reverify: Force re-verification even if cached
            
        Returns:
            List of IntegrityReport objects
        """
        if not files:
            return []
        
        self.console.print()
        self.console.print("🔍 File Integrity Verification", style="bold blue")
        self.console.print()
        
        reports = []
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            TextColumn("[progress.completed]{task.completed}/{task.total} files"),
            "•",
            TimeRemainingColumn(),
            console=self.console
        ) as progress:
            
            task = progress.add_task("Verifying files...", total=len(files))
            
            for file in files:
                try:
                    # Check cache first
                    cache_key = f"{file.file_path}:{file.file_size}"
                    if not force_reverify and cache_key in self.integrity_cache:
                        report = self.integrity_cache[cache_key]
                        reports.append(report)
                        progress.update(task, advance=1)
                        continue
                    
                    # Create new report
                    report = IntegrityReport(
                        file_path=file.file_path,
                        original_size=file.file_size,
                        actual_size=0  # Will be updated below
                    )
                    
                    # Check if file exists
                    if not file.file_path.exists():
                        report.status = IntegrityStatus.MISSING
                        report.error_message = "File not found"
                        report.actual_size = 0
                    else:
                        # Check file size
                        actual_size = file.file_path.stat().st_size
                        report.actual_size = actual_size
                        
                        if actual_size == 0:
                            report.status = IntegrityStatus.CORRUPTED
                            report.error_message = "File is empty"
                        elif actual_size != file.file_size:
                            report.status = IntegrityStatus.INCOMPLETE
                            report.error_message = f"Size mismatch: expected {file.file_size}, got {actual_size}"
                        else:
                            # Calculate checksum for verification
                            try:
                                checksum = self._calculate_file_checksum(file.file_path)
                                report.checksum_actual = checksum
                                report.status = IntegrityStatus.VERIFIED
                            except Exception as e:
                                report.status = IntegrityStatus.UNKNOWN
                                report.error_message = f"Checksum calculation failed: {str(e)}"
                    
                    # Cache the report
                    self.integrity_cache[cache_key] = report
                    reports.append(report)
                    
                except Exception as e:
                    report = IntegrityReport(
                        file_path=file.file_path,
                        original_size=file.file_size,
                        actual_size=0,
                        status=IntegrityStatus.UNKNOWN,
                        error_message=str(e)
                    )
                    reports.append(report)
                
                progress.update(task, advance=1)
        
        # Show verification results
        self._show_integrity_results(reports)
        
        return reports
    
    def move_files(self, files: List[DownloadedFile], target_directory: Path,
                  organize_by_type: bool = True) -> OperationSummary:
        """
        Move files to a new directory with optional organization.
        
        Args:
            files: List of files to move
            target_directory: Destination directory
            organize_by_type: Whether to organize by movies/tv subdirectories
            
        Returns:
            OperationSummary with results
        """
        if not files:
            return OperationSummary()
        
        self.console.print()
        self.console.print("📁 Bulk File Move Operation", style="bold blue")
        self.console.print()
        
        # Ensure target directory exists
        target_directory.mkdir(parents=True, exist_ok=True)
        
        # Calculate total size
        total_size = sum(f.file_size for f in files)
        total_size_gb = total_size / (1024**3)
        
        self.console.print(f"Moving {len(files)} files ({total_size_gb:.2f} GB) to:")
        self.console.print(f"  📁 {target_directory}")
        
        if organize_by_type:
            self.console.print("  📂 Files will be organized by type (movies/tv)")
        
        self.console.print()
        
        if not Confirm.ask("Proceed with file move [Y/n]", default=True):
            return OperationSummary(total_files=len(files), skipped=len(files))
        
        # Perform move operation
        summary = OperationSummary(total_files=len(files))
        start_time = time.time()
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            TextColumn("[progress.completed]{task.completed}/{task.total} files"),
            "•",
            TimeRemainingColumn(),
            console=self.console
        ) as progress:
            
            task = progress.add_task("Moving files...", total=len(files))
            
            for file in files:
                try:
                    # Determine target path
                    if organize_by_type:
                        # Organize by movies/tv
                        if 'movie' in file.display_name.lower():
                            type_dir = target_directory / "movies"
                        else:
                            type_dir = target_directory / "tv"
                        type_dir.mkdir(exist_ok=True)
                        target_path = type_dir / file.file_path.name
                    else:
                        target_path = target_directory / file.file_path.name
                    
                    # Handle name conflicts
                    counter = 1
                    original_target = target_path
                    while target_path.exists():
                        stem = original_target.stem
                        suffix = original_target.suffix
                        target_path = original_target.parent / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    # Move the file
                    shutil.move(str(file.file_path), str(target_path))
                    
                    # Record operation
                    operation = FileOperation(
                        operation_type="move",
                        file_path=file.file_path,
                        target_path=target_path,
                        file_size=file.file_size
                    )
                    self.operation_history.append(operation)
                    
                    summary.successful += 1
                    summary.bytes_processed += file.file_size
                    
                except Exception as e:
                    summary.failed += 1
                    error_msg = f"Failed to move {file.display_name}: {str(e)}"
                    summary.errors.append(error_msg)
                    progress.console.print(f"❌ {error_msg}")
                
                progress.update(task, advance=1)
        
        summary.time_elapsed = time.time() - start_time
        
        # Show results
        self.console.print()
        self.console.print("📁 Move Operation Complete", style="bold green")
        self.console.print(f"✅ Successfully moved: {summary.successful} files")
        if summary.failed > 0:
            self.console.print(f"❌ Failed: {summary.failed} files")
        
        moved_gb = summary.bytes_processed / (1024**3)
        self.console.print(f"📊 Data moved: {moved_gb:.2f} GB")
        self.console.print(f"⏱️  Time elapsed: {summary.time_elapsed:.1f} seconds")
        
        return summary
    
    def copy_files(self, files: List[DownloadedFile], target_directory: Path,
                  organize_by_type: bool = True) -> OperationSummary:
        """
        Copy files to a new directory with optional organization.
        
        Args:
            files: List of files to copy
            target_directory: Destination directory
            organize_by_type: Whether to organize by movies/tv subdirectories
            
        Returns:
            OperationSummary with results
        """
        if not files:
            return OperationSummary()
        
        self.console.print()
        self.console.print("📋 Bulk File Copy Operation", style="bold blue")
        self.console.print()
        
        # Ensure target directory exists
        target_directory.mkdir(parents=True, exist_ok=True)
        
        # Calculate total size and check space
        total_size = sum(f.file_size for f in files)
        total_size_gb = total_size / (1024**3)
        
        # Check available space
        try:
            free_space = shutil.disk_usage(target_directory).free
            free_space_gb = free_space / (1024**3)
            
            if total_size > free_space:
                self.console.print(f"❌ Insufficient space: need {total_size_gb:.2f} GB, have {free_space_gb:.2f} GB", style="red")
                return OperationSummary(total_files=len(files), skipped=len(files))
        except OSError:
            pass  # Can't check space, proceed anyway
        
        self.console.print(f"Copying {len(files)} files ({total_size_gb:.2f} GB) to:")
        self.console.print(f"  📁 {target_directory}")
        
        if organize_by_type:
            self.console.print("  📂 Files will be organized by type (movies/tv)")
        
        self.console.print()
        
        if not Confirm.ask("Proceed with file copy [Y/n]", default=True):
            return OperationSummary(total_files=len(files), skipped=len(files))
        
        # Perform copy operation
        summary = OperationSummary(total_files=len(files))
        start_time = time.time()
        
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            TextColumn("[progress.completed]{task.completed}/{task.total} files"),
            "•",
            TimeRemainingColumn(),
            console=self.console
        ) as progress:
            
            task = progress.add_task("Copying files...", total=len(files))
            
            for file in files:
                try:
                    # Determine target path
                    if organize_by_type:
                        # Organize by movies/tv
                        if 'movie' in file.display_name.lower():
                            type_dir = target_directory / "movies"
                        else:
                            type_dir = target_directory / "tv"
                        type_dir.mkdir(exist_ok=True)
                        target_path = type_dir / file.file_path.name
                    else:
                        target_path = target_directory / file.file_path.name
                    
                    # Handle name conflicts
                    counter = 1
                    original_target = target_path
                    while target_path.exists():
                        stem = original_target.stem
                        suffix = original_target.suffix
                        target_path = original_target.parent / f"{stem}_{counter}{suffix}"
                        counter += 1
                    
                    # Copy the file
                    shutil.copy2(str(file.file_path), str(target_path))
                    
                    # Record operation
                    operation = FileOperation(
                        operation_type="copy",
                        file_path=file.file_path,
                        target_path=target_path,
                        file_size=file.file_size
                    )
                    self.operation_history.append(operation)
                    
                    summary.successful += 1
                    summary.bytes_processed += file.file_size
                    
                except Exception as e:
                    summary.failed += 1
                    error_msg = f"Failed to copy {file.display_name}: {str(e)}"
                    summary.errors.append(error_msg)
                    progress.console.print(f"❌ {error_msg}")
                
                progress.update(task, advance=1)
        
        summary.time_elapsed = time.time() - start_time
        
        # Show results
        self.console.print()
        self.console.print("📋 Copy Operation Complete", style="bold green")
        self.console.print(f"✅ Successfully copied: {summary.successful} files")
        if summary.failed > 0:
            self.console.print(f"❌ Failed: {summary.failed} files")
        
        copied_gb = summary.bytes_processed / (1024**3)
        self.console.print(f"📊 Data copied: {copied_gb:.2f} GB")
        self.console.print(f"⏱️  Time elapsed: {summary.time_elapsed:.1f} seconds")
        
        return summary
    
    def _calculate_file_checksum(self, file_path: Path, algorithm: str = "sha256") -> str:
        """Calculate checksum for a file."""
        hash_func = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            # Read in chunks to handle large files
            chunk_size = 8192
            while chunk := f.read(chunk_size):
                hash_func.update(chunk)
        
        return hash_func.hexdigest()
    
    def _show_integrity_results(self, reports: List[IntegrityReport]):
        """Display integrity verification results."""
        if not reports:
            return
        
        self.console.print()
        self.console.print("🔍 Integrity Verification Results", style="bold blue")
        self.console.print()
        
        # Count statuses
        status_counts = {}
        for report in reports:
            status = report.status
            if status not in status_counts:
                status_counts[status] = 0
            status_counts[status] += 1
        
        # Show summary
        self.console.print("Summary:")
        for status, count in status_counts.items():
            if status == IntegrityStatus.VERIFIED:
                self.console.print(f"  ✅ Verified: {count} files")
            elif status == IntegrityStatus.CORRUPTED:
                self.console.print(f"  ❌ Corrupted: {count} files")
            elif status == IntegrityStatus.INCOMPLETE:
                self.console.print(f"  ⚠️  Incomplete: {count} files")
            elif status == IntegrityStatus.MISSING:
                self.console.print(f"  👻 Missing: {count} files")
            elif status == IntegrityStatus.UNKNOWN:
                self.console.print(f"  ❓ Unknown: {count} files")
        
        # Show detailed results for problematic files
        problematic = [r for r in reports if r.status != IntegrityStatus.VERIFIED]
        if problematic:
            self.console.print()
            self.console.print("Issues Found:")
            
            table = Table(show_header=True, header_style="bold red")
            table.add_column("File", style="dim")
            table.add_column("Status", justify="center")
            table.add_column("Issue", style="dim")
            
            for report in problematic[:10]:  # Show first 10 issues
                if report.status == IntegrityStatus.CORRUPTED:
                    status = "❌ Corrupted"
                elif report.status == IntegrityStatus.INCOMPLETE:
                    status = "⚠️ Incomplete"
                elif report.status == IntegrityStatus.MISSING:
                    status = "👻 Missing"
                else:
                    status = "❓ Unknown"
                
                table.add_row(
                    report.file_path.name,
                    status,
                    report.error_message or "No details"
                )
            
            self.console.print(table)
            
            if len(problematic) > 10:
                self.console.print(f"... and {len(problematic) - 10} more issues")
    
    def get_operation_history(self) -> List[FileOperation]:
        """Get history of all file operations."""
        return self.operation_history.copy()
    
    def clear_operation_history(self):
        """Clear the operation history."""
        self.operation_history.clear()
    
    def export_operation_log(self, output_file: Path):
        """Export operation history to a JSON file."""
        log_data = []
        for operation in self.operation_history:
            log_data.append({
                "operation_type": operation.operation_type,
                "file_path": str(operation.file_path),
                "target_path": str(operation.target_path) if operation.target_path else None,
                "file_size": operation.file_size,
                "checksum": operation.checksum,
                "created_at": operation.created_at.isoformat()
            })
        
        with open(output_file, 'w') as f:
            json.dump(log_data, f, indent=2)
        
        self.console.print(f"✅ Operation log exported to: {output_file}") 