"""
PlexSync - Sync Engine
Core synchronization engine with rsync integration, progress tracking, and interruption handling.
"""

import os
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable
import threading
import queue
import json

from .integrity import IntegrityChecker
from .progress import ProgressTracker, SyncProgress
from .retry import RetryManager, SyncError


class SyncStatus(Enum):
    """Sync operation status"""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SyncMode(Enum):
    """Sync operation modes"""
    COPY = "copy"          # Copy files (default)
    MOVE = "move"          # Move files (delete source)
    SYNC = "sync"          # Bidirectional sync
    VERIFY = "verify"      # Verify existing files only


@dataclass
class SyncOptions:
    """Sync operation configuration"""
    bandwidth_limit: Optional[int] = None  # KB/s
    preserve_permissions: bool = True
    preserve_timestamps: bool = True
    compress: bool = True
    delete_after: bool = False
    dry_run: bool = False
    checksum: bool = True
    partial: bool = True  # Keep partial files
    progress: bool = True
    verbose: bool = False
    exclude_patterns: List[str] = None
    include_patterns: List[str] = None
    
    def __post_init__(self):
        if self.exclude_patterns is None:
            self.exclude_patterns = []
        if self.include_patterns is None:
            self.include_patterns = []


@dataclass
class SyncResult:
    """Sync operation result"""
    status: SyncStatus
    source_path: str
    destination_path: str
    bytes_transferred: int = 0
    files_transferred: int = 0
    duration: float = 0.0
    error_message: Optional[str] = None
    checksum_verified: bool = False
    partial_transfer: bool = False
    
    @property
    def success(self) -> bool:
        return self.status == SyncStatus.COMPLETED
    
    @property
    def transfer_rate(self) -> float:
        """Transfer rate in MB/s"""
        if self.duration > 0:
            return (self.bytes_transferred / 1024 / 1024) / self.duration
        return 0.0


class SyncEngine:
    """Core synchronization engine with rsync integration"""
    
    def __init__(self, options: SyncOptions = None):
        self.options = options or SyncOptions()
        self.integrity_checker = IntegrityChecker()
        self.progress_tracker = ProgressTracker()
        self.retry_manager = RetryManager()
        
        # State management
        self._current_process: Optional[subprocess.Popen] = None
        self._is_cancelled = False
        self._pause_event = threading.Event()
        self._pause_event.set()  # Initially not paused
        
        # Progress callback
        self._progress_callback: Optional[Callable[[SyncProgress], None]] = None
        
        # Signal handling for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def set_progress_callback(self, callback: Callable[[SyncProgress], None]):
        """Set callback for progress updates"""
        self._progress_callback = callback
    
    def _signal_handler(self, signum, frame):
        """Handle interruption signals"""
        self.cancel()
    
    def _build_rsync_command(self, source: str, destination: str) -> List[str]:
        """Build rsync command with options"""
        cmd = ["rsync"]
        
        # Basic options
        cmd.append("-a")  # Archive mode (recursive, preserve everything)
        
        if self.options.verbose:
            cmd.append("-v")
        
        if self.options.progress:
            cmd.append("--progress")
        
        if self.options.partial:
            cmd.append("--partial")
        
        if self.options.compress:
            cmd.append("-z")
        
        if self.options.checksum:
            cmd.append("-c")
        
        if self.options.delete_after:
            cmd.append("--delete-after")
        
        if self.options.dry_run:
            cmd.append("--dry-run")
        
        # Bandwidth limiting
        if self.options.bandwidth_limit:
            cmd.append(f"--bwlimit={self.options.bandwidth_limit}")
        
        # Exclude patterns
        for pattern in self.options.exclude_patterns:
            cmd.extend(["--exclude", pattern])
        
        # Include patterns
        for pattern in self.options.include_patterns:
            cmd.extend(["--include", pattern])
        
        # Stats and human readable
        cmd.append("--stats")
        cmd.append("--human-readable")
        
        # Source and destination
        cmd.append(source)
        cmd.append(destination)
        
        return cmd
    
    def _parse_rsync_output(self, output: str) -> Dict[str, Any]:
        """Parse rsync output for statistics"""
        stats = {
            "files_transferred": 0,
            "bytes_transferred": 0,
            "total_size": 0,
            "speedup": 0.0
        }
        
        lines = output.split('\n')
        for line in lines:
            line = line.strip()
            try:
                if "Number of files transferred:" in line:
                    # Extract number, handling potential commas
                    num_str = line.split()[-1].replace(',', '')
                    if num_str.isdigit():
                        stats["files_transferred"] = int(num_str)
                elif "Total bytes transferred:" in line:
                    # Handle both "1,234,567" and "1,234,567 bytes" formats
                    parts = line.split()
                    for part in reversed(parts):
                        if part.replace(',', '').isdigit():
                            stats["bytes_transferred"] = int(part.replace(',', ''))
                            break
                elif "Total file size:" in line:
                    # Handle both "1,234,567" and "1,234,567 bytes" formats
                    parts = line.split()
                    for part in reversed(parts):
                        if part.replace(',', '').isdigit():
                            stats["total_size"] = int(part.replace(',', ''))
                            break
                elif "Literal data:" in line:
                    # Sometimes rsync reports literal data instead
                    parts = line.split()
                    if len(parts) >= 3:
                        bytes_str = parts[2].replace(',', '')
                        if bytes_str.isdigit():
                            stats["bytes_transferred"] = int(bytes_str)
            except (ValueError, IndexError):
                # Skip lines that can't be parsed
                continue
        
        return stats
    
    def _monitor_progress(self, process: subprocess.Popen, total_size: int = 0):
        """Monitor rsync progress in separate thread"""
        def progress_reader():
            while process.poll() is None:
                if self._is_cancelled:
                    break
                
                # Wait for pause event
                self._pause_event.wait()
                
                # Read progress from stderr
                if process.stderr:
                    try:
                        line = process.stderr.readline()
                        if line:
                            line = line.decode().strip()
                            if "%" in line and "bytes" in line:
                                # Parse progress line
                                progress = self.progress_tracker.parse_rsync_progress(line)
                                if progress and self._progress_callback:
                                    self._progress_callback(progress)
                    except:
                        pass
                
                time.sleep(0.1)
        
        thread = threading.Thread(target=progress_reader, daemon=True)
        thread.start()
        return thread
    
    def sync_file(self, source_path: str, destination_path: str, 
                  verify_integrity: bool = True) -> SyncResult:
        """Sync a single file with full error handling and verification"""
        
        source_path = str(Path(source_path).resolve())
        destination_path = str(Path(destination_path).resolve())
        
        # Pre-sync validation
        if not os.path.exists(source_path):
            return SyncResult(
                status=SyncStatus.FAILED,
                source_path=source_path,
                destination_path=destination_path,
                error_message=f"Source file not found: {source_path}"
            )
        
        # Create destination directory if needed
        dest_dir = os.path.dirname(destination_path)
        os.makedirs(dest_dir, exist_ok=True)
        
        start_time = time.time()
        
        # Get source file size for progress tracking
        source_size = os.path.getsize(source_path)
        
        # Start progress tracking
        progress = self.progress_tracker.start_transfer(
            source_path, destination_path, source_size
        )
        
        try:
            # Pre-sync integrity check
            source_checksum = None
            if verify_integrity:
                source_checksum = self.integrity_checker.calculate_checksum(source_path)
            
            # Execute sync with retry mechanism
            result = self.retry_manager.execute_with_retry(
                self._execute_sync_operation,
                source_path,
                destination_path,
                source_size
            )
            
            duration = time.time() - start_time
            
            # Post-sync verification
            checksum_verified = False
            if verify_integrity and source_checksum and os.path.exists(destination_path):
                dest_checksum = self.integrity_checker.calculate_checksum(destination_path)
                checksum_verified = source_checksum == dest_checksum
                
                if not checksum_verified:
                    return SyncResult(
                        status=SyncStatus.FAILED,
                        source_path=source_path,
                        destination_path=destination_path,
                        error_message="Checksum verification failed",
                        duration=duration
                    )
            
            # Parse result
            if result.get("success", False):
                return SyncResult(
                    status=SyncStatus.COMPLETED,
                    source_path=source_path,
                    destination_path=destination_path,
                    bytes_transferred=result.get("bytes_transferred", source_size),
                    files_transferred=1,
                    duration=duration,
                    checksum_verified=checksum_verified
                )
            else:
                return SyncResult(
                    status=SyncStatus.FAILED,
                    source_path=source_path,
                    destination_path=destination_path,
                    error_message=result.get("error", "Unknown sync error"),
                    duration=duration
                )
        
        except Exception as e:
            return SyncResult(
                status=SyncStatus.FAILED,
                source_path=source_path,
                destination_path=destination_path,
                error_message=str(e),
                duration=time.time() - start_time
            )
        
        finally:
            self.progress_tracker.finish_transfer(progress.transfer_id)
    
    def _execute_sync_operation(self, source_path: str, destination_path: str, 
                               total_size: int) -> Dict[str, Any]:
        """Execute the actual rsync operation"""
        
        if self._is_cancelled:
            return {"success": False, "error": "Operation cancelled"}
        
        # Build rsync command
        cmd = self._build_rsync_command(source_path, destination_path)
        
        try:
            # Execute rsync
            self._current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            # Monitor progress
            progress_thread = self._monitor_progress(self._current_process, total_size)
            
            # Wait for completion
            stdout, stderr = self._current_process.communicate()
            
            # Wait for progress thread to finish
            progress_thread.join(timeout=1.0)
            
            if self._current_process.returncode == 0:
                # Parse output for statistics
                stats = self._parse_rsync_output(stdout)
                return {
                    "success": True,
                    "bytes_transferred": stats["bytes_transferred"],
                    "files_transferred": stats["files_transferred"],
                    "output": stdout
                }
            else:
                return {
                    "success": False,
                    "error": f"rsync failed with code {self._current_process.returncode}: {stderr}",
                    "output": stdout,
                    "stderr": stderr
                }
        
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Sync operation timed out"}
        except Exception as e:
            return {"success": False, "error": f"Sync operation failed: {str(e)}"}
        
        finally:
            self._current_process = None
    
    def pause(self):
        """Pause the current sync operation"""
        self._pause_event.clear()
        if self._current_process:
            self._current_process.send_signal(signal.SIGSTOP)
    
    def resume(self):
        """Resume the paused sync operation"""
        self._pause_event.set()
        if self._current_process:
            self._current_process.send_signal(signal.SIGCONT)
    
    def cancel(self):
        """Cancel the current sync operation"""
        self._is_cancelled = True
        self._pause_event.set()  # Ensure progress thread can exit
        
        if self._current_process:
            try:
                self._current_process.terminate()
                self._current_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._current_process.kill()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current sync engine status"""
        return {
            "is_running": self._current_process is not None,
            "is_paused": not self._pause_event.is_set(),
            "is_cancelled": self._is_cancelled,
            "current_transfers": self.progress_tracker.get_active_transfers(),
            "options": self.options.__dict__
        } 