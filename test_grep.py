import re

with open(r'f:\Projects\campus-dining-experience\dining_system\pages\c-client\backend\app.py', 'r', encoding='utf-8') as f:
    for i, line in enumerate(f):
        if 'canteen_id' in line or 'identity' in line:
            print(f'{i+1}: {line.strip()}')