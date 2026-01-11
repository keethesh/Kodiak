"""
Skill Loading System for Kodiak Agents

Provides dynamic skill loading capabilities for agents to specialize
in specific vulnerability types, technologies, and testing methodologies.
"""

import os
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
from pydantic import BaseModel, Field


class Skill(BaseModel):
    """Represents a specialized skill for an agent"""
    name: str = Field(..., description="Skill name/identifier")
    category: str = Field(..., description="Skill category (vulnerabilities, frameworks, etc.)")
    description: str = Field(..., description="Brief description of the skill")
    techniques: List[str] = Field(default=[], description="List of techniques provided by this skill")
    tools: List[str] = Field(default=[], description="Recommended tools for this skill")
    knowledge: str = Field(..., description="Detailed knowledge content for the skill")
    examples: List[Dict[str, Any]] = Field(default=[], description="Practical examples and payloads")
    validation_methods: List[str] = Field(default=[], description="Methods to validate findings")
    references: List[str] = Field(default=[], description="External references and resources")


class SkillLoader:
    """Loads and manages skills for agents"""
    
    def __init__(self):
        self.skills_dir = Path(__file__).parent / "definitions"
        self._skills_cache: Dict[str, Skill] = {}
        self._load_all_skills()
    
    def _load_all_skills(self):
        """Load all available skills from the definitions directory"""
        if not self.skills_dir.exists():
            return
        
        for category_dir in self.skills_dir.iterdir():
            if category_dir.is_dir():
                self._load_category_skills(category_dir)
    
    def _load_category_skills(self, category_dir: Path):
        """Load skills from a specific category directory"""
        category = category_dir.name
        
        for skill_file in category_dir.glob("*.yaml"):
            try:
                skill = self._load_skill_file(skill_file, category)
                if skill:
                    self._skills_cache[skill.name] = skill
            except Exception as e:
                print(f"Warning: Failed to load skill {skill_file}: {e}")
    
    def _load_skill_file(self, skill_file: Path, category: str) -> Optional[Skill]:
        """Load a single skill file"""
        try:
            with open(skill_file, 'r', encoding='utf-8') as f:
                skill_data = yaml.safe_load(f)
            
            skill_data['category'] = category
            return Skill(**skill_data)
        except Exception as e:
            print(f"Error loading skill file {skill_file}: {e}")
            return None
    
    def get_skill(self, skill_name: str) -> Optional[Skill]:
        """Get a specific skill by name"""
        return self._skills_cache.get(skill_name)
    
    def get_skills_by_category(self, category: str) -> List[Skill]:
        """Get all skills in a specific category"""
        return [skill for skill in self._skills_cache.values() if skill.category == category]
    
    def list_available_skills(self) -> Dict[str, List[str]]:
        """List all available skills grouped by category"""
        skills_by_category = {}
        for skill in self._skills_cache.values():
            if skill.category not in skills_by_category:
                skills_by_category[skill.category] = []
            skills_by_category[skill.category].append(skill.name)
        return skills_by_category
    
    def load_skills_for_agent(self, skill_names: List[str], max_skills: int = 5) -> str:
        """
        Load specified skills for an agent and return formatted knowledge.
        
        Args:
            skill_names: List of skill names to load
            max_skills: Maximum number of skills to load (default: 5)
        
        Returns:
            Formatted skill knowledge string for injection into agent prompt
        """
        if len(skill_names) > max_skills:
            skill_names = skill_names[:max_skills]
        
        loaded_skills = []
        for skill_name in skill_names:
            skill = self.get_skill(skill_name)
            if skill:
                loaded_skills.append(skill)
        
        if not loaded_skills:
            return ""
        
        return self._format_skills_for_prompt(loaded_skills)
    
    def _format_skills_for_prompt(self, skills: List[Skill]) -> str:
        """Format skills into a prompt-ready string"""
        if not skills:
            return ""
        
        formatted = "# SPECIALIZED SKILLS\n\n"
        formatted += "You have been equipped with the following specialized skills:\n\n"
        
        for skill in skills:
            formatted += f"## {skill.name.upper()} ({skill.category})\n"
            formatted += f"{skill.description}\n\n"
            
            if skill.techniques:
                formatted += "### Techniques:\n"
                for technique in skill.techniques:
                    formatted += f"- {technique}\n"
                formatted += "\n"
            
            if skill.knowledge:
                formatted += "### Knowledge:\n"
                formatted += f"{skill.knowledge}\n\n"
            
            if skill.examples:
                formatted += "### Examples:\n"
                for i, example in enumerate(skill.examples, 1):
                    formatted += f"{i}. **{example.get('title', 'Example')}**\n"
                    if example.get('description'):
                        formatted += f"   {example['description']}\n"
                    if example.get('payload'):
                        formatted += f"   Payload: `{example['payload']}`\n"
                    if example.get('validation'):
                        formatted += f"   Validation: {example['validation']}\n"
                    formatted += "\n"
            
            if skill.validation_methods:
                formatted += "### Validation Methods:\n"
                for method in skill.validation_methods:
                    formatted += f"- {method}\n"
                formatted += "\n"
            
            if skill.tools:
                formatted += "### Recommended Tools:\n"
                for tool in skill.tools:
                    formatted += f"- {tool}\n"
                formatted += "\n"
            
            formatted += "---\n\n"
        
        formatted += "Use these skills to enhance your testing capabilities and make informed decisions about tool selection and payload crafting.\n\n"
        
        return formatted
    
    def suggest_skills_for_target(self, target_info: Dict[str, Any]) -> List[str]:
        """
        Suggest relevant skills based on target information.
        
        Args:
            target_info: Dictionary containing target information (technologies, services, etc.)
        
        Returns:
            List of suggested skill names
        """
        suggested = []
        
        # Extract information from target
        technologies = target_info.get('technologies', [])
        services = target_info.get('services', [])
        ports = target_info.get('ports', [])
        
        # Web application skills
        if any(port in [80, 443, 8080, 8443] for port in ports):
            suggested.extend(['web_application_testing', 'xss_detection', 'sql_injection'])
        
        # Framework-specific skills
        for tech in technologies:
            tech_lower = tech.lower()
            if 'django' in tech_lower:
                suggested.append('django_testing')
            elif 'express' in tech_lower or 'node' in tech_lower:
                suggested.append('nodejs_testing')
            elif 'react' in tech_lower or 'next' in tech_lower:
                suggested.append('spa_testing')
        
        # Service-specific skills
        for service in services:
            service_lower = service.lower()
            if 'ssh' in service_lower:
                suggested.append('ssh_testing')
            elif 'ftp' in service_lower:
                suggested.append('ftp_testing')
            elif 'mysql' in service_lower or 'postgres' in service_lower:
                suggested.append('database_testing')
        
        # Remove duplicates and limit to available skills
        suggested = list(set(suggested))
        available_skills = list(self._skills_cache.keys())
        suggested = [skill for skill in suggested if skill in available_skills]
        
        return suggested[:5]  # Return top 5 suggestions


# Global skill loader instance
skill_loader = SkillLoader()