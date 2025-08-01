#!/usr/bin/env python3
"""
Test script for interactive sync functionality.
Run this to test the new interactive episode selection.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from plexsync.cli import main

if __name__ == "__main__":
    # Test the interactive sync
    sys.argv = [
        'plexsync', 
        'sync', 
        '--show', 'Spongebob Squarepants',
        '--season', '1'
    ]
    main() 