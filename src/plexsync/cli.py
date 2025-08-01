"""
Main CLI entry point for PlexSync.

This module provides the command-line interface for PlexSync, including
media discovery, interactive selection, and individual file synchronization.
"""

import sys
import os
import time
import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.progress import Progress, SpinnerColumn, TextColumn
from .settings_manager import get_settings_manager
from typing import Optional, List

from . import __version__
from .compatibility import CompatibilityMatrix, PlatformSupport, TerminalCapability
from .datasets import (
    MediaDiscovery, MediaSelector, MediaLibrary, MediaType, MediaItem,
    get_default_media_sources, TestDatasetSize, TEST_DATASETS
)
from .interactive import InteractiveSyncManager
from .mount import get_mount_manager, MountStatus, check_and_mount_media_folders
from .environment import validate_environment, CheckStatus
from .config import get_config_manager, get_active_config
from .sync import SyncEngine, SyncOptions, SyncStatus
from .progress import ProgressTracker, SyncProgress


# Global console instance for rich output
console = Console()


def show_banner(show_first_time_tips: bool = None):
    """Display the PlexSync banner.
    
    Args:
        show_first_time_tips: If True, show first-time user tips. If None, auto-detect.
    """
    banner_text = """
╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║   ██████╗ ██╗     ███████╗██╗  ██╗███████╗██╗   ██╗███╗   ██╗ ██████╗        ║
║   ██╔══██╗██║     ██╔════╝╚██╗██╔╝██╔════╝╚██╗ ██╔╝████╗  ██║██╔════╝        ║
║   ██████╔╝██║     █████╗   ╚███╔╝ ███████╗ ╚████╔╝ ██╔██╗ ██║██║             ║
║   ██╔═══╝ ██║     ██╔══╝   ██╔██╗ ╚════██║  ╚██╔╝  ██║╚██╗██║██║             ║
║   ██║     ███████╗███████╗██╔╝ ██╗███████║   ██║   ██║ ╚████║╚██████╗        ║
║   ╚═╝     ╚══════╝╚══════╝╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝  ╚═══╝ ╚═════╝        ║
║                                                                              ║
║                    Interactive Media Synchronization                         ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
    """
    
    # Only show banner if terminal is wide enough
    if console.size.width >= 80:
        console.print(banner_text, style="bold blue")
    else:
        console.print("PlexSync", style="bold blue")
        console.print("Interactive Media Synchronization", style="dim")
    
    console.print(f"Version: {__version__}", style="dim")
    console.print()
    
    # Show first-time user tips if requested or auto-detected
    if show_first_time_tips is None:
        show_first_time_tips = _is_first_time_user()
    
    if show_first_time_tips:
        _show_first_time_tips()


def _is_first_time_user() -> bool:
    """Detect if this is a first-time user.
    
    Returns:
        True if no configuration exists, False otherwise
    """
    try:
        from .config import get_config_manager
        config_manager = get_config_manager()
        return not os.path.exists(config_manager.config_file)
    except Exception:
        return True


def _show_first_time_tips():
    """Show helpful tips for first-time users."""
    tips_text = """
🌟 New to PlexSync? Get started quickly:

   • Run 'plexsync --setup-wizard' for guided configuration
   • Use 'plexsync --help' to see all available commands
   • Check 'plexsync --check-env' to validate your system

💡 The setup wizard will help you configure media sources and destinations
   in just a few minutes!
    """.strip()
    
    from rich.panel import Panel
    panel = Panel(
        tips_text,
        title="[bold green]Getting Started[/bold green]",
        border_style="green",
        padding=(1, 2)
    )
    
    console.print(panel)
    console.print()


def show_compatibility_report():
    """Display the compatibility report."""
    report = CompatibilityMatrix.get_compatibility_report()
    
    # Create main table
    table = Table(title="System Compatibility Report", show_header=True, header_style="bold magenta")
    table.add_column("Component", style="cyan", width=15)
    table.add_column("Status", width=20)
    table.add_column("Details", style="dim")
    
    # Platform row
    platform_status = report["platform"]["support_level"]
    platform_color = "green" if platform_status == "full" else "yellow" if platform_status == "limited" else "red"
    table.add_row(
        "Platform",
        f"[{platform_color}]{platform_status.upper()}[/{platform_color}]",
        f"{report['platform']['os']} {report['platform']['version']}"
    )
    
    # Python row
    python_status = report["python"]["status"]
    python_color = "green" if python_status == "recommended" else "yellow" if python_status == "supported" else "red"
    table.add_row(
        "Python",
        f"[{python_color}]{python_status.upper()}[/{python_color}]",
        f"Version {report['python']['version']}"
    )
    
    # Terminal row
    terminal_capability = report["terminal"]["capability"]
    terminal_color = "green" if terminal_capability == "truecolor" else "yellow" if terminal_capability == "basic_color" else "red"
    table.add_row(
        "Terminal",
        f"[{terminal_color}]{terminal_capability.upper()}[/{terminal_color}]",
        f"{report['terminal']['columns']}x{report['terminal']['lines']}"
    )
    
    # Rsync row
    rsync_available = report["rsync"]["available"]
    rsync_recommended = report["rsync"]["recommended"]
    if rsync_available:
        rsync_color = "green" if rsync_recommended else "yellow"
        rsync_status = "OPTIMAL" if rsync_recommended else "BASIC"
        rsync_details = f"Version {report['rsync']['version']}"
    else:
        rsync_color = "red"
        rsync_status = "NOT FOUND"
        rsync_details = "Please install rsync"
    
    table.add_row(
        "Rsync",
        f"[{rsync_color}]{rsync_status}[/{rsync_color}]",
        rsync_details
    )
    
    console.print(table)
    console.print()
    
    # Show warnings and recommendations
    if report["warnings"]:
        console.print("⚠️  Warnings:", style="bold yellow")
        for warning in report["warnings"]:
            console.print(f"  • {warning}", style="yellow")
        console.print()
    
    if report["recommendations"]:
        console.print("💡 Recommendations:", style="bold blue")
        for rec in report["recommendations"]:
            console.print(f"  • {rec}", style="blue")
        console.print()


def show_environment_report():
    """Display comprehensive environment validation report."""
    console.print("🔍 Environment Validation", style="bold cyan")
    console.print()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Validating environment...", total=None)
        env_report = validate_environment()
        progress.update(task, completed=100)
    
    # Create status table
    table = Table(title="Environment Status", show_header=True, header_style="bold magenta")
    table.add_column("Check", style="cyan", width=20)
    table.add_column("Status", width=12)
    table.add_column("Details", style="dim")
    
    for check in env_report.checks:
        if check.status == CheckStatus.PASS:
            status_color = "green"
            status_text = "✅ PASS"
        elif check.status == CheckStatus.WARN:
            status_color = "yellow"
            status_text = "⚠️  WARN"
        elif check.status == CheckStatus.FAIL:
            status_color = "red"
            status_text = "❌ FAIL"
        else:
            status_color = "dim"
            status_text = "⏭️  SKIP"
        
        table.add_row(
            check.name,
            f"[{status_color}]{status_text}[/{status_color}]",
            check.message
        )
    
    console.print(table)
    console.print()
    
    # Summary
    console.print("📊 Summary:", style="bold")
    console.print(f"  ✅ Passed: {env_report.passed}")
    console.print(f"  ⚠️  Warnings: {env_report.warned}")
    console.print(f"  ❌ Failed: {env_report.failed}")
    console.print(f"  ⏭️  Skipped: {env_report.skipped}")
    console.print()
    
    # Show failed checks with fix suggestions
    failed_checks = [c for c in env_report.checks if c.status == CheckStatus.FAIL]
    if failed_checks:
        console.print("🔧 Fix Suggestions:", style="bold red")
        for check in failed_checks:
            if check.fix_suggestion:
                console.print(f"  • {check.name}: {check.fix_suggestion}", style="red")
        console.print()
    
    return env_report.is_ready


def show_mount_report():
    """Display mount point status report."""
    console.print("📁 Mount Point Status", style="bold green")
    console.print()
    
    mount_manager = get_mount_manager()
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Discovering mount points...", total=None)
        mount_manager.discover_mounts()
        progress.update(task, completed=100)
    
    report = mount_manager.get_mount_report()
    
    # Create mount table
    table = Table(title="Mount Points", show_header=True, header_style="bold magenta")
    table.add_column("Path", style="cyan", width=30)
    table.add_column("Type", width=10)
    table.add_column("Status", width=12)
    table.add_column("Response", width=10)
    table.add_column("Details", style="dim")
    
    for mount in report["mounts"]:
        if mount["status"] == "healthy":
            status_color = "green"
            status_text = "✅ HEALTHY"
        elif mount["status"] == "degraded":
            status_color = "yellow"
            status_text = "⚠️  DEGRADED"
        elif mount["status"] == "unavailable":
            status_color = "red"
            status_text = "❌ UNAVAIL"
        else:
            status_color = "dim"
            status_text = "❓ UNKNOWN"
        
        response_time = ""
        if mount["response_time_ms"]:
            response_time = f"{mount['response_time_ms']:.1f}ms"
        
        details = mount.get("error_message", mount["device"])
        
        table.add_row(
            mount["path"],
            mount["type"].upper(),
            f"[{status_color}]{status_text}[/{status_color}]",
            response_time,
            details
        )
    
    console.print(table)
    console.print()
    
    # Summary
    console.print("📊 Mount Summary:", style="bold")
    console.print(f"  📁 Total Mounts: {report['total_mounts']}")
    console.print(f"  ✅ Healthy: {report['healthy_mounts']}")
    console.print(f"  ⚠️  Degraded: {report['degraded_mounts']}")
    console.print(f"  ❌ Unavailable: {report['unavailable_mounts']}")
    console.print(f"  🌐 Network: {report['network_mounts']}")
    console.print(f"  💾 Local: {report['local_mounts']}")
    console.print()


def show_media_library_info():
    """Display information about media discovery and selection."""
    console.print("Media Discovery & Selection", style="bold green")
    console.print()
    
    # Media discovery explanation
    discovery_info = """
PlexSync discovers and catalogs your media for interactive selection:

🎬 Movies: Individual movie files for one-at-a-time syncing
📺 TV Shows: Episode-by-episode or season-by-season selection
🔍 Smart Discovery: Automatically finds media across multiple source folders
📝 Unified Listings: Combines Movies/Movies2 and TV/TV2 into sorted alphabetical lists
🎯 Interactive Selection: Browse, search, and select exactly what you want to sync
    """.strip()
    
    console.print(discovery_info)
    console.print()
    
    # Show test dataset sizes
    console.print("Test Dataset Sizes (for development):", style="bold yellow")
    console.print()
    
    for size in TestDatasetSize:
        spec = TEST_DATASETS[size]
        
        content = f"""
Movies: {spec.movies_count}
TV Shows: {spec.shows_count} ({spec.avg_episodes_per_show} episodes avg)
Purpose: {spec.purpose}
        """.strip()
        
        color = "green" if size == TestDatasetSize.SMALL else "yellow" if size == TestDatasetSize.MEDIUM else "red"
        
        panel = Panel(
            content,
            title=f"[bold]{size.value.upper()} Dataset[/bold]",
            border_style=color,
            padding=(1, 2)
        )
        
        console.print(panel)
        console.print()


@click.group(invoke_without_command=True)
@click.option('--version', is_flag=True, help='Show version and exit')
@click.option('--check-compat', is_flag=True, help='Check system compatibility and exit')
@click.option('--check-env', is_flag=True, help='Check environment readiness and exit')
@click.option('--setup-wizard', is_flag=True, help='Run interactive first-time setup wizard')
@click.option('--plain', is_flag=True, help='Use plain text output (no colors/formatting)')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose output')
@click.pass_context
def main(ctx, version, check_compat, check_env, setup_wizard, plain, verbose):
    """
    PlexSync - Interactive media synchronization tool.
    
    A robust CLI tool for syncing individual movies and TV episodes from 
    mounted network drives to local storage with beautiful interactive
    selection and bulletproof error handling.
    
    By default, 'plexsync' starts interactive sync mode. Use subcommands
    for other operations:
    
    \b
    plexsync discover    Scan media sources and build library
    plexsync browse      Browse and select media interactively  
    plexsync sync        Sync selected media to local storage (default)
    plexsync config      Manage configuration
    plexsync status      Show library and sync status
    plexsync doctor      Diagnose system issues
    """
    
    # Set up global console mode
    if plain:
        global console
        console = Console(force_terminal=False, no_color=True)
    
    # Store options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['plain'] = plain
    
    # Handle version flag
    if version:
        console.print(f"PlexSync version {__version__}")
        sys.exit(0)
    
    # Handle compatibility check flag
    if check_compat:
        show_banner()
        show_compatibility_report()
        sys.exit(0)
    
    # Handle environment check flag
    if check_env:
        show_banner()
        is_ready = show_environment_report()
        if not is_ready:
            console.print("❌ Environment is not ready for operation", style="bold red")
            sys.exit(1)
        else:
            console.print("✅ Environment is ready for operation", style="bold green")
            sys.exit(0)
    
    # Handle setup wizard flag
    if setup_wizard:
        show_banner()
        console.print("🚀 Starting PlexSync Setup Wizard", style="bold green")
        console.print("   This wizard will guide you through the initial configuration process.")
        console.print()
        
        try:
            from .setup_wizard import SetupWizard
            wizard = SetupWizard(console=console, verbose=verbose)
            success = wizard.run()
            
            if success:
                console.print("✅ Setup completed successfully!", style="bold green")
                console.print("   You can now run 'plexsync' to start syncing media.")
                sys.exit(0)
            else:
                console.print("❌ Setup was not completed", style="bold red")
                console.print("   You can run 'plexsync --setup-wizard' again to retry.")
                sys.exit(1)
                
        except ImportError:
            console.print("❌ Setup wizard is not available", style="bold red")
            console.print("   Please check your PlexSync installation.")
            sys.exit(1)
        except Exception as e:
            console.print(f"❌ Setup wizard encountered an error: {e}", style="bold red")
            if verbose:
                import traceback
                console.print(traceback.format_exc())
            sys.exit(1)
    
    # If no subcommand provided, default to sync command (interactive mode)
    if ctx.invoked_subcommand is None:
        show_banner()
        
        # Check and mount /mnt/media folders early in startup
        console.print("🔍 Checking media mount points...", style="dim")
        mount_success = check_and_mount_media_folders()
        if not mount_success:
            console.print("⚠️  Some media mount points are unavailable", style="yellow")
            console.print("   Continuing with available mount points...", style="dim")
        else:
            console.print("✅ Media mount points are ready", style="dim")
        console.print()
        
        # Quick compatibility check
        is_compatible, errors = CompatibilityMatrix.validate_environment()
        
        if not is_compatible:
            console.print("❌ System Compatibility Issues:", style="bold red")
            for error in errors:
                console.print(f"  • {error}", style="red")
            console.print()
            console.print("Run 'plexsync --check-compat' for detailed information.")
            sys.exit(1)
        else:
            console.print("✅ System is compatible with PlexSync", style="bold green")
            console.print()
        
        # Default to interactive sync mode
        console.print("🚀 Starting Interactive Sync (default mode)", style="bold cyan")
        console.print("💡 Tip: Use 'plexsync --help' to see all available commands", style="dim")
        console.print()
        
        # Load library and set up context for all commands
        library = _load_discovered_library()
        if library:
            ctx.obj['library'] = library
        
        # Invoke sync command with default parameters
        ctx.invoke(sync, 
                  interactive=True, 
                  dry_run=False, 
                  movie=None, 
                  show=None, 
                  season=None, 
                  episode=None, 
                  profile=None, 
                  bandwidth=None, 
                  verify=True, 
                  no_verify=False)


@main.command()
@click.option('--rescan', is_flag=True, help='Force rescan of all media sources')
@click.option('--sources', help='Comma-separated list of source names to scan')
@click.option('--workers', type=int, default=4, help='Number of parallel workers (default: 4)')
@click.option('--clear-cache', is_flag=True, help='Clear the discovery cache before scanning')
@click.pass_context
def discover(ctx, rescan, sources, workers, clear_cache):
    """Discover and catalog media from configured sources."""
    console.print("🔍 Media Discovery", style="bold green")
    console.print()
    
    # Check and mount /mnt/media folders before discovery
    console.print("📡 Checking media mount points...", style="dim")
    mount_success = check_and_mount_media_folders()
    if not mount_success:
        console.print("⚠️  Some media mount points are unavailable", style="yellow")
        console.print("   Discovery will continue with available mount points...", style="dim")
    else:
        console.print("✅ All media mount points are ready", style="dim")
    console.print()
    
    # Load configuration
    config = get_active_config()
    if not config:
        console.print("❌ No configuration found. Run 'plexsync config --init' first.", style="red")
        return
    
    # Get configured media sources
    configured_sources = config.sources
    
    # Convert to discovery format
    from .datasets import MediaSource, MediaType
    media_sources = []
    for source in configured_sources:
        media_type = MediaType.MOVIE if source.media_type == "movie" else MediaType.TV_SHOW
        media_sources.append(MediaSource(
            name=source.name,
            base_path=source.base_path,
            media_type=media_type,
            enabled=source.enabled,
            scan_depth=source.scan_depth
        ))
    
    if sources:
        # Filter to specific sources
        source_names = [s.strip() for s in sources.split(',')]
        media_sources = [s for s in media_sources if s.name in source_names]
        console.print(f"📂 Scanning specific sources: {', '.join(source_names)}")
    else:
        console.print("📂 Scanning all configured media sources")
    
    console.print(f"🔧 Using {workers} parallel workers")
    console.print()
    
    # Check mount points first
    mount_manager = get_mount_manager()
    mount_paths = [source.base_path for source in media_sources]
    media_mounts = mount_manager.get_media_mounts(mount_paths)
    
    # Show mount status
    unhealthy_mounts = [m for m in media_mounts if not m.is_healthy]
    if unhealthy_mounts:
        console.print("⚠️  Mount Issues Detected:", style="yellow")
        for mount in unhealthy_mounts:
            status_color = "red" if mount.status == MountStatus.UNAVAILABLE else "yellow"
            console.print(f"  • {mount.path}: [{status_color}]{mount.status.value}[/{status_color}]")
            if mount.error_message:
                console.print(f"    {mount.error_message}")
        console.print()
    
    # Initialize optimized discovery
    discovery = MediaDiscovery(media_sources, max_workers=workers)
    
    # Clear cache if requested
    if clear_cache:
        try:
            if discovery.cache_file.exists():
                discovery.cache_file.unlink()
                console.print("🗑️  Cache cleared", style="yellow")
            else:
                console.print("💾 No cache file found", style="dim")
        except Exception as e:
            console.print(f"⚠️  Failed to clear cache: {e}", style="yellow")
    
    # Scan and build library
    try:
        start_time = time.time()
        library = discovery.scan_all_sources(force_rescan=rescan)
        end_time = time.time()
        
        # Show results
        console.print()
        console.print("📊 Discovery Results:", style="bold blue")
        console.print(f"  Movies: {len(library.movies)}")
        console.print(f"  TV Shows: {len(library.tv_shows)}")
        console.print(f"  Total Episodes: {sum(len(eps) for eps in library.tv_shows.values())}")
        console.print(f"  Total Items: {library.total_items}")
        console.print(f"  Scan Duration: {end_time - start_time:.2f} seconds")
        
        if library.total_items == 0:
            console.print()
            console.print("⚠️  No media found. Check your source paths:", style="yellow")
            for source in media_sources:
                exists = "✅" if os.path.exists(source.base_path) else "❌"
                console.print(f"  {exists} {source.name}: {source.base_path}")
        else:
            console.print()
            console.print("✅ Media discovery completed successfully", style="green")
            console.print("💡 Tip: Subsequent scans will be faster thanks to caching", style="dim")
        
    except Exception as e:
        console.print(f"❌ Discovery failed: {e}", style="red")
        if ctx.obj['verbose']:
            import traceback
            console.print(traceback.format_exc())


@main.command()
@click.option('--type', 'media_type', type=click.Choice(['movie', 'tv']), 
              help='Browse only movies or TV shows')
@click.option('--search', help='Search query to filter results')
@click.option('--interactive', is_flag=True, default=True, help='Interactive selection mode')
@click.pass_context
def browse(ctx, media_type, search, interactive):
    """Browse and select media interactively."""
    console.print("🎬 Media Browser", style="bold green")
    console.print()
    
    # Load actual discovered media library from cache
    library = _load_discovered_library()
    
    if not library or library.total_items == 0:
        console.print("❌ No media library found", style="red")
        console.print("Run 'plexsync discover' first to scan your media sources")
        return
    
    # Apply filters
    if media_type == 'movie':
        _browse_movies(library, search)
    elif media_type == 'tv':
        _browse_tv_shows(library, search)
    else:
        # Show both movies and TV shows
        _browse_all_media(library, search)


def _load_discovered_library():
    """Load the actual discovered media library from cache."""
    from .datasets import MediaDiscovery, MediaLibrary, MediaItem, MediaType
    
    try:
        # Create a temporary discovery instance to access the cache
        discovery = MediaDiscovery(sources=[], max_workers=1)
        
        # Check if cache exists
        if not discovery.cache_file.exists():
            return None
        
        # Load cache entries
        cache = discovery._load_cache()
        if not cache:
            return None
        
        # Extract media items from all cache entries
        all_movies = []
        all_tv_shows = {}
        
        for cache_key, cache_entry in cache.items():
            if not cache_entry.items:
                continue
                
            for item in cache_entry.items:
                if item.media_type == MediaType.MOVIE:
                    all_movies.append(item)
                elif item.media_type == MediaType.TV_EPISODE:
                    if item.show_name not in all_tv_shows:
                        all_tv_shows[item.show_name] = []
                    all_tv_shows[item.show_name].append(item)
        
        # Create library from cached data
        library = MediaLibrary(
            movies=all_movies,
            tv_shows=all_tv_shows,
            last_scan=time.time(),
            total_items=len(all_movies) + sum(len(eps) for eps in all_tv_shows.values())
        )
        
        return library
        
    except Exception as e:
        print(f"⚠️  Failed to load discovered library: {e}")
        return None


def _load_or_create_test_library():
    """Load or create a test media library for demonstration."""
    from .datasets import MediaLibrary, MediaItem, MediaType
    
    # Create test movies
    movies = [
        MediaItem("Avatar", MediaType.MOVIE, "/mnt/movies/Avatar.mkv", "Avatar.mkv", 4500000000, ".mkv"),
        MediaItem("Blade Runner 2049", MediaType.MOVIE, "/mnt/movies/Blade Runner 2049.mkv", "Blade Runner 2049.mkv", 6800000000, ".mkv"),
        MediaItem("The Matrix", MediaType.MOVIE, "/mnt/movies/The Matrix.mkv", "The Matrix.mkv", 3200000000, ".mkv"),
        MediaItem("Aliens", MediaType.MOVIE, "/mnt/movies/Aliens.mkv", "Aliens.mkv", 2800000000, ".mkv"),
        MediaItem("Dune", MediaType.MOVIE, "/mnt/movies/Dune.mkv", "Dune.mkv", 5200000000, ".mkv"),
        MediaItem("Inception", MediaType.MOVIE, "/mnt/movies/Inception.mkv", "Inception.mkv", 4100000000, ".mkv"),
        MediaItem("Interstellar", MediaType.MOVIE, "/mnt/movies/Interstellar.mkv", "Interstellar.mkv", 6200000000, ".mkv"),
        MediaItem("The Dark Knight", MediaType.MOVIE, "/mnt/movies/The Dark Knight.mkv", "The Dark Knight.mkv", 3800000000, ".mkv"),
    ]
    
    # Create test TV episodes
    tv_shows = {
        "Breaking Bad": [
            MediaItem("Pilot", MediaType.TV_EPISODE, "/mnt/tv/Breaking Bad/S01E01.mkv", "S01E01.mkv", 
                     1800000000, ".mkv", show_name="Breaking Bad", season=1, episode=1, episode_title="Pilot"),
            MediaItem("Cat's in the Bag...", MediaType.TV_EPISODE, "/mnt/tv/Breaking Bad/S01E02.mkv", "S01E02.mkv", 
                     1750000000, ".mkv", show_name="Breaking Bad", season=1, episode=2, episode_title="Cat's in the Bag..."),
            MediaItem("...And the Bag's in the River", MediaType.TV_EPISODE, "/mnt/tv/Breaking Bad/S01E03.mkv", "S01E03.mkv", 
                     1820000000, ".mkv", show_name="Breaking Bad", season=1, episode=3, episode_title="...And the Bag's in the River"),
        ],
        "Game of Thrones": [
            MediaItem("Winter Is Coming", MediaType.TV_EPISODE, "/mnt/tv/Game of Thrones/S01E01.mkv", "S01E01.mkv", 
                     2100000000, ".mkv", show_name="Game of Thrones", season=1, episode=1, episode_title="Winter Is Coming"),
            MediaItem("The Kingsroad", MediaType.TV_EPISODE, "/mnt/tv/Game of Thrones/S01E02.mkv", "S01E02.mkv", 
                     2050000000, ".mkv", show_name="Game of Thrones", season=1, episode=2, episode_title="The Kingsroad"),
            MediaItem("Lord Snow", MediaType.TV_EPISODE, "/mnt/tv/Game of Thrones/S01E03.mkv", "S01E03.mkv", 
                     2080000000, ".mkv", show_name="Game of Thrones", season=1, episode=3, episode_title="Lord Snow"),
        ],
        "The Mandalorian": [
            MediaItem("Chapter 1", MediaType.TV_EPISODE, "/mnt/tv/The Mandalorian/S01E01.mkv", "S01E01.mkv", 
                     2200000000, ".mkv", show_name="The Mandalorian", season=1, episode=1, episode_title="Chapter 1: The Mandalorian"),
            MediaItem("Chapter 2", MediaType.TV_EPISODE, "/mnt/tv/The Mandalorian/S01E02.mkv", "S01E02.mkv", 
                     2150000000, ".mkv", show_name="The Mandalorian", season=1, episode=2, episode_title="Chapter 2: The Child"),
        ]
    }
    
    return MediaLibrary(
        movies=movies,
        tv_shows=tv_shows,
        last_scan=time.time(),
        total_items=len(movies) + sum(len(eps) for eps in tv_shows.values())
    )


def _browse_all_media(library, search=None):
    """Browse all media types."""
    console.print("📚 Media Library Overview", style="bold cyan")
    console.print()
    
    # Summary statistics
    movie_count = len(library.movies)
    show_count = len(library.tv_shows)
    episode_count = sum(len(eps) for eps in library.tv_shows.values())
    
    console.print(f"📊 Library Statistics:", style="bold blue")
    console.print(f"  Movies: {movie_count}")
    console.print(f"  TV Shows: {show_count}")
    console.print(f"  Episodes: {episode_count}")
    console.print(f"  Total Items: {library.total_items}")
    console.print()
    
    # Show top movies
    console.print("🎬 Movies (Top 5):", style="bold yellow")
    _show_movies_table(library, search, limit=5)
    console.print()
    
    # Show TV shows
    console.print("📺 TV Shows:", style="bold yellow")
    _show_tv_shows_table(library, search)
    console.print()
    
    console.print("💡 Use --type movie or --type tv to browse specific media types")
    console.print("💡 Use --search to filter results")


def _browse_movies(library, search=None):
    """Browse movies with detailed view."""
    console.print("🎬 Movie Browser", style="bold cyan")
    console.print()
    
    _show_movies_table(library, search)
    console.print()
    
    movie_count = len(library.movies)
    if search:
        filtered = library.search_movies(search)
        console.print(f"Showing {len(filtered)} of {movie_count} movies matching '{search}'")
    else:
        console.print(f"Showing all {movie_count} movies")


def _browse_tv_shows(library, search=None):
    """Browse TV shows with detailed view."""
    console.print("📺 TV Show Browser", style="bold cyan")
    console.print()
    
    _show_tv_shows_table(library, search)
    console.print()
    
    show_count = len(library.tv_shows)
    if search:
        filtered = library.search_shows(search)
        console.print(f"Showing {len(filtered)} of {show_count} TV shows matching '{search}'")
    else:
        console.print(f"Showing all {show_count} TV shows")


def _show_movies_table(library, search=None, limit=None):
    """Display movies in a formatted table."""
    movies = library.search_movies(search) if search else library.get_all_movies_sorted()
    
    if limit:
        movies = movies[:limit]
    
    if not movies:
        console.print("No movies found", style="dim")
        return
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Title", style="cyan", width=40)
    table.add_column("Size", style="green", width=12)
    table.add_column("Format", style="yellow", width=8)
    table.add_column("Location", style="dim", width=50)
    
    for movie in movies:
        # Format file size
        size_mb = movie.file_size / (1024 * 1024)
        if size_mb >= 1000:
            size_str = f"{size_mb/1024:.1f} GB"
        else:
            size_str = f"{size_mb:.0f} MB"
        
        # Format extension
        ext = movie.file_extension.upper()[1:]  # Remove dot and uppercase
        
        # Truncate location if too long
        location = movie.source_path
        if len(location) > 50:
            location = "..." + location[-47:]
        
        table.add_row(
            movie.title,
            size_str,
            ext,
            location
        )
    
    console.print(table)


def _show_tv_shows_table(library, search=None):
    """Display TV shows in a formatted table."""
    show_names = library.search_shows(search) if search else library.get_all_shows_sorted()
    
    if not show_names:
        console.print("No TV shows found", style="dim")
        return
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Show Name", style="cyan", width=30)
    table.add_column("Episodes", style="green", width=10)
    table.add_column("Seasons", style="yellow", width=8)
    table.add_column("Total Size", style="blue", width=12)
    table.add_column("Sample Episode", style="dim", width=30)
    
    for show_name in show_names:
        episodes = library.get_show_episodes(show_name)
        
        # Calculate statistics
        episode_count = len(episodes)
        seasons = set(ep.season for ep in episodes if ep.season)
        season_count = len(seasons)
        total_size = sum(ep.file_size for ep in episodes)
        
        # Format total size
        size_gb = total_size / (1024 * 1024 * 1024)
        if size_gb >= 1:
            size_str = f"{size_gb:.1f} GB"
        else:
            size_str = f"{total_size / (1024 * 1024):.0f} MB"
        
        # Get sample episode
        sample_ep = episodes[0] if episodes else None
        sample_title = sample_ep.episode_title if sample_ep and sample_ep.episode_title else "N/A"
        if len(sample_title) > 30:
            sample_title = sample_title[:27] + "..."
        
        table.add_row(
            show_name,
            str(episode_count),
            str(season_count),
            size_str,
            sample_title
        )
    
    console.print(table)


@main.command()
@click.option('--interactive', is_flag=True, default=True, help='Interactive mode (default)')
@click.option('--dry-run', is_flag=True, help='Show what would be synced without actually syncing')
@click.option('--movie', help='Movie title to sync')
@click.option('--show', help='TV show name to sync')
@click.option('--season', type=int, help='Season number (use with --show)')
@click.option('--episode', type=int, help='Episode number (use with --show and --season)')
@click.option('--profile', help='Configuration profile to use')
@click.option('--bandwidth', type=int, help='Bandwidth limit in KB/s')
@click.option('--verify', is_flag=True, default=True, help='Verify file integrity (default: enabled)')
@click.option('--no-verify', is_flag=True, help='Skip file integrity verification')
@click.pass_context
def sync(ctx, interactive, dry_run, movie, show, season, episode, profile, bandwidth, verify, no_verify):
    """Sync selected media to local storage."""
    # Handle verification flags
    if no_verify:
        verify = False
    
    # Load media library
    library = _load_discovered_library()
    
    if not library or library.total_items == 0:
        console.print("❌ No media library found", style="red")
        console.print("Run 'plexsync discover' first to scan your media sources")
        return
    
    # Store library in context for downloaded media management
    ctx.ensure_object(dict)
    ctx.obj['library'] = library

    # Handle specific media selection (legacy mode)
    if movie or show:
        console.print("🚀 PlexSync Transfer", style="bold green")
        console.print()
        
        if dry_run:
            console.print("🔍 Dry run mode enabled - no files will be transferred", style="yellow")
            console.print()
        
        # Show what would be synced
        if movie:
            console.print(f"📽️  Movie: {movie}")
        elif show:
            show_text = f"📺 TV Show: {show}"
            if season:
                show_text += f" Season {season}"
            if episode:
                show_text += f" Episode {episode}"
            console.print(show_text)
        
        console.print()
        
        selected_item = None
        
        if movie:
            # Search for the movie
            matches = library.search_movies(movie)
            if not matches:
                console.print(f"❌ No movie found matching '{movie}'", style="red")
                console.print("Available movies:")
                for m in library.get_all_movies_sorted()[:5]:
                    console.print(f"  • {m.title}")
                return
            elif len(matches) > 1:
                console.print(f"⚠️  Multiple movies found matching '{movie}':", style="yellow")
                for i, m in enumerate(matches):
                    console.print(f"  {i+1}. {m.title}")
                selected_item = matches[0]
                console.print(f"Using first match: {selected_item.title}")
            else:
                selected_item = matches[0]
        
        elif show:
            # Search for the TV show
            show_matches = library.search_shows(show)
            if not show_matches:
                console.print(f"❌ No TV show found matching '{show}'", style="red")
                console.print("Available TV shows:")
                for s in library.get_all_shows_sorted():
                    console.print(f"  • {s}")
                return
            
            show_name = show_matches[0]
            episodes = library.get_show_episodes(show_name)
            
            # Filter by season/episode if specified
            if season:
                episodes = [ep for ep in episodes if ep.season == season]
                if not episodes:
                    console.print(f"❌ No episodes found for season {season}", style="red")
                    return
            
            if episode:
                episodes = [ep for ep in episodes if ep.episode == episode]
                if not episodes:
                    console.print(f"❌ Episode {episode} not found", style="red")
                    return
            
            if len(episodes) == 1:
                selected_item = episodes[0]
            else:
                console.print(f"⚠️  Multiple episodes selected ({len(episodes)} episodes)", style="yellow")
                
                # Show interactive episode selection
                selected_episodes = _interactive_episode_selection(episodes, show_name, season)
                
                if not selected_episodes:
                    console.print("❌ No episodes selected for sync", style="red")
                    return
                
                if len(selected_episodes) == 1:
                    selected_item = selected_episodes[0]
                else:
                    # Batch sync multiple selected episodes
                    _batch_sync_episodes(selected_episodes, dry_run, bandwidth, verify, confirmed=False)
                    return  # Exit after batch sync
        
        if selected_item:
            console.print(f"🎯 Selected: {selected_item.title}")
            if selected_item.media_type == MediaType.TV_EPISODE:
                console.print(f"    Show: {selected_item.show_name}")
                console.print(f"    Season {selected_item.season}, Episode {selected_item.episode}")
            console.print(f"    Size: {selected_item.file_size / (1024*1024*1024):.1f} GB")
            console.print(f"    Location: {selected_item.source_path}")
            console.print()
            
            # Perform actual sync with the selected item
            _perform_real_sync(dry_run, bandwidth, verify, selected_item)
        
    else:
        # Interactive mode - use the new immersive experience
        _interactive_sync_flow(library, dry_run, bandwidth, verify)


def _interactive_sync_flow(library: MediaLibrary, dry_run: bool = False, bandwidth: int = None, verify: bool = True):
    """Execute the new immersive interactive sync experience."""
    # Create the interactive sync manager
    interactive_manager = InteractiveSyncManager(library)
    
    # Start the interactive flow
    wants_to_sync = interactive_manager.start_interactive_flow()
    
    if not wants_to_sync:
        console.print("❌ Sync cancelled", style="yellow")
        return
    
    # Get the user's selections
    selections = interactive_manager.get_selections()
    
    # Execute sync based on selections
    if selections.selected_movies:
        for movie in selections.selected_movies:
            console.print(f"🎬 Syncing movie: {movie.title}")
            _perform_real_sync(dry_run, bandwidth, verify, movie)
    
    if selections.selected_episodes:
        # Use existing batch sync for episodes - already confirmed in interactive flow
        _batch_sync_episodes(selections.selected_episodes, dry_run, bandwidth, verify, confirmed=True)
    
    if selections.selected_show and not selections.selected_episodes:
        console.print(f"📺 Selected show: {selections.selected_show}")
        console.print("⚠️  Episode selection not yet implemented - coming in Phase 2!", style="yellow")


def _perform_real_sync(dry_run: bool = False, bandwidth: int = None, verify: bool = True, selected_item = None):
    """Perform actual file synchronization with real media files."""
    import time
    from rich.live import Live
    from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn, TransferSpeedColumn
    
    if not selected_item:
        console.print("❌ No media item selected for sync", style="red")
        return
    
    console.print("🚀 File Synchronization", style="bold green")
    console.print()
    
    # Check if source file exists
    if not os.path.exists(selected_item.source_path):
        console.print(f"❌ Source file not found: {selected_item.source_path}", style="red")
        return
    
    # Get file size
    try:
        file_size = os.path.getsize(selected_item.source_path)
        console.print(f"📁 File size: {file_size / (1024*1024*1024):.2f} GB ({file_size:,} bytes)")
    except OSError:
        console.print("⚠️  Could not determine file size", style="yellow")
        file_size = 0
    
    # Set up destination path - use a local sync directory
    sync_dir = os.path.expanduser("~/PlexSync")
    if not os.path.exists(sync_dir):
        os.makedirs(sync_dir, exist_ok=True)
    
    filename = os.path.basename(selected_item.source_path)
    dest_file = os.path.join(sync_dir, filename)
    
    console.print("⚙️  Sync Configuration:", style="bold blue")
    console.print(f"  Source: {selected_item.source_path}")
    console.print(f"  Destination: {dest_file}")
    console.print(f"  Dry Run: {'Yes' if dry_run else 'No'}")
    console.print(f"  Bandwidth Limit: {bandwidth} KB/s" if bandwidth else "  Bandwidth Limit: Unlimited")
    console.print(f"  Integrity Verification: {'Yes' if verify else 'No'}")
    console.print()
    
    if dry_run:
        console.print("🔍 Dry run mode - no files will be transferred", style="yellow")
        console.print("✅ Dry run completed successfully!", style="green")
        console.print(f"  📊 Would transfer: {file_size:,} bytes")
        console.print(f"  📁 From: {selected_item.source_path}")
        console.print(f"  📁 To: {dest_file}")
        return
    
    # Check if destination already exists
    if os.path.exists(dest_file):
        console.print(f"⚠️  Destination file already exists: {dest_file}", style="yellow")
        dest_size = os.path.getsize(dest_file)
        if dest_size == file_size:
            console.print(f"   Same size ({dest_size:,} bytes) - skipping transfer", style="yellow")
            console.print("✅ File already synchronized!", style="green")
            return
        else:
            console.print(f"   Different size (existing: {dest_size:,}, source: {file_size:,}) - will overwrite")
        console.print()
    
    # Create sync options
    sync_options = SyncOptions(
        bandwidth_limit=bandwidth,
        dry_run=False,
        checksum=verify,
        verbose=True
    )
    
    # Create sync engine
    sync_engine = SyncEngine(sync_options)
    
    # Set up progress tracking
    progress_data = {"bytes_transferred": 0, "last_update": time.time()}
    
    def progress_callback(progress: SyncProgress):
        progress_data["bytes_transferred"] = progress.bytes_transferred
        progress_data["last_update"] = time.time()
    
    sync_engine.set_progress_callback(progress_callback)
    
    # Start the sync operation with progress display
    console.print("🚀 Starting sync operation...", style="bold blue")
    
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TextColumn("•"),
        TransferSpeedColumn(),
        TextColumn("•"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        
        task = progress.add_task(f"Syncing {filename}", total=file_size)
        
        start_time = time.time()
        
        try:
            # Use reliable file copy with progress instead of rsync for now
            # This avoids the rsync signal handling issues
            import shutil
            
            def copy_with_progress(src, dst):
                with open(src, 'rb') as fsrc, open(dst, 'wb') as fdst:
                    copied = 0
                    while True:
                        chunk = fsrc.read(1024 * 1024)  # 1MB chunks for better performance
                        if not chunk:
                            break
                        fdst.write(chunk)
                        copied += len(chunk)
                        progress.update(task, completed=copied)
            
            copy_with_progress(selected_item.source_path, dest_file)
            
            # Create a simple result object
            class SimpleResult:
                def __init__(self):
                    self.success = True
                    self.bytes_transferred = file_size
                    self.checksum_verified = False
                    self.error_message = None
            
            result = SimpleResult()
            
            end_time = time.time()
            duration = end_time - start_time
            
            # Verify integrity if requested
            if verify and os.path.exists(dest_file):
                console.print("🔍 Verifying file integrity...", style="yellow")
                import hashlib
                
                def get_file_hash(filepath):
                    hash_sha256 = hashlib.sha256()
                    with open(filepath, "rb") as f:
                        for chunk in iter(lambda: f.read(4096), b""):
                            hash_sha256.update(chunk)
                    return hash_sha256.hexdigest()
                
                try:
                    source_hash = get_file_hash(selected_item.source_path)
                    dest_hash = get_file_hash(dest_file)
                    
                    if source_hash == dest_hash:
                        console.print("✅ File integrity verified!", style="green")
                        result.checksum_verified = True
                    else:
                        console.print("❌ File integrity check failed!", style="red")
                        result.success = False
                except Exception as e:
                    console.print(f"⚠️  Could not verify integrity: {e}", style="yellow")
            
            # Show results
            if result.success:
                console.print("✅ Sync completed successfully!", style="bold green")
                console.print(f"  📊 Transferred: {file_size:,} bytes")
                if duration > 0:
                    rate = file_size / duration / (1024 * 1024)
                    console.print(f"  ⚡ Average rate: {rate:.1f} MB/s")
                console.print(f"  🕐 Duration: {duration:.2f} seconds")
                if verify and hasattr(result, 'checksum_verified') and result.checksum_verified:
                    console.print("  🔒 Integrity verified")
                    
                # Show destination info
                console.print(f"  📁 Synced to: {dest_file}")
                
            else:
                console.print(f"❌ Sync failed: {getattr(result, 'error_message', 'Unknown error')}", style="red")
                
        except Exception as e:
            console.print(f"❌ Sync operation failed: {e}", style="red")
            console.print("   This might be due to network issues, permission problems, or disk space", style="dim")
    
    console.print()
    console.print("🎉 Sync operation complete!", style="bold green")


def _interactive_episode_selection(episodes: List[MediaItem], show_name: str, season: Optional[int] = None) -> List[MediaItem]:
    """Interactive episode selection interface."""
    from rich.table import Table
    from rich.prompt import Prompt, Confirm
    
    console.print()
    console.print("🎯 Interactive Episode Selection", style="bold cyan")
    console.print(f"Show: {show_name}")
    if season:
        console.print(f"Season: {season}")
    console.print()
    
    # Sort episodes by season and episode number
    sorted_episodes = sorted(episodes, key=lambda ep: (ep.season or 0, ep.episode or 0))
    
    # Create episodes table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("#", style="dim", width=4)
    table.add_column("Episode", style="cyan", width=10)
    table.add_column("Title", style="green", width=50)
    table.add_column("Size", style="yellow", width=10)
    table.add_column("Status", style="blue", width=12)
    
    # Check which episodes are already synced
    sync_dir = os.path.expanduser("~/PlexSync")
    
    for i, episode in enumerate(sorted_episodes, 1):
        # Check if already synced
        filename = os.path.basename(episode.source_path)
        dest_file = os.path.join(sync_dir, filename)
        
        if os.path.exists(dest_file):
            dest_size = os.path.getsize(dest_file)
            if dest_size == episode.file_size:
                status = "✅ Synced"
            else:
                status = "⚠️  Partial"
        else:
            status = "⬜ Not synced"
        
        episode_info = f"S{episode.season:02d}E{episode.episode:02d}" if episode.season and episode.episode else "N/A"
        size_gb = episode.file_size / (1024*1024*1024)
        
        table.add_row(
            str(i),
            episode_info,
            episode.episode_title or episode.title,
            f"{size_gb:.2f} GB",
            status
        )
    
    console.print(table)
    console.print()
    
    # Selection options
    console.print("📋 Selection Options:", style="bold yellow")
    console.print("  • Enter episode numbers (e.g., 1,3,5-8)")
    console.print("  • Type 'all' to select all episodes")
    console.print("  • Type 'new' to select only unsynced episodes")
    console.print("  • Type 'none' or press Enter to cancel")
    console.print()
    
    # Get user selection
    try:
        selection = Prompt.ask("Select episodes to sync", default="new")
        
        if not selection or selection.lower() == 'none':
            return []
        
        if selection.lower() == 'all':
            return sorted_episodes
        
        if selection.lower() == 'new':
            # Select only unsynced episodes
            new_episodes = []
            for episode in sorted_episodes:
                filename = os.path.basename(episode.source_path)
                dest_file = os.path.join(sync_dir, filename)
                
                if not os.path.exists(dest_file):
                    new_episodes.append(episode)
                else:
                    # Check if sizes match
                    dest_size = os.path.getsize(dest_file)
                    if dest_size != episode.file_size:
                        new_episodes.append(episode)
            
            if not new_episodes:
                console.print("✅ All episodes are already synced!", style="green")
                return []
            
            return new_episodes
        
        # Parse number ranges and individual numbers
        selected_episodes = []
        parts = selection.split(',')
        
        for part in parts:
            part = part.strip()
            if '-' in part:
                # Range like "5-8"
                try:
                    start, end = part.split('-')
                    start_idx = int(start.strip()) - 1  # Convert to 0-based
                    end_idx = int(end.strip()) - 1
                    
                    for i in range(start_idx, end_idx + 1):
                        if 0 <= i < len(sorted_episodes):
                            selected_episodes.append(sorted_episodes[i])
                except ValueError:
                    console.print(f"⚠️  Invalid range: {part}", style="yellow")
            else:
                # Individual number
                try:
                    idx = int(part) - 1  # Convert to 0-based
                    if 0 <= idx < len(sorted_episodes):
                        selected_episodes.append(sorted_episodes[idx])
                    else:
                        console.print(f"⚠️  Invalid episode number: {part}", style="yellow")
                except ValueError:
                    console.print(f"⚠️  Invalid selection: {part}", style="yellow")
        
        # Remove duplicates while preserving order
        seen = set()
        unique_selected = []
        for episode in selected_episodes:
            if episode not in seen:
                seen.add(episode)
                unique_selected.append(episode)
        
        return unique_selected
        
    except KeyboardInterrupt:
        console.print("\n❌ Selection cancelled", style="red")
        return []
    except Exception as e:
        console.print(f"❌ Selection error: {e}", style="red")
        return []


def _batch_sync_episodes(episodes: List[MediaItem], dry_run: bool = False, bandwidth: int = None, verify: bool = True, confirmed: bool = False):
    """Batch sync multiple episodes with progress tracking."""
    console.print()
    console.print("🎬 Batch Episode Sync", style="bold green")
    console.print()
    
    total_episodes = len(episodes)
    total_size = sum(ep.file_size for ep in episodes)
    
    console.print(f"📺 Syncing {total_episodes} episodes")
    console.print(f"📦 Total size: {total_size / (1024*1024*1024):.2f} GB")
    console.print()
    
    # Confirm batch sync only if not already confirmed
    if not confirmed and not dry_run:
        from rich.prompt import Confirm
        if not Confirm.ask(f"Continue with syncing {total_episodes} episodes? [Y/n]", default=True):
            console.print("❌ Batch sync cancelled", style="red")
            return
    
    success_count = 0
    failed_episodes = []
    successful_episodes = []
    
    for i, episode in enumerate(episodes, 1):
        console.print(f"🎬 [{i}/{total_episodes}] {episode.title}")
        console.print(f"    Season {episode.season}, Episode {episode.episode}")
        console.print(f"    Size: {episode.file_size / (1024*1024*1024):.2f} GB")
        console.print()
        
        # Perform sync for this episode
        try:
            _perform_real_sync(dry_run, bandwidth, verify, episode)
            success_count += 1
            successful_episodes.append(episode)
            console.print(f"✅ Episode {i} completed successfully", style="green")
        except Exception as e:
            failed_episodes.append((episode, str(e)))
            console.print(f"❌ Episode {i} failed: {e}", style="red")
        
        console.print()
    
    # Show batch summary
    console.print("📊 Batch Sync Summary:", style="bold blue")
    console.print(f"  ✅ Successful: {success_count}/{total_episodes} episodes")
    console.print(f"  ❌ Failed: {len(failed_episodes)}/{total_episodes} episodes")
    
    # Calculate total synced size (only successful episodes)
    total_synced_size = sum(ep.file_size for ep in successful_episodes)
    console.print(f"  📦 Total synced: {total_synced_size / (1024*1024*1024):.2f} GB")
    
    if failed_episodes:
        console.print()
        console.print("Failed episodes:", style="red")
        for episode, error in failed_episodes:
            console.print(f"  • {episode.title}: {error}", style="red")
    
    console.print()
    console.print("🎉 Batch sync complete!", style="bold green")


@main.command()
@click.option('--show', is_flag=True, help='Show current configuration')
@click.option('--edit', is_flag=True, help='Edit configuration interactively')
@click.option('--validate', is_flag=True, help='Validate configuration')
@click.option('--init', is_flag=True, help='Initialize configuration with defaults')
@click.option('--profile', help='Configuration profile to use')
@click.pass_context
def config(ctx, show, edit, validate, init, profile):
    """Manage PlexSync configuration."""
    console.print("⚙️  Configuration Management", style="bold blue")
    console.print()
    
    config_manager = get_config_manager()
    
    if init:
        console.print("🔧 Initializing default configuration...")
        config_manager._create_default_config()
        config_manager.save_config()
        console.print("✅ Default configuration created")
        console.print()
        
        # Show configured sources
        active_config = config_manager.get_active_profile()
        if active_config:
            console.print("📂 Configured media sources:")
            for source in active_config.sources:
                status = "✅" if os.path.exists(source.base_path) else "❌"
                console.print(f"  {status} {source.name}: {source.base_path}")
        console.print()
        
    elif show:
        active_config = config_manager.get_active_profile()
        if not active_config:
            console.print("❌ No active configuration found", style="red")
            return
        
        console.print(f"📄 Active Profile: {active_config.name}", style="bold")
        console.print()
        
        # Show sources
        console.print("📂 Media Sources:", style="yellow")
        for source in active_config.sources:
            status_icon = "✅" if source.enabled else "❌"
            console.print(f"  {status_icon} {source.name}")
            console.print(f"    Path: {source.base_path}")
            console.print(f"    Type: {source.media_type}")
            console.print()
        
        # Show destinations
        console.print("🏠 Destinations:", style="yellow")
        console.print(f"  Movies: {active_config.destinations.movies}")
        console.print(f"  TV Shows: {active_config.destinations.tv}")
        console.print()
        
    elif validate:
        console.print("✅ Configuration validation:", style="yellow")
        errors = config_manager.validate_active_profile()
        if errors:
            console.print("❌ Configuration errors found:", style="red")
            for error in errors:
                console.print(f"  • {error}", style="red")
        else:
            console.print("✅ Configuration is valid", style="green")
        console.print()
        
    elif edit:
        console.print("✏️  Interactive configuration editor:", style="yellow")
        console.print("⚠️  Configuration editor not yet implemented", style="yellow")
        console.print("Use 'plexsync config --show' to view current configuration")
        console.print()
        
    else:
        console.print("Available profiles:", style="yellow")
        for profile_name in config_manager.profiles:
            is_active = profile_name == config_manager.active_profile_name
            marker = "→" if is_active else " "
            console.print(f"  {marker} {profile_name}")
        console.print()
        console.print("Use --init, --show, --edit, or --validate to specify action")


@main.command()
@click.option('--detailed', is_flag=True, help='Show detailed status information')
@click.option('--downloaded', is_flag=True, help='Show downloaded media status')
@click.option('--orphaned', is_flag=True, help='Show orphaned files')
@click.pass_context
def status(ctx, detailed, downloaded, orphaned):
    """Show media library and sync status."""
    console.print("📊 PlexSync Status", style="bold blue")
    console.print()
    
    if detailed or downloaded or orphaned:
        # Show downloaded media status
        try:
            from .downloaded import DownloadedMediaManager
            
            # Get downloaded media manager
            downloaded_manager = DownloadedMediaManager(library.config if hasattr(library, 'config') else None)
            status_report = downloaded_manager.get_status_report(library)
            
            summary = status_report['summary']
            percentages = status_report['percentages']
            issues = status_report['issues']
            
            if orphaned:
                # Show only orphaned files
                console.print("👻 Orphaned Files (not in library):", style="bold yellow")
                console.print()
                
                if summary.orphaned:
                    from rich.table import Table
                    table = Table(show_header=True, header_style="bold blue")
                    table.add_column("File", style="dim")
                    table.add_column("Size", justify="right")
                    table.add_column("Downloaded", justify="right")
                    
                    for file in summary.orphaned:
                        table.add_row(
                            file.display_name,
                            f"{file.size_gb:.2f} GB",
                            file.download_date.strftime("%Y-%m-%d") if file.download_date else "Unknown"
                        )
                    
                    console.print(table)
                    console.print()
                    console.print(f"📊 Total orphaned: {len(summary.orphaned)} files • {sum(f.size_gb for f in summary.orphaned):.2f} GB")
                else:
                    console.print("✅ No orphaned files found")
                
            else:
                # Show full downloaded media status
                console.print("📱 Downloaded Media Status:", style="bold blue")
                console.print()
                
                # Summary statistics
                console.print("📊 Summary:")
                console.print(f"  📦 Total Files: {summary.total_files}")
                console.print(f"  💾 Total Size: {summary.total_size_gb:.2f} GB")
                console.print(f"  🎬 Movies: {summary.movie_count} ({summary.movies_size_gb:.2f} GB)")
                console.print(f"  📺 Episodes: {summary.episode_count} ({summary.episodes_size_gb:.2f} GB)")
                console.print()
                
                # Coverage percentages
                console.print("📈 Library Coverage:")
                console.print(f"  🎬 Movies: {percentages['movies']:.1f}% downloaded")
                console.print(f"  📺 Episodes: {percentages['episodes']:.1f}% downloaded")
                console.print()
                
                # Issues
                if issues['partial_count'] > 0 or issues['corrupted_count'] > 0 or issues['orphaned_count'] > 0:
                    console.print("⚠️  Issues Found:", style="bold yellow")
                    if issues['partial_count'] > 0:
                        console.print(f"  ⚠️  Partial Downloads: {issues['partial_count']} files")
                    if issues['corrupted_count'] > 0:
                        console.print(f"  ❌ Corrupted Files: {issues['corrupted_count']} files")
                    if issues['orphaned_count'] > 0:
                        console.print(f"  👻 Orphaned Files: {issues['orphaned_count']} files")
                    console.print()
                else:
                    console.print("✅ No issues found with downloaded files")
                    console.print()
                
                # Detailed view
                if detailed:
                    console.print("📋 Detailed File List:", style="bold blue")
                    console.print()
                    
                    from rich.table import Table
                    
                    if summary.movies:
                        console.print("🎬 Movies:", style="bold")
                        table = Table(show_header=True, header_style="bold blue")
                        table.add_column("Title", style="dim")
                        table.add_column("Size", justify="right")
                        table.add_column("Status", justify="center")
                        table.add_column("Downloaded", justify="right")
                        
                        for movie in summary.movies:
                            status_icon = "✅" if movie.status.value == "complete" else "⚠️"
                            table.add_row(
                                movie.display_name,
                                f"{movie.size_gb:.2f} GB",
                                f"{status_icon} {movie.status.value.title()}",
                                movie.download_date.strftime("%Y-%m-%d") if movie.download_date else "Unknown"
                            )
                        
                        console.print(table)
                        console.print()
                    
                    if summary.episodes:
                        console.print("📺 Episodes:", style="bold")
                        table = Table(show_header=True, header_style="bold blue")
                        table.add_column("Episode", style="dim")
                        table.add_column("Size", justify="right")
                        table.add_column("Status", justify="center")
                        table.add_column("Downloaded", justify="right")
                        
                        for episode in summary.episodes:
                            status_icon = "✅" if episode.status.value == "complete" else "⚠️"
                            table.add_row(
                                episode.display_name,
                                f"{episode.size_gb:.2f} GB",
                                f"{status_icon} {episode.status.value.title()}",
                                episode.download_date.strftime("%Y-%m-%d") if episode.download_date else "Unknown"
                            )
                        
                        console.print(table)
                        console.print()
                    
        except Exception as e:
            console.print(f"❌ Error accessing downloaded media: {e}", style="red")
            console.print("💡 Make sure your sync directory is accessible and contains media files")
    
    else:
        # Show regular library status
        console.print("📚 Library Status:", style="bold blue")
        console.print()
        
        # Movies
        if hasattr(library, 'movies') and library.movies:
            console.print(f"🎬 Movies: {len(library.movies)} available")
            
            if detailed:
                # Show sample movies
                console.print("   Sample movies:")
                for i, movie in enumerate(library.movies[:5]):
                    size_gb = movie.file_size / (1024**3)
                    console.print(f"     • {movie.title} ({size_gb:.2f} GB)")
                if len(library.movies) > 5:
                    console.print(f"     ... and {len(library.movies) - 5} more")
        
        # TV Shows
        if hasattr(library, 'tv_shows') and library.tv_shows:
            console.print(f"📺 TV Shows: {len(library.tv_shows)} shows available")
            
            if detailed:
                # Show sample shows
                console.print("   Sample shows:")
                for i, show in enumerate(library.tv_shows[:5]):
                    console.print(f"     • {show}")
                if len(library.tv_shows) > 5:
                    console.print(f"     ... and {len(library.tv_shows) - 5} more")
        
        console.print()
        
        # Show sync directory info
        try:
            from .downloaded import DownloadedMediaManager
            downloaded_manager = DownloadedMediaManager(library.config if hasattr(library, 'config') else None)
            summary = downloaded_manager.get_summary(library)
            
            if summary.total_files > 0:
                console.print(f"💾 Downloaded: {summary.total_files} files ({summary.total_size_gb:.2f} GB)")
            else:
                console.print("💾 Downloaded: No files downloaded yet")
                
        except Exception:
            console.print("💾 Downloaded: Unable to check sync directory")
    
    console.print()


@main.command()
@click.pass_context
def doctor(ctx):
    """Run comprehensive system diagnostics."""
    console.print("🔍 PlexSync System Diagnostics", style="bold cyan")
    console.print()
    
    # Environment validation
    is_ready = show_environment_report()
    
    # Mount point check
    show_mount_report()
    
    # Configuration validation
    console.print("⚙️  Configuration Status", style="bold blue")
    console.print()
    
    config_manager = get_config_manager()
    errors = config_manager.validate_active_profile()
    
    if errors:
        console.print("❌ Configuration Issues:", style="red")
        for error in errors:
            console.print(f"  • {error}", style="red")
    else:
        console.print("✅ Configuration is valid", style="green")
    
    console.print()
    
    # Final summary
    if is_ready and not errors:
        console.print("✅ System is ready for PlexSync operation", style="bold green")
    else:
        console.print("❌ System requires attention before operation", style="bold red")
        console.print("Run the suggested fixes above to resolve issues.")


@main.command()
@click.option('--movies', is_flag=True, help='Browse movies only')
@click.option('--tv', is_flag=True, help='Browse TV shows only')
@click.option('--search', type=str, help='Search downloaded content')
@click.option('--orphaned', is_flag=True, help='Show orphaned files only')
@click.option('--interactive', is_flag=True, default=True, help='Use interactive browser (default)')
@click.pass_context
def downloaded(ctx, movies, tv, search, orphaned, interactive):
    """Browse and manage downloaded media files."""
    console.print()
    console.print("📱 Downloaded Media Browser", style="bold green")
    console.print()
    
    try:
        from .downloaded import DownloadedMediaManager
        from .downloaded_browser import DownloadedMediaBrowserInterface
        
        # Get library from context, or try to load it
        library = None
        if ctx.obj and 'library' in ctx.obj:
            library = ctx.obj['library']
        
        if not library:
            console.print("📦 Loading media library...", style="dim")
            library = _load_discovered_library()
            if library:
                ctx.ensure_object(dict)
                ctx.obj['library'] = library
        
        if not library:
            console.print("❌ No media library available", style="red")
            console.print("💡 Run 'plexsync discover' first to scan your media sources")
            console.print("   Then you can use 'plexsync downloaded' to manage downloaded files")
            return
        
        # Initialize downloaded media manager
        downloaded_manager = DownloadedMediaManager(library.config if hasattr(library, 'config') else None)
        
        if search:
            # Search mode
            console.print(f"🔍 Searching for: '{search}'")
            console.print()
            
            summary = downloaded_manager.get_summary(library)
            all_files = summary.movies + summary.episodes + summary.orphaned
            
            # Use fuzzy search with relevance scoring
            from .search_utils import fuzzy_search_files
            matching_files = fuzzy_search_files(all_files, search)
            
            if not matching_files:
                console.print(f"❌ No files found matching '{search}'", style="red")
                return
            
            # Show results in table
            from rich.table import Table
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Type", width=10)
            table.add_column("Name", style="dim")
            table.add_column("Size", justify="right")
            table.add_column("Status", justify="center")
            table.add_column("Downloaded", justify="right")
            
            for file in matching_files:
                if file in summary.movies:
                    file_type = "🎬 Movie"
                elif file in summary.episodes:
                    file_type = "📺 Episode"
                else:
                    file_type = "👻 Orphaned"
                
                name = file.display_name
                size = f"{file.size_gb:.2f} GB"
                
                if file.status.value == "complete":
                    status = "✅ Complete"
                elif file.status.value == "partial":
                    status = "⚠️ Partial"
                elif file.status.value == "corrupted":
                    status = "❌ Corrupted"
                else:
                    status = f"❓ {file.status.value.title()}"
                
                downloaded = file.download_date.strftime("%Y-%m-%d") if file.download_date else "Unknown"
                
                table.add_row(file_type, name, size, status, downloaded)
            
            console.print(table)
            console.print()
            console.print(f"📊 Found {len(matching_files)} files matching '{search}'")
            
        elif orphaned:
            # Show orphaned files only
            orphaned_files = downloaded_manager.find_orphaned_files(library)
            
            if not orphaned_files:
                console.print("✅ No orphaned files found", style="green")
                return
            
            console.print("👻 Orphaned Files (not in library):", style="bold yellow")
            console.print()
            
            from rich.table import Table
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("File", style="dim")
            table.add_column("Size", justify="right")
            table.add_column("Downloaded", justify="right")
            table.add_column("Location", style="dim")
            
            for file in orphaned_files:
                table.add_row(
                    file.display_name,
                    f"{file.size_gb:.2f} GB",
                    file.download_date.strftime("%Y-%m-%d") if file.download_date else "Unknown",
                    str(file.file_path.parent)
                )
            
            console.print(table)
            console.print()
            console.print(f"📊 Total orphaned: {len(orphaned_files)} files • {sum(f.size_gb for f in orphaned_files):.2f} GB")
            
        elif movies or tv:
            # Show specific media type
            summary = downloaded_manager.get_summary(library)
            
            if movies:
                files_to_show = summary.movies
                title = "🎬 Downloaded Movies"
            else:  # tv
                files_to_show = summary.episodes
                title = "📺 Downloaded TV Episodes"
            
            if not files_to_show:
                console.print(f"❌ No {title.lower()} found", style="red")
                return
            
            console.print(title, style="bold blue")
            console.print()
            
            from rich.table import Table
            table = Table(show_header=True, header_style="bold blue")
            table.add_column("Title", style="dim")
            table.add_column("Size", justify="right")
            table.add_column("Status", justify="center")
            table.add_column("Downloaded", justify="right")
            
            for file in files_to_show:
                if file.status.value == "complete":
                    status = "✅ Complete"
                elif file.status.value == "partial":
                    status = "⚠️ Partial"
                elif file.status.value == "corrupted":
                    status = "❌ Corrupted"
                else:
                    status = f"❓ {file.status.value.title()}"
                
                table.add_row(
                    file.display_name,
                    f"{file.size_gb:.2f} GB",
                    status,
                    file.download_date.strftime("%Y-%m-%d") if file.download_date else "Unknown"
                )
            
            console.print(table)
            console.print()
            
            total_size = sum(f.file_size for f in files_to_show) / (1024**3)
            console.print(f"📊 Total: {len(files_to_show)} files • {total_size:.2f} GB")
            
        else:
            # Interactive browser mode (default)
            if not interactive:
                # Quick status overview
                status_report = downloaded_manager.get_status_report(library)
                summary = status_report['summary']
                
                console.print("📊 Downloaded Media Summary:")
                console.print(f"  🎬 Movies: {summary.movie_count} files ({summary.movies_size_gb:.2f} GB)")
                console.print(f"  📺 Episodes: {summary.episode_count} files ({summary.episodes_size_gb:.2f} GB)")
                console.print(f"  📊 Total: {summary.total_files} files • {summary.total_size_gb:.2f} GB")
                
                if summary.orphaned or summary.partial or summary.corrupted:
                    console.print()
                    console.print("⚠️  Issues Found:", style="yellow")
                    if summary.orphaned:
                        console.print(f"  👻 Orphaned: {len(summary.orphaned)} files")
                    if summary.partial:
                        console.print(f"  ⚠️  Partial: {len(summary.partial)} files")
                    if summary.corrupted:
                        console.print(f"  ❌ Corrupted: {len(summary.corrupted)} files")
                else:
                    console.print("  ✅ No issues found")
            else:
                # Launch interactive browser
                browser = DownloadedMediaBrowserInterface(console, downloaded_manager)
                browser.show_main_menu(library)
        
    except ImportError as e:
        console.print(f"❌ Downloaded media functionality not available: {e}", style="red")
    except Exception as e:
        console.print(f"❌ Error accessing downloaded media: {e}", style="red")
        console.print("💡 Make sure your sync directory is accessible and contains media files")


@main.group()
@click.pass_context
def system(ctx):
    """
    System management and advanced tools.
    
    Provides comprehensive system settings management, health diagnostics,
    maintenance tools, and advanced configuration options for PlexSync.
    
    \b
    plexsync system settings     Manage system settings
    plexsync system health       System health diagnostics
    plexsync system cache        Cache management tools
    plexsync system logs         Log management tools
    plexsync system backup       Configuration backup/restore
    """
    pass


@system.group()
@click.pass_context  
def settings(ctx):
    """
    Manage PlexSync system settings.
    
    System settings control application behavior, UI preferences,
    performance options, and default paths. These are separate
    from profile-specific configuration.
    
    \b
    plexsync system settings list       Show all settings
    plexsync system settings get KEY    Get specific setting
    plexsync system settings set KEY VALUE   Set specific setting
    plexsync system settings reset     Reset to defaults
    plexsync system settings export    Export settings to file
    plexsync system settings import    Import settings from file
    """
    pass


@settings.command('list')
@click.option('--category', help='Filter by category (ui, performance, paths, logging, security)')
@click.option('--format', 'output_format', type=click.Choice(['table', 'yaml', 'json']), 
              default='table', help='Output format')
@click.pass_context
def list_settings(ctx, category, output_format):
    """Show all system settings."""
    from .settings_manager import get_settings_manager
    
    console.print("⚙️  System Settings", style="bold blue")
    console.print()
    
    settings_manager = get_settings_manager()
    all_settings = settings_manager.get_all_settings()
    
    # Filter by category if specified
    if category:
        filtered_settings = {k: v for k, v in all_settings.items() if k.startswith(f"{category}.")}
        if not filtered_settings:
            console.print(f"❌ No settings found for category: {category}", style="red")
            console.print("Available categories: ui, performance, paths, logging, security")
            return
        all_settings = filtered_settings
    
    if output_format == 'table':
        # Create settings table
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Setting", style="cyan", width=30)
        table.add_column("Value", style="green", width=20)
        table.add_column("Type", style="yellow", width=10)
        table.add_column("Description", style="dim", width=40)
        
        # Setting descriptions
        descriptions = {
            'ui.theme': 'UI color theme (auto, light, dark)',
            'ui.color_output': 'Enable colored console output',
            'ui.progress_bars': 'Show progress bars during operations',
            'ui.banner_display': 'Show PlexSync banner on startup',
            'ui.table_style': 'Table display style',
            'ui.confirmation_prompts': 'Show confirmation prompts',
            'performance.max_workers': 'Maximum parallel workers',
            'performance.cache_enabled': 'Enable result caching',
            'performance.cache_ttl_seconds': 'Cache time-to-live in seconds',
            'performance.health_check_timeout': 'Health check timeout in seconds',
            'performance.mount_check_timeout': 'Mount check timeout in seconds',
            'performance.default_bandwidth_limit': 'Default bandwidth limit (0=unlimited)',
            'performance.parallel_health_checks': 'Run health checks in parallel',
            'paths.config_dir': 'Configuration directory path',
            'paths.cache_dir': 'Cache directory path',
            'paths.log_dir': 'Log directory path',
            'paths.backup_dir': 'Backup directory path',
            'paths.temp_dir': 'Temporary files directory path',
            'logging.level': 'Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)',
            'logging.file_logging': 'Enable logging to file',
            'logging.console_logging': 'Enable console logging',
            'logging.max_file_size_mb': 'Maximum log file size in MB',
            'logging.backup_count': 'Number of log backup files to keep',
            'logging.format_string': 'Log message format string',
            'security.path_redaction': 'Redact sensitive paths in logs',
            'security.encrypt_backups': 'Encrypt configuration backups',
            'security.secure_credential_storage': 'Use secure credential storage',
            'security.auto_update_checks': 'Check for updates automatically',
            'security.anonymous_usage_stats': 'Send anonymous usage statistics'
        }
        
        for key, value in sorted(all_settings.items()):
            value_str = str(value)
            if len(value_str) > 18:
                value_str = value_str[:15] + "..."
            
            value_type = type(value).__name__
            description = descriptions.get(key, "")
            
            table.add_row(key, value_str, value_type, description)
        
        console.print(table)
        console.print()
        console.print(f"📊 Total settings: {len(all_settings)}")
        
    elif output_format == 'yaml':
        import yaml
        console.print(yaml.dump(all_settings, default_flow_style=False, indent=2))
        
    elif output_format == 'json':
        import json
        console.print(json.dumps(all_settings, indent=2))


@settings.command('get')
@click.argument('key')
@click.pass_context
def get_setting(ctx, key):
    """Get a specific setting value."""
    from .settings_manager import get_settings_manager
    
    settings_manager = get_settings_manager()
    value = settings_manager.get_setting(key)
    
    if value is None:
        console.print(f"❌ Setting not found: {key}", style="red")
        console.print("💡 Use 'plexsync system settings list' to see available settings")
        return
    
    console.print(f"⚙️  Setting: [cyan]{key}[/cyan]")
    console.print(f"📄 Value: [green]{value}[/green]")
    console.print(f"📋 Type: [yellow]{type(value).__name__}[/yellow]")


@settings.command('set')
@click.argument('key')
@click.argument('value')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
def set_setting(ctx, key, value, confirm):
    """Set a specific setting value."""
    from .settings_manager import get_settings_manager
    
    settings_manager = get_settings_manager()
    
    # Get current value for comparison
    current_value = settings_manager.get_setting(key)
    if current_value is None:
        console.print(f"❌ Setting not found: {key}", style="red")
        console.print("💡 Use 'plexsync system settings list' to see available settings")
        return
    
    # Convert value to appropriate type
    try:
        # Handle boolean values
        if isinstance(current_value, bool):
            if value.lower() in ('true', '1', 'yes', 'on'):
                typed_value = True
            elif value.lower() in ('false', '0', 'no', 'off'):
                typed_value = False
            else:
                raise ValueError(f"Invalid boolean value: {value}")
        
        # Handle integer values
        elif isinstance(current_value, int):
            typed_value = int(value)
        
        # Handle float values
        elif isinstance(current_value, float):
            typed_value = float(value)
        
        # Handle string values (default)
        else:
            typed_value = value
            
    except ValueError as e:
        console.print(f"❌ Invalid value format: {e}", style="red")
        return
    
    # Show change preview
    console.print("🔄 Setting Change Preview:", style="bold yellow")
    console.print(f"  Setting: [cyan]{key}[/cyan]")
    console.print(f"  Current: [dim]{current_value}[/dim]")
    console.print(f"  New:     [green]{typed_value}[/green]")
    console.print()
    
    # Confirm change
    if not confirm:
        from rich.prompt import Confirm
        if not Confirm.ask("Apply this change?", default=True):
            console.print("❌ Change cancelled", style="yellow")
            return
    
    # Apply setting
    if settings_manager.set_setting(key, typed_value):
        if settings_manager.save_settings():
            console.print(f"✅ Setting '{key}' updated successfully", style="green")
        else:
            console.print("❌ Failed to save settings", style="red")
    else:
        console.print(f"❌ Failed to update setting '{key}'", style="red")


@settings.command('reset')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
def reset_settings(ctx, confirm):
    """Reset all settings to defaults."""
    from .settings_manager import get_settings_manager
    
    console.print("⚠️  Reset All Settings", style="bold red")
    console.print("This will reset ALL system settings to their default values.")
    console.print("Your profile configurations will NOT be affected.")
    console.print()
    
    if not confirm:
        from rich.prompt import Confirm
        if not Confirm.ask("Are you sure you want to reset all settings?", default=False):
            console.print("❌ Reset cancelled", style="yellow")
            return
    
    settings_manager = get_settings_manager()
    if settings_manager.reset_settings():
        console.print("✅ All settings reset to defaults", style="green")
    else:
        console.print("❌ Failed to reset settings", style="red")


@settings.command('export')
@click.argument('file_path', required=False)
@click.option('--format', 'export_format', type=click.Choice(['yaml', 'json']), 
              default='yaml', help='Export format')
@click.pass_context
def export_settings(ctx, file_path, export_format):
    """Export settings to a file."""
    from .settings_manager import get_settings_manager
    import time
    
    if not file_path:
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        file_path = f"plexsync_settings_{timestamp}.{export_format}"
    
    settings_manager = get_settings_manager()
    
    if settings_manager.export_settings(file_path):
        console.print(f"✅ Settings exported to: [cyan]{file_path}[/cyan]", style="green")
        
        # Show file info
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            console.print(f"📊 File size: {file_size} bytes")
    else:
        console.print(f"❌ Failed to export settings to: {file_path}", style="red")


@settings.command('import')
@click.argument('file_path')
@click.option('--confirm', is_flag=True, help='Skip confirmation prompt')
@click.pass_context
def import_settings(ctx, file_path, confirm):
    """Import settings from a file."""
    from .settings_manager import get_settings_manager
    
    if not os.path.exists(file_path):
        console.print(f"❌ File not found: {file_path}", style="red")
        return
    
    console.print("📥 Import Settings", style="bold blue")
    console.print(f"Source file: [cyan]{file_path}[/cyan]")
    console.print()
    console.print("⚠️  This will replace your current system settings.")
    console.print("Your profile configurations will NOT be affected.")
    console.print()
    
    if not confirm:
        from rich.prompt import Confirm
        if not Confirm.ask("Continue with import?", default=False):
            console.print("❌ Import cancelled", style="yellow")
            return
    
    settings_manager = get_settings_manager() 
    if settings_manager.import_settings(file_path):
        console.print("✅ Settings imported successfully", style="green")
        console.print("💡 Use 'plexsync system settings list' to verify imported settings")
    else:
        console.print("❌ Failed to import settings", style="red")


@system.command()
@click.option('--category', type=click.Choice(['connectivity', 'filesystem', 'configuration', 'dependencies', 'performance']),
              help='Filter checks by category')
@click.option('--severity', type=click.Choice(['1', '2', '3', '4']), help='Filter by minimum severity level')
@click.option('--format', 'output_format', type=click.Choice(['table', 'json']), default='table', help='Output format')
@click.option('--parallel/--sequential', default=None, help='Run checks in parallel or sequential mode')
@click.option('--timeout', type=int, help='Timeout for individual checks in seconds')
@click.pass_context
def health(ctx, category, severity, output_format, parallel, timeout):
    """
    Run comprehensive system health diagnostics.
    
    Performs health checks across multiple categories to identify
    potential issues and provide actionable feedback for troubleshooting.
    
    Categories:
    - connectivity: Network and mount connectivity
    - filesystem: Disk space, permissions, path accessibility  
    - configuration: Config and settings validation
    - dependencies: Python version, packages, system binaries
    - performance: System resources and I/O performance
    """
    from .health_checker import get_health_checker, HealthCategory, HealthStatus
    
    console.print("🏥 System Health Diagnostics", style="bold green")
    console.print()
    
    # Parse category filter
    categories = None
    if category:
        categories = [HealthCategory(category)]
    
    # Set timeout if specified
    if timeout:
        settings_manager = get_settings_manager()
        settings_manager.settings.performance.health_check_timeout = timeout
    
    # Run health checks
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("Running health checks...", total=None)
        
        health_checker = get_health_checker()
        report = health_checker.run_all_checks(categories=categories, parallel=parallel)
        
        progress.update(task, completed=100)
    
    console.print()
    
    if output_format == 'json':
        import json
        # Convert report to JSON-serializable format  
        json_data = {
            'overall_health': report.overall_health.value,
            'health_percentage': report.health_percentage,
            'total_checks': report.total_checks,
            'healthy_count': report.healthy_count,
            'warning_count': report.warning_count,
            'critical_count': report.critical_count,
            'unknown_count': report.unknown_count,
            'total_duration_ms': report.total_duration_ms,
            'timestamp': report.timestamp,
            'results': [
                {
                    'name': result.name,
                    'category': result.category.value,
                    'status': result.status.value,
                    'message': result.message,
                    'details': result.details,
                    'fix_suggestion': result.fix_suggestion,
                    'check_duration_ms': result.check_duration_ms,
                    'severity': result.severity
                }
                for result in report.results
            ]
        }
        console.print(json.dumps(json_data, indent=2))
        return
    
    # Display results in table format
    
    # Overall health status
    if report.overall_health == HealthStatus.HEALTHY:
        status_color = "green"
        status_icon = "✅"
    elif report.overall_health == HealthStatus.WARNING:
        status_color = "yellow"
        status_icon = "⚠️"
    elif report.overall_health == HealthStatus.CRITICAL:
        status_color = "red"
        status_icon = "❌"
    else:
        status_color = "dim"
        status_icon = "❓"
    
    console.print(f"🎯 Overall Health: [{status_color}]{status_icon} {report.overall_health.value.upper()}[/{status_color}]", style="bold")
    console.print(f"📊 Health Score: {report.health_percentage:.1f}% ({report.healthy_count}/{report.total_checks} checks passing)")
    console.print(f"⏱️  Total Duration: {report.total_duration_ms:.1f}ms")
    console.print()
    
    # Filter results by severity if specified
    filtered_results = report.results
    if severity:
        min_severity = int(severity)
        filtered_results = [r for r in report.results if r.severity >= min_severity]
    
    if not filtered_results:
        console.print("No health checks match the specified filters.", style="dim")
        return
    
    # Create health results table
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Check", style="cyan", width=25)
    table.add_column("Category", style="blue", width=12)
    table.add_column("Status", width=12)
    table.add_column("Message", style="dim", width=40)
    table.add_column("Duration", style="yellow", width=8)
    
    for result in filtered_results:
        # Status with color and icon
        if result.status == HealthStatus.HEALTHY:
            status_display = "[green]✅ HEALTHY[/green]"
        elif result.status == HealthStatus.WARNING:
            status_display = "[yellow]⚠️  WARNING[/yellow]"
        elif result.status == HealthStatus.CRITICAL:
            status_display = "[red]❌ CRITICAL[/red]"
        else:
            status_display = "[dim]❓ UNKNOWN[/dim]"
        
        # Duration
        duration_str = f"{result.check_duration_ms:.0f}ms" if result.check_duration_ms else "N/A"
        
        # Truncate long messages
        message = result.message
        if len(message) > 38:
            message = message[:35] + "..."
        
        table.add_row(
            result.name,
            result.category.value.title(),
            status_display,
            message,
            duration_str
        )
    
    console.print(table)
    console.print()
    
    # Show summary by category
    console.print("📋 Summary by Category:", style="bold blue")
    categories_summary = {}
    for result in report.results:
        cat = result.category.value
        if cat not in categories_summary:
            categories_summary[cat] = {'healthy': 0, 'warning': 0, 'critical': 0, 'unknown': 0}
        
        if result.status == HealthStatus.HEALTHY:
            categories_summary[cat]['healthy'] += 1
        elif result.status == HealthStatus.WARNING:
            categories_summary[cat]['warning'] += 1
        elif result.status == HealthStatus.CRITICAL:
            categories_summary[cat]['critical'] += 1
        else:
            categories_summary[cat]['unknown'] += 1
    
    for category, counts in sorted(categories_summary.items()):
        total = sum(counts.values())
        healthy_pct = (counts['healthy'] / total * 100) if total > 0 else 0
        
        if counts['critical'] > 0:
            category_color = "red"
        elif counts['warning'] > 0:
            category_color = "yellow"  
        else:
            category_color = "green"
        
        console.print(f"  [{category_color}]{category.title()}[/{category_color}]: "
                     f"{counts['healthy']}/{total} healthy ({healthy_pct:.0f}%)")
    
    console.print()
    
    # Show issues that need attention
    issues = [r for r in report.results if r.needs_attention]
    if issues:
        console.print("🔧 Issues Requiring Attention:", style="bold red")
        for issue in issues:
            severity_indicator = "🔴" if issue.status == HealthStatus.CRITICAL else "🟡"
            console.print(f"  {severity_indicator} {issue.name}: {issue.message}")
            if issue.fix_suggestion:
                console.print(f"     💡 {issue.fix_suggestion}", style="dim")
        console.print()
    
    # Show performance summary
    perf_results = [r for r in report.results if r.category == HealthCategory.PERFORMANCE]
    if perf_results:
        console.print("⚡ Performance Summary:", style="bold cyan")
        for result in perf_results:
            if result.details:
                console.print(f"  {result.name}: {result.details}")
        console.print()
    
    # Final recommendations
    if report.overall_health == HealthStatus.CRITICAL:
        console.print("🚨 Action Required: Critical issues detected that may prevent proper operation.", style="bold red")
    elif report.overall_health == HealthStatus.WARNING:
        console.print("⚠️  Attention Recommended: Some issues detected that may affect performance.", style="bold yellow")
    else:
        console.print("✅ System appears healthy and ready for operation.", style="bold green")


if __name__ == "__main__":
    main() 