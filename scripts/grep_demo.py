SOURCE = r'f:\Projects\campus-dining-experience\dining_system\pages\c-client\backend\app.py'


if __name__ == '__main__':
    with open(SOURCE, 'r', encoding='utf-8') as handle:
        for index, line in enumerate(handle):
            if 'canteen_id' in line or 'identity' in line:
                print(f'{index + 1}: {line.strip()}')
