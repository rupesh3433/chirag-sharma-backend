import time
from collections import defaultdict
from typing import Dict, List, Tuple
import threading

class RateLimiter:
    """Improved in-memory rate limiter with thread safety"""
    
    def __init__(self, max_requests: int = 15, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests: Dict[str, List[float]] = defaultdict(list)
        self.lock = threading.RLock()
    
    def check_rate_limit(self, key: str) -> bool:
        """
        Check if request is within rate limit
        """
        with self.lock:
            now = time.time()
            
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if now - req_time < self.window_seconds
            ]
            
            if len(self.requests[key]) >= self.max_requests:
                return False
            
            self.requests[key].append(now)
            return True
    
    def get_remaining(self, key: str) -> int:
        """Get remaining requests in current window"""
        with self.lock:
            now = time.time()
            
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if now - req_time < self.window_seconds
            ]
            
            return max(0, self.max_requests - len(self.requests[key]))
    
    def get_reset_time(self, key: str) -> float:
        """Get time until rate limit resets (in seconds)"""
        with self.lock:
            if not self.requests[key]:
                return 0
            
            now = time.time()
            
            valid_requests = [
                req_time for req_time in self.requests[key]
                if now - req_time < self.window_seconds
            ]
            
            if not valid_requests:
                return 0
            
            oldest_request = min(valid_requests)
            reset_time = oldest_request + self.window_seconds - now
            
            return max(0, reset_time)
    
    def get_status(self, key: str) -> Dict[str, any]:
        """Get detailed rate limit status for a key"""
        with self.lock:
            now = time.time()
            
            self.requests[key] = [
                req_time for req_time in self.requests[key]
                if now - req_time < self.window_seconds
            ]
            
            remaining = self.get_remaining(key)
            reset_time = self.get_reset_time(key)
            
            return {
                "key": key,
                "requests_used": len(self.requests[key]),
                "requests_allowed": self.max_requests,
                "requests_remaining": remaining,
                "window_seconds": self.window_seconds,
                "reset_in_seconds": reset_time,
                "is_rate_limited": remaining == 0
            }
    
    def cleanup_old_entries(self, max_age_seconds: int = 3600):
        """Clean up old rate limit entries"""
        with self.lock:
            now = time.time()
            keys_to_remove = []
            
            for key, timestamps in self.requests.items():
                recent_timestamps = [
                    ts for ts in timestamps
                    if now - ts < max_age_seconds
                ]
                
                if recent_timestamps:
                    self.requests[key] = recent_timestamps
                else:
                    keys_to_remove.append(key)
            
            for key in keys_to_remove:
                del self.requests[key]
            
            return len(keys_to_remove)

rate_limiter = RateLimiter(max_requests=20, window_seconds=60)