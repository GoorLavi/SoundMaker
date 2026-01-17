#!/usr/bin/env python3
"""
SoundMaker - Internet Radio Player with AirPlay Support
Main entry point for the application
"""

import signal
import sys
import time
import logging

from config import parse_arguments, get_config_from_args, DEFAULT_STREAM_URL, RESTART_DELAY
from logger_setup import setup_logging
from utils import test_stream_accessibility
from stream_player import StreamPlayer
from audio_controller import AudioController, AudioState
from airplay_manager import AirPlayManager
import state_service

# Global references for signal handling
audio_controller = None
airplay_manager = None
logger = None


def process_command(controller):
    """
    Check for and process commands from command file
    
    Args:
        controller: AudioController instance
        
    Returns:
        bool: True if a command was processed
    """
    command = state_service.read_command()
    if not command:
        return False
    
    action = command.get('action', '').lower()
    log = logging.getLogger('soundmaker')
    
    # Ignore commands during AirPlay
    if not controller.is_controllable():
        log.debug(f"Ignoring command '{action}' - AirPlay active")
        return True
    
    if action == 'set_volume':
        value = command.get('value', 100)
        controller.set_volume(value)
        state_service.write_state_from_controller(controller)
        
    elif action == 'play':
        if controller.get_state() != AudioState.STREAMING:
            controller.start_streaming()
            state_service.write_state_from_controller(controller)
            
    elif action == 'stop':
        controller.stop_streaming()
        state_service.write_state_from_controller(controller)
    
    return True


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    # Get logger if available
    log = logging.getLogger('soundmaker')
    log.info(f"Received shutdown signal ({sig}), shutting down...")
    
    # Write 'idle' state before shutdown
    state_service.write_state(mode="idle", volume=0, playback="stopped")
    
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
    audio_controller = AudioController(
        config['stream_url'],
        config['volume'],
        audio_format=config.get('audio_format'),
        audio_samplerate=config.get('audio_samplerate'),
    )
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
    state_service.write_state_from_controller(audio_controller)
    
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
                    state_service.write_state_from_controller(audio_controller)
                elif event == 'disconnect':
                    logger.info("AirPlay device disconnected - switching to streaming mode")
                    audio_controller.switch_to_streaming()
                    state_service.write_state_from_controller(audio_controller)
            
            # Check for commands from Homebridge/external control
            process_command(audio_controller)
            
            # Monitor streaming state
            current_state = audio_controller.get_state()
            
            # Write state file if state changed
            if current_state != last_state:
                state_service.write_state_from_controller(audio_controller)
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
                        state_service.write_state_from_controller(audio_controller)
                        if audio_controller.start_streaming():
                            # Reset restart count only on successful start
                            audio_controller.stream_player.reset_restart_count()
                            state_service.write_state_from_controller(audio_controller)
                            logger.info("Streaming restarted successfully")
                        else:
                            logger.error("Failed to restart streaming")
                            state_service.write_state_from_controller(audio_controller)
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
                    state_service.write_state_from_controller(audio_controller)
                    time.sleep(1)
                else:
                    state_service.write_state_from_controller(audio_controller)
                    time.sleep(0.5)
                
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
        signal_handler(signal.SIGTERM, None)


if __name__ == "__main__":
    main()
