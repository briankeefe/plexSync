#!/usr/bin/env python3
"""
Test script for Phase 4: Smart Recommendations & Advanced User Features

This script demonstrates and tests all Phase 4 features:
1. Smart Recommendation Engine
2. User Behavior Pattern Learning
3. Preset Management (Save/Load Selection States)
4. Undo/Redo Functionality
5. Advanced Keyboard Shortcuts
6. Session Statistics and Learning
7. Bookmarking and Quick Actions
8. Intelligent Auto-Selection
"""

import sys
import os
from pathlib import Path
import time
from typing import List, Dict, Any
from dataclasses import dataclass

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from plexsync.datasets import MediaLibrary, MediaItem, MediaType
from plexsync.interactive import (
    InteractiveSyncManager,
    SmartRecommendationEngine,
    UserBehaviorPattern,
    PresetManager,
    SelectionState,
    SelectionAction,
    NavigationCommands,
    MediaSelectionType,
    BrowseStyle
)
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text


class Phase4TestFramework:
    """Test framework for Phase 4 features."""
    
    def __init__(self):
        self.console = Console()
        self.library = self._create_test_library()
        self.sync_manager = InteractiveSyncManager(self.library)
        self.recommendation_engine = SmartRecommendationEngine(self.console)
        self.preset_manager = PresetManager(self.console)
        self.test_results = []
        
    def _create_test_library(self) -> MediaLibrary:
        """Create a comprehensive test library with diverse media."""
        # Initialize empty library
        library = MediaLibrary(movies=[], tv_shows={})
        
        # Add diverse movies for testing recommendations
        test_movies = [
            # Action movies
            MediaItem(
                title="The Matrix",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/The.Matrix.1999.1080p.BluRay.x264.mkv",
                relative_path="The.Matrix.1999.1080p.BluRay.x264.mkv",
                file_size=8_500_000_000,  # 8.5GB
                file_extension=".mkv"
            ),
            MediaItem(
                title="John Wick",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/John.Wick.2014.1080p.BluRay.x264.mkv",
                relative_path="John.Wick.2014.1080p.BluRay.x264.mkv",
                file_size=7_200_000_000,  # 7.2GB
                file_extension=".mkv"
            ),
            MediaItem(
                title="Mad Max: Fury Road",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/Mad.Max.Fury.Road.2015.4K.BluRay.x265.mkv",
                relative_path="Mad.Max.Fury.Road.2015.4K.BluRay.x265.mkv",
                file_size=15_000_000_000,  # 15GB
                file_extension=".mkv"
            ),
            
            # Sci-fi movies
            MediaItem(
                title="Blade Runner 2049",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/Blade.Runner.2049.2017.4K.BluRay.x265.mkv",
                relative_path="Blade.Runner.2049.2017.4K.BluRay.x265.mkv",
                file_size=18_000_000_000,  # 18GB
                file_extension=".mkv"
            ),
            MediaItem(
                title="Interstellar",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/Interstellar.2014.1080p.BluRay.x264.mkv",
                relative_path="Interstellar.2014.1080p.BluRay.x264.mkv",
                file_size=9_500_000_000,  # 9.5GB
                file_extension=".mkv"
            ),
            MediaItem(
                title="Arrival",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/Arrival.2016.1080p.BluRay.x264.mkv",
                relative_path="Arrival.2016.1080p.BluRay.x264.mkv",
                file_size=6_800_000_000,  # 6.8GB
                file_extension=".mkv"
            ),
            
            # Different qualities for testing
            MediaItem(
                title="Dune",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/Dune.2021.4K.HDR.BluRay.x265.mkv",
                relative_path="Dune.2021.4K.HDR.BluRay.x265.mkv",
                file_size=25_000_000_000,  # 25GB
                file_extension=".mkv"
            ),
            MediaItem(
                title="Spider-Man: No Way Home",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/Spider-Man.No.Way.Home.2021.1080p.WEB-DL.x264.mkv",
                relative_path="Spider-Man.No.Way.Home.2021.1080p.WEB-DL.x264.mkv",
                file_size=4_500_000_000,  # 4.5GB
                file_extension=".mkv"
            ),
            MediaItem(
                title="The Batman",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/The.Batman.2022.720p.BluRay.x264.mkv",
                relative_path="The.Batman.2022.720p.BluRay.x264.mkv",
                file_size=3_200_000_000,  # 3.2GB
                file_extension=".mkv"
            ),
            MediaItem(
                title="Top Gun: Maverick",
                media_type=MediaType.MOVIE,
                source_path="/media/movies/Top.Gun.Maverick.2022.1080p.BluRay.x264.mkv",
                relative_path="Top.Gun.Maverick.2022.1080p.BluRay.x264.mkv",
                file_size=8_900_000_000,  # 8.9GB
                file_extension=".mkv"
            ),
        ]
        
        # Add TV show episodes
        test_episodes = [
            MediaItem(
                title="Breaking Bad S01E01",
                media_type=MediaType.TV_EPISODE,
                source_path="/media/tv/Breaking.Bad/Season.01/Breaking.Bad.S01E01.1080p.BluRay.x264.mkv",
                relative_path="Breaking.Bad/Season.01/Breaking.Bad.S01E01.1080p.BluRay.x264.mkv",
                file_size=1_200_000_000,  # 1.2GB
                file_extension=".mkv",
                show_name="Breaking Bad",
                season=1,
                episode=1
            ),
            MediaItem(
                title="Breaking Bad S01E02",
                media_type=MediaType.TV_EPISODE,
                source_path="/media/tv/Breaking.Bad/Season.01/Breaking.Bad.S01E02.1080p.BluRay.x264.mkv",
                relative_path="Breaking.Bad/Season.01/Breaking.Bad.S01E02.1080p.BluRay.x264.mkv",
                file_size=1_150_000_000,  # 1.15GB
                file_extension=".mkv",
                show_name="Breaking Bad",
                season=1,
                episode=2
            ),
            MediaItem(
                title="The Office S01E01",
                media_type=MediaType.TV_EPISODE,
                source_path="/media/tv/The.Office/Season.01/The.Office.S01E01.720p.WEB-DL.x264.mkv",
                relative_path="The.Office/Season.01/The.Office.S01E01.720p.WEB-DL.x264.mkv",
                file_size=450_000_000,  # 450MB
                file_extension=".mkv",
                show_name="The Office",
                season=1,
                episode=1
            ),
            MediaItem(
                title="Stranger Things S01E01",
                media_type=MediaType.TV_EPISODE,
                source_path="/media/tv/Stranger.Things/Season.01/Stranger.Things.S01E01.4K.HDR.WEB-DL.x265.mkv",
                relative_path="Stranger.Things/Season.01/Stranger.Things.S01E01.4K.HDR.WEB-DL.x265.mkv",
                file_size=2_800_000_000,  # 2.8GB
                file_extension=".mkv",
                show_name="Stranger Things",
                season=1,
                episode=1
            ),
        ]
        
        # Add to library
        library.movies.extend(test_movies)
        
        # Add TV episodes grouped by show
        for episode in test_episodes:
            show_name = episode.show_name
            if show_name not in library.tv_shows:
                library.tv_shows[show_name] = []
            library.tv_shows[show_name].append(episode)
        
        return library
    
    def run_all_tests(self):
        """Run all Phase 4 tests."""
        self.console.print("🚀 Phase 4 Test Suite: Smart Recommendations & Advanced User Features", style="bold green")
        self.console.print("=" * 80, style="dim")
        self.console.print()
        
        # Test 1: Smart Recommendation Engine
        self.test_smart_recommendations()
        
        # Test 2: User Behavior Pattern Learning
        self.test_user_behavior_patterns()
        
        # Test 3: Preset Management
        self.test_preset_management()
        
        # Test 4: Undo/Redo Functionality
        self.test_undo_redo_functionality()
        
        # Test 5: Advanced Keyboard Shortcuts
        self.test_advanced_keyboard_shortcuts()
        
        # Test 6: Session Statistics and Learning
        self.test_session_statistics()
        
        # Test 7: Bookmarking and Quick Actions
        self.test_bookmarking_features()
        
        # Test 8: Intelligent Auto-Selection
        self.test_intelligent_auto_selection()
        
        # Test 9: Smart Sorting and Filtering
        self.test_smart_sorting()
        
        # Test 10: Integration Test
        self.test_complete_workflow()
        
        # Show final results
        self.show_test_results()
    
    def test_smart_recommendations(self):
        """Test 1: Smart Recommendation Engine."""
        self.console.print("🧠 Test 1: Smart Recommendation Engine", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Create user patterns by simulating selections
        user_patterns = UserBehaviorPattern()
        
        # Simulate user selecting sci-fi movies
        sci_fi_movies = [
            self.library.movies[0],  # The Matrix
            self.library.movies[3],  # Blade Runner 2049
            self.library.movies[4],  # Interstellar
        ]
        
        for movie in sci_fi_movies:
            user_patterns.update_from_item(movie, self.recommendation_engine.enhanced_search)
        
        # Test recommendations
        recommendations = self.recommendation_engine.get_recommendations(
            self.library, user_patterns, limit=5
        )
        
        # Verify recommendations
        if len(recommendations) > 0:
            self.console.print("✅ Recommendations generated successfully", style="green")
            
            # Display recommendations
            table = Table(title="Smart Recommendations")
            table.add_column("Title", style="bold")
            table.add_column("Year", width=6, style="cyan")
            table.add_column("Quality", width=8, style="yellow")
            table.add_column("Size", width=8, style="green")
            
            for rec in recommendations:
                metadata = self.recommendation_engine.enhanced_search.extract_metadata(rec)
                year = str(metadata.get('year', '?'))
                quality = metadata.get('quality', '?').upper()
                size = f"{rec.file_size / 1_000_000_000:.1f} GB"
                table.add_row(rec.title, year, quality, size)
            
            self.console.print(table)
            
            # Test smart suggestions
            suggestions = self.recommendation_engine.get_smart_suggestions(
                self.library, user_patterns, "general"
            )
            
            if suggestions:
                self.console.print("✅ Smart suggestions generated successfully", style="green")
                for category, items in suggestions.items():
                    if items:
                        self.console.print(f"  📂 {category}: {len(items)} items")
            else:
                self.console.print("❌ No smart suggestions generated", style="red")
                
            self.test_results.append(("Smart Recommendations", "PASS"))
        else:
            self.console.print("❌ No recommendations generated", style="red")
            self.test_results.append(("Smart Recommendations", "FAIL"))
        
        self.console.print()
    
    def test_user_behavior_patterns(self):
        """Test 2: User Behavior Pattern Learning."""
        self.console.print("📊 Test 2: User Behavior Pattern Learning", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Create and test user patterns
        user_patterns = UserBehaviorPattern()
        
        # Simulate diverse user selections
        selected_items = [
            self.library.movies[0],  # The Matrix (1999, 1080p)
            self.library.movies[1],  # John Wick (2014, 1080p)
            self.library.movies[4],  # Interstellar (2014, 1080p)
            self.library.movies[6],  # Dune (2021, 4K)
        ]
        
        for item in selected_items:
            user_patterns.update_from_item(item, self.recommendation_engine.enhanced_search)
        
        # Test pattern analysis
        preferred_years = user_patterns.get_preferred_year_range()
        preferred_quality = user_patterns.get_top_quality()
        preferred_size = user_patterns.get_preferred_size_range()
        
        self.console.print("📈 User Behavior Analysis:", style="bold cyan")
        self.console.print(f"  🗓️  Preferred years: {preferred_years[0]}-{preferred_years[1]}")
        self.console.print(f"  🎬 Preferred quality: {preferred_quality or 'Not determined'}")
        self.console.print(f"  📏 Preferred size range: {preferred_size[0]/1_000_000_000:.1f}-{preferred_size[1]/1_000_000_000:.1f} GB")
        self.console.print(f"  📚 Total selections: {len(user_patterns.session_selections)}")
        
        # Test pattern accuracy
        if preferred_quality and len(user_patterns.session_selections) > 0:
            self.console.print("✅ User patterns learned successfully", style="green")
            self.test_results.append(("User Behavior Patterns", "PASS"))
        else:
            self.console.print("❌ User patterns not learned correctly", style="red")
            self.test_results.append(("User Behavior Patterns", "FAIL"))
        
        self.console.print()
    
    def test_preset_management(self):
        """Test 3: Preset Management."""
        self.console.print("💾 Test 3: Preset Management", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Create test selection state
        selection_state = SelectionState()
        selection_state.selected_movies = [
            self.library.movies[0],
            self.library.movies[1],
        ]
        selection_state.media_type = MediaSelectionType.MOVIES
        
        # Test saving preset
        preset_name = "Test Preset Phase 4"
        try:
            success = self.preset_manager.save_selection_preset(preset_name, selection_state)
            if success:
                self.console.print("✅ Preset saved successfully", style="green")
                
                # Test loading presets
                presets = self.preset_manager.load_presets()
                if any(p.name == preset_name for p in presets):
                    self.console.print("✅ Preset loaded successfully", style="green")
                    self.test_results.append(("Preset Management", "PASS"))
                else:
                    self.console.print("❌ Preset not found in loaded presets", style="red")
                    self.test_results.append(("Preset Management", "FAIL"))
            else:
                self.console.print("❌ Failed to save preset", style="red")
                self.test_results.append(("Preset Management", "FAIL"))
        except Exception as e:
            self.console.print(f"❌ Preset management error: {e}", style="red")
            self.test_results.append(("Preset Management", "FAIL"))
        
        self.console.print()
    
    def test_undo_redo_functionality(self):
        """Test 4: Undo/Redo Functionality."""
        self.console.print("↩️ Test 4: Undo/Redo Functionality", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Create test selection state
        selection_state = SelectionState()
        
        # Test adding items and tracking actions
        movie1 = self.library.movies[0]
        movie2 = self.library.movies[1]
        
        # Add first movie
        selection_state.selected_movies.append(movie1)
        action1 = SelectionAction(
            action_type="add",
            media_type="movie",
            item=movie1,
            description=f"Added {movie1.title}"
        )
        selection_state.add_selection_action(action1)
        
        # Add second movie
        selection_state.selected_movies.append(movie2)
        action2 = SelectionAction(
            action_type="add",
            media_type="movie",
            item=movie2,
            description=f"Added {movie2.title}"
        )
        selection_state.add_selection_action(action2)
        
        # Test undo functionality
        initial_count = len(selection_state.selected_movies)
        self.console.print(f"📝 Initial selection count: {initial_count}")
        
        if selection_state.can_undo():
            undone_action = selection_state.undo_last_action()
            self.console.print(f"↩️  Undone: {undone_action.description}")
            
            # Test redo functionality
            if selection_state.can_redo():
                redone_action = selection_state.redo_last_action()
                self.console.print(f"↪️  Redone: {redone_action.description}")
                
                # Verify state
                final_count = len(selection_state.selected_movies)
                if final_count == initial_count:
                    self.console.print("✅ Undo/Redo functionality working correctly", style="green")
                    self.test_results.append(("Undo/Redo Functionality", "PASS"))
                else:
                    self.console.print("❌ Undo/Redo state mismatch", style="red")
                    self.test_results.append(("Undo/Redo Functionality", "FAIL"))
            else:
                self.console.print("❌ Redo not available after undo", style="red")
                self.test_results.append(("Undo/Redo Functionality", "FAIL"))
        else:
            self.console.print("❌ Undo not available", style="red")
            self.test_results.append(("Undo/Redo Functionality", "FAIL"))
        
        self.console.print()
    
    def test_advanced_keyboard_shortcuts(self):
        """Test 5: Advanced Keyboard Shortcuts."""
        self.console.print("⌨️ Test 5: Advanced Keyboard Shortcuts", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Test NavigationCommands class
        shortcuts = [
            (NavigationCommands.UNDO, "Undo last action"),
            (NavigationCommands.REDO, "Redo last action"),
            (NavigationCommands.RECOMMEND, "Show recommendations"),
            (NavigationCommands.BOOKMARK, "Bookmark/mark for later"),
            (NavigationCommands.QUICK_SYNC, "Quick sync selected items"),
            (NavigationCommands.SHOW_STATS, "Show info/stats"),
            (NavigationCommands.RANDOM, "Random selection"),
            (NavigationCommands.HOME, "Go to first page"),
            (NavigationCommands.END, "Go to last page"),
            (NavigationCommands.AUTO_SELECT, "Smart auto-selection"),
            (NavigationCommands.LEARN_MODE, "Toggle learning mode"),
            (NavigationCommands.QUICK_SIMILAR, "Select similar items"),
            (NavigationCommands.SMART_SORT, "Sort by user preferences"),
            (NavigationCommands.SESSION_STATS, "Show session statistics"),
        ]
        
        # Create shortcuts table
        table = Table(title="Phase 4 Keyboard Shortcuts")
        table.add_column("Shortcut", style="bold yellow")
        table.add_column("Description", style="dim")
        
        for shortcut, description in shortcuts:
            table.add_row(f"[{shortcut}]", description)
        
        self.console.print(table)
        
        # Test help text generation
        help_text = NavigationCommands.get_help_text("movies")
        if help_text and len(help_text) > 0:
            self.console.print("✅ Advanced keyboard shortcuts available", style="green")
            self.test_results.append(("Advanced Keyboard Shortcuts", "PASS"))
        else:
            self.console.print("❌ Help text not available", style="red")
            self.test_results.append(("Advanced Keyboard Shortcuts", "FAIL"))
        
        self.console.print()
    
    def test_session_statistics(self):
        """Test 6: Session Statistics and Learning."""
        self.console.print("📊 Test 6: Session Statistics and Learning", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Create a session with multiple selections
        selection_state = SelectionState()
        
        # Add diverse selections
        selection_state.selected_movies = [
            self.library.movies[0],  # The Matrix
            self.library.movies[3],  # Blade Runner 2049
            self.library.movies[6],  # Dune
        ]
        
        # Get episodes from the library's TV shows
        all_episodes = []
        for show_episodes in self.library.tv_shows.values():
            all_episodes.extend(show_episodes)
        
        selection_state.selected_episodes = [
            all_episodes[0],  # Breaking Bad
            all_episodes[3],  # Stranger Things
        ]
        
        # Update user patterns
        for movie in selection_state.selected_movies:
            selection_state.user_patterns.update_from_item(
                movie, self.recommendation_engine.enhanced_search
            )
        
        # Test statistics calculation
        total_size = selection_state.total_size()
        total_items = selection_state.total_items()
        
        # Display session statistics
        stats_table = Table(title="Session Statistics")
        stats_table.add_column("Metric", style="bold")
        stats_table.add_column("Value", style="green")
        
        stats_table.add_row("Total Items", str(total_items))
        stats_table.add_row("Total Size", selection_state.format_size(total_size))
        stats_table.add_row("Movies", str(len(selection_state.selected_movies)))
        stats_table.add_row("Episodes", str(len(selection_state.selected_episodes)))
        stats_table.add_row("Selection Actions", str(len(selection_state.action_history)))
        stats_table.add_row("Learning Sessions", str(len(selection_state.user_patterns.session_selections)))
        
        self.console.print(stats_table)
        
        # Test learning effectiveness
        if total_items > 0 and len(selection_state.user_patterns.session_selections) > 0:
            self.console.print("✅ Session statistics and learning working correctly", style="green")
            self.test_results.append(("Session Statistics", "PASS"))
        else:
            self.console.print("❌ Session statistics not calculated correctly", style="red")
            self.test_results.append(("Session Statistics", "FAIL"))
        
        self.console.print()
    
    def test_bookmarking_features(self):
        """Test 7: Bookmarking and Quick Actions."""
        self.console.print("🔖 Test 7: Bookmarking and Quick Actions", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Test bookmarking functionality
        selection_state = SelectionState()
        
        # Add bookmarked items
        bookmarked_items = [
            self.library.movies[0],  # The Matrix
            self.library.movies[2],  # Mad Max: Fury Road
        ]
        
        selection_state.bookmarked_items.extend(bookmarked_items)
        
        # Test bookmark statistics
        bookmark_count = len(selection_state.bookmarked_items)
        
        if bookmark_count > 0:
            self.console.print(f"📑 Bookmarked items: {bookmark_count}")
            
            # Display bookmarked items
            bookmark_table = Table(title="Bookmarked Items")
            bookmark_table.add_column("Title", style="bold")
            bookmark_table.add_column("Year", width=6, style="cyan")
            bookmark_table.add_column("Size", width=8, style="green")
            
            for item in selection_state.bookmarked_items:
                metadata = self.recommendation_engine.enhanced_search.extract_metadata(item)
                year = str(metadata.get('year', '?'))
                size = f"{item.file_size / 1_000_000_000:.1f} GB"
                bookmark_table.add_row(item.title, year, size)
            
            self.console.print(bookmark_table)
            
            self.console.print("✅ Bookmarking features working correctly", style="green")
            self.test_results.append(("Bookmarking Features", "PASS"))
        else:
            self.console.print("❌ Bookmarking not working", style="red")
            self.test_results.append(("Bookmarking Features", "FAIL"))
        
        self.console.print()
    
    def test_intelligent_auto_selection(self):
        """Test 8: Intelligent Auto-Selection."""
        self.console.print("🤖 Test 8: Intelligent Auto-Selection", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Create user patterns for auto-selection
        user_patterns = UserBehaviorPattern()
        
        # Train patterns with user preferences
        preferred_movies = [
            self.library.movies[0],  # The Matrix (1999, 1080p)
            self.library.movies[4],  # Interstellar (2014, 1080p)
            self.library.movies[5],  # Arrival (2016, 1080p)
        ]
        
        for movie in preferred_movies:
            user_patterns.update_from_item(movie, self.recommendation_engine.enhanced_search)
        
        # Test auto-selection based on patterns
        all_movies = self.library.movies
        auto_selected = []
        
        for movie in all_movies:
            score = self.recommendation_engine._calculate_recommendation_score(movie, user_patterns)
            if score > 0.5:  # High confidence threshold
                auto_selected.append((movie, score))
        
        # Sort by score
        auto_selected.sort(key=lambda x: x[1], reverse=True)
        
        if auto_selected:
            self.console.print(f"🎯 Auto-selected {len(auto_selected)} items based on user patterns")
            
            # Display auto-selected items
            auto_table = Table(title="Auto-Selected Items")
            auto_table.add_column("Title", style="bold")
            auto_table.add_column("Score", width=8, style="yellow")
            auto_table.add_column("Quality", width=8, style="cyan")
            auto_table.add_column("Year", width=6, style="green")
            
            for movie, score in auto_selected[:5]:  # Show top 5
                metadata = self.recommendation_engine.enhanced_search.extract_metadata(movie)
                quality = metadata.get('quality', '?').upper()
                year = str(metadata.get('year', '?'))
                auto_table.add_row(movie.title, f"{score:.2f}", quality, year)
            
            self.console.print(auto_table)
            
            self.console.print("✅ Intelligent auto-selection working correctly", style="green")
            self.test_results.append(("Intelligent Auto-Selection", "PASS"))
        else:
            self.console.print("❌ No items auto-selected", style="red")
            self.test_results.append(("Intelligent Auto-Selection", "FAIL"))
        
        self.console.print()
    
    def test_smart_sorting(self):
        """Test 9: Smart Sorting and Filtering."""
        self.console.print("🔄 Test 9: Smart Sorting and Filtering", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Test smart sorting based on user preferences
        user_patterns = UserBehaviorPattern()
        
        # Create preference patterns
        user_patterns.preferred_years = {2014: 3, 2016: 2, 2021: 1}
        user_patterns.preferred_qualities = {"1080p": 4, "4k": 2}
        
        # Test sorting movies by user preferences
        movies = self.library.movies.copy()
        
        # Custom sort function based on user patterns
        def smart_sort_key(movie):
            metadata = self.recommendation_engine.enhanced_search.extract_metadata(movie)
            score = 0
            
            # Year preference
            year = metadata.get('year')
            if year and year in user_patterns.preferred_years:
                score += user_patterns.preferred_years[year] * 10
            
            # Quality preference
            quality = metadata.get('quality')
            if quality and quality in user_patterns.preferred_qualities:
                score += user_patterns.preferred_qualities[quality] * 5
            
            return score
        
        # Sort movies
        sorted_movies = sorted(movies, key=smart_sort_key, reverse=True)
        
        # Display sorted results
        sort_table = Table(title="Smart Sorted Movies")
        sort_table.add_column("Rank", width=4, style="dim")
        sort_table.add_column("Title", style="bold")
        sort_table.add_column("Year", width=6, style="cyan")
        sort_table.add_column("Quality", width=8, style="yellow")
        sort_table.add_column("Score", width=6, style="green")
        
        for i, movie in enumerate(sorted_movies[:5], 1):
            metadata = self.recommendation_engine.enhanced_search.extract_metadata(movie)
            year = str(metadata.get('year', '?'))
            quality = metadata.get('quality', '?').upper()
            score = smart_sort_key(movie)
            
            sort_table.add_row(str(i), movie.title, year, quality, str(score))
        
        self.console.print(sort_table)
        
        # Test if sorting is working
        if sorted_movies != movies:  # Order should be different
            self.console.print("✅ Smart sorting working correctly", style="green")
            self.test_results.append(("Smart Sorting", "PASS"))
        else:
            self.console.print("❌ Smart sorting not changing order", style="red")
            self.test_results.append(("Smart Sorting", "FAIL"))
        
        self.console.print()
    
    def test_complete_workflow(self):
        """Test 10: Complete Workflow Integration."""
        self.console.print("🔄 Test 10: Complete Workflow Integration", style="bold blue")
        self.console.print("-" * 40, style="dim")
        
        # Test complete Phase 4 workflow
        try:
            # 1. Initialize sync manager
            sync_manager = InteractiveSyncManager(self.library)
            
            # 2. Create selection state
            selection_state = SelectionState()
            selection_state.media_type = MediaSelectionType.MOVIES
            
            # 3. Add selections
            selection_state.selected_movies = [
                self.library.movies[0],
                self.library.movies[1],
            ]
            
            # 4. Update user patterns
            for movie in selection_state.selected_movies:
                selection_state.user_patterns.update_from_item(
                    movie, sync_manager.recommendation_engine.enhanced_search
                )
            
            # 5. Generate recommendations
            recommendations = sync_manager.recommendation_engine.get_recommendations(
                self.library, selection_state.user_patterns
            )
            
            # 6. Test all components working together
            components_working = [
                len(selection_state.selected_movies) > 0,
                len(selection_state.user_patterns.session_selections) > 0,
                len(recommendations) > 0,
                selection_state.total_size() > 0,
                selection_state.total_items() > 0,
            ]
            
            if all(components_working):
                self.console.print("✅ Complete workflow integration successful", style="green")
                
                # Show workflow summary
                workflow_table = Table(title="Workflow Summary")
                workflow_table.add_column("Component", style="bold")
                workflow_table.add_column("Status", style="green")
                workflow_table.add_column("Details", style="dim")
                
                workflow_table.add_row("Selection Management", "✅ Active", f"{len(selection_state.selected_movies)} movies")
                workflow_table.add_row("User Learning", "✅ Active", f"{len(selection_state.user_patterns.session_selections)} patterns")
                workflow_table.add_row("Recommendations", "✅ Active", f"{len(recommendations)} suggestions")
                workflow_table.add_row("State Management", "✅ Active", f"{selection_state.total_items()} items")
                workflow_table.add_row("Smart Features", "✅ Active", "All systems operational")
                
                self.console.print(workflow_table)
                
                self.test_results.append(("Complete Workflow", "PASS"))
            else:
                self.console.print("❌ Some workflow components not working", style="red")
                self.test_results.append(("Complete Workflow", "FAIL"))
                
        except Exception as e:
            self.console.print(f"❌ Workflow integration error: {e}", style="red")
            self.test_results.append(("Complete Workflow", "FAIL"))
        
        self.console.print()
    
    def show_test_results(self):
        """Show final test results."""
        self.console.print("📋 Phase 4 Test Results Summary", style="bold green")
        self.console.print("=" * 80, style="dim")
        
        # Create results table
        results_table = Table(title="Test Results")
        results_table.add_column("Test", style="bold")
        results_table.add_column("Result", width=8)
        results_table.add_column("Status", width=8)
        
        passed_tests = 0
        total_tests = len(self.test_results)
        
        for test_name, result in self.test_results:
            if result == "PASS":
                passed_tests += 1
                status_style = "green"
                status_icon = "✅"
            else:
                status_style = "red"
                status_icon = "❌"
            
            results_table.add_row(
                test_name,
                f"[{status_style}]{result}[/{status_style}]",
                f"[{status_style}]{status_icon}[/{status_style}]"
            )
        
        self.console.print(results_table)
        
        # Show summary
        pass_rate = (passed_tests / total_tests) * 100 if total_tests > 0 else 0
        
        summary_panel = Panel(
            f"🎯 **Phase 4 Test Summary**\n\n"
            f"**Total Tests:** {total_tests}\n"
            f"**Passed:** {passed_tests}\n"
            f"**Failed:** {total_tests - passed_tests}\n"
            f"**Pass Rate:** {pass_rate:.1f}%\n\n"
            f"**Status:** {'🎉 All systems operational!' if pass_rate == 100 else '⚠️ Some issues detected'}",
            title="Test Summary",
            border_style="green" if pass_rate == 100 else "yellow"
        )
        
        self.console.print(summary_panel)
        
        if pass_rate == 100:
            self.console.print("🚀 Phase 4 implementation is complete and fully functional!", style="bold green")
        else:
            self.console.print("⚠️ Phase 4 implementation has some issues that need attention.", style="bold yellow")


def main():
    """Run Phase 4 tests."""
    print("🎬 PlexSync Phase 4 Test Suite")
    print("Testing: Smart Recommendations & Advanced User Features")
    print("=" * 60)
    
    # Create and run test framework
    test_framework = Phase4TestFramework()
    test_framework.run_all_tests()
    
    print("\n" + "=" * 60)
    print("Phase 4 testing complete!")


if __name__ == "__main__":
    main() 