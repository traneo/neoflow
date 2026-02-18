# Agent System Prompts

This folder contains specialized system prompts that override the default agent behavior for specific tasks and domains.

## Overview

System prompts in this folder are used to tailor the AI agent's behavior for particular use cases, technologies, or workflows. When a system prompt is loaded, it replaces the default agent instructions with specialized guidance.

## How to Use

1. **Select a prompt**: Choose a system prompt file that matches your specific need
2. **Load it**: Use the NeoFlow agent system to load the prompt
3. **Interact**: The agent will now follow the specialized instructions in that prompt

## Structure

Each system prompt file should follow this format:

```markdown
# IMPORTANT
- The information below, override the default agent behavior.
- Follow the instruction below.
- You no longer assists with software development 

[Your specialized instructions here]
```

## Available Prompts

### Language/Framework Specific
- **c#.md** - C# development and .NET framework expertise
- **java.md** - Java development and ecosystem guidance

### Task Specific
- **qa.md** - Software architecture and security review
- **test_cases.md** - Test case generation and QA guidance
- **online.md** - Online/web-specific development

## Creating Custom Prompts

To create a new system prompt:

1. Create a new `.md` file in this directory
2. Start with the "IMPORTANT" header to override default behavior
3. Define the agent's new role and expertise
4. Provide specific instructions, including:
   - What the agent should focus on
   - Expected output format
   - Key areas to cover
   - Examples or templates (if applicable)

## Best Practices

- **Be specific**: Clearly define the agent's role and responsibilities
- **Provide structure**: Use numbered lists, sections, and bullet points
- **Include examples**: Show the expected format for outputs
- **Set boundaries**: Explicitly state what the agent should or shouldn't do
- **Focus on outcomes**: Describe the desired end result

## Examples

See the existing prompt files in this directory for examples of well-structured system prompts. Each prompt is tailored for a specific domain or task while maintaining a consistent format.

## Notes

- System prompts completely override default behavior
- Choose prompts carefully based on your specific task
- You can edit existing prompts or create new ones as needed
- Keep prompts focused on a single domain or task type
