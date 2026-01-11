"""
Skill Registry for Kodiak

Provides a centralized registry of all available skills and their metadata.
"""

from typing import Dict, List, Set
from .skill_loader import skill_loader


class SkillRegistry:
    """Registry for managing and discovering skills"""
    
    def __init__(self):
        self.loader = skill_loader
    
    def get_all_skills(self) -> Dict[str, str]:
        """Get all available skills with their descriptions"""
        return {
            skill.name: skill.description 
            for skill in self.loader._skills_cache.values()
        }
    
    def get_skills_by_category(self) -> Dict[str, List[str]]:
        """Get skills organized by category"""
        return self.loader.list_available_skills()
    
    def search_skills(self, query: str) -> List[str]:
        """Search for skills by name or description"""
        query_lower = query.lower()
        matching_skills = []
        
        for skill in self.loader._skills_cache.values():
            if (query_lower in skill.name.lower() or 
                query_lower in skill.description.lower() or
                any(query_lower in technique.lower() for technique in skill.techniques)):
                matching_skills.append(skill.name)
        
        return matching_skills
    
    def get_skill_dependencies(self, skill_name: str) -> List[str]:
        """Get recommended tools for a skill"""
        skill = self.loader.get_skill(skill_name)
        return skill.tools if skill else []
    
    def validate_skill_combination(self, skill_names: List[str]) -> Dict[str, any]:
        """Validate if a combination of skills makes sense together"""
        if len(skill_names) > 5:
            return {
                "valid": False,
                "reason": "Too many skills selected (max 5)",
                "suggestions": skill_names[:5]
            }
        
        # Check if all skills exist
        missing_skills = []
        existing_skills = []
        
        for skill_name in skill_names:
            if self.loader.get_skill(skill_name):
                existing_skills.append(skill_name)
            else:
                missing_skills.append(skill_name)
        
        if missing_skills:
            return {
                "valid": False,
                "reason": f"Skills not found: {', '.join(missing_skills)}",
                "existing_skills": existing_skills
            }
        
        # Check for complementary skills
        categories = set()
        for skill_name in existing_skills:
            skill = self.loader.get_skill(skill_name)
            if skill:
                categories.add(skill.category)
        
        return {
            "valid": True,
            "categories_covered": list(categories),
            "skill_count": len(existing_skills),
            "recommendations": self._get_complementary_skills(existing_skills)
        }
    
    def _get_complementary_skills(self, selected_skills: List[str]) -> List[str]:
        """Get skills that complement the selected ones"""
        selected_categories = set()
        for skill_name in selected_skills:
            skill = self.loader.get_skill(skill_name)
            if skill:
                selected_categories.add(skill.category)
        
        # Suggest skills from underrepresented categories
        all_categories = set()
        for skill in self.loader._skills_cache.values():
            all_categories.add(skill.category)
        
        missing_categories = all_categories - selected_categories
        recommendations = []
        
        for category in missing_categories:
            category_skills = self.loader.get_skills_by_category(category)
            if category_skills:
                recommendations.append(category_skills[0].name)  # Add first skill from category
        
        return recommendations[:3]  # Return top 3 recommendations


# Global skill registry instance
skill_registry = SkillRegistry()