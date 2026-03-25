import os

from app import app


if __name__ == '__main__':
    port = int(os.getenv('PORT', '5000'))
    print('api_server.py 已收敛为主应用入口代理。')
    print(f'正在启动统一后端服务: http://127.0.0.1:{port}/api/...')
    app.run(debug=True, port=port)
