
import os
import shutil
import re

# 配置路径
PROJECT_ROOT = r"f:\Projects\campus-dining-experience"
SOURCE_DIR = os.path.join(PROJECT_ROOT, "pages", "c-client")
TARGET_DIR = os.path.join(PROJECT_ROOT, "dining_system", "pages", "c-client")

# 需要迁移的文件列表 (根据 ls 结果)
FILES_TO_MOVE = [
    "canteen_detail.html",
    "dish_detail.html",
    "evaluation_scan.html",
    "post_detail.html",
    "post_publish.html",
    "rank_list.html",
    "scan_review_demo.html",
    "scan_review_advanced.html",
    "scan_review_modular.html"
]

def fix_and_move_files():
    print(f"Source: {SOURCE_DIR}")
    print(f"Target: {TARGET_DIR}")
    
    if not os.path.exists(SOURCE_DIR):
        print("Error: Source directory not found!")
        return

    if not os.path.exists(TARGET_DIR):
        os.makedirs(TARGET_DIR)
        print("Created target directory.")

    for filename in FILES_TO_MOVE:
        src_path = os.path.join(SOURCE_DIR, filename)
        dst_path = os.path.join(TARGET_DIR, filename)
        
        if not os.path.exists(src_path):
            print(f"Warning: Source file not found: {filename}")
            continue
            
        # 读取文件内容
        with open(src_path, 'r', encoding='utf-8') as f:
            content = f.read()
            
        # 修正资源路径 (简单替换)
        new_content = content
        
        # 1. 替换 CSS 路径
        # 匹配 href=".../bootstrap.min.css" 或 href="bootstrap.min.css"
        new_content = re.sub(r'href=".*?bootstrap\.min\.css"', 'href="../../static/css/bootstrap.min.css"', new_content)
        
        # 2. 替换 JS 路径
        new_content = re.sub(r'src=".*?bootstrap\.bundle\.min\.js"', 'src="../../static/js/bootstrap.bundle.min.js"', new_content)
        
        # 3. 注入 common.css (如果不存在)
        if 'common.css' not in new_content:
            new_content = new_content.replace('</head>', '    <link href="../../static/css/common.css" rel="stylesheet">\n</head>')
        else:
            new_content = re.sub(r'href=".*?common\.css"', 'href="../../static/css/common.css"', new_content)
            
        # 4. 注入 common.js (如果不存在)
        if 'common.js' not in new_content:
            new_content = new_content.replace('</body>', '    <script src="../../static/js/common.js"></script>\n</body>')
        else:
            new_content = re.sub(r'src=".*?common\.js"', 'src="../../static/js/common.js"', new_content)

        # 5. 注入 mock_data.js (如果不存在)
        if 'mock_data.js' not in new_content:
             new_content = new_content.replace('</body>', '    <script src="../../static/js/mock_data.js"></script>\n</body>')
        
        # 写入目标文件
        with open(dst_path, 'w', encoding='utf-8') as f:
            f.write(new_content)
            
        print(f"Processed & Moved: {filename}")

if __name__ == "__main__":
    fix_and_move_files()
