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

# ======================
# GLOBAL INITIALIZATION
# ======================
running = True
current_test = 'snellen'
viewing_distance_cm = 300 * 10  # in mm
brightness = 100
contrast = 50
language = 'english'
screen = None
screen_width = 800
screen_height = 480

# ======================
# CONFIGURATION SETUP
# ======================
CONFIG_FILE = 'vision_config.json'
DEFAULT_CONFIG = {
    'screen_width': 800,
    'screen_height': 480,
    'viewing_distance_cm': 300,
    'current_test': current_test,
    'brightness': brightness,
    'contrast': contrast,
    'language': language,
    'orientation': 'landscape',
    'remote_control': 'web',
    'ir_pin': 23,
    'bluetooth_port': 1
}

def load_config():
    global current_test, viewing_distance_cm, brightness, contrast, language, screen_width, screen_height
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            config = json.load(f)
        
        # Update globals from config
        current_test = config.get('current_test', current_test)
        viewing_distance_cm = config.get('viewing_distance_cm', 300) * 10
        brightness = config.get('brightness', brightness)
        contrast = config.get('contrast', contrast)
        language = config.get('language', language)
        
        # Handle screen orientation
        if config.get('orientation', 'landscape') == 'landscape':
            screen_width = config.get('screen_width', 800)
            screen_height = config.get('screen_height', 480)
        else:
            screen_width = config.get('screen_height', 480)
            screen_height = config.get('screen_width', 800)
            
        return config
    except (FileNotFoundError, json.JSONDecodeError):
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f)
        return DEFAULT_CONFIG

# ======================
# DISPLAY INITIALIZATION
# ======================
def init_display():
    global screen, screen_width, screen_height
    
    try:
        pygame.init()
        pygame.font.init()
        
        try:
            screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
            print(f"Display set to {screen_width}x{screen_height} (Fullscreen)")
        except pygame.error:
            screen = pygame.display.set_mode((800, 480))
            screen_width, screen_height = 800, 480
            print("Fell back to 800x480 windowed mode")
        
        pygame.mouse.set_visible(False)
        return True
    except Exception as e:
        print(f"Display initialization failed: {e}")
        return False

# ======================
# TEST DATA & FUNCTIONS
# ======================
SNELLEN_LINES = [("E", 200), ("FP", 100), ("TOZ", 70), ("LPED", 50), ("PECFD", 40), ("EDFCZP", 30), ("FELOPZD", 20)]
LOGMAR_LINES = [("E", 1.0), ("P", 0.8), ("T", 0.63), ("O", 0.5), ("Z", 0.4), ("L", 0.32), ("E", 0.25)]
TUMBLING_E_ORIENTATIONS = ['up', 'right', 'down', 'left']
C_CHART_ORIENTATIONS = ['up', 'right', 'down', 'left']

LANGUAGES = {
    'english': {
        'snellen': SNELLEN_LINES,
        'logmar': LOGMAR_LINES,
        'numbers': [("12345", 200), ("67890", 100)],
        'instructions': "Cover one eye and read the smallest line you can see"
    },
    'hindi': {
        'snellen': [("अ", 200), ("आ", 100), ("इ", 70), ("ई", 50)],
        'instructions': "एक आँख को ढकें और सबसे छोटी पंक्ति पढ़ें जो आप देख सकते हैं"
    },
    'urdu': {
        'snellen': [("ا", 200), ("ب", 100), ("پ", 70), ("ت", 50)],
        'instructions': "ایک آنکھ کو ڈھانپیں اور سب سے چھوٹی لکیر پڑھیں جو آپ دیکھ سکتے ہیں"
    },
    'arabic': {
        'snellen': [("أ", 200), ("ب", 100), ("ج", 70), ("د", 50)],
        'instructions': "غطي عين واحدة واقرأ أصغر سطر يمكنك رؤيته"
    }
}

def mm_to_pixels(mm, viewing_distance_mm):
    screen_diagonal_in = math.sqrt(screen_width**2 + screen_height**2) / 96
    screen_diagonal_mm = screen_diagonal_in * 25.4
    scaling_factor = screen_diagonal_mm / (2 * viewing_distance_mm * math.tan(math.radians(1/60)))
    return int(mm * scaling_factor)

# [Include all your drawing functions here: draw_snellen_optotype(), draw_tumbling_e(), etc.]

# ======================
# COMMUNICATION SERVERS
# ======================
def bluetooth_server():
    global running
    
    try:
        server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
        port = config['bluetooth_port']
        
        server_sock.bind(("", port))
        server_sock.listen(1)
        print(f"Bluetooth server started on port {port}")

        while running:
            try:
                client_sock, client_info = server_sock.accept()
                print(f"Accepted connection from {client_info}")

                while running:
                    data = client_sock.recv(1024)
                    if not data:
                        break
                    
                    command = data.decode('utf-8').strip()
                    print(f"Received Bluetooth command: {command}")
                    handle_command(command)
                    
            except bluetooth.btcommon.BluetoothError as e:
                print(f"Bluetooth error: {e}")
            except Exception as e:
                print(f"Connection error: {e}")
            finally:
                try:
                    client_sock.close()
                except:
                    pass

    except Exception as e:
        print(f"Bluetooth server failed: {e}")

class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            html = f"""<html><body>
                <h1>Vision Test Controller</h1>
                <p>Current Test: {current_test}</p>
                <!-- Rest of your web interface HTML -->
            </body></html>"""
            self.wfile.write(html.encode('utf-8'))
        
        elif self.path.startswith('/command'):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            
            query = parse_qs(urlparse(self.path).query)
            if 'test' in query:
                handle_command(f"test {query['test'][0]}")
            # Handle other commands...
            
            self.wfile.write(b"OK")

def start_web_server():
    try:
        server = HTTPServer(('0.0.0.0', 8080), RequestHandler)
        print("Web server started on port 8080")
        server.serve_forever()
    except Exception as e:
        print(f"Web server failed: {e}")

def setup_ir_remote():
    try:
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(config['ir_pin'], GPIO.IN)
        
        def ir_callback(channel):
            print("IR signal received")
            handle_command("next")
        
        GPIO.add_event_detect(config['ir_pin'], GPIO.FALLING, callback=ir_callback, bouncetime=200)
    except Exception as e:
        print(f"IR remote setup failed: {e}")

# ======================
# MAIN PROGRAM LOGIC
# ======================
def handle_command(command):
    global current_test, viewing_distance_cm, brightness, contrast, language, running
    
    parts = command.lower().split()
    if not parts:
        return
    
    cmd = parts[0]
    args = parts[1:]
    
    if cmd == 'test' and args:
        current_test = args[0]
        config['current_test'] = current_test
        save_config()
    elif cmd == 'exit':
        running = False
    # Handle other commands...
    
    draw_test()

def save_config():
    config.update({
        'current_test': current_test,
        'viewing_distance_cm': viewing_distance_cm // 10,
        'brightness': brightness,
        'contrast': contrast,
        'language': language
    })
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

def draw_test():
    try:
        screen.fill(WHITE)
        
        if current_test == 'snellen':
            # Draw Snellen chart
            pass
        # Other test cases...
        
        pygame.display.flip()
    except Exception as e:
        print(f"Drawing error: {e}")

def main():
    global running, config
    
    if not init_display():
        return
    
    config = load_config()
    
    try:
        # Start services
        bt_thread = threading.Thread(target=bluetooth_server, daemon=True)
        bt_thread.start()
        
        web_thread = threading.Thread(target=start_web_server, daemon=True)
        web_thread.start()
        
        setup_ir_remote()
        
        # Main loop
        clock = pygame.time.Clock()
        while running:
            for event in pygame.event.get():
                if event.type == QUIT:
                    running = False
                elif event.type == KEYDOWN:
                    if event.key == K_ESCAPE:
                        running = False
                    # Handle other keys...
            
            draw_test()
            clock.tick(30)
            
    except Exception as e:
        print(f"Runtime error: {e}")
    finally:
        pygame.quit()
        GPIO.cleanup()
        print("Program exited cleanly")

if __name__ == "__main__":
    main()