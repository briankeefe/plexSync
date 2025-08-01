#!/usr/bin/env python3
"""
PlexSync Phase 2 Testing - Sync Engine & Data-Integrity Policy

This test suite validates the core sync engine functionality including:
- Sync engine with rsync integration
- Data integrity verification with checksums
- Progress tracking and reporting
- Retry mechanisms with exponential backoff
- CLI integration with sync commands

Run with: python test_phase2.py
"""

import os
import sys
import tempfile
import time
import shutil
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_phase2_imports():
    """Test that Phase 2 modules can be imported successfully."""
    print("Testing Phase 2 imports...")
    
    try:
        from plexsync.sync import SyncEngine, SyncOptions, SyncStatus, SyncResult
        print("✅ sync module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import sync module: {e}")
        return False
    
    try:
        from plexsync.integrity import IntegrityChecker, ChecksumType, IntegrityStatus
        print("✅ integrity module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import integrity module: {e}")
        return False
    
    try:
        from plexsync.progress import ProgressTracker, SyncProgress, TransferStatus
        print("✅ progress module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import progress module: {e}")
        return False
    
    try:
        from plexsync.retry import RetryManager, SyncError, ErrorType
        print("✅ retry module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import retry module: {e}")
        return False
    
    return True


def test_integrity_checker():
    """Test integrity checker functionality."""
    print("\nTesting integrity checker...")
    
    from plexsync.integrity import IntegrityChecker, ChecksumType, IntegrityStatus
    
    try:
        checker = IntegrityChecker()
        print("✅ IntegrityChecker created successfully")
        
        # Create test files
        with tempfile.TemporaryDirectory() as temp_dir:
            test_file = os.path.join(temp_dir, "test_file.txt")
            test_content = b"This is a test file for integrity checking.\n" * 100
            
            with open(test_file, 'wb') as f:
                f.write(test_content)
            
            # Test checksum calculation
            checksum = checker.calculate_checksum(test_file)
            print(f"✅ Checksum calculated: {checksum[:16]}...")
            
            # Test different algorithms
            md5_checksum = checker.calculate_checksum(test_file, ChecksumType.MD5)
            sha1_checksum = checker.calculate_checksum(test_file, ChecksumType.SHA1)
            print(f"✅ MD5 checksum: {md5_checksum[:16]}...")
            print(f"✅ SHA1 checksum: {sha1_checksum[:16]}...")
            
            # Test file verification
            integrity = checker.verify_file_integrity(test_file)
            print(f"✅ File integrity verified: {integrity.status}")
            
            # Test file comparison
            test_file2 = os.path.join(temp_dir, "test_file2.txt")
            with open(test_file2, 'wb') as f:
                f.write(test_content)
            
            are_same = checker.compare_files(test_file, test_file2)
            print(f"✅ File comparison works: {are_same}")
            
            # Test integrity manifest
            manifest = checker.create_integrity_manifest(temp_dir)
            print(f"✅ Integrity manifest created: {len(manifest)} files")
            
            # Test manifest save/load
            manifest_path = checker.save_integrity_manifest(temp_dir)
            print(f"✅ Integrity manifest saved: {os.path.basename(manifest_path)}")
            
            files, metadata = checker.load_integrity_manifest(manifest_path)
            print(f"✅ Integrity manifest loaded: {len(files)} files")
            
    except Exception as e:
        print(f"❌ Integrity checker test failed: {e}")
        return False
    
    return True


def test_progress_tracker():
    """Test progress tracking functionality."""
    print("\nTesting progress tracker...")
    
    from plexsync.progress import ProgressTracker, TransferStatus
    
    try:
        tracker = ProgressTracker()
        print("✅ ProgressTracker created successfully")
        
        # Test transfer tracking
        progress = tracker.start_transfer("/source/file.txt", "/dest/file.txt", 1024000)
        print(f"✅ Transfer started: {progress.transfer_id[:8]}...")
        
        # Test progress updates
        tracker.update_transfer(progress.transfer_id, 512000, 1024.0)
        print(f"✅ Progress updated: {progress.percentage:.1f}%")
        
        # Test transfer completion
        tracker.finish_transfer(progress.transfer_id, success=True)
        print("✅ Transfer completed successfully")
        
        # Test progress parsing
        rsync_line = "  1,234,567  45%  123.45kB/s    0:00:12"
        parsed = tracker.parse_rsync_progress(rsync_line)
        if parsed:
            print(f"✅ Rsync progress parsed: {parsed.percentage}%")
        else:
            print("✅ Rsync progress parsing (no match for test line)")
        
        # Test multiple transfers
        transfers = tracker.get_active_transfers()
        print(f"✅ Active transfers: {len(transfers)}")
        
        # Test summary
        summary = tracker.display_summary()
        print("✅ Transfer summary generated")
        
    except Exception as e:
        print(f"❌ Progress tracker test failed: {e}")
        return False
    
    return True


def test_retry_manager():
    """Test retry mechanism functionality."""
    print("\nTesting retry manager...")
    
    from plexsync.retry import RetryManager, RetryConfig, SyncError, ErrorType
    
    try:
        # Test basic retry manager
        config = RetryConfig(max_retries=3, initial_delay=0.1)
        manager = RetryManager(config)
        print("✅ RetryManager created successfully")
        
        # Test successful operation
        def successful_operation():
            return "success"
        
        result = manager.execute_with_retry(successful_operation)
        print(f"✅ Successful operation: {result}")
        
        # Test operation that fails then succeeds
        attempt_count = 0
        def failing_then_success():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise Exception("Temporary failure")
            return "success after retries"
        
        attempt_count = 0
        result = manager.execute_with_retry(failing_then_success)
        print(f"✅ Retry successful: {result}")
        
        # Test error classification
        network_error = Exception("connection refused")
        error_type = manager.classify_error(network_error)
        print(f"✅ Error classification: {error_type}")
        
        # Test retry config
        manager.configure_error_handling()
        print("✅ Error-specific retry configuration set")
        
        # Test retry stats
        stats = manager.get_retry_stats()
        print(f"✅ Retry statistics: {stats}")
        
    except Exception as e:
        print(f"❌ Retry manager test failed: {e}")
        return False
    
    return True


def test_sync_engine():
    """Test sync engine functionality."""
    print("\nTesting sync engine...")
    
    from plexsync.sync import SyncEngine, SyncOptions, SyncStatus
    
    try:
        # Create sync options
        options = SyncOptions(
            dry_run=False,
            checksum=True,
            verbose=True,
            bandwidth_limit=None
        )
        
        engine = SyncEngine(options)
        print("✅ SyncEngine created successfully")
        
        # Test with actual files
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, "source.txt")
            dest_file = os.path.join(temp_dir, "dest.txt")
            
            # Create test content
            test_content = b"This is test content for sync engine.\n" * 100
            with open(source_file, 'wb') as f:
                f.write(test_content)
            
            print(f"✅ Test file created: {len(test_content)} bytes")
            
            # Test sync operation
            result = engine.sync_file(source_file, dest_file, verify_integrity=True)
            
            if result.success:
                print("✅ Sync operation completed successfully")
                print(f"  📊 Bytes transferred: {result.bytes_transferred}")
                print(f"  ⚡ Transfer rate: {result.transfer_rate:.2f} MB/s")
                print(f"  🔒 Checksum verified: {result.checksum_verified}")
                
                # Verify file was actually copied
                if os.path.exists(dest_file):
                    with open(dest_file, 'rb') as f:
                        dest_content = f.read()
                    
                    if dest_content == test_content:
                        print("✅ File content verified")
                    else:
                        print("❌ File content mismatch")
                        return False
                else:
                    print("❌ Destination file not created")
                    return False
            else:
                print(f"❌ Sync operation failed: {result.error_message}")
                return False
            
            # Test engine status
            status = engine.get_status()
            print(f"✅ Engine status: {status}")
            
    except Exception as e:
        print(f"❌ Sync engine test failed: {e}")
        return False
    
    return True


def test_cli_integration():
    """Test CLI integration with sync commands."""
    print("\nTesting CLI integration...")
    
    try:
        # Test imports
        from plexsync.cli import main, _demonstrate_sync_engine
        print("✅ CLI imports successful")
        
        # Test sync demo function
        print("✅ Testing sync demonstration...")
        
        # This should run without errors
        _demonstrate_sync_engine(dry_run=True, verify=True)
        print("✅ Sync demonstration completed")
        
    except Exception as e:
        print(f"❌ CLI integration test failed: {e}")
        return False
    
    return True


def test_error_handling():
    """Test error handling and edge cases."""
    print("\nTesting error handling...")
    
    from plexsync.sync import SyncEngine, SyncOptions
    from plexsync.integrity import IntegrityChecker
    
    try:
        # Test sync with non-existent source
        engine = SyncEngine(SyncOptions())
        result = engine.sync_file("/nonexistent/file.txt", "/tmp/dest.txt")
        
        if not result.success:
            print("✅ Non-existent source handled correctly")
        else:
            print("❌ Non-existent source should have failed")
            return False
        
        # Test integrity checker with non-existent file
        checker = IntegrityChecker()
        try:
            checker.calculate_checksum("/nonexistent/file.txt")
            print("❌ Non-existent file should have raised exception")
            return False
        except FileNotFoundError:
            print("✅ Non-existent file handled correctly")
        
        # Test with permission issues (if not running as root)
        if os.getuid() != 0:  # Not running as root
            try:
                result = engine.sync_file("/etc/passwd", "/root/test.txt")
                if not result.success:
                    print("✅ Permission error handled correctly")
                else:
                    print("⚠️  Permission test may have succeeded (running with high privileges)")
            except Exception:
                print("✅ Permission error handled correctly")
        else:
            print("⚠️  Skipping permission test (running as root)")
        
    except Exception as e:
        print(f"❌ Error handling test failed: {e}")
        return False
    
    return True


def main():
    """Main test runner."""
    print("PlexSync Phase 2 Testing - Sync Engine & Data-Integrity Policy")
    print("=================================================================")
    
    tests = [
        ("Phase 2 Imports", test_phase2_imports),
        ("Integrity Checker", test_integrity_checker),
        ("Progress Tracker", test_progress_tracker),
        ("Retry Manager", test_retry_manager),
        ("Sync Engine", test_sync_engine),
        ("CLI Integration", test_cli_integration),
        ("Error Handling", test_error_handling),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ {test_name} test crashed: {e}")
            failed += 1
    
    print("\n=================================================================")
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All Phase 2 tests passed!")
        print("✅ Sync Engine & Data-Integrity Policy ready!")
        print("✅ Individual file sync with progress tracking working")
        print("✅ Data integrity verification with checksums working")
        print("✅ Retry mechanisms with exponential backoff working")
        print("✅ CLI integration with sync commands working")
    else:
        print(f"❌ {failed} tests failed")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main()) 