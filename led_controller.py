#!/usr/bin/env python3
"""
LED Status Controller for SoundMaker
Controls GPIO LEDs to indicate current audio mode (Stream or AirPlay)
"""

import signal
import sys
import time
import logging
from pathlib import Path

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    # Create a mock GPIO for non-Pi environments (testing)
    class MockGPIO:
        BCM = 'BCM'
        OUT = 'OUT'
        LOW = 0
        HIGH = 1
        
        @staticmethod
        def setmode(mode):
            pass
        
        @staticmethod
        def setup(pin, mode):
            pass
        
        @staticmethod
        def output(pin, state):
            pass
        
        @staticmethod
        def cleanup():
            pass
    GPIO = MockGPIO()

# GPIO Pin Configuration (BCM numbering)
STREAM_LED_PIN = 17  # Physical Pin 11
AIRPLAY_LED_PIN = 27  # Physical Pin 13

# State file path
STATE_FILE = Path("/tmp/soundmaker_state")

# Polling interval (seconds)
POLL_INTERVAL = 0.5

logger = logging.getLogger('soundmaker.led_controller')


class LEDController:
    """Controls status LEDs based on audio state"""
    
    def __init__(self):
        """Initialize GPIO pins and set LEDs to OFF"""
        if not GPIO_AVAILABLE:
            logger.warning("RPi.GPIO not available - running in mock mode")
            logger.warning("LEDs will not actually control hardware")
        
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(STREAM_LED_PIN, GPIO.OUT)
            GPIO.setup(AIRPLAY_LED_PIN, GPIO.OUT)
            
            # Initialize both LEDs to OFF
            GPIO.output(STREAM_LED_PIN, GPIO.LOW)
            GPIO.output(AIRPLAY_LED_PIN, GPIO.LOW)
            
            logger.info("GPIO initialized - LEDs set to OFF")
            logger.info(f"Stream LED: GPIO {STREAM_LED_PIN} (Physical Pin 11)")
            logger.info(f"AirPlay LED: GPIO {AIRPLAY_LED_PIN} (Physical Pin 13)")
        except Exception as e:
            logger.error(f"Failed to initialize GPIO: {e}")
            raise
    
    def read_state(self):
        """
        Read current audio state from state file
        
        Returns:
            str: 'streaming', 'airplay', 'idle', or None if file doesn't exist/read fails
        """
        try:
            if not STATE_FILE.exists():
                return None
            
            with open(STATE_FILE, 'r') as f:
                state = f.read().strip().lower()
            
            # Validate state
            if state in ('streaming', 'airplay', 'idle'):
                return state
            else:
                logger.warning(f"Invalid state in file: {state}")
                return None
        except Exception as e:
            logger.warning(f"Failed to read state file: {e}")
            return None
    
    def update_leds(self, state):
        """
        Update LEDs based on audio state with priority rules
        
        Priority: AirPlay > Stream > Idle
        
        Args:
            state: 'streaming', 'airplay', 'idle', or None
        """
        try:
            if state == 'airplay':
                # AirPlay active: AirPlay LED ON, Stream LED OFF
                GPIO.output(AIRPLAY_LED_PIN, GPIO.HIGH)
                GPIO.output(STREAM_LED_PIN, GPIO.LOW)
                logger.debug("LEDs: AirPlay ON, Stream OFF")
            elif state == 'streaming':
                # Streaming active: Stream LED ON, AirPlay LED OFF
                GPIO.output(STREAM_LED_PIN, GPIO.HIGH)
                GPIO.output(AIRPLAY_LED_PIN, GPIO.LOW)
                logger.debug("LEDs: Stream ON, AirPlay OFF")
            else:
                # Idle or None: Both LEDs OFF
                GPIO.output(STREAM_LED_PIN, GPIO.LOW)
                GPIO.output(AIRPLAY_LED_PIN, GPIO.LOW)
                logger.debug("LEDs: Both OFF")
        except Exception as e:
            logger.error(f"Failed to update LEDs: {e}")
            # Don't raise - allow service to continue and retry
    
    def run(self):
        """Main loop: poll state file and update LEDs"""
        logger.info("Starting LED controller main loop...")
        logger.info(f"Polling state file: {STATE_FILE}")
        logger.info(f"Poll interval: {POLL_INTERVAL} seconds")
        
        last_state = None
        
        try:
            while True:
                # Read current state
                current_state = self.read_state()
                
                # Update LEDs if state changed
                if current_state != last_state:
                    if current_state is None:
                        logger.debug("State file not found or invalid - treating as idle")
                    else:
                        logger.info(f"State changed: {last_state} -> {current_state}")
                    
                    self.update_leds(current_state)
                    last_state = current_state
                
                # Sleep before next poll
                time.sleep(POLL_INTERVAL)
        
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        except Exception as e:
            logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
            raise
        finally:
            self.cleanup()
    
    def cleanup(self):
        """Turn off all LEDs and cleanup GPIO"""
        logger.info("Cleaning up GPIO...")
        try:
            GPIO.output(STREAM_LED_PIN, GPIO.LOW)
            GPIO.output(AIRPLAY_LED_PIN, GPIO.LOW)
            GPIO.cleanup()
            logger.info("GPIO cleaned up - all LEDs OFF")
        except Exception as e:
            logger.error(f"Error during GPIO cleanup: {e}")


# Global reference for signal handler
led_controller = None


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully"""
    logger.info(f"Received shutdown signal ({sig}), shutting down...")
    if led_controller:
        led_controller.cleanup()
    logger.info("LED controller stopped")
    sys.exit(0)


def setup_logging():
    """Setup logging for LED controller"""
    logger = logging.getLogger('soundmaker.led_controller')
    logger.setLevel(logging.INFO)
    
    # Clear existing handlers
    logger.handlers.clear()
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger


def main():
    """Main entry point"""
    global led_controller
    
    # Setup logging
    setup_logging()
    
    logger.info("=" * 60)
    logger.info("SoundMaker LED Status Controller")
    logger.info("=" * 60)
    
    # Check GPIO availability
    if not GPIO_AVAILABLE:
        logger.error("RPi.GPIO library not available")
        logger.error("This script requires RPi.GPIO to control LEDs")
        logger.error("Install with: sudo apt-get install python3-rpi.gpio")
        sys.exit(1)
    
    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Initialize LED controller
        led_controller = LEDController()
        
        # Run main loop
        led_controller.run()
    
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

