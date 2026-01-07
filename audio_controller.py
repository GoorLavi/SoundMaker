"""
Audio Controller for SoundMaker
Main coordinator that manages switching between streaming and AirPlay
"""

import logging
from enum import Enum

from stream_player import StreamPlayer

logger = logging.getLogger('soundmaker.audio_controller')


class AudioState(Enum):
    """Audio source states"""
    STREAMING = "streaming"
    AIRPLAY = "airplay"
    IDLE = "idle"
    TRANSITIONING = "transitioning"


class AudioController:
    """Main controller for managing audio sources"""
    
    def __init__(self, stream_url, volume=100):
        """
        Initialize AudioController
        
        Args:
            stream_url: URL of the stream to play
            volume: Volume level (0-100)
        """
        self.stream_player = StreamPlayer(stream_url, volume)
        self.state = AudioState.IDLE
        self.stream_url = stream_url
        self.volume = volume
    
    def start_streaming(self):
        """
        Start streaming internet radio
        
        Returns:
            bool: True if started successfully
        """
        if self.state == AudioState.AIRPLAY:
            logger.warning("Cannot start streaming while AirPlay is active")
            return False
        
        # Check if already streaming AND process is actually running
        if self.state == AudioState.STREAMING:
            if self.stream_player.is_playing():
                logger.info("Streaming already active")
                return True
            else:
                # State says streaming but process is dead - need to restart
                logger.warning("Stream state is STREAMING but process is not running, restarting...")
                self.state = AudioState.IDLE
        
        logger.info("Starting streaming mode...")
        self.state = AudioState.TRANSITIONING
        
        if self.stream_player.start():
            self.state = AudioState.STREAMING
            logger.info("Streaming started successfully")
            return True
        else:
            self.state = AudioState.IDLE
            logger.error("Failed to start streaming")
            return False
    
    def stop_streaming(self):
        """Stop streaming internet radio"""
        if self.state == AudioState.STREAMING:
            logger.info("Stopping streaming...")
            self.stream_player.stop()
            self.state = AudioState.IDLE
            logger.info("Streaming stopped")
        elif self.state == AudioState.TRANSITIONING:
            # If transitioning, just update state
            self.state = AudioState.IDLE
    
    def switch_to_airplay(self):
        """
        Switch to AirPlay mode (stop streaming)
        
        Returns:
            bool: True if switched successfully
        """
        if self.state == AudioState.AIRPLAY:
            logger.info("Already in AirPlay mode")
            return True
        
        logger.info("Switching to AirPlay mode...")
        
        # Stop streaming if active
        if self.state == AudioState.STREAMING:
            self.stop_streaming()
        
        self.state = AudioState.AIRPLAY
        logger.info("Switched to AirPlay mode")
        return True
    
    def switch_to_streaming(self):
        """
        Switch back to streaming mode (from AirPlay)
        
        Returns:
            bool: True if switched successfully
        """
        if self.state == AudioState.STREAMING:
            # Check if actually playing
            if self.stream_player.is_playing():
                logger.info("Already in streaming mode")
                return True
            else:
                # State is STREAMING but process is dead
                logger.warning("State is STREAMING but process not running, restarting...")
                self.state = AudioState.IDLE
        
        logger.info("Switching to streaming mode...")
        
        # Update state first
        if self.state == AudioState.AIRPLAY:
            self.state = AudioState.IDLE
        
        # Start streaming - if it fails, log it clearly
        if self.start_streaming():
            logger.info("Successfully switched to streaming mode")
            return True
        else:
            logger.error("Failed to start streaming after AirPlay disconnect")
            # State is already IDLE, main loop will retry
            return False
    
    def get_state(self):
        """Get current audio state"""
        return self.state
    
    def is_streaming(self):
        """Check if currently streaming"""
        return self.state == AudioState.STREAMING and self.stream_player.is_playing()
    
    def handle_stream_exit(self, return_code):
        """
        Handle stream player process exit
        
        Args:
            return_code: Process exit code
            
        Returns:
            bool: True if should restart, False if should stop
        """
        logger.warning(f"Stream player exited with code {return_code}")
        
        # Only handle restart if we're supposed to be streaming
        if self.state != AudioState.STREAMING:
            logger.info("Not in streaming state, not restarting")
            return False
        
        # Interpret exit codes
        if return_code == 0:
            logger.info("Stream player stopped normally")
            return False
        elif return_code == 1:
            logger.error("Stream player error: general error")
        elif return_code == 2:
            logger.error("Stream player error: file/stream error")
        else:
            logger.warning(f"Stream player exited with unexpected code: {return_code}")
        
        # Check restart count
        if self.stream_player.increment_restart_count():
            logger.error("Maximum restart attempts reached")
            return False
        
        logger.info(f"Will restart streaming (attempt {self.stream_player.restart_count})")
        return True
    
    def shutdown(self):
        """Shutdown the audio controller and stop all playback"""
        logger.info("Shutting down audio controller...")
        self.stop_streaming()
        self.state = AudioState.IDLE
        logger.info("Audio controller shut down")

