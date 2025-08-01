"""
Quick Start Manager for PlexSync.

This module provides the simplified, 3-step quick start experience that gets
users syncing media in under 2 minutes with minimal configuration overhead.
"""

import os
import sys
import time
import logging
from typing import Optional, List, Dict, Any
from pathlib import Path
from dataclasses import dataclass

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.text import Text
from rich.align import Align

from .media_finder import get_media_finder, MediaCandidate, MediaType
from .settings_manager import get_settings_manager, QuickStartPreferences
from .config import get_config_manager, ProfileConfig, MediaSourceConfig, DestinationConfig
from .mount import get_mount_manager


logger = logging.getLogger(__name__)


class QuickStartError(Exception):
    """Base exception for quick start failures."""
    pass


class AutoDetectionFailure(QuickStartError):
    """When media auto-detection finds no viable sources."""
    pass


class ConnectionFailure(QuickStartError):
    """When Plex server connection fails."""
    pass


@dataclass
class QuickStartSession:
    """Represents a quick start session with selected options."""
    source_path: Optional[Path] = None
    destination_path: Optional[Path] = None
    media_type: Optional[MediaType] = None
    skip_plex: bool = False
    start_time: Optional[float] = None
    
    def get_duration(self) -> float:
        """Get session duration in seconds."""
        if self.start_time:
            return time.time() - self.start_time
        return 0.0


class QuickStartManager:
    """Manages the simplified quick start experience."""
    
    def __init__(self, console: Optional[Console] = None, verbose: bool = False):
        """Initialize QuickStartManager.
        
        Args:
            console: Rich console instance for output
            verbose: Enable verbose logging
        """
        self.console = console or Console()
        self.verbose = verbose
        self.settings_manager = get_settings_manager()
        self.config_manager = get_config_manager()
        self.mount_manager = get_mount_manager()
        self.media_finder = get_media_finder(console=self.console)
        
        # Load user preferences
        self.settings_manager.load_settings()
        self.preferences = self.settings_manager.settings.quick_start
        
        # Session tracking
        self.session = QuickStartSession(start_time=time.time())
        
    def run(self) -> bool:
        """Execute the complete quick start process.
        
        Returns:
            True if sync was initiated successfully, False if fallback needed
        """
        try:
            self._show_welcome()
            
            # Step 1: Source Selection (Decision 1)
            if not self._select_media_source():
                return self._fallback_to_setup_wizard("source selection failed")
            
            # Step 2: Destination Selection (Decision 2) 
            if not self._select_destination():
                return self._fallback_to_setup_wizard("destination selection failed")
            
            # Step 3: Plex Connection Validation (Decision 3 if needed)
            if not self._validate_plex_connection():
                return self._fallback_to_setup_wizard("Plex validation failed")
            
            # Execute sync with minimal configuration
            return self._execute_quick_sync()
            
        except KeyboardInterrupt:
            self.console.print("\\n[yellow]Quick start cancelled by user[/yellow]")
            return False
        except Exception as e:
            logger.error(f"Quick start failed with error: {e}")
            if self.verbose:
                import traceback
                self.console.print(f"[red]Error details:[/red]\\n{traceback.format_exc()}")
            return self._fallback_to_setup_wizard(f"unexpected error: {e}")
    
    def _show_welcome(self):
        """Display the quick start welcome message."""
        welcome_text = Text()
        welcome_text.append("PlexSync Quick Start", style="bold blue")
        welcome_text.append("\\n\\nGet your media syncing in 3 simple steps:", style="dim")
        welcome_text.append("\\n\\n1. Select media source (auto-detected)")
        welcome_text.append("\\n2. Choose destination location")  
        welcome_text.append("\\n3. Validate Plex connection")
        
        if self.preferences.successful_completion_count > 0:
            success_rate = self.preferences.get_success_rate_estimate()
            welcome_text.append(f"\\n\\n✨ Based on your history, success rate: {success_rate:.0%}", style="green")
        
        panel = Panel(
            Align.center(welcome_text),
            border_style="blue",
            padding=(1, 2)
        )
        self.console.print(panel)
        self.console.print()
    
    def _select_media_source(self) -> bool:
        """Step 1: Select media source with auto-detection.
        
        Returns:
            True if source selected successfully, False otherwise
        """
        self.console.print("[bold]Step 1: Media Source Selection[/bold]")
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=self.console,
            transient=True
        ) as progress:
            task = progress.add_task("Scanning for media sources...", total=None)
            
            # Find potential media sources
            candidates = self.media_finder.find_potential_sources()
            
            if not candidates:
                raise AutoDetectionFailure("No media sources found")
                
            progress.update(task, description="Found media sources!")
                
        # Show found sources
        if len(candidates) == 1:
            # Only one source found - use it automatically
            selected = candidates[0]
            self.console.print(f"[green]✓[/green] Found media source: {selected.path}")
            self.console.print(f"  Type: {selected.media_type.value.replace('_', ' ').title()}")
            self.console.print(f"  Reason: {selected.reason}")
            
            if not Confirm.ask("Use this source?", default=True):
                return False
                
        else:
            # Multiple sources - let user choose
            selected = self._choose_from_candidates(candidates)
            if not selected:
                return False
        
        self.session.source_path = selected.path
        self.session.media_type = selected.media_type
        
        self.console.print(f"[green]✓[/green] Source selected: {selected.path}")
        self.console.print()
        return True
    
    def _choose_from_candidates(self, candidates: List[MediaCandidate]) -> Optional[MediaCandidate]:
        """Display candidates and let user choose.
        
        Args:
            candidates: List of media candidates
            
        Returns:
            Selected MediaCandidate or None if cancelled
        """
        # Prioritize previous selection if available
        if self.preferences.last_source_path:
            for candidate in candidates:
                if str(candidate.path) == self.preferences.last_source_path:
                    candidate.reason += " (Previously used)"
                    # Move to front of list
                    candidates.remove(candidate)
                    candidates.insert(0, candidate)
                    break
        
        # Create selection table
        table = Table(title="Found Media Sources", show_header=True, header_style="bold blue")
        table.add_column("Option", style="cyan", width=6)
        table.add_column("Path", style="green")
        table.add_column("Type", style="yellow")
        table.add_column("Details", style="dim")
        
        for i, candidate in enumerate(candidates[:5], 1):  # Limit to top 5
            media_type = candidate.media_type.value.replace('_', ' ').title()
            details = f"{candidate.reason}"
            if candidate.file_count:
                details += f" ({candidate.file_count} files)"
                
            table.add_row(
                str(i),
                str(candidate.path),
                media_type,
                details
            )
        
        self.console.print(table)
        self.console.print()
        
        # Get user choice
        while True:
            try:
                choice = Prompt.ask(
                    "Select media source [1-{}] or 'q' to quit".format(len(candidates[:5])),
                    default="1"
                )
                
                if choice.lower() == 'q':
                    return None
                    
                index = int(choice) - 1
                if 0 <= index < len(candidates[:5]):
                    return candidates[index]
                else:
                    self.console.print("[red]Invalid selection. Please try again.[/red]")
                    
            except ValueError:
                self.console.print("[red]Please enter a number or 'q' to quit.[/red]")
    
    def _select_destination(self) -> bool:
        """Step 2: Select destination directory.
        
        Returns:
            True if destination selected successfully, False otherwise
        """
        self.console.print("[bold]Step 2: Destination Selection[/bold]")
        
        # Check if we have a preference and it's still valid
        if self.preferences.last_destination_path:
            last_dest = Path(self.preferences.last_destination_path)
            if last_dest.exists() and last_dest.is_dir():
                self.console.print(f"[dim]Previous destination: {last_dest}[/dim]")
                
                if Confirm.ask("Use previous destination?", default=True):
                    self.session.destination_path = last_dest
                    self.console.print(f"[green]✓[/green] Destination: {last_dest}")
                    self.console.print()
                    return True
        
        # Suggest smart defaults based on source
        suggestions = self._get_destination_suggestions()
        
        if suggestions:
            self.console.print("[dim]Suggested destinations:[/dim]")
            for i, suggestion in enumerate(suggestions, 1):
                self.console.print(f"  {i}. {suggestion}")
            self.console.print()
            
            choice = Prompt.ask(
                f"Select destination [1-{len(suggestions)}] or enter custom path",
                default="1"
            )
            
            try:
                index = int(choice) - 1
                if 0 <= index < len(suggestions):
                    selected_path = Path(suggestions[index])
                else:
                    raise ValueError()
            except ValueError:
                # User entered custom path
                selected_path = Path(choice.strip()).expanduser()
        else:
            # No suggestions, ask for path
            path_input = Prompt.ask("Enter destination directory path")
            selected_path = Path(path_input.strip()).expanduser()
        
        # Validate destination
        try:
            # Create directory if it doesn't exist
            selected_path.mkdir(parents=True, exist_ok=True)
            
            if not selected_path.is_dir():
                self.console.print(f"[red]Error: {selected_path} is not a directory[/red]")
                return False
                
            # Check write permissions
            test_file = selected_path / ".plexsync_test"
            try:
                test_file.write_text("test")
                test_file.unlink()
            except Exception:
                self.console.print(f"[red]Error: No write permission to {selected_path}[/red]")
                return False
                
        except Exception as e:
            self.console.print(f"[red]Error creating destination directory: {e}[/red]")
            return False
        
        self.session.destination_path = selected_path
        self.console.print(f"[green]✓[/green] Destination: {selected_path}")
        self.console.print()
        return True
    
    def _get_destination_suggestions(self) -> List[str]:
        """Get smart destination suggestions based on source and system.
        
        Returns:
            List of suggested destination paths
        """
        suggestions = []
        
        if self.session.source_path:
            source_parent = self.session.source_path.parent
            
            # Suggest a sync folder in the same parent directory
            sync_folder = source_parent / "PlexSync"
            suggestions.append(str(sync_folder))
            
            # Suggest user's home directory
            home_sync = Path.home() / "PlexSync"
            if str(home_sync) not in suggestions:
                suggestions.append(str(home_sync))
        
        # Add other common locations
        if sys.platform != "win32":
            common_paths = ["/tmp/plexsync", "/var/tmp/plexsync"]
        else:
            common_paths = [os.path.expandvars(r"%TEMP%\\plexsync")]
            
        for path in common_paths:
            if path not in suggestions:
                suggestions.append(path)
        
        return suggestions[:3]  # Limit to 3 suggestions
    
    def _validate_plex_connection(self) -> bool:
        """Step 3: Validate Plex server connection.
        
        Returns:
            True if connection validated or skipped, False if setup required
        """
        self.console.print("[bold]Step 3: Plex Server Validation[/bold]")
        
        # Check if user wants to skip Plex validation
        if self.preferences.skip_plex_validation:
            self.console.print("[dim]Plex validation disabled in preferences[/dim]")
            self.session.skip_plex = True
            self.console.print("[green]✓[/green] Skipping Plex validation")
            self.console.print()
            return True
        
        # Try to find existing Plex configuration
        try:
            config = self.config_manager.get_active_config()
            if config and hasattr(config, 'plex') and config.plex:
                self.console.print("[green]✓[/green] Found existing Plex configuration")
                self.console.print()
                return True
        except Exception:
            pass  # No existing config
        
        # Ask user what to do about Plex
        self.console.print("[yellow]No Plex server configuration found.[/yellow]")
        choice = Prompt.ask(
            "What would you like to do?",
            choices=["skip", "configure", "abort"],
            default="skip"
        )
        
        if choice == "skip":
            self.session.skip_plex = True
            
            # Ask if they want to remember this choice
            if Confirm.ask("Remember this choice for future quick starts?", default=False):
                self.preferences.skip_plex_validation = True
                self.settings_manager.save_settings()
            
            self.console.print("[green]✓[/green] Skipping Plex validation")
            self.console.print()
            return True
            
        elif choice == "configure":
            # Hand off to setup wizard for Plex configuration
            return False
            
        else:  # abort
            self.console.print("[yellow]Quick start cancelled[/yellow]")
            return False
    
    def _execute_quick_sync(self) -> bool:
        """Execute the sync with minimal configuration.
        
        Returns:
            True if sync initiated successfully, False otherwise
        """
        self.console.print("[bold]Executing Quick Sync[/bold]")
        
        try:
            # Create minimal configuration for sync
            sync_config = self._create_minimal_config()
            
            # Show what will be synced
            self._show_sync_preview()
            
            # Ask for final confirmation
            if not Confirm.ask("Start syncing now?", default=True):
                self.console.print("[yellow]Sync cancelled by user[/yellow]")
                return False
            
            # Record this success in preferences
            duration = self.session.get_duration()
            self.preferences.record_success(
                source_path=str(self.session.source_path),
                destination_path=str(self.session.destination_path),
                completion_time_seconds=duration,
                media_type=self.session.media_type.value if self.session.media_type else None
            )
            self.settings_manager.save_settings()
            
            # Show completion summary
            self._show_completion_summary(duration)
            
            # Initialize the sync process (integration point for real sync)
            self.console.print("[green]✓[/green] Quick sync configuration complete!")
            self.console.print("[dim]Sync process would be initiated here in full implementation[/dim]")
            self.console.print(f"[dim]Setup Duration: {duration:.1f} seconds[/dim]")
            
            # Provide next steps
            self._show_next_steps()
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to execute quick sync: {e}")
            self.console.print(f"[red]Error executing sync: {e}[/red]")
            return False
    
    def _show_sync_preview(self):
        """Show preview of what will be synced."""
        self.console.print("[bold]Sync Preview[/bold]")
        
        # Count files in source (sample for preview)
        try:
            file_count = 0
            total_size = 0
            sample_files = []
            
            for item in self.session.source_path.iterdir():
                if item.is_file() and file_count < 5:  # Sample first 5 files
                    sample_files.append(item.name)
                    try:
                        total_size += item.stat().st_size
                    except OSError:
                        pass
                file_count += 1
                if file_count >= 100:  # Limit scan for performance
                    break
            
            size_mb = total_size / (1024 * 1024)
            
            self.console.print(f"[dim]Source:[/dim] {self.session.source_path}")
            self.console.print(f"[dim]Destination:[/dim] {self.session.destination_path}")
            self.console.print(f"[dim]Files found:[/dim] {file_count}+ files ({size_mb:.1f} MB sampled)")
            
            if sample_files:
                self.console.print(f"[dim]Sample files:[/dim] {', '.join(sample_files[:3])}")
                if len(sample_files) > 3:
                    self.console.print(f"[dim]... and {len(sample_files) - 3} more[/dim]")
                    
        except Exception as e:
            self.console.print(f"[dim]Could not preview source: {e}[/dim]")
        
        self.console.print()
    
    def _show_next_steps(self):
        """Show next steps after quick start completion."""
        next_steps = Table(title="Next Steps", show_header=False)
        next_steps.add_column("Action", style="cyan")
        next_steps.add_column("Command", style="green")
        
        next_steps.add_row("Monitor sync progress", "plexsync status")
        next_steps.add_row("Configure more sources", "plexsync --setup-wizard")
        next_steps.add_row("Browse available media", "plexsync discover")
        next_steps.add_row("Sync specific items", "plexsync sync --interactive")
        
        self.console.print(next_steps)
        self.console.print()
    
    def _create_minimal_config(self) -> Dict[str, Any]:
        """Create minimal configuration for sync.
        
        Returns:
            Dictionary containing minimal sync configuration
        """
        return {
            "source": {
                "path": str(self.session.source_path),
                "type": self.session.media_type.value if self.session.media_type else "mixed"
            },
            "destination": {
                "path": str(self.session.destination_path)
            },
            "skip_plex": self.session.skip_plex,
            "quick_start": True
        }
    
    def _show_completion_summary(self, duration: float):
        """Show completion summary to user.
        
        Args:
            duration: Total completion time in seconds
        """
        summary = Table(title="Quick Start Summary", show_header=False)
        summary.add_column("Setting", style="cyan")
        summary.add_column("Value", style="green")
        
        summary.add_row("Source", str(self.session.source_path))
        summary.add_row("Destination", str(self.session.destination_path))
        summary.add_row("Media Type", self.session.media_type.value.replace('_', ' ').title() if self.session.media_type else "Mixed")
        summary.add_row("Plex Integration", "Disabled" if self.session.skip_plex else "Enabled")
        summary.add_row("Completion Time", f"{duration:.1f} seconds")
        
        self.console.print(summary)
        self.console.print()
    
    def _fallback_to_setup_wizard(self, reason: str) -> bool:
        """Fallback to the full setup wizard.
        
        Args:
            reason: Reason for fallback
            
        Returns:
            False (indicating quick start didn't complete)
        """
        logger.info(f"Quick start fallback: {reason}")
        
        self.console.print(f"[yellow]Quick start needs additional setup: {reason}[/yellow]")
        self.console.print("Switching to the full setup wizard for complete configuration...")
        self.console.print()
        
        try:
            from .setup_wizard import SetupWizard
            wizard = SetupWizard(console=self.console, verbose=self.verbose)
            wizard.run()
            return False  # Indicate that quick start didn't complete
            
        except ImportError:
            self.console.print("[red]Setup wizard is not available[/red]")
            return False
        except Exception as e:
            self.console.print(f"[red]Setup wizard failed: {e}[/red]")
            return False


def get_quick_start_manager(console: Optional[Console] = None, verbose: bool = False) -> QuickStartManager:
    """Get a QuickStartManager instance.
    
    Args:
        console: Optional Rich console instance
        verbose: Enable verbose logging
        
    Returns:
        QuickStartManager instance
    """
    return QuickStartManager(console, verbose)