"""YAML template loader and form runner for the /t= command."""

import os
from dataclasses import dataclass

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt


class TemplateError(Exception):
    """Raised when a template is missing or invalid."""


@dataclass
class TemplateInfo:
    """Information about a template."""
    name: str
    title: str
    fields: list[str]


def load_template(name: str, templates_dir: str = "templates") -> dict:
    """Load and validate a YAML template by name.

    Parameters
    ----------
    name:
        Template name (without the .yaml extension).
    templates_dir:
        Directory where templates are stored.

    Returns
    -------
    dict
        Parsed template with ``form`` and ``prompt`` sections.
    """
    path = os.path.join(templates_dir, f"{name}.yaml")

    if not os.path.isfile(path):
        available = [
            f.removesuffix(".yaml")
            for f in os.listdir(templates_dir)
            if f.endswith(".yaml")
        ] if os.path.isdir(templates_dir) else []
        hint = f" Available: {', '.join(available)}" if available else ""
        raise TemplateError(f"Template '{name}' not found.{hint}")

    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise TemplateError(f"Template '{name}' is not a valid YAML mapping.")

    for key in ("form", "prompt"):
        if key not in data:
            raise TemplateError(f"Template '{name}' is missing required key: {key}")

    form = data["form"]
    if "fields" not in form or not form["fields"]:
        raise TemplateError(f"Template '{name}' has no fields defined.")
    if "title" not in form:
        raise TemplateError(f"Template '{name}' form is missing a title.")

    for i, field in enumerate(form["fields"]):
        if "label" not in field or "alias" not in field:
            raise TemplateError(
                f"Template '{name}' field #{i + 1} must have 'label' and 'alias'."
            )

    if "query" not in data["prompt"]:
        raise TemplateError(f"Template '{name}' prompt is missing a query.")

    return data


def list_templates(templates_dir: str = "templates") -> list[TemplateInfo]:
    """List all available templates in the templates directory.

    Parameters
    ----------
    templates_dir:
        Directory where templates are stored.

    Returns
    -------
    list[TemplateInfo]
        List of available templates with their metadata.
    """
    if not os.path.isdir(templates_dir):
        return []
    
    templates = []
    
    for filename in sorted(os.listdir(templates_dir)):
        if not filename.endswith(".yaml"):
            continue
        
        name = filename.removesuffix(".yaml")
        
        try:
            template_data = load_template(name, templates_dir)
            form = template_data.get("form", {})
            title = form.get("title", name)
            fields = [field["alias"] for field in form.get("fields", [])]
            
            templates.append(TemplateInfo(
                name=name,
                title=title,
                fields=fields
            ))
        except (TemplateError, KeyError, TypeError):
            # Skip invalid templates
            continue
    
    return templates


def run_template_form(template: dict, console: Console) -> str:
    """Display the form, collect user inputs, and return the final query.

    Parameters
    ----------
    template:
        Parsed template dict (from :func:`load_template`).
    console:
        Rich console instance for rendering.

    Returns
    -------
    str
        The prompt query with all placeholders replaced by user input.
    """
    form = template["form"]
    console.print()
    console.print(Panel(f"[bold]{form['title']}[/bold]", border_style="blue"))

    values: dict[str, str] = {}
    for field in form["fields"]:
        default = field.get("default", "")
        answer = Prompt.ask(f"  [bold]{field['label']}[/bold]", default=default or None)
        values[field["alias"]] = answer or ""

    query_template = template["prompt"]["query"]

    try:
        query = query_template.format_map(values)
    except KeyError as exc:
        raise TemplateError(
            f"Placeholder {exc} in prompt query has no matching field alias."
        ) from exc

    return query
