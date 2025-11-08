import traceback
import os
import logging
from glob import glob
from importlib import import_module

from config import config
from base.exception import SystemInternalError, NVRManagerError
from base.app import app, register_all_blueprints, make_nvr_manager_response
from base.ext import db
from base.init import init_all
from base.scheduler import scheduler
from base.logger import get_logger, init_logger


logger = get_logger('server')

@app.route('/')
def hello():
    return '你好，这里是NVR-Manger，你已成功访问管理接口'

@app.errorhandler(Exception)
def handle_error(e):
    error_msg = f'系统内部错误[{str(e)}]：\n{traceback.format_exc()}'
    logger.error(error_msg)
    return make_nvr_manager_response(error=SystemInternalError(error_msg))

@app.errorhandler(NVRManagerError)
def handle_error(e):
    return make_nvr_manager_response(error=e)

def import_views():
    views = glob('**/view.py', recursive=True)  # 切换为开发配置后，他会改变工作空间，此时再查找模块就是在部署环境中找了，换言之，此时跑的就不是开发代码了，所以要在这里就查找
    # 动态导入所有view.py，这样就不用每个模块写一堆__init__了
    for view_path in views:
        view_path = view_path.replace('.py', '').replace('/', '.')
        import_module(view_path[view_path.find('module'):])

def server_init():
    init_logger()
    logger.info('程序启动...')
    # 注册所有视图
    register_all_blueprints()

    with app.app_context():
        db.create_all()
        init_all()
        scheduler.start() 

import_views()

# 进行服务的初始化，创建表并初始化所有的子模块
if __name__ == '__main__':
    os.chdir('/usr/local/nvr-manager')
    config._LOGGER_LEVEL = logging.DEBUG

server_init()

if __name__ == '__main__':
    app.run('0.0.0.0', config._SERVER_PORT)