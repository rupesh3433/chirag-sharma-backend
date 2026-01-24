"""
Prompt Builder - Builds prompts dynamically
"""

from typing import Dict, List
from .templates import PromptTemplates


class PromptBuilder:
    """Build prompts dynamically based on context"""
    
    def __init__(self):
        """Initialize prompt builder"""
        pass
    
    def build_state_prompt(self, state: str, memory, language: str) -> str:
        """Build prompt for current state"""
        pass
    
    def build_missing_fields_prompt(self, missing_fields: List[str], collected: Dict, language: str) -> str:
        """Build prompt for missing fields"""
        pass
    
    def build_extracted_fields_ack(self, extracted_fields: Dict, language: str) -> str:
        """Build acknowledgment for extracted fields"""
        pass
    
    def build_next_expected_prompt(self, state: str, intent, language: str) -> str:
        """Build prompt for next expected action"""
        pass