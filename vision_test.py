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

# Initialize pygame with error handling
try:
    pygame.init()
    pygame.font.init()
    print("Pygame initialized successfully")
except Exception as e:
    print(f"Pygame initialization failed: {e}")
    exit(1)

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
    config = {**DEFAULT_CONFIG, **config}
except (FileNotFoundError, json.JSONDecodeError):
    config = DEFAULT_CONFIG
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config, f)

# Screen setup with fallback
try:
    if config['orientation'] == 'landscape':
        screen_width, screen_height = config['screen_width'], config['screen_height']
    else:
        screen_width, screen_height = config['screen_height'], config['screen_width']

    screen = pygame.display.set_mode((screen_width, screen_height), pygame.FULLSCREEN)
    print(f"Display set to {screen_width}x{screen_height} (Fullscreen)")
except pygame.error as e:
    print(f"Fullscreen failed: {e}. Falling back to windowed mode.")
    screen = pygame.display.set_mode((800, 480))
    screen_width, screen_height = 800, 480

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

# Fonts with fallback
try:
    main_font = pygame.font.Font(None, 100)
    small_font = pygame.font.Font(None, 40)
except:
    main_font = pygame.font.SysFont('arial', 100)
    small_font = pygame.font.SysFont('arial', 40)

# Global variables
running = True  # Fix for UnboundLocalError
viewing_distance_cm = config['viewing_distance_cm'] * 10
current_test = config['current_test']
brightness = config['brightness']
contrast = config['contrast']
language = config['language']

# [Rest of your original helper functions remain unchanged...]
# (Include all your draw_snellen_optotype(), draw_tumbling_e(), etc. functions here)

def draw_test():
    try:
        screen.fill(BACKGROUND)
        
        if current_test == 'snellen':
            # [Your existing snellen test code...]
            pass
        # [All other test cases...]
        
        pygame.display.flip()
    except Exception as e:
        print(f"Drawing error: {e}")

def main():
    global running
    
    # Initial test draw
    draw_test()
    
    # Start services
    try:
        bt_thread = threading.Thread(target=bluetooth_server, daemon=True)
        bt_thread.start()
        web_thread = threading.Thread(target=start_web_server, daemon=True)
        web_thread.start()
        setup_ir_remote()
    except Exception as e:
        print(f"Service startup error: {e}")

    # Main loop
    clock = pygame.time.Clock()
    while running:
        for event in pygame.event.get():
            if event.type == QUIT:
                running = False
            elif event.type == KEYDOWN:
                if event.key == K_ESCAPE:
                    running = False
                # [Other key handlers...]
        
        clock.tick(30)  # Limit to 30 FPS
    
    pygame.quit()
    GPIO.cleanup()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Fatal error: {e}")
        pygame.quit()