import time
from collections import defaultdict
from typing import Dict, List

class RateLimiter:
    """Simple in-memory rate limiter"""
    
    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)
    
    def check_rate_limit(self, key: str) -> bool:
        """
        Check if request is within rate limit
        
        Args:
            key: Identifier (session_id, IP, etc.)
            
        Returns:
            True if allowed, False if rate limited
        """
        now = time.time()
        
        # Clean old requests outside the window
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if now - req_time < self.window_seconds
        ]
        
        # Check if exceeded limit
        if len(self.requests[key]) >= self.max_requests:
            return False
        
        # Add current request
        self.requests[key].append(now)
        return True
    
    def get_remaining(self, key: str) -> int:
        """Get remaining requests in current window"""
        now = time.time()
        
        # Clean old requests
        self.requests[key] = [
            req_time for req_time in self.requests[key]
            if now - req_time < self.window_seconds
        ]
        
        return max(0, self.max_requests - len(self.requests[key]))
    
    def get_reset_time(self, key: str) -> float:
        """Get time until rate limit resets (in seconds)"""
        if not self.requests[key]:
            return 0
        
        now = time.time()
        oldest_request = min(self.requests[key])
        reset_time = oldest_request + self.window_seconds - now
        
        return max(0, reset_time)

# Global rate limiter instance
rate_limiter = RateLimiter(max_requests=15, window_seconds=60)