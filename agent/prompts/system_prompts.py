"""
System Prompts for LLM
"""

from typing import Dict


class SystemPrompts:
    """System prompts for different contexts"""
    
    def get_agent_system_prompt(self, language: str, memory_state: Dict) -> str:
        """Get main agent system prompt"""
        pass
    
    def get_booking_system_prompt(self, language: str, context: Dict) -> str:
        """Get booking mode system prompt"""
        pass
    
    def get_info_system_prompt(self, language: str) -> str:
        """Get info mode system prompt"""
        pass
    
    def get_base_system_prompt(self, language: str) -> str:
        """Get base system prompt"""
        pass