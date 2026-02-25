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
    
    def get_skills_catalog(self) -> str:
        """Return a compact catalog of all available skills (name + description) for prompt injection."""
        if not self._skills_cache:
            return ""

        by_category: Dict[str, List[Skill]] = {}
        for skill in self._skills_cache.values():
            by_category.setdefault(skill.category, []).append(skill)

        lines = []
        for category in sorted(by_category):
            for skill in sorted(by_category[category], key=lambda s: s.name):
                lines.append(f"  - {skill.name}: {skill.description}")
        return "\n".join(lines)

    def suggest_skills_for_target(self, target_info: Dict[str, Any]) -> List[str]:
        """
        Suggest relevant skills based on target information.
        
        Args:
            target_info: Dictionary containing target information (technologies, services, etc.)
        
        Returns:
            List of suggested skill names
        """
        scores: Dict[str, int] = {}
        
        technologies = target_info.get('technologies', [])
        services = target_info.get('services', [])
        ports = target_info.get('ports', [])
        urls = target_info.get('urls', [])
        
        tech_str = ' '.join(t.lower() for t in technologies)
        service_str = ' '.join(s.lower() for s in services)
        url_str = ' '.join(u.lower() for u in urls)
        
        def boost(skill: str, points: int = 1):
            scores[skill] = scores.get(skill, 0) + points
        
        # Baseline — any HTTP service gets generic web vuln skills (low weight)
        if any(port in [80, 443, 8080, 8443, 3000, 5000, 8000, 8888] for port in ports):
            for s in ['sql_injection', 'xss_detection', 'idor', 'ssrf', 'csrf',
                       'command_injection', 'authentication_bypass', 'information_disclosure']:
                boost(s, 1)
        
        # Context-specific signals (higher weight — these differentiate)
        if any(kw in url_str for kw in ['/api/', '/graphql', '/rest/', '/v1/', '/v2/']):
            boost('api_testing', 3)
            boost('idor', 2)
        
        if any(kw in tech_str for kw in ['jwt', 'oauth', 'auth0', 'keycloak']):
            boost('jwt_testing', 3)
            boost('authentication_bypass', 2)
        if any(kw in url_str for kw in ['/login', '/auth', '/oauth', '/token', '/register']):
            boost('authentication_bypass', 2)
        
        if any(kw in tech_str for kw in ['xml', 'soap', 'saml']):
            boost('xxe', 3)
        
        if any(kw in url_str for kw in ['/upload', '/import', '/attach', '/file']):
            boost('insecure_file_uploads', 3)
        
        if 'django' in tech_str:
            boost('django_testing', 3)
        if any(kw in tech_str for kw in ['express', 'node', 'next.js', 'koa']):
            boost('nodejs_testing', 3)
        
        if any(kw in service_str for kw in ['mysql', 'postgres', 'mssql', 'oracle', 'mariadb']):
            boost('sql_injection', 2)
        
        if any(kw in url_str for kw in ['/cart', '/checkout', '/payment', '/order', '/pricing']):
            boost('business_logic', 3)
            boost('race_conditions', 3)
        
        if any(kw in url_str for kw in ['/admin', '/dashboard', '/manage']):
            boost('authentication_bypass', 2)
            boost('idor', 2)
        
        # Rank by score descending, filter to available skills
        available_skills = set(self._skills_cache.keys())
        ranked = sorted(
            ((skill, score) for skill, score in scores.items() if skill in available_skills),
            key=lambda x: x[1],
            reverse=True,
        )
        
        return [skill for skill, _ in ranked[:5]]


# Global skill loader instance
skill_loader = SkillLoader()