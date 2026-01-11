"""
Kodiak Skills System

Skills are specialized knowledge packages that enhance agent capabilities
for specific vulnerability types, technologies, and testing methodologies.
"""

from .skill_loader import SkillLoader, Skill
from .skill_registry import skill_registry

__all__ = ["SkillLoader", "Skill", "skill_registry"]