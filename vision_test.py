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

# Initialize pygame
pygame.init()
pygame.font.init()

# Configuration
CONFIG_FILE = 'vision_config.json'
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

# Load or create config
try:
    with open(CONFIG_FILE, 'r') as f:
        config = json.load(f)
    # Merge with default to ensure all keys exist
    config = {**DEFAULT_CONFIG, **config}
except (FileNotFoundError, json.JSONDecodeError):
    config = DEFAULT_CONFIG
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# Screen setup
if config['orientation'] == 'landscape':
    screen_width, screen_height = config['screen_width'], config['screen_height']
else:
    screen_width, screen_height = config['screen_height'], config['screen_width']

screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
pygame.mouse.set_visible(False)

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
BLUE = (0, 0, 255)
GRAY = (128, 128, 128)
BACKGROUND = WHITE
FOREGROUND = BLACK

# Fonts
try:
    main_font = pygame.font.Font(None, 100)
    small_font = pygame.font.Font(None, 40)
except:
    # Fallback if fonts aren't available
    main_font = pygame.font.SysFont('arial', 100)
    small_font = pygame.font.SysFont('arial', 40)

# Test parameters
viewing_distance_cm = config['viewing_distance_cm'] * 10  # convert to mm
current_test = config['current_test']
brightness = config['brightness']
contrast = config['contrast']
language = config['language']
running = True

# Test data
SNELLEN_LINES = [
    ("E", 200),
    ("FP", 100),
    ("TOZ", 70),
    ("LPED", 50),
    ("PECFD", 40),
    ("EDFCZP", 30),
    ("FELOPZD", 20)
]

LOGMAR_LINES = [
    ("E", 1.0),
    ("P", 0.8),
    ("T", 0.63),
    ("O", 0.5),
    ("Z", 0.4),
    ("L", 0.32),
    ("E", 0.25)
]

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

# Helper functions
def mm_to_pixels(mm, viewing_distance_mm):
    # Convert mm at viewing distance to pixels on screen
    # Assuming typical screen DPI (96) and size (depends on config)
    screen_diagonal_in = math.sqrt(screen_width**2 + screen_height**2) / 96
    screen_diagonal_mm = screen_diagonal_in * 25.4
    scaling_factor = screen_diagonal_mm / (2 * viewing_distance_mm * math.tan(math.radians(1/60)))  # 1 arcminute
    return int(mm * scaling_factor)

def draw_snellen_optotype(optotype, size_mm, x, y):
    size_px = mm_to_pixels(size_mm, viewing_distance_cm * 10)
    if optotype in ['E', 'P', 'T', 'O', 'Z', 'L', 'D', 'F', 'C']:
        # Draw standard Snellen letters
        font = pygame.font.Font(None, size_px)
        text = font.render(optotype, True, FOREGROUND)
        text_rect = text.get_rect(center=(x, y))
        screen.blit(text, text_rect)
    elif optotype == 'FP':
        # Draw two letters
        font = pygame.font.Font(None, size_px)
        text1 = font.render('F', True, FOREGROUND)
        text2 = font.render('P', True, FOREGROUND)
        screen.blit(text1, (x - size_px, y - size_px//2))
        screen.blit(text2, (x + size_px//2, y - size_px//2))
    else:
        # Handle other cases
        pass

def draw_tumbling_e(orientation, size_mm, x, y):
    size_px = mm_to_pixels(size_mm, viewing_distance_cm * 10)
    bar_width = size_px // 5
    bar_length = size_px
    
    # Create a surface for the E
    e_surface = pygame.Surface((size_px, size_px), pygame.SRCALPHA)
    
    # Draw the E based on orientation
    if orientation == 'up':
        pygame.draw.rect(e_surface, FOREGROUND, (0, 0, size_px, bar_width))  # Top
        pygame.draw.rect(e_surface, FOREGROUND, (0, 0, bar_width, size_px))  # Left
        pygame.draw.rect(e_surface, FOREGROUND, (0, size_px//2 - bar_width//2, size_px, bar_width))  # Middle
        pygame.draw.rect(e_surface, FOREGROUND, (0, size_px - bar_width, size_px, bar_width))  # Bottom
    elif orientation == 'right':
        pygame.draw.rect(e_surface, FOREGROUND, (0, 0, size_px, bar_width))  # Top
        pygame.draw.rect(e_surface, FOREGROUND, (size_px - bar_width, 0, bar_width, size_px))  # Right
        pygame.draw.rect(e_surface, FOREGROUND, (0, size_px//2 - bar_width//2, size_px, bar_width))  # Middle
        pygame.draw.rect(e_surface, FOREGROUND, (0, size_px - bar_width, size_px, bar_width))  # Bottom
    elif orientation == 'down':
        pygame.draw.rect(e_surface, FOREGROUND, (0, 0, bar_width, size_px))  # Left
        pygame.draw.rect(e_surface, FOREGROUND, (0, 0, size_px, bar_width))  # Top
        pygame.draw.rect(e_surface, FOREGROUND, (0, size_px//2 - bar_width//2, size_px, bar_width))  # Middle
        pygame.draw.rect(e_surface, FOREGROUND, (size_px - bar_width, 0, bar_width, size_px))  # Right
    elif orientation == 'left':
        pygame.draw.rect(e_surface, FOREGROUND, (0, 0, size_px, bar_width))  # Top
        pygame.draw.rect(e_surface, FOREGROUND, (0, 0, bar_width, size_px))  # Left
        pygame.draw.rect(e_surface, FOREGROUND, (0, size_px//2 - bar_width//2, size_px, bar_width))  # Middle
        pygame.draw.rect(e_surface, FOREGROUND, (size_px - bar_width, 0, bar_width, size_px))  # Right
    
    # Rotate if needed and draw to screen
    rotated = pygame.transform.rotate(e_surface, {'up':0, 'right':270, 'down':180, 'left':90}[orientation])
    screen.blit(rotated, (x - size_px//2, y - size_px//2))

def draw_c_chart(orientation, size_mm, x, y):
    size_px = mm_to_pixels(size_mm, viewing_distance_cm * 10)
    ring_width = size_px // 5
    gap_size = size_px // 4
    
    # Create a surface for the C
    c_surface = pygame.Surface((size_px, size_px), pygame.SRCALPHA)
    pygame.draw.circle(c_surface, FOREGROUND, (size_px//2, size_px//2), size_px//2)
    pygame.draw.circle(c_surface, BACKGROUND, (size_px//2, size_px//2), size_px//2 - ring_width)
    
    # Cut out the gap based on orientation
    gap_rect = pygame.Rect(0, 0, gap_size, ring_width * 2)
    if orientation == 'up':
        gap_rect.center = (size_px//2, size_px//2 - size_px//2 + ring_width//2)
    elif orientation == 'right':
        gap_rect.center = (size_px//2 + size_px//2 - ring_width//2, size_px//2)
    elif orientation == 'down':
        gap_rect.center = (size_px//2, size_px//2 + size_px//2 - ring_width//2)
    elif orientation == 'left':
        gap_rect.center = (size_px//2 - size_px//2 + ring_width//2, size_px//2)
    
    pygame.draw.rect(c_surface, BACKGROUND, gap_rect)
    
    # Rotate if needed and draw to screen
    screen.blit(c_surface, (x - size_px//2, y - size_px//2))

def draw_astigmatic_fan():
    center_x, center_y = screen_width // 2, screen_height // 2
    radius = min(screen_width, screen_height) // 2 - 20
    
    # Draw fan lines
    for angle in range(0, 180, 10):
        rad = math.radians(angle)
        end_x = center_x + radius * math.cos(rad)
        end_y = center_y + radius * math.sin(rad)
        pygame.draw.line(screen, FOREGROUND, (center_x, center_y), (end_x, end_y), 2)
    
    # Add labels
    for angle in range(0, 180, 30):
        rad = math.radians(angle)
        label_x = center_x + (radius + 20) * math.cos(rad)
        label_y = center_y + (radius + 20) * math.sin(rad)
        label = small_font.render(str(angle), True, FOREGROUND)
        screen.blit(label, (label_x - label.get_width()//2, label_y - label.get_height()//2))

def draw_duochrome():
    # Left half red, right half green
    pygame.draw.rect(screen, (255, 50, 50), (0, 0, screen_width//2, screen_height))
    pygame.draw.rect(screen, (50, 255, 50), (screen_width//2, 0, screen_width//2, screen_height))
    
    # Add letters in the middle
    font_size = mm_to_pixels(10, viewing_distance_cm * 10)
    font = pygame.font.Font(None, font_size)
    
    for i, letter in enumerate("ABCDEFGH"):
        y_pos = (i + 1) * screen_height // 9
        # Red side
        text = font.render(letter, True, BLACK)
        screen.blit(text, (screen_width//4 - text.get_width()//2, y_pos - text.get_height()//2))
        # Green side
        screen.blit(text, (3*screen_width//4 - text.get_width()//2, y_pos - text.get_height()//2))

def draw_contrast_sensitivity():
    # Create a gradient from high to low contrast
    for i in range(screen_width):
        # Logarithmic scale for contrast
        contrast_level = 1.0 - (i / screen_width) ** 2
        color = int(255 * contrast_level)
        pygame.draw.line(screen, (color, color, color), (i, 0), (i, screen_height))
    
    # Add letters with decreasing contrast
    font_size = mm_to_pixels(20, viewing_distance_cm * 10)
    font = pygame.font.Font(None, font_size)
    
    for i in range(1, 6):
        x_pos = i * screen_width // 6
        contrast_level = 1.0 - (i / 6) ** 2
        color = int(255 * contrast_level)
        text = font.render("TEST", True, (color, color, color))
        screen.blit(text, (x_pos - text.get_width()//2, screen_height//2 - text.get_height()//2))

def draw_color_vision():
    # Ishihara-like plates (simplified)
    circles = [
        (screen_width//4, screen_height//4, 100, (255, 100, 100), "12"),
        (3*screen_width//4, screen_height//4, 100, (100, 255, 100), "8"),
        (screen_width//4, 3*screen_height//4, 100, (100, 100, 255), "6"),
        (3*screen_width//4, 3*screen_height//4, 100, (255, 255, 100), "15")
    ]
    
    for x, y, r, color, number in circles:
        pygame.draw.circle(screen, color, (x, y), mm_to_pixels(r, viewing_distance_cm * 10))
        font_size = mm_to_pixels(30, viewing_distance_cm * 10)
        font = pygame.font.Font(None, font_size)
        text = font.render(number, True, BLACK)
        screen.blit(text, (x - text.get_width()//2, y - text.get_height()//2))

def draw_test():
    screen.fill(BACKGROUND)
    
    if current_test == 'snellen':
        lang_data = LANGUAGES.get(language, LANGUAGES['english'])
        for i, (optotypes, size_mm) in enumerate(lang_data['snellen']):
            y_pos = (i + 1) * screen_height // (len(lang_data['snellen']) + 1)
            for j, optotype in enumerate(optotypes):
                x_pos = screen_width // 2 + (j - len(optotypes)//2) * mm_to_pixels(size_mm * 1.5, viewing_distance_cm * 10)
                draw_snellen_optotype(optotype, size_mm, x_pos, y_pos)
        
        # Instructions
        instructions = small_font.render(lang_data.get('instructions', ''), True, FOREGROUND)
        screen.blit(instructions, (screen_width//2 - instructions.get_width()//2, screen_height - 50))
    
    elif current_test == 'logmar':
        for i, (optotype, logmar_size) in enumerate(LOGMAR_LINES):
            size_mm = 50 * (10 ** logmar_size)  # Convert logMAR to mm
            y_pos = (i + 1) * screen_height // (len(LOGMAR_LINES) + 1)
            x_pos = screen_width // 2
            draw_snellen_optotype(optotype, size_mm, x_pos, y_pos)
    
    elif current_test == 'tumbling_e':
        size_mm = 50  # Starting size
        orientations = TUMBLING_E_ORIENTATIONS * 3  # Repeat for multiple lines
        
        for i in range(5):  # 5 lines
            y_pos = (i + 1) * screen_height // 6
            current_size = size_mm / (i + 1)
            
            for j in range(3):  # 3 Es per line
                x_pos = screen_width // 4 * (j + 1)
                orientation = orientations[i*3 + j]
                draw_tumbling_e(orientation, current_size, x_pos, y_pos)
    
    elif current_test == 'c_chart':
        size_mm = 50  # Starting size
        orientations = C_CHART_ORIENTATIONS * 3  # Repeat for multiple lines
        
        for i in range(5):  # 5 lines
            y_pos = (i + 1) * screen_height // 6
            current_size = size_mm / (i + 1)
            
            for j in range(3):  # 3 Cs per line
                x_pos = screen_width // 4 * (j + 1)
                orientation = orientations[i*3 + j]
                draw_c_chart(orientation, current_size, x_pos, y_pos)
    
    elif current_test == 'numbers':
        lang_data = LANGUAGES.get(language, LANGUAGES['english'])
        for i, (numbers, size_mm) in enumerate(lang_data['numbers']):
            y_pos = (i + 1) * screen_height // (len(lang_data['numbers']) + 1)
            for j, number in enumerate(numbers):
                x_pos = screen_width // 2 + (j - len(numbers)//2) * mm_to_pixels(size_mm * 1.5, viewing_distance_cm * 10)
                draw_snellen_optotype(number, size_mm, x_pos, y_pos)
    
    elif current_test == 'astigmatic_fan':
        draw_astigmatic_fan()
    
    elif current_test == 'duochrome':
        draw_duochrome()
    
    elif current_test == 'contrast':
        draw_contrast_sensitivity()
    
    elif current_test == 'color':
        draw_color_vision()
    
    # Display current test name and settings
    test_name = small_font.render(f"Test: {current_test.upper()} | Distance: {viewing_distance_cm//10}cm | Lang: {language}", True, FOREGROUND)
    screen.blit(test_name, (10, 10))
    
    pygame.display.flip()

# Bluetooth server
def bluetooth_server():
    server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
    server_sock.bind(("", config['bluetooth_port']))
    server_sock.listen(1)
    
    while running:
        try:
            client_sock, address = server_sock.accept()
            print(f"Bluetooth connection from {address}")
            
            while running:
                data = client_sock.recv(1024).decode('utf-8').strip()
                if not data:
                    break
                
                print(f"Bluetooth command: {data}")
                handle_command(data)
                
        except bluetooth.btcommon.BluetoothError as e:
            print(f"Bluetooth error: {e}")
            time.sleep(1)

# Web server
class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            
            # Simple web interface
            html = f"""
            <html>
                <body>
                    <h1>Vision Test Controller</h1>
                    <p>Current Test: {current_test}</p>
                    <p>Viewing Distance: {viewing_distance_cm//10}cm</p>
                    <p>Language: {language}</p>
                    
                    <h2>Change Test</h2>
                    <a href="/command?test=snellen"><button>Snellen</button></a>
                    <a href="/command?test=logmar"><button>LogMAR</button></a>
                    <a href="/command?test=tumbling_e"><button>Tumbling E</button></a>
                    <a href="/command?test=c_chart"><button>C Chart</button></a>
                    <a href="/command?test=numbers"><button>Numbers</button></a>
                    <a href="/command?test=astigmatic_fan"><button>Astigmatic Fan</button></a>
                    <a href="/command?test=duochrome"><button>Duochrome</button></a>
                    <a href="/command?test=contrast"><button>Contrast</button></a>
                    <a href="/command?test=color"><button>Color Vision</button></a>
                    
                    <h2>Settings</h2>
                    <form action="/command">
                        <label>Distance (cm): <input type="number" name="distance" value="{viewing_distance_cm//10}"></label>
                        <input type="submit" value="Set">
                    </form>
                    
                    <h2>Language</h2>
                    <a href="/command?language=english"><button>English</button></a>
                    <a href="/command?language=hindi"><button>Hindi</button></a>
                    <a href="/command?language=urdu"><button>Urdu</button></a>
                    <a href="/command?language=arabic"><button>Arabic</button></a>
                    
                    <h2>System</h2>
                    <a href="/command?brightness=up"><button>Brightness +</button></a>
                    <a href="/command?brightness=down"><button>Brightness -</button></a>
                    <a href="/command?exit"><button>Exit</button></a>
                </body>
            </html>
            """
            self.wfile.write(html.encode('utf-8'))
        
        elif self.path.startswith('/command'):
            self.send_response(200)
            self.send_header('Content-type', 'text/plain')
            self.end_headers()
            
            # Parse query parameters
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(self.path).query)
            
            # Handle commands
            if 'test' in query:
                handle_command(f"test {query['test'][0]}")
            elif 'distance' in query:
                handle_command(f"distance {query['distance'][0]}")
            elif 'language' in query:
                handle_command(f"language {query['language'][0]}")
            elif 'brightness' in query:
                handle_command(f"brightness {query['brightness'][0]}")
            elif 'exit' in query:
                handle_command("exit")
            
            self.wfile.write(b"OK")
    
    def log_message(self, format, *args):
        # Disable logging to stderr
        return

def start_web_server():
    server = HTTPServer(('0.0.0.0', 8080), RequestHandler)
    print("Web server started on port 8080")
    server.serve_forever()

# IR remote control (simplified)
def setup_ir_remote():
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(config['ir_pin'], GPIO.IN)
    
    # Simple IR decoding (would need to be customized for your remote)
    def ir_callback(channel):
        # This is a placeholder - actual IR decoding would be more complex
        print("IR signal received")
        handle_command("next")  # Just cycle to next test for demo
    
    GPIO.add_event_detect(config['ir_pin'], GPIO.FALLING, callback=ir_callback, bouncetime=200)

# Command handling
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
    
    elif cmd == 'distance' and args:
        try:
            viewing_distance_cm = int(args[0]) * 10
            config['viewing_distance_cm'] = viewing_distance_cm // 10
            save_config()
        except ValueError:
            pass
    
    elif cmd == 'brightness' and args:
        if args[0] == 'up' and brightness < 100:
            brightness += 10
        elif args[0] == 'down' and brightness > 0:
            brightness -= 10
        config['brightness'] = brightness
        save_config()
        # In a real implementation, you'd adjust the screen brightness here
    
    elif cmd == 'contrast' and args:
        if args[0] == 'up' and contrast < 100:
            contrast += 10
        elif args[0] == 'down' and contrast > 0:
            contrast -= 10
        config['contrast'] = contrast
        save_config()
    
    elif cmd == 'language' and args:
        language = args[0]
        config['language'] = language
        save_config()
    
    elif cmd == 'next':
        tests = ['snellen', 'logmar', 'tumbling_e', 'c_chart', 'numbers', 
                'astigmatic_fan', 'duochrome', 'contrast', 'color']
        current_idx = tests.index(current_test) if current_test in tests else 0
        current_test = tests[(current_idx + 1) % len(tests)]
        config['current_test'] = current_test
        save_config()
    
    elif cmd == 'prev':
        tests = ['snellen', 'logmar', 'tumbling_e', 'c_chart', 'numbers', 
                'astigmatic_fan', 'duochrome', 'contrast', 'color']
        current_idx = tests.index(current_test) if current_test in tests else 0
        current_test = tests[(current_idx - 1) % len(tests)]
        config['current_test'] = current_test
        save_config()
    
    elif cmd == 'exit':
        running = False
    
    draw_test()

def save_config():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# Main loop
def main():
    # Start Bluetooth server in a thread
    bt_thread = threading.Thread(target=bluetooth_server, daemon=True)
    bt_thread.start()
    
    # Start web server in a thread
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    
    # Setup IR remote
    try:
        setup_ir_remote()
    except Exception as e:
        print(f"Failed to setup IR remote: {e}")
    
    # Initial draw
    draw_test()
    
    # Main event loop
    while running:
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    running = False
                elif event.key == K_RIGHT:
                    handle_command("next")
                elif event.key == K_LEFT:
                    handle_command("prev")
                elif event.key == K_UP:
                    handle_command("brightness up")
                elif event.key == K_DOWN:
                    handle_command("brightness down")
                elif event.key == K_1:
                    handle_command("test snellen")
                elif event.key == K_2:
                    handle_command("test logmar")
                elif event.key == K_3:
                    handle_command("test tumbling_e")
                elif event.key == K_4:
                    handle_command("test c_chart")
                elif event.key == K_5:
                    handle_command("test numbers")
                elif event.key == K_6:
                    handle_command("test astigmatic_fan")
                elif event.key == K_7:
                    handle_command("test duochrome")
                elif event.key == K_8:
                    handle_command("test contrast")
                elif event.key == K_9:
                    handle_command("test color")
                elif event.key == K_l:
                    handle_command("language english")
                elif event.key == K_h:
                    handle_command("language hindi")
                elif event.key == K_u:
                    handle_command("language urdu")
                elif event.key == K_a:
                    handle_command("language arabic")
        
        time.sleep(0.1)
    
    pygame.quit()
    GPIO.cleanup()

if __name__ == "__main__":
    main()