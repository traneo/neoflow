"""Dictionary Substitution algorithm for compressing large command outputs.

This module implements a simple dictionary-based compression that finds
frequent repeated patterns in text and replaces them with shorter tokens,
reducing the overall token count while preserving the original information.

The compressed text can be stored in message history (reducing token usage),
but is automatically decompressed before being sent to the LLM, ensuring the
agent sees and responds with normal text.
"""

import re
from dataclasses import dataclass
from collections import Counter


@dataclass
class CompressionResult:
    """Result of dictionary compression."""
    compressed_text: str
    dictionary: dict[str, str]  # token -> original_pattern mapping
    original_size: int  # character count before compression
    compressed_size: int  # character count after compression
    compression_ratio: float  # compressed_size / original_size


def compress_text(
    text: str,
    min_pattern_length: int = 10,
    min_occurrences: int = 3,
    max_dictionary_size: int = 100,
) -> CompressionResult:
    """Apply dictionary substitution compression to text.
    
    Args:
        text: The text to compress
        min_pattern_length: Minimum length of patterns to consider (in characters)
        min_occurrences: Minimum number of times a pattern must appear
        max_dictionary_size: Maximum number of entries in the dictionary
    
    Returns:
        CompressionResult with compressed text and dictionary mapping
    """
    if not text or len(text) < min_pattern_length * min_occurrences:
        # Text too small to benefit from compression
        return CompressionResult(
            compressed_text=text,
            dictionary={},
            original_size=len(text),
            compressed_size=len(text),
            compression_ratio=1.0,
        )
    
    # Find repeated patterns (words, file paths, common phrases)
    patterns = _find_frequent_patterns(
        text,
        min_pattern_length=min_pattern_length,
        min_occurrences=min_occurrences,
    )
    
    # Select top patterns by compression savings
    selected_patterns = _select_best_patterns(
        patterns,
        text,
        max_dictionary_size=max_dictionary_size,
    )
    
    if not selected_patterns:
        # No beneficial patterns found
        return CompressionResult(
            compressed_text=text,
            dictionary={},
            original_size=len(text),
            compressed_size=len(text),
            compression_ratio=1.0,
        )
    
    # Build dictionary with short tokens
    dictionary = {}  # token -> original_pattern
    compressed_text = text
    
    for idx, pattern in enumerate(selected_patterns):
        # Use short tokens: Đ1, Đ2, etc. (Đ is distinctive and unlikely in code)
        token = f"Đ{idx}"
        dictionary[token] = pattern
        # Replace all occurrences of pattern with token
        compressed_text = compressed_text.replace(pattern, token)
    
    original_size = len(text)
    compressed_size = len(compressed_text)
    compression_ratio = compressed_size / original_size if original_size > 0 else 1.0
    
    return CompressionResult(
        compressed_text=compressed_text,
        dictionary=dictionary,
        original_size=original_size,
        compressed_size=compressed_size,
        compression_ratio=compression_ratio,
    )


def decompress_text(compressed_text: str, dictionary: dict[str, str]) -> str:
    """Decompress text using the provided dictionary.
    
    Args:
        compressed_text: The compressed text with tokens
        dictionary: Mapping of tokens to original patterns
    
    Returns:
        Decompressed original text
    """
    if not dictionary:
        return compressed_text
    
    decompressed = compressed_text
    # Replace tokens with original patterns
    # Sort by token number (numerically) to ensure consistent replacement order
    # Extract number from token like "Đ5" -> 5
    def token_sort_key(token: str) -> int:
        try:
            return int(token[1:])  # Skip the 'Đ' character
        except (ValueError, IndexError):
            return 0
    
    for token in sorted(dictionary.keys(), key=token_sort_key, reverse=True):
        pattern = dictionary[token]
        decompressed = decompressed.replace(token, pattern)
    
    return decompressed


def _find_frequent_patterns(
    text: str,
    min_pattern_length: int,
    min_occurrences: int,
) -> list[str]:
    """Find frequently repeated patterns in text.
    
    Looks for:
    - Repeated word sequences
    - File paths
    - Common phrases
    - Repeated code patterns
    """
    patterns = []
    
    # 1. Find repeated multi-word sequences
    words = text.split()
    for window_size in range(10, 2, -1):  # Try longer sequences first
        for i in range(len(words) - window_size + 1):
            phrase = " ".join(words[i : i + window_size])
            if len(phrase) >= min_pattern_length:
                patterns.append(phrase)
    
    # 2. Find repeated file paths (common in command output)
    # Match patterns like /path/to/file or path/to/file.ext
    path_pattern = r'(?:[/\w.-]+/){2,}[\w.-]+'
    paths = re.findall(path_pattern, text)
    patterns.extend(paths)
    
    # 3. Find repeated URL-like patterns
    url_pattern = r'https?://[^\s]+'
    urls = re.findall(url_pattern, text)
    patterns.extend(urls)
    
    # 4. Find repeated identifiers/tokens (common in logs)
    # Match patterns like word_word or word.word or word::word
    identifier_pattern = r'\b\w+(?:[._:]\w+){2,}\b'
    identifiers = re.findall(identifier_pattern, text)
    patterns.extend(identifiers)
    
    # Count occurrences
    pattern_counts = Counter(patterns)
    
    # Filter by minimum occurrences and length
    frequent = [
        pattern
        for pattern, count in pattern_counts.items()
        if count >= min_occurrences and len(pattern) >= min_pattern_length
    ]
    
    return frequent


def _select_best_patterns(
    patterns: list[str],
    text: str,
    max_dictionary_size: int,
) -> list[str]:
    """Select patterns that provide the best compression savings.
    
    Calculates the savings as: (pattern_length - token_length) * occurrences
    Selects top patterns by savings, up to max_dictionary_size.
    Ensures patterns don't overlap to avoid decompression issues.
    """
    if not patterns:
        return []
    
    pattern_savings = []
    for pattern in patterns:
        count = text.count(pattern)
        # Token will be like Đ1, Đ99 (2-3 characters)
        token_length = 3 if len(patterns) > 10 else 2
        savings = (len(pattern) - token_length) * count
        
        # Only keep patterns that actually save space
        if savings > 0:
            pattern_savings.append((pattern, savings, count))
    
    # Sort by savings (descending)
    pattern_savings.sort(key=lambda x: x[1], reverse=True)
    
    # Select non-overlapping patterns
    selected = []
    for pattern, _, _ in pattern_savings:
        if len(selected) >= max_dictionary_size:
            break
        
        # Check if this pattern is a substring of any already-selected pattern
        # or if any selected pattern is a substring of this one
        is_overlapping = False
        for selected_pattern in selected:
            if pattern in selected_pattern or selected_pattern in pattern:
                is_overlapping = True
                break
        
        if not is_overlapping:
            selected.append(pattern)
    
    # Sort by length (descending) to replace longer patterns first
    selected.sort(key=len, reverse=True)
    
    return selected


def should_compress(
    text: str,
    min_size_chars: int = 5000,
    min_size_tokens: int = 1000,
) -> bool:
    """Check if text is large enough to benefit from compression.
    
    Args:
        text: Text to check
        min_size_chars: Minimum character count to consider compression
        min_size_tokens: Minimum estimated token count to consider compression
    
    Returns:
        True if text should be compressed, False otherwise
    """
    if len(text) < min_size_chars:
        return False
    
    # Rough token estimate: ~4 characters per token
    estimated_tokens = len(text) / 4
    return estimated_tokens >= min_size_tokens
