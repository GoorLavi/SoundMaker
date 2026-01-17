"""
State Service for SoundMaker
Centralized module for reading/writing state and command files
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger('soundmaker.state_service')

# File paths
STATE_FILE = Path("/tmp/soundmaker_state")
COMMAND_FILE = Path("/tmp/soundmaker_commands")

# Valid states
VALID_MODES = ('streaming', 'airplay', 'idle', 'transitioning')
VALID_PLAYBACK = ('playing', 'stopped')
VALID_ACTIONS = ('set_volume', 'play', 'stop')


def read_state():
    """
    Read current state from JSON file
    
    Returns:
        dict: {"mode": str, "volume": int, "playback": str} or None if unavailable
    """
    try:
        if not STATE_FILE.exists():
            return None
        
        with open(STATE_FILE, 'r') as f:
            content = f.read().strip()
        
        if not content:
            return None
        
        state = json.loads(content)
        
        # Validate structure
        if not isinstance(state, dict):
            logger.warning(f"State file contains invalid data type: {type(state)}")
            return None
        
        return state
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse state file JSON: {e}")
        return None
    except IOError as e:
        logger.warning(f"Failed to read state file: {e}")
        return None


def get_mode():
    """
    Get current mode from state file
    
    Returns:
        str: 'streaming', 'airplay', 'idle', 'transitioning', or None
    """
    state = read_state()
    if state is None:
        return None
    
    mode = state.get('mode', '').lower()
    if mode in VALID_MODES:
        return mode
    
    logger.warning(f"Invalid mode in state file: {mode}")
    return None


def get_volume():
    """
    Get current volume from state file
    
    Returns:
        int: Volume level 0-100, or None if unavailable
    """
    state = read_state()
    if state is None:
        return None
    
    volume = state.get('volume')
    if isinstance(volume, int) and 0 <= volume <= 100:
        return volume
    
    return None


def get_playback():
    """
    Get current playback status from state file
    
    Returns:
        str: 'playing' or 'stopped', or None if unavailable
    """
    state = read_state()
    if state is None:
        return None
    
    playback = state.get('playback', '').lower()
    if playback in VALID_PLAYBACK:
        return playback
    
    return None


def write_state(mode, volume, playback):
    """
    Write state to JSON file atomically
    
    Args:
        mode: 'streaming', 'airplay', 'idle', 'transitioning'
        volume: 0-100
        playback: 'playing' or 'stopped'
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        state_dict = {
            "mode": str(mode).lower(),
            "volume": int(volume),
            "playback": str(playback).lower()
        }
        
        # Ensure directory exists
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Atomic write: write to temp file, then rename
        temp_file = STATE_FILE.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            json.dump(state_dict, f)
            f.write('\n')
        
        temp_file.replace(STATE_FILE)
        return True
        
    except (IOError, ValueError) as e:
        logger.warning(f"Failed to write state file: {e}")
        return False


def write_state_from_controller(controller):
    """
    Write state from an AudioController instance
    
    Args:
        controller: AudioController instance with get_full_state() method
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        state = controller.get_full_state()
        return write_state(
            mode=state['mode'],
            volume=state['volume'],
            playback=state['playback']
        )
    except Exception as e:
        logger.warning(f"Failed to write state from controller: {e}")
        return False


def read_command():
    """
    Read next command from command file (consumes it)
    
    Returns:
        dict: {"action": str, ...} or None if no command
    """
    try:
        if not COMMAND_FILE.exists():
            return None
        
        with open(COMMAND_FILE, 'r') as f:
            content = f.read().strip()
        
        if not content:
            return None
        
        # Clear the file after reading (consume the command)
        COMMAND_FILE.write_text('')
        
        command = json.loads(content)
        
        # Validate command structure
        if not isinstance(command, dict):
            logger.warning(f"Command file contains invalid data type: {type(command)}")
            return None
        
        action = command.get('action', '').lower()
        if action not in VALID_ACTIONS:
            logger.warning(f"Invalid action in command file: {action}")
            return None
        
        return command
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse command file JSON: {e}")
        # Clear invalid command
        try:
            COMMAND_FILE.write_text('')
        except IOError:
            pass
        return None
    except IOError as e:
        logger.warning(f"Failed to read command file: {e}")
        return None


def write_command(action, **kwargs):
    """
    Write command to command file
    
    Args:
        action: 'set_volume', 'play', 'stop'
        **kwargs: Additional parameters (e.g., value=70 for set_volume)
        
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if action not in VALID_ACTIONS:
            logger.warning(f"Invalid action: {action}")
            return False
        
        command = {"action": action, **kwargs}
        
        # Ensure directory exists
        COMMAND_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(COMMAND_FILE, 'w') as f:
            json.dump(command, f)
            f.write('\n')
        
        return True
        
    except IOError as e:
        logger.warning(f"Failed to write command file: {e}")
        return False


def clear_command():
    """
    Clear any pending command
    
    Returns:
        bool: True if successful, False otherwise
    """
    try:
        if COMMAND_FILE.exists():
            COMMAND_FILE.write_text('')
        return True
    except IOError as e:
        logger.warning(f"Failed to clear command file: {e}")
        return False
