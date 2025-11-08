from typing import Any

from config import config
from base.init import init
from base.ext import db
from base.logger import get_logger
from .driver import IOTDeviceDriver


_logger = get_logger('iot')
_driver = IOTDeviceDriver()

@init
def auto_enable_driver():
    if config.IOT_DEVICE_DRIVER_ENABLE:
        try:
            _driver.start()
        except Exception as e:
            _logger.warning(f'自启动IOT驱动器失败，原因为：\n{str(e)}')

def enable_driver():
    _driver.start()

def stop_driver():
    _driver.stop()

def get_driver() -> dict:
    return {
        'enable': _driver.enable,
        'driver_code': _driver.code,
        'status': _driver.status
    }

def set_driver(args: dict):
    enable = _driver.enable
    if code := args.get('driver_code'):
        if code != _driver.code:
            _driver.code = code
            _driver.stop()  # 只有先停掉才会重新加载代码

    if enable:
        _driver.start()
    else:
        _driver.stop()

def get_json_data() -> dict:
    return _driver.json_data