# PlexSync

> **Interactive Media Synchronization**

A robust, interactive CLI tool for syncing individual movies and TV episodes from mounted network drives to local storage with beautiful selection interface, bulletproof error handling, and enterprise-grade reliability.

## 🎯 Features

- **Interactive Selection**: Browse and select individual movies or TV episodes
- **Smart Discovery**: Automatically catalogs media across multiple source folders  
- **Unified Listings**: Combines Movies/Movies2 and TV/TV2 into sorted alphabetical lists
- **Search & Autocomplete**: Quick filtering and selection with fuzzy matching
- **Bulletproof Transfers**: Automatic recovery from network failures and connection drops
- **Progress Tracking**: Beautiful terminal interface with real-time transfer progress
- **Resume Capability**: Interrupted transfers resume from exact byte position
- **Data Integrity**: SHA-256 checksums and configurable validation
- **Cross-Platform**: Linux, macOS, and Windows support
- **Rsync Backend**: Built on battle-tested rsync with optimizations

## 📋 Success Metrics

PlexSync is designed to meet enterprise-grade reliability standards for individual file transfers:

- **MTBF**: ≥ 30 days continuous operation
- **Recovery Time**: ≤ 60 seconds after connection loss
- **Data Integrity**: 100% bit-for-bit accuracy with ≤ 10⁻⁶ corruption rate
- **UI Responsiveness**: < 100ms for media browsing with 10,000+ items
- **Discovery Speed**: < 5 seconds to scan 1,000+ media items per source

## 🚀 Quick Start

### Prerequisites

- Python 3.8 or higher
- rsync 3.1.0+ (3.2.0+ recommended)
- Network-mounted media drives (typically in `/mnt/media`)

### Installation

```bash
# Clone the repository
git clone https://github.com/plexsync/plexsync.git
cd plexsync

# Install dependencies
pip install -e .

# Or install with pipx (recommended)
pipx install plexsync
```

### Basic Usage

```bash
# Check system compatibility
plexsync --check-compat

# Discover and catalog your media
plexsync discover

# Browse and select media interactively
plexsync browse

# Sync a specific movie
plexsync sync --movie "Avatar"

# Sync TV show episodes
plexsync sync --show "Breaking Bad" --season 1

# Run diagnostics
plexsync doctor

# NEW: Interactive sync experience
plexsync sync  # Immersive guided selection
```

## 🎬 How It Works

### 1. Media Discovery
PlexSync scans your configured media sources and builds a searchable library:

```bash
# Scan all configured sources
plexsync discover

# Scan specific sources only
plexsync discover --sources "Movies Primary,TV Shows Primary"
```

**Example Output:**
```
🔍 Scanning media sources...
  📁 Scanning Movies Primary (/mnt/media/Movies)
    Found 847 movies
  📁 Scanning TV Shows Primary (/mnt/media/TV)
    Found 23 TV shows
✅ Scan complete: 847 movies, 23 TV shows
```

### 2. Interactive Selection
Browse your media with powerful search and selection:

```bash
# Browse all media
plexsync browse

# Browse only movies
plexsync browse --type movie

# Search for specific titles
plexsync browse --search "matrix"
```

**Features:**
- 🎯 **Alphabetical Sorting**: All movies and TV shows sorted for easy browsing
- 🔍 **Fuzzy Search**: Find media even with partial or misspelled titles
- 📺 **Episode Selection**: Choose individual episodes, ranges, or entire seasons
- 📊 **File Info**: See file sizes, quality, and source locations before syncing

### 3. Interactive Sync Experience 🆕
**NEW**: Immersive, guided media selection - no commands to remember!

```bash
# Start the interactive experience
plexsync sync
```

**What you get:**
- 🎯 **Guided Selection**: Step-by-step media type → show → season → episode selection
- 📊 **Sync Status**: Real-time indicators (✅ Synced, ⚠️ Partial, ⬜ Not synced)
- 🎛️ **Flexible Selection**: Individual episodes (1,3,5), ranges (5-8), or smart "new only"
- 🎨 **Beautiful Interface**: Rich terminal tables with colors and professional formatting
- 🔄 **Multi-Season Support**: Select episodes across multiple seasons efficiently
- 🔍 **Fuzzy Search**: Smart matching handles typos and partial titles
- 🎯 **Advanced Filtering**: Filter by year, quality, size, codec automatically
- 📄 **Jump-to-Page**: Direct page navigation for large libraries
- 💾 **Selection Presets**: Save and reuse common filter combinations
- ⌨️ **Keyboard Shortcuts**: Power user features with single-key navigation (`~` random, `?` recommendations, `u` undo)
- 🤖 **Smart Recommendations**: AI-like suggestions based on your viewing patterns
- ↶ **Undo/Redo System**: Complete mistake recovery with action history
- 🧠 **User Learning**: Adaptive interface that learns your preferences over time
- 🚀 **Zero Learning Curve**: Intuitive navigation with [n]ext, [b]ack, [q]uit commands

### 4. Legacy Command-Line Sync
Traditional targeted synchronization still available:

```bash
# Sync a single movie
plexsync sync --movie "The Matrix"

# Sync a TV show season
plexsync sync --show "Game of Thrones" --season 1

# Sync a specific episode
plexsync sync --show "Breaking Bad" --season 2 --episode 5
```

## 🏗️ Architecture

### Media Discovery System

```
Media Sources (Multiple)          Media Library (Unified)
├── /mnt/media/Movies       ─┐
├── /mnt/media/Movies2      ─┤──→ Movies: [sorted alphabetically]
├── /mnt/media/TV          ─┤    TV Shows: {
└── /mnt/media/TV2         ─┘      "Show Name": [episodes sorted by S/E]
                                 }
```

### Core Components

```
src/plexsync/
├── __init__.py           # Success metrics constants
├── cli.py                # Interactive CLI with media commands
├── compatibility.py      # Platform compatibility matrix
├── datasets.py           # Media discovery and selection
├── config/               # Configuration management
├── sync/                 # Individual file sync engine
├── ui/                   # Terminal UI components
├── mount/                # Mount point management
├── integrity/            # Data integrity and checksums
└── utils/                # Utilities and helpers
```

## 🔧 Configuration

### Basic Configuration

```yaml
# ~/.config/plexsync/config.yaml
sources:
  movies:
    - /mnt/media/Movies
    - /mnt/media/Movies2
  tv:
    - /mnt/media/TV
    - /mnt/media/TV2

destinations:
  movies: ~/Media/Movies
  tv: ~/Media/TV

discovery:
  video_extensions: [".mkv", ".mp4", ".avi", ".mov"]
  ignore_patterns: ["sample", "trailer", "extras"]
  scan_depth: 5

sync:
  mode: incremental
  checksum_validation: true
  retry_attempts: 3
  retry_backoff: exponential
```

### Advanced Configuration

```yaml
# Multiple profiles for different setups
profiles:
  home:
    sources:
      movies: ["/mnt/nas/Movies"]
      tv: ["/mnt/nas/TV"]
    destinations:
      movies: "~/Media/Movies"
      tv: "~/Media/TV"
    
  office:
    sources:
      movies: ["/mnt/work-share/media/movies"]
      tv: ["/mnt/work-share/media/tv"]
    destinations:
      movies: "/data/media/movies"
      tv: "/data/media/tv"

# Individual file transfer settings
sync:
  rsync_flags: ["-aAXH", "--info=progress2", "--partial"]
  bandwidth_limit: 0  # 0 = unlimited
  parallel_workers: 1  # Individual files, sequential transfer
  
  # Resume and retry settings
  resume_threshold: 1048576  # Resume files > 1MB
  retry_max_attempts: 5
  retry_backoff_base: 2
  retry_backoff_max: 300

# Media discovery settings
discovery:
  title_cleanup: true
  extract_metadata: true
  cache_results: true
  cache_ttl: 3600  # 1 hour

# Security settings
security:
  ssh_key_path: "~/.ssh/id_rsa"
  path_redaction: true
  
# Logging
logging:
  level: INFO
  file: "~/.local/share/plexsync/logs/plexsync.log"
  max_size: 10MB
  backup_count: 5
```

## 🧪 Testing

### Media Library Test Scenarios

PlexSync includes structured test scenarios for different library sizes:

- **Small** (10 movies, 2 TV shows): Unit testing and CI/CD
- **Medium** (100 movies, 10 TV shows): UI performance validation  
- **Large** (1,000 movies, 50 TV shows): Scale testing and autocomplete performance

### Running Tests

```bash
# Unit tests
pytest tests/

# Test media discovery
plexsync discover --dry-run

# Test with sample data
plexsync config --init
plexsync discover
plexsync browse --type movie
```

## 🔍 Compatibility

### Platform Support

| Platform | Support Level | Notes |
|----------|---------------|-------|
| Linux | Full | Ubuntu 20.04+, CentOS 8+, Arch Linux |
| macOS | Full | macOS 12.0+ (Monterey) |
| Windows | Limited | Windows 10+, limited metadata support |

### Python Versions

- **Supported**: 3.8, 3.9, 3.10, 3.11, 3.12
- **Recommended**: 3.10+ for optimal performance
- **Tested**: All versions in CI/CD pipeline

### Terminal Compatibility

- **Full Support**: Modern terminals with truecolor (iTerm2, modern xterm)
- **Graceful Degradation**: SSH sessions, tmux, screen
- **Fallback**: Plain text for automation/scripts

## 📊 Monitoring & Observability

### Individual Transfer Metrics

- Transfer speed and completion time per file
- Retry attempts and success rates
- Network interruption detection and recovery
- File integrity verification results

### Discovery Performance

- Media library scan times per source
- File categorization accuracy rates
- Search and autocomplete response times
- Memory usage during large library scans

### Example Commands

```bash
# View recent transfer history
plexsync status

# Detailed system information
plexsync status --detailed

# Export metrics for analysis
plexsync logs --export --format json > transfer_metrics.json
```

## 🐛 Troubleshooting

### Common Issues

1. **No Media Found During Discovery**
   ```bash
   # Check mount points and permissions
   plexsync doctor
   
   # Verify source paths exist
   ls -la /mnt/media/Movies
   ```

2. **Permission Denied Errors**
   ```bash
   # Check source permissions
   plexsync doctor
   
   # Fix destination permissions if needed
   chmod 755 ~/Media/
   ```

3. **Network Connection Issues**
   ```bash
   # Test basic connectivity
   ping your-nas-server
   
   # Test rsync directly
   rsync -av /mnt/media/Movies/sample/ ~/test-sync/
   ```

### Debug Mode

```bash
# Enable verbose output
plexsync discover --verbose
plexsync sync --movie "Test Movie" --verbose

# Maximum debug information
export PLEXSYNC_DEBUG=1
plexsync sync --show "Test Show"
```

## 🎯 Use Cases

### Individual Movie Syncing
```bash
# Find and sync a specific movie
plexsync browse --search "blade runner"
plexsync sync --movie "Blade Runner 2049 (2017)"
```

### TV Show Management
```bash
# Browse available shows
plexsync browse --type tv

# Sync a complete season
plexsync sync --show "The Mandalorian" --season 1

# Sync specific episodes
plexsync sync --show "Breaking Bad" --season 3 --episode 7
```

### Batch Operations
```bash
# Queue multiple items (future feature)
plexsync queue --movie "Avatar"
plexsync queue --show "Game of Thrones" --season 1
plexsync sync --queue
```

## 🚀 Future Enhancements

- **Queue Management**: Build transfer queues for batch operations
- **Transcoding**: Optional transcoding during transfer
- **Cloud Integration**: Support for cloud storage backends
- **Mobile Companion**: Mobile app for remote queue management
- **Smart Recommendations**: AI-powered content suggestions

## 🤝 Contributing

### Development Setup

```bash
# Clone repository
git clone https://github.com/plexsync/plexsync.git
cd plexsync

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install development dependencies
pip install -e ".[dev]"

# Run tests
python test_phase0.py
pytest

# Code formatting
black src/ tests/
flake8 src/ tests/
```

### Development Guidelines

1. **Individual Focus**: All features should support single-file operations
2. **Interactive First**: Prioritize user experience and selection workflows
3. **Success Metrics**: All features must align with defined success metrics
4. **Testing**: Test across small, medium, and large media libraries
5. **Documentation**: Update docs for all user-facing changes

## 📚 Documentation

- [Success Metrics](docs/SUCCESS_METRICS.md) - Measurable reliability targets for individual transfers
- [Media Discovery](docs/DISCOVERY.md) - How media scanning and cataloging works
- [Selection Interface](docs/SELECTION.md) - Interactive browsing and search
- [Transfer Engine](docs/TRANSFER.md) - Individual file synchronization
- [Configuration Reference](docs/CONFIG.md) - Complete configuration options
- [Troubleshooting Guide](docs/TROUBLESHOOTING.md) - Common issues and solutions

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- [rsync](https://rsync.samba.org/) - The backbone of reliable file synchronization
- [Rich](https://github.com/Textualize/rich) - Beautiful terminal formatting
- [Textual](https://github.com/Textualize/textual) - Modern terminal user interfaces
- [Click](https://click.palletsprojects.com/) - Elegant command-line interfaces

---

**PlexSync** - *Where precision meets elegance in media synchronization* 