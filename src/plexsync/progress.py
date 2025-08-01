"""
PlexSync - Progress Tracking
Real-time progress tracking and display for sync operations.
"""

import re
import time
import threading
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable, Any
from uuid import uuid4

try:
    from rich.console import Console
    from rich.progress import Progress, TaskID, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
    from rich.live import Live
    from rich.table import Table
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


class TransferStatus(Enum):
    """Transfer status"""
    PENDING = "pending"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SyncProgress:
    """Individual sync progress information"""
    transfer_id: str
    source_path: str
    destination_path: str
    total_bytes: int
    transferred_bytes: int = 0
    transfer_rate: float = 0.0  # bytes per second
    percentage: float = 0.0
    eta_seconds: float = 0.0
    status: TransferStatus = TransferStatus.PENDING
    start_time: float = 0.0
    error_message: Optional[str] = None
    
    @property
    def elapsed_time(self) -> float:
        """Time elapsed since start"""
        if self.start_time > 0:
            return time.time() - self.start_time
        return 0.0
    
    @property
    def remaining_bytes(self) -> int:
        """Bytes remaining to transfer"""
        return max(0, self.total_bytes - self.transferred_bytes)
    
    @property
    def is_complete(self) -> bool:
        """Whether transfer is complete"""
        return self.status == TransferStatus.COMPLETED
    
    @property
    def is_active(self) -> bool:
        """Whether transfer is currently active"""
        return self.status == TransferStatus.ACTIVE


class ProgressTracker:
    """Progress tracker for sync operations"""
    
    def __init__(self):
        self._transfers: Dict[str, SyncProgress] = {}
        self._lock = threading.Lock()
        self._progress_callbacks: List[Callable[[SyncProgress], None]] = []
        
        # Rich console for display
        if RICH_AVAILABLE:
            self.console = Console()
            self._rich_progress: Optional[Progress] = None
            self._rich_tasks: Dict[str, TaskID] = {}
        else:
            self.console = None
    
    def add_progress_callback(self, callback: Callable[[SyncProgress], None]):
        """Add callback for progress updates"""
        self._progress_callbacks.append(callback)
    
    def start_transfer(self, source_path: str, destination_path: str, 
                      total_bytes: int) -> SyncProgress:
        """Start tracking a new transfer"""
        
        transfer_id = str(uuid4())
        
        progress = SyncProgress(
            transfer_id=transfer_id,
            source_path=source_path,
            destination_path=destination_path,
            total_bytes=total_bytes,
            start_time=time.time(),
            status=TransferStatus.ACTIVE
        )
        
        with self._lock:
            self._transfers[transfer_id] = progress
        
        # Add to Rich progress if available
        if RICH_AVAILABLE and self._rich_progress:
            task_id = self._rich_progress.add_task(
                f"[cyan]{self._format_filename(source_path)}",
                total=total_bytes
            )
            self._rich_tasks[transfer_id] = task_id
        
        return progress
    
    def update_transfer(self, transfer_id: str, transferred_bytes: int, 
                       transfer_rate: float = None):
        """Update transfer progress"""
        
        with self._lock:
            if transfer_id not in self._transfers:
                return
            
            progress = self._transfers[transfer_id]
            progress.transferred_bytes = transferred_bytes
            
            if transfer_rate is not None:
                progress.transfer_rate = transfer_rate
            
            # Calculate percentage
            if progress.total_bytes > 0:
                progress.percentage = (transferred_bytes / progress.total_bytes) * 100
            
            # Calculate ETA
            if progress.transfer_rate > 0:
                remaining_bytes = progress.total_bytes - transferred_bytes
                progress.eta_seconds = remaining_bytes / progress.transfer_rate
            
            # Update Rich progress
            if RICH_AVAILABLE and self._rich_progress and transfer_id in self._rich_tasks:
                self._rich_progress.update(
                    self._rich_tasks[transfer_id],
                    completed=transferred_bytes
                )
        
        # Notify callbacks
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception:
                pass
    
    def finish_transfer(self, transfer_id: str, success: bool = True, 
                       error_message: str = None):
        """Mark transfer as finished"""
        
        with self._lock:
            if transfer_id not in self._transfers:
                return
            
            progress = self._transfers[transfer_id]
            
            if success:
                progress.status = TransferStatus.COMPLETED
                progress.percentage = 100.0
                progress.transferred_bytes = progress.total_bytes
            else:
                progress.status = TransferStatus.FAILED
                progress.error_message = error_message
            
            # Remove from Rich progress
            if RICH_AVAILABLE and self._rich_progress and transfer_id in self._rich_tasks:
                self._rich_progress.remove_task(self._rich_tasks[transfer_id])
                del self._rich_tasks[transfer_id]
        
        # Notify callbacks
        for callback in self._progress_callbacks:
            try:
                callback(progress)
            except Exception:
                pass
    
    def pause_transfer(self, transfer_id: str):
        """Pause a transfer"""
        with self._lock:
            if transfer_id in self._transfers:
                self._transfers[transfer_id].status = TransferStatus.PAUSED
    
    def resume_transfer(self, transfer_id: str):
        """Resume a paused transfer"""
        with self._lock:
            if transfer_id in self._transfers:
                self._transfers[transfer_id].status = TransferStatus.ACTIVE
    
    def cancel_transfer(self, transfer_id: str):
        """Cancel a transfer"""
        with self._lock:
            if transfer_id in self._transfers:
                progress = self._transfers[transfer_id]
                progress.status = TransferStatus.CANCELLED
                
                # Remove from Rich progress
                if RICH_AVAILABLE and self._rich_progress and transfer_id in self._rich_tasks:
                    self._rich_progress.remove_task(self._rich_tasks[transfer_id])
                    del self._rich_tasks[transfer_id]
    
    def get_transfer(self, transfer_id: str) -> Optional[SyncProgress]:
        """Get transfer progress"""
        with self._lock:
            return self._transfers.get(transfer_id)
    
    def get_active_transfers(self) -> List[SyncProgress]:
        """Get all active transfers"""
        with self._lock:
            return [p for p in self._transfers.values() if p.is_active]
    
    def get_all_transfers(self) -> List[SyncProgress]:
        """Get all transfers"""
        with self._lock:
            return list(self._transfers.values())
    
    def clear_completed(self):
        """Clear completed transfers"""
        with self._lock:
            completed_ids = [
                tid for tid, progress in self._transfers.items()
                if progress.status in (TransferStatus.COMPLETED, TransferStatus.FAILED, TransferStatus.CANCELLED)
            ]
            for tid in completed_ids:
                del self._transfers[tid]
    
    def parse_rsync_progress(self, progress_line: str) -> Optional[SyncProgress]:
        """Parse rsync progress line"""
        # Example: "  1,234,567  45%  123.45kB/s    0:00:12"
        # More complex: "  1.23M  45%  123.45kB/s    0:00:12 (xfr#1, to-chk=0/1)"
        
        patterns = [
            # Standard rsync progress format
            r'^\s*(\d+(?:,\d+)*|\d+\.?\d*[KMGT]?)\s+(\d+)%\s+(\d+\.?\d*[KMGT]?B/s)\s+(\d+:\d+:\d+)',
            # Alternative format
            r'^\s*(\d+(?:,\d+)*)\s+(\d+)%\s+(\d+\.?\d*[KMGT]?B/s)\s+(\d+:\d+:\d+)',
        ]
        
        for pattern in patterns:
            match = re.match(pattern, progress_line)
            if match:
                try:
                    bytes_str, percent_str, speed_str, time_str = match.groups()
                    
                    # Parse bytes
                    bytes_transferred = self._parse_bytes(bytes_str)
                    
                    # Parse percentage
                    percentage = float(percent_str)
                    
                    # Parse speed
                    transfer_rate = self._parse_speed(speed_str)
                    
                    # Parse time remaining
                    eta_seconds = self._parse_time(time_str)
                    
                    # Create progress object (we don't know the transfer_id here)
                    return SyncProgress(
                        transfer_id="",
                        source_path="",
                        destination_path="",
                        total_bytes=0,
                        transferred_bytes=bytes_transferred,
                        transfer_rate=transfer_rate,
                        percentage=percentage,
                        eta_seconds=eta_seconds,
                        status=TransferStatus.ACTIVE
                    )
                
                except Exception:
                    continue
        
        return None
    
    def _parse_bytes(self, bytes_str: str) -> int:
        """Parse byte string (e.g., '1,234,567' or '1.23M')"""
        # Remove commas
        bytes_str = bytes_str.replace(',', '')
        
        # Check for size suffix
        if bytes_str.endswith('K'):
            return int(float(bytes_str[:-1]) * 1024)
        elif bytes_str.endswith('M'):
            return int(float(bytes_str[:-1]) * 1024 * 1024)
        elif bytes_str.endswith('G'):
            return int(float(bytes_str[:-1]) * 1024 * 1024 * 1024)
        elif bytes_str.endswith('T'):
            return int(float(bytes_str[:-1]) * 1024 * 1024 * 1024 * 1024)
        else:
            return int(float(bytes_str))
    
    def _parse_speed(self, speed_str: str) -> float:
        """Parse speed string (e.g., '123.45kB/s')"""
        # Remove '/s' suffix
        speed_str = speed_str.replace('/s', '')
        
        # Check for size suffix
        if speed_str.endswith('kB'):
            return float(speed_str[:-2]) * 1024
        elif speed_str.endswith('MB'):
            return float(speed_str[:-2]) * 1024 * 1024
        elif speed_str.endswith('GB'):
            return float(speed_str[:-2]) * 1024 * 1024 * 1024
        elif speed_str.endswith('B'):
            return float(speed_str[:-1])
        else:
            return float(speed_str)
    
    def _parse_time(self, time_str: str) -> float:
        """Parse time string (e.g., '0:00:12')"""
        parts = time_str.split(':')
        if len(parts) == 3:
            hours, minutes, seconds = map(int, parts)
            return hours * 3600 + minutes * 60 + seconds
        return 0.0
    
    def _format_filename(self, path: str) -> str:
        """Format filename for display"""
        import os
        filename = os.path.basename(path)
        if len(filename) > 50:
            return filename[:47] + "..."
        return filename
    
    def create_rich_progress(self) -> Optional[Progress]:
        """Create Rich progress display"""
        if not RICH_AVAILABLE:
            return None
        
        self._rich_progress = Progress(
            TextColumn("[bold blue]{task.fields[filename]}", justify="left"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.1f}%",
            "•",
            TransferSpeedColumn(),
            "•",
            TimeRemainingColumn(),
            console=self.console,
            expand=True
        )
        
        return self._rich_progress
    
    def display_summary(self) -> str:
        """Display transfer summary"""
        with self._lock:
            total_transfers = len(self._transfers)
            completed = sum(1 for p in self._transfers.values() if p.status == TransferStatus.COMPLETED)
            failed = sum(1 for p in self._transfers.values() if p.status == TransferStatus.FAILED)
            active = sum(1 for p in self._transfers.values() if p.is_active)
            
            total_bytes = sum(p.total_bytes for p in self._transfers.values())
            transferred_bytes = sum(p.transferred_bytes for p in self._transfers.values())
            
            summary = f"""
📊 Transfer Summary:
   Total: {total_transfers}
   ✅ Completed: {completed}
   ❌ Failed: {failed}
   🔄 Active: {active}
   
📈 Data Transfer:
   Total Size: {self._format_bytes(total_bytes)}
   Transferred: {self._format_bytes(transferred_bytes)}
   Progress: {(transferred_bytes/total_bytes*100):.1f}% if total_bytes > 0 else 0.0%
"""
            
            return summary
    
    def _format_bytes(self, bytes_count: int) -> str:
        """Format bytes for display"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.1f} PB"
    
    def create_transfer_table(self) -> Optional[Table]:
        """Create Rich table showing all transfers"""
        if not RICH_AVAILABLE:
            return None
        
        table = Table(title="Transfer Status")
        table.add_column("File", style="cyan", no_wrap=True)
        table.add_column("Progress", style="yellow")
        table.add_column("Speed", style="green")
        table.add_column("ETA", style="blue")
        table.add_column("Status", style="magenta")
        
        with self._lock:
            for progress in self._transfers.values():
                filename = self._format_filename(progress.source_path)
                progress_bar = f"{progress.percentage:.1f}%"
                speed = f"{self._format_bytes(progress.transfer_rate)}/s" if progress.transfer_rate > 0 else "N/A"
                eta = f"{progress.eta_seconds:.0f}s" if progress.eta_seconds > 0 else "N/A"
                
                # Status with emoji
                status_map = {
                    TransferStatus.PENDING: "⏳ Pending",
                    TransferStatus.ACTIVE: "🔄 Active",
                    TransferStatus.PAUSED: "⏸️ Paused",
                    TransferStatus.COMPLETED: "✅ Complete",
                    TransferStatus.FAILED: "❌ Failed",
                    TransferStatus.CANCELLED: "🛑 Cancelled"
                }
                
                status = status_map.get(progress.status, "❓ Unknown")
                
                table.add_row(filename, progress_bar, speed, eta, status)
        
        return table 