"""
Setup wizard for PlexSync first-time configuration.

This module provides an interactive setup wizard that guides new users through
the initial configuration process, including mount point detection, path
selection, destination setup, and test sync validation.
"""

import os
import sys
import time
import tempfile
import hashlib
from typing import Optional, List, Dict, Tuple
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskID
from rich.text import Text
from rich.align import Align

from .config import get_config_manager, ProfileConfig, MediaSourceConfig, DestinationConfig
from .mount import get_mount_manager, MountPoint, MountStatus, MountType
from .environment import validate_environment, CheckStatus


class SetupWizardError(Exception):
    """Custom exception for setup wizard errors."""
    pass


class SetupWizard:
    """Interactive setup wizard for PlexSync first-time configuration."""
    
    def __init__(self, console: Optional[Console] = None, verbose: bool = False):
        """Initialize the setup wizard.
        
        Args:
            console: Rich console instance for output
            verbose: Enable verbose logging
        """
        self.console = console or Console()
        self.verbose = verbose
        self.config_manager = get_config_manager()
        self.mount_manager = get_mount_manager()
        
        # In-memory configuration being built
        self.temp_config: Optional[ProfileConfig] = None
        self.selected_sources: List[MediaSourceConfig] = []
        self.destination_config: Optional[DestinationConfig] = None
        
    def run(self) -> bool:
        """Run the complete setup wizard flow.
        
        Returns:
            True if setup completed successfully, False otherwise
        """
        try:
            self._show_welcome()
            
            # Check for existing configuration
            if not self._check_existing_configuration():
                return False
            
            # Step 1: Environment validation
            if not self._validate_environment():
                return False
            
            # Step 2: Mount detection and source selection
            if not self._detect_and_select_sources():
                return False
            
            # Step 3: Destination setup
            if not self._setup_destination():
                return False
            
            # Step 4: Test sync and finalize configuration
            if not self._test_sync_and_finalize():
                return False
            
            self._show_success_message()
            return True
            
        except KeyboardInterrupt:
            self.console.print("\n❌ Setup wizard cancelled by user", style="bold red")
            self.console.print("   No configuration changes have been made.")
            return False
        except Exception as e:
            self.console.print(f"\n❌ Setup wizard failed: {e}", style="bold red")
            if self.verbose:
                import traceback
                self.console.print(traceback.format_exc())
            return False
    
    def _show_welcome(self):
        """Display the welcome screen."""
        welcome_text = """
Welcome to the PlexSync Setup Wizard!

This wizard will help you configure PlexSync for first-time use. The process
involves four simple steps:

1. Environment validation
2. Media source detection and selection
3. Destination directory setup
4. Configuration test and finalization

The entire process should take less than 5 minutes.
        """.strip()
        
        panel = Panel(
            welcome_text,
            title="[bold blue]PlexSync Setup Wizard[/bold blue]",
            border_style="blue",
            padding=(1, 2)
        )
        
        self.console.print(panel)
        self.console.print()
        
        # Prompt to continue
        if not Confirm.ask("Ready to begin setup?", default=True):
            raise KeyboardInterrupt("User chose not to continue")
    
    def _check_existing_configuration(self) -> bool:
        """Check if configuration already exists and handle accordingly.
        
        Returns:
            True to continue setup, False to exit
        """
        config_file = self.config_manager.config_file
        
        if os.path.exists(config_file):
            self.console.print("⚠️  Existing Configuration Found", style="bold yellow")
            self.console.print(f"   Configuration file: {config_file}")
            self.console.print()
            
            overwrite = Confirm.ask(
                "An existing configuration was found. Would you like to overwrite it?",
                default=False
            )
            
            if not overwrite:
                self.console.print("Setup wizard cancelled.", style="yellow")
                self.console.print("Use 'plexsync config --show' to view your current configuration.")
                return False
        
        return True
    
    def _validate_environment(self) -> bool:
        """Validate the system environment.
        
        Returns:
            True if environment is ready, False otherwise
        """
        self.console.print("📋 [bold cyan]Step 1/4: Environment Validation[/bold cyan]")
        self.console.print()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            task = progress.add_task("Validating system environment...", total=None)
            env_report = validate_environment()
            progress.update(task, completed=100)
        
        # Show critical failures
        critical_failures = [
            check for check in env_report.checks 
            if check.status == CheckStatus.FAIL and check.required
        ]
        
        if critical_failures:
            self.console.print("❌ Critical Environment Issues Found:", style="bold red")
            for check in critical_failures:
                self.console.print(f"   • {check.name}: {check.message}", style="red")
                if check.fix_suggestion:
                    self.console.print(f"     Fix: {check.fix_suggestion}", style="dim")
            self.console.print()
            self.console.print("Please resolve these issues before running the setup wizard again.")
            return False
        
        # Show warnings
        warnings = [check for check in env_report.checks if check.status == CheckStatus.WARN]
        if warnings:
            self.console.print("⚠️  Environment Warnings:", style="bold yellow")
            for check in warnings:
                self.console.print(f"   • {check.name}: {check.message}", style="yellow")
            self.console.print()
            
            continue_with_warnings = Confirm.ask(
                "Continue setup with warnings?", 
                default=True
            )
            if not continue_with_warnings:
                return False
        
        self.console.print("✅ Environment validation completed", style="bold green")
        self.console.print()
        return True
    
    def _detect_and_select_sources(self) -> bool:
        """Detect mount points and allow user to select media sources.
        
        Returns:
            True if sources were selected, False otherwise
        """
        self.console.print("📂 [bold cyan]Step 2/4: Media Source Detection[/bold cyan]")
        self.console.print()
        
        # Discover mount points
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            task = progress.add_task("Discovering mount points...", total=None)
            discovered_mounts = self.mount_manager.discover_mounts()
            progress.update(task, completed=100)
        
        # Filter for potential media mount points
        media_mounts = self._filter_media_mounts(discovered_mounts)
        
        if not media_mounts:
            self.console.print("⚠️  No common media mount points detected", style="bold yellow")
            return self._handle_manual_path_entry()
        
        # Display discovered mount points
        self._display_mount_points_table(media_mounts)
        
        # Allow user to select sources
        return self._select_media_sources(media_mounts)
    
    def _filter_media_mounts(self, mounts: List[MountPoint]) -> List[MountPoint]:
        """Filter mount points for potential media sources.
        
        Args:
            mounts: List of all discovered mount points
            
        Returns:
            List of mount points that could contain media
        """
        media_paths = ['/mnt/media', '/media', '/mount', '/mnt']
        media_mounts = []
        
        for mount in mounts:
            # Check if mount path starts with common media prefixes
            if any(mount.path.startswith(prefix) for prefix in media_paths):
                media_mounts.append(mount)
            # Also include mounts that contain media-like subdirectories
            elif self._has_media_subdirectories(mount.path):
                media_mounts.append(mount)
        
        return media_mounts
    
    def _has_media_subdirectories(self, path: str) -> bool:
        """Check if a path contains media-like subdirectories.
        
        Args:
            path: Path to check
            
        Returns:
            True if path contains media-like subdirectories
        """
        if not os.path.exists(path) or not os.access(path, os.R_OK):
            return False
        
        try:
            subdirs = [d for d in os.listdir(path) 
                      if os.path.isdir(os.path.join(path, d))]
            
            media_keywords = ['movie', 'tv', 'film', 'video', 'media', 'shows', 'series']
            
            for subdir in subdirs:
                if any(keyword in subdir.lower() for keyword in media_keywords):
                    return True
        except (OSError, PermissionError):
            pass
        
        return False
    
    def _display_mount_points_table(self, mounts: List[MountPoint]):
        """Display discovered mount points in a table.
        
        Args:
            mounts: List of mount points to display
        """
        table = Table(title="Discovered Media Mount Points", show_header=True, header_style="bold magenta")
        table.add_column("#", style="dim", width=3)
        table.add_column("Path", style="cyan", width=40)
        table.add_column("Type", width=10)
        table.add_column("Status", width=12)
        table.add_column("Response", width=10)
        
        for i, mount in enumerate(mounts, 1):
            # Status styling
            if mount.status == MountStatus.HEALTHY:
                status_text = "[green]✅ HEALTHY[/green]"
            elif mount.status == MountStatus.DEGRADED:
                status_text = "[yellow]⚠️  DEGRADED[/yellow]"
            else:
                status_text = "[red]❌ UNAVAIL[/red]"
            
            # Response time
            response = ""
            if mount.response_time_ms:
                response = f"{mount.response_time_ms:.1f}ms"
            
            table.add_row(
                str(i),
                mount.path,
                mount.mount_type.value.upper(),
                status_text,
                response
            )
        
        self.console.print(table)
        self.console.print()
    
    def _select_media_sources(self, mounts: List[MountPoint]) -> bool:
        """Allow user to select media sources from discovered mounts.
        
        Args:
            mounts: List of available mount points
            
        Returns:
            True if sources were selected, False otherwise
        """
        self.console.print("📝 [bold cyan]Select Media Sources[/bold cyan]")
        self.console.print("   Choose which mount points contain your media files.")
        self.console.print()
        
        selected_indices = []
        
        # Allow multiple selections
        while True:
            self.console.print("Available options:")
            for i, mount in enumerate(mounts, 1):
                selected_marker = "✅" if (i-1) in selected_indices else "  "
                status_color = "green" if mount.status == MountStatus.HEALTHY else "yellow"
                self.console.print(f"   {selected_marker} {i}. {mount.path} [{status_color}]{mount.status.value.upper()}[/{status_color}]")
            
            self.console.print(f"   🔧 {len(mounts) + 1}. Add custom path")
            self.console.print(f"   ✅ {len(mounts) + 2}. Finish selection")
            self.console.print()
            
            try:
                choice = Prompt.ask(
                    "Select an option",
                    choices=[str(i) for i in range(1, len(mounts) + 3)],
                    show_choices=False
                )
                
                choice_num = int(choice)
                
                if choice_num <= len(mounts):
                    # Toggle mount selection
                    mount_index = choice_num - 1
                    if mount_index in selected_indices:
                        selected_indices.remove(mount_index)
                        self.console.print(f"   Removed: {mounts[mount_index].path}", style="yellow")
                    else:
                        # Validate the mount before adding
                        mount = mounts[mount_index]
                        if self._validate_media_path(mount.path):
                            selected_indices.append(mount_index)
                            self.console.print(f"   Added: {mount.path}", style="green")
                        else:
                            self.console.print(f"   ❌ Path validation failed for: {mount.path}", style="red")
                            continue_anyway = Confirm.ask("Add this path anyway?", default=False)
                            if continue_anyway:
                                selected_indices.append(mount_index)
                                self.console.print(f"   Added: {mount.path} (validation bypassed)", style="yellow")
                
                elif choice_num == len(mounts) + 1:
                    # Add custom path
                    if self._handle_custom_path_entry():
                        pass  # Custom path was added to selected_sources
                    
                elif choice_num == len(mounts) + 2:
                    # Finish selection
                    break
                    
            except (ValueError, KeyboardInterrupt):
                self.console.print("   Invalid selection, please try again.", style="red")
                continue
            
            self.console.print()
        
        # Convert selected indices to MediaSourceConfig objects
        for index in selected_indices:
            mount = mounts[index]
            media_type = self._detect_media_type(mount.path)
            
            source_config = MediaSourceConfig(
                name=self._generate_source_name(mount.path, media_type),
                base_path=mount.path,
                media_type=media_type,
                enabled=True
            )
            self.selected_sources.append(source_config)
        
        if not self.selected_sources:
            self.console.print("❌ No media sources selected", style="red")
            return False
        
        # Show summary
        self.console.print("✅ Selected Media Sources:", style="bold green")
        for source in self.selected_sources:
            self.console.print(f"   • {source.name}: {source.base_path} ({source.media_type})")
        self.console.print()
        
        return True
    
    def _validate_media_path(self, path: str) -> bool:
        """Validate that a path is suitable for media storage.
        
        Args:
            path: Path to validate
            
        Returns:
            True if path is valid for media storage
        """
        try:
            # Check if path exists and is readable
            if not os.path.exists(path):
                return False
            
            if not os.access(path, os.R_OK):
                return False
            
            # Check if path has reasonable free space (at least 1GB)
            import shutil
            free_bytes = shutil.disk_usage(path).free
            if free_bytes < 1024**3:  # 1GB
                self.console.print(f"   ⚠️  Low disk space: {free_bytes / 1024**3:.1f}GB free", style="yellow")
            
            return True
            
        except (OSError, PermissionError):
            return False
    
    def _detect_media_type(self, path: str) -> str:
        """Detect the likely media type based on path.
        
        Args:
            path: Path to analyze
            
        Returns:
            "movie" or "tv_show" based on path analysis
        """
        path_lower = path.lower()
        
        # Check for TV-related keywords
        tv_keywords = ['tv', 'television', 'series', 'shows', 'episodes']
        if any(keyword in path_lower for keyword in tv_keywords):
            return "tv_show"
        
        # Check for movie-related keywords
        movie_keywords = ['movie', 'film', 'cinema', 'flick']
        if any(keyword in path_lower for keyword in movie_keywords):
            return "movie"
        
        # Default to movie if unclear
        return "movie"
    
    def _generate_source_name(self, path: str, media_type: str) -> str:
        """Generate a descriptive name for a media source.
        
        Args:
            path: Source path
            media_type: Type of media ("movie" or "tv_show")
            
        Returns:
            Generated source name
        """
        # Extract the last meaningful part of the path
        path_parts = path.rstrip('/').split('/')
        
        for part in reversed(path_parts):
            if part and part not in ['mnt', 'media', 'mount']:
                if media_type == "tv_show":
                    return f"TV Shows ({part})"
                else:
                    return f"Movies ({part})"
        
        # Fallback names
        return "TV Shows" if media_type == "tv_show" else "Movies"
    
    def _handle_custom_path_entry(self) -> bool:
        """Handle manual entry of a custom media path.
        
        Returns:
            True if custom path was added successfully
        """
        self.console.print("🔧 [bold cyan]Add Custom Media Path[/bold cyan]")
        self.console.print("   Enter the full path to your media directory.")
        self.console.print()
        
        while True:
            try:
                custom_path = Prompt.ask("Media path", default="")
                
                if not custom_path:
                    return False
                
                # Expand path
                custom_path = os.path.expanduser(custom_path)
                custom_path = os.path.abspath(custom_path)
                
                # Validate path
                if not os.path.exists(custom_path):
                    self.console.print(f"   ❌ Path does not exist: {custom_path}", style="red")
                    if not Confirm.ask("Try a different path?", default=True):
                        return False
                    continue
                
                if not os.access(custom_path, os.R_OK):
                    self.console.print(f"   ❌ Path is not readable: {custom_path}", style="red")
                    if not Confirm.ask("Try a different path?", default=True):
                        return False
                    continue
                
                # Detect media type
                media_type = self._detect_media_type(custom_path)
                type_confirm = Confirm.ask(f"Is this a {media_type} directory?", default=True)
                
                if not type_confirm:
                    media_type = "tv_show" if media_type == "movie" else "movie"
                
                # Create source config
                source_config = MediaSourceConfig(
                    name=self._generate_source_name(custom_path, media_type),
                    base_path=custom_path,
                    media_type=media_type,
                    enabled=True
                )
                
                self.selected_sources.append(source_config)
                self.console.print(f"   ✅ Added: {source_config.name} -> {custom_path}", style="green")
                return True
                
            except KeyboardInterrupt:
                return False
    
    def _handle_manual_path_entry(self) -> bool:
        """Handle manual path entry when no mounts are detected.
        
        Returns:
            True if valid path was entered, False otherwise
        """
        self.console.print("🔧 Manual Path Entry", style="bold yellow")
        self.console.print("   Please enter the path to your media directory manually.")
        self.console.print()
        
        # TODO: Implement manual path entry
        self.console.print("📝 Manual path entry will be implemented in Phase 2")
        return False
    
    def _setup_destination(self) -> bool:
        """Set up the destination directory.
        
        Returns:
            True if destination was set up successfully, False otherwise
        """
        self.console.print("🏠 [bold cyan]Step 3/4: Destination Setup[/bold cyan]")
        self.console.print("   Configure where your synced media will be stored.")
        self.console.print()
        
        # Default destinations
        default_base = os.path.expanduser("~/PlexSync")
        default_movies = os.path.join(default_base, "Movies")
        default_tv = os.path.join(default_base, "TV")
        
        self.console.print(f"📁 Default destination structure:")
        self.console.print(f"   Movies: {default_movies}")
        self.console.print(f"   TV Shows: {default_tv}")
        self.console.print()
        
        use_default = Confirm.ask("Use default destination paths?", default=True)
        
        if use_default:
            movies_dest = default_movies
            tv_dest = default_tv
        else:
            # Custom destination setup
            self.console.print("🔧 [bold cyan]Custom Destination Setup[/bold cyan]")
            
            # Movies destination
            movies_dest = Prompt.ask(
                "Movies destination path",
                default=default_movies
            )
            movies_dest = os.path.expanduser(movies_dest)
            movies_dest = os.path.abspath(movies_dest)
            
            # TV destination
            tv_dest = Prompt.ask(
                "TV shows destination path", 
                default=default_tv
            )
            tv_dest = os.path.expanduser(tv_dest)
            tv_dest = os.path.abspath(tv_dest)
        
        # Validate destinations don't conflict with sources
        if not self._validate_destination_paths(movies_dest, tv_dest):
            return False
        
        # Create directories if they don't exist
        if not self._create_destination_directories(movies_dest, tv_dest):
            return False
        
        # Check available space
        self._check_destination_space(movies_dest, tv_dest)
        
        # Create destination configuration
        self.destination_config = DestinationConfig(
            movies=movies_dest,
            tv=tv_dest,
            create_directories=True,
            preserve_permissions=True
        )
        
        self.console.print("✅ Destination setup completed:", style="bold green")
        self.console.print(f"   Movies: {movies_dest}")
        self.console.print(f"   TV Shows: {tv_dest}")
        self.console.print()
        
        return True
    
    def _validate_destination_paths(self, movies_dest: str, tv_dest: str) -> bool:
        """Validate destination paths don't conflict with source paths.
        
        Args:
            movies_dest: Movies destination path
            tv_dest: TV shows destination path
            
        Returns:
            True if paths are valid, False otherwise
        """
        destinations = [movies_dest, tv_dest]
        
        for dest in destinations:
            for source in self.selected_sources:
                # Check if destination is inside a source path
                if dest.startswith(source.base_path):
                    self.console.print(
                        f"❌ Destination path conflicts with source: {dest} overlaps with {source.base_path}",
                        style="red"
                    )
                    return False
                
                # Check if source is inside destination path
                if source.base_path.startswith(dest):
                    self.console.print(
                        f"❌ Source path conflicts with destination: {source.base_path} overlaps with {dest}",
                        style="red"
                    )
                    return False
        
        return True
    
    def _create_destination_directories(self, movies_dest: str, tv_dest: str) -> bool:
        """Create destination directories with proper permissions.
        
        Args:
            movies_dest: Movies destination path
            tv_dest: TV shows destination path
            
        Returns:
            True if directories were created successfully, False otherwise
        """
        destinations = [movies_dest, tv_dest]
        
        for dest in destinations:
            try:
                if not os.path.exists(dest):
                    self.console.print(f"   Creating directory: {dest}")
                    os.makedirs(dest, mode=0o755, exist_ok=True)
                
                # Check write permissions
                if not os.access(dest, os.W_OK):
                    self.console.print(
                        f"❌ Cannot write to destination: {dest}",
                        style="red"
                    )
                    
                    # Suggest fix
                    import getpass
                    username = getpass.getuser()
                    self.console.print(
                        f"   Try: sudo chown -R {username}:{username} {dest}",
                        style="dim"
                    )
                    return False
                
                self.console.print(f"   ✅ Directory ready: {dest}", style="green")
                
            except PermissionError:
                self.console.print(
                    f"❌ Permission denied creating: {dest}",
                    style="red"
                )
                return False
            except OSError as e:
                self.console.print(
                    f"❌ Error creating directory {dest}: {e}",
                    style="red"
                )
                return False
        
        return True
    
    def _check_destination_space(self, movies_dest: str, tv_dest: str):
        """Check available space at destination paths.
        
        Args:
            movies_dest: Movies destination path
            tv_dest: TV shows destination path
        """
        import shutil
        
        destinations = [movies_dest, tv_dest]
        
        for dest in destinations:
            try:
                usage = shutil.disk_usage(dest)
                free_gb = usage.free / (1024**3)
                total_gb = usage.total / (1024**3)
                
                if free_gb < 10:  # Less than 10GB
                    self.console.print(
                        f"⚠️  Low disk space at {dest}: {free_gb:.1f}GB free of {total_gb:.1f}GB total",
                        style="yellow"
                    )
                else:
                    self.console.print(
                        f"💾 Disk space at {dest}: {free_gb:.1f}GB free of {total_gb:.1f}GB total",
                        style="dim"
                    )
                    
            except OSError:
                self.console.print(
                    f"⚠️  Could not check disk space for: {dest}",
                    style="yellow"
                )
    
    def _test_sync_and_finalize(self) -> bool:
        """Perform test sync and finalize configuration.
        
        Returns:
            True if test sync succeeded and config was saved, False otherwise
        """
        self.console.print("🧪 [bold cyan]Step 4/4: Test Sync & Configuration[/bold cyan]")
        self.console.print("   Performing a test sync to validate your configuration.")
        self.console.print()
        
        # Create in-memory configuration first
        if not self._build_configuration():
            return False
        
        # Show configuration summary
        self._show_configuration_summary()
        
        # Confirm before test
        proceed_with_test = Confirm.ask("Proceed with test sync?", default=True)
        if not proceed_with_test:
            self.console.print("Test sync cancelled.", style="yellow")
            return False
        
        # Perform test sync
        if not self._perform_test_sync():
            return False
        
        # Save configuration atomically
        if not self._save_configuration():
            return False
        
        self.console.print("✅ Configuration validation completed", style="bold green")
        return True
    
    def _build_configuration(self) -> bool:
        """Build complete configuration in memory.
        
        Returns:
            True if configuration was built successfully, False otherwise
        """
        try:
            # Create profile configuration
            self.temp_config = ProfileConfig(
                name="setup-wizard",
                sources=self.selected_sources,
                destinations=self.destination_config
            )
            
            # Validate configuration
            validation_errors = self.temp_config.validate()
            if validation_errors:
                self.console.print("❌ Configuration validation failed:", style="red")
                for error in validation_errors:
                    self.console.print(f"   • {error}", style="red")
                return False
            
            return True
            
        except Exception as e:
            self.console.print(f"❌ Error building configuration: {e}", style="red")
            return False
    
    def _show_configuration_summary(self):
        """Display a summary of the configuration to be created."""
        self.console.print("📋 [bold cyan]Configuration Summary[/bold cyan]")
        self.console.print()
        
        # Show sources
        self.console.print("📂 [bold]Media Sources:[/bold]")
        for source in self.selected_sources:
            self.console.print(f"   • {source.name}")
            self.console.print(f"     Path: {source.base_path}")
            self.console.print(f"     Type: {source.media_type}")
            self.console.print()
        
        # Show destinations
        self.console.print("🏠 [bold]Destinations:[/bold]")
        self.console.print(f"   • Movies: {self.destination_config.movies}")
        self.console.print(f"   • TV Shows: {self.destination_config.tv}")
        self.console.print()
    
    def _perform_test_sync(self) -> bool:
        """Perform a test sync with a temporary file.
        
        Returns:
            True if test sync succeeded, False otherwise
        """
        self.console.print("🔄 [bold cyan]Performing Test Sync[/bold cyan]")
        
        # Choose first source for test
        test_source = self.selected_sources[0]
        test_destination = (
            self.destination_config.movies if test_source.media_type == "movie" 
            else self.destination_config.tv
        )
        
        test_file_path = None
        test_dest_path = None
        
        try:
            # Create temporary test file
            test_file_path = self._create_test_file(test_source.base_path)
            if not test_file_path:
                return False
            
            # Perform the sync
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                BarColumn(),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                console=self.console
            ) as progress:
                
                task = progress.add_task("Syncing test file...", total=100)
                
                # Simulate sync process (in real implementation, use actual sync engine)
                for i in range(0, 101, 10):
                    time.sleep(0.1)  # Simulate work
                    progress.update(task, completed=i)
                
                # Copy test file to destination
                import shutil
                test_dest_path = os.path.join(test_destination, os.path.basename(test_file_path))
                shutil.copy2(test_file_path, test_dest_path)
                
                progress.update(task, completed=100)
            
            # Verify test sync
            if not self._verify_test_sync(test_file_path, test_dest_path):
                return False
            
            self.console.print("✅ Test sync completed successfully!", style="bold green")
            return True
            
        except Exception as e:
            self.console.print(f"❌ Test sync failed: {e}", style="red")
            return False
            
        finally:
            # Clean up test files
            self._cleanup_test_files(test_file_path, test_dest_path)
    
    def _create_test_file(self, source_path: str) -> Optional[str]:
        """Create a temporary test file in the source directory.
        
        Args:
            source_path: Source directory path
            
        Returns:
            Path to created test file, or None if failed
        """
        try:
            test_filename = f"plexsync_test_{int(time.time())}.tmp"
            test_file_path = os.path.join(source_path, test_filename)
            
            # Create test content with checksum
            test_content = f"""PlexSync Test File
Created: {time.strftime('%Y-%m-%d %H:%M:%S')}
Source: {source_path}
Wizard Version: 1.0
"""
            
            with open(test_file_path, 'w', encoding='utf-8') as f:
                f.write(test_content)
            
            self.console.print(f"   Created test file: {test_file_path}", style="dim")
            return test_file_path
            
        except Exception as e:
            self.console.print(f"❌ Failed to create test file: {e}", style="red")
            return None
    
    def _verify_test_sync(self, source_path: str, dest_path: str) -> bool:
        """Verify the test sync completed correctly.
        
        Args:
            source_path: Source file path
            dest_path: Destination file path
            
        Returns:
            True if verification passed, False otherwise
        """
        try:
            # Check if destination file exists
            if not os.path.exists(dest_path):
                self.console.print("❌ Test file not found at destination", style="red")
                return False
            
            # Compare file sizes
            source_size = os.path.getsize(source_path)
            dest_size = os.path.getsize(dest_path)
            
            if source_size != dest_size:
                self.console.print(
                    f"❌ File size mismatch: source={source_size}, dest={dest_size}", 
                    style="red"
                )
                return False
            
            # Compare file contents
            with open(source_path, 'rb') as f1, open(dest_path, 'rb') as f2:
                source_hash = hashlib.sha256(f1.read()).hexdigest()
                dest_hash = hashlib.sha256(f2.read()).hexdigest()
            
            if source_hash != dest_hash:
                self.console.print("❌ File content mismatch (checksum failed)", style="red")
                return False
            
            self.console.print("✅ Test file verification passed", style="green")
            return True
            
        except Exception as e:
            self.console.print(f"❌ Test verification failed: {e}", style="red")
            return False
    
    def _cleanup_test_files(self, source_path: Optional[str], dest_path: Optional[str]):
        """Clean up temporary test files.
        
        Args:
            source_path: Source test file path (may be None)
            dest_path: Destination test file path (may be None)
        """
        files_to_remove = [f for f in [source_path, dest_path] if f and os.path.exists(f)]
        
        for file_path in files_to_remove:
            try:
                os.remove(file_path)
                if self.verbose:
                    self.console.print(f"   Cleaned up: {file_path}", style="dim")
            except Exception as e:
                if self.verbose:
                    self.console.print(f"   Warning: Could not remove {file_path}: {e}", style="yellow")
    
    def _save_configuration(self) -> bool:
        """Save the configuration atomically.
        
        Returns:
            True if configuration was saved successfully, False otherwise  
        """
        self.console.print("💾 [bold cyan]Saving Configuration[/bold cyan]")
        
        try:
            # Add the profile to config manager
            self.config_manager.profiles["default"] = self.temp_config
            self.config_manager.active_profile_name = "default"
            
            # Save configuration to disk
            if self.config_manager.save_config():
                self.console.print("✅ Configuration saved successfully", style="green")
                return True
            else:
                self.console.print("❌ Failed to save configuration", style="red")
                return False
                
        except Exception as e:
            self.console.print(f"❌ Error saving configuration: {e}", style="red")
            return False
    
    def _show_success_message(self):
        """Display success message after completed setup."""
        success_text = """
Setup completed successfully!

Your PlexSync configuration has been created and validated. You can now:

• Run 'plexsync' to start the interactive sync interface
• Run 'plexsync discover' to scan your media sources
• Run 'plexsync config --show' to view your configuration
• Run 'plexsync --help' to see all available commands

Happy syncing!
        """.strip()
        
        panel = Panel(
            success_text,
            title="[bold green]Setup Complete[/bold green]",
            border_style="green",
            padding=(1, 2)
        )
        
        self.console.print(panel)