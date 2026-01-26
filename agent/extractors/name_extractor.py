"""
Name Extractor - Enhanced for robust name extraction
FINAL FIXED VERSION - Handles "Rupesh Poudel" correctly
Includes all missing methods and removed common names dependency
"""

import re
from typing import Optional, Dict, Any, List
from .base_extractor import BaseExtractor
import logging

logger = logging.getLogger(__name__)


class NameExtractor(BaseExtractor):
    """Extract names from messages with improved logic - PRODUCTION FIX"""
    
    # Common titles/honorifics
    TITLES = [
        'mr', 'mrs', 'ms', 'miss', 'dr', 'prof', 'sir', 'madam',
        'shri', 'smt', 'kumari', 'sheikh', 'maulana', 'pandit'
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
        'already', 'gave', 'told', 'provided', 'give', 'need',
        'option', 'choose', 'selected', 'selection', 'prefer'
    ]
    
    # Common sentence starters/connectors to remove
    CONNECTOR_WORDS = [
        'my', 'name', 'is', 'am', 'are', 'was', 'were', 'be', 'been',
        'i', 'me', 'mine', 'myself', 'names', 'call', 'called',
        'for', 'in', 'at', 'on', 'by', 'to', 'of', 'from', 'with',
        'about', 'regarding', 'concerning', 'choose', 'selected'
    ]
    
    def extract(self, message: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict]:
        """Extract name from message"""
        message = self.clean_message(message)
        logger.info(f"NameExtractor: Processing message: '{message}'")
        
        # Try extraction methods in order of confidence
        extraction_methods = [
            ('explicit_pattern', self._extract_explicit_name),
            ('with_title', self._extract_name_with_title),
            ('cleaned_message', self._extract_cleaned_message_name),
            ('simple_name', self._extract_simple_name),
            ('proper_noun', self._extract_proper_noun),
            ('history', lambda: self._extract_from_history(context['history']) if context and 'history' in context else None),
        ]
        
        for method_name, method in extraction_methods:
            try:
                name = method(message) if method_name != 'history' else method()
                if name:
                    # Clean and validate the name
                    cleaned_name = self._clean_name_candidate(name)
                    if cleaned_name and self._validate_name_candidate(cleaned_name):
                        logger.info(f"✅ Name extracted via {method_name}: '{cleaned_name}' from '{name}'")
                        return {
                            'name': cleaned_name,
                            'confidence': 'high' if method_name in ['explicit_pattern', 'with_title', 'cleaned_message'] else 'medium',
                            'method': method_name,
                            'original': name
                        }
            except Exception as e:
                logger.debug(f"Method {method_name} failed: {e}")
                continue
        
        logger.warning(f"No name found in message: '{message}'")
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
                logger.debug(f"Explicit pattern match: '{name}'")
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
    
    def _extract_cleaned_message_name(self, message: str) -> Optional[str]:
        """
        Extract name by cleaning the entire message and finding name-like patterns
        This handles cases like "Rupesh poudel" when typed alone
        """
        # Clean the message of non-name content
        cleaned = self._remove_non_name_patterns(message)
        logger.debug(f"Cleaned message for name extraction: '{cleaned}'")
        
        if not cleaned or len(cleaned.strip()) < 2:
            return None
        
        # Split into words
        words = [w for w in cleaned.split() if w]
        
        # Try to find name patterns in the cleaned message
        # First, look for capitalized word pairs (most likely names)
        capitalized_pairs = []
        for i in range(len(words) - 1):
            if words[i][0].isupper() and words[i+1][0].isupper():
                candidate = f"{words[i]} {words[i+1]}"
                if self._validate_name_candidate_raw(candidate):
                    capitalized_pairs.append(candidate)
        
        if capitalized_pairs:
            logger.debug(f"Found capitalized pairs: {capitalized_pairs}")
            # Return the first valid one
            for candidate in capitalized_pairs:
                cleaned_candidate = self._clean_name_candidate(candidate)
                if cleaned_candidate:
                    return cleaned_candidate
        
        # If no capitalized pairs, try all word combinations
        max_words = min(4, len(words))
        
        # Try from longest to shortest combinations
        for word_count in range(max_words, 0, -1):
            for i in range(len(words) - word_count + 1):
                candidate = ' '.join(words[i:i + word_count])
                
                # Validate the raw candidate first
                if self._validate_name_candidate_raw(candidate):
                    cleaned_candidate = self._clean_name_candidate(candidate)
                    if cleaned_candidate and len(cleaned_candidate.split()) >= word_count:
                        logger.debug(f"Validated multi-word candidate: '{cleaned_candidate}'")
                        return cleaned_candidate
        
        # Try single word as last resort
        for word in words:
            if len(word) >= 2 and word[0].isalpha() and not any(c.isdigit() for c in word):
                cleaned_word = self._clean_name_candidate(word)
                if cleaned_word:
                    return cleaned_word
        
        return None
    
    def _extract_simple_name(self, message: str) -> Optional[str]:
        """Extract simple name patterns (2-3 words that look like names)"""
        # Clean the message
        cleaned = self._remove_non_name_patterns(message)
        
        if not cleaned or len(cleaned.strip()) < 2:
            return None
        
        # Look for 2-3 word sequences that look like names
        words = cleaned.split()
        
        # Try 3-word names first (most likely full names)
        if len(words) >= 3:
            for i in range(len(words) - 2):
                candidate = ' '.join(words[i:i + 3])
                if self._validate_name_candidate_raw(candidate):
                    cleaned_candidate = self._clean_name_candidate(candidate)
                    if cleaned_candidate:
                        return cleaned_candidate
        
        # Try 2-word names
        if len(words) >= 2:
            for i in range(len(words) - 1):
                candidate = ' '.join(words[i:i + 2])
                if self._validate_name_candidate_raw(candidate):
                    cleaned_candidate = self._clean_name_candidate(candidate)
                    if cleaned_candidate:
                        return cleaned_candidate
        
        # Try single words
        for word in words:
            if len(word) >= 2 and word[0].isalpha() and not any(c.isdigit() for c in word):
                cleaned_word = self._clean_name_candidate(word)
                if cleaned_word and self._validate_name_candidate_raw(cleaned_word):
                    return cleaned_word
        
        return None
    
    def _extract_proper_noun(self, message: str) -> Optional[str]:
        """Extract proper nouns that look like names"""
        # Patterns for capitalized names
        patterns = [
            # Two capitalized words (like "Rupesh Poudel")
            r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)\b',
            # Three capitalized words
            r'\b([A-Z][a-z]+\s+[A-Z][a-z]+\s+[A-Z][a-z]+)\b',
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
            logger.debug(f"Proper noun candidates: {candidates}")
            return candidates[0]
        
        return None
    
    # BACKWARD COMPATIBILITY METHODS
    def _extract_cleaned_name(self, message: str) -> Optional[str]:
        """Alias for backward compatibility - calls the new method"""
        return self._extract_cleaned_message_name(message)
    
    def _extract_from_history(self, history: List[Dict]) -> Optional[str]:
        """Extract name from conversation history"""
        if not history:
            return None
        
        # Look through recent user messages
        for msg in reversed(history[-10:]):
            if msg.get('role') == 'user':
                content = msg.get('content', '')
                
                # Try all extraction methods
                for method in [
                    self._extract_explicit_name,
                    self._extract_name_with_title,
                    self._extract_cleaned_message_name,
                    self._extract_simple_name,
                    self._extract_proper_noun,
                ]:
                    name = method(content)
                    if name:
                        logger.debug(f"Found name in history: '{name}'")
                        return name
        
        return None
    
    def _clean_name_candidate(self, name: str) -> str:
        """Clean name candidate - LESS AGGRESSIVE for multi-word names"""
        if not name:
            return name
        
        words = name.split()
        
        # Special handling for 2-word names - preserve both words
        if len(words) == 2:
            # Check if both words look like name components
            word1_valid = (len(words[0]) >= 2 and words[0][0].isalpha() and 
                          not any(c.isdigit() for c in words[0]) and
                          words[0].lower() not in self.EXCLUDED_WORDS and
                          words[0].lower() not in self.CONNECTOR_WORDS)
            
            word2_valid = (len(words[1]) >= 2 and words[1][0].isalpha() and 
                          not any(c.isdigit() for c in words[1]) and
                          words[1].lower() not in self.EXCLUDED_WORDS and
                          words[1].lower() not in self.CONNECTOR_WORDS)
            
            if word1_valid and word2_valid:
                # Format both words properly
                formatted = f"{words[0][0].upper()}{words[0][1:].lower()} {words[1][0].upper()}{words[1][1:].lower()}"
                logger.debug(f"Preserving 2-word name: '{formatted}'")
                return formatted
        
        # General cleaning for other cases
        cleaned_words = []
        
        for word in words:
            word_lower = word.lower()
            
            # Skip ONLY obvious connector/excluded words
            if word_lower in self.EXCLUDED_WORDS:
                continue
            
            if word_lower in self.CONNECTOR_WORDS:
                continue
            
            # Keep the word if it's at least 2 characters and alphabetic
            if len(word) >= 2 and word[0].isalpha() and not any(c.isdigit() for c in word):
                cleaned_words.append(word)
        
        # Reconstruct the name
        cleaned_name = ' '.join(cleaned_words)
        
        # Format properly (capitalize)
        if cleaned_name:
            return self._format_name(cleaned_name)
        
        return ""
    
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
        
        # Remove common booking phrases but preserve potential names
        booking_phrases = [
            r'\b(?:book|booking|service|makeup|bridal|party|engagement|wedding|henna|mehendi|package)\b',
            r'\b(?:option|choose|selected|selection|number|please|thank|thanks|hello|hi)\b',
            r'\b(?:price|cost|date|time|location|address|email|phone|whatsapp|contact)\b'
        ]
        
        for phrase in booking_phrases:
            cleaned = re.sub(phrase, '', cleaned, flags=re.IGNORECASE)
        
        # Clean up
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        
        return cleaned
    
    def _validate_name_candidate(self, name: str) -> bool:
        """Validate if string is likely a name"""
        return self._validate_name_candidate_raw(name)
    
    def _validate_name_candidate_raw(self, name: str) -> bool:
        """Validate name BEFORE cleaning - more lenient for multi-word names"""
        if not name or len(name.strip()) < 2:
            return False
        
        words = name.strip().split()
        
        # Must have at least 1 word, max 4
        if len(words) < 1 or len(words) > 4:
            return False
        
        # For multi-word names (like "Rupesh Poudel")
        if len(words) >= 2:
            valid_words = 0
            
            for word in words:
                word_lower = word.lower()
                
                # Must be at least 2 characters
                if len(word) < 2:
                    return False
                
                # Must start with a letter
                if not word[0].isalpha():
                    return False
                
                # No digits allowed
                if any(c.isdigit() for c in word):
                    return False
                
                # Skip if it's a clear non-name word
                if word_lower in self.EXCLUDED_WORDS:
                    return False
                
                # Count valid words
                valid_words += 1
            
            # For 2-word names, both should be valid
            # For 3-4 word names, at least 2 should be valid
            if len(words) == 2:
                return valid_words == 2
            else:
                return valid_words >= 2
        
        # For single words
        if len(words) == 1:
            word = words[0]
            word_lower = word.lower()
            
            # Check excluded words
            if word_lower in self.EXCLUDED_WORDS:
                return False
            
            # Check connector words
            if word_lower in self.CONNECTOR_WORDS:
                return False
            
            # Must be at least 2 characters
            if len(word) < 2:
                return False
            
            # No digits
            if any(c.isdigit() for c in word):
                return False
            
            # Valid single word name
            return True
        
        return False
    
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
            
            # Capitalize first letter, rest lowercase
            if len(word) > 1:
                formatted = word[0].upper() + word[1:].lower()
            else:
                formatted = word.upper()
            formatted_words.append(formatted)
        
        return ' '.join(formatted_words)