"""
Name Extractor - Enhanced for robust name extraction
"""

import re
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor


class NameExtractor(BaseExtractor):
    """Extract names from messages with improved logic"""
    
    # Common titles/honorifics
    TITLES = [
        'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'sir', 'madam',
        'shri', 'smt', 'kumari', 'sheikh', 'maulana', 'pandit'
    ]
    
    # Common Indian/Nepali name patterns
    COMMON_FIRST_NAMES = [
        'amit', 'rahul', 'priya', 'sneha', 'rajesh', 'suresh', 'pooja',
        'anita', 'sunita', 'manish', 'rakesh', 'deepak', 'sanjay',
        'vijay', 'ajay', 'anil', 'sunil', 'raj', 'ravi', 'arjun',
        'krishna', 'ram', 'sita', 'gita', 'maya', 'devi', 'kumar',
        'rupesh', 'poudel', 'chirag', 'sharma', 'john', 'smith', 
        'david', 'michael', 'james', 'robert', 'mary', 'jennifer',
        'linda', 'susan', 'patel', 'singh', 'khan', 'verma', 'sharma'
    ]
    
    # Words that are NOT names
    EXCLUDED_WORDS = [
        'book', 'booking', 'service', 'makeup', 'bridal', 'party',
        'engagement', 'wedding', 'henna', 'mehendi', 'package',
        'price', 'cost', 'date', 'time', 'location', 'address',
        'email', 'phone', 'whatsapp', 'number', 'contact',
        'hello', 'hi', 'hey', 'thanks', 'please', 'yes', 'no',
        'want', 'need', 'like', 'today', 'tomorrow', 'yesterday',
        'india', 'nepal', 'pakistan', 'bangladesh', 'dubai',
        'mumbai', 'delhi', 'pune', 'kathmandu', 'karachi', 'dhaka',
        'and', 'the', 'for', 'with', 'this', 'that', 'have', 'has',
        'thank', 'you', 'can', 'could', 'would', 'let', 'me',
        'already', 'gave', 'told', 'provided', 'give', 'need'
    ]
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract name from message"""
        message = self.clean_message(message)
        
        # Try explicit name patterns first
        name = self._extract_explicit_name(message)
        if name:
            return {
                'name': name,
                'confidence': 'high',
                'method': 'explicit'
            }
        
        # Try name with title pattern
        name = self._extract_name_with_title(message)
        if name:
            return {
                'name': name,
                'confidence': 'high',
                'method': 'with_title'
            }
        
        # Try to find proper noun patterns
        name = self._extract_proper_noun(message)
        if name:
            return {
                'name': name,
                'confidence': 'medium',
                'method': 'proper_noun'
            }
        
        # Try simple name detection for short messages (2-3 words)
        name = self._extract_simple_name(message)
        if name:
            return {
                'name': name,
                'confidence': 'medium',
                'method': 'simple'
            }
        
        # Try from conversation context
        if context and 'history' in context:
            name = self._extract_from_history(context['history'])
            if name:
                return {
                    'name': name,
                    'confidence': 'low',
                    'method': 'history'
                }
        
        return None
    
    def _extract_explicit_name(self, message: str) -> Optional[str]:
        """Extract name from explicit patterns like 'my name is...'"""
        patterns = [
            # "My name is John Doe"
            r'(?:my\s+)?name\s+(?:is|:)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            # "My name is john doe" (lowercase)
            r'(?:my\s+)?name\s+(?:is|:)\s+([a-z]+\s+[a-z]+(?:\s+[a-z]+)?)',
            # "I am John Doe" / "I'm John Doe"
            r'I\s+(?:am|\'m)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            # "I am john doe" (lowercase)
            r'I\s+(?:am|\'m)\s+([a-z]+\s+[a-z]+(?:\s+[a-z]+)?)',
            # "This is John Doe"
            r'(?:this\s+is|it\'s)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            # "Name: John Doe"
            r'name\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            # "Name: john doe" (lowercase)
            r'name\s*:\s*([a-z]+\s+[a-z]+(?:\s+[a-z]+)?)',
            # Hindi/Nepali patterns
            r'(?:mera|मेरा)\s+(?:naam|नाम)\s+(?:hai|है)\s+([A-Za-z]+(?:\s+[A-Za-z]+){1,3})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                if self._validate_name_candidate(name):
                    return self._format_name(name)
        
        return None
    
    def _extract_name_with_title(self, message: str) -> Optional[str]:
        """Extract name that starts with a title"""
        # Build title pattern
        title_pattern = '|'.join(self.TITLES)
        
        # Pattern: "Mr. John Doe" or "Dr John Doe"
        pattern = rf'\b(?:{title_pattern})\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,3}})\b'
        
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            name_part = match.group(1).strip()
            if self._validate_name_candidate(name_part):
                # Include title in formatted name
                title = match.group(0).split()[0]
                formatted_name = f"{title.title()}. {self._format_name(name_part)}"
                return formatted_name
        
        return None
    
    def _extract_proper_noun(self, message: str) -> Optional[str]:
        """Extract proper nouns that look like names (case-insensitive)"""
        # First check for 2-3 capitalized words in a row
        patterns = [
            # Two capitalized words
            r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b',
            # Three capitalized words
            r'\b([A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+)\b',
        ]
        
        candidates = []
        for pattern in patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                candidate = match.group(1).strip()
                if self._validate_name_candidate(candidate):
                    candidates.append(candidate)
        
        # Return the first valid candidate
        if candidates:
            # Prefer longer names (more specific)
            candidates.sort(key=lambda x: len(x.split()), reverse=True)
            return self._format_name(candidates[0])
        
        return None
    
    def _extract_simple_name(self, message: str) -> Optional[str]:
        """Extract simple name patterns (2-3 lowercase words)"""
        # Clean message - remove common patterns that are not names
        clean_msg = message.lower()
        
        # Remove any email, phone, date patterns first
        clean_msg = re.sub(r'\+\d{10,15}', '', clean_msg)  # Remove phone
        clean_msg = re.sub(r'\S+@\S+\.\S+', '', clean_msg)  # Remove email
        clean_msg = re.sub(r'\b\d{1,2}[-/]\d{1,2}[-/]\d{4}\b', '', clean_msg)  # Remove date
        clean_msg = re.sub(r'\b\d{5,6}\b', '', clean_msg)  # Remove pincode
        
        # Also remove common booking-related words
        for word in self.EXCLUDED_WORDS:
            clean_msg = re.sub(rf'\b{word}\b', '', clean_msg, flags=re.IGNORECASE)
        
        # Clean extra spaces
        clean_msg = re.sub(r'\s+', ' ', clean_msg).strip()
        
        # Look for 2-3 word sequences that look like names
        # Pattern for 2-3 words, each at least 2 characters
        pattern = r'\b([a-z]{2,}\s+[a-z]{2,}(?:\s+[a-z]{2,})?)\b'
        
        matches = re.findall(pattern, clean_msg)
        for name_candidate in matches:
            # Skip if it's too long or too short
            words = name_candidate.split()
            if len(words) not in [2, 3]:
                continue
                
            # Check if it's likely a name (not a sentence or common phrase)
            if self._looks_like_name(words):
                return self._format_name(name_candidate)
        
        return None
    
    def _extract_from_history(self, history: List[Dict]) -> Optional[str]:
        """Extract name from conversation history"""
        if not history:
            return None
        
        # Look through recent user messages
        for msg in reversed(history[-10:]):
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                
                # Try extraction methods
                name = self._extract_explicit_name(content)
                if name:
                    return name
                
                name = self._extract_name_with_title(content)
                if name:
                    return name
                
                name = self._extract_proper_noun(content)
                if name:
                    return name
        
        return None
    
    def _looks_like_name(self, words: List[str]) -> bool:
        """Check if words look like a name"""
        candidate = ' '.join(words).lower()
        
        # Common non-name phrases
        non_names = [
            'thank you', 'please help', 'hello there', 'hi there', 
            'can you', 'could you', 'would you', 'let me',
            'i want', 'i need', 'my booking', 'the service',
            'how much', 'what is', 'tell me', 'show me'
        ]
        
        if candidate in non_names:
            return False
        
        # Check if words are too generic
        generic_words = ['and', 'the', 'for', 'with', 'this', 'that', 'have', 'has']
        if any(word in generic_words for word in words):
            return False
        
        # Check if at least one word looks like a common name
        return any(word in self.COMMON_FIRST_NAMES for word in words)
    
    def _validate_name_candidate(self, name: str) -> bool:
        """Validate if string is likely a name"""
        if not name or len(name) < 2:
            return False
        
        # Split into words
        words = name.split()
        
        # Check word count (1-4 words for names)
        if len(words) < 1 or len(words) > 4:
            return False
        
        # Check each word
        for word in words:
            word_lower = word.lower()
            
            # Check minimum length
            if len(word) < 2:
                return False
            
            # Check if it's an excluded word
            if word_lower in self.EXCLUDED_WORDS:
                return False
            
            # Check if it has digits (names shouldn't have digits)
            if any(c.isdigit() for c in word):
                return False
            
            # Check if it's all uppercase (likely acronym, not name)
            if word.isupper() and len(word) > 1:
                return False
        
        # Additional validation for single words
        if len(words) == 1:
            word_lower = words[0].lower()
            # Single word should be a common first name or at least 3 chars
            if len(words[0]) < 3 and word_lower not in self.COMMON_FIRST_NAMES:
                return False
        
        # Check if the whole phrase is not in excluded list
        full_phrase = ' '.join([w.lower() for w in words])
        if full_phrase in self.EXCLUDED_WORDS:
            return False
        
        return True
    
    def _format_name(self, name: str) -> str:
        """Format name (capitalize properly)"""
        # Split into words
        words = name.split()
        
        # Special cases for titles
        if len(words) > 1 and words[0].lower() in self.TITLES:
            # Format title with dot
            title = words[0].lower()
            if not title.endswith('.'):
                title = title + '.'
            formatted_words = [title.title()]
            # Format the rest of the name
            for word in words[1:]:
                formatted_words.append(word.capitalize())
            return ' '.join(formatted_words)
        
        # Regular capitalization for all words
        formatted_words = []
        for word in words:
            # Skip empty words
            if not word:
                continue
            
            # Capitalize first letter, rest lowercase
            formatted_word = word[0].upper() + word[1:].lower()
            formatted_words.append(formatted_word)
        
        return ' '.join(formatted_words)
    
    def _find_name_patterns(self, message: str) -> list:
        """Find potential name patterns (legacy method)"""
        candidates = []
        
        # Pattern 1: Sequences of capitalized words
        pattern1 = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
        matches = re.finditer(pattern1, message)
        for match in matches:
            candidates.append(match.group(1))
        
        # Pattern 2: After "name is/:" or similar
        pattern2 = r'(?:name\s+(?:is|:)|my\s+name\s+is|I\s+am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})'
        matches = re.finditer(pattern2, message, re.IGNORECASE)
        for match in matches:
            candidates.append(match.group(1))
        
        return candidates