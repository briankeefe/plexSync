"""
Interactive sync management for PlexSync.

This module implements the immersive interactive sync experience where users
are guided through media selection step-by-step without needing to remember
show names, episode numbers, or complex parameters.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import os
import time
from pathlib import Path
import re
import difflib
from collections import defaultdict
import json
import threading
import queue
import random
from datetime import datetime, timedelta

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.columns import Columns
from rich.live import Live
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.align import Align

from .datasets import MediaLibrary, MediaItem, MediaType, MediaDiscovery


class SyncStatus(Enum):
    """Sync status for media items."""
    SYNCED = "synced"
    PARTIAL = "partial"
    NOT_SYNCED = "not_synced"


class SyncStatusChecker:
    """Utility class to check sync status of media items."""
    
    def __init__(self, sync_dir: str = None):
        self.sync_dir = sync_dir or os.path.expanduser("~/PlexSync")
    
    def check_item_status(self, item: MediaItem) -> SyncStatus:
        """Check the sync status of a media item."""
        filename = os.path.basename(item.source_path)
        dest_file = os.path.join(self.sync_dir, filename)
        
        if not os.path.exists(dest_file):
            return SyncStatus.NOT_SYNCED
        
        try:
            dest_size = os.path.getsize(dest_file)
            if dest_size == item.file_size:
                return SyncStatus.SYNCED
            else:
                return SyncStatus.PARTIAL
        except OSError:
            return SyncStatus.NOT_SYNCED
    
    def get_status_indicator(self, status: SyncStatus) -> str:
        """Get visual indicator for sync status."""
        indicators = {
            SyncStatus.SYNCED: "✅ Synced",
            SyncStatus.PARTIAL: "⚠️ Partial",
            SyncStatus.NOT_SYNCED: "⬜ Not synced"
        }
        return indicators[status]
    
    def get_season_status(self, episodes: List[MediaItem]) -> Tuple[SyncStatus, str]:
        """Get overall status for a season of episodes."""
        if not episodes:
            return SyncStatus.NOT_SYNCED, "⬜ No episodes"
        
        synced_count = 0
        partial_count = 0
        
        for episode in episodes:
            status = self.check_item_status(episode)
            if status == SyncStatus.SYNCED:
                synced_count += 1
            elif status == SyncStatus.PARTIAL:
                partial_count += 1
        
        total_count = len(episodes)
        
        if synced_count == total_count:
            return SyncStatus.SYNCED, "✅ Complete"
        elif synced_count > 0 or partial_count > 0:
            return SyncStatus.PARTIAL, f"⚪ Partial ({synced_count}/{total_count})"
        else:
            return SyncStatus.NOT_SYNCED, "⬜ None"


class MediaSelectionType(Enum):
    """Types of media selection for interactive sync."""
    MOVIES = "movies"
    TV_SHOWS = "tv_shows"
    BOTH = "both"


class BrowseStyle(Enum):
    """Different ways to browse media."""
    SEARCH = "search"
    BROWSE_ALL = "browse_all"
    RANDOM = "random"
    BY_SIZE = "by_size"
    RECENT = "recent"


@dataclass
class SelectionAction:
    """Represents a selection action for undo/redo functionality."""
    action_type: str  # 'add', 'remove', 'clear'
    media_type: str  # 'movie', 'episode'
    item: Optional[MediaItem] = None
    items: List[MediaItem] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    description: str = ""


@dataclass 
class UserBehaviorPattern:
    """Tracks user behavior for smart recommendations."""
    preferred_years: Dict[int, int] = field(default_factory=dict)  # year -> count
    preferred_qualities: Dict[str, int] = field(default_factory=dict)  # quality -> count
    preferred_sizes: List[int] = field(default_factory=list)  # file sizes
    selected_genres: Dict[str, int] = field(default_factory=dict)  # genre -> count
    session_selections: List[MediaItem] = field(default_factory=list)
    last_updated: float = field(default_factory=time.time)
    
    def update_from_item(self, item: MediaItem, enhanced_search):
        """Update patterns based on selected item."""
        # Extract metadata and update preferences
        metadata = enhanced_search.extract_metadata(item)
        
        if metadata.get('year'):
            self.preferred_years[metadata['year']] = self.preferred_years.get(metadata['year'], 0) + 1
        
        if metadata.get('quality'):
            self.preferred_qualities[metadata['quality']] = self.preferred_qualities.get(metadata['quality'], 0) + 1
        
        self.preferred_sizes.append(item.file_size)
        self.session_selections.append(item)
        self.last_updated = time.time()
    
    def get_preferred_year_range(self) -> Tuple[int, int]:
        """Get user's preferred year range."""
        if not self.preferred_years:
            return 2020, 2024  # Default recent range
        
        years = list(self.preferred_years.keys())
        return min(years), max(years)
    
    def get_top_quality(self) -> Optional[str]:
        """Get user's most preferred quality."""
        if not self.preferred_qualities:
            return None
        
        return max(self.preferred_qualities.items(), key=lambda x: x[1])[0]
    
    def get_preferred_size_range(self) -> Tuple[int, int]:
        """Get user's preferred file size range."""
        if not self.preferred_sizes:
            return 0, float('inf')
        
        sizes = sorted(self.preferred_sizes)
        # Use middle 80% as preferred range
        start_idx = int(len(sizes) * 0.1)
        end_idx = int(len(sizes) * 0.9)
        
        return sizes[start_idx], sizes[end_idx]


@dataclass
class SelectionState:
    """State management for user selections during interactive sync."""
    media_type: Optional[MediaSelectionType] = None
    browse_style: Optional[BrowseStyle] = None
    selected_movies: List[MediaItem] = field(default_factory=list)
    selected_show: Optional[str] = None
    selected_seasons: List[int] = field(default_factory=list)
    selected_episodes: List[MediaItem] = field(default_factory=list)
    current_page: int = 1
    
    # Phase 4: Advanced state management
    action_history: List[SelectionAction] = field(default_factory=list)
    undo_stack: List[SelectionAction] = field(default_factory=list)
    redo_stack: List[SelectionAction] = field(default_factory=list)
    bookmarked_items: List[MediaItem] = field(default_factory=list)
    user_patterns: UserBehaviorPattern = field(default_factory=UserBehaviorPattern)
    
    def total_size(self) -> int:
        """Calculate total size of all selections."""
        size = 0
        for movie in self.selected_movies:
            size += movie.file_size
        for episode in self.selected_episodes:
            size += episode.file_size
        return size
    
    def total_items(self) -> int:
        """Count total selected items."""
        return len(self.selected_movies) + len(self.selected_episodes)
    
    def format_size(self, size_bytes: int) -> str:
        """Format file size in human-readable format."""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.1f} PB"
    
    def add_selection_action(self, action: SelectionAction):
        """Add an action to history for undo/redo functionality."""
        self.action_history.append(action)
        self.undo_stack.append(action)
        self.redo_stack.clear()  # Clear redo stack when new action is made
        
        # Limit history size
        if len(self.action_history) > 50:
            self.action_history = self.action_history[-50:]
        if len(self.undo_stack) > 20:
            self.undo_stack = self.undo_stack[-20:]
    
    def can_undo(self) -> bool:
        """Check if undo is possible."""
        return len(self.undo_stack) > 0
    
    def can_redo(self) -> bool:
        """Check if redo is possible."""
        return len(self.redo_stack) > 0
    
    def undo_last_action(self) -> Optional[SelectionAction]:
        """Undo the last action."""
        if not self.can_undo():
            return None
        
        action = self.undo_stack.pop()
        self.redo_stack.append(action)
        
        # Reverse the action
        if action.action_type == "add":
            if action.media_type == "movie" and action.item in self.selected_movies:
                self.selected_movies.remove(action.item)
            elif action.media_type == "episode" and action.item in self.selected_episodes:
                self.selected_episodes.remove(action.item)
        elif action.action_type == "remove":
            if action.media_type == "movie":
                self.selected_movies.append(action.item)
            elif action.media_type == "episode":
                self.selected_episodes.append(action.item)
        
        return action
    
    def redo_last_action(self) -> Optional[SelectionAction]:
        """Redo the last undone action."""
        if not self.can_redo():
            return None
        
        action = self.redo_stack.pop()
        self.undo_stack.append(action)
        
        # Reapply the action
        if action.action_type == "add":
            if action.media_type == "movie":
                self.selected_movies.append(action.item)
            elif action.media_type == "episode":
                self.selected_episodes.append(action.item)
        elif action.action_type == "remove":
            if action.media_type == "movie" and action.item in self.selected_movies:
                self.selected_movies.remove(action.item)
            elif action.media_type == "episode" and action.item in self.selected_episodes:
                self.selected_episodes.remove(action.item)
        
        return action


class NavigationCommands:
    """Navigation commands for interactive browsing."""
    NEXT = "n"
    PREVIOUS = "p"
    SEARCH = "s"
    FILTER = "f"
    SORT = "o"
    HELP = "h"
    QUIT = "q"
    BACK = "b"
    ALL = "a"
    NEW = "new"
    CUSTOM = "c"
    JUMP = "j"  # Jump to page
    ADVANCED_SEARCH = "as"  # Advanced search
    FILTER_GENRE = "fg"  # Filter by genre
    FILTER_YEAR = "fy"  # Filter by year
    FILTER_QUALITY = "fq"  # Filter by quality
    
    # Phase 4: Keyboard Shortcuts
    QUICK_SELECT = " "  # Space bar for quick select
    UNDO = "u"  # Undo last action
    REDO = "r"  # Redo last undone action
    RECOMMEND = "?"  # Show recommendations
    BOOKMARK = "m"  # Bookmark/mark for later
    QUICK_SYNC = "!"  # Quick sync selected items
    SHOW_STATS = "i"  # Show info/stats
    RANDOM = "~"  # Random selection
    HOME = "0"  # Go to first page
    END = "$"  # Go to last page
    
    # Phase 4: Smart actions
    AUTO_SELECT = "auto"  # Smart auto-selection
    LEARN_MODE = "learn"  # Toggle learning mode
    QUICK_SIMILAR = "sim"  # Select similar items
    SMART_SORT = "sort"  # Sort by user preferences
    SESSION_STATS = "session"  # Show session statistics
    
    @classmethod
    def get_help_text(cls, context: str) -> str:
        """Get context-sensitive help text."""
        help_texts = {
            "main": """
Navigation Commands:
  \\[n]ext     - Next page
  \\[p]revious - Previous page
  \\[s]earch   - Search media
  \\[h]elp     - Show this help
  \\[q]uit     - Exit interactive mode
  \\[b]ack     - Go back to previous step
            """,
            "movies": """
🎬 Movie Browser Commands:
  
Basic Navigation:
  \\[n]ext     - Next page          \\[p]revious - Previous page
  \\[j]ump     - Jump to page       \\[s]earch   - Search movies
  \\[b]ack     - Back to selection  \\[q]uit     - Exit
  
Quick Navigation:
  \\[0]        - First page         \\[$]        - Last page
  \\[~]        - Random selection   \\[?]        - Show recommendations
  
Actions:
  \\[u]ndo     - Undo last action   \\[r]edo     - Redo action
  \\[i]nfo     - Show library stats \\[m]ark     - Bookmark
  \\[h]elp     - Show this help
            """,
            "shows": """
📺 TV Show Browser Commands:
  
Basic Navigation:
  \\[n]ext     - Next page          \\[p]revious - Previous page
  \\[j]ump     - Jump to page       \\[s]earch   - Search shows
  \\[b]ack     - Back to selection  \\[q]uit     - Exit
  
Quick Navigation:
  \\[0]        - First page         \\[$]        - Last page
  \\[~]        - Random selection   \\[?]        - Show recommendations
  
Actions:
  \\[u]ndo     - Undo last action   \\[r]edo     - Redo action
  \\[i]nfo     - Show library stats \\[m]ark     - Bookmark
  \\[h]elp     - Show this help
            """
        }
        return help_texts.get(context, help_texts["main"])


class BrowserInterface:
    """Rich interface for browsing media with pagination and navigation."""
    
    def __init__(self, console: Console):
        self.console = console
        self.page_size = 10
        self.status_checker = SyncStatusChecker()
        
    def browse_movies(self, movies: List[MediaItem], page: int = 1, selected_movies: List[MediaItem] = None) -> Tuple[Optional[List[MediaItem]], str]:
        """
        Paginated movie browser with selection indicators.
        
        Returns:
            Tuple of (selected_movies, command) where command indicates next action
        """
        if selected_movies is None:
            selected_movies = []
        
        total_pages = (len(movies) + self.page_size - 1) // self.page_size
        
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
            
        start_idx = (page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_movies = movies[start_idx:end_idx]
        
        # Create movie table with selection indicators
        table = Table(title=f"🎬 Movie Selection (Page {page}/{total_pages})")
        table.add_column("#", width=3, style="dim")
        table.add_column("✓", width=2, style="green")  # Selection indicator
        table.add_column("Title", style="bold")
        table.add_column("Size", width=10, style="green")
        table.add_column("Path", style="dim", max_width=45)
        
        for i, movie in enumerate(page_movies, 1):
            size_str = SelectionState().format_size(movie.file_size)
            # Truncate path for display
            path_display = str(movie.relative_path)
            if len(path_display) > 40:
                path_display = "..." + path_display[-37:]
            
            # Check if movie is already selected
            is_selected = any(selected.source_path == movie.source_path for selected in selected_movies)
            selection_indicator = "✅" if is_selected else ""
            
            # Style title differently if already selected
            title_style = "dim" if is_selected else "bold"
            
            table.add_row(
                str(i),
                selection_indicator,
                f"[{title_style}]{movie.title}[/{title_style}]",
                size_str,
                path_display
            )
        
        # Show statistics
        total_size = sum(m.file_size for m in movies)
        selected_count = len(selected_movies)
        stats_text = f"Total: {len(movies)} movies • {SelectionState().format_size(total_size)}"
        if selected_count > 0:
            stats_text += f" • {selected_count} selected"
        
        panel = Panel(
            table,
            subtitle=stats_text,
            border_style="blue"
        )
        
        self.console.print(panel)
        self.console.print()
        
        # Phase 3: Enhanced navigation help with batch operations
        nav_help = f"Navigation: \\[n]ext, \\[p]revious, \\[s]earch, \\[b]ack, \\[q]uit"
        if total_pages > 1:
            nav_help += f" • Page {page}/{total_pages} • \\[j]ump to page"
        
        self.console.print(nav_help, style="dim")
        
        # Phase 3: Show batch selection options
        self.console.print("📋 Batch Selection: \\[*] all on page, \\[**] all movies, \\[f] filter, ranges (1,3,5-8)", style="dim")
        
        # Get user input
        response = Prompt.ask(
            f"Select movie(s) \\[1-{len(page_movies)}], range, or command",
            default=""
        ).strip().lower()
        
        # Handle navigation commands
        if response in [NavigationCommands.NEXT, "next"]:
            return None, "next"
        elif response in [NavigationCommands.PREVIOUS, "prev", "previous"]:
            return None, "previous"
        elif response in [NavigationCommands.SEARCH, "search"]:
            return None, "search"
        elif response in [NavigationCommands.JUMP, "jump", "j"]:
            return None, "jump"
        elif response in [NavigationCommands.BACK, "back"]:
            return None, "back"
        elif response in [NavigationCommands.QUIT, "quit", "exit"]:
            return None, "quit"
        elif response in [NavigationCommands.HELP, "help"]:
            self.console.print(NavigationCommands.get_help_text("movies"))
            return None, "help"
        elif response == "":
            return None, "back"
        
        # Phase 4: Enhanced keyboard shortcuts
        elif response == NavigationCommands.HOME:
            return None, "home"
        elif response == NavigationCommands.END:
            return None, "end"
        elif response == NavigationCommands.RANDOM:
            return None, "random"
        elif response == NavigationCommands.RECOMMEND:
            return None, "recommend"
        elif response == NavigationCommands.UNDO:
            return None, "undo"
        elif response == NavigationCommands.REDO:
            return None, "redo"
        elif response == NavigationCommands.SHOW_STATS:
            return None, "stats"
        elif response == NavigationCommands.BOOKMARK:
            return None, "bookmark"
        
        # Phase 3: Batch selection commands
        elif response == "*":
            # Select all movies on current page
            return page_movies, "batch_selected"
        elif response == "**":
            # Select all movies in the current list
            return movies, "batch_all_selected"
        elif response == "f" or response == "filter":
            return None, "filter"
        
        # Phase 3: Enhanced selection handling (ranges, multiple selections)
        try:
            # Handle multiple selections and ranges
            selected_movies = self._parse_movie_selection(response, page_movies)
            if selected_movies:
                return selected_movies, "batch_selected" if len(selected_movies) > 1 else "selected"
            else:
                self.console.print(f"❌ Invalid selection. Please choose 1-{len(page_movies)}", style="red")
                return None, "invalid"
        except ValueError:
            self.console.print(f"❌ Invalid input. Use numbers (1,3,5), ranges (1-5), * for page, ** for all, or commands", style="red")
            return None, "invalid"
    
    def _parse_movie_selection(self, response: str, page_movies: List[MediaItem]) -> List[MediaItem]:
        """Parse user selection input for movies (single, multiple, ranges)."""
        selected_movies = []
        
        # Handle single number
        if response.isdigit():
            idx = int(response) - 1
            if 0 <= idx < len(page_movies):
                return [page_movies[idx]]
            return []
        
        # Handle comma-separated selections and ranges
        parts = response.split(',')
        
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Range like "1-5"
                try:
                    start, end = part.split('-')
                    start_idx = int(start.strip()) - 1
                    end_idx = int(end.strip()) - 1
                    
                    for i in range(start_idx, end_idx + 1):
                        if 0 <= i < len(page_movies):
                            selected_movies.append(page_movies[i])
                except ValueError:
                    continue
            else:
                # Individual number
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(page_movies):
                        selected_movies.append(page_movies[idx])
                except ValueError:
                    continue
        
        # Remove duplicates while preserving order
        seen_paths = set()
        unique_selected = []
        for movie in selected_movies:
            movie_path = str(movie.source_path)
            if movie_path not in seen_paths:
                seen_paths.add(movie_path)
                unique_selected.append(movie)
        
        return unique_selected
    
    def browse_shows(self, shows: List[str], page: int = 1, library: MediaLibrary = None, selected_episodes: List[MediaItem] = None) -> Tuple[Optional[str], str]:
        """
        Paginated show browser with selection indicators.
        
        Returns:
            Tuple of (selected_show, command) where command indicates next action
        """
        if selected_episodes is None:
            selected_episodes = []
        
        total_pages = (len(shows) + self.page_size - 1) // self.page_size
        
        if page < 1:
            page = 1
        elif page > total_pages:
            page = total_pages
            
        start_idx = (page - 1) * self.page_size
        end_idx = start_idx + self.page_size
        page_shows = shows[start_idx:end_idx]
        
        # Create shows table with selection indicators
        table = Table(title=f"📺 TV Show Selection (Page {page}/{total_pages})")
        table.add_column("#", width=3, style="dim")
        table.add_column("✓", width=2, style="green")  # Selection indicator
        table.add_column("Show Name", style="bold")
        table.add_column("Episodes", width=10, style="green")
        table.add_column("Seasons", width=8, style="blue")
        
        for i, show in enumerate(page_shows, 1):
            # Get episode count and season count from library if available
            episode_count = "?"
            season_count = "?"
            
            if library:
                episodes = library.get_show_episodes(show)
                episode_count = str(len(episodes))
                
                # Count unique seasons
                seasons = set()
                for episode in episodes:
                    if episode.season:
                        seasons.add(episode.season)
                season_count = str(len(seasons))
            
            # Check if any episodes from this show are already selected
            show_episodes_selected = sum(1 for ep in selected_episodes if ep.show_name == show)
            selection_indicator = "✅" if show_episodes_selected > 0 else ""
            
            # Style show name differently if episodes are already selected
            show_style = "dim" if show_episodes_selected > 0 else "bold"
            
            table.add_row(
                str(i),
                selection_indicator,
                f"[{show_style}]{show}[/{show_style}]",
                episode_count,
                season_count
            )
        
        # Show statistics
        total_selected_episodes = len(selected_episodes)
        stats_text = f"Total: {len(shows)} TV shows"
        if total_selected_episodes > 0:
            stats_text += f" • {total_selected_episodes} episodes selected"
        
        panel = Panel(
            table,
            subtitle=stats_text,
            border_style="blue"
        )
        
        self.console.print(panel)
        self.console.print()
        
        # Phase 3: Enhanced navigation help with batch operations
        nav_help = f"Navigation: \\[n]ext, \\[p]revious, \\[s]earch, \\[b]ack, \\[q]uit"
        if total_pages > 1:
            nav_help += f" • Page {page}/{total_pages} • \\[j]ump to page"
        
        self.console.print(nav_help, style="dim")
        
        # Phase 3: Show batch selection options for TV shows
        self.console.print("📋 Batch Selection: \\[*] all on page, \\[**] all shows, \\[f] filter, ranges (1,3,5-8)", style="dim")
        
        # Get user input
        response = Prompt.ask(
            f"Select show(s) \\[1-{len(page_shows)}], range, or command",
            default=""
        ).strip().lower()
        
        # Handle navigation commands
        if response in [NavigationCommands.NEXT, "next"]:
            return None, "next"
        elif response in [NavigationCommands.PREVIOUS, "prev", "previous"]:
            return None, "previous"
        elif response in [NavigationCommands.SEARCH, "search"]:
            return None, "search"
        elif response in [NavigationCommands.JUMP, "jump", "j"]:
            return None, "jump"
        elif response in [NavigationCommands.BACK, "back"]:
            return None, "back"
        elif response in [NavigationCommands.QUIT, "quit", "exit"]:
            return None, "quit"
        elif response in [NavigationCommands.HELP, "help"]:
            self.console.print(NavigationCommands.get_help_text("shows"))
            return None, "help"
        elif response == "":
            return None, "back"
        
        # Phase 4: Enhanced keyboard shortcuts
        elif response == NavigationCommands.HOME:
            return None, "home"
        elif response == NavigationCommands.END:
            return None, "end"
        elif response == NavigationCommands.RANDOM:
            return None, "random"
        elif response == NavigationCommands.RECOMMEND:
            return None, "recommend"
        elif response == NavigationCommands.UNDO:
            return None, "undo"
        elif response == NavigationCommands.REDO:
            return None, "redo"
        elif response == NavigationCommands.SHOW_STATS:
            return None, "stats"
        elif response == NavigationCommands.BOOKMARK:
            return None, "bookmark"
        
        # Phase 3: Batch selection commands for TV shows
        elif response == "*":
            # Select all shows on current page
            return page_shows, "batch_selected"
        elif response == "**":
            # Select all shows in the current list
            return shows, "batch_all_selected"
        elif response == "f" or response == "filter":
            return None, "filter"
        
        # Phase 3: Enhanced selection handling (ranges, multiple selections)
        try:
            # Handle multiple selections and ranges
            selected_shows = self._parse_show_selection(response, page_shows)
            if selected_shows:
                if len(selected_shows) == 1:
                    return selected_shows[0], "selected"
                else:
                    return selected_shows, "batch_selected"
            else:
                self.console.print(f"❌ Invalid selection. Please choose 1-{len(page_shows)}", style="red")
                return None, "invalid"
        except ValueError:
            self.console.print(f"❌ Invalid input. Use numbers (1,3,5), ranges (1-5), * for page, ** for all, or commands", style="red")
            return None, "invalid"
    
    def _parse_show_selection(self, response: str, page_shows: List[str]) -> List[str]:
        """Parse user selection input for TV shows (single, multiple, ranges)."""
        selected_shows = []
        
        # Handle single number
        if response.isdigit():
            idx = int(response) - 1
            if 0 <= idx < len(page_shows):
                return [page_shows[idx]]
            return []
        
        # Handle comma-separated selections and ranges
        parts = response.split(',')
        
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Range like "1-5"
                try:
                    start, end = part.split('-')
                    start_idx = int(start.strip()) - 1
                    end_idx = int(end.strip()) - 1
                    
                    for i in range(start_idx, end_idx + 1):
                        if 0 <= i < len(page_shows):
                            selected_shows.append(page_shows[i])
                except ValueError:
                    continue
            else:
                # Individual number
                try:
                    idx = int(part) - 1
                    if 0 <= idx < len(page_shows):
                        selected_shows.append(page_shows[idx])
                except ValueError:
                    continue
        
        # Remove duplicates while preserving order
        seen_shows = set()
        unique_selected = []
        for show in selected_shows:
            if show not in seen_shows:
                seen_shows.add(show)
                unique_selected.append(show)
        
        return unique_selected
    
    def browse_seasons(self, show_name: str, library: MediaLibrary) -> Tuple[Optional[List[int]], str]:
        """
        Season browser for a TV show.
        
        Returns:
            Tuple of (selected_seasons, command) where command indicates next action
        """
        # Get all episodes for the show
        all_episodes = library.get_show_episodes(show_name)
        
        if not all_episodes:
            self.console.print(f"❌ No episodes found for {show_name}", style="red")
            return None, "back"
        
        # Group episodes by season
        seasons = {}
        for episode in all_episodes:
            season_num = episode.season or 1
            if season_num not in seasons:
                seasons[season_num] = []
            seasons[season_num].append(episode)
        
        # Sort seasons
        sorted_seasons = sorted(seasons.keys())
        
        # Create season table
        table = Table(title=f"📺 {show_name} - Season Selection")
        table.add_column("#", width=3, style="dim")
        table.add_column("Season", style="bold")
        table.add_column("Episodes", width=10, style="green")
        table.add_column("Size", width=12, style="blue")
        table.add_column("Status", width=18, style="yellow")
        
        for i, season_num in enumerate(sorted_seasons, 1):
            season_episodes = seasons[season_num]
            episode_count = len(season_episodes)
            
            # Calculate total size
            total_size = sum(ep.file_size for ep in season_episodes)
            
            # Get season status
            _, status_text = self.status_checker.get_season_status(season_episodes)
            
            table.add_row(
                str(i),
                f"Season {season_num}",
                str(episode_count),
                SelectionState().format_size(total_size),
                status_text
            )
        
        # Show statistics
        total_episodes = sum(len(eps) for eps in seasons.values())
        total_size = sum(ep.file_size for ep in all_episodes)
        stats_text = f"Total: {len(seasons)} seasons • {total_episodes} episodes • {SelectionState().format_size(total_size)}"
        
        panel = Panel(
            table,
            subtitle=stats_text,
            border_style="blue"
        )
        
        self.console.print(panel)
        self.console.print()
        
        # Navigation help
        nav_help = "Navigation: \\[a]ll seasons, \\[b]ack to shows, \\[q]uit"
        self.console.print(nav_help, style="dim")
        
        # Get user input
        response = Prompt.ask(
            f"Select season \\[1-{len(sorted_seasons)}] or command",
            default=""
        ).strip().lower()
        
        # Handle navigation commands
        if response in [NavigationCommands.ALL, "all"]:
            return sorted_seasons, "all_selected"
        elif response in [NavigationCommands.BACK, "back"]:
            return None, "back"
        elif response in [NavigationCommands.QUIT, "quit", "exit"]:
            return None, "quit"
        elif response in [NavigationCommands.HELP, "help"]:
            self.console.print(NavigationCommands.get_help_text("seasons"))
            return None, "help"
        elif response == "":
            return None, "back"
        
        # Handle season selection
        try:
            selection = int(response)
            if 1 <= selection <= len(sorted_seasons):
                selected_season = sorted_seasons[selection - 1]
                return [selected_season], "selected"
            else:
                self.console.print(f"❌ Invalid selection. Please choose 1-{len(sorted_seasons)}", style="red")
                return None, "invalid"
        except ValueError:
            self.console.print(f"❌ Invalid input. Type a number 1-{len(sorted_seasons)} or navigation command", style="red")
            return None, "invalid"
    
    def browse_episodes(self, show_name: str, season: int, library: MediaLibrary) -> Tuple[Optional[List[MediaItem]], str]:
        """
        Episode browser for a specific season.
        
        Returns:
            Tuple of (selected_episodes, command) where command indicates next action
        """
        # Get episodes for the specific season
        all_episodes = library.get_show_episodes(show_name)
        season_episodes = [ep for ep in all_episodes if ep.season == season]
        
        if not season_episodes:
            self.console.print(f"❌ No episodes found for {show_name} Season {season}", style="red")
            return None, "back"
        
        # Sort episodes by episode number
        sorted_episodes = sorted(season_episodes, key=lambda ep: ep.episode or 0)
        
        # Create episode table
        table = Table(title=f"📺 {show_name} - Season {season} Episodes")
        table.add_column("#", width=3, style="dim")
        table.add_column("Episode", style="bold", width=10)
        table.add_column("Title", style="green", width=40)
        table.add_column("Size", width=10, style="blue")
        table.add_column("Status", width=12, style="yellow")
        
        for i, episode in enumerate(sorted_episodes, 1):
            # Get episode status
            status = self.status_checker.check_item_status(episode)
            status_text = self.status_checker.get_status_indicator(status)
            
            # Format episode info
            episode_info = f"S{episode.season:02d}E{episode.episode:02d}" if episode.season and episode.episode else "N/A"
            episode_title = episode.episode_title or episode.title
            if len(episode_title) > 35:
                episode_title = episode_title[:32] + "..."
            
            table.add_row(
                str(i),
                episode_info,
                episode_title,
                SelectionState().format_size(episode.file_size),
                status_text
            )
        
        # Show statistics
        total_size = sum(ep.file_size for ep in sorted_episodes)
        stats_text = f"Total: {len(sorted_episodes)} episodes • {SelectionState().format_size(total_size)}"
        
        panel = Panel(
            table,
            subtitle=stats_text,
            border_style="blue"
        )
        
        self.console.print(panel)
        self.console.print()
        
        # Show selection options
        self.console.print("📋 Selection Options:", style="bold yellow")
        self.console.print("  • Enter episode numbers (e.g., 1,3,5-8)")
        self.console.print("  • Type 'all' to select all episodes")
        self.console.print("  • Type 'new' to select only unsynced episodes")
        self.console.print("  • Type 'back' to return to season selection")
        self.console.print()
        
        # Get user selection
        response = Prompt.ask("Select episodes to sync", default="new").strip().lower()
        
        # Handle navigation commands
        if response in [NavigationCommands.ALL, "all"]:
            return sorted_episodes, "all_selected"
        elif response in [NavigationCommands.BACK, "back"]:
            return None, "back"
        elif response in [NavigationCommands.QUIT, "quit", "exit"]:
            return None, "quit"
        elif response in [NavigationCommands.NEW, "new"]:
            # Select only unsynced episodes
            new_episodes = []
            for episode in sorted_episodes:
                status = self.status_checker.check_item_status(episode)
                if status != SyncStatus.SYNCED:
                    new_episodes.append(episode)
            
            if not new_episodes:
                self.console.print("✅ All episodes are already synced!", style="green")
                return None, "all_synced"
            
            return new_episodes, "new_selected"
        elif response == "":
            # Default to 'new'
            new_episodes = []
            for episode in sorted_episodes:
                status = self.status_checker.check_item_status(episode)
                if status != SyncStatus.SYNCED:
                    new_episodes.append(episode)
            
            if not new_episodes:
                self.console.print("✅ All episodes are already synced!", style="green")
                return None, "all_synced"
            
            return new_episodes, "new_selected"
        
        # Handle custom selection (numbers, ranges)
        try:
            selected_episodes = []
            parts = response.split(',')
            
            for part in parts:
                part = part.strip()
                if '-' in part:
                    # Range like "5-8"
                    start, end = part.split('-')
                    start_idx = int(start.strip()) - 1
                    end_idx = int(end.strip()) - 1
                    
                    for i in range(start_idx, end_idx + 1):
                        if 0 <= i < len(sorted_episodes):
                            selected_episodes.append(sorted_episodes[i])
                else:
                    # Individual number
                    idx = int(part) - 1
                    if 0 <= idx < len(sorted_episodes):
                        selected_episodes.append(sorted_episodes[idx])
            
            # Remove duplicates while preserving order
            seen_paths = set()
            unique_selected = []
            for episode in selected_episodes:
                # Use the source path as a unique identifier
                episode_path = str(episode.source_path)
                if episode_path not in seen_paths:
                    seen_paths.add(episode_path)
                    unique_selected.append(episode)
            
            return unique_selected, "custom_selected"
            
        except ValueError:
            self.console.print("❌ Invalid selection format. Use numbers, ranges (1-5), or commands", style="red")
            return None, "invalid"


class EnhancedSearchInterface:
    """Advanced search interface with fuzzy matching and filtering."""
    
    def __init__(self, console: Console):
        self.console = console
    
    def fuzzy_search_movies(self, library: MediaLibrary, query: str, max_results: int = 20) -> List[MediaItem]:
        """Perform fuzzy search on movie titles with similarity scoring."""
        if not query:
            return []
        
        query_lower = query.lower()
        candidates = []
        
        for movie in library.movies:
            title_lower = movie.title.lower()
            
            # Calculate similarity scores
            scores = []
            
            # Exact match (highest score)
            if query_lower == title_lower:
                scores.append(1.0)
            
            # Starts with query
            elif title_lower.startswith(query_lower):
                scores.append(0.9)
            
            # Contains query
            elif query_lower in title_lower:
                scores.append(0.8)
            
            # Fuzzy matching using difflib
            similarity = difflib.SequenceMatcher(None, query_lower, title_lower).ratio()
            scores.append(similarity)
            
            # Word-based matching
            query_words = query_lower.split()
            title_words = title_lower.split()
            
            if query_words and title_words:
                word_matches = 0
                for q_word in query_words:
                    for t_word in title_words:
                        if len(q_word) >= 3 and len(t_word) >= 3 and (q_word in t_word or t_word in q_word):
                            word_matches += 1
                            break
                
                word_score = word_matches / len(query_words)
                scores.append(word_score)
            
            # Use the best score
            best_score = max(scores)
            
            # Only include if score is above threshold
            if best_score >= 0.5:
                candidates.append((movie, best_score))
        
        # Sort by score (descending) and return top results
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [movie for movie, score in candidates[:max_results]]
    
    def fuzzy_search_shows(self, library: MediaLibrary, query: str, max_results: int = 20) -> List[str]:
        """Perform fuzzy search on TV show names with similarity scoring."""
        if not query:
            return []
        
        query_lower = query.lower()
        candidates = []
        
        for show_name in library.tv_shows.keys():
            show_lower = show_name.lower()
            
            # Calculate similarity scores
            scores = []
            
            # Exact match (highest score)
            if query_lower == show_lower:
                scores.append(1.0)
            
            # Starts with query
            elif show_lower.startswith(query_lower):
                scores.append(0.9)
            
            # Contains query
            elif query_lower in show_lower:
                scores.append(0.8)
            
            # Fuzzy matching using difflib
            similarity = difflib.SequenceMatcher(None, query_lower, show_lower).ratio()
            scores.append(similarity)
            
            # Word-based matching
            query_words = query_lower.split()
            show_words = show_lower.split()
            
            if query_words and show_words:
                word_matches = 0
                for q_word in query_words:
                    for s_word in show_words:
                        if len(q_word) >= 3 and len(s_word) >= 3 and (q_word in s_word or s_word in q_word):
                            word_matches += 1
                            break
                
                word_score = word_matches / len(query_words)
                scores.append(word_score)
            
            # Use the best score
            best_score = max(scores)
            
            # Only include if score is above threshold
            if best_score >= 0.5:
                candidates.append((show_name, best_score))
        
        # Sort by score (descending) and return top results
        candidates.sort(key=lambda x: x[1], reverse=True)
        return [show_name for show_name, score in candidates[:max_results]]
    
    def extract_metadata(self, item: MediaItem) -> Dict[str, Any]:
        """Extract metadata from media item path and filename."""
        metadata = {
            'year': None,
            'quality': None,
            'genre': None,
            'language': None,
            'codec': None,
            'resolution': None
        }
        
        # Combine path and filename for analysis
        full_path = item.source_path.lower()
        filename = os.path.basename(item.source_path).lower()
        
        # Extract year (4 digits)
        year_match = re.search(r'\b(19|20)\d{2}\b', full_path)
        if year_match:
            metadata['year'] = int(year_match.group())
        
        # Extract quality indicators
        quality_patterns = {
            '4k': r'\b(4k|2160p|uhd)\b',
            '1080p': r'\b1080p?\b',
            '720p': r'\b720p?\b',
            '480p': r'\b480p?\b',
            'dvd': r'\bdvd\b',
            'bluray': r'\b(bluray|blu-ray|bdr|bd)\b',
            'webrip': r'\b(webrip|web-rip)\b',
            'webdl': r'\b(webdl|web-dl)\b',
            'hdtv': r'\bhdtv\b',
            'cam': r'\bcam\b',
            'ts': r'\b(ts|telesync)\b'
        }
        
        for quality, pattern in quality_patterns.items():
            if re.search(pattern, full_path):
                metadata['quality'] = quality
                break
        
        # Extract codec
        codec_patterns = {
            'h264': r'\b(h\.?264|x264|avc)\b',
            'h265': r'\b(h\.?265|x265|hevc)\b',
            'xvid': r'\bxvid\b',
            'divx': r'\bdivx\b'
        }
        
        for codec, pattern in codec_patterns.items():
            if re.search(pattern, full_path):
                metadata['codec'] = codec
                break
        
        # Extract resolution
        resolution_patterns = {
            '2160p': r'\b2160p?\b',
            '1080p': r'\b1080p?\b',
            '720p': r'\b720p?\b',
            '480p': r'\b480p?\b'
        }
        
        for resolution, pattern in resolution_patterns.items():
            if re.search(pattern, full_path):
                metadata['resolution'] = resolution
                break
        
        return metadata
    
    def filter_movies_by_criteria(self, movies: List[MediaItem], criteria: Dict[str, Any]) -> List[MediaItem]:
        """Filter movies based on various criteria."""
        filtered = []
        
        for movie in movies:
            metadata = self.extract_metadata(movie)
            
            # Apply filters
            if criteria.get('year'):
                if metadata.get('year') != criteria['year']:
                    continue
            
            if criteria.get('quality'):
                if metadata.get('quality') != criteria['quality']:
                    continue
            
            if criteria.get('min_size'):
                if movie.file_size < criteria['min_size']:
                    continue
            
            if criteria.get('max_size'):
                if movie.file_size > criteria['max_size']:
                    continue
            
            if criteria.get('resolution'):
                if metadata.get('resolution') != criteria['resolution']:
                    continue
            
            if criteria.get('codec'):
                if metadata.get('codec') != criteria['codec']:
                    continue
            
            filtered.append(movie)
        
        return filtered
    
    def advanced_search_movies(self, library: MediaLibrary) -> List[MediaItem]:
        """Interactive advanced search for movies."""
        self.console.print("🔍 Advanced Movie Search", style="bold green")
        self.console.print()
        
        # Search query
        query = Prompt.ask("Search term (optional)", default="").strip()
        
        # Start with all movies or search results
        if query:
            movies = self.fuzzy_search_movies(library, query)
            if not movies:
                self.console.print(f"❌ No movies found matching '{query}'", style="red")
                return []
            self.console.print(f"Found {len(movies)} movies matching '{query}'", style="green")
        else:
            movies = library.get_all_movies_sorted()
            self.console.print(f"Working with all {len(movies)} movies", style="blue")
        
        # Apply filters
        criteria = {}
        
        # Year filter
        year_input = Prompt.ask("Filter by year (optional)", default="").strip()
        if year_input:
            try:
                criteria['year'] = int(year_input)
            except ValueError:
                self.console.print("⚠️ Invalid year format, ignoring", style="yellow")
        
        # Quality filter
        self.console.print("\nQuality options: 4k, 1080p, 720p, 480p, bluray, webrip, webdl, hdtv")
        quality_input = Prompt.ask("Filter by quality (optional)", default="").strip().lower()
        if quality_input:
            criteria['quality'] = quality_input
        
        # Size filter
        size_input = Prompt.ask("Minimum size in GB (optional)", default="").strip()
        if size_input:
            try:
                criteria['min_size'] = float(size_input) * 1024 * 1024 * 1024  # Convert GB to bytes
            except ValueError:
                self.console.print("⚠️ Invalid size format, ignoring", style="yellow")
        
        # Apply filters
        if criteria:
            filtered_movies = self.filter_movies_by_criteria(movies, criteria)
            self.console.print(f"Applied filters: {len(filtered_movies)} movies match criteria", style="green")
            return filtered_movies
        
        return movies
    
    def get_popular_years(self, library: MediaLibrary) -> List[int]:
        """Get most common years from movie library."""
        year_counts = defaultdict(int)
        
        for movie in library.movies:
            metadata = self.extract_metadata(movie)
            if metadata.get('year'):
                year_counts[metadata['year']] += 1
        
        # Return top 10 years sorted by count
        return sorted(year_counts.keys(), key=lambda y: year_counts[y], reverse=True)[:10]
    
    def get_popular_qualities(self, library: MediaLibrary) -> List[str]:
        """Get most common qualities from movie library."""
        quality_counts = defaultdict(int)
        
        for movie in library.movies:
            metadata = self.extract_metadata(movie)
            if metadata.get('quality'):
                quality_counts[metadata['quality']] += 1
        
        # Return qualities sorted by count
        return sorted(quality_counts.keys(), key=lambda q: quality_counts[q], reverse=True)


@dataclass
class SelectionPreset:
    """Saved selection preset for quick reuse."""
    name: str
    description: str
    media_type: str
    criteria: Dict[str, Any]
    created_at: float
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'name': self.name,
            'description': self.description,
            'media_type': self.media_type,
            'criteria': self.criteria,
            'created_at': self.created_at
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SelectionPreset':
        """Create preset from dictionary."""
        return cls(
            name=data['name'],
            description=data['description'],
            media_type=data['media_type'],
            criteria=data['criteria'],
            created_at=data['created_at']
        )


class SmartRecommendationEngine:
    """AI-like recommendation engine based on user behavior patterns."""
    
    def __init__(self, console: Console):
        self.console = console
        self.enhanced_search = EnhancedSearchInterface(console)
    
    def get_recommendations(self, library: MediaLibrary, user_patterns: UserBehaviorPattern, limit: int = 10) -> List[MediaItem]:
        """Generate smart recommendations based on user patterns."""
        recommendations = []
        
        # Get user preferences
        preferred_year_range = user_patterns.get_preferred_year_range()
        preferred_quality = user_patterns.get_top_quality()
        preferred_size_range = user_patterns.get_preferred_size_range()
        
        # Score all movies based on user preferences
        scored_items = []
        
        for movie in library.movies:
            score = self._calculate_recommendation_score(movie, user_patterns)
            if score > 0.3:  # Minimum threshold
                scored_items.append((movie, score))
        
        # Sort by score and return top items
        scored_items.sort(key=lambda x: x[1], reverse=True)
        return [item for item, score in scored_items[:limit]]
    
    def _calculate_recommendation_score(self, item: MediaItem, patterns: UserBehaviorPattern) -> float:
        """Calculate recommendation score for an item based on user patterns."""
        score = 0.0
        metadata = self.enhanced_search.extract_metadata(item)
        
        # Year preference scoring
        if metadata.get('year') and patterns.preferred_years:
            year = metadata['year']
            year_range = patterns.get_preferred_year_range()
            if year_range[0] <= year <= year_range[1]:
                # Boost score for years in preferred range
                year_frequency = patterns.preferred_years.get(year, 0)
                score += 0.3 + (year_frequency * 0.1)
        
        # Quality preference scoring
        if metadata.get('quality') and patterns.preferred_qualities:
            quality = metadata['quality']
            if quality in patterns.preferred_qualities:
                frequency = patterns.preferred_qualities[quality]
                score += 0.2 + (frequency * 0.05)
        
        # Size preference scoring
        if patterns.preferred_sizes:
            size_range = patterns.get_preferred_size_range()
            if size_range[0] <= item.file_size <= size_range[1]:
                score += 0.2
        
        # Similar to recent selections
        if patterns.session_selections:
            # Check for similar titles or franchises
            for selected_item in patterns.session_selections[-5:]:  # Last 5 selections
                if self._items_are_similar(item, selected_item):
                    score += 0.3
                    break
        
        # Random boost for variety
        import random
        score += random.uniform(0.0, 0.1)
        
        return min(score, 1.0)  # Cap at 1.0
    
    def _items_are_similar(self, item1: MediaItem, item2: MediaItem) -> bool:
        """Check if two items are similar (franchise, genre, etc.)."""
        # Simple similarity check based on title words
        words1 = set(item1.title.lower().split())
        words2 = set(item2.title.lower().split())
        
        # Remove common words
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        words1 -= common_words
        words2 -= common_words
        
        # Check for shared words
        if words1 & words2:  # Intersection
            return True
        
        # Check for franchise patterns (e.g., "Movie 1" and "Movie 2")
        if any(word in item2.title.lower() for word in words1 if len(word) > 3):
            return True
        
        return False
    
    def get_smart_suggestions(self, library: MediaLibrary, patterns: UserBehaviorPattern, context: str) -> Dict[str, List[MediaItem]]:
        """Get categorized smart suggestions."""
        suggestions = {
            "recommended": [],
            "similar_to_recent": [],
            "trending_quality": [],
            "size_matched": []
        }
        
        # Get general recommendations
        suggestions["recommended"] = self.get_recommendations(library, patterns, 5)
        
        # Similar to recent selections
        if patterns.session_selections:
            recent_item = patterns.session_selections[-1]
            similar_items = []
            for movie in library.movies:
                if movie != recent_item and self._items_are_similar(movie, recent_item):
                    similar_items.append(movie)
            suggestions["similar_to_recent"] = similar_items[:3]
        
        # Trending quality (user's preferred quality)
        preferred_quality = patterns.get_top_quality()
        if preferred_quality:
            quality_matches = self.enhanced_search.filter_movies_by_criteria(
                library.movies, 
                {'quality': preferred_quality}
            )
            suggestions["trending_quality"] = quality_matches[:3]
        
        # Size matched (within preferred range)
        size_range = patterns.get_preferred_size_range()
        if size_range[0] > 0:
            size_matches = []
            for movie in library.movies:
                if size_range[0] <= movie.file_size <= size_range[1]:
                    size_matches.append(movie)
            suggestions["size_matched"] = size_matches[:3]
        
        return suggestions
    
    def display_recommendations(self, library: MediaLibrary, patterns: UserBehaviorPattern):
        """Display smart recommendations in a beautiful format."""
        self.console.print("🎯 Smart Recommendations", style="bold green")
        self.console.print("Based on your selection patterns", style="dim")
        self.console.print()
        
        suggestions = self.get_smart_suggestions(library, patterns, "general")
        
        for category, items in suggestions.items():
            if not items:
                continue
                
            category_names = {
                "recommended": "🌟 Recommended for You",
                "similar_to_recent": "🔄 Similar to Recent",
                "trending_quality": f"🎬 Your Preferred Quality ({patterns.get_top_quality() or 'N/A'})",
                "size_matched": "📊 Perfect Size Match"
            }
            
            self.console.print(f"{category_names.get(category, category.title())}", style="bold cyan")
            
            # Create table for recommendations
            table = Table(show_header=True, header_style="bold magenta")
            table.add_column("#", width=3, style="dim")
            table.add_column("Title", style="bold")
            table.add_column("Year", width=6, style="cyan")
            table.add_column("Quality", width=8, style="yellow")
            table.add_column("Size", width=8, style="green")
            
            for i, item in enumerate(items[:5], 1):
                metadata = self.enhanced_search.extract_metadata(item)
                year = str(metadata.get('year', '?'))
                quality = metadata.get('quality', '?').upper()
                size = SelectionState().format_size(item.file_size)
                
                table.add_row(str(i), item.title, year, quality, size)
            
            self.console.print(table)
            self.console.print()


class PresetManager:
    """Manager for saving and loading selection presets."""
    
    def __init__(self, console: Console):
        self.console = console
        self.presets_file = Path.home() / ".plexsync" / "presets.json"
        self.presets_file.parent.mkdir(exist_ok=True)
    
    def load_presets(self) -> List[SelectionPreset]:
        """Load presets from file."""
        if not self.presets_file.exists():
            return []
        
        try:
            with open(self.presets_file, 'r') as f:
                data = json.load(f)
            
            return [SelectionPreset.from_dict(preset_data) for preset_data in data]
        except Exception as e:
            self.console.print(f"⚠️ Error loading presets: {e}", style="yellow")
            return []
    
    def save_presets(self, presets: List[SelectionPreset]):
        """Save presets to file."""
        try:
            with open(self.presets_file, 'w') as f:
                json.dump([preset.to_dict() for preset in presets], f, indent=2)
        except Exception as e:
            self.console.print(f"❌ Error saving presets: {e}", style="red")
    
    def create_preset(self, name: str, description: str, media_type: str, criteria: Dict[str, Any]) -> SelectionPreset:
        """Create a new preset."""
        return SelectionPreset(
            name=name,
            description=description,
            media_type=media_type,
            criteria=criteria,
            created_at=time.time()
        )
    
    def save_preset_interactive(self, media_type: str, criteria: Dict[str, Any]):
        """Interactive preset saving."""
        self.console.print("💾 Save Selection as Preset", style="bold green")
        self.console.print()
        
        name = Prompt.ask("Preset name").strip()
        if not name:
            self.console.print("❌ Preset name cannot be empty", style="red")
            return
        
        description = Prompt.ask("Description (optional)", default="").strip()
        
        # Load existing presets
        presets = self.load_presets()
        
        # Check for duplicate names
        for preset in presets:
            if preset.name.lower() == name.lower():
                from rich.prompt import Confirm
                if not Confirm.ask(f"Preset '{name}' already exists. Overwrite? [y/N]", default=False):
                    return
                presets = [p for p in presets if p.name.lower() != name.lower()]
                break
        
        # Create and save new preset
        new_preset = self.create_preset(name, description, media_type, criteria)
        presets.append(new_preset)
        
        self.save_presets(presets)
        self.console.print(f"✅ Preset '{name}' saved successfully", style="green")
    
    def load_preset_interactive(self, media_type: str) -> Optional[Dict[str, Any]]:
        """Interactive preset loading."""
        presets = self.load_presets()
        
        # Filter by media type
        compatible_presets = [p for p in presets if p.media_type == media_type or p.media_type == "both"]
        
        if not compatible_presets:
            self.console.print(f"No saved presets found for {media_type}", style="yellow")
            return None
        
        self.console.print("📋 Available Presets", style="bold green")
        self.console.print()
        
        # Show presets table
        table = Table()
        table.add_column("#", width=3, style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Description", style="dim")
        table.add_column("Created", width=12, style="cyan")
        
        for i, preset in enumerate(compatible_presets, 1):
            created_date = time.strftime("%Y-%m-%d", time.localtime(preset.created_at))
            table.add_row(
                str(i),
                preset.name,
                preset.description or "No description",
                created_date
            )
        
        self.console.print(table)
        self.console.print()
        
        while True:
            try:
                choice = IntPrompt.ask(
                    f"Select preset \\[1-{len(compatible_presets)}] or 0 to cancel",
                    default=0
                )
                
                if choice == 0:
                    return None
                elif 1 <= choice <= len(compatible_presets):
                    selected_preset = compatible_presets[choice - 1]
                    self.console.print(f"✅ Loaded preset: {selected_preset.name}", style="green")
                    return selected_preset.criteria
                else:
                    self.console.print(f"❌ Invalid choice. Please select 1-{len(compatible_presets)} or 0", style="red")
                    
            except KeyboardInterrupt:
                return None
            except Exception:
                self.console.print("❌ Invalid input. Please enter a number", style="red")
    
    def save_selection_preset(self, name: str, selection_state: 'SelectionState') -> bool:
        """Save current selection state as a preset."""
        if not selection_state.selected_movies and not selection_state.selected_episodes:
            self.console.print("❌ No selections to save", style="red")
            return False
            
        # Create criteria from selection state
        criteria = {
            'selected_movies': [
                {
                    'title': movie.title,
                    'source_path': str(movie.source_path),
                    'file_size': movie.file_size
                }
                for movie in selection_state.selected_movies
            ],
            'selected_episodes': [
                {
                    'title': episode.title,
                    'source_path': str(episode.source_path),
                    'file_size': episode.file_size,
                    'show_name': episode.show_name,
                    'season': episode.season,
                    'episode': episode.episode
                }
                for episode in selection_state.selected_episodes
            ],
            'media_type': selection_state.media_type.value if selection_state.media_type else 'mixed',
            'total_items': selection_state.total_items(),
            'total_size': selection_state.total_size()
        }
        
        # Determine media type for preset
        if selection_state.selected_movies and selection_state.selected_episodes:
            media_type = 'both'
        elif selection_state.selected_movies:
            media_type = 'movies'
        elif selection_state.selected_episodes:
            media_type = 'tv_shows'
        else:
            media_type = 'mixed'
            
        # Create preset
        preset = self.create_preset(
            name=name,
            description=f"Saved selection: {selection_state.total_items()} items, {selection_state.format_size(selection_state.total_size())}",
            media_type=media_type,
            criteria=criteria
        )
        
        # Load existing presets
        presets = self.load_presets()
        
        # Check for duplicate names
        presets = [p for p in presets if p.name.lower() != name.lower()]
        
        # Add new preset
        presets.append(preset)
        
        # Save presets
        self.save_presets(presets)
        
        self.console.print(f"✅ Saved preset '{name}' successfully", style="green")
        return True
    
    def load_selection_preset(self) -> Optional['SelectionState']:
        """Load a saved selection preset and return SelectionState."""
        presets = self.load_presets()
        
        if not presets:
            self.console.print("No saved presets found", style="yellow")
            return None
            
        self.console.print("📋 Available Selection Presets", style="bold green")
        self.console.print()
        
        # Show presets table
        table = Table()
        table.add_column("#", width=3, style="dim")
        table.add_column("Name", style="bold")
        table.add_column("Description", style="dim")
        table.add_column("Type", width=10, style="cyan")
        table.add_column("Created", width=12, style="yellow")
        
        for i, preset in enumerate(presets, 1):
            created_date = time.strftime("%Y-%m-%d", time.localtime(preset.created_at))
            table.add_row(
                str(i),
                preset.name,
                preset.description or "No description",
                preset.media_type,
                created_date
            )
        
        self.console.print(table)
        self.console.print()
        
        while True:
            try:
                choice = IntPrompt.ask(
                    f"Select preset \\[1-{len(presets)}] or 0 to cancel",
                    default=0
                )
                
                if choice == 0:
                    return None
                elif 1 <= choice <= len(presets):
                    selected_preset = presets[choice - 1]
                    
                    # Create new SelectionState from preset
                    from dataclasses import dataclass
                    selection_state = SelectionState()
                    
                    # Load movies from preset
                    if 'selected_movies' in selected_preset.criteria:
                        # Note: We can't fully reconstruct MediaItem objects from saved data
                        # This is a limitation - presets work better for criteria than exact selections
                        self.console.print("⚠️  Preset contains saved selections, but full media objects cannot be reconstructed", style="yellow")
                        self.console.print("💡 Consider using filter presets instead for better restoration", style="dim")
                        return None
                    
                    self.console.print(f"✅ Loaded preset: {selected_preset.name}", style="green")
                    return selection_state
                else:
                    self.console.print(f"❌ Invalid choice. Please select 1-{len(presets)} or 0", style="red")
                    
            except KeyboardInterrupt:
                return None
            except Exception:
                self.console.print("❌ Invalid input. Please enter a number", style="red")


class SearchInterface:
    """Interface for searching media with fuzzy matching."""
    
    def __init__(self, console: Console):
        self.console = console
        self.enhanced_search = EnhancedSearchInterface(console)
        
    def search_movies(self, library: MediaLibrary) -> List[MediaItem]:
        """Interactive movie search with fuzzy matching."""
        self.console.print("🔍 Movie Search", style="bold green")
        self.console.print()
        
        # Ask for search type
        self.console.print("Search Options:")
        self.console.print("  1. 🔍 Quick Search - Simple text search")
        self.console.print("  2. 🎯 Advanced Search - Fuzzy matching + filters")
        self.console.print()
        
        search_type = Prompt.ask("Select search type \\[1-2]", default="1").strip()
        
        if search_type == "2":
            return self.enhanced_search.advanced_search_movies(library)
        
        # Quick search
        while True:
            query = Prompt.ask("Search for movies", default="").strip()
            
            if not query:
                return []
            
            # Use enhanced fuzzy search instead of basic search
            results = self.enhanced_search.fuzzy_search_movies(library, query)
            
            if not results:
                self.console.print(f"❌ No movies found matching '{query}'", style="red")
                self.console.print("💡 Try a different search term, use advanced search, or browse all movies", style="dim")
                continue
            
            self.console.print(f"Found {len(results)} movies matching '{query}':", style="green")
            
            # Show results in table with metadata
            table = Table()
            table.add_column("#", width=3, style="dim")
            table.add_column("Title", style="bold")
            table.add_column("Year", width=8, style="cyan")
            table.add_column("Quality", width=10, style="yellow")
            table.add_column("Size", width=10, style="green")
            
            for i, movie in enumerate(results[:10], 1):  # Show top 10
                metadata = self.enhanced_search.extract_metadata(movie)
                size_str = SelectionState().format_size(movie.file_size)
                year_str = str(metadata.get('year', '?'))
                quality_str = metadata.get('quality', '?').upper() if metadata.get('quality') else '?'
                
                table.add_row(str(i), movie.title, year_str, quality_str, size_str)
            
            if len(results) > 10:
                table.add_row("...", f"and {len(results) - 10} more", "", "", "")
            
            self.console.print(table)
            self.console.print()
            
            return results
    
    def search_shows(self, library: MediaLibrary) -> List[str]:
        """Interactive show search with fuzzy matching."""
        self.console.print("🔍 TV Show Search", style="bold green")
        self.console.print()
        
        while True:
            query = Prompt.ask("Search for TV shows", default="").strip()
            
            if not query:
                return []
            
            # Use enhanced fuzzy search instead of basic search
            results = self.enhanced_search.fuzzy_search_shows(library, query)
            
            if not results:
                self.console.print(f"❌ No TV shows found matching '{query}'", style="red")
                self.console.print("💡 Try a different search term or browse all shows", style="dim")
                continue
            
            self.console.print(f"Found {len(results)} TV shows matching '{query}':", style="green")
            
            # Show results in table with episode info
            table = Table()
            table.add_column("#", width=3, style="dim")
            table.add_column("Show Name", style="bold")
            table.add_column("Episodes", width=10, style="green")
            table.add_column("Seasons", width=8, style="blue")
            
            for i, show in enumerate(results[:10], 1):  # Show top 10
                episodes = library.get_show_episodes(show)
                episode_count = len(episodes)
                
                # Count unique seasons
                seasons = set()
                for episode in episodes:
                    if episode.season:
                        seasons.add(episode.season)
                season_count = len(seasons)
                
                table.add_row(str(i), show, str(episode_count), str(season_count))
            
            if len(results) > 10:
                table.add_row("...", f"and {len(results) - 10} more", "", "")
            
            self.console.print(table)
            self.console.print()
            
            return results


@dataclass
class FilterCriteria:
    """Criteria for advanced filtering of media items."""
    min_size: Optional[int] = None  # Bytes
    max_size: Optional[int] = None  # Bytes
    min_year: Optional[int] = None
    max_year: Optional[int] = None
    qualities: Optional[List[str]] = None  # ['1080p', '720p', '4K']
    formats: Optional[List[str]] = None   # ['mkv', 'mp4', 'avi']
    exclude_synced: bool = False
    name_contains: Optional[str] = None
    name_excludes: Optional[str] = None


class AdvancedFilteringEngine:
    """Advanced filtering system for media libraries."""
    
    def __init__(self, console: Console):
        self.console = console
        self.enhanced_search = EnhancedSearchInterface(console)
    
    def filter_movies(self, movies: List[MediaItem], criteria: FilterCriteria) -> List[MediaItem]:
        """Filter movies based on criteria."""
        filtered = []
        
        for movie in movies:
            if self._matches_criteria(movie, criteria):
                filtered.append(movie)
        
        return filtered
    
    def filter_shows(self, shows: List[str], library: MediaLibrary, criteria: FilterCriteria) -> List[str]:
        """Filter TV shows based on criteria applied to their episodes."""
        filtered = []
        
        for show in shows:
            episodes = library.get_show_episodes(show)
            # Show matches if any episode matches criteria
            if any(self._matches_criteria(ep, criteria) for ep in episodes):
                filtered.append(show)
        
        return filtered
    
    def _matches_criteria(self, item: MediaItem, criteria: FilterCriteria) -> bool:
        """Check if an item matches the filter criteria."""
        # Size filtering
        if criteria.min_size and item.file_size < criteria.min_size:
            return False
        if criteria.max_size and item.file_size > criteria.max_size:
            return False
        
        # Extract metadata for advanced filtering
        metadata = self.enhanced_search.extract_metadata(item)
        
        # Year filtering
        year = metadata.get('year')
        if criteria.min_year and (not year or year < criteria.min_year):
            return False
        if criteria.max_year and (not year or year > criteria.max_year):
            return False
        
        # Quality filtering
        if criteria.qualities:
            quality = metadata.get('quality', '').lower()
            if not any(q.lower() in quality for q in criteria.qualities):
                return False
        
        # Format filtering
        if criteria.formats:
            extension = item.file_extension.lower().lstrip('.')
            if extension not in [f.lower() for f in criteria.formats]:
                return False
        
        # Name filtering
        if criteria.name_contains:
            if criteria.name_contains.lower() not in item.title.lower():
                return False
        
        if criteria.name_excludes:
            if criteria.name_excludes.lower() in item.title.lower():
                return False
        
        # Sync status filtering
        if criteria.exclude_synced:
            status_checker = SyncStatusChecker()
            status = status_checker.check_item_status(item)
            if status == SyncStatus.SYNCED:
                return False
        
        return True
    
    def create_interactive_filter(self, media_type: str) -> Optional[FilterCriteria]:
        """Create filter criteria through interactive prompts."""
        self.console.print("🔍 Advanced Filtering", style="bold cyan")
        self.console.print(f"Create filter criteria for {media_type}", style="dim")
        self.console.print()
        
        criteria = FilterCriteria()
        
        # Size filtering
        if self._ask_yes_no("Filter by file size?"):
            criteria.min_size, criteria.max_size = self._ask_size_range()
        
        # Year filtering  
        if self._ask_yes_no("Filter by year?"):
            criteria.min_year, criteria.max_year = self._ask_year_range()
        
        # Quality filtering
        if self._ask_yes_no("Filter by quality?"):
            criteria.qualities = self._ask_qualities()
        
        # Format filtering
        if self._ask_yes_no("Filter by file format?"):
            criteria.formats = self._ask_formats()
        
        # Name filtering
        if self._ask_yes_no("Filter by name?"):
            criteria.name_contains = self._ask_name_filter()
        
        # Sync status filtering
        criteria.exclude_synced = self._ask_yes_no("Exclude already synced items?", default=True)
        
        # Show summary
        self._show_filter_summary(criteria)
        
        if self._ask_yes_no("Apply this filter?", default=True):
            return criteria
        
        return None
    
    def _ask_yes_no(self, question: str, default: bool = False) -> bool:
        """Ask a yes/no question with clear default indication."""
        from rich.prompt import Confirm
        
        # Show default more clearly in prompt
        if default:
            display_prompt = f"{question} [Y/n]"
        else:
            display_prompt = f"{question} [y/N]"
        
        return Confirm.ask(display_prompt, default=default)
    
    def _ask_size_range(self) -> Tuple[Optional[int], Optional[int]]:
        """Ask for size range in GB."""
        self.console.print("📊 File Size Range", style="bold yellow")
        
        min_gb = input("Minimum size (GB, enter for no limit): ").strip()
        max_gb = input("Maximum size (GB, enter for no limit): ").strip()
        
        min_size = None
        max_size = None
        
        try:
            if min_gb:
                min_size = int(float(min_gb) * 1024 * 1024 * 1024)
        except ValueError:
            pass
        
        try:
            if max_gb:
                max_size = int(float(max_gb) * 1024 * 1024 * 1024)
        except ValueError:
            pass
        
        return min_size, max_size
    
    def _ask_year_range(self) -> Tuple[Optional[int], Optional[int]]:
        """Ask for year range."""
        self.console.print("📅 Year Range", style="bold yellow")
        
        min_year_str = input("Minimum year (enter for no limit): ").strip()
        max_year_str = input("Maximum year (enter for no limit): ").strip()
        
        min_year = None
        max_year = None
        
        try:
            if min_year_str:
                min_year = int(min_year_str)
        except ValueError:
            pass
        
        try:
            if max_year_str:
                max_year = int(max_year_str)
        except ValueError:
            pass
        
        return min_year, max_year
    
    def _ask_qualities(self) -> List[str]:
        """Ask for quality preferences."""
        self.console.print("🎥 Quality Filter", style="bold yellow")
        self.console.print("Common qualities: 4K, 1080p, 720p, 480p, BluRay, WEB-DL")
        
        qualities_str = input("Enter qualities (comma-separated): ").strip()
        if qualities_str:
            return [q.strip() for q in qualities_str.split(',')]
        return []
    
    def _ask_formats(self) -> List[str]:
        """Ask for format preferences."""
        self.console.print("📁 Format Filter", style="bold yellow")
        self.console.print("Common formats: mkv, mp4, avi, mov")
        
        formats_str = input("Enter formats (comma-separated): ").strip()
        if formats_str:
            return [f.strip() for f in formats_str.split(',')]
        return []
    
    def _ask_name_filter(self) -> Optional[str]:
        """Ask for name filter."""
        self.console.print("📝 Name Filter", style="bold yellow")
        name_filter = input("Title must contain (enter for no filter): ").strip()
        return name_filter if name_filter else None
    
    def _show_filter_summary(self, criteria: FilterCriteria):
        """Show summary of filter criteria."""
        self.console.print()
        self.console.print("📋 Filter Summary:", style="bold green")
        
        if criteria.min_size or criteria.max_size:
            min_str = f"{criteria.min_size / (1024**3):.1f}GB" if criteria.min_size else "no limit"
            max_str = f"{criteria.max_size / (1024**3):.1f}GB" if criteria.max_size else "no limit"
            self.console.print(f"  Size: {min_str} - {max_str}")
        
        if criteria.min_year or criteria.max_year:
            min_str = str(criteria.min_year) if criteria.min_year else "no limit"
            max_str = str(criteria.max_year) if criteria.max_year else "no limit"
            self.console.print(f"  Year: {min_str} - {max_str}")
        
        if criteria.qualities:
            self.console.print(f"  Quality: {', '.join(criteria.qualities)}")
        
        if criteria.formats:
            self.console.print(f"  Format: {', '.join(criteria.formats)}")
        
        if criteria.name_contains:
            self.console.print(f"  Name contains: '{criteria.name_contains}'")
        
        if criteria.exclude_synced:
            self.console.print("  Exclude: Already synced items")
        
        self.console.print()


class InteractiveSyncManager:
    """Main interactive sync manager for the immersive experience."""
    
    def __init__(self, library: MediaLibrary):
        self.library = library
        self.console = Console()
        self.state = SelectionState()
        self.browser = BrowserInterface(self.console)
        self.search = SearchInterface(self.console)
        self.preset_manager = PresetManager(self.console)
        
        # Phase 4: Advanced features
        self.recommendation_engine = SmartRecommendationEngine(self.console)
        self.enhanced_search = EnhancedSearchInterface(self.console)
        
        # Phase 3: Advanced filtering
        self.filtering_engine = AdvancedFilteringEngine(self.console)
        
    def start_interactive_flow(self) -> bool:
        """
        Start the main interactive flow.
        
        Returns:
            True if user made selections and wants to sync, False if cancelled
        """
        self.console.print()
        self.console.print("🎬 PlexSync Interactive Sync", style="bold green")
        self.console.print()
        
        # Main navigation loop - allows going back to media type selection
        while True:
            # Step 1: Show library status with downloaded media info
            self._show_library_status()
            
            # Step 2: Media Type Selection
            media_type = self._ask_media_type()
            if not media_type:
                return False
                
            self.state.media_type = media_type
            
            # Step 3: Browse/Select Media
            if media_type == MediaSelectionType.MOVIES:
                success = self._movie_selection_flow()
            elif media_type == MediaSelectionType.TV_SHOWS:
                success = self._tv_selection_flow()
            else:  # BOTH
                success = self._mixed_selection_flow()
            
            if success:
                # Step 4: Confirm Selection
                return self._confirm_selection()
            else:
                # User pressed 'back' from media selection - go back to media type selection
                # Clear the media type so we start fresh
                self.state.media_type = None
                continue
    
    def _show_library_status(self):
        """Display library status including downloaded media information."""
        try:
            # Import here to avoid circular imports
            from .downloaded import DownloadedMediaManager
            
            # Get downloaded media status
            downloaded_manager = DownloadedMediaManager(self.library.config if hasattr(self.library, 'config') else None)
            status_report = downloaded_manager.get_status_report(self.library)
            
            summary = status_report['summary']
            percentages = status_report['percentages']
            issues = status_report['issues']
            
            # Display library overview with downloaded status
            self.console.print("📊 Library Status:", style="bold blue")
            
            # Movies status
            movies_available = len(self.library.movies) if hasattr(self.library, 'movies') else 0
            if movies_available > 0:
                movies_downloaded = summary.movie_count
                movies_percentage = percentages['movies']
                movies_status = f"{movies_available} available • {movies_downloaded} downloaded ({movies_percentage:.1f}%)"
                self.console.print(f"  🎬 Movies: {movies_status}")
            
            # TV Shows status
            shows_available = len(self.library.tv_shows) if hasattr(self.library, 'tv_shows') else 0
            if shows_available > 0:
                episodes_downloaded = summary.episode_count
                episodes_status = f"{shows_available} shows • {episodes_downloaded} episodes downloaded"
                self.console.print(f"  📺 TV Shows: {episodes_status}")
            
            # Total downloaded status
            if summary.total_files > 0:
                total_status = f"{summary.total_size_gb:.1f} GB total"
                self.console.print(f"  💾 Downloaded: {total_status}")
                
                # Show issues if any
                if issues['partial_count'] > 0:
                    self.console.print(f"  ⚠️  Issues: {issues['partial_count']} partial downloads need attention", style="yellow")
                if issues['orphaned_count'] > 0:
                    self.console.print(f"  👻 Orphaned: {issues['orphaned_count']} files not in library", style="yellow")
            else:
                self.console.print("  💾 Downloaded: No files downloaded yet")
            
            self.console.print()
            
        except Exception as e:
            # Show debug info about what went wrong
            self.console.print(f"⚠️ Downloaded media status unavailable: {e}", style="dim yellow")
            
            # If there's an error with downloaded media scanning, just show basic library info
            self.console.print("📊 Library Status:", style="bold blue")
            
            movies_count = len(self.library.movies) if hasattr(self.library, 'movies') else 0
            shows_count = len(self.library.tv_shows) if hasattr(self.library, 'tv_shows') else 0
            
            if movies_count > 0:
                self.console.print(f"  🎬 Movies: {movies_count} available")
            if shows_count > 0:
                self.console.print(f"  📺 TV Shows: {shows_count} shows available")
            
            self.console.print()
    
    def _ask_media_type(self) -> Optional[MediaSelectionType]:
        """Ask user what type of media they want to sync."""
        
        while True:  # Main menu loop
            self.console.print("What would you like to do?", style="bold yellow")
            self.console.print()
            
            # Get basic library counts
            movies_count = len(self.library.movies) if hasattr(self.library, 'movies') else 0
            shows_count = len(self.library.tv_shows) if hasattr(self.library, 'tv_shows') else 0
            
            # Count not downloaded items
            try:
                from .downloaded import DownloadedMediaManager
                from .downloaded_browser import DownloadedMediaBrowserInterface
                
                downloaded_manager = DownloadedMediaManager(self.library.config if hasattr(self.library, 'config') else None)
                summary = downloaded_manager.get_summary(self.library)
                movies_not_downloaded = max(0, movies_count - summary.movie_count)
                
                options = [
                    ("1", "🎬 Browse & Sync Movies", f"({movies_not_downloaded} not downloaded)" if movies_not_downloaded > 0 else "(browse and sync more)"),
                    ("2", "📺 Browse & Sync TV Shows", f"(sync more episodes)" if shows_count > 0 else "(no shows available)"),
                    ("3", "🎭 Browse All Media", "(mixed selection)"),
                    ("4", "📱 Manage Downloaded Media", f"({summary.total_files} files • {summary.total_size_gb:.1f} GB)" if summary.total_files > 0 else "(no files downloaded)"),
                ]
                
                # Add additional options if there are issues
                if summary.partial or summary.corrupted:
                    issue_count = len(summary.partial) + len(summary.corrupted)
                    options.append(("5", "🔄 Re-sync Corrupted Files", f"({issue_count} need attention)"))
                else:
                    options.append(("5", "🔄 Re-sync Corrupted Files", "(all files healthy)"))
                
                # Always add Settings & Advanced Tools
                options.append(("6", "⚙️ Settings & Advanced Tools", "(configuration & diagnostics)"))
                
            except Exception as e:
                # Show debug info about what went wrong
                self.console.print(f"⚠️ Downloaded media features unavailable: {e}", style="dim yellow")
                
                # Fallback to basic options if downloaded media scanning fails
                options = [
                    ("1", "🎬 Browse & Sync Movies", f"({movies_count} available)" if movies_count > 0 else "(no movies available)"),
                    ("2", "📺 Browse & Sync TV Shows", f"({shows_count} shows available)" if shows_count > 0 else "(no shows available)"),
                    ("3", "🎭 Browse All Media", "(mixed selection)"),
                    ("4", "📱 Manage Downloaded Media", "(feature unavailable)"),
                    ("5", "🔄 Re-sync Corrupted Files", "(feature unavailable)"),
                    ("6", "⚙️ Settings & Advanced Tools", "(basic settings)")
                ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} {desc}")
            
            self.console.print()
            
            # Dynamic prompt based on available options
            max_option = len(options)
            prompt_text = f"Select [1-{max_option}]"
            
            # Choice selection loop
            while True:
                choice = Prompt.ask(prompt_text, default="1").strip()
                
                if choice == "1":
                    return MediaSelectionType.MOVIES
                elif choice == "2":
                    return MediaSelectionType.TV_SHOWS
                elif choice == "3":
                    return MediaSelectionType.BOTH
                elif choice == "4":
                    # Handle downloaded media management
                    try:
                        from .downloaded import DownloadedMediaManager
                        from .downloaded_browser import DownloadedMediaBrowserInterface
                        
                        downloaded_manager = DownloadedMediaManager(self.library.config if hasattr(self.library, 'config') else None)
                        browser = DownloadedMediaBrowserInterface(self.console, downloaded_manager)
                        
                        # Show downloaded media browser
                        browser.show_main_menu(self.library)
                        
                        # After returning from downloaded media browser, restart the main menu
                        break  # Break out of choice loop to restart main menu loop
                        
                    except ImportError as e:
                        self.console.print(f"❌ Downloaded media functionality not available: {e}", style="red")
                        self.console.print("💡 The downloaded media management features are not installed", style="yellow")
                        continue
                    except Exception as e:
                        self.console.print(f"❌ Error accessing downloaded media: {e}", style="red")
                        self.console.print("💡 Make sure your sync directory is accessible", style="yellow")
                        continue
                elif choice == "5" and max_option >= 5:
                    # Future: Handle re-sync partial files
                    self.console.print("🔄 Re-sync functionality will be available in Phase 3", style="yellow")
                    continue
                elif choice == "6" and max_option >= 6:
                    # Future: Handle settings and diagnostics
                    self.console.print("⚙️ Settings & Advanced Tools functionality will be available in Phase 3", style="yellow")
                    continue
                elif choice.lower() in ["q", "quit", "exit"]:
                    return None
                elif choice == "":
                    return MediaSelectionType.MOVIES  # Default to movies
                else:
                    self.console.print("❌ Invalid choice. Please select a valid option", style="red")
                    continue
            
            # If we reach here, we broke out of the choice loop and need to restart the main menu
            # Continue the main menu loop to rebuild options and show menu again
            continue
    
    def _movie_selection_flow(self) -> bool:
        """Handle movie selection flow with multi-selection support."""
        self.console.print("🎬 Movie Selection", style="bold green")
        self.console.print()
        
        # Phase 2: Enhanced navigation loop with multi-selection support
        while True:
            # Show current selection queue if any
            self._show_selection_queue()
            
            # Phase 3: Check for selection management commands
            if self.state.selected_movies:
                management_response = input("Enter selection management command (clear/view/save/load) or press Enter to browse: ").strip().lower()
                if management_response in ["clear", "view", "save", "load"]:
                    if self._handle_selection_management(management_response):
                        continue
            
            # Ask how they want to browse
            browse_style = self._ask_browse_style("movies")
            if not browse_style:
                # User chose to go back to media type selection
                return False
            
            movies = self.library.get_all_movies_sorted()
            
            if browse_style == BrowseStyle.SEARCH:
                search_results = self.search.search_movies(self.library)
                if not search_results:
                    # No search results, go back to browse style selection
                    continue
                movies = search_results
            
            # Browse movies with pagination
            page = 1
            total_pages = (len(movies) + self.browser.page_size - 1) // self.browser.page_size
            
            while True:
                # Phase 2: Pass current selections to browser for visual indicators
                selected_movies, command = self.browser.browse_movies(movies, page, self.state.selected_movies)
                
                if command == "next":
                    page = min(page + 1, total_pages)
                elif command == "previous":
                    page = max(1, page - 1)
                elif command == "jump":
                    page = self._handle_page_jump(len(movies), page)
                    continue
                elif command == "search":
                    search_results = self.search.search_movies(self.library)
                    if search_results:
                        movies = search_results
                        page = 1
                        total_pages = (len(movies) + self.browser.page_size - 1) // self.browser.page_size
                    continue
                elif command == "back":
                    # Phase 2: Go back to browse style selection instead of canceling
                    break  # Break out of movie browsing loop to browse style selection
                elif command == "quit":
                    return False
                elif command in ["selected", "batch_selected", "batch_all_selected"]:
                    # Phase 3: Enhanced selection handling for batch operations
                    added_count = 0
                    for movie in selected_movies:
                        if not any(existing.source_path == movie.source_path for existing in self.state.selected_movies):
                            self.state.selected_movies.append(movie)
                            added_count += 1
                            
                            # Phase 4: Track selection for smart recommendations
                            self.state.user_patterns.update_from_item(movie, self.enhanced_search)
                            action = SelectionAction(
                                action_type="add",
                                media_type="movie", 
                                item=movie,
                                description=f"Selected movie: {movie.title}"
                            )
                            self.state.add_selection_action(action)
                    
                    # Phase 3: Show batch selection confirmation
                    if command == "batch_all_selected":
                        self.console.print(f"✅ Added {added_count} movies from entire list to selection", style="green")
                    elif command == "batch_selected":
                        self.console.print(f"✅ Added {added_count} movies from batch to selection", style="green")
                    else:
                        self.console.print(f"✅ Added {added_count} movie(s) to selection", style="green")
                    
                    # Phase 2: Ask if user wants to continue selecting more movies
                    if self._ask_continue_selection():
                        # Continue selecting more movies
                        continue
                    else:
                        # User is done selecting, return to sync
                        return True
                elif command == "filter":
                    # Phase 3: Apply advanced filtering
                    filter_criteria = self.filtering_engine.create_interactive_filter("movies")
                    if filter_criteria:
                        filtered_movies = self.filtering_engine.filter_movies(movies, filter_criteria)
                        if filtered_movies:
                            movies = filtered_movies
                            page = 1
                            total_pages = (len(movies) + self.browser.page_size - 1) // self.browser.page_size
                            self.console.print(f"🔍 Applied filter: {len(movies)} movies match criteria", style="green")
                        else:
                            self.console.print("❌ No movies match the filter criteria", style="red")
                    continue
                elif command in ["help", "invalid"]:
                    continue
                
                # Phase 4: Enhanced keyboard shortcuts
                elif command == "home":
                    page = 1
                elif command == "end":
                    page = total_pages
                elif command == "random":
                    self._handle_random_selection(movies, "movie")
                    continue
                elif command == "recommend":
                    self._show_recommendations("movie")
                    continue
                elif command == "undo":
                    self._handle_undo()
                    continue
                elif command == "redo":
                    self._handle_redo()
                    continue
                elif command == "stats":
                    self._show_library_stats("movie")
                    continue
                elif command == "bookmark":
                    self._handle_bookmark_toggle(movies, page)
                    continue
                else:
                    continue
            
            # If we reach here, user pressed 'back' from movie browsing
            # Continue to browse style selection (outer loop)
            continue
        
        return False
    
    def _tv_selection_flow(self) -> bool:
        """Handle TV show selection flow with proper navigation."""
        self.console.print("📺 TV Show Selection", style="bold green")
        self.console.print()
        
        # Phase 2: Enhanced navigation loop with multi-selection support
        while True:
            # Show current selection queue if any
            self._show_selection_queue()
            
            # Phase 3: Check for selection management commands
            if self.state.selected_episodes:
                management_response = input("Enter selection management command (clear/view/save/load) or press Enter to browse: ").strip().lower()
                if management_response in ["clear", "view", "save", "load"]:
                    if self._handle_selection_management(management_response):
                        continue
            
            # Ask how they want to browse
            browse_style = self._ask_browse_style("tv")
            if not browse_style:
                # User chose to go back to media type selection
                return False
            
            shows = self.library.get_all_shows_sorted()
            
            if browse_style == BrowseStyle.SEARCH:
                search_results = self.search.search_shows(self.library)
                if not search_results:
                    # No search results, go back to browse style selection
                    continue
                shows = search_results
            
            # Browse shows with pagination
            page = 1
            while True:
                # Phase 2: Pass current selections to browser for visual indicators
                selected_show, command = self.browser.browse_shows(shows, page, self.library, self.state.selected_episodes)
                
                if command == "next":
                    page += 1
                elif command == "previous":
                    page = max(1, page - 1)
                elif command == "jump":
                    page = self._handle_page_jump(len(shows), page)
                    continue
                elif command == "search":
                    search_results = self.search.search_shows(self.library)
                    if search_results:
                        shows = search_results
                        page = 1
                    continue
                elif command == "back":
                    # Phase 2: Go back to browse style selection instead of canceling
                    break  # Break out of show browsing loop to browse style selection
                elif command == "quit":
                    return False
                elif command == "selected":
                    self.state.selected_show = selected_show
                    # Phase 2: Multi-selection flow - collect episodes and continue
                    show_result = self._season_selection_flow(selected_show)
                    if show_result:
                        # Episodes were selected, show confirmation and ask what to do next
                        if self._ask_continue_selection():
                            # Continue selecting more shows/episodes
                            continue
                        else:
                            # User is done selecting, return to sync
                            return True
                    else:
                        # User cancelled season selection, continue browsing shows
                        continue
                elif command in ["batch_selected", "batch_all_selected"]:
                    # Phase 3: Handle batch TV show selection
                    if isinstance(selected_show, list):
                        shows_to_process = selected_show
                    else:
                        shows_to_process = [selected_show]
                    
                    # For batch selection, process all shows at once
                    total_episodes_added = 0
                    for show in shows_to_process:
                        self.state.selected_show = show
                        show_result = self._batch_season_selection_flow(show)
                        if show_result:
                            total_episodes_added += show_result
                    
                    if total_episodes_added > 0:
                        if command == "batch_all_selected":
                            self.console.print(f"✅ Added {total_episodes_added} episodes from all shows to selection", style="green")
                        else:
                            self.console.print(f"✅ Added {total_episodes_added} episodes from batch selection to selection", style="green")
                        
                        # Ask if user wants to continue selecting more
                        if self._ask_continue_selection():
                            continue
                        else:
                            return True
                    else:
                        self.console.print("❌ No episodes were selected from batch", style="red")
                        continue
                elif command == "filter":
                    # Phase 3: Apply advanced filtering to TV shows
                    filter_criteria = self.filtering_engine.create_interactive_filter("TV shows")
                    if filter_criteria:
                        filtered_shows = self.filtering_engine.filter_shows(shows, self.library, filter_criteria)
                        if filtered_shows:
                            shows = filtered_shows
                            page = 1
                            self.console.print(f"🔍 Applied filter: {len(shows)} shows match criteria", style="green")
                        else:
                            self.console.print("❌ No shows match the filter criteria", style="red")
                    continue
                elif command in ["help", "invalid"]:
                    continue
                else:
                    continue
            
            # If we reach here, user pressed 'back' from show browsing
            # Continue to browse style selection (outer loop)
            continue
        
        return False
    
    def _season_selection_flow(self, show_name: str) -> bool:
        """Handle season selection for a TV show."""
        while True:
            selected_seasons, command = self.browser.browse_seasons(show_name, self.library)
            
            if command == "back":
                return False  # Go back to show selection
            elif command == "quit":
                return False
            elif command in ["selected", "all_selected"]:
                self.state.selected_seasons = selected_seasons
                
                # If multiple seasons selected, need to handle each
                if len(selected_seasons) == 1:
                    return self._episode_selection_flow(show_name, selected_seasons[0])
                else:
                    # Handle multiple seasons
                    return self._multi_season_episode_selection_flow(show_name, selected_seasons)
            elif command in ["help", "invalid"]:
                continue
            else:
                continue
    
    def _batch_season_selection_flow(self, show_name: str) -> int:
        """
        Handle batch season selection for TV shows.
        
        Returns:
            Number of episodes added to selection
        """
        # Get all episodes for the show
        all_episodes = self.library.get_show_episodes(show_name)
        
        if not all_episodes:
            self.console.print(f"❌ No episodes found for {show_name}", style="red")
            return 0
        
        # For batch processing, automatically select all episodes
        episodes_added = 0
        for episode in all_episodes:
            if not any(existing.source_path == episode.source_path for existing in self.state.selected_episodes):
                self.state.selected_episodes.append(episode)
                episodes_added += 1
                
                # Phase 4: Track selection for smart recommendations
                self.state.user_patterns.update_from_item(episode, self.enhanced_search)
                action = SelectionAction(
                    action_type="add",
                    media_type="tv_episode",
                    item=episode,
                    description=f"Selected episode: {episode.title}"
                )
                self.state.add_selection_action(action)
        
        return episodes_added
    
    def _episode_selection_flow(self, show_name: str, season: int) -> bool:
        """Handle episode selection for a specific season."""
        while True:
            selected_episodes, command = self.browser.browse_episodes(show_name, season, self.library)
            
            if command == "back":
                return False  # Go back to season selection
            elif command == "quit":
                return False
            elif command in ["all_selected", "new_selected", "custom_selected"]:
                if selected_episodes:
                    self.state.selected_episodes.extend(selected_episodes)
                    self.console.print(f"✅ Selected {len(selected_episodes)} episodes from {show_name} Season {season}", style="green")
                    return True
                else:
                    self.console.print("❌ No episodes selected", style="yellow")
                    continue
            elif command == "all_synced":
                self.console.print("✅ All episodes already synced", style="green")
                return True
            elif command in ["help", "invalid"]:
                continue
            else:
                continue
    
    def _multi_season_episode_selection_flow(self, show_name: str, seasons: List[int]) -> bool:
        """Handle episode selection across multiple seasons."""
        self.console.print(f"📺 Multi-Season Selection: {show_name}", style="bold green")
        self.console.print(f"Selected seasons: {', '.join(map(str, seasons))}", style="dim")
        self.console.print()
        
        total_selected = 0
        
        for season in seasons:
            self.console.print(f"🎯 Selecting episodes for Season {season}...", style="bold blue")
            
            # Get episodes for this season
            all_episodes = self.library.get_show_episodes(show_name)
            season_episodes = [ep for ep in all_episodes if ep.season == season]
            
            if not season_episodes:
                self.console.print(f"⚠️ No episodes found for Season {season}", style="yellow")
                continue
            
            # Check if any episodes need syncing
            status_checker = SyncStatusChecker()
            new_episodes = []
            for episode in season_episodes:
                status = status_checker.check_item_status(episode)
                if status != SyncStatus.SYNCED:
                    new_episodes.append(episode)
            
            if not new_episodes:
                self.console.print(f"✅ Season {season}: All episodes already synced", style="green")
                continue
            
            # Ask user what to do with this season
            from rich.prompt import Confirm
            self.console.print(f"Season {season}: {len(new_episodes)} new episodes available", style="yellow")
            
            if Confirm.ask(f"Add all {len(new_episodes)} new episodes from Season {season}? [Y/n]", default=True):
                self.state.selected_episodes.extend(new_episodes)
                total_selected += len(new_episodes)
                self.console.print(f"✅ Added {len(new_episodes)} episodes from Season {season}", style="green")
            else:
                # Use individual episode selection for this season
                episode_result = self._episode_selection_flow(show_name, season)
                if not episode_result:
                    continue
            
            self.console.print()
        
        if total_selected > 0:
            self.console.print(f"✅ Total selected: {total_selected} episodes from {len(seasons)} seasons", style="bold green")
            return True
        else:
            self.console.print("❌ No episodes selected", style="yellow")
            return False
    
    def _mixed_selection_flow(self) -> bool:
        """Handle mixed media selection flow."""
        self.console.print("🎭 Mixed Media Selection", style="bold green")
        self.console.print("Select movies and TV shows in the same session", style="dim")
        self.console.print()
        
        # Main loop for mixed selection
        while True:
            # Show current selection queue
            self._show_selection_queue()
            
            # Ask what type of media to browse next
            self.console.print("What would you like to browse next?", style="bold yellow")
            self.console.print()
            
            options = [
                ("1", "🎬 Browse Movies", f"({len(self.library.movies)} available)"),
                ("2", "📺 Browse TV Shows", f"({len(self.library.tv_shows)} shows available)"),
                ("3", "✅ Done Selecting", "Proceed to sync"),
                ("4", "🔄 Clear All", "Start over")
            ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} {desc}")
            
            self.console.print()
            
            choice = Prompt.ask("Select [1-4]", default="").strip()
            
            if choice == "1":
                # Browse movies
                movie_success = self._movie_selection_flow()
                if not movie_success:
                    # User pressed back, continue mixed selection
                    continue
                # Movies were selected, ask if they want to continue
                if not self._ask_continue_selection():
                    return True  # Done selecting, proceed to sync
                    
            elif choice == "2":
                # Browse TV shows
                tv_success = self._tv_selection_flow()
                if not tv_success:
                    # User pressed back, continue mixed selection
                    continue
                # TV shows were selected, ask if they want to continue
                if not self._ask_continue_selection():
                    return True  # Done selecting, proceed to sync
                    
            elif choice == "3":
                # Check if user has made any selections
                if self.state.total_items() == 0:
                    self.console.print("❌ No items selected. Please select some media first.", style="red")
                    continue
                return True  # Done selecting, proceed to sync
                
            elif choice == "4":
                # Clear all selections
                if self._clear_all_selections():
                    continue  # Start over
                else:
                    continue  # User cancelled clear, continue selecting
                    
            elif choice.lower() in ["q", "quit", "exit", "b", "back"]:
                return False  # Go back to media type selection
                
            elif choice == "":
                # Default to done if they have selections
                if self.state.total_items() > 0:
                    return True
                else:
                    self.console.print("❌ No items selected. Please select some media first.", style="red")
                    continue
                    
            else:
                self.console.print("❌ Invalid choice. Please select 1-4", style="red")
                continue
    
    def _handle_page_jump(self, total_items: int, current_page: int) -> int:
        """Handle page jumping functionality."""
        page_size = self.browser.page_size
        total_pages = (total_items + page_size - 1) // page_size
        
        if total_pages <= 1:
            self.console.print("Only one page available", style="yellow")
            return current_page
        
        self.console.print(f"📄 Page Jump (Current: {current_page}, Total: {total_pages})", style="bold cyan")
        
        while True:
            try:
                target_page = IntPrompt.ask(
                    f"Jump to page [1-{total_pages}]",
                    default=current_page
                )
                
                if 1 <= target_page <= total_pages:
                    if target_page == current_page:
                        self.console.print("Already on that page", style="dim")
                    else:
                        self.console.print(f"Jumping to page {target_page}", style="green")
                    return target_page
                else:
                    self.console.print(f"❌ Invalid page. Please enter 1-{total_pages}", style="red")
                    
            except KeyboardInterrupt:
                self.console.print("\nPage jump cancelled", style="yellow")
                return current_page
            except Exception:
                self.console.print("❌ Invalid input. Please enter a number", style="red")
    
    def _ask_browse_style(self, media_type: str) -> Optional[BrowseStyle]:
        """Ask user how they want to browse media."""
        type_emoji = "🎬" if media_type == "movies" else "📺"
        type_name = media_type.title()
        
        self.console.print(f"How would you like to browse {type_name.lower()}?", style="bold yellow")
        self.console.print()
        
        options = [
            ("1", "🔍 Search by title", "Find specific titles"),
            ("2", "📋 Browse all", "Paginated list of all media"),
            ("3", "🎲 Random selections", "Show random picks"),
            ("4", "📊 Browse by size", "Largest files first"),
            ("5", "🆕 Recently added", "Newest additions"),
            ("6", "💾 Load preset", "Use saved selection criteria")
        ]
        
        for num, icon_name, desc in options:
            self.console.print(f"  {num}. {icon_name} - {desc}")
        
        self.console.print()
        
        while True:
            choice = Prompt.ask("Select \\[1-6]", default="2").strip()
            
            if choice == "1":
                return BrowseStyle.SEARCH
            elif choice == "2" or choice == "":
                return BrowseStyle.BROWSE_ALL
            elif choice == "3":
                return BrowseStyle.RANDOM
            elif choice == "4":
                return BrowseStyle.BY_SIZE
            elif choice == "5":
                return BrowseStyle.RECENT
            elif choice == "6":
                # Load preset and apply it
                criteria = self.preset_manager.load_preset_interactive(media_type)
                if criteria:
                    return self._apply_preset_criteria(criteria, media_type)
                else:
                    continue  # Go back to browse style selection
            elif choice.lower() in ["q", "quit", "exit", "b", "back"]:
                return None
            else:
                self.console.print("❌ Invalid choice. Please select 1-6", style="red")
                continue
    
    def _apply_preset_criteria(self, criteria: Dict[str, Any], media_type: str) -> Optional[BrowseStyle]:
        """Apply preset criteria and filter media accordingly."""
        self.console.print("🎯 Applying preset criteria...", style="green")
        
        if media_type == "movies":
            # Apply criteria to movies
            movies = self.library.get_all_movies_sorted()
            if criteria:
                enhanced_search = EnhancedSearchInterface(self.console)
                filtered_movies = enhanced_search.filter_movies_by_criteria(movies, criteria)
                self.console.print(f"Preset filtered to {len(filtered_movies)} movies", style="blue")
                
                # Store filtered results temporarily (we could enhance this further)
                # For now, just return BROWSE_ALL and let the normal flow handle it
                # This is a simplified implementation - could be enhanced to store the filtered results
                
        return BrowseStyle.BROWSE_ALL
    
    def _handle_random_selection(self, items: List[MediaItem], media_type: str):
        """Handle random selection from current items."""
        import random
        
        if not items:
            self.console.print("❌ No items available for random selection", style="red")
            return
        
        # Select 1-3 random items
        num_to_select = min(random.randint(1, 3), len(items))
        random_items = random.sample(items, num_to_select)
        
        self.console.print(f"🎲 Random Selection ({num_to_select} items)", style="bold magenta")
        
        # Show random selections
        table = Table()
        table.add_column("Title", style="bold")
        table.add_column("Year", width=6, style="cyan")
        table.add_column("Size", width=8, style="green")
        
        for item in random_items:
            metadata = self.enhanced_search.extract_metadata(item)
            year = str(metadata.get('year', '?'))
            size = self.state.format_size(item.file_size)
            table.add_row(item.title, year, size)
        
        self.console.print(table)
        self.console.print()
        
        from rich.prompt import Confirm
        if Confirm.ask("Add these random selections? [Y/n]", default=True):
            for item in random_items:
                if media_type == "movie":
                    self.state.selected_movies.append(item)
                self.state.user_patterns.update_from_item(item, self.enhanced_search)
                
                action = SelectionAction(
                    action_type="add",
                    media_type=media_type,
                    item=item,
                    description=f"Random selection: {item.title}"
                )
                self.state.add_selection_action(action)
            
            self.console.print(f"✅ Added {len(random_items)} random selections", style="green")
    
    def _show_recommendations(self, media_type: str):
        """Show smart recommendations based on user patterns."""
        if media_type == "movie":
            self.recommendation_engine.display_recommendations(self.library, self.state.user_patterns)
        
        self.console.print("\n💡 Tip: Select items to improve recommendations", style="dim")
        self.console.print("Press any key to continue...", style="dim")
        try:
            input()
        except KeyboardInterrupt:
            pass
    
    def _handle_undo(self):
        """Handle undo operation."""
        if not self.state.can_undo():
            self.console.print("❌ Nothing to undo", style="yellow")
            return
        
        action = self.state.undo_last_action()
        if action:
            self.console.print(f"↶ Undone: {action.description}", style="yellow")
    
    def _handle_redo(self):
        """Handle redo operation."""
        if not self.state.can_redo():
            self.console.print("❌ Nothing to redo", style="yellow")
            return
        
        action = self.state.redo_last_action()
        if action:
            self.console.print(f"↷ Redone: {action.description}", style="green")
    
    def _show_library_stats(self, media_type: str):
        """Show detailed library statistics."""
        self.console.print("📊 Library Statistics", style="bold blue")
        self.console.print("=" * 30, style="dim")
        
        if media_type == "movie":
            movies = self.library.movies
            
            # Basic stats
            total_size = sum(m.file_size for m in movies)
            self.console.print(f"Total Movies: {len(movies)}")
            self.console.print(f"Total Size: {self.state.format_size(total_size)}")
            
            # Year distribution
            years = {}
            qualities = {}
            
            for movie in movies:
                metadata = self.enhanced_search.extract_metadata(movie)
                year = metadata.get('year')
                quality = metadata.get('quality')
                
                if year:
                    years[year] = years.get(year, 0) + 1
                if quality:
                    qualities[quality] = qualities.get(quality, 0) + 1
            
            # Show top years
            if years:
                top_years = sorted(years.items(), key=lambda x: x[1], reverse=True)[:5]
                self.console.print(f"\nTop Years: {', '.join(f'{year} ({count})' for year, count in top_years)}")
            
            # Show quality distribution
            if qualities:
                quality_list = sorted(qualities.items(), key=lambda x: x[1], reverse=True)
                self.console.print(f"Qualities: {', '.join(f'{qual} ({count})' for qual, count in quality_list)}")
            
            # User selection stats
            if self.state.user_patterns.session_selections:
                self.console.print(f"\nYour Selections This Session: {len(self.state.user_patterns.session_selections)}")
                preferred_quality = self.state.user_patterns.get_top_quality()
                if preferred_quality:
                    self.console.print(f"Your Preferred Quality: {preferred_quality.upper()}")
        
        self.console.print("\nPress any key to continue...", style="dim")
        try:
            input()
        except KeyboardInterrupt:
            pass
    
    def _handle_bookmark_toggle(self, items: List[MediaItem], page: int):
        """Handle bookmark/favorite functionality."""
        # This is a placeholder for bookmarking functionality
        # Could be expanded to save favorite searches, etc.
        self.console.print("💾 Bookmark functionality coming soon!", style="yellow")
        self.console.print("This will save current search/filter state", style="dim")
    
    def _confirm_selection(self) -> bool:
        """Confirm the user's selection before syncing."""
        self.console.print()
        self.console.print("📋 Selection Summary", style="bold blue")
        self.console.print()
        
        total_items = self.state.total_items()
        total_size = self.state.total_size()
        
        if total_items == 0:
            self.console.print("❌ No items selected", style="red")
            return False
        
        # Show summary
        summary_table = Table()
        summary_table.add_column("Type", style="bold")
        summary_table.add_column("Count", style="green")
        summary_table.add_column("Size", style="blue")
        
        if self.state.selected_movies:
            movies_size = sum(m.file_size for m in self.state.selected_movies)
            summary_table.add_row(
                "Movies",
                str(len(self.state.selected_movies)),
                self.state.format_size(movies_size)
            )
        
        if self.state.selected_episodes:
            episodes_size = sum(e.file_size for e in self.state.selected_episodes)
            summary_table.add_row(
                "Episodes",
                str(len(self.state.selected_episodes)),
                self.state.format_size(episodes_size)
            )
        
        if self.state.selected_show and not self.state.selected_episodes:
            summary_table.add_row(
                "TV Show",
                self.state.selected_show,
                "Episodes TBD"
            )
        
        self.console.print(summary_table)
        self.console.print()
        
        self.console.print(f"📊 Total: {total_items} items • {self.state.format_size(total_size)}", style="bold")
        self.console.print()
        
        # Confirm sync with clear default indication
        return Confirm.ask("🚀 Start sync with these selections? [Y/n]", default=True)
    
    def get_selections(self) -> SelectionState:
        """Get the current selection state."""
        return self.state
    
    def _show_selection_queue(self):
        """Show current selection queue if any items are selected."""
        if not self.state.selected_movies and not self.state.selected_episodes:
            return
        
        self.console.print("📋 Current Selection Queue:", style="bold cyan")
        
        if self.state.selected_movies:
            self.console.print(f"  🎬 Movies: {len(self.state.selected_movies)} selected", style="green")
            
        if self.state.selected_episodes:
            self.console.print(f"  📺 Episodes: {len(self.state.selected_episodes)} selected", style="green")
        
        total_size = self.state.total_size()
        self.console.print(f"  📊 Total: {self.state.total_items()} items • {self.state.format_size(total_size)}", style="bold")
        
        # Phase 3: Show selection management options
        self.console.print("⚙️  Selection Management: \\[clear] all, \\[view] details, \\[save] preset", style="dim")
        self.console.print()
    
    def _handle_selection_management(self, command: str) -> bool:
        """
        Handle selection management commands.
        
        Returns:
            True if command was handled, False otherwise
        """
        if command == "clear":
            return self._clear_all_selections()
        elif command == "view":
            return self._view_selection_details()
        elif command == "save":
            return self._save_selection_preset()
        elif command == "load":
            return self._load_selection_preset()
        
        return False
    
    def _clear_all_selections(self) -> bool:
        """Clear all current selections."""
        if not self.state.selected_movies and not self.state.selected_episodes:
            self.console.print("❌ No selections to clear", style="red")
            return True
        
        from rich.prompt import Confirm
        if Confirm.ask(f"🗑️  Clear all {self.state.total_items()} selected items? [y/N]", default=False):
            self.state.selected_movies.clear()
            self.state.selected_episodes.clear()
            self.console.print("✅ All selections cleared", style="green")
        
        return True
    
    def _view_selection_details(self) -> bool:
        """Show detailed view of current selections."""
        if not self.state.selected_movies and not self.state.selected_episodes:
            self.console.print("❌ No selections to view", style="red")
            return True
        
        self.console.print("📋 Selection Details:", style="bold cyan")
        
        if self.state.selected_movies:
            self.console.print(f"\n🎬 Movies ({len(self.state.selected_movies)}):", style="bold green")
            for i, movie in enumerate(self.state.selected_movies, 1):
                size_str = self.state.format_size(movie.file_size)
                self.console.print(f"  {i}. {movie.title} ({size_str})")
        
        if self.state.selected_episodes:
            self.console.print(f"\n📺 Episodes ({len(self.state.selected_episodes)}):", style="bold green")
            for i, episode in enumerate(self.state.selected_episodes, 1):
                size_str = self.state.format_size(episode.file_size)
                self.console.print(f"  {i}. {episode.show_name} - S{episode.season:02d}E{episode.episode:02d} ({size_str})")
        
        self.console.print()
        input("Press Enter to continue...")
        return True
    
    def _save_selection_preset(self) -> bool:
        """Save current selection as a preset."""
        if not self.state.selected_movies and not self.state.selected_episodes:
            self.console.print("❌ No selections to save", style="red")
            return True
        
        from rich.prompt import Prompt
        preset_name = Prompt.ask("Enter preset name").strip()
        
        if preset_name:
            # Phase 3: Save preset through preset manager
            success = self.preset_manager.save_selection_preset(preset_name, self.state)
            if success:
                self.console.print(f"✅ Saved preset: {preset_name}", style="green")
            else:
                self.console.print("❌ Failed to save preset", style="red")
        
        return True
    
    def _load_selection_preset(self) -> bool:
        """Load a saved selection preset."""
        # Phase 3: Load preset through preset manager
        loaded_state = self.preset_manager.load_selection_preset()
        if loaded_state:
            self.state.selected_movies = loaded_state.selected_movies
            self.state.selected_episodes = loaded_state.selected_episodes
            self.console.print("✅ Loaded preset successfully", style="green")
        else:
            self.console.print("❌ No preset loaded", style="red")
        
        return True
        
    def _ask_continue_selection(self) -> bool:
        """Ask user if they want to continue selecting more media."""
        self.console.print()
        self.console.print(f"✅ Selection Summary:", style="bold green")
        self.console.print(f"  Movies: {len(self.state.selected_movies)}")
        self.console.print(f"  Episodes: {len(self.state.selected_episodes)}")
        self.console.print(f"  Total: {self.state.total_items()} items • {self.state.format_size(self.state.total_size())}")
        self.console.print()
        
        from rich.prompt import Confirm
        
        choices = [
            "Continue selecting more media",
            "Proceed to sync with current selection",
            "Cancel and start over"
        ]
        
        self.console.print("What would you like to do next?", style="bold yellow")
        for i, choice in enumerate(choices, 1):
            self.console.print(f"  {i}. {choice}")
        self.console.print()
        
        while True:
            response = input("Select [1-3] (2): ").strip()
            
            if response == "1":
                return True  # Continue selecting
            elif response == "2" or response == "":
                return False  # Proceed to sync
            elif response == "3":
                # Clear selections and start over
                self.state.selected_movies.clear()
                self.state.selected_episodes.clear()
                self.console.print("🔄 Selection cleared", style="yellow")
                return True  # Continue (restart)
            else:
                self.console.print("❌ Invalid choice. Please select 1, 2, or 3", style="red") 