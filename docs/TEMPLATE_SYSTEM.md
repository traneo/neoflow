# Template System

Guide to creating and using query templates in NeoFlow.

## Table of Contents

- [Overview](#overview)
- [Template Structure](#template-structure)
- [Creating Templates](#creating-templates)
- [Using Templates](#using-templates)
- [Examples](#examples)
- [Best Practices](#best-practices)

## Overview

Templates provide reusable query patterns with user-fillable fields. They're useful for:

- Standardized workflows
- Recurring queries
- Structured information gathering
- Report generation
- Documentation creation

### Template Storage Location

- Runtime templates are loaded from `~/.neoflow/templates/`.
- On first NeoFlow run, default templates are copied there from bundled package files.
- User files in `~/.neoflow/templates/` are never overwritten during bootstrap.

## Template Structure

Templates are YAML files with two main sections:

### Basic Structure

```yaml
form:
  title: "Template Title"
  fields:
    - label: "Field Label"
      alias: "field_name"
      default: "Optional default value"

prompt:
  query: "Query text with {field_name placeholders}"
```

### Required Fields

**form section:**
- `title`: Display title for the template
- `fields`: List of field definitions

**Each field:**
- `label`: User-facing field label
- `alias`: Variable name for substitution

**prompt section:**
- `query`: Query template with placeholder variables

### Optional Fields

**Field options:**
- `default`: Default value (shown as suggestion)

## Creating Templates

### Step 1: Create Template File

Create `~/.neoflow/templates/your_template.yaml`:

```yaml
form:
  title: "Your Template Name"
  fields:
    - label: "First Field"
      alias: "field1"
      default: "Default value"
    
    - label: "Second Field"
      alias: "field2"

prompt:
  query: |
    Your query with {field1} and {field2} placeholders.
    Can be multi-line.
```

### Step 2: Test Template

```bash
neoflow
```

```
You: /t=your_template
[Template form appears]
```

## Using Templates

### Interactive Mode

In interactive chat:

```bash
$ neoflow
You: /t=template_name
```

Form prompts appear for each field:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
           Template Title
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  First Field: [type value]
  Second Field: [type value]
```

After filling, query is executed automatically.

### CLI Mode

```bash
neoflow template template_name
```

### API Mode

```bash
curl -X POST http://localhost:9720/api/v1/templates/template_name \
  -H "Content-Type: application/json" \
  -d '{
    "values": {
      "field1": "value1",
      "field2": "value2"
    }
  }'
```

### List Available Templates

```bash
neoflow templates
```

Or via API:

```bash
curl http://localhost:9720/api/v1/templates
```

## Examples

### Example 1: Statement of Work

**~/.neoflow/templates/sow.yaml:**

```yaml
form:
  title: "Statement of Work Generator"
  fields:
    - label: "Project Name"
      alias: "project_name"
    
    - label: "Project Description"
      alias: "description"
    
    - label: "Scope (what's included)"
      alias: "scope"
    
    - label: "Out of Scope (what's excluded)"
      alias: "out_scope"
      default: "TBD"
    
    - label: "Timeline Estimate"
      alias: "timeline"
      default: "4 weeks"

prompt:
  query: |
    Generate a comprehensive Statement of Work document for a software project with these details:
    
    Project Name: {project_name}
    Description: {description}
    Scope: {scope}
    Out of Scope: {out_scope}
    Timeline: {timeline}
    
    Include sections for:
    - Project Overview
    - Scope of Work
    - Deliverables
    - Timeline
    - Technical Requirements
    - Assumptions
    - Success Criteria
    
    Format as a professional document.
```

**Usage:**

```
You: /t=sow
Project Name: User Management API
Project Description: REST API for user CRUD operations
Scope: Backend API development, authentication, database design
Out of Scope: Frontend, mobile apps, DevOps
Timeline: 6 weeks
```

### Example 2: Status Report

**~/.neoflow/templates/status.yaml:**

```yaml
form:
  title: "Project Status Report"
  fields:
    - label: "Project Name"
      alias: "project"
    
    - label: "Current Sprint/Week"
      alias: "period"
    
    - label: "Accomplishments"
      alias: "done"
    
    - label: "In Progress"
      alias: "wip"
    
    - label: "Blockers/Issues"
      alias: "blockers"
      default: "None"
    
    - label: "Next Steps"
      alias: "next"

prompt:
  query: |
    Create a professional status report for {project} covering {period}.
    
    Completed:
    {done}
    
    In Progress:
    {wip}
    
    Blockers:
    {blockers}
    
    Planned:
    {next}
    
    Search the codebase and documentation for relevant context about this project.
    Format the report with proper structure and include any relevant metrics or links.
```

### Example 3: Code Review

**~/.neoflow/templates/review.yaml:**

```yaml
form:
  title: "Code Review Request"
  fields:
    - label: "File or Module to Review"
      alias: "target"
    
    - label: "Focus Areas"
      alias: "focus"
      default: "Code quality, security, performance"
    
    - label: "Specific Concerns"
      alias: "concerns"
      default: "None"

prompt:
  query: |
    Perform a code review of {target}.
    
    Focus on: {focus}
    Specific concerns: {concerns}
    
    Search the code and provide:
    1. Overall assessment
    2. Issues found (with severity)
    3. Suggestions for improvement
    4. Best practices recommendations
    5. References to similar patterns in codebase
```

### Example 4: API Documentation

**~/.neoflow/templates/api_docs.yaml:**

```yaml
form:
  title: "API Endpoint Documentation"
  fields:
    - label: "Endpoint Path"
      alias: "path"
    
    - label: "HTTP Method"
      alias: "method"
      default: "GET"
    
    - label: "Purpose"
      alias: "purpose"

prompt:
  query: |
    Generate comprehensive API documentation for:
    
    Endpoint: {method} {path}
    Purpose: {purpose}
    
    Search the codebase for this endpoint and include:
    - Description
    - Request parameters
    - Request body schema (if applicable)
    - Response schema
    - Status codes
    - Example request and response
    - Authentication requirements
    - Error scenarios
    
    Format using OpenAPI/Swagger style.
```

### Example 5: Bug Report

**~/.neoflow/templates/bug.yaml:**

```yaml
form:
  title: "Bug Investigation"
  fields:
    - label: "Bug Description"
      alias: "description"
    
    - label: "Error Message (if any)"
      alias: "error"
      default: "N/A"
    
    - label: "Affected Component"
      alias: "component"
    
    - label: "Steps to Reproduce"
      alias: "steps"

prompt:
  query: |
    Investigate this bug:
    
    Description: {description}
    Error: {error}
    Component: {component}
    
    Steps to reproduce:
    {steps}
    
    Search the codebase, documentation, and support tickets for:
    1. Relevant code that might cause this issue
    2. Similar past issues and their resolutions
    3. Potential root causes
    4. Suggested fixes
    
    Provide a detailed analysis with code references.
```

## Best Practices

### 1. Clear Field Labels

**Good:**
```yaml
- label: "Project Name (e.g., 'User Management API')"
  alias: "project_name"
```

**Avoid:**
```yaml
- label: "Name"
  alias: "n"
```

### 2. Provide Helpful Defaults

```yaml
- label: "Priority Level"
  alias: "priority"
  default: "Medium"  # Gives users a starting point
```

### 3. Use Descriptive Queries

Include instructions in the query:

```yaml
prompt:
  query: |
    Create a {document_type} with the following requirements:
    
    {requirements}
    
    Search the documentation for templates and examples.
    Format the output professionally with proper sections.
    Include relevant code examples if applicable.
```

### 4. Keep Fields Focused

**Better:**
```yaml
fields:
  - label: "Feature Name"
    alias: "feature"
  - label: "User Story"
    alias: "story"
  - label: "Acceptance Criteria"
    alias: "criteria"
```

**Avoid:**
```yaml
fields:
  - label: "Everything about the feature"
    alias: "everything"
```

### 5. Validate Field Names

Field aliases used in query must match exactly:

```yaml
fields:
  - alias: "project_name"  # ✓ Valid

prompt:
  query: "For project {project_name}..."  # ✓ Matches
  # NOT: {projectName} or {project} or {name}
```

### 6. Use Multi-Line Queries

For complex templates:

```yaml
prompt:
  query: |
    Line 1
    Line 2
    {field1}
    Line 3
```

### 7. Template Naming

Use descriptive names:

- **Good**: `sow.yaml`, `status_report.yaml`, `api_docs.yaml`
- **Avoid**: `template1.yaml`, `t.yaml`, `thing.yaml`

### 8. Document Your Templates

Add comments in YAML:

```yaml
# Statement of Work template
# Used for: Project planning, client proposals, internal docs
form:
  title: "Statement of Work"
  # ...
```

## Template Organization

### Directory Structure

```
~/.neoflow/templates/
├── README.md                 # Template documentation
├── sow.yaml                  # Statement of Work
├── status.yaml               # Status reports
├── review.yaml               # Code reviews
├── bug.yaml                  # Bug investigations
└── custom/
    ├── team_specific.yaml
    └── project_specific.yaml
```

### README.md for Templates

```markdown
# NeoFlow Templates

## Available Templates

- **sow**: Statement of Work generator
- **status**: Project status reports
- **review**: Code review requests
- **bug**: Bug investigation

## Usage

In interactive mode: `/t=template_name`
CLI: `neoflow template template_name`
API: `POST /api/v1/templates/template_name`

## Creating New Templates

See TEMPLATE_GUIDE.md for instructions.
```

## Troubleshooting

### Template Not Found

**Error:** `Template 'xxx' not found`

**Check:**
1. File exists: `ls ~/.neoflow/templates/xxx.yaml`
2. Extension is `.yaml` (not `.yml`)
3. File is in `~/.neoflow/templates/` directory

### Missing Placeholder

**Error:** `Placeholder {xxx} has no matching field`

**Fix:** Add field with matching alias:

```yaml
fields:
  - label: "Missing Field"
    alias: "xxx"  # Must match placeholder
```

### Invalid YAML

**Error:** `Template 'xxx' is not a valid YAML mapping`

**Fix:** Check YAML syntax:
```bash
python -m yaml ~/.neoflow/templates/xxx.yaml
# Or use online YAML validator
```

### Missing Required Keys

**Error:** `Template is missing required key: form`

**Fix:** Ensure both sections exist:

```yaml
form:
  title: "..."
  fields: [...]

prompt:
  query: "..."
```

## See Also

- [CLI Reference](CLI_REFERENCE.md)
- [Chat System](CHAT_SYSTEM.md)
- [API Server](API_SERVER.md)
