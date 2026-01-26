"""
Name Extractor - Enhanced for robust name extraction
ENHANCED VERSION
"""

import re
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor


class NameExtractor(BaseExtractor):
    """Extract names from messages with improved logic - ENHANCED"""
    
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
    
    # Common sentence starters/connectors to remove
    CONNECTOR_WORDS = [
        'my', 'name', 'is', 'am', 'are', 'was', 'were', 'be', 'been',
        'i', 'me', 'mine', 'myself', 'names', 'call', 'called',
        'for', 'in', 'at', 'on', 'by', 'to', 'of', 'from', 'with',
        'about', 'regarding', 'concerning'
    ]
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract name from message"""
        message = self.clean_message(message)
        
        # Try extraction methods in order of confidence
        extraction_methods = [
            ('explicit_pattern', self._extract_explicit_name),
            ('with_title', self._extract_name_with_title),
            ('proper_noun', self._extract_proper_noun),
            ('cleaned_simple', self._extract_cleaned_name),  # New method
            ('simple', self._extract_simple_name),
            ('history', lambda: self._extract_from_history(context['history']) if context and 'history' in context else None),
        ]
        
        for method_name, method in extraction_methods:
            try:
                name = method(message) if method_name != 'history' else method()
                if name:
                    # Clean and validate the name
                    cleaned_name = self._clean_name_candidate(name)
                    if cleaned_name and self._validate_name_candidate(cleaned_name):
                        return {
                            'name': cleaned_name,
                            'confidence': 'high' if method_name in ['explicit_pattern', 'with_title'] else 'medium',
                            'method': method_name,
                            'original': name
                        }
            except Exception:
                continue
        
        return None
    
    def _extract_explicit_name(self, message: str) -> Optional[str]:
        """Extract name from explicit patterns like 'my name is...'"""
        patterns = [
            # "My name is John Doe" (case sensitive)
            r'(?:my\s+)?name\s+(?:is|:)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            # "My name is john doe" (case insensitive)
            r'(?:my\s+)?name\s+(?:is|:)\s+([a-z]+\s+[a-z]+(?:\s+[a-z]+)?)',
            # "I am John Doe" / "I'm John Doe"
            r'I\s+(?:am|\'m)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            # "I am john doe"
            r'I\s+(?:am|\'m)\s+([a-z]+\s+[a-z]+(?:\s+[a-z]+)?)',
            # "This is John Doe"
            r'(?:this\s+is|it\'s)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            # "Name: John Doe"
            r'name\s*:\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})',
            # "Name: john doe"
            r'name\s*:\s*([a-z]+\s+[a-z]+(?:\s+[a-z]+)?)',
            # Hindi/Nepali patterns
            r'(?:mera|मेरा)\s+(?:naam|नाम)\s+(?:hai|है)\s+([A-Za-z]+(?:\s+[A-Za-z]+){1,3})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, message, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Clean the extracted name
                cleaned = self._clean_name_candidate(name)
                if cleaned:
                    return cleaned
        
        return None
    
    def _extract_name_with_title(self, message: str) -> Optional[str]:
        """Extract name that starts with a title"""
        title_pattern = '|'.join(self.TITLES)
        pattern = rf'\b(?:{title_pattern})\.?\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){{1,3}})\b'
        
        match = re.search(pattern, message, re.IGNORECASE)
        if match:
            name_part = match.group(1).strip()
            title = match.group(0).split()[0]
            
            # Format title properly
            if not title.endswith('.'):
                title = title + '.'
            
            cleaned_name = self._clean_name_candidate(name_part)
            if cleaned_name:
                return f"{title.title()} {cleaned_name}"
        
        return None
    
    def _extract_proper_noun(self, message: str) -> Optional[str]:
        """Extract proper nouns that look like names"""
        # Patterns for capitalized names
        patterns = [
            # Two capitalized words
            r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b',
            # Three capitalized words
            r'\b([A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+)\b',
            # Single capitalized word that's a common name
            rf'\b({"|".join([name.capitalize() for name in self.COMMON_FIRST_NAMES])})\b',
        ]
        
        candidates = []
        for pattern in patterns:
            matches = re.finditer(pattern, message)
            for match in matches:
                candidate = match.group(1).strip()
                cleaned = self._clean_name_candidate(candidate)
                if cleaned:
                    candidates.append(cleaned)
        
        if candidates:
            # Prefer longer names
            candidates.sort(key=lambda x: len(x.split()), reverse=True)
            return candidates[0]
        
        return None
    
    def _extract_cleaned_name(self, message: str) -> Optional[str]:
        """Extract and clean name from any part of message - ENHANCED VERSION"""
        # Remove common non-name patterns first
        cleaned_msg = self._remove_non_name_patterns(message)
        
        # Look for word sequences that might be names
        words = cleaned_msg.split()
        
        if not words:
            return None
        
        # Try different combinations, starting with LONGEST combinations first
        # This ensures we get full names like "Rupesh Poudel" before partial matches
        max_words = min(4, len(words))  # Try up to 4-word names
        
        # Start from longest combinations down to shortest
        for word_count in range(max_words, 0, -1):
            for i in range(len(words) - word_count + 1):
                candidate = ' '.join(words[i:i + word_count])
                
                # Clean and validate
                cleaned = self._clean_name_candidate(candidate)
                if cleaned and self._validate_name_candidate(cleaned):
                    # Additional check: prefer names with 2+ words over single words
                    if word_count >= 2 or len(cleaned.split()) >= 2:
                        return cleaned
        
        # If no multi-word names found, try single words as last resort
        for word in words:
            if len(word) >= 3:  # Minimum 3 characters for a name
                cleaned = self._clean_name_candidate(word)
                if cleaned and self._validate_name_candidate(cleaned):
                    # Only return single word if it's a known common name
                    if word.lower() in self.COMMON_FIRST_NAMES:
                        return cleaned
        
        return None
    
    def _extract_simple_name(self, message: str) -> Optional[str]:
        """Extract simple name patterns (2-3 lowercase words)"""
        clean_msg = message.lower()
        
        # Remove non-name patterns
        clean_msg = self._remove_non_name_patterns(clean_msg)
        
        # Also remove common booking-related words
        for word in self.EXCLUDED_WORDS + self.CONNECTOR_WORDS:
            clean_msg = re.sub(rf'\b{word}\b', '', clean_msg, flags=re.IGNORECASE)
        
        # Clean extra spaces
        clean_msg = re.sub(r'\s+', ' ', clean_msg).strip()
        
        # Look for 2-3 word sequences
        pattern = r'\b([a-z]{2,}\s+[a-z]{2,}(?:\s+[a-z]{2,})?)\b'
        
        matches = re.findall(pattern, clean_msg)
        for name_candidate in matches:
            words = name_candidate.split()
            if len(words) not in [2, 3]:
                continue
                
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
                
                # Try all extraction methods
                name = self._extract_explicit_name(content)
                if name:
                    return name
                
                name = self._extract_name_with_title(content)
                if name:
                    return name
                
                name = self._extract_proper_noun(content)
                if name:
                    return name
                
                name = self._extract_cleaned_name(content)
                if name:
                    return name
        
        return None
    
    def _clean_name_candidate(self, name: str) -> str:
        """Clean name candidate by removing unwanted words"""
        if not name:
            return name
        
        words = name.split()
        cleaned_words = []
        
        for word in words:
            word_lower = word.lower()
            
            # Skip connector words and excluded words
            if word_lower in self.CONNECTOR_WORDS or word_lower in self.EXCLUDED_WORDS:
                continue
            
            # Skip very short words unless they're common names
            if len(word) < 2 and word_lower not in self.COMMON_FIRST_NAMES:
                continue
            
            # Skip digits
            if any(c.isdigit() for c in word):
                continue
            
            cleaned_words.append(word)
        
        # Reconstruct the name
        cleaned_name = ' '.join(cleaned_words)
        
        # Remove any remaining unwanted patterns
        cleaned_name = re.sub(r'\s+', ' ', cleaned_name).strip()
        
        # Check if it looks reasonable
        if len(cleaned_name) < 2:
            return ""
        
        # Format properly
        return self._format_name(cleaned_name)
    
    def _remove_non_name_patterns(self, message: str) -> str:
        """Remove patterns that are definitely not names"""
        cleaned = message
        
        # Remove email patterns
        cleaned = re.sub(r'\S+@\S+\.\S+', '', cleaned)
        
        # Remove phone patterns
        cleaned = re.sub(r'\+\d[\d\s\-\(\)]{8,}', '', cleaned)
        cleaned = re.sub(r'\b\d{10,}\b', '', cleaned)
        
        # Remove date patterns
        cleaned = re.sub(r'\b\d{1,2}[-/\.]\d{1,2}[-/\.]\d{2,4}\b', '', cleaned)
        cleaned = re.sub(r'\b\d{4}[-/\.]\d{1,2}[-/\.]\d{1,2}\b', '', cleaned)
        
        # Remove month names with numbers
        months = ['jan', 'feb', 'mar', 'apr', 'may', 'jun', 'jul', 'aug', 'sep', 'oct', 'nov', 'dec']
        for month in months:
            cleaned = re.sub(rf'\b{month}\s+\d{{1,2}}\b', '', cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(rf'\b\d{{1,2}}\s+{month}\b', '', cleaned, flags=re.IGNORECASE)
        
        # Remove pincodes
        cleaned = re.sub(r'\b\d{5,6}\b', '', cleaned)
        
        # Remove standalone years
        cleaned = re.sub(r'\b(202[4-9]|203[0-9])\b', '', cleaned)
        
        # Clean up
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _looks_like_name(self, words: List[str]) -> bool:
        """Check if words look like a name"""
        if not words:
            return False
        
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
        
        # Check for connector words
        if any(word in self.CONNECTOR_WORDS for word in words):
            return False
        
        # Check if too generic
        generic_words = ['and', 'the', 'for', 'with', 'this', 'that', 'have', 'has']
        if any(word in generic_words for word in words):
            return False
        
        # Check if at least one word looks like a common name
        return any(word in self.COMMON_FIRST_NAMES for word in words)
    
    def _validate_name_candidate(self, name: str) -> bool:
        """Validate if string is likely a name - ENHANCED"""
        if not name or len(name) < 2:
            return False
        
        words = name.split()
        
        # Check word count (1-4 words for names)
        if len(words) < 1 or len(words) > 4:
            return False
        
        # For single words, check if it's a common name
        if len(words) == 1:
            word_lower = words[0].lower()
            
            # Single letters or very short strings are not names
            if len(words[0]) < 2:
                return False
                
            # Check if it's in excluded words
            if word_lower in self.EXCLUDED_WORDS:
                return False
                
            # Check if it's a connector word
            if word_lower in self.CONNECTOR_WORDS:
                return False
                
            # No digits
            if any(c.isdigit() for c in words[0]):
                return False
                
            # Must be at least 2 characters and look like a name
            return len(words[0]) >= 2 and words[0][0].isalpha()
        
        # For multi-word names (like "Rupesh Poudel")
        valid_word_count = 0
        
        for word in words:
            word_lower = word.lower()
            
            # Minimum length
            if len(word) < 2:
                return False
            
            # Check excluded words
            if word_lower in self.EXCLUDED_WORDS:
                return False
            
            # Check connector words
            if word_lower in self.CONNECTOR_WORDS:
                return False
            
            # No digits
            if any(c.isdigit() for c in word):
                return False
            
            # Not all uppercase (unless it's a title abbreviation)
            if word.isupper() and len(word) > 2:
                return False
            
            # Count valid words
            if len(word) >= 2 and word[0].isalpha():
                valid_word_count += 1
        
        # At least half of the words should be valid
        return valid_word_count >= max(2, len(words) // 2)
    
    def _format_name(self, name: str) -> str:
        """Format name (capitalize properly)"""
        if not name:
            return name
        
        words = name.split()
        formatted_words = []
        
        for i, word in enumerate(words):
            # Skip empty words
            if not word:
                continue
            
            word_lower = word.lower()
            
            # Handle titles
            if i == 0 and word_lower in self.TITLES:
                formatted = word_lower.title()
                if not formatted.endswith('.'):
                    formatted = formatted + '.'
                formatted_words.append(formatted)
                continue
            
            # Check if it's a common name that should stay capitalized
            if word_lower in self.COMMON_FIRST_NAMES:
                formatted_words.append(word.capitalize())
            else:
                # Capitalize first letter, rest lowercase
                formatted = word[0].upper() + word[1:].lower() if len(word) > 1 else word.upper()
                formatted_words.append(formatted)
        
        return ' '.join(formatted_words)
    
    def _find_name_patterns(self, message: str) -> list:
        """Find potential name patterns (legacy method)"""
        candidates = []
        
        pattern1 = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b'
        matches = re.finditer(pattern1, message)
        for match in matches:
            candidates.append(match.group(1))
        
        pattern2 = r'(?:name\s+(?:is|:)|my\s+name\s+is|I\s+am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})'
        matches = re.finditer(pattern2, message, re.IGNORECASE)
        for match in matches:
            candidates.append(match.group(1))
        
        return candidates
    
    def extract_all_possible(self, message: str) -> List[Dict]:
        """Extract all possible names from message"""
        results = []
        seen = set()
        
        methods = [
            ('explicit', self._extract_explicit_name),
            ('with_title', self._extract_name_with_title),
            ('proper_noun', self._extract_proper_noun),
            ('cleaned', self._extract_cleaned_name),
            ('simple', self._extract_simple_name),
        ]
        
        for method_name, method in methods:
            name = method(message)
            if name and name not in seen:
                cleaned = self._clean_name_candidate(name)
                if cleaned and self._validate_name_candidate(cleaned):
                    results.append({
                        'name': cleaned,
                        'method': method_name,
                        'original': name
                    })
                    seen.add(cleaned)
        
        return results