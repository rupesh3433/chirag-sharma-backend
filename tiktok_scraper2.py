#!/usr/bin/env python3
"""
TikTok Public Profile Scraper
Scrapes publicly available user and video metadata from TikTok profiles.
No authentication, no video downloads, no external APIs.
"""

import json
import re
import sys
import subprocess
from typing import Dict, List, Optional, Any
from urllib.parse import quote

# Note: Using curl via subprocess to bypass Python SSL/TLS issues on Windows


def fetch_html_with_curl(url: str) -> str:
    """
    Fetch HTML using system curl to bypass Python SSL/TLS issues.
    
    Args:
        url: URL to fetch
    
    Returns:
        HTML content as string
    
    Raises:
        Exception: If curl fails
    """
    result = subprocess.run(
        [
            "curl",
            "-L",  # Follow redirects
            "--compressed",  # Accept gzip/deflate
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "-H", "Accept: text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "-H", "Accept-Language: en-US,en;q=0.9",
            "--max-time", "30",  # 30 second timeout
            url
        ],
        capture_output=True,
        text=True,
        timeout=35
    )
    
    if result.returncode != 0:
        raise Exception(f"curl failed with code {result.returncode}: {result.stderr}")
    
    if not result.stdout:
        raise Exception("curl returned empty response")
    
    return result.stdout


class TikTokScraper:
    """Scraper for TikTok public profile data."""
    
    def scrape_profile(self, username: str) -> Dict[str, Any]:
        """
        Scrape a TikTok user profile and return structured data.
        
        Args:
            username: TikTok username (without @)
        
        Returns:
            Dictionary with 'user' and 'videos' keys
        """
        # Ensure username doesn't have @ prefix
        username = username.lstrip('@')
        
        # Construct profile URL
        profile_url = f"https://www.tiktok.com/@{quote(username)}"
        
        try:
            # Fetch the profile page using curl (bypasses Python SSL issues)
            html_content = fetch_html_with_curl(profile_url)
            
        except Exception as e:
            error_msg = str(e).lower()
            # Check if it's a 404 error
            if '404' in error_msg or 'not found' in error_msg:
                return {
                    "error": "Profile not found",
                    "username": username,
                    "user": None,
                    "videos": []
                }
            raise Exception(f"Error fetching profile: {e}")
        
        # Extract JSON data from HTML
        json_data = self._extract_next_data(html_content)
        
        if not json_data:
            return {
                "error": "Could not extract data from page",
                "username": username,
                "user": None,
                "videos": []
            }
        
        # Parse user and video data
        user_data = self._parse_user_data(json_data, username)
        video_data = self._parse_video_data(json_data)
        
        return {
            "user": user_data,
            "videos": video_data
        }
    
    def _extract_next_data(self, html: str) -> Optional[Dict]:
        """
        Extract JSON data from __NEXT_DATA__ script tag.
        
        Args:
            html: Raw HTML content
        
        Returns:
            Parsed JSON data or None
        """
        # Pattern to match __NEXT_DATA__ script tag
        pattern = r'<script\s+id="__NEXT_DATA__"\s+type="application/json"\s*>(.*?)</script>'
        
        match = re.search(pattern, html, re.DOTALL)
        if not match:
            # Try alternative pattern without attributes order
            pattern = r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>'
            match = re.search(pattern, html, re.DOTALL)
        
        if not match:
            return None
        
        try:
            json_str = match.group(1)
            data = json.loads(json_str)
            return data
        except json.JSONDecodeError as e:
            print(f"Warning: Failed to parse JSON data: {e}")
            return None
    
    def _parse_user_data(self, json_data: Dict, username: str) -> Optional[Dict[str, Any]]:
        """
        Parse user metadata from JSON data.
        
        Args:
            json_data: Parsed __NEXT_DATA__ JSON
            username: Username being scraped
        
        Returns:
            User metadata dictionary
        """
        try:
            # Navigate to user data - structure may vary
            props = json_data.get('props', {})
            page_props = props.get('pageProps', {})
            
            # Try multiple possible paths to user data
            user_info = None
            
            # Path 1: Direct userInfo
            if 'userInfo' in page_props:
                user_info = page_props['userInfo']
            
            # Path 2: Nested in user object
            elif 'user' in page_props:
                user_info = page_props['user']
            
            # Path 3: Inside userData
            elif 'userData' in page_props:
                user_info = page_props['userData']
            
            if not user_info:
                return None
            
            # Extract user fields with safe navigation
            user_detail = user_info.get('user', user_info)
            stats = user_info.get('stats', {})
            
            return {
                "internal_user_id": self._safe_get(user_detail, 'id'),
                "username": self._safe_get(user_detail, 'uniqueId', username),
                "nickname": self._safe_get(user_detail, 'nickname'),
                "bio": self._safe_get(user_detail, 'signature'),
                "verified": self._safe_get(user_detail, 'verified', False),
                "followers_count": self._safe_get(stats, 'followerCount', 0),
                "following_count": self._safe_get(stats, 'followingCount', 0),
                "total_likes_count": self._safe_get(stats, 'heartCount', 0),
                "video_count": self._safe_get(stats, 'videoCount', 0),
                "profile_picture_url": self._get_profile_picture(user_detail),
            }
            
        except Exception as e:
            print(f"Warning: Error parsing user data: {e}")
            return None
    
    def _parse_video_data(self, json_data: Dict) -> List[Dict[str, Any]]:
        """
        Parse video metadata from JSON data.
        
        Args:
            json_data: Parsed __NEXT_DATA__ JSON
        
        Returns:
            List of video metadata dictionaries
        """
        videos = []
        
        try:
            props = json_data.get('props', {})
            page_props = props.get('pageProps', {})
            
            # Try multiple possible paths to video data
            video_list = None
            
            # Path 1: Direct itemList
            if 'itemList' in page_props:
                video_list = page_props['itemList']
            
            # Path 2: Nested in items
            elif 'items' in page_props:
                video_list = page_props['items']
            
            # Path 3: Inside videos array
            elif 'videos' in page_props:
                video_list = page_props['videos']
            
            # Path 4: Inside userData
            elif 'userData' in page_props:
                user_data = page_props['userData']
                video_list = user_data.get('itemList', user_data.get('videos', []))
            
            if not video_list:
                return []
            
            # Parse each video
            for item in video_list:
                video = self._parse_single_video(item)
                if video:
                    videos.append(video)
            
        except Exception as e:
            print(f"Warning: Error parsing video data: {e}")
        
        return videos
    
    def _parse_single_video(self, item: Dict) -> Optional[Dict[str, Any]]:
        """
        Parse a single video item.
        
        Args:
            item: Video item dictionary
        
        Returns:
            Video metadata dictionary
        """
        try:
            # Extract video fields
            video_id = self._safe_get(item, 'id')
            
            # Video stats
            stats = item.get('stats', {})
            
            # Music/sound info
            music = item.get('music', {})
            
            # Author info
            author = item.get('author', {})
            
            # Video object for technical details
            video_obj = item.get('video', {})
            
            return {
                "video_id": video_id,
                "video_url": f"https://www.tiktok.com/@{author.get('uniqueId', 'unknown')}/video/{video_id}" if video_id else None,
                "description": self._safe_get(item, 'desc'),
                "create_time": self._safe_get(item, 'createTime'),
                "duration": self._safe_get(video_obj, 'duration'),
                "thumbnail_url": self._get_thumbnail_url(video_obj),
                "view_count": self._safe_get(stats, 'playCount', 0),
                "like_count": self._safe_get(stats, 'diggCount', 0),
                "comment_count": self._safe_get(stats, 'commentCount', 0),
                "share_count": self._safe_get(stats, 'shareCount', 0),
                "author_id": self._safe_get(author, 'id'),
                "author_username": self._safe_get(author, 'uniqueId'),
                "music_title": self._safe_get(music, 'title'),
                "music_author": self._safe_get(music, 'authorName'),
                "music_id": self._safe_get(music, 'id'),
            }
            
        except Exception as e:
            print(f"Warning: Error parsing video item: {e}")
            return None
    
    def _get_profile_picture(self, user_detail: Dict) -> Optional[str]:
        """Extract profile picture URL from user detail."""
        avatar_data = user_detail.get('avatarLarger') or user_detail.get('avatarMedium') or user_detail.get('avatarThumb')
        return avatar_data if isinstance(avatar_data, str) else None
    
    def _get_thumbnail_url(self, video_obj: Dict) -> Optional[str]:
        """Extract thumbnail URL from video object."""
        cover = video_obj.get('cover') or video_obj.get('dynamicCover') or video_obj.get('originCover')
        return cover if isinstance(cover, str) else None
    
    def _safe_get(self, data: Dict, key: str, default: Any = None) -> Any:
        """
        Safely get a value from a dictionary.
        
        Args:
            data: Dictionary to access
            key: Key to retrieve
            default: Default value if key not found
        
        Returns:
            Value or default
        """
        value = data.get(key, default)
        # Handle empty strings
        if value == '' and default is not None:
            return default
        return value


def main():
    """Main execution function."""
    # Check command line arguments
    if len(sys.argv) < 2:
        print("Usage: python tiktok_scraper.py <username>")
        print("Example: python tiktok_scraper.py cristiano")
        sys.exit(1)
    
    username = sys.argv[1]
    
    print(f"Scraping TikTok profile: @{username}")
    print("-" * 50)
    
    # Create scraper instance
    scraper = TikTokScraper()
    
    try:
        # Scrape the profile
        result = scraper.scrape_profile(username)
        
        # Print results as formatted JSON
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Print summary
        if result.get('user'):
            print("\n" + "=" * 50)
            print("SCRAPING SUMMARY")
            print("=" * 50)
            print(f"Username: @{result['user'].get('username')}")
            print(f"Nickname: {result['user'].get('nickname')}")
            print(f"Followers: {result['user'].get('followers_count'):,}")
            print(f"Videos scraped: {len(result.get('videos', []))}")
        else:
            print("\n" + "=" * 50)
            print("SCRAPING FAILED")
            print("=" * 50)
            if 'error' in result:
                print(f"Error: {result['error']}")
    
    except Exception as e:
        print(f"\nERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()