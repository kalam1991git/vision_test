#!/usr/bin/env python3
import pygame
import math
import time
import os
import socket
import threading
from pygame.locals import *
import RPi.GPIO as GPIO
import bluetooth
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
import atexit
import traceback

# ======================
# CONSTANTS & CONFIG
# ======================
# Color Constants
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (128, 128, 128)

# Configuration
CONFIG_FILE = os.path.expanduser('~/vision_config.json')
DEFAULT_CONFIG = {
    'screen_width': 800,
    'screen_height': 480,
    'viewing_distance_cm': 300,
    'current_test': 'snellen',
    'brightness': 100,
    'contrast': 50,
    'language': 'english',
    'orientation': 'landscape',
    'remote_control': 'web',
    'ir_pin': 23,
    'bluetooth_port': 1
}

# Test Constants
SNELLEN_LINES = [("E", 200), ("FP", 100), ("TOZ", 70), ("LPED", 50), ("PECFD", 40), ("EDFCZP", 30), ("FELOPZD", 20)]
LOGMAR_LINES = [("E", 1.0), ("P", 0.8), ("T", 0.63), ("O", 0.5), ("Z", 0.4), ("L", 0.32), ("E", 0.25)]
TUMBLING_E_ORIENTATIONS = ['up', 'right', 'down', 'left']
C_CHART_ORIENTATIONS = ['up', 'right', 'down', 'left']

# ======================
# GLOBAL STATE
# ======================
class AppState:
    def __init__(self):
        self.running = True
        self.current_test = 'snellen'
        self.viewing_distance_cm = 300 * 10  # in mm
        self.brightness = 100
        self.contrast = 50
        self.language = 'english'
        self.screen = None
        self.screen_width = 800
        self.screen_height = 480
        self.main_font = None
        self.small_font = None
        self.config = DEFAULT_CONFIG.copy()

state = AppState()

# ======================
# INITIALIZATION
# ======================
def load_config():
    """Load configuration from file with error handling"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                state.config = {**DEFAULT_CONFIG, **json.load(f)}
        
        # Apply config to state
        state.current_test = state.config.get('current_test', 'snellen')
        state.viewing_distance_cm = state.config.get('viewing_distance_cm', 300) * 10
        state.brightness = state.config.get('brightness', 100)
        state.contrast = state.config.get('contrast', 50)
        state.language = state.config.get('language', 'english')
        
        # Handle screen orientation
        if state.config.get('orientation', 'landscape') == 'landscape':
            state.screen_width = state.config.get('screen_width', 800)
            state.screen_height = state.config.get('screen_height', 480)
        else:
            state.screen_width = state.config.get('screen_height', 480)
            state.screen_height = state.config.get('screen_width', 800)
            
    except Exception as e:
        print(f"Config load error: {e}. Using defaults.")
        save_config()

def save_config():
    """Save current configuration to file"""
    try:
        state.config.update({
            'current_test': state.current_test,
            'viewing_distance_cm': state.viewing_distance_cm // 10,
            'brightness': state.brightness,
            'contrast': state.contrast,
            'language': state.language
        })
        with open(CONFIG_FILE, 'w') as f:
            json.dump(state.config, f, indent=2)
    except Exception as e:
        print(f"Config save error: {e}")

def init_display():
    """Initialize pygame display with fallbacks"""
    try:
        pygame.init()
        pygame.font.init()
        
        # Initialize fonts with fallbacks
        try:
            state.main_font = pygame.font.Font(None, 100)
            state.small_font = pygame.font.Font(None, 40)
        except:
            state.main_font = pygame.font.SysFont('arial', 100)
            state.small_font = pygame.font.SysFont('arial', 40)
        
        # Initialize display with fallback
        try:
            state.screen = pygame.display.set_mode(
                (state.screen_width, state.screen_height), 
                pygame.FULLSCREEN | pygame.HWSURFACE
            )
            print(f"Display: {state.screen_width}x{state.screen_height} (Fullscreen)")
        except pygame.error:
            state.screen = pygame.display.set_mode((800, 480))
            state.screen_width, state.screen_height = 800, 480
            print("Display: Fallback to 800x480 windowed")
        
        pygame.mouse.set_visible(False)
        return True
        
    except Exception as e:
        print(f"Display init failed: {e}")
        return False

def cleanup():
    """Ensure proper cleanup on exit"""
    pygame.quit()
    GPIO.cleanup()
    print("Cleanup complete")

# ======================
# DRAWING FUNCTIONS
# ======================
def mm_to_pixels(mm):
    """Convert mm at viewing distance to screen pixels"""
    viewing_distance_mm = state.viewing_distance_cm * 10
    screen_diagonal_in = math.sqrt(state.screen_width**2 + state.screen_height**2) / 96
    screen_diagonal_mm = screen_diagonal_in * 25.4
    scaling_factor = screen_diagonal_mm / (2 * viewing_distance_mm * math.tan(math.radians(1/60)))
    return int(mm * scaling_factor)

def draw_snellen_optotype(optotype, size_mm, x, y):
    """Draw Snellen optotype at specified position and size"""
    try:
        size_px = mm_to_pixels(size_mm)
        if optotype in ['E', 'P', 'T', 'O', 'Z', 'L', 'D', 'F', 'C']:
            font = pygame.font.Font(None, size_px)
            text = font.render(optotype, True, BLACK)
            text_rect = text.get_rect(center=(x, y))
            state.screen.blit(text, text_rect)
        elif optotype == 'FP':
            font = pygame.font.Font(None, size_px)
            text1 = font.render('F', True, BLACK)
            text2 = font.render('P', True, BLACK)
            state.screen.blit(text1, (x - size_px, y - size_px//2))
            state.screen.blit(text2, (x + size_px//2, y - size_px//2))
    except Exception as e:
        print(f"Error drawing optotype: {e}")

# [Include other drawing functions with similar error handling...]

def draw_test():
    """Draw the current vision test"""
    try:
        state.screen.fill(WHITE)
        
        if state.current_test == 'snellen':
            # Draw Snellen chart
            lang_data = LANGUAGES.get(state.language, LANGUAGES['english'])
            for i, (optotypes, size_mm) in enumerate(lang_data['snellen']):
                y_pos = (i + 1) * state.screen_height // (len(lang_data['snellen']) + 1)
                for j, optotype in enumerate(optotypes):
                    x_pos = state.screen_width // 2 + (j - len(optotypes)//2) * mm_to_pixels(size_mm * 1.5)
                    draw_snellen_optotype(optotype, size_mm, x_pos, y_pos)
            
            instructions = state.small_font.render(
                lang_data.get('instructions', ''), 
                True, 
                BLACK
            )
            state.screen.blit(
                instructions, 
                (state.screen_width//2 - instructions.get_width()//2, 
                 state.screen_height - 50)
            )
        
        # [Other test cases...]
        
        # Display current settings
        test_name = state.small_font.render(
            f"Test: {state.current_test.upper()} | "
            f"Distance: {state.viewing_distance_cm//10}cm | "
            f"Lang: {state.language}", 
            True, 
            BLACK
        )
        state.screen.blit(test_name, (10, 10))
        
        pygame.display.flip()
        
    except Exception as e:
        print(f"Draw error: {e}")
        traceback.print_exc()

# ======================
# COMMUNICATION SERVERS
# ======================
def bluetooth_server():
    """Handle Bluetooth remote commands"""
    try:
        server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        port = state.config['bluetooth_port']
        
        server_sock.bind(("", port))
        server_sock.listen(1)
        print(f"Bluetooth: Listening on port {port}")

        while state.running:
            try:
                client_sock, client_info = server_sock.accept()
                print(f"Bluetooth: Connected to {client_info}")
                
                client_sock.settimeout(5.0)  # Prevent hanging
                
                while state.running:
                    try:
                        data = client_sock.recv(1024)
                        if not data:
                            break
                        
                        command = data.decode('utf-8').strip()
                        print(f"Bluetooth command: {command}")
                        handle_command(command)
                        
                    except bluetooth.btcommon.BluetoothError as e:
                        print(f"Bluetooth error: {e}")
                        break
                    except socket.timeout:
                        continue
                        
            except Exception as e:
                print(f"Bluetooth connection error: {e}")
            finally:
                try:
                    client_sock.close()
                except:
                    pass
                
    except Exception as e:
        print(f"Bluetooth server failed: {e}")
    finally:
        try:
            server_sock.close()
        except:
            pass

class RequestHandler(BaseHTTPRequestHandler):
    """Handle web interface requests"""
    def do_GET(self):
        try:
            if self.path == '/':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                html = f"""<html><body>
                    <h1>Vision Test Controller</h1>
                    <p>Current Test: {state.current_test}</p>
                    <!-- Rest of web interface -->
                </body></html>"""
                self.wfile.write(html.encode('utf-8'))
            
            elif self.path.startswith('/command'):
                self.send_response(200)
                self.send_header('Content-type', 'text/plain')
                self.end_headers()
                
                query = parse_qs(urlparse(self.path).query)
                if 'test' in query:
                    handle_command(f"test {query['test'][0]}")
                # [Handle other commands...]
                
                self.wfile.write(b"OK")
                
        except Exception as e:
            print(f"Web request error: {e}")
            self.send_error(500)

    def log_message(self, format, *args):
        pass  # Disable default logging

def start_web_server():
    """Run the web interface server"""
    try:
        server = HTTPServer(('0.0.0.0', 8080), RequestHandler)
        print(f"Web server: Running on port 8080")
        server.serve_forever()
    except Exception as e:
        print(f"Web server error: {e}")

def setup_ir_remote():
    """Initialize IR remote control"""
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(state.config['ir_pin'], GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        def ir_callback(channel):
            if not GPIO.input(channel):  # Only on falling edge
                print("IR: Next command")
                handle_command("next")
        
        GPIO.add_event_detect(
            state.config['ir_pin'], 
            GPIO.FALLING, 
            callback=ir_callback, 
            bouncetime=200
        )
        print("IR remote: Ready")
    except Exception as e:
        print(f"IR remote error: {e}")

# ======================
# COMMAND HANDLING
# ======================
def handle_command(command):
    """Process control commands from any interface"""
    try:
        parts = command.lower().split()
        if not parts:
            return
        
        cmd = parts[0]
        args = parts[1:]
        
        if cmd == 'test' and args:
            state.current_test = args[0]
            state.config['current_test'] = state.current_test
            save_config()
        
        # [Other command handling...]
        
        elif cmd == 'exit':
            state.running = False
            return
        
        draw_test()
        
    except Exception as e:
        print(f"Command error: {e}")

# ======================
# MAIN APPLICATION
# ======================
def main():
    """Main application entry point"""
    atexit.register(cleanup)
    load_config()
    
    if not init_display():
        return
    
    try:
        # Start services in threads
        services = [
            threading.Thread(target=bluetooth_server, daemon=True),
            threading.Thread(target=start_web_server, daemon=True)
        ]
        
        for service in services:
            service.start()
        
        setup_ir_remote()
        
        # Main loop
        clock = pygame.time.Clock()
        draw_test()  # Initial draw
        
        while state.running:
            for event in pygame.event.get():
                if event.type == QUIT:
                    state.running = False
                elif event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        state.running = False
                    # [Other key handlers...]
            
            clock.tick(30)  # Cap at 30 FPS
            
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Fatal error: {e}")
        traceback.print_exc()
    finally:
        state.running = False
        time.sleep(1)  # Allow threads to exit

if __name__ == "__main__":
    main()