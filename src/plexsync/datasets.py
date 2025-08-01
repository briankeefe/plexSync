"""
Media discovery and selection definitions for PlexSync.

This module defines the media discovery system for interactive selection
of individual movies and TV episodes from mounted network drives.
"""

from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from enum import Enum
import os
import json
import time
import hashlib
import pickle
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class MediaType(Enum):
    """Media types for discovery and selection."""
    MOVIE = "movie"
    TV_SHOW = "tv_show"
    TV_EPISODE = "tv_episode"


@dataclass
class MediaItem:
    """Individual media item (movie or TV episode)."""
    title: str
    media_type: MediaType
    source_path: str
    relative_path: str
    file_size: int
    file_extension: str
    # TV-specific fields
    show_name: Optional[str] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    episode_title: Optional[str] = None


@dataclass
class MediaSource:
    """Configuration for a media source directory."""
    name: str
    base_path: str
    media_type: MediaType
    enabled: bool = True
    scan_depth: int = 5  # How deep to scan for media files


@dataclass
class ScanCache:
    """Cache for scan results to avoid re-scanning unchanged directories."""
    path: str
    last_modified: float
    last_scan: float
    file_count: int
    total_size: int
    items: List[MediaItem]
    
    def is_valid(self) -> bool:
        """Check if cache is still valid using fast directory checks."""
        try:
            # Check if the base directory still exists
            if not os.path.exists(self.path):
                return False
            
            # Fast check: just compare the top-level directory modification time
            # This catches most cases (new files/folders added) without expensive traversal
            current_mtime = os.path.getmtime(self.path)
            
            # If the base directory hasn't changed, assume cache is valid
            # This is a reasonable trade-off between speed and perfect accuracy
            return current_mtime <= self.last_modified
            
        except (OSError, FileNotFoundError):
            return False


@dataclass
class MediaLibrary:
    """Complete media library with movies and TV shows."""
    movies: List[MediaItem]
    tv_shows: Dict[str, List[MediaItem]]  # show_name -> episodes
    last_scan: Optional[float] = None
    total_items: int = 0
    
    def get_all_movies_sorted(self) -> List[MediaItem]:
        """Get all movies sorted alphabetically."""
        return sorted(self.movies, key=lambda m: m.title.lower())
    
    def get_all_shows_sorted(self) -> List[str]:
        """Get all TV show names sorted alphabetically."""
        return sorted(self.tv_shows.keys(), key=str.lower)
    
    def get_show_episodes(self, show_name: str) -> List[MediaItem]:
        """Get episodes for a specific show, sorted by season/episode."""
        episodes = self.tv_shows.get(show_name, [])
        return sorted(episodes, key=lambda e: (e.season or 0, e.episode or 0))
    
    def search_movies(self, query: str) -> List[MediaItem]:
        """Search movies by title (case-insensitive)."""
        query_lower = query.lower()
        return [m for m in self.movies if query_lower in m.title.lower()]
    
    def search_shows(self, query: str) -> List[str]:
        """Search TV shows by name (case-insensitive)."""
        query_lower = query.lower()
        return [show for show in self.tv_shows.keys() if query_lower in show.lower()]


class MediaDiscovery:
    """Optimized media discovery and cataloging system with persistent caching."""
    
    # Common video file extensions
    VIDEO_EXTENSIONS = {
        '.mkv', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', 
        '.m4v', '.mpg', '.mpeg', '.3gp', '.ogv'
    }
    
    # Patterns to ignore
    IGNORE_PATTERNS = {
        'sample', 'trailer', 'extras', 'behind-the-scenes', 
        'deleted-scenes', 'featurettes', '.DS_Store', 'Thumbs.db'
    }
    
    def __init__(self, sources: List[MediaSource], max_workers: int = 4, cache_dir: str = None):
        self.sources = sources
        self.library = MediaLibrary(movies=[], tv_shows={})
        self.max_workers = max_workers
        self.progress_callback = None
        self.lock = threading.Lock()
        
        # Set up cache directory
        if cache_dir:
            self.cache_dir = Path(cache_dir)
        else:
            # Use user's cache directory
            if os.name == 'nt':  # Windows
                cache_base = os.environ.get('APPDATA', os.path.expanduser('~'))
            else:  # Unix/Linux/macOS
                cache_base = os.environ.get('XDG_CACHE_HOME', os.path.expanduser('~/.cache'))
            self.cache_dir = Path(cache_base) / 'plexsync'
        
        # Create cache directory if it doesn't exist
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / 'discovery_cache.pkl'
        
        # Load existing cache
        self.cache = self._load_cache()
        
        # Pre-compiled regex patterns for better performance
        import re
        self.season_episode_patterns = [
            re.compile(r'[Ss](\d+)[Ee](\d+)'),  # S01E01
            re.compile(r'(\d+)x(\d+)'),         # 1x01
            re.compile(r'Season\s*(\d+).*Episode\s*(\d+)', re.IGNORECASE),  # Season 1 Episode 1
        ]
        
        self.quality_patterns = [
            re.compile(r'\b(1080p|720p|480p|4K|UHD|HDR|BluRay|DVD|WEB-DL|WEBRip)\b', re.IGNORECASE),
            re.compile(r'\b(x264|x265|H\.264|H\.265|HEVC)\b', re.IGNORECASE),
            re.compile(r'\b(AAC|AC3|DTS|MP3)\b', re.IGNORECASE),
        ]
    
    def _load_cache(self) -> Dict:
        """Load cache from disk."""
        try:
            if self.cache_file.exists():
                with open(self.cache_file, 'rb') as f:
                    cache = pickle.load(f)
                    print(f"📦 Loaded cache with {len(cache)} entries")
                    return cache
        except (pickle.PickleError, EOFError, OSError) as e:
            print(f"⚠️  Cache file corrupted, starting fresh: {e}")
        
        return {}
    
    def _save_cache(self):
        """Save cache to disk."""
        try:
            with open(self.cache_file, 'wb') as f:
                pickle.dump(self.cache, f)
        except (pickle.PickleError, OSError) as e:
            print(f"⚠️  Failed to save cache: {e}")
    
    def set_progress_callback(self, callback):
        """Set a progress callback function."""
        self.progress_callback = callback
    
    def scan_all_sources(self, force_rescan: bool = False) -> MediaLibrary:
        """Scan all configured sources in parallel and build media library."""
        print("🔍 Starting parallel media discovery...")
        
        all_movies = []
        all_tv_shows = {}
        cache_hits = 0
        cache_misses = 0
        
        # Prepare enabled sources
        enabled_sources = [s for s in self.sources if s.enabled]
        
        if not enabled_sources:
            print("⚠️  No enabled sources found")
            return MediaLibrary(movies=[], tv_shows={})
        
        # Scan sources in parallel
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all scan tasks
            future_to_source = {}
            for source in enabled_sources:
                if source.media_type == MediaType.MOVIE:
                    future = executor.submit(self._scan_movie_source_optimized, source, force_rescan)
                elif source.media_type == MediaType.TV_SHOW:
                    future = executor.submit(self._scan_tv_source_optimized, source, force_rescan)
                else:
                    continue
                future_to_source[future] = source
            
            # Collect results as they complete
            for future in as_completed(future_to_source):
                source = future_to_source[future]
                try:
                    result, was_cached = future.result()
                    
                    if was_cached:
                        cache_hits += 1
                    else:
                        cache_misses += 1
                    
                    if source.media_type == MediaType.MOVIE:
                        movies = result
                        all_movies.extend(movies)
                        cache_status = "💾 cached" if was_cached else "🔍 scanned"
                        print(f"✅ {source.name}: Found {len(movies)} movies ({cache_status})")
                    
                    elif source.media_type == MediaType.TV_SHOW:
                        tv_shows = result
                        # Merge TV shows from different sources
                        for show_name, episodes in tv_shows.items():
                            if show_name in all_tv_shows:
                                all_tv_shows[show_name].extend(episodes)
                            else:
                                all_tv_shows[show_name] = episodes
                        episode_count = sum(len(eps) for eps in tv_shows.values())
                        cache_status = "💾 cached" if was_cached else "🔍 scanned"
                        print(f"✅ {source.name}: Found {len(tv_shows)} shows, {episode_count} episodes ({cache_status})")
                        
                except Exception as e:
                    print(f"❌ {source.name}: Error - {e}")
                    cache_misses += 1
        
        # Save cache after all scanning is complete
        self._save_cache()
        
        # Remove duplicates and sort
        all_movies = self._deduplicate_movies(all_movies)
        all_tv_shows = self._deduplicate_tv_shows(all_tv_shows)
        
        self.library = MediaLibrary(
            movies=all_movies,
            tv_shows=all_tv_shows,
            last_scan=time.time(),
            total_items=len(all_movies) + sum(len(eps) for eps in all_tv_shows.values())
        )
        
        # Show cache statistics
        total_sources = cache_hits + cache_misses
        if total_sources > 0:
            cache_hit_rate = (cache_hits / total_sources) * 100
            print(f"📊 Cache performance: {cache_hits}/{total_sources} hits ({cache_hit_rate:.1f}%)")
        
        print(f"🎉 Discovery complete: {len(all_movies)} movies, {len(all_tv_shows)} TV shows")
        return self.library
    
    def _scan_movie_source_optimized(self, source: MediaSource, force_rescan: bool = False) -> Tuple[List[MediaItem], bool]:
        """Optimized movie source scanning with persistent caching."""
        print(f"📁 Scanning {source.name} ({source.base_path})")
        
        if not os.path.exists(source.base_path):
            print(f"    ⚠️  Path not found: {source.base_path}")
            return [], False
        
        # Check cache first
        cache_key = f"{source.base_path}:movies"
        if not force_rescan and cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if cache_entry.is_valid():
                print(f"    💾 Using cached results ({len(cache_entry.items)} items)")
                return cache_entry.items, True
        
        movies = []
        
        try:
            # Use os.scandir for better performance than os.walk
            for entry in self._scan_directory_optimized(source.base_path, source.scan_depth):
                if entry.is_file() and self._is_video_file(entry.name) and not self._should_ignore(entry.name):
                    try:
                        stat_info = entry.stat()
                        relative_path = os.path.relpath(entry.path, source.base_path)
                        
                        # Extract movie title from filename/folder structure
                        title = self._extract_movie_title(relative_path)
                        
                        movie = MediaItem(
                            title=title,
                            media_type=MediaType.MOVIE,
                            source_path=entry.path,
                            relative_path=relative_path,
                            file_size=stat_info.st_size,
                            file_extension=os.path.splitext(entry.name)[1].lower()
                        )
                        movies.append(movie)
                    except OSError:
                        continue  # Skip files we can't stat
        
        except Exception as e:
            print(f"    ❌ Error scanning {source.base_path}: {e}")
        
        # Cache results with simple directory mtime
        try:
            base_mtime = os.path.getmtime(source.base_path)
            self.cache[cache_key] = ScanCache(
                path=source.base_path,
                last_modified=base_mtime,
                last_scan=time.time(),
                file_count=len(movies),  # Just count what we found
                total_size=sum(m.file_size for m in movies),  # Sum what we found
                items=movies
            )
        except Exception as e:
            print(f"    ⚠️  Failed to cache results: {e}")
        
        return movies, False
    
    def _scan_tv_source_optimized(self, source: MediaSource, force_rescan: bool = False) -> Tuple[Dict[str, List[MediaItem]], bool]:
        """Optimized TV show source scanning with persistent caching."""
        print(f"📺 Scanning {source.name} ({source.base_path})")
        
        if not os.path.exists(source.base_path):
            print(f"    ⚠️  Path not found: {source.base_path}")
            return {}, False
        
        # Check cache first
        cache_key = f"{source.base_path}:tv"
        if not force_rescan and cache_key in self.cache:
            cache_entry = self.cache[cache_key]
            if cache_entry.is_valid():
                print(f"    💾 Using cached results ({len(cache_entry.items)} items)")
                # Convert cached items back to show structure
                cached_shows = {}
                for item in cache_entry.items:
                    if item.show_name not in cached_shows:
                        cached_shows[item.show_name] = []
                    cached_shows[item.show_name].append(item)
                return cached_shows, True
        
        tv_shows = {}
        
        try:
            # Use os.scandir for better performance than os.walk
            for entry in self._scan_directory_optimized(source.base_path, source.scan_depth):
                if entry.is_file() and self._is_video_file(entry.name) and not self._should_ignore(entry.name):
                    try:
                        stat_info = entry.stat()
                        relative_path = os.path.relpath(entry.path, source.base_path)
                        
                        # Extract show info from path structure
                        show_info = self._extract_tv_info_optimized(relative_path)
                        if not show_info:
                            continue
                        
                        show_name, season, episode, episode_title = show_info
                        
                        episode_item = MediaItem(
                            title=episode_title or entry.name,
                            media_type=MediaType.TV_EPISODE,
                            source_path=entry.path,
                            relative_path=relative_path,
                            file_size=stat_info.st_size,
                            file_extension=os.path.splitext(entry.name)[1].lower(),
                            show_name=show_name,
                            season=season,
                            episode=episode,
                            episode_title=episode_title
                        )
                        
                        if show_name not in tv_shows:
                            tv_shows[show_name] = []
                        tv_shows[show_name].append(episode_item)
                    
                    except OSError:
                        continue  # Skip files we can't stat
        
        except Exception as e:
            print(f"    ❌ Error scanning {source.base_path}: {e}")
        
        # Cache results with simple directory mtime
        try:
            all_items = []
            for episodes in tv_shows.values():
                all_items.extend(episodes)
            
            base_mtime = os.path.getmtime(source.base_path)
            self.cache[cache_key] = ScanCache(
                path=source.base_path,
                last_modified=base_mtime,
                last_scan=time.time(),
                file_count=len(all_items),  # Just count what we found
                total_size=sum(item.file_size for item in all_items),  # Sum what we found
                items=all_items
            )
        except Exception as e:
            print(f"    ⚠️  Failed to cache results: {e}")
        
        return tv_shows, False
    

    
    def _scan_directory_optimized(self, base_path: str, max_depth: int):
        """Optimized directory scanning using os.scandir."""
        def _scan_recursive(path: str, current_depth: int):
            if current_depth >= max_depth:
                return
            
            try:
                with os.scandir(path) as entries:
                    for entry in entries:
                        if entry.is_file():
                            yield entry
                        elif entry.is_dir() and not entry.name.startswith('.'):
                            yield from _scan_recursive(entry.path, current_depth + 1)
            except (OSError, PermissionError):
                pass  # Skip directories we can't access
        
        yield from _scan_recursive(base_path, 0)
    
    def _is_video_file(self, filename: str) -> bool:
        """Check if file is a video file."""
        return os.path.splitext(filename)[1].lower() in self.VIDEO_EXTENSIONS
    
    def _should_ignore(self, filename: str) -> bool:
        """Check if file should be ignored."""
        filename_lower = filename.lower()
        return any(pattern in filename_lower for pattern in self.IGNORE_PATTERNS)
    
    def _extract_movie_title(self, relative_path: str) -> str:
        """Extract movie title from file path."""
        # Try to extract from folder structure first
        path_parts = relative_path.split(os.sep)
        
        # If in a folder, use folder name
        if len(path_parts) > 1:
            folder_name = path_parts[-2]
            # Clean up folder name (remove year, quality markers, etc.)
            title = self._clean_title(folder_name)
            if title:
                return title
        
        # Fall back to filename
        filename = os.path.splitext(os.path.basename(relative_path))[0]
        return self._clean_title(filename)
    
    def _extract_tv_info_optimized(self, relative_path: str) -> Optional[Tuple[str, int, int, str]]:
        """Optimized TV show info extraction using pre-compiled patterns."""
        path_parts = relative_path.split(os.sep)
        filename = os.path.splitext(os.path.basename(relative_path))[0]
        
        # Extract show name (usually the first folder)
        show_name = path_parts[0] if path_parts else "Unknown Show"
        show_name = self._clean_title(show_name)
        
        # Try to extract season/episode from filename using pre-compiled patterns
        season = None
        episode = None
        
        for pattern in self.season_episode_patterns:
            match = pattern.search(filename)
            if match:
                season = int(match.group(1))
                episode = int(match.group(2))
                break
        
        # Extract episode title (everything after SxxExx pattern)
        episode_title = filename
        if season and episode:
            # Remove season/episode info to get clean title
            for pattern in self.season_episode_patterns:
                episode_title = pattern.sub('', episode_title).strip()
                episode_title = episode_title.lstrip('- ')  # Remove leading dashes
                if episode_title:
                    break
        
        return show_name, season, episode, episode_title
    
    def _clean_title(self, title: str) -> str:
        """Clean up title by removing common artifacts using pre-compiled patterns."""
        import re
        
        # Remove year in parentheses
        title = re.sub(r'\s*\(\d{4}\)\s*', ' ', title)
        
        # Remove quality markers using pre-compiled patterns
        for pattern in self.quality_patterns:
            title = pattern.sub('', title)
        
        # Remove multiple spaces and clean up
        title = re.sub(r'\s+', ' ', title).strip()
        
        # Remove trailing dots and dashes
        title = re.sub(r'[-.\s]+$', '', title)
        
        return title or "Unknown"
    
    def _deduplicate_movies(self, movies: List[MediaItem]) -> List[MediaItem]:
        """Remove duplicate movies based on title and size."""
        seen = set()
        unique_movies = []
        
        for movie in movies:
            key = (movie.title.lower(), movie.file_size)
            if key not in seen:
                seen.add(key)
                unique_movies.append(movie)
        
        return unique_movies
    
    def _deduplicate_tv_shows(self, tv_shows: Dict[str, List[MediaItem]]) -> Dict[str, List[MediaItem]]:
        """Remove duplicate TV episodes based on show, season, episode."""
        deduplicated = {}
        
        for show_name, episodes in tv_shows.items():
            seen = set()
            unique_episodes = []
            
            for episode in episodes:
                key = (show_name.lower(), episode.season, episode.episode, episode.file_size)
                if key not in seen:
                    seen.add(key)
                    unique_episodes.append(episode)
            
            if unique_episodes:
                deduplicated[show_name] = unique_episodes
        
        return deduplicated


class MediaSelector:
    """Interactive media selection interface."""
    
    def __init__(self, library: MediaLibrary):
        self.library = library
    
    def select_movie(self, query: str = "") -> Optional[MediaItem]:
        """Select a movie with optional search query."""
        if query:
            candidates = self.library.search_movies(query)
        else:
            candidates = self.library.get_all_movies_sorted()
        
        if not candidates:
            return None
        
        if len(candidates) == 1:
            return candidates[0]
        
        # This would be implemented with interactive selection in the UI
        return candidates[0]  # Placeholder
    
    def select_show_episodes(self, show_name: str, season: Optional[int] = None) -> List[MediaItem]:
        """Select episodes from a TV show."""
        episodes = self.library.get_show_episodes(show_name)
        
        if season is not None:
            episodes = [ep for ep in episodes if ep.season == season]
        
        return episodes
    
    def get_available_shows(self) -> List[str]:
        """Get list of available TV shows for autocomplete."""
        return self.library.get_all_shows_sorted()
    
    def get_available_movies(self) -> List[str]:
        """Get list of available movies for autocomplete."""
        return [movie.title for movie in self.library.get_all_movies_sorted()]


# Configuration for typical PlexSync setup
def get_default_media_sources() -> List[MediaSource]:
    """Get default media sources configuration."""
    return [
        MediaSource(
            name="Movies Primary",
            base_path="/mnt/media/Movies",
            media_type=MediaType.MOVIE,
            enabled=True
        ),
        MediaSource(
            name="Movies Secondary", 
            base_path="/mnt/media/Movies2",
            media_type=MediaType.MOVIE,
            enabled=True
        ),
        MediaSource(
            name="TV Shows Primary",
            base_path="/mnt/media/TV",
            media_type=MediaType.TV_SHOW,
            enabled=True
        ),
        MediaSource(
            name="TV Shows Secondary",
            base_path="/mnt/media/TV2", 
            media_type=MediaType.TV_SHOW,
            enabled=True
        ),
    ]


# Test dataset sizes (for development/testing)
class TestDatasetSize(Enum):
    """Test dataset sizes for development."""
    SMALL = "small"      # ~10 movies, 2 shows with 1 season each
    MEDIUM = "medium"    # ~100 movies, 10 shows with 2-3 seasons each  
    LARGE = "large"      # ~1000 movies, 50 shows with multiple seasons


@dataclass
class TestDatasetSpec:
    """Specification for test datasets."""
    size: TestDatasetSize
    movies_count: int
    shows_count: int
    avg_episodes_per_show: int
    purpose: str


# Test dataset configurations
TEST_DATASETS = {
    TestDatasetSize.SMALL: TestDatasetSpec(
        size=TestDatasetSize.SMALL,
        movies_count=10,
        shows_count=2,
        avg_episodes_per_show=10,
        purpose="Unit testing, quick iteration"
    ),
    TestDatasetSize.MEDIUM: TestDatasetSpec(
        size=TestDatasetSize.MEDIUM,
        movies_count=100,
        shows_count=10,
        avg_episodes_per_show=25,
        purpose="UI testing, performance validation"
    ),
    TestDatasetSize.LARGE: TestDatasetSpec(
        size=TestDatasetSize.LARGE,
        movies_count=1000,
        shows_count=50,
        avg_episodes_per_show=50,
        purpose="Scale testing, autocomplete performance"
    ),
} 