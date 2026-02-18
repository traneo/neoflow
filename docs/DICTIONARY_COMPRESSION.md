# Dictionary Substitution Compression

## Overview

Dictionary Substitution compression automatically reduces the token count of large `run_command` outputs before context optimization runs. This can help avoid expensive LLM summarization calls while preserving the full information.

## How It Works

1. **Detection**: When the agent executes a `run_command` action and the output exceeds configured thresholds, compression is triggered.

2. **Compression**: The algorithm:
   - Identifies frequently repeated patterns (file paths, URLs, identifiers, phrases)
   - Builds a dictionary mapping short tokens (Đ0, Đ1, Đ2...) to original patterns
   - Replaces patterns with tokens to compress the text
   - Stores both compressed text and dictionary as message metadata

3. **Storage**: The compressed text is stored in message history, significantly reducing token count for context window calculations.

4. **Decompression**: Before sending messages to the LLM, compressed messages are automatically decompressed back to their original form.

5. **Transparency**: The agent sees only the original, decompressed text and is unaware of the compression, ensuring normal responses.

## Configuration

Add to your environment variables or modify `config.py`:

```bash
# Enable/disable dictionary compression (default: true)
AGENT_COMPRESSION_ENABLED=true

# Minimum tokens to trigger compression (default: 1000)
AGENT_COMPRESSION_MIN_TOKENS=1000

# Minimum characters to trigger compression (default: 5000)
AGENT_COMPRESSION_MIN_CHARS=5000
```

## Configuration in Code

In [neoflow/config.py](neoflow/config.py):

```python
@dataclass
class AgentConfig:
    # ... other settings ...
    
    # Dictionary compression settings
    compression_enabled: bool = True
    compression_min_tokens: int = 1000  # Minimum tokens to trigger compression
    compression_min_chars: int = 5000   # Minimum characters to trigger compression
```

## Compression Algorithm

The algorithm performs the following steps:

1. **Pattern Discovery**: Finds repeated patterns including:
   - Multi-word sequences (10+ words)
   - File paths (`/path/to/file.ext`)
   - URLs (`http://...`)
   - Qualified identifiers (`com.example.Class`)

2. **Pattern Selection**: 
   - Calculates compression savings for each pattern
   - Selects non-overlapping patterns (prevents decompression errors)
   - Prioritizes patterns with highest savings
   - Limits to top 100 patterns

3. **Token Replacement**:
   - Uses distinctive tokens: Đ0, Đ1, Đ2, ... Đ99
   - Replaces longest patterns first
   - Achieves 50-90% size reduction for repetitive output

4. **Decompression**:
   - Simple token-to-pattern substitution
   - Guarantees exact original text recovery
   - Happens transparently before LLM sees the message

## Example

### Before Compression (9,500 characters):
```
/usr/bin/python3 /path/to/script.py
/usr/bin/python3 /path/to/another.py
/usr/bin/python3 /path/to/third.py
Error: Module not found
Error: Module not found
Error: Module not found
Connection to http://localhost:8080 established
Connection to http://localhost:8080 established
... (repeated many times) ...
```

### After Compression (980 characters, 90% reduction):
```
Đ6 Đ4
Đ6 Đ3
Đ6 Đ5
Đ2
Đ2
Đ2
Đ0
Đ0
... (compressed with tokens) ...
```

### Dictionary:
```python
{
    'Đ0': 'Connection to http://localhost:8080 established',
    'Đ1': 'Success: Operation completed successfully',
    'Đ2': 'Error: Module not found',
    'Đ3': '/path/to/another.py',
    'Đ4': '/path/to/script.py',
    'Đ5': '/path/to/third.py',
    'Đ6': '/usr/bin/python3'
}
```

## Benefits

1. **Reduced Token Usage**: 50-90% reduction in token count for repetitive output
2. **Avoid Summarization**: Keeps full information without expensive LLM summarization
3. **Transparent to Agent**: Agent sees original text, responds naturally
4. **No Information Loss**: Perfect decompression guarantees no data loss
5. **Automatic**: Triggers only when beneficial, no manual intervention needed

## When Compression Helps Most

- **Large log outputs** with repeated messages
- **Directory listings** with similar paths
- **Test results** with repeated test names/patterns  
- **API responses** with repeated JSON structures
- **Build outputs** with repeated compiler messages

## Implementation Files

- [neoflow/agent/dictionary_compression.py](neoflow/agent/dictionary_compression.py) - Core compression algorithm
- [neoflow/agent/context_optimizer.py](neoflow/agent/context_optimizer.py) - Integration with message handling
- [neoflow/config.py](neoflow/config.py) - Configuration options
- [tests/test_dictionary_compression.py](tests/test_dictionary_compression.py) - Comprehensive test suite

## Testing

Run tests with:
```bash
PYTHONPATH=/path/to/NeoFlow python3 tests/test_dictionary_compression.py
```

Or with pytest:
```bash
pytest tests/test_dictionary_compression.py -v
```

## Limitations

- Only applies to `run_command` outputs (most common large outputs)
- Requires minimum size thresholds to avoid overhead on small outputs
- Most effective with repetitive patterns (logs, paths, etc.)
- Less effective with unique/random content

## Monitoring

The system logs compression statistics:
```
INFO: Applying dictionary compression to run_command output
INFO: Compression saved 85.2%: 15000 -> 2220 chars
```

Check logs to see compression effectiveness and adjust thresholds if needed.
