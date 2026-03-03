import os
import shutil
import re

# 配置项目根目录 (相对于当前脚本)
BASE_DIR = os.getcwd()

# 目录结构配置
DIR_STRUCTURE = {
    'pages/c-client': [
        'index.html', 'login.html', 'forget_password.html', 'user_center.html',
        'evaluation_scan.html', 'post_publish.html', 'post_detail.html',
        'canteen_detail.html', 'dish_detail.html', 'safety_list.html', 'rank_list.html',
        'scan_review_demo.html', 'scan_review_advanced.html', 'scan_review_modular.html' # 包含早期的demo文件
    ],
    'pages/b-admin': [
        'admin_index.html', 'admin_user.html', 'admin_audit.html',
        'admin_settings.html', 'dish_evaluation_admin.html'
    ],
    'pages/common': [
        'error_page.html'
    ],
    'static/css': [
        'common.css'
    ],
    'static/js': [
        'common.js'
    ],
    'static/img': [], # 图片文件夹，暂无具体文件移动
}

# 资源路径替换规则 (HTML文件)
# key: 文件所在目录类型, value: 替换逻辑
REPLACE_RULES = {
    'pages/c-client': [
        (r'href="[^"]*bootstrap\.min\.css"', 'href="../../static/css/bootstrap.min.css"'),
        (r'href="[^"]*common\.css"', 'href="../../static/css/common.css"'),
        (r'src="[^"]*bootstrap\.bundle\.min\.js"', 'src="../../static/js/bootstrap.bundle.min.js"'),
        (r'src="[^"]*common\.js"', 'src="../../static/js/common.js"'),
        # 修复页面间的跳转链接 (简单处理，添加 ../c-client/ 前缀或根据目标调整)
        # 注意：这里需要更精细的正则来避免破坏已经是相对路径的链接
        # 暂只替换通用资源引用，页面跳转建议手动检查或统一使用 common.js 的 jumpTo
    ],
    'pages/b-admin': [
        (r'href="[^"]*bootstrap\.min\.css"', 'href="../../static/css/bootstrap.min.css"'),
        (r'href="[^"]*common\.css"', 'href="../../static/css/common.css"'),
        (r'src="[^"]*bootstrap\.bundle\.min\.js"', 'src="../../static/js/bootstrap.bundle.min.js"'),
        (r'src="[^"]*common\.js"', 'src="../../static/js/common.js"')
    ],
    'pages/common': [
        (r'href="[^"]*bootstrap\.min\.css"', 'href="../../static/css/bootstrap.min.css"'),
        (r'href="[^"]*common\.css"', 'href="../../static/css/common.css"')
    ]
}

def create_directories():
    """创建目标目录结构"""
    print(">>> 1. 开始创建目录结构...")
    for folder in DIR_STRUCTURE.keys():
        path = os.path.join(BASE_DIR, folder)
        if not os.path.exists(path):
            os.makedirs(path)
            print(f"    Created: {folder}")
        else:
            print(f"    Exists: {folder}")

def move_files():
    """移动文件到对应目录"""
    print("\n>>> 2. 开始移动文件...")
    
    for target_dir, files in DIR_STRUCTURE.items():
        for filename in files:
            src_path = os.path.join(BASE_DIR, filename)
            dst_path = os.path.join(BASE_DIR, target_dir, filename)
            
            if os.path.exists(src_path):
                # 如果目标文件已存在，先删除，确保覆盖
                if os.path.exists(dst_path):
                    os.remove(dst_path)
                
                shutil.move(src_path, dst_path)
                print(f"    Moved: {filename} -> {target_dir}/")
            else:
                # 检查是否已经在目标目录 (防止重复运行脚本报错)
                if os.path.exists(dst_path):
                    print(f"    Skipped (Already in target): {filename}")
                else:
                    print(f"    Warning: Source file not found: {filename}")

def update_resource_paths():
    """更新HTML文件中的资源引用路径"""
    print("\n>>> 3. 开始更新资源引用路径...")
    
    for dir_path, rules in REPLACE_RULES.items():
        full_dir_path = os.path.join(BASE_DIR, dir_path)
        if not os.path.exists(full_dir_path):
            continue
            
        for filename in os.listdir(full_dir_path):
            if not filename.endswith('.html'):
                continue
                
            file_path = os.path.join(full_dir_path, filename)
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            new_content = content
            # 1. 注入通用CSS/JS引用 (如果文件中没有)
            # 在 </head> 前插入 common.css
            if 'common.css' not in new_content:
                new_content = new_content.replace('</head>', '    <link href="../../static/css/common.css" rel="stylesheet">\n</head>')
            
            # 在 </body> 前插入 common.js
            if 'common.js' not in new_content:
                new_content = new_content.replace('</body>', '    <script src="../../static/js/common.js"></script>\n</body>')

            # 2. 应用正则替换规则 (修正 Bootstrap 等路径)
            # 注意：这里的替换比较暴力，实际项目中建议使用 HTML 解析库
            # 为了演示，我们将 CDN 链接替换为本地相对路径，或者修正已有的相对路径
            
            # 替换 Bootstrap CSS CDN
            new_content = re.sub(
                r'href="https://cdn\.jsdelivr\.net/npm/bootstrap@[^"]*bootstrap\.min\.css"', 
                'href="../../static/css/bootstrap.min.css"', 
                new_content
            )
            
            # 替换 Bootstrap JS CDN
            new_content = re.sub(
                r'src="https://cdn\.jsdelivr\.net/npm/bootstrap@[^"]*bootstrap\.bundle\.min\.js"', 
                'src="../../static/js/bootstrap.bundle.min.js"', 
                new_content
            )
            
            # 替换 Bootstrap Icons CDN (保留 CDN，因为本地没有下载字体文件)
            # new_content = new_content.replace(...) 

            # 3. 修正页面间的跳转链接 (简单修正 href="xxx.html")
            # C端页面跳转修正
            if 'c-client' in dir_path:
                # 替换跳转到 B端 的链接
                new_content = re.sub(r'href="admin_([a-z_]+)\.html"', r'href="../b-admin/admin_\1.html"', new_content)
                # 替换跳转到 错误页 的链接
                new_content = new_content.replace('href="error_page.html"', 'href="../common/error_page.html"')
            
            # B端页面跳转修正
            if 'b-admin' in dir_path:
                # 替换跳转到 C端 的链接
                new_content = new_content.replace('href="index.html"', 'href="../c-client/index.html"')
                new_content = new_content.replace('href="login.html"', 'href="../c-client/login.html"')

            if new_content != content:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"    Updated: {filename}")

def download_static_assets():
    """(模拟) 下载必要的静态资源"""
    print("\n>>> 4. 检查静态资源...")
    # 这里我们只创建空文件占位，提示用户下载
    # 实际脚本可以使用 requests 下载 bootstrap 文件
    
    css_dir = os.path.join(BASE_DIR, 'static/css')
    js_dir = os.path.join(BASE_DIR, 'static/js')
    
    bs_css = os.path.join(css_dir, 'bootstrap.min.css')
    bs_js = os.path.join(js_dir, 'bootstrap.bundle.min.js')
    
    if not os.path.exists(bs_css):
        print(f"    [提示] 请下载 Bootstrap CSS 到: {bs_css}")
        # 创建一个空文件避免报错
        with open(bs_css, 'w') as f: f.write('/* Bootstrap CSS Placeholder */')
        
    if not os.path.exists(bs_js):
        print(f"    [提示] 请下载 Bootstrap JS 到: {bs_js}")
        with open(bs_js, 'w') as f: f.write('/* Bootstrap JS Placeholder */')

if __name__ == '__main__':
    print("=== 开始执行项目结构整理脚本 ===")
    create_directories()
    move_files()
    update_resource_paths()
    download_static_assets()
    print("\n=== 整理完成！ ===")
    print("请运行以下命令启动服务测试：")
    print("python -m http.server 8000")
    print("访问入口: http://localhost:8000/pages/c-client/index.html")
