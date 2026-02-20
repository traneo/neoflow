# Agent System Prompts

This folder contains bundled default domain prompt files used to bootstrap user resources.

## Overview

On first NeoFlow run, files from this folder are copied to `~/.neoflow/agent_system_prompt/` if missing. Runtime domain loading reads from `~/.neoflow/agent_system_prompt/`.

System prompts tailor the AI agent's behavior for particular use cases, technologies, or workflows.

## How to Use

1. **Select a prompt**: Choose a system prompt file in `~/.neoflow/agent_system_prompt/` that matches your specific need
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
- **page_crawler.md** - CLI-only static/dynamic page crawling and content extraction for Q&A

## Creating Custom Prompts

To create a new system prompt:

1. Create a new `.md` file in `~/.neoflow/agent_system_prompt/`
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

See the existing prompt files in `~/.neoflow/agent_system_prompt/` for examples of well-structured system prompts. Each prompt is tailored for a specific domain or task while maintaining a consistent format.

## Notes

- System prompts completely override default behavior
- Choose prompts carefully based on your specific task
- You can edit existing prompts or create new ones as needed
- Keep prompts focused on a single domain or task type
