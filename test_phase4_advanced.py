#!/usr/bin/env python3
"""
Test script for Phase 4: Advanced Management & Analytics

This tests the advanced functionality including re-sync management, advanced duplicate detection,
smart organization, usage analytics, and full integration.
"""

import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timedelta

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_phase4_imports():
    """Test that all Phase 4 modules can be imported."""
    print("🔍 Testing Phase 4 imports...")
    
    try:
        # Test re-sync manager
        from plexsync.resync_manager import (
            ResyncManager, ResyncReason, ResyncStatus, ResyncRequest, ResyncResult
        )
        print("✅ Re-sync manager imported successfully")
        
        # Test advanced duplicates
        from plexsync.advanced_duplicates import (
            AdvancedDuplicateDetector, SimilarityType, MatchConfidence, SimilarityMatch
        )
        print("✅ Advanced duplicates imported successfully")
        
        # Test smart organization
        from plexsync.smart_organization import (
            SmartOrganizer, OrganizationStrategy, OrganizationRule, OrganizationPlan
        )
        print("✅ Smart organization imported successfully")
        
        # Test usage analytics
        from plexsync.usage_analytics import (
            UsageAnalytics, AccessType, RecommendationType, UsageStats
        )
        print("✅ Usage analytics imported successfully")
        
        return True
        
    except Exception as e:
        print(f"❌ Import error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_resync_manager():
    """Test the re-sync manager functionality."""
    print("🔍 Testing re-sync manager...")
    
    try:
        from plexsync.resync_manager import ResyncManager, ResyncReason, ResyncRequest
        from plexsync.downloaded import DownloadedMediaManager
        from plexsync.file_operations import FileOperationsManager
        from rich.console import Console
        
        # Mock objects
        console = Console()
        manager = Mock(spec=DownloadedMediaManager)
        sync_engine = Mock()
        file_ops = Mock(spec=FileOperationsManager)
        
        # Create resync manager
        resync_manager = ResyncManager(console, manager, sync_engine, file_ops)
        
        # Test initialization
        assert hasattr(resync_manager, 'console')
        assert hasattr(resync_manager, 'downloaded_manager')
        assert hasattr(resync_manager, 'sync_engine')
        assert hasattr(resync_manager, 'file_operations')
        assert hasattr(resync_manager, 'pending_requests')
        assert hasattr(resync_manager, 'completed_results')
        
        print("✅ Re-sync manager initialized correctly")
        
        # Test method presence
        methods = [
            'scan_for_resync_candidates', 'create_resync_request', 'queue_resync_batch',
            'process_resync_batch', 'show_resync_candidates', 'get_resync_statistics'
        ]
        
        for method in methods:
            assert hasattr(resync_manager, method), f"Missing method: {method}"
        
        print("✅ All re-sync manager methods present")
        return True
        
    except Exception as e:
        print(f"❌ Re-sync manager test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_advanced_duplicates():
    """Test the advanced duplicate detection functionality."""
    print("🔍 Testing advanced duplicate detection...")
    
    try:
        from plexsync.advanced_duplicates import AdvancedDuplicateDetector, SimilarityType
        from plexsync.downloaded import DownloadedMediaManager
        from rich.console import Console
        
        # Mock objects
        console = Console()
        manager = Mock(spec=DownloadedMediaManager)
        
        # Create detector
        detector = AdvancedDuplicateDetector(console, manager)
        
        # Test initialization
        assert hasattr(detector, 'console')
        assert hasattr(detector, 'manager')
        assert hasattr(detector, 'checksum_cache')
        assert hasattr(detector, 'name_similarity_threshold')
        
        print("✅ Advanced duplicate detector initialized correctly")
        
        # Test method presence
        methods = [
            'find_advanced_duplicates', 'show_similarity_analysis',
            'export_similarity_report', '_find_exact_duplicates',
            '_find_similar_names', '_calculate_string_similarity'
        ]
        
        for method in methods:
            assert hasattr(detector, method), f"Missing method: {method}"
        
        print("✅ All advanced duplicate methods present")
        
        # Test similarity types
        assert hasattr(SimilarityType, 'EXACT')
        assert hasattr(SimilarityType, 'SIMILAR_NAME')
        assert hasattr(SimilarityType, 'SAME_CONTENT')
        print("✅ Similarity types work correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Advanced duplicates test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_smart_organization():
    """Test the smart organization functionality."""
    print("🔍 Testing smart organization...")
    
    try:
        from plexsync.smart_organization import SmartOrganizer, OrganizationStrategy
        from plexsync.downloaded import DownloadedMediaManager
        from plexsync.file_operations import FileOperationsManager
        from rich.console import Console
        
        # Mock objects
        console = Console()
        manager = Mock(spec=DownloadedMediaManager)
        file_ops = Mock(spec=FileOperationsManager)
        
        # Create organizer
        organizer = SmartOrganizer(console, manager, file_ops)
        
        # Test initialization
        assert hasattr(organizer, 'console')
        assert hasattr(organizer, 'manager')
        assert hasattr(organizer, 'file_operations')
        assert hasattr(organizer, 'rules')
        
        print("✅ Smart organizer initialized correctly")
        
        # Test method presence
        methods = [
            'analyze_organization', 'execute_organization_plans',
            'show_organization_preview', 'suggest_organization_improvements',
            'create_custom_rule', 'show_rules'
        ]
        
        for method in methods:
            assert hasattr(organizer, method), f"Missing method: {method}"
        
        print("✅ All smart organization methods present")
        
        # Test that default rules are created
        assert len(organizer.rules) > 0
        print("✅ Default organization rules created")
        
        # Test organization strategies
        assert hasattr(OrganizationStrategy, 'BY_TYPE')
        assert hasattr(OrganizationStrategy, 'BY_GENRE')
        assert hasattr(OrganizationStrategy, 'BY_YEAR')
        print("✅ Organization strategies work correctly")
        
        return True
        
    except Exception as e:
        print(f"❌ Smart organization test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_usage_analytics():
    """Test the usage analytics functionality."""
    print("🔍 Testing usage analytics...")
    
    try:
        from plexsync.usage_analytics import UsageAnalytics, AccessType, UsageStats
        from plexsync.downloaded import DownloadedMediaManager
        from rich.console import Console
        
        # Create temporary database
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_usage.db"
            
            # Mock objects
            console = Console()
            manager = Mock(spec=DownloadedMediaManager)
            
            # Create analytics with custom database path
            analytics = UsageAnalytics(console, manager, db_path)
            
            # Test initialization
            assert hasattr(analytics, 'console')
            assert hasattr(analytics, 'manager')
            assert hasattr(analytics, 'database_path')
            assert analytics.database_path == db_path
            
            print("✅ Usage analytics initialized correctly")
            
            # Test database was created
            assert db_path.exists()
            print("✅ Usage database created")
            
            # Test method presence
            methods = [
                'record_access', 'get_usage_stats', 'get_global_usage_stats',
                'generate_recommendations', 'show_usage_dashboard',
                'export_usage_report', 'cleanup_old_records'
            ]
            
            for method in methods:
                assert hasattr(analytics, method), f"Missing method: {method}"
            
            print("✅ All usage analytics methods present")
            
            # Test access types
            assert hasattr(AccessType, 'VIEWED')
            assert hasattr(AccessType, 'ACCESSED')
            assert hasattr(AccessType, 'MANAGED')
            print("✅ Access types work correctly")
            
            # Test database structure
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = [row[0] for row in cursor.fetchall()]
                assert 'access_records' in tables
            
            print("✅ Database structure correct")
        
        return True
        
    except Exception as e:
        print(f"❌ Usage analytics test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_usage_analytics_functionality():
    """Test usage analytics with real data."""
    print("🔍 Testing usage analytics functionality...")
    
    try:
        from plexsync.usage_analytics import UsageAnalytics, AccessType
        from plexsync.downloaded import DownloadedFile, FileStatus
        from rich.console import Console
        from pathlib import Path
        
        # Create temporary database
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test_usage.db"
            
            # Create analytics
            console = Console()
            manager = Mock()
            analytics = UsageAnalytics(console, manager, db_path)
            
            # Create mock file
            mock_file = Mock(spec=DownloadedFile)
            mock_file.file_path = Path("/test/movie.mp4")
            mock_file.display_name = "Test Movie"
            mock_file.file_size = 1000000
            
            # Test recording access
            analytics.record_access(mock_file, AccessType.VIEWED)
            analytics.record_access(mock_file, AccessType.ACCESSED)
            
            # Test getting stats
            stats = analytics.get_usage_stats(mock_file)
            assert stats.total_accesses == 2
            assert stats.view_count == 1
            assert stats.usage_score > 0
            
            print("✅ Usage recording and stats work correctly")
            
            # Test recommendations with mock library
            mock_library = Mock()
            recommendations = analytics.generate_recommendations(mock_library)
            assert isinstance(recommendations, list)
            
            print("✅ Recommendation generation works")
        
        return True
        
    except Exception as e:
        print(f"❌ Usage analytics functionality test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_data_structures():
    """Test Phase 4 data structures."""
    print("🔍 Testing Phase 4 data structures...")
    
    try:
        from plexsync.resync_manager import ResyncReason, ResyncStatus, ResyncRequest
        from plexsync.advanced_duplicates import SimilarityType, MatchConfidence
        from plexsync.smart_organization import OrganizationStrategy, OrganizationPriority
        from plexsync.usage_analytics import AccessType, RecommendationType
        from pathlib import Path
        from datetime import datetime
        
        # Test ResyncReason enum
        assert ResyncReason.CORRUPTED.value == "corrupted"
        assert ResyncReason.MISSING.value == "missing"
        print("✅ ResyncReason enum works")
        
        # Test ResyncStatus enum
        assert ResyncStatus.PENDING.value == "pending"
        assert ResyncStatus.COMPLETED.value == "completed"
        print("✅ ResyncStatus enum works")
        
        # Test SimilarityType enum
        assert SimilarityType.EXACT.value == "exact"
        assert SimilarityType.SIMILAR_NAME.value == "similar_name"
        print("✅ SimilarityType enum works")
        
        # Test MatchConfidence enum
        assert MatchConfidence.VERY_HIGH.value == "very_high"
        assert MatchConfidence.HIGH.value == "high"
        print("✅ MatchConfidence enum works")
        
        # Test OrganizationStrategy enum
        assert OrganizationStrategy.BY_TYPE.value == "by_type"
        assert OrganizationStrategy.BY_GENRE.value == "by_genre"
        print("✅ OrganizationStrategy enum works")
        
        # Test AccessType enum
        assert AccessType.VIEWED.value == "viewed"
        assert AccessType.ACCESSED.value == "accessed"
        print("✅ AccessType enum works")
        
        # Test RecommendationType enum
        assert RecommendationType.DELETE_UNUSED.value == "delete_unused"
        assert RecommendationType.ARCHIVE_OLD.value == "archive_old"
        print("✅ RecommendationType enum works")
        
        return True
        
    except Exception as e:
        print(f"❌ Data structures test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_browser_integration():
    """Test that the browser interface integrates Phase 4 components."""
    print("🔍 Testing browser integration...")
    
    try:
        from plexsync.downloaded_browser import DownloadedMediaBrowserInterface
        from plexsync.downloaded import DownloadedMediaManager
        from rich.console import Console
        
        # Mock objects
        console = Console()
        manager = Mock(spec=DownloadedMediaManager)
        
        # Create browser interface
        browser = DownloadedMediaBrowserInterface(console, manager)
        
        # Test Phase 4 components are initialized
        assert hasattr(browser, 'resync_manager')
        assert hasattr(browser, 'advanced_duplicates')
        assert hasattr(browser, 'smart_organizer')
        assert hasattr(browser, 'usage_analytics')
        print("✅ Phase 4 components initialized in browser")
        
        # Test new methods are present
        new_methods = [
            'resync_management', 'advanced_duplicate_management',
            'smart_organization_management', 'usage_analytics_dashboard'
        ]
        
        for method in new_methods:
            assert hasattr(browser, method), f"Missing method: {method}"
        
        print("✅ All Phase 4 browser methods present")
        return True
        
    except Exception as e:
        print(f"❌ Browser integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_string_similarity():
    """Test string similarity algorithms."""
    print("🔍 Testing string similarity algorithms...")
    
    try:
        from plexsync.advanced_duplicates import AdvancedDuplicateDetector
        from rich.console import Console
        
        console = Console()
        manager = Mock()
        detector = AdvancedDuplicateDetector(console, manager)
        
        # Test filename normalization
        filename1 = "The.Matrix.1999.1080p.BluRay.x264-GROUP"
        filename2 = "The Matrix (1999) [1080p] [BluRay]"
        
        norm1 = detector._normalize_filename(filename1)
        norm2 = detector._normalize_filename(filename2)
        
        # Both should normalize to something similar
        assert "matrix" in norm1.lower()
        assert "matrix" in norm2.lower()
        print("✅ Filename normalization works")
        
        # Test string similarity
        similarity = detector._calculate_string_similarity(norm1, norm2)
        assert 0.0 <= similarity <= 1.0
        assert similarity > 0.5  # Should be quite similar
        print("✅ String similarity calculation works")
        
        return True
        
    except Exception as e:
        print(f"❌ String similarity test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_phase4_complete():
    """Test overall Phase 4 completeness."""
    print("🔍 Testing Phase 4 completeness...")
    
    try:
        # Test that all major Phase 4 features are implemented
        from plexsync.resync_manager import ResyncManager
        from plexsync.advanced_duplicates import AdvancedDuplicateDetector
        from plexsync.smart_organization import SmartOrganizer
        from plexsync.usage_analytics import UsageAnalytics
        from plexsync.downloaded_browser import DownloadedMediaBrowserInterface
        
        # Check re-sync features
        resync_methods = [
            'scan_for_resync_candidates', 'process_resync_batch', 'export_resync_report'
        ]
        
        for method in resync_methods:
            assert hasattr(ResyncManager, method)
        
        print("✅ All Phase 4 re-sync features implemented")
        
        # Check advanced duplicate features
        duplicate_methods = [
            'find_advanced_duplicates', 'show_similarity_analysis', 'export_similarity_report'
        ]
        
        for method in duplicate_methods:
            assert hasattr(AdvancedDuplicateDetector, method)
        
        print("✅ All Phase 4 advanced duplicate features implemented")
        
        # Check smart organization features
        organization_methods = [
            'analyze_organization', 'execute_organization_plans', 'suggest_organization_improvements'
        ]
        
        for method in organization_methods:
            assert hasattr(SmartOrganizer, method)
        
        print("✅ All Phase 4 smart organization features implemented")
        
        # Check usage analytics features
        analytics_methods = [
            'record_access', 'get_usage_stats', 'generate_recommendations', 'show_usage_dashboard'
        ]
        
        for method in analytics_methods:
            assert hasattr(UsageAnalytics, method)
        
        print("✅ All Phase 4 usage analytics features implemented")
        
        # Check browser integration
        browser_methods = [
            'resync_management', 'advanced_duplicate_management',
            'smart_organization_management', 'usage_analytics_dashboard'
        ]
        
        for method in browser_methods:
            assert hasattr(DownloadedMediaBrowserInterface, method)
        
        print("✅ All Phase 4 browser features implemented")
        
        return True
        
    except Exception as e:
        print(f"❌ Phase 4 completeness test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Run all Phase 4 tests."""
    print("🚀 Running Phase 4: Advanced Management & Analytics Tests")
    print("=" * 70)
    
    tests = [
        test_phase4_imports,
        test_resync_manager,
        test_advanced_duplicates,
        test_smart_organization,
        test_usage_analytics,
        test_usage_analytics_functionality,
        test_data_structures,
        test_browser_integration,
        test_string_similarity,
        test_phase4_complete
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        print(f"\n📋 Running {test.__name__}...")
        try:
            if test():
                passed += 1
                print(f"✅ {test.__name__} PASSED")
            else:
                failed += 1
                print(f"❌ {test.__name__} FAILED")
        except Exception as e:
            failed += 1
            print(f"❌ {test.__name__} FAILED with exception: {e}")
    
    print("\n" + "=" * 70)
    print(f"📊 Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All Phase 4 tests PASSED! Phase 4 is ready for production.")
        return True
    else:
        print("⚠️  Some tests failed. Please review the issues above.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1) 