"""
Stream Player module for SoundMaker
Handles internet stream playback using mpv
"""

import subprocess
import time
import threading
import queue
import logging
import os

logger = logging.getLogger('soundmaker.stream_player')


class StreamPlayer:
    """Manages internet stream playback using mpv"""
    
    def __init__(self, stream_url, volume=100):
        """
        Initialize StreamPlayer
        
        Args:
            stream_url: URL of the stream to play
            volume: Volume level (0-100)
        """
        self.stream_url = stream_url
        self.volume = volume
        self.process = None
        self.restart_count = 0
        self.max_restart_attempts = 10
        self.restart_delay = 3
        self._is_playing = False
    
    def is_mpv_available(self):
        """Check if mpv is installed and available"""
        try:
            result = subprocess.run(
                ["mpv", "--version"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.decode().split('\n')[0]
                logger.info(f"mpv found: {version}")
                return True
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def start(self):
        """
        Start playing the stream
        
        Returns:
            bool: True if started successfully, False otherwise
        """
        # Check mpv availability
        if not self.is_mpv_available():
            logger.error("mpv not found. Please install it: sudo apt-get install mpv")
            return False
        
        # mpv command: audio-only, no video
        cmd = [
            "mpv",
            "--no-video",
            "--really-quiet",  # Minimal output
            "--audio-device=pulse",  # Use default PulseAudio connection
            "--cache=yes",  # Enable caching for better streaming
            f"--volume={self.volume}",
            self.stream_url
        ]
        
        logger.info(f"Starting stream: {self.stream_url}")
        logger.debug(f"Command: {' '.join(cmd)}")
        logger.info(f"Restart attempt: {self.restart_count + 1}")
        
        try:
            # Set up environment for PulseAudio access
            env = os.environ.copy()
            env['XDG_RUNTIME_DIR'] = '/run/user/1000'
            # Don't set PULSE_SERVER - let PulseAudio auto-detect
            
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env
            )
            
            # Log process start
            logger.info(f"mpv process started (PID: {self.process.pid})")
            
            # Give it a moment to start and check if it's still alive
            time.sleep(1)
            if self.process.poll() is not None:
                # Process exited immediately
                stderr_output = self.process.stderr.read() if self.process.stderr else "No error output"
                logger.error(f"mpv exited immediately. Error: {stderr_output}")
                self.process = None
                return False
            
            self._is_playing = True
            return True
            
        except FileNotFoundError:
            logger.error("mpv executable not found. Please install: sudo apt-get install mpv")
            return False
        except PermissionError:
            logger.error("Permission denied when trying to execute mpv")
            return False
        except Exception as e:
            logger.error(f"Failed to start mpv: {e}", exc_info=True)
            self.process = None
            return False
    
    def stop(self):
        """Stop playing the stream"""
        if self.process:
            logger.info("Stopping stream player...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
                logger.info("Stream player stopped successfully")
            except subprocess.TimeoutExpired:
                logger.warning("Process didn't terminate gracefully, forcing kill...")
                self.process.kill()
                self.process.wait()
                logger.info("Stream player killed")
            finally:
                self.process = None
                self._is_playing = False
    
    def is_playing(self):
        """Check if stream is currently playing"""
        if self.process is None:
            return False
        if self.process.poll() is not None:
            # Process has exited
            self._is_playing = False
            return False
        return self._is_playing
    
    def wait(self):
        """
        Wait for the process to complete and return exit code
        
        Returns:
            int: Process exit code
        """
        if not self.process:
            return -1
        
        return_code = self._monitor_process()
        self._is_playing = False
        return return_code
    
    def _monitor_process(self):
        """Monitor mpv process and capture output"""
        stderr_queue = queue.Queue()
        
        def read_stderr():
            """Read mpv stderr output in background"""
            try:
                if self.process and self.process.stderr:
                    for line in self.process.stderr:
                        if line.strip():
                            stderr_queue.put(line.strip())
            except Exception as e:
                logger.debug(f"Error reading stderr: {e}")
        
        # Start background thread to read stderr
        stderr_thread = threading.Thread(target=read_stderr, daemon=True)
        stderr_thread.start()
        
        # Wait for process to complete
        return_code = self.process.wait()
        
        # Log any captured stderr messages
        try:
            while not stderr_queue.empty():
                line = stderr_queue.get_nowait()
                logger.debug(f"mpv: {line}")
        except:
            pass
        
        return return_code
    
    def reset_restart_count(self):
        """Reset the restart counter"""
        self.restart_count = 0
    
    def increment_restart_count(self):
        """Increment restart counter and return if max reached"""
        self.restart_count += 1
        return self.restart_count >= self.max_restart_attempts

