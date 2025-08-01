#!/usr/bin/env python3
"""
Test script for Phase 0 functionality.
Tests basic imports and functionality without external dependencies.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_basic_imports():
    """Test that basic modules can be imported."""
    print("Testing basic imports...")
    
    try:
        import plexsync
        print(f"✅ plexsync imported successfully, version: {plexsync.__version__}")
    except ImportError as e:
        print(f"❌ Failed to import plexsync: {e}")
        return False
    
    try:
        from plexsync.compatibility import CompatibilityMatrix, PlatformSupport
        print("✅ compatibility module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import compatibility: {e}")
        return False
    
    try:
        from plexsync.datasets import MediaDiscovery, MediaType, TestDatasetSize
        print("✅ datasets module imported successfully")
    except ImportError as e:
        print(f"❌ Failed to import datasets: {e}")
        return False
    
    return True

def test_compatibility_matrix():
    """Test compatibility matrix functionality."""
    print("\nTesting compatibility matrix...")
    
    try:
        from plexsync.compatibility import CompatibilityMatrix
        
        # Test version comparison
        assert CompatibilityMatrix._version_meets_minimum("3.2.1", "3.2.0") == True
        assert CompatibilityMatrix._version_meets_minimum("3.1.9", "3.2.0") == False
        assert CompatibilityMatrix._version_meets_minimum(None, "3.2.0") == False
        print("✅ Version comparison tests passed")
        
        # Test platform detection
        platform_info = CompatibilityMatrix.detect_platform_info()
        print(f"✅ Platform detection successful: {platform_info.os_name} {platform_info.python_version}")
        
        # Test compatibility report
        report = CompatibilityMatrix.get_compatibility_report()
        assert "platform" in report
        assert "python" in report
        assert "terminal" in report
        assert "rsync" in report
        print("✅ Compatibility report generation successful")
        
        return True
        
    except Exception as e:
        print(f"❌ Compatibility matrix test failed: {e}")
        return False

def test_media_discovery():
    """Test media discovery functionality."""
    print("\nTesting media discovery...")
    
    try:
        from plexsync.datasets import (
            MediaDiscovery, MediaType, MediaSource, MediaItem, 
            get_default_media_sources, TEST_DATASETS, TestDatasetSize
        )
        
        # Test media source creation
        source = MediaSource(
            name="Test Movies",
            base_path="/tmp/test",
            media_type=MediaType.MOVIE,
            enabled=True
        )
        assert source.name == "Test Movies"
        assert source.media_type == MediaType.MOVIE
        print("✅ MediaSource creation works")
        
        # Test default sources
        default_sources = get_default_media_sources()
        assert len(default_sources) == 4  # 2 movie + 2 TV sources
        
        movie_sources = [s for s in default_sources if s.media_type == MediaType.MOVIE]
        tv_sources = [s for s in default_sources if s.media_type == MediaType.TV_SHOW]
        assert len(movie_sources) == 2
        assert len(tv_sources) == 2
        print("✅ Default media sources configured correctly")
        
        # Test media item creation
        movie = MediaItem(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            source_path="/tmp/test/movie.mkv",
            relative_path="movie.mkv",
            file_size=1000000,
            file_extension=".mkv"
        )
        assert movie.title == "Test Movie"
        assert movie.media_type == MediaType.MOVIE
        print("✅ MediaItem creation works")
        
        # Test episode creation
        episode = MediaItem(
            title="Test Episode",
            media_type=MediaType.TV_EPISODE,
            source_path="/tmp/test/show/s01e01.mkv",
            relative_path="show/s01e01.mkv",
            file_size=500000,
            file_extension=".mkv",
            show_name="Test Show",
            season=1,
            episode=1,
            episode_title="Pilot"
        )
        assert episode.show_name == "Test Show"
        assert episode.season == 1
        assert episode.episode == 1
        print("✅ TV episode creation works")
        
        return True
        
    except Exception as e:
        print(f"❌ Media discovery test failed: {e}")
        return False

def test_dataset_specs():
    """Test that test dataset specifications are properly defined."""
    print("\nTesting test dataset specs...")
    
    try:
        from plexsync.datasets import TEST_DATASETS, TestDatasetSize
        
        # Test that all sizes are defined
        assert TestDatasetSize.SMALL in TEST_DATASETS
        assert TestDatasetSize.MEDIUM in TEST_DATASETS
        assert TestDatasetSize.LARGE in TEST_DATASETS
        print("✅ All test dataset sizes defined")
        
        # Test small dataset spec
        small_spec = TEST_DATASETS[TestDatasetSize.SMALL]
        assert small_spec.movies_count == 10
        assert small_spec.shows_count == 2
        assert small_spec.avg_episodes_per_show == 10
        print("✅ Small dataset spec correct")
        
        # Test medium dataset spec
        medium_spec = TEST_DATASETS[TestDatasetSize.MEDIUM]
        assert medium_spec.movies_count == 100
        assert medium_spec.shows_count == 10
        assert medium_spec.avg_episodes_per_show == 25
        print("✅ Medium dataset spec correct")
        
        # Test large dataset spec
        large_spec = TEST_DATASETS[TestDatasetSize.LARGE]
        assert large_spec.movies_count == 1000
        assert large_spec.shows_count == 50
        assert large_spec.avg_episodes_per_show == 50
        print("✅ Large dataset spec correct")
        
        return True
        
    except Exception as e:
        print(f"❌ Dataset specs test failed: {e}")
        return False

def test_media_library():
    """Test media library functionality."""
    print("\nTesting media library...")
    
    try:
        from plexsync.datasets import MediaLibrary, MediaItem, MediaType
        
        # Create test movies
        movies = [
            MediaItem("Avatar", MediaType.MOVIE, "/tmp/avatar.mkv", "avatar.mkv", 1000, ".mkv"),
            MediaItem("Blade Runner", MediaType.MOVIE, "/tmp/blade.mkv", "blade.mkv", 2000, ".mkv"),
            MediaItem("Aliens", MediaType.MOVIE, "/tmp/aliens.mkv", "aliens.mkv", 1500, ".mkv"),
        ]
        
        # Create test TV episodes
        episodes = [
            MediaItem("Pilot", MediaType.TV_EPISODE, "/tmp/got/s01e01.mkv", "s01e01.mkv", 
                     500, ".mkv", show_name="Game of Thrones", season=1, episode=1),
            MediaItem("The Kingsroad", MediaType.TV_EPISODE, "/tmp/got/s01e02.mkv", "s01e02.mkv", 
                     600, ".mkv", show_name="Game of Thrones", season=1, episode=2),
        ]
        
        tv_shows = {"Game of Thrones": episodes}
        
        # Create library
        library = MediaLibrary(movies=movies, tv_shows=tv_shows, total_items=5)
        
        # Test movie sorting
        sorted_movies = library.get_all_movies_sorted()
        assert sorted_movies[0].title == "Aliens"  # Alphabetically first
        assert sorted_movies[1].title == "Avatar"
        assert sorted_movies[2].title == "Blade Runner"
        print("✅ Movie sorting works")
        
        # Test show listing
        shows = library.get_all_shows_sorted()
        assert shows == ["Game of Thrones"]
        print("✅ TV show listing works")
        
        # Test episode retrieval
        got_episodes = library.get_show_episodes("Game of Thrones")
        assert len(got_episodes) == 2
        assert got_episodes[0].episode == 1  # Should be sorted by episode
        assert got_episodes[1].episode == 2
        print("✅ Episode retrieval and sorting works")
        
        # Test search
        search_results = library.search_movies("avatar")
        assert len(search_results) == 1
        assert search_results[0].title == "Avatar"
        print("✅ Movie search works")
        
        return True
        
    except Exception as e:
        print(f"❌ Media library test failed: {e}")
        return False

def test_success_metrics():
    """Test that success metrics are properly defined."""
    print("\nTesting success metrics...")
    
    try:
        import plexsync
        
        # Test that constants are defined
        assert hasattr(plexsync, 'MTBF_TARGET_DAYS')
        assert hasattr(plexsync, 'RTO_TARGET_SECONDS')
        assert hasattr(plexsync, 'CORRUPTION_RATE_THRESHOLD')
        assert hasattr(plexsync, 'UI_REFRESH_LATENCY_MS')
        
        # Test values
        assert plexsync.MTBF_TARGET_DAYS == 30
        assert plexsync.RTO_TARGET_SECONDS == 60
        assert plexsync.CORRUPTION_RATE_THRESHOLD == 1e-6
        assert plexsync.UI_REFRESH_LATENCY_MS == 100
        
        print("✅ Success metrics constants defined correctly")
        return True
        
    except Exception as e:
        print(f"❌ Success metrics test failed: {e}")
        return False

def main():
    """Run all Phase 0 tests."""
    print("PlexSync Phase 0 Testing - Interactive Media Synchronization")
    print("=" * 65)
    
    tests = [
        test_basic_imports,
        test_compatibility_matrix,
        test_media_discovery,
        test_dataset_specs,
        test_media_library,
        test_success_metrics,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            if test():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test {test.__name__} failed with exception: {e}")
            failed += 1
    
    print("\n" + "=" * 65)
    print(f"Test Results: {passed} passed, {failed} failed")
    
    if failed == 0:
        print("🎉 All Phase 0 tests passed!")
        print("✅ Ready for interactive media selection and synchronization!")
        return 0
    else:
        print("❌ Some tests failed")
        return 1

if __name__ == "__main__":
    sys.exit(main()) 