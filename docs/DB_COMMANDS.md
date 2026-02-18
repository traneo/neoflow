# Database Management Commands

## Overview

NeoFlow now includes database management commands to help you maintain your Weaviate collections.

## Commands

### Clear Collections

The `db clear` command allows you to delete Weaviate collections.

#### Clear All Collections

To delete all collections in the Weaviate database:

```bash
neoflow db clear
```

This will:
1. Prompt for confirmation (safety feature)
2. Connect to Weaviate
3. List all existing collections
4. Delete each collection
5. Show a success message

**Example output:**
```
Are you sure you want to delete ALL collections? [y/N]: y
Deleting 3 collection(s)...
✓ Deleted: Tickets
✓ Deleted: Comments
✓ Deleted: CodeSnippets
All collections cleared successfully.
```

#### Clear a Specific Collection

To delete only a specific collection:

```bash
neoflow db clear --collection <collection_name>
```

**Examples:**

Clear only the Tickets collection:
```bash
neoflow db clear --collection Tickets
```

Clear only the CodeSnippets collection:
```bash
neoflow db clear --collection CodeSnippets
```

Clear only the Documentation collection:
```bash
neoflow db clear --collection Documentation
```

**Example output:**
```
Are you sure you want to delete the Tickets collection? [y/N]: y
✓ Deleted collection: Tickets
```

## Common Collection Names

Based on the NeoFlow data model, common collection names include:

- `Tickets` - Support ticket data
- `Comments` - Ticket comments with references
- `CodeSnippets` - Indexed code from GitLab repositories
- `Documentation` - Imported documentation files

## Safety Features

The `db clear` command includes several safety features:

1. **Confirmation prompt**: Always asks for confirmation before deleting
2. **Connection check**: Verifies Weaviate is running before proceeding
3. **Existence check**: Verifies the collection exists before attempting deletion
4. **Clear error messages**: Provides helpful feedback if something goes wrong

## Use Cases

### Reset Development Environment

```bash
# Clear all data and start fresh
neoflow db clear

# Re-import data
neoflow import
neoflow gitlab-index
neoflow import-documentation --path ./docs
```

### Remove Specific Data

```bash
# Remove only ticket data
neoflow db clear --collection Tickets
neoflow db clear --collection Comments

# Re-import tickets
neoflow import
```

### Clean Up Before Re-indexing

```bash
# Clear code index before re-indexing
neoflow db clear --collection CodeSnippets

# Re-index from GitLab
neoflow gitlab-index
```

## Prerequisites

- Weaviate must be running (typically via `docker compose up -d`)
- The Weaviate service must be accessible at the configured host/port

## Error Handling

If Weaviate is not running:
```
Cannot connect to Weaviate.
Make sure it's running: docker compose up -d
```

If a collection doesn't exist:
```
Collection 'MyCollection' does not exist.
```

If the operation is cancelled:
```
Operation cancelled.
```

## Related Commands

- `neoflow import` - Import ticket data
- `neoflow gitlab-index` - Index GitLab repositories
- `neoflow import-documentation` - Import documentation files
- `neoflow gitlab-refresh` - Refresh GitLab repository index

## Technical Details

The command:
1. Uses the `_check_services()` function to verify Weaviate connectivity
2. Requires user confirmation via `rich.prompt.Confirm`
3. Uses the Weaviate Python client v4 API
4. Properly closes the client connection in a `finally` block
5. Provides colorized output using Rich console formatting
