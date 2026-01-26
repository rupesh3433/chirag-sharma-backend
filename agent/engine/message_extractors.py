# agent/engine/message_extractors.py
"""
Message extraction utilities for FSM
"""
import re
from typing import Optional, Dict, Any
from .engine_config import SERVICE_PATTERNS, PACKAGE_KEYWORDS


class MessageExtractors:
    """Message extraction utilities"""
    
    @staticmethod
    def extract_service_selection(message: str) -> Optional[str]:
        """Extract service from message"""
        msg_lower = message.lower()
        
        for service, keywords in SERVICE_PATTERNS.items():
            for keyword in keywords:
                if keyword in msg_lower:
                    return service
        
        return None
    
    @staticmethod
    def extract_package_selection(message: str, service: str) -> Optional[str]:
        """Extract package from message for given service"""
        msg_lower = message.lower()
        
        # Check for exact package names
        from ..config.services_config import SERVICES
        if service in SERVICES:
            packages = list(SERVICES[service]["packages"].keys())
            for package in packages:
                package_lower = package.lower()
                if package_lower in msg_lower:
                    return package
        
        # Check for keywords
        for package, keywords in PACKAGE_KEYWORDS.items():
            if service in SERVICES and package in SERVICES[service]["packages"]:
                for keyword in keywords:
                    if keyword in msg_lower:
                        return package
        
        return None
    
    @staticmethod
    def extract_year_from_message(message: str) -> Optional[int]:
        """Extract year from message (e.g., 2025, 2026)"""
        from datetime import datetime
        
        year_match = re.search(r'\b(20[2-9][0-9]|2100)\b', message)
        if year_match:
            try:
                year = int(year_match.group(1))
                # Validate year is reasonable (2023-2100)
                current_year = datetime.now().year
                if current_year - 1 <= year <= current_year + 10:
                    return year
            except (ValueError, TypeError):
                pass
        return None