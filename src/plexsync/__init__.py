"""
PlexSync - A bulletproof CLI tool for syncing movie and TV files.

A robust, interactive synchronization tool that handles edge cases like
connection loss and provides beautiful progress tracking.
"""

__version__ = "0.1.0"
__author__ = "PlexSync Team"
__email__ = "team@plexsync.dev"

# Success metrics thresholds
MTBF_TARGET_DAYS = 30
RTO_TARGET_SECONDS = 60
CORRUPTION_RATE_THRESHOLD = 1e-6
UI_REFRESH_LATENCY_MS = 100
BANDWIDTH_UTILIZATION_TARGET = 0.8
MEMORY_LIMIT_MB = 500
CPU_UTILIZATION_LIMIT = 0.5 