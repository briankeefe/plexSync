"""
Search Utilities Module

This module provides shared search functionality for fuzzy matching downloaded media files.
"""

import re
import difflib
from pathlib import Path
from typing import List, Any, Tuple


def clean_filename_for_search(filename: str) -> str:
    """Clean filename to extract meaningful title for search."""
    # Remove file extension
    name = Path(filename).stem
    
    # Remove common patterns: year, quality, codec, release group
    patterns_to_remove = [
        r'\b(19|20)\d{2}\b',  # Years like 1996, 2023
        r'\b(720p|1080p|2160p|4K|HD|HDR|UHD)\b',  # Quality
        r'\b(BluRay|BRRip|DVDRip|WEBRip|HDTV|CAM)\b',  # Source
        r'\b(x264|x265|H264|H265|HEVC|AVC)\b',  # Codecs
        r'\b(AAC|DTS|AC3|TrueHD|Atmos)\b',  # Audio
        r'\[.*?\]',  # Anything in brackets
        r'\-\w+$',  # Release group at end
        r'[._]', # Replace dots and underscores with spaces
    ]
    
    clean_name = name
    for pattern in patterns_to_remove[:-1]:  # All except the last one
        clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
    
    # Replace dots and underscores with spaces (last pattern)
    clean_name = re.sub(r'[._]', ' ', clean_name)
    
    # Clean up extra whitespace
    clean_name = ' '.join(clean_name.split())
    
    return clean_name.strip()


def fuzzy_search_files(files: List[Any], query: str, max_results: int = 20) -> List[Any]:
    """Perform fuzzy search on files with similarity scoring."""
    if not query:
        return []
    
    query_lower = query.lower()
    candidates = []
    
    for file in files:
        # Use cleaned filename for better matching
        clean_name = clean_filename_for_search(file.display_name)
        name_lower = clean_name.lower()
        
        # Calculate similarity scores
        scores = []
        
        # Exact match (highest score)
        if query_lower == name_lower:
            scores.append(1.0)
        
        # Starts with query
        elif name_lower.startswith(query_lower):
            scores.append(0.9)
        
        # Contains query as whole words
        elif f" {query_lower} " in f" {name_lower} ":
            scores.append(0.85)
        
        # Contains query
        elif query_lower in name_lower:
            scores.append(0.7)
        
        # Fuzzy matching using difflib
        similarity = difflib.SequenceMatcher(None, query_lower, name_lower).ratio()
        scores.append(similarity)
        
        # Word-based matching
        query_words = query_lower.split()
        name_words = name_lower.split()
        
        if query_words and name_words:
            word_matches = 0
            for q_word in query_words:
                for n_word in name_words:
                    if q_word == n_word:  # Exact word match
                        word_matches += 1
                        break
                    elif q_word in n_word or n_word in q_word:  # Partial word match
                        word_matches += 0.5
                        break
            
            word_score = word_matches / len(query_words)
            scores.append(word_score)
        
        # Use the best score
        best_score = max(scores) if scores else 0
        
        # Only include if score is above threshold
        if best_score >= 0.3:
            candidates.append((file, best_score, clean_name))
    
    # Sort by score (descending) and return top results
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [file for file, score, clean_name in candidates[:max_results]]


def fuzzy_search_media_items(items: List[Any], query: str, max_results: int = 20) -> List[Any]:
    """Perform fuzzy search on media items with title attribute."""
    if not query:
        return []
    
    query_lower = query.lower()
    candidates = []
    
    for item in items:
        # Use title attribute for media items
        title_lower = item.title.lower()
        
        # Calculate similarity scores
        scores = []
        
        # Exact match (highest score)
        if query_lower == title_lower:
            scores.append(1.0)
        
        # Starts with query
        elif title_lower.startswith(query_lower):
            scores.append(0.9)
        
        # Contains query as whole words
        elif f" {query_lower} " in f" {title_lower} ":
            scores.append(0.85)
        
        # Contains query
        elif query_lower in title_lower:
            scores.append(0.7)
        
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
                    if q_word == t_word:  # Exact word match
                        word_matches += 1
                        break
                    elif q_word in t_word or t_word in q_word:  # Partial word match
                        word_matches += 0.5
                        break
            
            word_score = word_matches / len(query_words)
            scores.append(word_score)
        
        # Use the best score
        best_score = max(scores) if scores else 0
        
        # Only include if score is above threshold
        if best_score >= 0.3:
            candidates.append((item, best_score))
    
    # Sort by score (descending) and return top results
    candidates.sort(key=lambda x: x[1], reverse=True)
    return [item for item, score in candidates[:max_results]]