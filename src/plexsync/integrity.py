"""
PlexSync - Data Integrity
File integrity verification with checksums, validation, and corruption detection.
"""

import hashlib
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json


class ChecksumType(Enum):
    """Supported checksum algorithms"""
    MD5 = "md5"
    SHA1 = "sha1"
    SHA256 = "sha256"
    SHA512 = "sha512"
    CRC32 = "crc32"


class IntegrityStatus(Enum):
    """File integrity status"""
    VALID = "valid"
    CORRUPTED = "corrupted"
    MISSING = "missing"
    CHANGED = "changed"
    UNKNOWN = "unknown"


@dataclass
class FileIntegrity:
    """File integrity information"""
    file_path: str
    file_size: int
    checksum: str
    checksum_type: ChecksumType
    timestamp: float
    status: IntegrityStatus = IntegrityStatus.UNKNOWN
    
    @property
    def checksum_short(self) -> str:
        """Short version of checksum for display"""
        return self.checksum[:16] + "..." if len(self.checksum) > 16 else self.checksum


@dataclass
class IntegrityReport:
    """Integrity verification report"""
    total_files: int
    valid_files: int
    corrupted_files: int
    missing_files: int
    changed_files: int
    total_size: int
    verification_time: float
    
    @property
    def success_rate(self) -> float:
        """Percentage of files that passed verification"""
        return (self.valid_files / self.total_files * 100) if self.total_files > 0 else 0.0
    
    @property
    def has_issues(self) -> bool:
        """Whether any integrity issues were found"""
        return self.corrupted_files > 0 or self.missing_files > 0


class IntegrityChecker:
    """File integrity checker with multiple checksum algorithms"""
    
    def __init__(self, default_algorithm: ChecksumType = ChecksumType.SHA256):
        self.default_algorithm = default_algorithm
        self.chunk_size = 8192 * 1024  # 8MB chunks for large files
        self._integrity_cache: Dict[str, FileIntegrity] = {}
    
    def calculate_checksum(self, file_path: str, 
                          algorithm: ChecksumType = None) -> str:
        """Calculate checksum for a file"""
        algorithm = algorithm or self.default_algorithm
        
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Get hasher
        hasher = self._get_hasher(algorithm)
        
        # Calculate checksum in chunks to handle large files
        try:
            with open(file_path, 'rb') as f:
                while chunk := f.read(self.chunk_size):
                    hasher.update(chunk)
            
            return hasher.hexdigest()
        
        except Exception as e:
            raise RuntimeError(f"Failed to calculate checksum for {file_path}: {str(e)}")
    
    def _get_hasher(self, algorithm: ChecksumType):
        """Get hasher instance for algorithm"""
        if algorithm == ChecksumType.MD5:
            return hashlib.md5()
        elif algorithm == ChecksumType.SHA1:
            return hashlib.sha1()
        elif algorithm == ChecksumType.SHA256:
            return hashlib.sha256()
        elif algorithm == ChecksumType.SHA512:
            return hashlib.sha512()
        elif algorithm == ChecksumType.CRC32:
            # CRC32 is not in hashlib, we'll use a simple implementation
            import zlib
            class CRC32Hasher:
                def __init__(self):
                    self.crc = 0
                def update(self, data):
                    self.crc = zlib.crc32(data, self.crc)
                def hexdigest(self):
                    return f"{self.crc & 0xffffffff:08x}"
            return CRC32Hasher()
        else:
            raise ValueError(f"Unsupported checksum algorithm: {algorithm}")
    
    def verify_file_integrity(self, file_path: str, 
                             expected_checksum: str = None,
                             algorithm: ChecksumType = None) -> FileIntegrity:
        """Verify integrity of a single file"""
        
        file_path = str(Path(file_path).resolve())
        algorithm = algorithm or self.default_algorithm
        
        if not os.path.exists(file_path):
            return FileIntegrity(
                file_path=file_path,
                file_size=0,
                checksum="",
                checksum_type=algorithm,
                timestamp=time.time(),
                status=IntegrityStatus.MISSING
            )
        
        # Get file stats
        file_size = os.path.getsize(file_path)
        
        # Calculate current checksum
        try:
            current_checksum = self.calculate_checksum(file_path, algorithm)
        except Exception:
            return FileIntegrity(
                file_path=file_path,
                file_size=file_size,
                checksum="",
                checksum_type=algorithm,
                timestamp=time.time(),
                status=IntegrityStatus.CORRUPTED
            )
        
        # Determine status
        if expected_checksum:
            if current_checksum == expected_checksum:
                status = IntegrityStatus.VALID
            else:
                status = IntegrityStatus.CORRUPTED
        else:
            # No expected checksum, assume valid if we could calculate it
            status = IntegrityStatus.VALID
        
        return FileIntegrity(
            file_path=file_path,
            file_size=file_size,
            checksum=current_checksum,
            checksum_type=algorithm,
            timestamp=time.time(),
            status=status
        )
    
    def compare_files(self, file1_path: str, file2_path: str,
                     algorithm: ChecksumType = None) -> bool:
        """Compare two files using checksums"""
        
        try:
            checksum1 = self.calculate_checksum(file1_path, algorithm)
            checksum2 = self.calculate_checksum(file2_path, algorithm)
            return checksum1 == checksum2
        except Exception:
            return False
    
    def verify_directory_integrity(self, directory_path: str,
                                  integrity_manifest: Dict[str, str] = None,
                                  algorithm: ChecksumType = None) -> IntegrityReport:
        """Verify integrity of all files in a directory"""
        
        directory_path = str(Path(directory_path).resolve())
        algorithm = algorithm or self.default_algorithm
        
        if not os.path.exists(directory_path):
            return IntegrityReport(
                total_files=0,
                valid_files=0,
                corrupted_files=0,
                missing_files=0,
                changed_files=0,
                total_size=0,
                verification_time=0.0
            )
        
        start_time = time.time()
        
        # Get all files in directory
        files_to_check = []
        for root, _, files in os.walk(directory_path):
            for file in files:
                files_to_check.append(os.path.join(root, file))
        
        # Verify each file
        report_stats = {
            "total_files": len(files_to_check),
            "valid_files": 0,
            "corrupted_files": 0,
            "missing_files": 0,
            "changed_files": 0,
            "total_size": 0
        }
        
        for file_path in files_to_check:
            try:
                file_size = os.path.getsize(file_path)
                report_stats["total_size"] += file_size
                
                # Get expected checksum from manifest
                relative_path = os.path.relpath(file_path, directory_path)
                expected_checksum = None
                if integrity_manifest:
                    expected_checksum = integrity_manifest.get(relative_path)
                
                # Verify file
                integrity = self.verify_file_integrity(file_path, expected_checksum, algorithm)
                
                if integrity.status == IntegrityStatus.VALID:
                    report_stats["valid_files"] += 1
                elif integrity.status == IntegrityStatus.CORRUPTED:
                    report_stats["corrupted_files"] += 1
                elif integrity.status == IntegrityStatus.MISSING:
                    report_stats["missing_files"] += 1
                elif integrity.status == IntegrityStatus.CHANGED:
                    report_stats["changed_files"] += 1
                
                # Cache integrity info
                self._integrity_cache[file_path] = integrity
                
            except Exception:
                report_stats["corrupted_files"] += 1
        
        verification_time = time.time() - start_time
        
        return IntegrityReport(
            total_files=report_stats["total_files"],
            valid_files=report_stats["valid_files"],
            corrupted_files=report_stats["corrupted_files"],
            missing_files=report_stats["missing_files"],
            changed_files=report_stats["changed_files"],
            total_size=report_stats["total_size"],
            verification_time=verification_time
        )
    
    def create_integrity_manifest(self, directory_path: str,
                                 algorithm: ChecksumType = None) -> Dict[str, str]:
        """Create integrity manifest for a directory"""
        
        directory_path = str(Path(directory_path).resolve())
        algorithm = algorithm or self.default_algorithm
        
        manifest = {}
        
        if not os.path.exists(directory_path):
            return manifest
        
        # Calculate checksums for all files
        for root, _, files in os.walk(directory_path):
            for file in files:
                file_path = os.path.join(root, file)
                relative_path = os.path.relpath(file_path, directory_path)
                
                try:
                    checksum = self.calculate_checksum(file_path, algorithm)
                    manifest[relative_path] = checksum
                except Exception:
                    # Skip files that can't be read
                    continue
        
        return manifest
    
    def save_integrity_manifest(self, directory_path: str, 
                               manifest_path: str = None,
                               algorithm: ChecksumType = None) -> str:
        """Save integrity manifest to file"""
        
        manifest = self.create_integrity_manifest(directory_path, algorithm)
        
        if manifest_path is None:
            manifest_path = os.path.join(directory_path, ".plexsync_integrity.json")
        
        # Include metadata
        manifest_data = {
            "version": "1.0",
            "created": time.time(),
            "directory": directory_path,
            "algorithm": (algorithm or self.default_algorithm).value,
            "files": manifest
        }
        
        with open(manifest_path, 'w') as f:
            json.dump(manifest_data, f, indent=2)
        
        return manifest_path
    
    def load_integrity_manifest(self, manifest_path: str) -> Tuple[Dict[str, str], Dict[str, Any]]:
        """Load integrity manifest from file"""
        
        if not os.path.exists(manifest_path):
            return {}, {}
        
        try:
            with open(manifest_path, 'r') as f:
                data = json.load(f)
            
            files = data.get("files", {})
            metadata = {
                "version": data.get("version", "1.0"),
                "created": data.get("created", 0),
                "directory": data.get("directory", ""),
                "algorithm": data.get("algorithm", self.default_algorithm.value)
            }
            
            return files, metadata
        
        except Exception:
            return {}, {}
    
    def get_cached_integrity(self, file_path: str) -> Optional[FileIntegrity]:
        """Get cached integrity information"""
        return self._integrity_cache.get(file_path)
    
    def clear_cache(self):
        """Clear integrity cache"""
        self._integrity_cache.clear()
    
    def estimate_checksum_time(self, file_size: int, 
                              algorithm: ChecksumType = None) -> float:
        """Estimate time to calculate checksum based on file size"""
        algorithm = algorithm or self.default_algorithm
        
        # Rough estimates based on typical performance (MB/s)
        speed_estimates = {
            ChecksumType.MD5: 500,      # ~500 MB/s
            ChecksumType.SHA1: 400,     # ~400 MB/s
            ChecksumType.SHA256: 200,   # ~200 MB/s
            ChecksumType.SHA512: 150,   # ~150 MB/s
            ChecksumType.CRC32: 800,    # ~800 MB/s
        }
        
        speed_mbps = speed_estimates.get(algorithm, 200)
        file_size_mb = file_size / (1024 * 1024)
        
        return file_size_mb / speed_mbps
    
    def quick_verify(self, file_path: str, expected_size: int) -> bool:
        """Quick verification using file size only"""
        try:
            if not os.path.exists(file_path):
                return False
            
            actual_size = os.path.getsize(file_path)
            return actual_size == expected_size
        
        except Exception:
            return False 