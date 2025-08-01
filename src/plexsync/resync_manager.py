"""
Re-sync Manager Module for Advanced File Management

This module provides functionality to re-download corrupted, missing, or incomplete files
from the media library, with intelligent retry mechanisms and progress tracking.
"""

import os
import asyncio
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timedelta
import json
import tempfile
import shutil

from rich.console import Console
from rich.progress import Progress, TaskID, BarColumn, TextColumn, TimeRemainingColumn, DownloadColumn, TransferSpeedColumn
from rich.table import Table
from rich.prompt import Confirm, Prompt
from rich.panel import Panel
from rich.text import Text

from .downloaded import DownloadedFile, FileStatus, DownloadedMediaManager
from .datasets import MediaLibrary, MediaItem, MediaType
from .file_operations import FileOperationsManager, IntegrityReport, IntegrityStatus
from .sync import SyncEngine
from .retry import RetryManager, RetryConfig


class ResyncReason(Enum):
    """Reasons for re-syncing a file."""
    CORRUPTED = "corrupted"
    MISSING = "missing"
    INCOMPLETE = "incomplete"
    OUTDATED = "outdated"
    USER_REQUEST = "user_request"
    VERIFICATION_FAILED = "verification_failed"


class ResyncStatus(Enum):
    """Status of a re-sync operation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class ResyncRequest:
    """Request for re-syncing a file."""
    file: DownloadedFile
    media_item: MediaItem  # Changed from Any to MediaItem
    reason: ResyncReason
    priority: int = 1  # 1 = highest, 5 = lowest
    created_at: datetime = field(default_factory=datetime.now)
    attempts: int = 0
    last_error: Optional[str] = None
    estimated_size: Optional[int] = None
    
    @property
    def age_hours(self) -> float:
        """Age of the request in hours."""
        return (datetime.now() - self.created_at).total_seconds() / 3600


@dataclass
class ResyncResult:
    """Result of a re-sync operation."""
    request: ResyncRequest
    status: ResyncStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    bytes_downloaded: int = 0
    download_speed: float = 0.0  # bytes per second
    integrity_verified: bool = False
    error_message: Optional[str] = None
    
    @property
    def duration_seconds(self) -> float:
        """Duration of the operation in seconds."""
        if self.end_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0
    
    @property
    def success(self) -> bool:
        """Whether the re-sync was successful."""
        return self.status == ResyncStatus.COMPLETED and self.integrity_verified


@dataclass
class ResyncBatch:
    """Batch of re-sync requests."""
    requests: List[ResyncRequest] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    total_size: int = 0
    
    @property
    def priority_requests(self) -> List[ResyncRequest]:
        """Get requests sorted by priority."""
        return sorted(self.requests, key=lambda r: (r.priority, r.created_at))
    
    @property
    def estimated_duration(self) -> timedelta:
        """Estimated duration for the batch."""
        # Rough estimate: 10 MB/s download speed
        estimated_seconds = self.total_size / (10 * 1024 * 1024)
        return timedelta(seconds=estimated_seconds)


class ResyncManager:
    """Manages re-syncing of corrupted, missing, or incomplete files."""
    
    def __init__(self, console: Console, downloaded_manager: DownloadedMediaManager, 
                 sync_engine: Optional[SyncEngine], file_operations: FileOperationsManager):
        self.console = console
        self.downloaded_manager = downloaded_manager
        self.sync_engine = sync_engine
        self.file_operations = file_operations
        self.retry_manager = RetryManager(RetryConfig(max_retries=3))
        
        # State tracking
        self.pending_requests: Dict[str, ResyncRequest] = {}
        self.completed_results: List[ResyncResult] = []
        self.batch_queue: List[ResyncBatch] = []
        
        # Configuration
        self.max_concurrent_syncs = 2
        self.verify_after_sync = True
        self.cleanup_failed_downloads = True
        
    def scan_for_resync_candidates(self, library: MediaLibrary) -> List[ResyncRequest]:
        """Scan for files that need re-syncing."""
        candidates = []
        
        # Get integrity reports for all files
        summary = self.downloaded_manager.get_summary(library)
        all_files = summary.movies + summary.episodes
        
        if not all_files:
            return candidates
        
        self.console.print("🔍 Scanning for files that need re-syncing...")
        
        # Run integrity verification
        integrity_reports = self.file_operations.verify_file_integrity(all_files)
        
        # Process each file
        for file, report in zip(all_files, integrity_reports):
            request = self._create_resync_request_from_report(file, report, library)
            if request:
                candidates.append(request)
        
        # Sort by priority
        candidates.sort(key=lambda r: (r.priority, r.created_at))
        
        return candidates
    
    def create_resync_request(self, file: DownloadedFile, reason: ResyncReason, 
                            media_item: MediaItem, priority: int = 1) -> ResyncRequest:
        """Create a new re-sync request."""
        request = ResyncRequest(
            file=file,
            media_item=media_item,
            reason=reason,
            priority=priority,
            estimated_size=file.file_size
        )
        
        # Add to pending requests
        request_id = f"{file.file_path}:{reason.value}"
        self.pending_requests[request_id] = request
        
        return request
    
    def queue_resync_batch(self, requests: List[ResyncRequest]) -> ResyncBatch:
        """Queue a batch of re-sync requests."""
        batch = ResyncBatch(
            requests=requests,
            total_size=sum(r.estimated_size or 0 for r in requests)
        )
        
        self.batch_queue.append(batch)
        return batch
    
    async def process_resync_batch(self, batch: ResyncBatch) -> List[ResyncResult]:
        """Process a batch of re-sync requests."""
        results = []
        
        self.console.print()
        self.console.print(f"🔄 Processing Re-sync Batch", style="bold blue")
        self.console.print(f"📊 {len(batch.requests)} files • {batch.total_size / (1024**3):.2f} GB")
        self.console.print(f"⏱️  Estimated time: {batch.estimated_duration}")
        self.console.print()
        
        # Process requests with concurrency control
        semaphore = asyncio.Semaphore(self.max_concurrent_syncs)
        
        async def process_request(request: ResyncRequest) -> ResyncResult:
            async with semaphore:
                return await self._process_single_request(request)
        
        # Create tasks for all requests
        tasks = [process_request(request) for request in batch.priority_requests]
        
        # Process with progress tracking
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            "[progress.percentage]{task.percentage:>3.0f}%",
            "•",
            DownloadColumn(),
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            console=self.console
        ) as progress:
            
            # Add overall progress task
            overall_task = progress.add_task("Re-syncing files...", total=len(tasks))
            
            # Process tasks
            for coro in asyncio.as_completed(tasks):
                try:
                    result = await coro
                    results.append(result)
                    
                    # Update progress
                    progress.update(overall_task, advance=1)
                    
                    # Log result
                    if result.success:
                        progress.console.print(f"✅ {result.request.file.display_name}")
                    else:
                        progress.console.print(f"❌ {result.request.file.display_name}: {result.error_message}")
                        
                except Exception as e:
                    # Create failed result
                    failed_result = ResyncResult(
                        request=tasks[0].get_coro().cr_frame.f_locals['request'],
                        status=ResyncStatus.FAILED,
                        start_time=datetime.now(),
                        end_time=datetime.now(),
                        error_message=str(e)
                    )
                    results.append(failed_result)
                    progress.update(overall_task, advance=1)
                    progress.console.print(f"❌ Processing error: {e}")
        
        # Store results
        self.completed_results.extend(results)
        
        # Show summary
        self._show_batch_summary(results)
        
        return results
    
    async def _process_single_request(self, request: ResyncRequest) -> ResyncResult:
        """Process a single re-sync request."""
        result = ResyncResult(
            request=request,
            status=ResyncStatus.IN_PROGRESS,
            start_time=datetime.now()
        )
        
        try:
            # Backup original file if it exists
            backup_path = None
            if request.file.file_path.exists():
                backup_path = self._create_backup(request.file.file_path)
            
            # Perform the re-sync
            success = await self._perform_resync(request, result)
            
            if success:
                # Verify integrity of downloaded file
                if self.verify_after_sync:
                    result.integrity_verified = await self._verify_resynced_file(request.file)
                else:
                    result.integrity_verified = True
                
                if result.integrity_verified:
                    result.status = ResyncStatus.COMPLETED
                    # Remove backup if successful
                    if backup_path and backup_path.exists():
                        backup_path.unlink()
                else:
                    result.status = ResyncStatus.FAILED
                    result.error_message = "Integrity verification failed"
                    # Restore backup if verification failed
                    if backup_path and backup_path.exists():
                        shutil.move(str(backup_path), str(request.file.file_path))
            else:
                result.status = ResyncStatus.FAILED
                # Restore backup if sync failed
                if backup_path and backup_path.exists():
                    shutil.move(str(backup_path), str(request.file.file_path))
            
        except Exception as e:
            result.status = ResyncStatus.FAILED
            result.error_message = str(e)
        
        finally:
            result.end_time = datetime.now()
        
        return result
    
    async def _perform_resync(self, request: ResyncRequest, result: ResyncResult) -> bool:
        """Perform the actual re-sync operation."""
        try:
            # Remove existing file if it exists
            if request.file.file_path.exists():
                request.file.file_path.unlink()
            
            # Ensure parent directory exists
            request.file.file_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Perform sync based on media type
            if request.media_item.media_type == MediaType.MOVIE:
                success = await self._resync_movie(request, result)
            elif request.media_item.media_type == MediaType.TV_EPISODE:
                success = await self._resync_episode(request, result)
            else:
                raise ValueError(f"Unsupported media type: {request.media_item.media_type}")
            
            return success
            
        except Exception as e:
            result.error_message = str(e)
            return False
    
    async def _resync_movie(self, request: ResyncRequest, result: ResyncResult) -> bool:
        """Re-sync a movie file."""
        media_item = request.media_item
        
        # Use the sync manager to download the movie
        try:
            # This would integrate with the actual sync functionality
            # For now, we'll simulate the download
            await self._simulate_download(request, result)
            return True
            
        except Exception as e:
            result.error_message = f"Movie re-sync failed: {str(e)}"
            return False
    
    async def _resync_episode(self, request: ResyncRequest, result: ResyncResult) -> bool:
        """Re-sync an episode file."""
        media_item = request.media_item
        
        # Use the sync manager to download the episode
        try:
            # This would integrate with the actual sync functionality
            # For now, we'll simulate the download
            await self._simulate_download(request, result)
            return True
            
        except Exception as e:
            result.error_message = f"Episode re-sync failed: {str(e)}"
            return False
    
    async def _simulate_download(self, request: ResyncRequest, result: ResyncResult):
        """Simulate file download for demonstration."""
        # This is a placeholder that would be replaced with actual download logic
        file_size = request.estimated_size or 1024 * 1024  # 1MB default
        
        # Simulate download progress
        chunk_size = 8192
        downloaded = 0
        
        # Create a temporary file with some content
        with open(request.file.file_path, 'wb') as f:
            while downloaded < file_size:
                chunk = min(chunk_size, file_size - downloaded)
                f.write(b'0' * chunk)
                downloaded += chunk
                
                # Simulate network delay
                await asyncio.sleep(0.01)
        
        result.bytes_downloaded = downloaded
        result.download_speed = downloaded / max(result.duration_seconds, 0.001)
    
    async def _verify_resynced_file(self, file: DownloadedFile) -> bool:
        """Verify the integrity of a re-synced file."""
        try:
            # Use the file operations manager for verification
            reports = self.file_operations.verify_file_integrity([file])
            
            if reports:
                report = reports[0]
                return report.status == IntegrityStatus.VERIFIED
            
            return False
            
        except Exception:
            return False
    
    def _create_backup(self, file_path: Path) -> Path:
        """Create a backup of the original file."""
        backup_path = file_path.with_suffix(f"{file_path.suffix}.backup")
        shutil.copy2(str(file_path), str(backup_path))
        return backup_path
    
    def _create_resync_request_from_report(self, file: DownloadedFile, 
                                          report: IntegrityReport, 
                                          library: MediaLibrary) -> Optional[ResyncRequest]:
        """Create a re-sync request from an integrity report."""
        # Determine if re-sync is needed
        if report.status == IntegrityStatus.VERIFIED:
            return None
        
        # Map integrity status to re-sync reason
        reason_map = {
            IntegrityStatus.CORRUPTED: ResyncReason.CORRUPTED,
            IntegrityStatus.MISSING: ResyncReason.MISSING,
            IntegrityStatus.INCOMPLETE: ResyncReason.INCOMPLETE,
            IntegrityStatus.UNKNOWN: ResyncReason.VERIFICATION_FAILED
        }
        
        reason = reason_map.get(report.status, ResyncReason.VERIFICATION_FAILED)
        
        # Find the corresponding media item
        media_item = self._find_media_item(file, library)
        if not media_item:
            return None
        
        # Set priority based on severity
        priority_map = {
            ResyncReason.MISSING: 1,
            ResyncReason.CORRUPTED: 2,
            ResyncReason.INCOMPLETE: 3,
            ResyncReason.VERIFICATION_FAILED: 4
        }
        
        priority = priority_map.get(reason, 5)
        
        return ResyncRequest(
            file=file,
            media_item=media_item,
            reason=reason,
            priority=priority,
            estimated_size=file.file_size
        )
    
    def _find_media_item(self, file: DownloadedFile, library: MediaLibrary) -> Optional[MediaItem]:
        """Find the media item corresponding to a downloaded file."""
        # This would use the same matching logic as the downloaded manager
        # For now, return a placeholder
        return None
    
    def _show_batch_summary(self, results: List[ResyncResult]):
        """Show summary of batch processing results."""
        if not results:
            return
        
        # Calculate statistics
        total_files = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total_files - successful
        total_bytes = sum(r.bytes_downloaded for r in results)
        total_time = sum(r.duration_seconds for r in results)
        
        self.console.print()
        self.console.print("🔄 Re-sync Batch Complete", style="bold green")
        self.console.print(f"✅ Successful: {successful} files")
        self.console.print(f"❌ Failed: {failed} files")
        self.console.print(f"📊 Data processed: {total_bytes / (1024**3):.2f} GB")
        self.console.print(f"⏱️  Total time: {total_time:.1f} seconds")
        
        if failed > 0:
            self.console.print()
            self.console.print("❌ Failed Re-syncs:")
            for result in results:
                if not result.success:
                    self.console.print(f"  • {result.request.file.display_name}: {result.error_message}")
    
    def show_resync_candidates(self, library: MediaLibrary):
        """Show files that are candidates for re-syncing."""
        candidates = self.scan_for_resync_candidates(library)
        
        if not candidates:
            self.console.print("✅ No files need re-syncing!", style="green")
            return
        
        self.console.print()
        self.console.print(f"🔄 Re-sync Candidates ({len(candidates)} files)", style="bold blue")
        self.console.print()
        
        # Group by reason
        by_reason = {}
        for candidate in candidates:
            reason = candidate.reason
            if reason not in by_reason:
                by_reason[reason] = []
            by_reason[reason].append(candidate)
        
        # Show grouped results
        for reason, files in by_reason.items():
            if reason == ResyncReason.CORRUPTED:
                icon = "❌"
                color = "red"
            elif reason == ResyncReason.MISSING:
                icon = "👻"
                color = "yellow"
            elif reason == ResyncReason.INCOMPLETE:
                icon = "⚠️"
                color = "yellow"
            else:
                icon = "❓"
                color = "dim"
            
            self.console.print(f"{icon} {reason.value.title()}: {len(files)} files", style=color)
            
            # Show first few files
            for file in files[:5]:
                size_mb = (file.estimated_size or 0) / (1024 * 1024)
                self.console.print(f"  • {file.file.display_name} ({size_mb:.1f} MB)")
            
            if len(files) > 5:
                self.console.print(f"  ... and {len(files) - 5} more files")
            
            self.console.print()
    
    def get_resync_statistics(self) -> Dict[str, Any]:
        """Get statistics about re-sync operations."""
        stats = {
            'pending_requests': len(self.pending_requests),
            'completed_results': len(self.completed_results),
            'success_rate': 0.0,
            'total_bytes_resynced': 0,
            'average_speed': 0.0,
            'reasons': {}
        }
        
        if self.completed_results:
            successful = sum(1 for r in self.completed_results if r.success)
            stats['success_rate'] = successful / len(self.completed_results)
            stats['total_bytes_resynced'] = sum(r.bytes_downloaded for r in self.completed_results)
            
            # Calculate average speed
            total_time = sum(r.duration_seconds for r in self.completed_results if r.duration_seconds > 0)
            if total_time > 0:
                stats['average_speed'] = stats['total_bytes_resynced'] / total_time
        
        # Count reasons
        for result in self.completed_results:
            reason = result.request.reason.value
            if reason not in stats['reasons']:
                stats['reasons'][reason] = 0
            stats['reasons'][reason] += 1
        
        return stats
    
    def export_resync_report(self, output_file: Path):
        """Export re-sync report to JSON file."""
        report = {
            'generated_at': datetime.now().isoformat(),
            'statistics': self.get_resync_statistics(),
            'pending_requests': [
                {
                    'file_path': str(req.file.file_path),
                    'reason': req.reason.value,
                    'priority': req.priority,
                    'created_at': req.created_at.isoformat(),
                    'attempts': req.attempts
                }
                for req in self.pending_requests.values()
            ],
            'completed_results': [
                {
                    'file_path': str(result.request.file.file_path),
                    'reason': result.request.reason.value,
                    'status': result.status.value,
                    'success': result.success,
                    'bytes_downloaded': result.bytes_downloaded,
                    'duration_seconds': result.duration_seconds,
                    'download_speed': result.download_speed,
                    'error_message': result.error_message
                }
                for result in self.completed_results
            ]
        }
        
        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.console.print(f"✅ Re-sync report exported to: {output_file}")
    
    def clear_completed_results(self):
        """Clear completed results to free memory."""
        self.completed_results.clear()
    
    def cancel_pending_requests(self, file_paths: Optional[List[str]] = None):
        """Cancel pending re-sync requests."""
        if file_paths:
            # Cancel specific requests
            for file_path in file_paths:
                requests_to_cancel = [
                    req_id for req_id, req in self.pending_requests.items()
                    if str(req.file.file_path) == file_path
                ]
                for req_id in requests_to_cancel:
                    del self.pending_requests[req_id]
        else:
            # Cancel all pending requests
            self.pending_requests.clear()
        
        self.console.print("✅ Pending re-sync requests cancelled") 