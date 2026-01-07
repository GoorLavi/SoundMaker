"""
AirPlay Manager for SoundMaker
Handles AirPlay detection via shairport-sync hooks and IPC communication
"""

import os
import select
import logging
import subprocess
from pathlib import Path

logger = logging.getLogger('soundmaker.airplay_manager')

# IPC configuration
IPC_PIPE_PATH = Path("/tmp/soundmaker_airplay_events")
HOOK_SCRIPT_PATH = Path("/opt/soundmaker/airplay_hook.sh")


class AirPlayManager:
    """Manages AirPlay detection and IPC communication"""
    
    def __init__(self, pipe_path=None):
        """
        Initialize AirPlayManager
        
        Args:
            pipe_path: Path to named pipe (default: /tmp/soundmaker_airplay_events)
        """
        self.pipe_path = Path(pipe_path) if pipe_path else IPC_PIPE_PATH
        self.pipe_fd = None
        self._is_connected = False
    
    def setup_ipc(self):
        """
        Set up the named pipe for IPC communication
        
        This method handles the pipe lifecycle gracefully:
        - If pipe exists and is readable, use it (don't delete/recreate)
        - If pipe exists but is broken, try to remove and recreate
        - If pipe doesn't exist, create it
        - Handles ownership issues (pipe may be owned by root after ExecStartPost)
        
        Returns:
            bool: True if setup successful
        """
        try:
            # Check if pipe already exists
            if self.pipe_path.exists():
                # Verify the existing pipe is usable
                try:
                    # Try to open it in non-blocking read mode to verify it's a valid FIFO
                    test_fd = os.open(str(self.pipe_path), os.O_RDONLY | os.O_NONBLOCK)
                    os.close(test_fd)
                    # Pipe exists and is readable - use it
                    logger.info(f"Using existing IPC pipe: {self.pipe_path}")
                    return True
                except OSError as e:
                    # Pipe exists but test open failed - might be broken or permission issue
                    logger.warning(f"Existing pipe test open failed: {e}")
                    # Try to remove it, but don't fail if we can't (might be owned by root)
                    try:
                        self.pipe_path.unlink()
                        logger.info("Removed existing pipe, will create new one")
                        # Continue to create new pipe below
                    except OSError as unlink_error:
                        # Can't remove (probably owned by root) - this is expected after ExecStartPost
                        # The pipe should still be usable with 666 permissions even if owned by root
                        logger.info(f"Could not remove existing pipe (owned by root): {unlink_error}")
                        logger.info("Pipe may be usable with current permissions - will attempt to use it")
                        # Return True - open_pipe() will handle any actual errors when trying to use it
                        return True
            
            # Pipe doesn't exist, create it
            # Save current umask
            old_umask = os.umask(0)
            
            try:
                # Create named pipe with permissions that allow shairport-sync to write
                # 0o666 = rw-rw-rw- (read/write for owner, group, and others)
                os.mkfifo(str(self.pipe_path), 0o666)
                
                # Explicitly set permissions (umask might have modified them)
                os.chmod(str(self.pipe_path), 0o666)
                
                logger.info(f"Created IPC pipe: {self.pipe_path} with permissions 666")
                
                # Try to change ownership to root so shairport-sync can write
                # This will fail silently if we don't have permissions, but systemd ExecStartPost will fix it
                try:
                    subprocess.run(
                        ['chown', 'root:root', str(self.pipe_path)],
                        check=False,
                        timeout=1,
                        capture_output=True
                    )
                    logger.debug("Attempted to change pipe ownership to root")
                except Exception:
                    # Silently fail - systemd ExecStartPost will handle it
                    pass
            finally:
                # Restore original umask
                os.umask(old_umask)
            
            return True
        except OSError as e:
            logger.error(f"Failed to setup IPC pipe: {e}")
            return False
    
    def open_pipe(self):
        """
        Open the named pipe for reading (non-blocking)
        
        Returns:
            bool: True if opened successfully
        """
        try:
            # Check if pipe exists
            if not self.pipe_path.exists():
                logger.warning(f"IPC pipe does not exist: {self.pipe_path}")
                return False
            
            # Open pipe in non-blocking mode
            self.pipe_fd = os.open(str(self.pipe_path), os.O_RDONLY | os.O_NONBLOCK)
            logger.info("Opened IPC pipe for reading")
            return True
        except OSError as e:
            logger.error(f"Failed to open IPC pipe: {e}")
            return False
    
    def close_pipe(self):
        """Close the IPC pipe"""
        if self.pipe_fd is not None:
            try:
                os.close(self.pipe_fd)
                self.pipe_fd = None
                logger.debug("Closed IPC pipe")
            except Exception as e:
                logger.warning(f"Error closing pipe: {e}")
    
    def cleanup(self):
        """
        Clean up IPC resources
        
        Note: We don't remove the pipe on cleanup because:
        1. It may be owned by root (after ExecStartPost fixes it)
        2. It should persist across service restarts
        3. shairport-sync may still need to write to it during shutdown
        We only close our file descriptor.
        """
        self.close_pipe()
        # Don't remove the pipe - it should persist and may be owned by root
        # The pipe will be reused on next service start
        logger.debug("Cleaned up IPC resources (pipe left in place for reuse)")
    
    def check_event(self, timeout=0.5):
        """
        Check for AirPlay events from the pipe (non-blocking)
        
        Args:
            timeout: Timeout in seconds (0 = non-blocking)
            
        Returns:
            str or None: Event type ('connect' or 'disconnect') or None if no event
        """
        if self.pipe_fd is None:
            # Try to reopen if closed
            if not self.open_pipe():
                return None
        
        try:
            # Use select to check if data is available
            ready, _, _ = select.select([self.pipe_fd], [], [], timeout)
            if ready:
                # Read event from pipe
                try:
                    data = os.read(self.pipe_fd, 64).decode('utf-8').strip()
                    if data:
                        event = data.lower()
                        if event in ('connect', 'disconnect'):
                            logger.info(f"AirPlay event received: {event}")
                            return event
                        else:
                            logger.warning(f"Unknown event received: {data}")
                except UnicodeDecodeError:
                    logger.warning("Failed to decode pipe data")
                except Exception as e:
                    logger.warning(f"Error reading pipe data: {e}")
        except OSError as e:
            # Pipe might have been closed or doesn't exist
            logger.debug(f"Error reading from pipe: {e}")
            # Try to reopen
            self.close_pipe()
            if self.pipe_path.exists():
                self.open_pipe()
        except Exception as e:
            logger.warning(f"Unexpected error reading pipe: {e}")
        
        return None
    
    def is_shairport_installed(self):
        """Check if shairport-sync is installed"""
        try:
            result = subprocess.run(
                ["shairport-sync", "-V"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.decode().strip()
                logger.info(f"shairport-sync found: {version}")
                return True
            return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def is_shairport_running(self):
        """Check if shairport-sync service is running"""
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "--quiet", "shairport-sync"],
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False
    
    def ensure_hook_script_exists(self):
        """
        Ensure the hook script exists and is executable
        
        Returns:
            bool: True if script exists and is executable
        """
        if not HOOK_SCRIPT_PATH.exists():
            logger.warning(f"Hook script not found: {HOOK_SCRIPT_PATH}")
            return False
        
        # Check if executable
        if not os.access(HOOK_SCRIPT_PATH, os.X_OK):
            logger.warning(f"Hook script is not executable: {HOOK_SCRIPT_PATH}")
            return False
        
        return True

