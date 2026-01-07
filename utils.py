"""
Utility functions for SoundMaker
"""

import urllib.request
import urllib.error
import logging

logger = logging.getLogger('soundmaker.utils')


def test_stream_accessibility(url):
    """
    Test if the stream URL is accessible
    
    Args:
        url: Stream URL to test
        
    Returns:
        bool: True if accessible, False otherwise
    """
    logger.info(f"Testing stream accessibility: {url}")
    
    try:
        # Try to open the URL with a short timeout
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'Mozilla/5.0 (compatible; SoundMaker/1.0)')
        
        with urllib.request.urlopen(req, timeout=10) as response:
            status_code = response.getcode()
            content_type = response.headers.get('Content-Type', 'unknown')
            
            logger.info(f"✓ Stream is accessible")
            logger.info(f"  Status code: {status_code}")
            logger.info(f"  Content-Type: {content_type}")
            
            # Try to read a small chunk to verify it's actually streaming
            try:
                chunk = response.read(1024)
                if chunk:
                    logger.info(f"  ✓ Stream data received ({len(chunk)} bytes)")
                    return True
                else:
                    logger.warning("  ⚠ Stream returned empty data")
                    return False
            except Exception as e:
                logger.warning(f"  ⚠ Could not read stream data: {e}")
                return False
                
    except urllib.error.HTTPError as e:
        logger.error(f"✗ HTTP Error: {e.code} - {e.reason}")
        return False
    except urllib.error.URLError as e:
        logger.error(f"✗ URL Error: {e.reason}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error: {e}")
        return False

