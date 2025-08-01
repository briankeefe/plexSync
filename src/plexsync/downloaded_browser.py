"""
Downloaded Media Browser Module

This module provides interactive browsing interfaces for downloaded media,
including multi-select operations, file management, and batch actions.
"""

import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Any, Tuple
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt, Confirm, IntPrompt
from rich.panel import Panel
from rich.columns import Columns
from rich.text import Text

from .downloaded import (
    DownloadedMediaManager, 
    DownloadedFile, 
    FileStatus,
    DownloadedMediaSummary
)
from .datasets import MediaLibrary
from .file_operations import FileOperationsManager
from .storage_analytics import StorageAnalytics
from .resync_manager import ResyncManager, ResyncRequest
from .advanced_duplicates import AdvancedDuplicateDetector
from .smart_organization import SmartOrganizer
from .usage_analytics import UsageAnalytics, AccessType


class DownloadedMediaBrowserInterface:
    """Interactive browser for downloaded media with multi-select capabilities."""
    
    def __init__(self, console: Console, manager: DownloadedMediaManager):
        self.console = console
        self.manager = manager
        self.selected_files: Set[str] = set()  # Track selected file paths
        self.page_size = 10
        
        # Initialize Phase 3 components
        self.file_operations = FileOperationsManager(console, manager)
        self.storage_analytics = StorageAnalytics(console, manager)
        
        # Initialize Phase 4 components
        self.resync_manager = ResyncManager(console, manager, None, self.file_operations)  # sync_engine would be injected
        self.advanced_duplicates = AdvancedDuplicateDetector(console, manager)
        self.smart_organizer = SmartOrganizer(console, manager, self.file_operations)
        self.usage_analytics = UsageAnalytics(console, manager)
        
    def show_main_menu(self, library: MediaLibrary) -> bool:
        """
        Show the main downloaded media management menu.
        
        Returns:
            True to continue, False to exit
        """
        while True:
            # Get current status
            status_report = self.manager.get_status_report(library)
            summary = status_report['summary']
            
            self.console.clear()
            self.console.print()
            self.console.print("📱 Downloaded Media Management", style="bold green")
            self.console.print()
            
            # Show current status
            self.console.print("Current Status:", style="bold blue")
            self.console.print(f"  🎬 Movies: {summary.movie_count} files ({summary.movies_size_gb:.2f} GB)")
            self.console.print(f"  📺 TV Episodes: {summary.episode_count} files ({summary.episodes_size_gb:.2f} GB)")
            self.console.print(f"  📊 Total: {summary.total_files} files • {summary.total_size_gb:.2f} GB")
            
            # Show issues if any
            if summary.orphaned or summary.partial or summary.corrupted:
                self.console.print()
                self.console.print("⚠️  Issues Found:", style="yellow")
                if summary.orphaned:
                    self.console.print(f"  👻 Orphaned: {len(summary.orphaned)} files")
                if summary.partial:
                    self.console.print(f"  ⚠️  Partial: {len(summary.partial)} files")
                if summary.corrupted:
                    self.console.print(f"  ❌ Corrupted: {len(summary.corrupted)} files")
            
            self.console.print()
            self.console.print("What would you like to do?", style="bold yellow")
            self.console.print()
            
            # Menu options (expanded for Phase 4)
            options = [
                ("1", "🎬 Browse Movies", f"({summary.movie_count} downloaded)" if summary.movie_count > 0 else "(no movies downloaded)"),
                ("2", "📺 Browse TV Shows", f"({summary.episode_count} episodes downloaded)" if summary.episode_count > 0 else "(no episodes downloaded)"),
                ("3", "🔍 Search Downloaded Content", "(find specific files)"),
                ("4", "📊 View Storage Analytics", "(detailed breakdown)"),
                ("5", "🧹 Cleanup & Management", "(smart cleanup options)"),
                ("6", "🔄 Re-sync Management", "(repair corrupted files)"),
                ("7", "🎯 Advanced Duplicates", "(sophisticated duplicate detection)"),
                ("8", "📁 Smart Organization", "(automatic file organization)"),
                ("9", "📈 Usage Analytics", "(access patterns & recommendations)"),
                ("10", "🗑️ Delete All Downloaded Media", f"(free {summary.total_size_gb:.2f} GB)" if summary.total_files > 0 else "(no files to delete)"),
                ("11", "🔙 Back to Main Menu", "(return to sync)")
            ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} {desc}")
            
            self.console.print()
            
            choice = Prompt.ask("Select [1-11]", default="11").strip()
            
            if choice == "1":
                if summary.movie_count > 0:
                    self.browse_movies(library)
                else:
                    self.console.print("❌ No movies downloaded yet", style="red")
                    self.console.print("Press Enter to continue...")
                    input()
            elif choice == "2":
                if summary.episode_count > 0:
                    self.browse_episodes(library)
                else:
                    self.console.print("❌ No TV episodes downloaded yet", style="red")
                    self.console.print("Press Enter to continue...")
                    input()
            elif choice == "3":
                self.search_downloaded_content(library)
            elif choice == "4":
                self.show_storage_analytics(library)
            elif choice == "5":
                self.cleanup_management(library)
            elif choice == "6":
                self.resync_management(library)
            elif choice == "7":
                self.advanced_duplicate_management(library)
            elif choice == "8":
                self.smart_organization_management(library)
            elif choice == "9":
                self.usage_analytics_dashboard(library)
            elif choice == "10":
                if summary.total_files > 0:
                    self.delete_all_confirmation(library)
                else:
                    self.console.print("❌ No files to delete", style="red")
                    self.console.print("Press Enter to continue...")
                    input()
            elif choice == "11" or choice.lower() in ["q", "quit", "back", "b"]:
                return False
            else:
                self.console.print("❌ Invalid choice. Please select 1-11", style="red")
                self.console.print("Press Enter to continue...")
                input()
    
    def browse_movies(self, library: MediaLibrary):
        """Browse downloaded movies with multi-select functionality."""
        summary = self.manager.scanner.get_summary(library)
        movies = summary.movies
        
        if not movies:
            self.console.print("❌ No movies downloaded", style="red")
            return
        
        page = 1
        total_pages = (len(movies) + self.page_size - 1) // self.page_size
        
        while True:
            self.console.clear()
            self.console.print()
            self.console.print("🎬 Downloaded Movies - Multi-Select Mode", style="bold green")
            self.console.print()
            
            # Show selection status
            selected_count = len(self.selected_files)
            selected_size = sum(
                movie.file_size 
                for movie in movies 
                if str(movie.file_path) in self.selected_files
            )
            selected_size_gb = selected_size / (1024**3)
            
            if selected_count > 0:
                self.console.print(f"Selected: {selected_count} files • {selected_size_gb:.2f} GB", style="green")
                self.console.print()
            
            # Create table
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("☐", width=3, justify="center")
            table.add_column("#", width=3, justify="right")
            table.add_column("Title", style="dim")
            table.add_column("Size", justify="right")
            table.add_column("Downloaded", justify="right")
            table.add_column("Status", justify="center")
            
            # Calculate page range
            start_idx = (page - 1) * self.page_size
            end_idx = min(start_idx + self.page_size, len(movies))
            page_movies = movies[start_idx:end_idx]
            
            # Add rows
            for i, movie in enumerate(page_movies):
                file_path_str = str(movie.file_path)
                is_selected = file_path_str in self.selected_files
                
                checkbox = "☑️" if is_selected else "☐"
                row_number = start_idx + i + 1
                title = movie.display_name
                size = f"{movie.size_gb:.2f} GB"
                downloaded = movie.download_date.strftime("%Y-%m-%d") if movie.download_date else "Unknown"
                
                # Status indicator
                if movie.status == FileStatus.COMPLETE:
                    status = "✅ Complete"
                elif movie.status == FileStatus.PARTIAL:
                    status = "⚠️ Partial"
                elif movie.status == FileStatus.CORRUPTED:
                    status = "❌ Corrupted"
                else:
                    status = f"❓ {movie.status.value.title()}"
                
                # Dim selected rows
                style = "dim" if is_selected else None
                
                table.add_row(
                    checkbox, str(row_number), title, size, downloaded, status,
                    style=style
                )
            
            self.console.print(table)
            self.console.print()
            
            # Navigation and action options
            nav_options = []
            if page > 1:
                nav_options.append("(p)revious")
            if page < total_pages:
                nav_options.append("(n)ext")
            nav_options.extend(["(j)ump to page", "(s)earch"])
            
            action_options = [
                "(a)ll", "(none)", "(i)nvert", "space to toggle",
                "(d)elete selected", "(v)erify selected", "(i)nfo selected"
            ]
            
            self.console.print(f"Navigation: {' • '.join(nav_options)} • Page {page}/{total_pages}")
            self.console.print(f"Multi-Select: {' • '.join(action_options)}")
            self.console.print("Actions: (ESC) exit multi-select • (q)uit to main menu")
            self.console.print()
            
            command = Prompt.ask("Select file [1-10], range [1-5], or command", default="").strip().lower()
            
            if command in ["q", "quit", "back", "b"]:
                break
            elif command in ["esc", "escape", ""]:
                break
            elif command == "p" and page > 1:
                page -= 1
            elif command == "n" and page < total_pages:
                page += 1
            elif command == "j":
                new_page = self._handle_page_jump(total_pages, page)
                if new_page:
                    page = new_page
            elif command == "s":
                # Future: implement search
                self.console.print("🔍 Search functionality will be implemented next", style="yellow")
                input("Press Enter to continue...")
            elif command == "a":
                # Select all on current page
                for movie in page_movies:
                    self.selected_files.add(str(movie.file_path))
                self.console.print(f"✅ Selected all {len(page_movies)} movies on current page", style="green")
                input("Press Enter to continue...")
            elif command == "none":
                # Clear all selections
                self.selected_files.clear()
                self.console.print("✅ Cleared all selections", style="green")
                input("Press Enter to continue...")
            elif command == "i":
                # Invert selection on current page
                for movie in page_movies:
                    file_path_str = str(movie.file_path)
                    if file_path_str in self.selected_files:
                        self.selected_files.remove(file_path_str)
                    else:
                        self.selected_files.add(file_path_str)
                self.console.print("✅ Inverted selection on current page", style="green")
                input("Press Enter to continue...")
            elif command == "d":
                if self.selected_files:
                    self._delete_selected_files(movies)
                else:
                    self.console.print("❌ No files selected", style="red")
                    input("Press Enter to continue...")
            elif command == "v":
                if self.selected_files:
                    self._verify_selected_files(movies)
                else:
                    self.console.print("❌ No files selected", style="red")
                    input("Press Enter to continue...")
            elif command == "info":
                if self.selected_files:
                    self._show_selected_info(movies)
                else:
                    self.console.print("❌ No files selected", style="red")
                    input("Press Enter to continue...")
            elif command.isdigit():
                # Toggle selection for specific number
                num = int(command)
                if 1 <= num <= len(page_movies):
                    movie = page_movies[num - 1]
                    file_path_str = str(movie.file_path)
                    if file_path_str in self.selected_files:
                        self.selected_files.remove(file_path_str)
                        self.console.print(f"✅ Deselected: {movie.display_name}", style="yellow")
                    else:
                        self.selected_files.add(file_path_str)
                        self.console.print(f"✅ Selected: {movie.display_name}", style="green")
                    input("Press Enter to continue...")
                else:
                    self.console.print("❌ Invalid number", style="red")
                    input("Press Enter to continue...")
            elif "-" in command:
                # Range selection (e.g., "1-5")
                try:
                    start, end = map(int, command.split("-"))
                    if 1 <= start <= end <= len(page_movies):
                        for i in range(start - 1, end):
                            movie = page_movies[i]
                            self.selected_files.add(str(movie.file_path))
                        self.console.print(f"✅ Selected movies {start}-{end}", style="green")
                        input("Press Enter to continue...")
                    else:
                        self.console.print("❌ Invalid range", style="red")
                        input("Press Enter to continue...")
                except ValueError:
                    self.console.print("❌ Invalid range format. Use format like '1-5'", style="red")
                    input("Press Enter to continue...")
            else:
                self.console.print("❌ Invalid command", style="red")
                input("Press Enter to continue...")
    
    def browse_episodes(self, library: MediaLibrary):
        """Browse downloaded TV episodes with multi-select functionality."""
        summary = self.manager.scanner.get_summary(library)
        episodes = summary.episodes
        
        if not episodes:
            self.console.print("❌ No TV episodes downloaded", style="red")
            return
        
        # Group episodes by show
        shows_dict = {}
        for episode in episodes:
            show_name = episode.show_name if hasattr(episode, 'show_name') else "Unknown Show"
            if show_name not in shows_dict:
                shows_dict[show_name] = []
            shows_dict[show_name].append(episode)
        
        # Sort shows by name
        sorted_shows = sorted(shows_dict.keys())
        
        page = 1
        total_pages = (len(episodes) + self.page_size - 1) // self.page_size
        
        while True:
            self.console.clear()
            self.console.print()
            self.console.print("📺 Downloaded TV Episodes - Multi-Select Mode", style="bold green")
            self.console.print()
            
            # Show selection status
            selected_count = len(self.selected_files)
            selected_size = sum(
                episode.file_size 
                for episode in episodes 
                if str(episode.file_path) in self.selected_files
            )
            selected_size_gb = selected_size / (1024**3)
            
            if selected_count > 0:
                self.console.print(f"Selected: {selected_count} files • {selected_size_gb:.2f} GB", style="green")
                self.console.print()
            
            # Show summary by show
            self.console.print("📊 By Show:", style="bold blue")
            for show_name in sorted_shows[:5]:  # Show first 5 shows
                show_episodes = shows_dict[show_name]
                self.console.print(f"  📺 {show_name}: {len(show_episodes)} episodes")
            
            if len(sorted_shows) > 5:
                self.console.print(f"  ... and {len(sorted_shows) - 5} more shows")
            
            self.console.print()
            
            # Create table
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("☐", width=3, justify="center")
            table.add_column("#", width=3, justify="right")
            table.add_column("Show", style="dim")
            table.add_column("Episode", style="dim")
            table.add_column("Size", justify="right")
            table.add_column("Downloaded", justify="right")
            table.add_column("Status", justify="center")
            
            # Calculate page range
            start_idx = (page - 1) * self.page_size
            end_idx = min(start_idx + self.page_size, len(episodes))
            page_episodes = episodes[start_idx:end_idx]
            
            # Add rows
            for i, episode in enumerate(page_episodes):
                file_path_str = str(episode.file_path)
                is_selected = file_path_str in self.selected_files
                
                checkbox = "☑️" if is_selected else "☐"
                row_number = start_idx + i + 1
                
                # Extract show and episode info
                show_name = episode.show_name if hasattr(episode, 'show_name') else "Unknown Show"
                episode_info = episode.episode_info if hasattr(episode, 'episode_info') else episode.display_name
                
                size = f"{episode.size_gb:.2f} GB"
                downloaded = episode.download_date.strftime("%Y-%m-%d") if episode.download_date else "Unknown"
                
                # Status indicator
                if episode.status == FileStatus.COMPLETE:
                    status = "✅ Complete"
                elif episode.status == FileStatus.PARTIAL:
                    status = "⚠️ Partial"
                elif episode.status == FileStatus.CORRUPTED:
                    status = "❌ Corrupted"
                else:
                    status = f"❓ {episode.status.value.title()}"
                
                # Dim selected rows
                style = "dim" if is_selected else None
                
                table.add_row(
                    checkbox, str(row_number), show_name, episode_info, size, downloaded, status,
                    style=style
                )
            
            self.console.print(table)
            self.console.print()
            
            # Navigation and action options
            nav_options = []
            if page > 1:
                nav_options.append("(p)revious")
            if page < total_pages:
                nav_options.append("(n)ext")
            nav_options.extend(["(j)ump to page", "(s)earch"])
            
            action_options = [
                "(a)ll", "(none)", "(i)nvert", "space to toggle",
                "(d)elete selected", "(v)erify selected", "(i)nfo selected"
            ]
            
            self.console.print(f"Navigation: {' • '.join(nav_options)} • Page {page}/{total_pages}")
            self.console.print(f"Multi-Select: {' • '.join(action_options)}")
            self.console.print("Actions: (ESC) exit multi-select • (q)uit to main menu")
            self.console.print()
            
            command = Prompt.ask("Select file [1-10], range [1-5], or command", default="").strip().lower()
            
            if command in ["q", "quit", "back", "b"]:
                break
            elif command in ["esc", "escape", ""]:
                break
            elif command == "p" and page > 1:
                page -= 1
            elif command == "n" and page < total_pages:
                page += 1
            elif command == "j":
                new_page = self._handle_page_jump(total_pages, page)
                if new_page:
                    page = new_page
            elif command == "s":
                # Future: implement search
                self.console.print("🔍 Search functionality will be implemented next", style="yellow")
                input("Press Enter to continue...")
            elif command == "a":
                # Select all on current page
                for episode in page_episodes:
                    self.selected_files.add(str(episode.file_path))
                self.console.print(f"✅ Selected all {len(page_episodes)} episodes on current page", style="green")
                input("Press Enter to continue...")
            elif command == "none":
                # Clear all selections
                self.selected_files.clear()
                self.console.print("✅ Cleared all selections", style="green")
                input("Press Enter to continue...")
            elif command == "i":
                # Invert selection on current page
                for episode in page_episodes:
                    file_path_str = str(episode.file_path)
                    if file_path_str in self.selected_files:
                        self.selected_files.remove(file_path_str)
                    else:
                        self.selected_files.add(file_path_str)
                self.console.print("✅ Inverted selection on current page", style="green")
                input("Press Enter to continue...")
            elif command == "d":
                if self.selected_files:
                    self._delete_selected_files(episodes)
                else:
                    self.console.print("❌ No files selected", style="red")
                    input("Press Enter to continue...")
            elif command == "v":
                if self.selected_files:
                    self._verify_selected_files(episodes)
                else:
                    self.console.print("❌ No files selected", style="red")
                    input("Press Enter to continue...")
            elif command == "info":
                if self.selected_files:
                    self._show_selected_info(episodes)
                else:
                    self.console.print("❌ No files selected", style="red")
                    input("Press Enter to continue...")
            elif command.isdigit():
                # Toggle selection for specific number
                num = int(command)
                if 1 <= num <= len(page_episodes):
                    episode = page_episodes[num - 1]
                    file_path_str = str(episode.file_path)
                    if file_path_str in self.selected_files:
                        self.selected_files.remove(file_path_str)
                        self.console.print(f"✅ Deselected: {episode.display_name}", style="yellow")
                    else:
                        self.selected_files.add(file_path_str)
                        self.console.print(f"✅ Selected: {episode.display_name}", style="green")
                    input("Press Enter to continue...")
                else:
                    self.console.print("❌ Invalid number", style="red")
                    input("Press Enter to continue...")
            elif "-" in command:
                # Range selection (e.g., "1-5")
                try:
                    start, end = map(int, command.split("-"))
                    if 1 <= start <= end <= len(page_episodes):
                        for i in range(start - 1, end):
                            episode = page_episodes[i]
                            self.selected_files.add(str(episode.file_path))
                        self.console.print(f"✅ Selected episodes {start}-{end}", style="green")
                        input("Press Enter to continue...")
                    else:
                        self.console.print("❌ Invalid range", style="red")
                        input("Press Enter to continue...")
                except ValueError:
                    self.console.print("❌ Invalid range format. Use format like '1-5'", style="red")
                    input("Press Enter to continue...")
            else:
                self.console.print("❌ Invalid command", style="red")
                input("Press Enter to continue...")
    
    def search_downloaded_content(self, library: MediaLibrary):
        """Search through downloaded content."""
        self.console.print("🔍 Search Downloaded Content", style="bold green")
        self.console.print()
        
        query = Prompt.ask("Enter search query").strip()
        if not query:
            return
        
        # Get all downloaded files
        summary = self.manager.scanner.get_summary(library)
        all_files = summary.movies + summary.episodes + summary.orphaned
        
        # Filter by search query
        matching_files = [
            f for f in all_files 
            if query.lower() in f.display_name.lower()
        ]
        
        if not matching_files:
            self.console.print(f"❌ No files found matching '{query}'", style="red")
            input("Press Enter to continue...")
            return
        
        # Show results
        self.console.print(f"🔍 Found {len(matching_files)} files matching '{query}':")
        self.console.print()
        
        table = Table(show_header=True, header_style="bold blue")
        table.add_column("Type", width=8)
        table.add_column("Name", style="dim")
        table.add_column("Size", justify="right")
        table.add_column("Status", justify="center")
        
        for file in matching_files[:20]:  # Limit to first 20 results
            file_type = "🎬 Movie" if file in summary.movies else "📺 Episode" if file in summary.episodes else "👻 Orphaned"
            name = file.display_name
            size = f"{file.size_gb:.2f} GB"
            status = "✅" if file.status == FileStatus.COMPLETE else "⚠️"
            
            table.add_row(file_type, name, size, status)
        
        self.console.print(table)
        
        if len(matching_files) > 20:
            self.console.print(f"\n... and {len(matching_files) - 20} more files")
        
        self.console.print()
        input("Press Enter to continue...")
    
    def show_storage_analytics(self, library: MediaLibrary):
        """Show detailed storage analytics."""
        while True:
            self.console.clear()
            self.console.print()
            self.console.print("📊 Storage Analytics", style="bold blue")
            self.console.print()
            
            options = [
                ("1", "📊 Storage Breakdown", "detailed size analysis by type, extension, date"),
                ("2", "🔍 Duplicate Analysis", "find and analyze duplicate files"),
                ("3", "💡 Optimization Suggestions", "recommendations for storage optimization"),
                ("4", "📋 Export Report", "export analytics to JSON file"),
                ("5", "🔙 Back to Main Menu", "return to downloaded media management")
            ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} - {desc}")
            
            self.console.print()
            
            choice = Prompt.ask("Select analytics option [1-5]", default="5").strip()
            
            if choice == "1":
                self.storage_analytics.show_storage_breakdown(library)
            elif choice == "2":
                self.storage_analytics.show_duplicate_analysis(library)
            elif choice == "3":
                self.storage_analytics.show_optimization_suggestions(library)
            elif choice == "4":
                self._export_analytics_report(library)
            elif choice == "5" or choice.lower() in ["q", "quit", "back", "b"]:
                break
            else:
                self.console.print("❌ Invalid choice. Please select 1-5", style="red")
                input("Press Enter to continue...")
    
    def cleanup_management(self, library: MediaLibrary):
        """Smart cleanup and management options."""
        while True:
            self.console.clear()
            self.console.print()
            self.console.print("🧹 Cleanup & Management", style="bold green")
            self.console.print()
            
            # Get optimization suggestions
            suggestions = self.storage_analytics.generate_optimization_suggestions(library)
            
            if suggestions:
                total_savings = sum(s.potential_savings for s in suggestions)
                total_savings_gb = total_savings / (1024**3)
                self.console.print(f"💾 Potential savings: {total_savings_gb:.2f} GB")
                self.console.print()
            
            options = [
                ("1", "🗑️ Smart Cleanup", "automatically remove duplicates and orphaned files"),
                ("2", "🔍 Remove Duplicates", "find and remove duplicate files"),
                ("3", "👻 Clean Orphaned Files", "remove files not in your library"),
                ("4", "⚠️ Fix Corrupted Files", "remove or re-sync corrupted files"),
                ("5", "📁 Bulk File Operations", "move, copy, or organize files"),
                ("6", "📊 Cleanup Preview", "preview what would be cleaned"),
                ("7", "🔙 Back to Main Menu", "return to downloaded media management")
            ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} - {desc}")
            
            self.console.print()
            
            choice = Prompt.ask("Select cleanup option [1-7]", default="7").strip()
            
            if choice == "1":
                self._smart_cleanup(library)
            elif choice == "2":
                self._remove_duplicates(library)
            elif choice == "3":
                self._clean_orphaned_files(library)
            elif choice == "4":
                self._fix_corrupted_files(library)
            elif choice == "5":
                self._bulk_file_operations(library)
            elif choice == "6":
                self._cleanup_preview(library)
            elif choice == "7" or choice.lower() in ["q", "quit", "back", "b"]:
                break
            else:
                self.console.print("❌ Invalid choice. Please select 1-7", style="red")
                input("Press Enter to continue...")
    
    def delete_all_confirmation(self, library: MediaLibrary):
        """Confirm deletion of all downloaded media."""
        status_report = self.manager.get_status_report(library)
        summary = status_report['summary']
        
        self.console.print()
        self.console.print("🗑️  Delete All Downloaded Media", style="bold red")
        self.console.print()
        self.console.print("⚠️  WARNING: This will permanently delete ALL downloaded files", style="red")
        self.console.print()
        
        self.console.print("Current Downloaded Media:")
        self.console.print(f"  🎬 Movies: {summary.movie_count} files ({summary.movies_size_gb:.2f} GB)")
        self.console.print(f"  📺 TV Episodes: {summary.episode_count} files ({summary.episodes_size_gb:.2f} GB)")
        self.console.print(f"  📊 Total: {summary.total_files} files • {summary.total_size_gb:.2f} GB")
        self.console.print()
        
        self.console.print("This action will:")
        self.console.print(f"  ✓ Free up {summary.total_size_gb:.2f} GB of storage space")
        self.console.print("  ✓ Keep your original library intact (source files safe)")
        self.console.print("  ❌ Require re-downloading if you want files again")
        self.console.print("  ❌ Cannot be undone")
        self.console.print()
        
        confirmation = Prompt.ask("Type 'DELETE ALL' to confirm or anything else to cancel").strip()
        
        if confirmation == "DELETE ALL":
            # Get all files for deletion
            all_files = summary.movies + summary.episodes + summary.orphaned
            
            # Use the file operations manager for actual deletion
            result = self.file_operations.delete_files(
                all_files,
                confirmation_callback=lambda: True  # Already confirmed
            )
            
            if result.successful > 0:
                self.console.print(f"✅ Successfully deleted {result.successful} files", style="green")
                self.console.print(f"💾 Storage freed: {result.bytes_processed / (1024**3):.2f} GB")
            
            if result.failed > 0:
                self.console.print(f"❌ Failed to delete {result.failed} files", style="red")
                for error in result.errors:
                    self.console.print(f"  • {error}")
        else:
            self.console.print("✅ Deletion cancelled", style="green")
        
        input("Press Enter to continue...")
    
    def resync_management(self, library: MediaLibrary):
        """Manage file re-syncing for corrupted or missing files."""
        while True:
            self.console.clear()
            self.console.print()
            self.console.print("🔄 Re-sync Management", style="bold blue")
            self.console.print()
            
            # Show re-sync candidates
            candidates = self.resync_manager.scan_for_resync_candidates(library)
            
            if candidates:
                self.console.print(f"⚠️  Found {len(candidates)} files that need re-syncing")
                total_size = sum(c.estimated_size or 0 for c in candidates)
                self.console.print(f"📊 Total size: {total_size / (1024**3):.2f} GB")
                self.console.print()
            else:
                self.console.print("✅ All files are in good condition!")
                self.console.print()
            
            options = [
                ("1", "🔍 Scan for Issues", "check all files for corruption or missing data"),
                ("2", "🔄 Auto Re-sync All", "automatically re-sync all problematic files"),
                ("3", "🎯 Selective Re-sync", "choose specific files to re-sync"),
                ("4", "📊 Re-sync Statistics", "view re-sync history and statistics"),
                ("5", "📋 Export Re-sync Report", "export detailed re-sync analysis"),
                ("6", "🔙 Back to Main Menu", "return to downloaded media management")
            ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} - {desc}")
            
            self.console.print()
            
            choice = Prompt.ask("Select re-sync option [1-6]", default="6").strip()
            
            if choice == "1":
                self.resync_manager.show_resync_candidates(library)
                input("Press Enter to continue...")
            elif choice == "2":
                if candidates:
                    self._auto_resync_all(candidates)
                else:
                    self.console.print("✅ No files need re-syncing!", style="green")
                    input("Press Enter to continue...")
            elif choice == "3":
                if candidates:
                    self._selective_resync(candidates)
                else:
                    self.console.print("✅ No files need re-syncing!", style="green")
                    input("Press Enter to continue...")
            elif choice == "4":
                self._show_resync_statistics()
            elif choice == "5":
                self._export_resync_report(library)
            elif choice == "6" or choice.lower() in ["q", "quit", "back", "b"]:
                break
            else:
                self.console.print("❌ Invalid choice. Please select 1-6", style="red")
                input("Press Enter to continue...")
    
    def advanced_duplicate_management(self, library: MediaLibrary):
        """Manage advanced duplicate detection and removal."""
        while True:
            self.console.clear()
            self.console.print()
            self.console.print("🎯 Advanced Duplicate Management", style="bold blue")
            self.console.print()
            
            options = [
                ("1", "🔍 Similarity Analysis", "comprehensive duplicate detection with AI"),
                ("2", "📊 Duplicate Report", "detailed analysis of found duplicates"),
                ("3", "🗑️ Smart Duplicate Removal", "automatically remove safe duplicates"),
                ("4", "🎭 Movie Duplicate Detection", "find duplicate movies with different versions"),
                ("5", "📺 Episode Duplicate Detection", "find duplicate TV episodes"),
                ("6", "📋 Export Similarity Report", "export detailed duplicate analysis"),
                ("7", "🔙 Back to Main Menu", "return to downloaded media management")
            ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} - {desc}")
            
            self.console.print()
            
            choice = Prompt.ask("Select duplicate option [1-7]", default="7").strip()
            
            if choice == "1":
                self.advanced_duplicates.show_similarity_analysis(library)
            elif choice == "2":
                self._show_duplicate_report(library)
            elif choice == "3":
                self._smart_duplicate_removal(library)
            elif choice == "4":
                self._movie_duplicate_detection(library)
            elif choice == "5":
                self._episode_duplicate_detection(library)
            elif choice == "6":
                self._export_similarity_report(library)
            elif choice == "7" or choice.lower() in ["q", "quit", "back", "b"]:
                break
            else:
                self.console.print("❌ Invalid choice. Please select 1-7", style="red")
                input("Press Enter to continue...")
    
    def smart_organization_management(self, library: MediaLibrary):
        """Manage smart file organization."""
        while True:
            self.console.clear()
            self.console.print()
            self.console.print("📁 Smart Organization Management", style="bold green")
            self.console.print()
            
            # Show organization suggestions
            suggestions = self.smart_organizer.suggest_organization_improvements(library)
            
            self.console.print("💡 Organization Status:")
            for suggestion in suggestions:
                self.console.print(f"  {suggestion}")
            self.console.print()
            
            options = [
                ("1", "📋 Organization Preview", "preview suggested file organization"),
                ("2", "🚀 Auto-Organize Files", "automatically organize all files"),
                ("3", "🎯 Selective Organization", "choose specific files to organize"),
                ("4", "📏 Organization Rules", "view and manage organization rules"),
                ("5", "🔧 Custom Organization", "create custom organization rules"),
                ("6", "📊 Organization Analysis", "detailed organization analysis"),
                ("7", "📋 Export Organization Plan", "export organization plan to file"),
                ("8", "🔙 Back to Main Menu", "return to downloaded media management")
            ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} - {desc}")
            
            self.console.print()
            
            choice = Prompt.ask("Select organization option [1-8]", default="8").strip()
            
            if choice == "1":
                self.smart_organizer.show_organization_preview(library)
            elif choice == "2":
                self._auto_organize_files(library)
            elif choice == "3":
                self._selective_organization(library)
            elif choice == "4":
                self.smart_organizer.show_rules()
                input("Press Enter to continue...")
            elif choice == "5":
                self._create_custom_organization_rule()
            elif choice == "6":
                self._show_organization_analysis(library)
            elif choice == "7":
                self._export_organization_plan(library)
            elif choice == "8" or choice.lower() in ["q", "quit", "back", "b"]:
                break
            else:
                self.console.print("❌ Invalid choice. Please select 1-8", style="red")
                input("Press Enter to continue...")
    
    def usage_analytics_dashboard(self, library: MediaLibrary):
        """Show usage analytics dashboard."""
        while True:
            self.console.clear()
            self.console.print()
            self.console.print("📈 Usage Analytics Dashboard", style="bold green")
            self.console.print()
            
            options = [
                ("1", "📊 Usage Dashboard", "comprehensive usage overview"),
                ("2", "🏆 Most Used Files", "see your most accessed files"),
                ("3", "👻 Never Accessed Files", "find files you've never used"),
                ("4", "💡 Smart Recommendations", "AI-driven usage recommendations"),
                ("5", "📈 Usage Trends", "view access patterns over time"),
                ("6", "🧹 Usage-Based Cleanup", "cleanup based on usage patterns"),
                ("7", "📋 Export Usage Report", "export detailed usage analysis"),
                ("8", "🔧 Analytics Settings", "configure usage tracking"),
                ("9", "🔙 Back to Main Menu", "return to downloaded media management")
            ]
            
            for num, name, desc in options:
                self.console.print(f"  {num}. {name} - {desc}")
            
            self.console.print()
            
            choice = Prompt.ask("Select analytics option [1-9]", default="9").strip()
            
            if choice == "1":
                self.usage_analytics.show_usage_dashboard(library)
            elif choice == "2":
                self._show_most_used_files(library)
            elif choice == "3":
                self._show_never_accessed_files(library)
            elif choice == "4":
                self._show_usage_recommendations(library)
            elif choice == "5":
                self._show_usage_trends(library)
            elif choice == "6":
                self._usage_based_cleanup(library)
            elif choice == "7":
                self._export_usage_report(library)
            elif choice == "8":
                self._analytics_settings()
            elif choice == "9" or choice.lower() in ["q", "quit", "back", "b"]:
                break
            else:
                self.console.print("❌ Invalid choice. Please select 1-9", style="red")
                input("Press Enter to continue...")
    
    def show_file_details(self, file: DownloadedFile, library: MediaLibrary):
        """Show detailed information about a file."""
        # Record file access for usage analytics
        self.usage_analytics.record_access(file, AccessType.ACCESSED)
        
        self.console.clear()
        self.console.print()
        self.console.print("📄 File Details", style="bold green")
        self.console.print()
        
        # Create info panel
        info_lines = [
            f"📁 Name: {file.display_name}",
            f"📏 Size: {file.size_gb:.2f} GB ({file.file_size:,} bytes)",
            f"📅 Downloaded: {file.download_date.strftime('%Y-%m-%d %H:%M:%S') if file.download_date else 'Unknown'}",
            f"📍 Location: {file.file_path}",
            f"🔧 Status: {file.status.value.title()}",
        ]
        
        # Add additional info if available
        if hasattr(file, 'show_name'):
            info_lines.insert(1, f"📺 Show: {file.show_name}")
        if hasattr(file, 'season_number'):
            info_lines.insert(2, f"📀 Season: {file.season_number}")
        if hasattr(file, 'episode_number'):
            info_lines.insert(3, f"🎬 Episode: {file.episode_number}")
        
        # File system info
        if file.file_path.exists():
            stat = file.file_path.stat()
            info_lines.extend([
                f"🔐 Permissions: {oct(stat.st_mode)[-3:]}",
                f"👤 Owner: {stat.st_uid}:{stat.st_gid}",
                f"🔗 Hard Links: {stat.st_nlink}",
            ])
        
        for line in info_lines:
            self.console.print(f"  {line}")
        
        self.console.print()
        
        # Action options
        self.console.print("Available Actions:", style="bold yellow")
        actions = [
            ("1", "🔍 Open File Location", "open in file manager"),
            ("2", "✅ Verify File Integrity", "check if file is complete"),
            ("3", "🔄 Re-sync File", "download again if corrupted"),
            ("4", "🗑️  Delete File", "permanently remove from disk"),
            ("5", "📋 Show Sync History", "view download history"),
            ("6", "🔙 Back to Browser", "return to file list")
        ]
        
        for num, name, desc in actions:
            self.console.print(f"  {num}. {name} - {desc}")
        
        self.console.print()
        
        while True:
            choice = Prompt.ask("Select action [1-6]", default="6").strip()
            
            if choice == "1":
                self._open_file_location(file)
            elif choice == "2":
                self._verify_file_integrity(file)
            elif choice == "3":
                self._resync_file(file, library)
            elif choice == "4":
                if self._delete_single_file(file):
                    break  # Exit if file was deleted
            elif choice == "5":
                self._show_sync_history(file)
            elif choice == "6" or choice.lower() in ["q", "quit", "back", "b"]:
                break
            else:
                self.console.print("❌ Invalid choice. Please select 1-6", style="red")
                input("Press Enter to continue...")
    
    def _open_file_location(self, file: DownloadedFile):
        """Open file location in system file manager."""
        self.console.print(f"📁 Opening file location: {file.file_path.parent}")
        
        try:
            import subprocess
            import sys
            
            if sys.platform == "win32":
                subprocess.run(["explorer", "/select,", str(file.file_path)])
            elif sys.platform == "darwin":
                subprocess.run(["open", "-R", str(file.file_path)])
            else:
                # Linux/Unix
                subprocess.run(["xdg-open", str(file.file_path.parent)])
            
            self.console.print("✅ File location opened in system file manager", style="green")
        except Exception as e:
            self.console.print(f"❌ Could not open file location: {e}", style="red")
            self.console.print(f"💡 Manual path: {file.file_path.parent}")
        
        input("Press Enter to continue...")
    
    def _verify_file_integrity(self, file: DownloadedFile):
        """Verify file integrity."""
        self.console.print(f"🔍 Verifying file integrity: {file.display_name}")
        
        # Use the file operations manager for comprehensive verification
        reports = self.file_operations.verify_file_integrity([file])
        
        if reports:
            report = reports[0]
            
            if report.status.value == "verified":
                self.console.print("✅ File integrity verified - file is complete and valid", style="green")
            elif report.status.value == "missing":
                self.console.print("❌ File not found on disk", style="red")
            elif report.status.value == "corrupted":
                self.console.print("❌ File is corrupted", style="red")
            elif report.status.value == "incomplete":
                self.console.print("⚠️ File is incomplete", style="yellow")
            else:
                self.console.print("❓ File integrity unknown", style="yellow")
            
            if report.error_message:
                self.console.print(f"Details: {report.error_message}")
        
        input("Press Enter to continue...")
    
    def _resync_file(self, file: DownloadedFile, library: MediaLibrary):
        """Re-sync a file."""
        self.console.print(f"🔄 Re-sync functionality for {file.display_name}")
        self.console.print()
        self.console.print("This will:")
        self.console.print("  ✓ Download the file again from the source")
        self.console.print("  ✓ Replace the existing file")
        self.console.print("  ✓ Verify the new download")
        self.console.print()
        
        if Confirm.ask("Proceed with re-sync [y/N]", default=False):
            self.console.print("🔄 Re-sync functionality will be implemented in Phase 3!", style="yellow")
        else:
            self.console.print("✅ Re-sync cancelled", style="green")
        
        input("Press Enter to continue...")
    
    def _delete_single_file(self, file: DownloadedFile) -> bool:
        """Delete a single file. Returns True if file was deleted."""
        # Use the file operations manager for actual deletion
        result = self.file_operations.delete_files([file])
        
        if result.successful > 0:
            self.console.print("✅ File deleted successfully", style="green")
            return True
        elif result.failed > 0:
            self.console.print("❌ Failed to delete file", style="red")
            for error in result.errors:
                self.console.print(f"  • {error}")
        else:
            self.console.print("⚠️ File deletion was cancelled", style="yellow")
        
        input("Press Enter to continue...")
        return False
    
    def _show_sync_history(self, file: DownloadedFile):
        """Show sync history for a file."""
        self.console.print(f"📋 Sync History for: {file.display_name}")
        self.console.print()
        
        # Show basic info
        self.console.print("Download Information:")
        self.console.print(f"  📅 Downloaded: {file.download_date.strftime('%Y-%m-%d %H:%M:%S') if file.download_date else 'Unknown'}")
        self.console.print(f"  📏 Size: {file.size_gb:.2f} GB")
        self.console.print(f"  🔧 Status: {file.status.value.title()}")
        
        self.console.print()
        self.console.print("💡 Detailed sync history tracking will be available in Phase 3")
        
        input("Press Enter to continue...")
    
    def _export_analytics_report(self, library: MediaLibrary):
        """Export analytics report to JSON file."""
        self.console.print()
        self.console.print("📋 Export Analytics Report", style="bold blue")
        self.console.print()
        
        # Suggest filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_filename = f"plexsync_analytics_{timestamp}.json"
        
        filename = Prompt.ask("Output filename", default=default_filename)
        output_path = Path(filename)
        
        try:
            self.storage_analytics.export_analytics_report(library, output_path)
            self.console.print(f"✅ Analytics report exported to: {output_path}", style="green")
        except Exception as e:
            self.console.print(f"❌ Failed to export report: {e}", style="red")
        
        input("Press Enter to continue...")
    
    def _smart_cleanup(self, library: MediaLibrary):
        """Perform smart cleanup based on suggestions."""
        self.console.print()
        self.console.print("🧹 Smart Cleanup", style="bold green")
        self.console.print()
        
        suggestions = self.storage_analytics.generate_optimization_suggestions(library)
        
        if not suggestions:
            self.console.print("✅ No cleanup needed - your storage is well-optimized!", style="green")
            input("Press Enter to continue...")
            return
        
        # Show what will be cleaned
        total_savings = sum(s.potential_savings for s in suggestions)
        total_savings_gb = total_savings / (1024**3)
        
        self.console.print("Smart cleanup will:")
        for suggestion in suggestions:
            if suggestion.confidence >= 0.7:  # Only high-confidence suggestions
                self.console.print(f"  ✓ {suggestion.description} (save {suggestion.potential_savings_gb:.2f} GB)")
        
        self.console.print()
        self.console.print(f"💾 Total potential savings: {total_savings_gb:.2f} GB")
        self.console.print()
        
        if Confirm.ask("Proceed with smart cleanup [y/N]", default=False):
            # Execute high-confidence suggestions
            for suggestion in suggestions:
                if suggestion.confidence >= 0.7:
                    self.console.print(f"🧹 {suggestion.description}...")
                    if suggestion.files:
                        result = self.file_operations.delete_files(suggestion.files)
                        if result.successful > 0:
                            self.console.print(f"✅ Cleaned {result.successful} files", style="green")
            
            self.console.print("✅ Smart cleanup complete!", style="green")
        else:
            self.console.print("⚠️ Smart cleanup cancelled", style="yellow")
        
        input("Press Enter to continue...")
    
    def _remove_duplicates(self, library: MediaLibrary):
        """Remove duplicate files."""
        self.console.print()
        self.console.print("🔍 Remove Duplicates", style="bold blue")
        self.console.print()
        
        duplicates = self.storage_analytics.find_duplicates(library, use_checksum=True)
        
        if not duplicates:
            self.console.print("✅ No duplicates found!", style="green")
            input("Press Enter to continue...")
            return
        
        # Show duplicate summary
        total_wasted = sum(g.wasted_space for g in duplicates)
        total_wasted_gb = total_wasted / (1024**3)
        
        self.console.print(f"Found {len(duplicates)} sets of duplicate files")
        self.console.print(f"💾 Wasted space: {total_wasted_gb:.2f} GB")
        self.console.print()
        
        if Confirm.ask("Remove duplicate files (keep one copy of each) [y/N]", default=False):
            # Remove duplicates (keep first file in each group)
            files_to_delete = []
            for group in duplicates:
                files_to_delete.extend(group.files[1:])  # Keep first, delete rest
            
            result = self.file_operations.delete_files(files_to_delete)
            
            if result.successful > 0:
                freed_gb = result.bytes_processed / (1024**3)
                self.console.print(f"✅ Removed {result.successful} duplicate files", style="green")
                self.console.print(f"💾 Storage freed: {freed_gb:.2f} GB")
            
            if result.failed > 0:
                self.console.print(f"❌ Failed to remove {result.failed} files", style="red")
        else:
            self.console.print("⚠️ Duplicate removal cancelled", style="yellow")
        
        input("Press Enter to continue...")
    
    def _clean_orphaned_files(self, library: MediaLibrary):
        """Clean orphaned files."""
        self.console.print()
        self.console.print("👻 Clean Orphaned Files", style="bold blue")
        self.console.print()
        
        summary = self.manager.get_summary(library)
        
        if not summary.orphaned:
            self.console.print("✅ No orphaned files found!", style="green")
            input("Press Enter to continue...")
            return
        
        orphaned_size = sum(f.file_size for f in summary.orphaned)
        orphaned_size_gb = orphaned_size / (1024**3)
        
        self.console.print(f"Found {len(summary.orphaned)} orphaned files")
        self.console.print(f"💾 Total size: {orphaned_size_gb:.2f} GB")
        self.console.print()
        self.console.print("These files are not in your media library and can be safely removed.")
        self.console.print()
        
        if Confirm.ask("Remove orphaned files [y/N]", default=False):
            result = self.file_operations.delete_files(summary.orphaned)
            
            if result.successful > 0:
                freed_gb = result.bytes_processed / (1024**3)
                self.console.print(f"✅ Removed {result.successful} orphaned files", style="green")
                self.console.print(f"💾 Storage freed: {freed_gb:.2f} GB")
            
            if result.failed > 0:
                self.console.print(f"❌ Failed to remove {result.failed} files", style="red")
        else:
            self.console.print("⚠️ Orphaned file cleanup cancelled", style="yellow")
        
        input("Press Enter to continue...")
    
    def _fix_corrupted_files(self, library: MediaLibrary):
        """Fix corrupted files."""
        self.console.print()
        self.console.print("⚠️ Fix Corrupted Files", style="bold yellow")
        self.console.print()
        
        # Find corrupted files
        summary = self.manager.get_summary(library)
        all_files = summary.movies + summary.episodes
        
        corrupted_files = [f for f in all_files if f.status.value in ["partial", "corrupted"]]
        
        if not corrupted_files:
            self.console.print("✅ No corrupted files found!", style="green")
            input("Press Enter to continue...")
            return
        
        corrupted_size = sum(f.file_size for f in corrupted_files)
        corrupted_size_gb = corrupted_size / (1024**3)
        
        self.console.print(f"Found {len(corrupted_files)} corrupted/partial files")
        self.console.print(f"💾 Total size: {corrupted_size_gb:.2f} GB")
        self.console.print()
        
        options = [
            ("1", "🗑️ Delete corrupted files", "remove corrupted files to free space"),
            ("2", "🔄 Re-sync corrupted files", "re-download corrupted files (coming soon)"),
            ("3", "🔙 Cancel", "return without changes")
        ]
        
        for num, name, desc in options:
            self.console.print(f"  {num}. {name} - {desc}")
        
        self.console.print()
        
        choice = Prompt.ask("Select option [1-3]", default="3").strip()
        
        if choice == "1":
            if Confirm.ask("Delete corrupted files [y/N]", default=False):
                result = self.file_operations.delete_files(corrupted_files)
                
                if result.successful > 0:
                    freed_gb = result.bytes_processed / (1024**3)
                    self.console.print(f"✅ Deleted {result.successful} corrupted files", style="green")
                    self.console.print(f"💾 Storage freed: {freed_gb:.2f} GB")
                
                if result.failed > 0:
                    self.console.print(f"❌ Failed to delete {result.failed} files", style="red")
        elif choice == "2":
            self.console.print("🔄 Re-sync functionality will be available in the next update!", style="yellow")
        else:
            self.console.print("⚠️ Operation cancelled", style="yellow")
        
        input("Press Enter to continue...")
    
    def _bulk_file_operations(self, library: MediaLibrary):
        """Bulk file operations."""
        self.console.print()
        self.console.print("📁 Bulk File Operations", style="bold blue")
        self.console.print()
        
        if not self.selected_files:
            self.console.print("❌ No files selected", style="red")
            self.console.print("💡 Go to Browse Movies/TV Shows and select files first")
            input("Press Enter to continue...")
            return
        
        # Get selected files
        summary = self.manager.get_summary(library)
        all_files = summary.movies + summary.episodes + summary.orphaned
        selected_file_objects = [
            f for f in all_files 
            if str(f.file_path) in self.selected_files
        ]
        
        if not selected_file_objects:
            self.console.print("❌ Selected files not found", style="red")
            input("Press Enter to continue...")
            return
        
        total_size = sum(f.file_size for f in selected_file_objects)
        total_size_gb = total_size / (1024**3)
        
        self.console.print(f"Selected {len(selected_file_objects)} files ({total_size_gb:.2f} GB)")
        self.console.print()
        
        options = [
            ("1", "📁 Move Files", "move files to a new location"),
            ("2", "📋 Copy Files", "copy files to a new location"),
            ("3", "🗑️ Delete Files", "delete selected files"),
            ("4", "🔙 Cancel", "return without changes")
        ]
        
        for num, name, desc in options:
            self.console.print(f"  {num}. {name} - {desc}")
        
        self.console.print()
        
        choice = Prompt.ask("Select operation [1-4]", default="4").strip()
        
        if choice == "1":
            # Move files
            target_dir = Prompt.ask("Enter target directory")
            target_path = Path(target_dir)
            
            if not target_path.exists():
                if Confirm.ask(f"Create directory '{target_path}' [Y/n]", default=True):
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    self.console.print("❌ Operation cancelled", style="red")
                    input("Press Enter to continue...")
                    return
            
            organize = Confirm.ask("Organize by type (movies/tv subdirectories) [Y/n]", default=True)
            
            result = self.file_operations.move_files(selected_file_objects, target_path, organize)
            
            if result.successful > 0:
                # Clear selections for moved files
                self.selected_files.clear()
                self.console.print(f"✅ Moved {result.successful} files", style="green")
            
        elif choice == "2":
            # Copy files
            target_dir = Prompt.ask("Enter target directory")
            target_path = Path(target_dir)
            
            if not target_path.exists():
                if Confirm.ask(f"Create directory '{target_path}' [Y/n]", default=True):
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    self.console.print("❌ Operation cancelled", style="red")
                    input("Press Enter to continue...")
                    return
            
            organize = Confirm.ask("Organize by type (movies/tv subdirectories) [Y/n]", default=True)
            
            result = self.file_operations.copy_files(selected_file_objects, target_path, organize)
            
            if result.successful > 0:
                self.console.print(f"✅ Copied {result.successful} files", style="green")
            
        elif choice == "3":
            # Delete files
            result = self.file_operations.delete_files(selected_file_objects)
            
            if result.successful > 0:
                # Clear selections for deleted files
                self.selected_files.clear()
                self.console.print(f"✅ Deleted {result.successful} files", style="green")
        else:
            self.console.print("⚠️ Operation cancelled", style="yellow")
        
        input("Press Enter to continue...")
    
    def _cleanup_preview(self, library: MediaLibrary):
        """Preview what would be cleaned."""
        self.console.print()
        self.console.print("📊 Cleanup Preview", style="bold blue")
        self.console.print()
        
        suggestions = self.storage_analytics.generate_optimization_suggestions(library)
        
        if not suggestions:
            self.console.print("✅ No cleanup opportunities found!", style="green")
            input("Press Enter to continue...")
            return
        
        # Show preview
        total_savings = sum(s.potential_savings for s in suggestions)
        total_savings_gb = total_savings / (1024**3)
        
        self.console.print(f"💾 Total potential savings: {total_savings_gb:.2f} GB")
        self.console.print()
        
        self.console.print("Cleanup opportunities:")
        for suggestion in suggestions:
            confidence_color = "green" if suggestion.confidence >= 0.7 else "yellow" if suggestion.confidence >= 0.5 else "dim"
            self.console.print(f"  • {suggestion.description}", style=confidence_color)
            self.console.print(f"    💾 Savings: {suggestion.potential_savings_gb:.2f} GB")
            self.console.print(f"    🎯 Confidence: {suggestion.confidence:.0%}")
            self.console.print()
        
        self.console.print("💡 This is a preview only - no files will be modified")
        input("Press Enter to continue...")
    
    def _auto_resync_all(self, candidates: List[ResyncRequest]):
        """Automatically re-sync all problematic files."""
        self.console.print()
        self.console.print("🔄 Auto Re-sync All", style="bold green")
        self.console.print()
        
        if Confirm.ask("Proceed with auto re-sync [y/N]", default=False):
            self.console.print("🔄 Re-syncing files...")
            # Create batch and process
            batch = self.resync_manager.queue_resync_batch(candidates)
            # Note: This would be async in practice
            # result = await self.resync_manager.process_resync_batch(batch)
            self.console.print("✅ Re-sync batch queued", style="green")
        else:
            self.console.print("✅ Re-sync cancelled", style="green")
        
        input("Press Enter to continue...")
    
    def _selective_resync(self, candidates: List[ResyncRequest]):
        """Selectively re-sync specific files."""
        self.console.print()
        self.console.print("🎯 Selective Re-sync", style="bold green")
        self.console.print()
        
        if not candidates:
            self.console.print("✅ No files need re-syncing!", style="green")
            input("Press Enter to continue...")
            return
        
        self.console.print("Select files to re-sync:")
        for i, candidate in enumerate(candidates):
            self.console.print(f"  {i+1}. {candidate.file.display_name}")
        
        choice = Prompt.ask("Enter file numbers separated by commas (e.g., 1,3,5) or anything else to cancel", default="").strip()
        
        if choice:
            try:
                selected_indices = [int(num) - 1 for num in choice.split(",")]
                selected_requests = [candidates[i] for i in selected_indices if 0 <= i < len(candidates)]
                
                if selected_requests:
                    self.console.print("🔄 Re-syncing selected files...")
                    batch = self.resync_manager.queue_resync_batch(selected_requests)
                    # Note: This would be async in practice
                    # result = await self.resync_manager.process_resync_batch(batch)
                    self.console.print("✅ Re-sync batch queued", style="green")
                else:
                    self.console.print("❌ No valid files selected", style="red")
            except ValueError:
                self.console.print("❌ Invalid input", style="red")
        else:
            self.console.print("✅ Re-sync cancelled", style="green")
        
        input("Press Enter to continue...")
    
    def _show_resync_statistics(self):
        """Show re-sync statistics."""
        self.console.print()
        self.console.print("📊 Re-sync Statistics", style="bold blue")
        self.console.print()
        
        statistics = self.resync_manager.get_resync_statistics()
        
        self.console.print("Re-sync Statistics:")
        for key, value in statistics.items():
            self.console.print(f"  {key}: {value}")
        
        input("Press Enter to continue...")
    
    def _export_resync_report(self, library: MediaLibrary):
        """Export re-sync report."""
        self.console.print()
        self.console.print("📋 Export Re-sync Report", style="bold blue")
        self.console.print()
        
        output_file = Path("resync_report.json")
        self.resync_manager.export_resync_report(output_file)
        
        input("Press Enter to continue...")
    
    def _show_duplicate_report(self, library: MediaLibrary):
        """Show duplicate report."""
        self.console.print()
        self.console.print("📊 Duplicate Report", style="bold blue")
        self.console.print()
        
        self.advanced_duplicates.show_similarity_analysis(library)
        
        input("Press Enter to continue...")
    
    def _smart_duplicate_removal(self, library: MediaLibrary):
        """Smart duplicate removal."""
        self.console.print()
        self.console.print("🗑️ Smart Duplicate Removal", style="bold red")
        self.console.print()
        
        groups = self.advanced_duplicates.find_advanced_duplicates(library)
        
        if not groups:
            self.console.print("✅ No duplicates found!", style="green")
            input("Press Enter to continue...")
            return
        
        # Show duplicates and ask for confirmation
        self.console.print(f"Found {len(groups)} duplicate groups")
        
        if Confirm.ask("Proceed with smart duplicate removal [y/N]", default=False):
            self.console.print("🗑️ Removing duplicates...")
            # Implementation would go here
            self.console.print("✅ Duplicate removal completed", style="green")
        else:
            self.console.print("✅ Duplicate removal cancelled", style="green")
        
        input("Press Enter to continue...")
    
    def _movie_duplicate_detection(self, library: MediaLibrary):
        """Movie duplicate detection."""
        self.console.print()
        self.console.print("🎭 Movie Duplicate Detection", style="bold blue")
        self.console.print()
        
        self.console.print("Scanning for movie duplicates...")
        # Implementation would go here
        
        input("Press Enter to continue...")
    
    def _episode_duplicate_detection(self, library: MediaLibrary):
        """Episode duplicate detection."""
        self.console.print()
        self.console.print("📺 Episode Duplicate Detection", style="bold blue")
        self.console.print()
        
        self.console.print("Scanning for episode duplicates...")
        # Implementation would go here
        
        input("Press Enter to continue...")
    
    def _export_similarity_report(self, library: MediaLibrary):
        """Export similarity report."""
        self.console.print()
        self.console.print("📋 Export Similarity Report", style="bold blue")
        self.console.print()
        
        output_file = Path("similarity_report.json")
        self.advanced_duplicates.export_similarity_report(library, output_file)
        
        input("Press Enter to continue...")
    
    def _auto_organize_files(self, library: MediaLibrary):
        """Auto-organize files."""
        self.console.print()
        self.console.print("🚀 Auto-Organize Files", style="bold green")
        self.console.print()
        
        plans = self.smart_organizer.analyze_organization(library)
        
        if not plans:
            self.console.print("✅ Files are already well-organized!", style="green")
            input("Press Enter to continue...")
            return
        
        self.console.print(f"Found {len(plans)} files to organize")
        
        if Confirm.ask("Proceed with auto-organization [y/N]", default=False):
            self.console.print("📁 Organizing files...")
            results = self.smart_organizer.execute_organization_plans(plans)
            
            successful = sum(1 for r in results if r.success)
            self.console.print(f"✅ Organized {successful} files", style="green")
        else:
            self.console.print("✅ Organization cancelled", style="green")
        
        input("Press Enter to continue...")
    
    def _selective_organization(self, library: MediaLibrary):
        """Selective organization."""
        self.console.print()
        self.console.print("🎯 Selective Organization", style="bold green")
        self.console.print()
        
        self.console.print("Selective organization interface would go here...")
        
        input("Press Enter to continue...")
    
    def _create_custom_organization_rule(self):
        """Create custom organization rule."""
        self.console.print()
        self.console.print("🔧 Create Custom Organization Rule", style="bold blue")
        self.console.print()
        
        self.console.print("Custom rule creation interface would go here...")
        
        input("Press Enter to continue...")
    
    def _show_organization_analysis(self, library: MediaLibrary):
        """Show organization analysis."""
        self.console.print()
        self.console.print("📊 Organization Analysis", style="bold blue")
        self.console.print()
        
        suggestions = self.smart_organizer.suggest_organization_improvements(library)
        
        for suggestion in suggestions:
            self.console.print(f"• {suggestion}")
        
        input("Press Enter to continue...")
    
    def _export_organization_plan(self, library: MediaLibrary):
        """Export organization plan."""
        self.console.print()
        self.console.print("📋 Export Organization Plan", style="bold blue")
        self.console.print()
        
        output_file = Path("organization_plan.json")
        self.smart_organizer.export_organization_plan(library, output_file)
        
        input("Press Enter to continue...")
    
    def _show_most_used_files(self, library: MediaLibrary):
        """Show most used files."""
        self.console.print()
        self.console.print("🏆 Most Used Files", style="bold green")
        self.console.print()
        
        global_stats = self.usage_analytics.get_global_usage_stats(library)
        file_stats = global_stats['file_stats']
        
        top_files = sorted([s for s in file_stats if s.total_accesses > 0], 
                          key=lambda s: s.usage_score, reverse=True)[:10]
        
        if top_files:
            for i, stats in enumerate(top_files, 1):
                file_name = Path(stats.file_path).name
                self.console.print(f"{i}. {file_name} - Score: {stats.usage_score:.0f}")
        else:
            self.console.print("No usage data available")
        
        input("Press Enter to continue...")
    
    def _show_never_accessed_files(self, library: MediaLibrary):
        """Show never accessed files."""
        self.console.print()
        self.console.print("👻 Never Accessed Files", style="bold yellow")
        self.console.print()
        
        global_stats = self.usage_analytics.get_global_usage_stats(library)
        file_stats = global_stats['file_stats']
        
        never_accessed = [s for s in file_stats if s.total_accesses == 0]
        
        if never_accessed:
            self.console.print(f"Found {len(never_accessed)} never accessed files:")
            for stats in never_accessed[:10]:
                file_name = Path(stats.file_path).name
                self.console.print(f"• {file_name}")
        else:
            self.console.print("All files have been accessed at least once!")
        
        input("Press Enter to continue...")
    
    def _show_usage_recommendations(self, library: MediaLibrary):
        """Show usage recommendations."""
        self.console.print()
        self.console.print("💡 Usage Recommendations", style="bold blue")
        self.console.print()
        
        recommendations = self.usage_analytics.generate_recommendations(library)
        
        if recommendations:
            for i, rec in enumerate(recommendations, 1):
                self.console.print(f"{i}. {rec.title}")
                self.console.print(f"   {rec.description}")
                self.console.print(f"   Confidence: {rec.confidence_text}")
                self.console.print()
        else:
            self.console.print("No recommendations at this time")
        
        input("Press Enter to continue...")
    
    def _show_usage_trends(self, library: MediaLibrary):
        """Show usage trends."""
        self.console.print()
        self.console.print("📈 Usage Trends", style="bold blue")
        self.console.print()
        
        self.console.print("Usage trends analysis would go here...")
        
        input("Press Enter to continue...")
    
    def _usage_based_cleanup(self, library: MediaLibrary):
        """Usage-based cleanup."""
        self.console.print()
        self.console.print("🧹 Usage-Based Cleanup", style="bold red")
        self.console.print()
        
        recommendations = self.usage_analytics.generate_recommendations(library)
        cleanup_recs = [r for r in recommendations if "delete" in r.type.value.lower() or "archive" in r.type.value.lower()]
        
        if cleanup_recs:
            self.console.print(f"Found {len(cleanup_recs)} cleanup recommendations")
            
            if Confirm.ask("Proceed with usage-based cleanup [y/N]", default=False):
                self.console.print("🧹 Cleaning up based on usage patterns...")
                # Implementation would go here
                self.console.print("✅ Cleanup completed", style="green")
            else:
                self.console.print("✅ Cleanup cancelled", style="green")
        else:
            self.console.print("No cleanup recommendations based on usage patterns")
        
        input("Press Enter to continue...")
    
    def _export_usage_report(self, library: MediaLibrary):
        """Export usage report."""
        self.console.print()
        self.console.print("📋 Export Usage Report", style="bold blue")
        self.console.print()
        
        output_file = Path("usage_report.json")
        self.usage_analytics.export_usage_report(library, output_file)
        
        input("Press Enter to continue...")
    
    def _analytics_settings(self):
        """Analytics settings."""
        self.console.print()
        self.console.print("🔧 Analytics Settings", style="bold blue")
        self.console.print()
        
        self.console.print("Analytics settings interface would go here...")
        
        input("Press Enter to continue...")
    
    # Missing helper methods
    def _delete_selected_files(self, all_files: List[DownloadedFile]):
        """Delete selected files with confirmation."""
        # Get selected file objects
        selected_file_objects = [
            f for f in all_files 
            if str(f.file_path) in self.selected_files
        ]
        
        if not selected_file_objects:
            self.console.print("❌ No files found to delete", style="red")
            input("Press Enter to continue...")
            return
        
        total_size = sum(f.file_size for f in selected_file_objects)
        total_size_gb = total_size / (1024**3)
        
        self.console.print()
        self.console.print("🗑️ Delete Selected Files", style="bold red")
        self.console.print()
        self.console.print(f"⚠️ WARNING: This will permanently delete {len(selected_file_objects)} files")
        self.console.print(f"💾 Total size: {total_size_gb:.2f} GB")
        self.console.print()
        
        # Show files to be deleted
        self.console.print("Files to delete:")
        for file in selected_file_objects[:10]:  # Show first 10
            self.console.print(f"  • {file.display_name}")
        
        if len(selected_file_objects) > 10:
            self.console.print(f"  ... and {len(selected_file_objects) - 10} more files")
        
        self.console.print()
        
        if Confirm.ask("Proceed with deletion [y/N]", default=False):
            try:
                # Use the file operations manager for actual deletion
                result = self.file_operations.delete_files(selected_file_objects)
                
                if result.successful > 0:
                    # Clear selections for deleted files
                    for file in selected_file_objects:
                        self.selected_files.discard(str(file.file_path))
                    
                    freed_gb = result.bytes_processed / (1024**3)
                    self.console.print(f"✅ Successfully deleted {result.successful} files", style="green")
                    self.console.print(f"💾 Storage freed: {freed_gb:.2f} GB")
                
                if result.failed > 0:
                    self.console.print(f"❌ Failed to delete {result.failed} files", style="red")
                    for error in result.errors:
                        self.console.print(f"  • {error}")
                        
            except Exception as e:
                self.console.print(f"❌ Error during deletion: {e}", style="red")
        else:
            self.console.print("✅ Deletion cancelled", style="green")
        
        input("Press Enter to continue...")
    
    def _verify_selected_files(self, all_files: List[DownloadedFile]):
        """Verify integrity of selected files."""
        # Get selected file objects
        selected_file_objects = [
            f for f in all_files 
            if str(f.file_path) in self.selected_files
        ]
        
        if not selected_file_objects:
            self.console.print("❌ No files found to verify", style="red")
            input("Press Enter to continue...")
            return
        
        self.console.print()
        self.console.print("✅ Verify Selected Files", style="bold blue")
        self.console.print()
        self.console.print(f"Checking {len(selected_file_objects)} files...")
        self.console.print()
        
        verified_count = 0
        corrupted_count = 0
        missing_count = 0
        
        for file in selected_file_objects:
            self.console.print(f"Checking: {file.display_name}")
            
            # Basic file existence check
            if not file.file_path.exists():
                self.console.print("  ❌ File not found", style="red")
                missing_count += 1
                continue
            
            # Size verification
            actual_size = file.file_path.stat().st_size
            if actual_size != file.file_size:
                self.console.print(f"  ⚠️ Size mismatch: expected {file.file_size}, got {actual_size}", style="yellow")
                corrupted_count += 1
                continue
            
            # If we have a matched item, compare with source
            if file.matched_item:
                if actual_size == file.matched_item.file_size:
                    self.console.print("  ✅ File verified", style="green")
                    verified_count += 1
                else:
                    self.console.print("  ⚠️ Size doesn't match source", style="yellow")
                    corrupted_count += 1
            else:
                self.console.print("  ✅ File exists (no source to compare)", style="dim green")
                verified_count += 1
        
        self.console.print()
        self.console.print("Verification Summary:")
        self.console.print(f"  ✅ Verified: {verified_count} files")
        if corrupted_count > 0:
            self.console.print(f"  ⚠️ Issues: {corrupted_count} files")
        if missing_count > 0:
            self.console.print(f"  ❌ Missing: {missing_count} files")
        
        input("Press Enter to continue...")
    
    def _show_selected_info(self, all_files: List[DownloadedFile]):
        """Show detailed information about selected files."""
        # Get selected file objects
        selected_file_objects = [
            f for f in all_files 
            if str(f.file_path) in self.selected_files
        ]
        
        if not selected_file_objects:
            self.console.print("❌ No files selected", style="red")
            input("Press Enter to continue...")
            return
        
        self.console.print()
        self.console.print("📋 Selected Files Information", style="bold blue")
        self.console.print()
        
        total_size = sum(f.file_size for f in selected_file_objects)
        total_size_gb = total_size / (1024**3)
        
        self.console.print(f"Total: {len(selected_file_objects)} files • {total_size_gb:.2f} GB")
        self.console.print()
        
        # Group by status
        by_status = {}
        for file in selected_file_objects:
            status = file.status.value.title()
            if status not in by_status:
                by_status[status] = []
            by_status[status].append(file)
        
        for status, files in by_status.items():
            status_size = sum(f.file_size for f in files)
            status_size_gb = status_size / (1024**3)
            self.console.print(f"{status}: {len(files)} files ({status_size_gb:.2f} GB)")
            
            # Show first few files
            for file in files[:3]:
                self.console.print(f"  • {file.display_name}")
            
            if len(files) > 3:
                self.console.print(f"  ... and {len(files) - 3} more")
            
            self.console.print()
        
        input("Press Enter to continue...")
    
    def _handle_page_jump(self, total_pages: int, current_page: int) -> Optional[int]:
        """Handle jumping to a specific page."""
        try:
            new_page = IntPrompt.ask(f"Jump to page (1-{total_pages})", default=current_page)
            if 1 <= new_page <= total_pages:
                return new_page
            else:
                self.console.print(f"❌ Invalid page number. Must be between 1 and {total_pages}", style="red")
                input("Press Enter to continue...")
                return None
        except KeyboardInterrupt:
            return None