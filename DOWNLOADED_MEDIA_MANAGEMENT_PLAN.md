# PlexSync Downloaded Media Management - Complete Implementation Plan

## Overview
Add comprehensive management capabilities for already-sync'ed (downloaded) media with real-time file system state detection, full interactive integration, and advanced bulk operations.

## Core Principles
- **File System is Truth**: Always derive state by scanning actual files rather than maintaining state databases
- **Interactive First**: Full integration into existing interactive flows, not just CLI commands  
- **Safety & Confirmation**: Multiple confirmation levels for destructive operations
- **Bulk Operations**: Support for multi-select, batch operations, and "delete all" functionality

---

## **Phase 1: Discovery & Status Foundation**
**Timeline**: 1-2 weeks  
**Goal**: Build the foundation for discovering and reporting on downloaded media

### Core Components

#### 1. **Downloaded Media Scanner**
```python
class DownloadedMediaScanner:
    """Scans sync directory and matches files to library entries."""
    
    def scan_sync_directory(self) -> Dict[str, Any]:
        """Scan and catalog all downloaded files."""
        
    def match_files_to_library(self, files: List[Path], library: MediaLibrary) -> Dict[str, Any]:
        """Match downloaded files back to original library entries."""
        
    def detect_file_status(self, file_path: Path, original_item: MediaItem) -> FileStatus:
        """Determine file status (complete, partial, corrupted, etc.)."""
```

#### 2. **File Status System**
```python
class FileStatus(Enum):
    COMPLETE = "complete"      # Perfect match to source
    PARTIAL = "partial"        # Incomplete transfer
    CORRUPTED = "corrupted"    # Size matches but checksum fails
    ORPHANED = "orphaned"      # No matching library entry
    MODIFIED = "modified"      # File modified after download
```

#### 3. **Enhanced Main Menu Integration**
```
🎬 PlexSync Interactive

📊 Library Status:
  🎬 Movies: 299 available • 15 downloaded (5.0%)
  📺 TV Shows: 56 shows • 23 episodes downloaded
  💾 Downloaded: 12.3 GB total

What would you like to do?

  1. 🎬 Browse & Sync Movies (284 not downloaded)
  2. 📺 Browse & Sync TV Shows (sync more episodes)
  3. 🎭 Browse All Media (mixed selection)
  4. 📱 Manage Downloaded Media (browse • cleanup • organize)
  5. 🔄 Re-sync Corrupted Files (2 need attention)
  6. ⚙️  Settings & Advanced Tools

Select [1-6] (1):
```

### CLI Commands (Phase 1)
```bash
plexsync status --downloaded
plexsync status --detailed
plexsync status --orphaned
```

---

## **Phase 2: Interactive Downloaded Media Browser**
**Timeline**: 1-2 weeks  
**Goal**: Rich interactive interface for browsing and exploring downloaded content

### Interactive Downloaded Management Menu
```
📱 Downloaded Media Management

Current Status:
  🎬 Movies: 15 files (4.2 GB)
  📺 TV Episodes: 23 files (8.1 GB) 
  📊 Total: 38 files • 12.3 GB

What would you like to do?

  1. 🎬 Browse Movies (15 downloaded)
  2. 📺 Browse TV Shows (23 episodes downloaded)
  3. 🔍 Search Downloaded Content
  4. 📊 View Storage Analytics  
  5. 🧹 Cleanup & Management
  6. 🗑️  Delete All Downloaded Media
  7. ⚙️  Organization Tools
  8. 🔙 Back to Main Menu
```

### Interactive Movie Browser with Multi-Select
```
🎬 Downloaded Movies - Multi-Select Mode

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ ☐ │ Title                           │ Size    │ Downloaded │ Status      ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━━┩
│ ☑️ │ 100% Julian Edelman (2019)     │ 2.1 GB  │ 2024-01-15 │ ✅ Complete │
│ ☑️ │ The Matrix (1999)              │ 1.8 GB  │ 2024-01-14 │ ⚠️ Partial  │
│ ☐ │ Inception (2010)               │ 2.9 GB  │ 2024-01-13 │ ✅ Complete │
│ ☑️ │ Avatar (2009)                  │ 3.2 GB  │ 2024-01-12 │ ✅ Complete │
│ ☐ │ Interstellar (2014)            │ 4.1 GB  │ 2024-01-11 │ ✅ Complete │
└───┴─────────────────────────────────┴─────────┴────────────┴─────────────┘

Selected: 3 files • 7.1 GB
Multi-Select: [a]ll, [n]one, [i]nvert, space to toggle • [1-5] to select
Actions: [d]elete selected, [v]erify selected, [ESC] exit multi-select
```

### Batch Selection Commands
```
Selection: [m]ulti-select mode, [*] select all page, [**] select all movies
Quick Actions: [d]elete, [v]erify, [i]nfo • Select file [1-10] or range [1-5,8]

Advanced Selection:
  • Type "1,3,5" to select specific files
  • Type "1-5" to select range  
  • Type "1,3-7,9" for mixed selection
  • Type "*" to select all on current page
  • Type "**" to select all movies
  • Type "partial" to select only partial downloads
  • Type "old" to select files older than 30 days
```

### Individual File Management
```
📁 File Details: 100% Julian Edelman (2019)

File Information:
  📍 Location: /home/brian/PlexSync/100% Julian Edelman (2019) WEBDL-720p.mkv
  📏 Size: 2.12 GB (matches source)
  📅 Downloaded: Jan 15, 2024 at 3:42 PM
  🔒 Integrity: ✅ Verified (SHA256 match)
  📺 Source: /mnt/media/Movies/100% Julian Edelman (2019)/
  ⏱️  Last Accessed: 2 days ago

What would you like to do?

  1. ▶️  Open File Location
  2. 🔍 Verify Integrity 
  3. 🔄 Re-sync from Source
  4. 🗑️  Delete Downloaded File
  5. 📋 View Sync History
  6. 🔙 Back to Browser
```

### CLI Commands (Phase 2)
```bash
plexsync downloaded                    # Interactive browser
plexsync downloaded --movies           # Browse movies only
plexsync downloaded --tv               # Browse TV shows only
plexsync downloaded --search "query"   # Search downloaded content
plexsync downloaded --orphaned         # Show orphaned files
```

---

## **Phase 3: Bulk Operations & File Management**
**Timeline**: 2-3 weeks  
**Goal**: Comprehensive file management operations with safety features and bulk deletion

### Delete All Confirmation Flow
```
🗑️  Delete All Downloaded Media

⚠️  WARNING: This will permanently delete ALL downloaded files

Current Downloaded Media:
  🎬 Movies: 15 files (4.2 GB)
  📺 TV Episodes: 23 files (8.1 GB)
  📊 Total: 38 files • 12.3 GB

This action will:
  ✓ Free up 12.3 GB of storage space
  ✓ Keep your original library intact (source files safe)
  ❌ Require re-downloading if you want files again
  ❌ Cannot be undone

Type "DELETE ALL" to confirm or anything else to cancel: ___
```

### Smart Bulk Selection
```
🧹 Smart Cleanup - Bulk Selection

I found several categories you might want to delete:

  1. ⚠️  Partial Downloads (2 files, 890 MB)
     ☑️ The Matrix (1999) - 1.8 GB partial
     ☑️ Tenet (2020) - 1.1 GB partial

  2. 👻 Orphaned Files (1 file, 1.2 GB)  
     ☑️ Old_Movie_No_Longer_In_Library.mkv

  3. 💤 Old Files (30+ days, 3 files, 4.1 GB)
     ☐ Ancient_Movie_1.mkv (45 days old)
     ☐ Ancient_Movie_2.mkv (52 days old) 
     ☐ Ancient_Movie_3.mkv (67 days old)

  4. 🔄 Duplicate Files (2 groups, 4.2 GB potential savings)
     ☐ Matrix duplicates (keep newer version)
     ☐ Inception duplicates (keep larger version)

Select categories to delete [1,2,3,4] or [a]ll, [c]ustom selection: ___
```

### Bulk Deletion Progress
```
🗑️  Deleting Selected Files

Progress: Deleting 5 files (7.8 GB)

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Status │ File                            │ Size    │ Progress           ┃
┡━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━┩
│ ✅ Done │ 100% Julian Edelman (2019)     │ 2.1 GB  │ ████████████████████ │
│ ✅ Done │ The Matrix (1999)              │ 1.8 GB  │ ████████████████████ │
│ 🔄 Del  │ Avatar (2009)                  │ 3.2 GB  │ ██████████░░░░░░░░░░ │
│ ⏳ Wait │ Tenet (2020)                   │ 1.1 GB  │ ░░░░░░░░░░░░░░░░░░░░ │
│ ⏳ Wait │ Old_Movie_File.mkv             │ 1.2 GB  │ ░░░░░░░░░░░░░░░░░░░░ │
└────────┴─────────────────────────────────┴─────────┴────────────────────┘

⚡ Deleting: Avatar (2009) • 3.2 GB • 67% complete
📊 Total Progress: 3/5 files • 5.1/7.8 GB freed • 2 files remaining

[C] to cancel remaining deletions
```

### Safety Confirmation System
```
🗑️  Confirm Bulk Deletion

You selected 15 files for deletion (8.2 GB total)

⚠️  Safety Check Required:
Since you're deleting more than 5 files or 5GB, please confirm:

1. Type the number of files to delete: _____ (expected: 15)
2. Are you sure you want to delete 8.2 GB? [y/N]: ___
3. Final confirmation - type "DELETE" to proceed: _____

💡 Tip: You can enable "Trust Mode" in settings to skip this for future operations
```

### File Organization System
```
📺 TV Show Organization

Current Structure:
  📁 Archer.S01E01.Mole.Hunt.1080p.Blu-ray.DTS.x264-CtrlHD.mkv
  📁 Breaking Bad S03E07 - One Minute.mkv
  📁 The Office (US) - S02E01 - The Dundies.mkv

Suggested Organization:
  📁 TV Shows/
    └── 📁 Archer (2009)/
        └── 📁 Season 01/
            └── 📄 S01E01 - Mole Hunt.mkv
    └── 📁 Breaking Bad/
        └── 📁 Season 03/
            └── 📄 S03E07 - One Minute.mkv

Organize into structured directories? [Y/n]:
Custom naming pattern? [y/N]:
```

### CLI Commands (Phase 3)
```bash
plexsync manage                        # Interactive management mode
plexsync manage --delete FILE          # Delete specific file
plexsync manage --verify FILE          # Verify file integrity
plexsync manage --re-sync FILE         # Re-download file
plexsync manage --organize             # Organize file structure
plexsync manage --cleanup              # Interactive cleanup mode
plexsync manage --delete-all           # Delete all downloaded media
```

---

## **Phase 4: Advanced Management & Analytics**
**Timeline**: 2-3 weeks  
**Goal**: Intelligent automation, analytics, and advanced management features

### Interactive Storage Analytics
```
📊 Downloaded Media Analytics

Storage Overview:
  ╭─ Total Downloaded ────────────────────────────────────╮
  │ 📦 12.3 GB across 38 files                           │
  │ 🎬 Movies: 4.2 GB (15 files)                         │  
  │ 📺 TV Shows: 8.1 GB (23 episodes)                    │
  ╰───────────────────────────────────────────────────────╯

Usage Patterns:
  📈 Most Downloaded: Breaking Bad (8 episodes)
  ⏰ Most Recent: 100% Julian Edelman (2 days ago)
  🔥 Most Accessed: The Office episodes (daily)
  💤 Least Accessed: Matrix trilogy (30+ days)

Trends:
  📅 This Month: +2.1 GB downloaded
  🗑️  Last Cleanup: 2 weeks ago
  ⚡ Avg Download Speed: 41.2 MB/s

Press [Enter] to continue or [d] for detailed breakdown...
```

### Interactive Duplicate Manager
```
🔍 Duplicate File Detection

Found 2 potential duplicate groups:

Group 1: The Matrix (1999)
  📄 Matrix_1999_1080p.mkv          (2.1 GB) ✅ Complete
  📄 The.Matrix.1999.BluRay.mkv     (2.1 GB) ✅ Complete
  🔍 Content Hash: IDENTICAL
  
  Actions: [k]eep first, keep [s]econd, keep [b]oth, [c]ompare

Group 2: Inception (2010)  
  📄 Inception.2010.1080p.mkv       (2.9 GB) ✅ Complete
  📄 Inception_Director_Cut.mkv     (3.1 GB) ✅ Complete
  🔍 Content Hash: DIFFERENT (likely different versions)
  
  Actions: [k]eep first, keep [s]econd, keep [b]oth, [c]ompare

Process duplicates [1,2] or [a]ll, [s]kip:
```

### Cross-Flow Integration
```
🎬 Movie Selection Results

Found 5 movies matching your criteria:

┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ # │ ✓ │ Title                  │ Year │ Size   │ Quality │ Downloaded    ┃
┡━━━╇━━━╇━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━╇━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━┩
│ 1 │   │ Avatar (2009)          │ 2009 │ 3.2 GB │ 1080p   │ ❌ Not synced │
│ 2 │ ✅ │ Inception (2010)       │ 2010 │ 2.9 GB │ 1080p   │ ✅ Downloaded │
│ 3 │   │ Interstellar (2014)    │ 2014 │ 4.1 GB │ 1080p   │ ❌ Not synced │
│ 4 │ ⚠️ │ The Matrix (1999)      │ 1999 │ 2.1 GB │ 1080p   │ ⚠️ Partial    │
│ 5 │   │ Tenet (2020)           │ 2020 │ 3.8 GB │ 1080p   │ ❌ Not synced │
└───┴───┴────────────────────────┴──────┴────────┴─────────┴───────────────┘

✨ Smart Suggestions:
  • Re-sync #4 (The Matrix) - partial download detected
  • Skip #2 (Inception) - already downloaded and verified

Navigation: [n]ext, [p]revious, [s]earch, [b]ack, [q]uit
Actions: [m]anage downloaded, [r]e-sync partial • Select movies [1,3,5]
```

### CLI Commands (Phase 4)
```bash
plexsync cleanup                       # Smart cleanup wizard
plexsync cleanup --duplicates          # Find and handle duplicates
plexsync cleanup --suggest             # Suggest files to delete
plexsync analytics                     # Show usage analytics
plexsync automate --setup              # Setup automation rules
plexsync automate --run                # Run scheduled tasks
```

---

## **Keyboard Shortcuts & Navigation**

### Multi-Select & Bulk Operations
```
📋 Multi-Select & Bulk Operations Shortcuts

Selection:
  Space       Toggle selection on current item
  A           Select all items on current page  
  Shift+A     Select all items (all pages)
  Ctrl+A      Smart select (partial, old, duplicates)
  N           Select none (clear all selections)
  I           Invert selection
  
Quick Selection:
  1,3,5       Select specific items
  1-5         Select range of items  
  1,3-7,9     Mixed selection
  *           Select all on page
  **          Select all items
  
Bulk Actions:
  D           Delete selected items
  V           Verify selected items
  R           Re-sync selected items
  M           Move/organize selected items
  
Safety:
  Ctrl+Z      Undo last deletion (if trash enabled)
  ESC         Cancel current operation
  ?           Show help
```

---

## **Technical Architecture**

### Core Components
```python
# New modules to be created
src/plexsync/downloaded.py              # Main downloaded media management
src/plexsync/file_operations.py         # File operations with safety
src/plexsync/bulk_operations.py         # Bulk selection and operations
src/plexsync/analytics.py               # Usage analytics and insights
src/plexsync/organization.py            # File organization and structure
```

### Integration Points
- **Enhanced interactive.py** - Add downloaded management flows
- **Extended cli.py** - New commands for downloaded media management
- **Updated datasets.py** - Integration with file system scanning
- **Shared UI components** - Consistent interface patterns

### Key Features
- **Real-time file system scanning** - No persistent state files
- **Content-based matching** - Intelligent file-to-library matching
- **Multi-level confirmations** - Safety for destructive operations
- **Progress tracking** - Real-time feedback for long operations
- **Cross-flow integration** - Seamless navigation between sync and manage modes

---

## **Implementation Timeline**

- **Phase 1**: 1-2 weeks - Core scanning and status foundation
- **Phase 2**: 1-2 weeks - Interactive browser and basic management  
- **Phase 3**: 2-3 weeks - Bulk operations and safety systems
- **Phase 4**: 2-3 weeks - Analytics, automation, and advanced features

**Total estimated time**: 6-10 weeks for complete implementation

---

**Ready for approval to proceed with Phase 1 implementation.** 