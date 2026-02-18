from fastapi import APIRouter
from neoflow.api.models import TemplatesResponse, TemplateInfo
from neoflow.template import list_templates

router = APIRouter(tags=["templates"])


@router.get("/templates", response_model=TemplatesResponse)
async def list_templates_endpoint():
    """List available query templates."""
    template_list = list_templates()
    
    template_infos = [
        TemplateInfo(
            name=template.name,
            title=template.title,
            fields=template.fields,
        )
        for template in template_list
    ]
    
    return TemplatesResponse(templates=template_infos)
