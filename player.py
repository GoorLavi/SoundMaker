#!/usr/bin/env python3
"""
SoundMaker - Internet Radio Player with AirPlay Support
Main entry point for the application
"""

import signal
import sys
import time
import logging
from pathlib import Path

from config import parse_arguments, get_config_from_args, DEFAULT_STREAM_URL, RESTART_DELAY
from logger_setup import setup_logging
from utils import test_stream_accessibility
from stream_player import StreamPlayer
from audio_controller import AudioController, AudioState
from airplay_manager import AirPlayManager

# Global references for signal handling
audio_controller = None
airplay_manager = None
logger = None

# State file for LED controller
STATE_FILE = Path("/tmp/soundmaker_state")


def write_state_file(state):
    """
    Write audio state to file for LED controller
    
    Args:
        state: AudioState enum value or string ('streaming', 'airplay', 'idle')
    """
    try:
        # Convert AudioState enum to string if needed
        if isinstance(state, AudioState):
            state_str = state.value
        else:
            state_str = str(state).lower()
        
        # Ensure directory exists (it should, but be safe)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        # Atomic write: write to temp file, then rename
        temp_file = STATE_FILE.with_suffix('.tmp')
        with open(temp_file, 'w') as f:
            f.write(state_str + '\n')
        temp_file.replace(STATE_FILE)
        
    except Exception as e:
        # Log warning but don't crash the main service
        log = logging.getLogger('soundmaker')
        log.warning(f"Failed to write state file: {e}")


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    # Get logger if available
    log = logging.getLogger('soundmaker')
    log.info(f"Received shutdown signal ({sig}), shutting down...")
    
    # Write 'idle' state before shutdown
    write_state_file('idle')
    
    if audio_controller:
        audio_controller.shutdown()
    
    if airplay_manager:
        airplay_manager.cleanup()
    
    log.info("SoundMaker stopped")
    sys.exit(0)


def main():
    """Main application entry point"""
    global audio_controller, airplay_manager, logger
    
    # Parse command-line arguments
    args = parse_arguments()
    config = get_config_from_args(args)
    
    # Setup logging
    logger = setup_logging(verbose=config.get('verbose', False))
    logger.info("=" * 60)
    logger.info("SoundMaker - Internet Radio Player")
    logger.info("=" * 60)
    
    # Test mode: just test stream and exit
    if config.get('test_mode', False):
        logger.info("Stream Test Mode")
        logger.info("=" * 60)
        
        # Test mpv availability
        test_player = StreamPlayer(config['stream_url'], config['volume'])
        if not test_player.is_mpv_available():
            logger.error("mpv not found. Please install it: sudo apt-get install mpv")
            sys.exit(1)
        
        # Test stream accessibility
        if test_stream_accessibility(config['stream_url']):
            logger.info("=" * 60)
            logger.info("✓ All tests passed!")
            sys.exit(0)
        else:
            logger.error("=" * 60)
            logger.error("✗ Stream test failed!")
            sys.exit(1)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Initialize components
    logger.info("Initializing components...")
    audio_controller = AudioController(config['stream_url'], config['volume'])
    airplay_manager = AirPlayManager()
    
    # Setup AirPlay IPC
    if not airplay_manager.setup_ipc():
        logger.error("Failed to setup AirPlay IPC. Continuing without AirPlay support...")
        airplay_manager = None
    else:
        if not airplay_manager.open_pipe():
            logger.warning("Failed to open AirPlay IPC pipe. AirPlay detection may not work.")
        else:
            # Check shairport-sync
            if airplay_manager.is_shairport_installed():
                if airplay_manager.is_shairport_running():
                    logger.info("shairport-sync is running")
                else:
                    logger.warning("shairport-sync is installed but not running")
            else:
                logger.info("shairport-sync not installed - AirPlay support disabled")
                logger.info("Install with: sudo apt-get install shairport-sync")
    
    # Log startup information
    logger.info("=" * 60)
    logger.info("Starting SoundMaker...")
    logger.info(f"Stream URL: {config['stream_url']}")
    logger.info(f"Volume: {config['volume']}%")
    logger.info(f"AirPlay: {'Enabled' if airplay_manager else 'Disabled'}")
    logger.info("=" * 60)
    
    # Start streaming
    if not audio_controller.start_streaming():
        logger.error("Failed to start streaming. Exiting.")
        sys.exit(1)
    
    # Write initial state
    write_state_file(audio_controller.get_state())
    
    # Main loop
    logger.info("Entering main loop...")
    last_state = None
    try:
        while True:
            # Check for AirPlay events (non-blocking)
            if airplay_manager:
                event = airplay_manager.check_event(timeout=0.5)
                if event == 'connect':
                    logger.info("AirPlay device connected - switching to AirPlay mode")
                    audio_controller.switch_to_airplay()
                    write_state_file(audio_controller.get_state())
                elif event == 'disconnect':
                    logger.info("AirPlay device disconnected - switching to streaming mode")
                    audio_controller.switch_to_streaming()
                    write_state_file(audio_controller.get_state())
            
            # Monitor streaming state
            current_state = audio_controller.get_state()
            
            # Write state file if state changed
            if current_state != last_state:
                write_state_file(current_state)
                last_state = current_state
            
            if current_state == AudioState.STREAMING:
                # Check if stream player is still running
                if not audio_controller.stream_player.is_playing():
                    # Process exited, handle it
                    return_code = audio_controller.stream_player.wait()
                    should_restart = audio_controller.handle_stream_exit(return_code)
                    
                    if should_restart:
                        logger.info(f"Restarting streaming in {RESTART_DELAY} seconds... (attempt {audio_controller.stream_player.restart_count})")
                        time.sleep(RESTART_DELAY)
                        # Update state to IDLE so start_streaming will actually start
                        audio_controller.state = AudioState.IDLE
                        write_state_file(audio_controller.get_state())
                        if audio_controller.start_streaming():
                            # Reset restart count only on successful start
                            audio_controller.stream_player.reset_restart_count()
                            write_state_file(audio_controller.get_state())
                            logger.info("Streaming restarted successfully")
                        else:
                            logger.error("Failed to restart streaming")
                            write_state_file(audio_controller.get_state())
                            time.sleep(RESTART_DELAY)
                    else:
                        logger.info("Streaming stopped, exiting main loop")
                        break
                else:
                    # Stream is playing, sleep briefly
                    time.sleep(0.5)
            elif current_state == AudioState.AIRPLAY:
                # In AirPlay mode, just wait and check for events
                time.sleep(0.5)
            else:
                # IDLE state, try to start streaming
                logger.info("In IDLE state, starting streaming...")
                if not audio_controller.start_streaming():
                    logger.warning("Failed to start streaming from IDLE state")
                    write_state_file(audio_controller.get_state())
                    time.sleep(1)
                else:
                    write_state_file(audio_controller.get_state())
                    time.sleep(0.5)
                
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
        signal_handler(signal.SIGTERM, None)


if __name__ == "__main__":
    main()
