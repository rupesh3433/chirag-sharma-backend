"""
Base Extractor - Abstract base class for all extractors
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import re
import logging

logger = logging.getLogger(__name__)


class BaseExtractor(ABC):
    """Base class for all field extractors with common utilities"""
    
    def __init__(self):
        """Initialize base extractor"""
        self.logger = logger
    
    @abstractmethod
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """
        Extract field from message
        
        Args:
            message: The input message to extract from
            context: Optional context including conversation history, other extracted fields
            
        Returns:
            Dictionary with extracted value and metadata, or None if not found
            Format: {
                'field_name': extracted_value,
                'confidence': 'high'|'medium'|'low',
                'method': 'extraction_method_used',
                ...additional metadata
            }
        """
        pass
    
    def clean_message(self, message: str) -> str:
        """
        Clean message before extraction
        
        Args:
            message: Raw input message
            
        Returns:
            Cleaned message with normalized whitespace and punctuation
        """
        if not message:
            return ""
        
        # Remove extra whitespace
        cleaned = re.sub(r'\s+', ' ', message.strip())
        
        # Remove trailing punctuation from end
        cleaned = re.sub(r'[.,;!?]+$', '', cleaned)

        # Remove special characters that might interfere
        cleaned = re.sub(r'[^\w\s@+.,-]', ' ', cleaned)
        
        # Remove leading punctuation
        cleaned = re.sub(r'^[.,;!?]+', '', cleaned)
        
        return cleaned
    
    def find_pattern(self, message: str, pattern: str, flags: int = re.IGNORECASE) -> Optional[str]:
        """
        Helper method to find pattern in message
        
        Args:
            message: Message to search
            pattern: Regex pattern
            flags: Regex flags (default: IGNORECASE)
            
        Returns:
            First match group or None
        """
        try:
            match = re.search(pattern, message, flags)
            return match.group(1) if match else None
        except Exception as e:
            self.logger.error(f"Pattern matching error: {e}")
            return None
    
    def find_all_patterns(self, message: str, pattern: str, flags: int = re.IGNORECASE) -> List[str]:
        """
        Find all occurrences of pattern in message
        
        Args:
            message: Message to search
            pattern: Regex pattern
            flags: Regex flags (default: IGNORECASE)
            
        Returns:
            List of all matches
        """
        try:
            matches = re.finditer(pattern, message, flags)
            return [match.group(1) for match in matches if match.group(1)]
        except Exception as e:
            self.logger.error(f"Pattern matching error: {e}")
            return []
    
    def extract_from_context(self, field_name: str, context: Optional[Dict[str, Any]]) -> Optional[Any]:
        """
        Extract field from context dictionary
        
        Args:
            field_name: Name of the field to extract
            context: Context dictionary
            
        Returns:
            Field value or None
        """
        if not context:
            return None
        
        # Direct field lookup
        if field_name in context:
            return context[field_name]
        
        # Check nested structures
        if 'extracted_fields' in context and field_name in context['extracted_fields']:
            return context['extracted_fields'][field_name]
        
        if 'intent' in context:
            intent = context['intent']
            if isinstance(intent, dict) and field_name in intent:
                return intent[field_name]
            elif hasattr(intent, field_name):
                return getattr(intent, field_name)
        
        return None
    
    def get_conversation_history(self, context: Optional[Dict[str, Any]]) -> List[Dict]:
        """
        Get conversation history from context
        
        Args:
            context: Context dictionary
            
        Returns:
            List of conversation messages
        """
        if not context:
            return []
        
        # Try different possible locations
        if 'history' in context:
            return context['history']
        
        if 'conversation_history' in context:
            return context['conversation_history']
        
        if 'messages' in context:
            return context['messages']
        
        return []
    
    def search_in_history(self, history: List[Dict], extractor_func, max_messages: int = 10) -> Optional[Any]:
        """
        Search for field in conversation history
        
        Args:
            history: Conversation history
            extractor_func: Function to extract from message
            max_messages: Maximum messages to search
            
        Returns:
            Extracted value or None
        """
        if not history:
            return None
        
        # Search recent messages (reverse order)
        for msg in reversed(history[-max_messages:]):
            if isinstance(msg, dict) and msg.get('role') == 'user':
                content = msg.get('content', '')
                
                try:
                    result = extractor_func(content)
                    if result:
                        return result
                except Exception as e:
                    self.logger.debug(f"History search error: {e}")
                    continue
        
        return None
    
    def normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison
        
        Args:
            text: Input text
            
        Returns:
            Normalized text (lowercase, trimmed)
        """
        if not text:
            return ""
        
        return text.lower().strip()
    
    def remove_noise(self, message: str, noise_patterns: List[str]) -> str:
        """
        Remove noise patterns from message
        
        Args:
            message: Input message
            noise_patterns: List of regex patterns to remove
            
        Returns:
            Cleaned message
        """
        cleaned = message
        
        for pattern in noise_patterns:
            try:
                cleaned = re.sub(pattern, ' ', cleaned, flags=re.IGNORECASE)
            except Exception as e:
                self.logger.debug(f"Noise removal error for pattern {pattern}: {e}")
        
        # Normalize whitespace after removal
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def validate_length(self, value: str, min_length: int = 1, max_length: int = 1000) -> bool:
        """
        Validate value length
        
        Args:
            value: Value to validate
            min_length: Minimum allowed length
            max_length: Maximum allowed length
            
        Returns:
            True if valid, False otherwise
        """
        if not value:
            return False
        
        length = len(value)
        return min_length <= length <= max_length
    
    def extract_with_confidence(self, extractors: List[tuple]) -> Optional[Dict]:
        """
        Try multiple extraction methods and return best result
        
        Args:
            extractors: List of (extractor_func, confidence_level) tuples
            
        Returns:
            Best extraction result with highest confidence
        """
        results = []
        
        for extractor_func, confidence in extractors:
            try:
                result = extractor_func()
                if result:
                    results.append({
                        'value': result,
                        'confidence': confidence
                    })
            except Exception as e:
                self.logger.debug(f"Extractor error: {e}")
                continue
        
        if not results:
            return None
        
        # Sort by confidence (high > medium > low)
        confidence_order = {'high': 3, 'medium': 2, 'low': 1}
        results.sort(key=lambda x: confidence_order.get(x['confidence'], 0), reverse=True)
        
        return results[0] if results else None
    
    def merge_results(self, *results: Optional[Dict]) -> Optional[Dict]:
        """
        Merge multiple extraction results, preferring higher confidence
        
        Args:
            results: Multiple result dictionaries
            
        Returns:
            Merged result with best confidence
        """
        valid_results = [r for r in results if r is not None]
        
        if not valid_results:
            return None
        
        # Sort by confidence
        confidence_order = {'high': 3, 'medium': 2, 'low': 1}
        valid_results.sort(
            key=lambda x: confidence_order.get(x.get('confidence', 'low'), 0),
            reverse=True
        )
        
        # Return highest confidence result
        return valid_results[0]
    
    def build_result(self, value: Any, confidence: str = 'medium', 
                     method: str = 'unknown', **kwargs) -> Dict:
        """
        Build standardized result dictionary
        
        Args:
            value: Extracted value
            confidence: Confidence level ('high', 'medium', 'low')
            method: Extraction method used
            **kwargs: Additional metadata
            
        Returns:
            Standardized result dictionary
        """
        result = {
            'value': value,
            'confidence': confidence,
            'method': method
        }
        
        # Add any additional metadata
        result.update(kwargs)
        
        return result
    
    def log_extraction(self, field: str, success: bool, method: str = None):
        """
        Log extraction attempt
        
        Args:
            field: Field being extracted
            success: Whether extraction succeeded
            method: Method used
        """
        status = "SUCCESS" if success else "FAILED"
        method_str = f" ({method})" if method else ""
        self.logger.debug(f"{status}: {field} extraction{method_str}")