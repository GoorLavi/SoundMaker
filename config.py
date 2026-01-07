"""
Configuration management for SoundMaker
Handles default settings, command-line arguments, and configuration validation
"""

import argparse

# Default Stream URL
DEFAULT_STREAM_URL = "https://uk3.internet-radio.com/proxy/1940sradio/stream"

# Default configuration values
DEFAULT_VOLUME = 100
MAX_RESTART_ATTEMPTS = 10
RESTART_DELAY = 3


def parse_arguments():
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='Internet Radio Player for Raspberry Pi',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Use default stream URL
  %(prog)s --url https://example.com/stream   # Use custom stream URL
  %(prog)s --url https://example.com/stream --volume 80  # Set volume to 80%%
  %(prog)s --test                             # Test stream accessibility
        """
    )
    
    parser.add_argument(
        '--url',
        type=str,
        default=DEFAULT_STREAM_URL,
        help=f'Stream URL to play (default: {DEFAULT_STREAM_URL})'
    )
    
    parser.add_argument(
        '--volume',
        type=int,
        default=DEFAULT_VOLUME,
        choices=range(0, 101),
        metavar='0-100',
        help=f'Volume level 0-100 (default: {DEFAULT_VOLUME})'
    )
    
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test stream accessibility and exit'
    )
    
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose/debug logging'
    )
    
    return parser.parse_args()


def get_config_from_args(args):
    """Convert parsed arguments to configuration dictionary"""
    return {
        'stream_url': args.url,
        'volume': args.volume,
        'test_mode': args.test,
        'verbose': args.verbose
    }

