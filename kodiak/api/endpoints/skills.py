"""
Skills management API endpoints
"""

from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from kodiak.skills import skill_registry, skill_loader

router = APIRouter()


class SkillSuggestionRequest(BaseModel):
    target_info: Dict[str, Any]


class SkillValidationRequest(BaseModel):
    skill_names: List[str]


@router.get("/", response_model=Dict[str, str])
async def list_all_skills():
    """Get all available skills with descriptions"""
    try:
        return skill_registry.get_all_skills()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load skills: {str(e)}")


@router.get("/categories", response_model=Dict[str, List[str]])
async def get_skills_by_category():
    """Get skills organized by category"""
    try:
        return skill_registry.get_skills_by_category()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load skill categories: {str(e)}")


@router.get("/search/{query}", response_model=List[str])
async def search_skills(query: str):
    """Search for skills by name or description"""
    try:
        return skill_registry.search_skills(query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/{skill_name}")
async def get_skill_details(skill_name: str):
    """Get detailed information about a specific skill"""
    try:
        skill = skill_loader.get_skill(skill_name)
        if not skill:
            raise HTTPException(status_code=404, detail=f"Skill '{skill_name}' not found")
        
        return skill.dict()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load skill: {str(e)}")


@router.post("/suggest", response_model=List[str])
async def suggest_skills(request: SkillSuggestionRequest):
    """Get skill suggestions based on target information"""
    try:
        suggestions = skill_loader.suggest_skills_for_target(request.target_info)
        return suggestions
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {str(e)}")


@router.post("/validate", response_model=Dict[str, Any])
async def validate_skill_combination(request: SkillValidationRequest):
    """Validate if a combination of skills makes sense together"""
    try:
        validation_result = skill_registry.validate_skill_combination(request.skill_names)
        return validation_result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation failed: {str(e)}")


@router.post("/load", response_model=Dict[str, str])
async def load_skills_preview(request: SkillValidationRequest):
    """Preview how skills would be formatted for an agent"""
    try:
        if len(request.skill_names) > 5:
            raise HTTPException(status_code=400, detail="Maximum 5 skills allowed")
        
        formatted_skills = skill_loader.load_skills_for_agent(request.skill_names)
        
        return {
            "skills_loaded": request.skill_names,
            "formatted_content": formatted_skills,
            "character_count": len(formatted_skills)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load skills: {str(e)}")


@router.get("/{skill_name}/dependencies", response_model=List[str])
async def get_skill_dependencies(skill_name: str):
    """Get recommended tools for a specific skill"""
    try:
        dependencies = skill_registry.get_skill_dependencies(skill_name)
        return dependencies
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get dependencies: {str(e)}")