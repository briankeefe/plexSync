"""
Unit tests for Quick Start Mode components.

Tests MediaFinder, QuickStartManager, and related functionality.
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tempfile
import os
from pathlib import Path

# Add src to path for testing
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from plexsync.media_finder import MediaFinder, MediaCandidate, MediaType
from plexsync.quick_start import QuickStartManager, QuickStartSession
from plexsync.settings_manager import QuickStartPreferences


class TestMediaFinder(unittest.TestCase):
    """Test MediaFinder functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_mount_manager = Mock()
        self.mock_console = Mock()
        self.media_finder = MediaFinder(
            mount_manager=self.mock_mount_manager,
            console=self.mock_console
        )
    
    def test_media_candidate_creation(self):
        """Test MediaCandidate dataclass."""
        candidate = MediaCandidate(
            path=Path("/test/movies"),
            score=10,
            reason="Test reason",
            media_type=MediaType.MOVIES
        )
        
        self.assertEqual(candidate.path, Path("/test/movies"))
        self.assertEqual(candidate.score, 10)
        self.assertEqual(candidate.media_type, MediaType.MOVIES)
        self.assertEqual(str(candidate), "/test/movies (Movies, Score: 10)")
    
    def test_determine_media_type_movies(self):
        """Test media type detection for movies."""
        test_dir = Path("/test/movies")
        media_files = [Path("/test/movies/movie1.mp4"), Path("/test/movies/movie2.mkv")]
        
        result = self.media_finder._determine_media_type(test_dir, media_files)
        self.assertEqual(result, MediaType.MOVIES)
    
    def test_determine_media_type_tv_shows(self):
        """Test media type detection for TV shows."""
        test_dir = Path("/test/tv_shows")
        media_files = [Path("/test/tv_shows/show_s01e01.mp4")]
        
        result = self.media_finder._determine_media_type(test_dir, media_files)
        self.assertEqual(result, MediaType.TV_SHOWS)
    
    def test_deduplicate_candidates(self):
        """Test candidate deduplication."""
        candidates = [
            MediaCandidate(Path("/test/path"), 5, "Low score"),
            MediaCandidate(Path("/test/path"), 10, "High score"),
            MediaCandidate(Path("/test/other"), 7, "Different path")
        ]
        
        result = self.media_finder._deduplicate_candidates(candidates)
        
        # Should keep highest scored duplicate and unique paths
        self.assertEqual(len(result), 2)
        paths = [str(c.path.resolve()) for c in result]
        self.assertIn(str(Path("/test/path").resolve()), paths)
        self.assertIn(str(Path("/test/other").resolve()), paths)
        
        # Check that high score was kept
        path_candidate = next(c for c in result if str(c.path.resolve()) == str(Path("/test/path").resolve()))
        self.assertEqual(path_candidate.score, 10)


class TestQuickStartPreferences(unittest.TestCase):
    """Test QuickStartPreferences functionality."""
    
    def test_preferences_initialization(self):
        """Test preferences default initialization."""
        prefs = QuickStartPreferences()
        
        self.assertIsNone(prefs.last_source_path)
        self.assertIsNone(prefs.last_destination_path)
        self.assertEqual(prefs.successful_completion_count, 0)
        self.assertFalse(prefs.skip_plex_validation)
    
    def test_record_success(self):
        """Test recording successful completion."""
        prefs = QuickStartPreferences()
        
        prefs.record_success(
            source_path="/test/source",
            destination_path="/test/dest", 
            completion_time_seconds=90.5,
            media_type="movies"
        )
        
        self.assertEqual(prefs.last_source_path, "/test/source")
        self.assertEqual(prefs.last_destination_path, "/test/dest")
        self.assertEqual(prefs.successful_completion_count, 1)
        self.assertEqual(prefs.preferred_media_type, "movies")
        self.assertEqual(prefs.average_completion_time_seconds, 90.5)
        self.assertIsNotNone(prefs.last_success_timestamp)
    
    def test_success_rate_estimation(self):
        """Test success rate estimation."""
        prefs = QuickStartPreferences()
        
        # No completions
        self.assertEqual(prefs.get_success_rate_estimate(), 0.0)
        
        # One completion
        prefs.successful_completion_count = 1
        self.assertEqual(prefs.get_success_rate_estimate(), 0.6)
        
        # Many completions (should cap at 0.95)
        prefs.successful_completion_count = 10
        self.assertEqual(prefs.get_success_rate_estimate(), 0.95)


class TestQuickStartSession(unittest.TestCase):
    """Test QuickStartSession functionality."""
    
    def test_session_initialization(self):
        """Test session initialization."""
        session = QuickStartSession()
        
        self.assertIsNone(session.source_path)
        self.assertIsNone(session.destination_path)
        self.assertIsNone(session.media_type)
        self.assertFalse(session.skip_plex)
    
    @patch('time.time', return_value=150.5)
    def test_session_duration(self, mock_time):
        """Test session duration calculation."""
        session = QuickStartSession(start_time=100.0)
        duration = session.get_duration()
        
        self.assertEqual(duration, 50.5)


class TestQuickStartManager(unittest.TestCase):
    """Test QuickStartManager functionality."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.mock_console = Mock()
        self.mock_settings_manager = Mock()
        self.mock_config_manager = Mock()
        self.mock_mount_manager = Mock()
        self.mock_media_finder = Mock()
        
        # Create preferences mock
        self.mock_preferences = Mock(spec=QuickStartPreferences)
        self.mock_preferences.successful_completion_count = 0
        self.mock_preferences.get_success_rate_estimate.return_value = 0.0
        
        with patch('plexsync.quick_start.get_settings_manager', return_value=self.mock_settings_manager), \
             patch('plexsync.quick_start.get_config_manager', return_value=self.mock_config_manager), \
             patch('plexsync.quick_start.get_mount_manager', return_value=self.mock_mount_manager), \
             patch('plexsync.quick_start.get_media_finder', return_value=self.mock_media_finder):
            
            self.manager = QuickStartManager(console=self.mock_console)
            self.manager.preferences = self.mock_preferences
    
    def test_manager_initialization(self):
        """Test manager initialization."""
        self.assertIsNotNone(self.manager.console)
        self.assertIsNotNone(self.manager.session)
        self.assertIsNotNone(self.manager.session.start_time)
    
    def test_get_destination_suggestions(self):
        """Test destination path suggestions."""
        self.manager.session.source_path = Path("/mnt/media/Movies")
        
        suggestions = self.manager._get_destination_suggestions()
        
        self.assertIsInstance(suggestions, list)
        self.assertGreater(len(suggestions), 0)
        self.assertTrue(any("PlexSync" in suggestion for suggestion in suggestions))
    
    def test_create_minimal_config(self):
        """Test minimal configuration creation."""
        self.manager.session.source_path = Path("/test/source")
        self.manager.session.destination_path = Path("/test/dest")
        self.manager.session.media_type = MediaType.MOVIES
        self.manager.session.skip_plex = True
        
        config = self.manager._create_minimal_config()
        
        expected = {
            "source": {
                "path": "/test/source",
                "type": "movies"
            },
            "destination": {
                "path": "/test/dest"
            },
            "skip_plex": True,
            "quick_start": True
        }
        
        self.assertEqual(config, expected)


class TestQuickStartIntegration(unittest.TestCase):
    """Integration tests for Quick Start Mode."""
    
    def test_media_finder_integration(self):
        """Test that MediaFinder integrates properly with mount manager."""
        with patch('plexsync.media_finder.get_mount_manager') as mock_get_mount:
            mock_mount_manager = Mock()
            mock_mount_manager.discover_mounts.return_value = []
            mock_get_mount.return_value = mock_mount_manager
            
            media_finder = MediaFinder()
            candidates = media_finder.find_potential_sources()
            
            self.assertIsInstance(candidates, list)
            mock_mount_manager.discover_mounts.assert_called_once()
    
    def test_settings_manager_integration(self):
        """Test QuickStartPreferences integration with settings manager."""
        from plexsync.settings_manager import SystemSettings
        
        settings = SystemSettings()
        self.assertIsNotNone(settings.quick_start)
        self.assertIsInstance(settings.quick_start, QuickStartPreferences)


if __name__ == '__main__':
    unittest.main()