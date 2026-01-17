#!/usr/bin/env python3
"""
Homebridge Bridge for SoundMaker
HTTP server that exposes state/control endpoints for Homebridge plugins
"""

import json
import logging
import signal
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

import state_service

# Configuration
HOST = '127.0.0.1'
PORT = 8080

logger = logging.getLogger('soundmaker.homebridge_bridge')


class BridgeHandler(BaseHTTPRequestHandler):
    """HTTP request handler for Homebridge integration"""
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.debug(f"{self.address_string()} - {format % args}")
    
    def send_json(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def send_error_json(self, message, status=400):
        """Send JSON error response"""
        self.send_json({"error": message}, status)
    
    def do_GET(self):
        """Handle GET requests"""
        path = urlparse(self.path).path
        
        if path == '/state':
            # Return full state
            state = state_service.read_state()
            if state:
                state['controllable'] = state.get('mode') != 'airplay'
                self.send_json(state)
            else:
                self.send_json({"mode": "idle", "volume": 0, "playback": "stopped", "controllable": True})
        
        elif path == '/volume':
            # Return just volume
            volume = state_service.get_volume()
            self.send_json({"volume": volume if volume is not None else 0})
        
        elif path == '/playback':
            # Return playback status with controllable flag
            state = state_service.read_state()
            if state:
                self.send_json({
                    "playback": state.get('playback', 'stopped'),
                    "controllable": state.get('mode') != 'airplay'
                })
            else:
                self.send_json({"playback": "stopped", "controllable": True})
        
        elif path == '/health':
            # Health check endpoint
            self.send_json({"status": "ok"})
        
        else:
            self.send_error_json("Not found", 404)
    
    def do_POST(self):
        """Handle POST requests"""
        path = urlparse(self.path).path
        
        # Read body
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            self.send_error_json("Invalid JSON")
            return
        
        # Check if controllable
        state = state_service.read_state()
        if state and state.get('mode') == 'airplay':
            self.send_error_json("Cannot control during AirPlay", 403)
            return
        
        if path == '/volume':
            # Set volume
            volume = data.get('volume')
            if volume is None:
                self.send_error_json("Missing 'volume' field")
                return
            try:
                volume = int(volume)
                if not 0 <= volume <= 100:
                    raise ValueError()
            except (ValueError, TypeError):
                self.send_error_json("Volume must be 0-100")
                return
            
            state_service.write_command('set_volume', value=volume)
            self.send_json({"success": True, "volume": volume})
        
        elif path == '/playback':
            # Control playback
            action = data.get('action', '').lower()
            if action not in ('play', 'stop'):
                self.send_error_json("Action must be 'play' or 'stop'")
                return
            
            state_service.write_command(action)
            self.send_json({"success": True, "action": action})
        
        else:
            self.send_error_json("Not found", 404)
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()


def setup_logging():
    """Setup logging for bridge"""
    log = logging.getLogger('soundmaker.homebridge_bridge')
    log.setLevel(logging.INFO)
    log.handlers.clear()
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    ))
    log.addHandler(handler)
    return log


def signal_handler(sig, frame):
    """Handle shutdown signals"""
    logger.info(f"Received signal {sig}, shutting down...")
    sys.exit(0)


def main():
    """Main entry point"""
    global logger
    logger = setup_logging()
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    logger.info("=" * 50)
    logger.info("SoundMaker Homebridge Bridge")
    logger.info("=" * 50)
    logger.info(f"Starting HTTP server on {HOST}:{PORT}")
    
    try:
        server = HTTPServer((HOST, PORT), BridgeHandler)
        logger.info("Server started. Endpoints:")
        logger.info("  GET  /state    - Full state")
        logger.info("  GET  /volume   - Current volume")
        logger.info("  POST /volume   - Set volume")
        logger.info("  GET  /playback - Playback status")
        logger.info("  POST /playback - Control playback")
        logger.info("  GET  /health   - Health check")
        server.serve_forever()
    except OSError as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
