import subprocess as sp
import threading
import time

from config import config
from base.app import app
from base.ext import db
from base.init import init
from base.logger import get_logger
from base.methods import register_method
from base.setting import *
from ..device.model.device import Device
from ..device.exception import DeviceNotExistsError
from .exception import (
    FowardError,
    FowardAlreadyEnabled
)


_logger = get_logger('cloud.forward')
_forwarders = {}

class _ForwardDeamon:
    def __init__(self, device_id: str):
        self._process = None
        self._running = True  # 就是守护线程要不要继续跑了
        self._restart = False  # 手动重启时，把这个指定为True，他就不等待直接重启进程了
        self._device_id = device_id

        def daemon():
            while self._running:
                with app.app_context():
                    device = Device.query.get(self._device_id)
                self._process = sp.Popen([
                    'ffmpeg',
                    '-rtsp_transport', 'tcp',
                    '-i', device.source,
                    '-an',
                    '-c:v', 'h264_rkmpp',
                    '-b:v', config._CLOUD_FORWARD_CBR,
                    '-f', 'flv',
                    f'rtmp://{config.CLOUD_FORWARD_HOST}:{config.CLOUD_FORWARD_PORT}/live/{device.id}'
                ], stdout=sp.DEVNULL, stderr=sp.DEVNULL)

                self._process.wait()

                if not self._running:
                    return

                # 这里判断是不是异常退出
                if self._restart:
                    self._restart = False
                    _logger.debug(f'监控[{device_id}]修改配置，转发推流任务重启......')
                else:
                    _logger.info(f'监控[{device_id}]转发推流任务异常退出，将在{config._CLOUD_FORWARD_RESTART_INTERVAL_SECONDS}秒后重启......')
                    time.sleep(config._CLOUD_FORWARD_RESTART_INTERVAL_SECONDS)
        
        threading.Thread(target=daemon, daemon=True).start()

    def restart(self):
        self._restart = True
        if self._process:
            self._process.terminate()

    def stop(self):
        self._running = False
        if self._process:
            self._process.terminate()

@init
def _launch_forwarders():
    for device in Device.query.filter(Device.enable_forward == True).all():
        _forwarders[device.id] = _ForwardDeamon(device.id)
        _logger.debug(f'{device.id}的推流转发已启动')

def start_forward(device_id: str):
    device = Device.query.get(device_id)
    if not device:
        raise DeviceNotExistsError(f'推流转发开启失败，监控设备{device_id}不存在')
    
    if device.enable_forward:
        raise FowardAlreadyEnabled(f'监控设备{device_id}已开启推流转发')

    if config.is_atlas200idka2():
        raise FowardError('该平台暂不支持云端推流转发')
    
    device.enable_forward = True
    db.session.commit()
    _forwarders[device_id] = _ForwardDeamon(device_id)

@register_method('cloud_forward_stop_forward')
def stop_forward(device_id: str):
    device = Device.query.get(device_id)
    if not device:
        raise DeviceNotExistsError(f'推流转发关闭失败，监控设备{device_id}不存在')
    
    if not device.enable_forward:
        raise FowardAlreadyEnabled(f'监控设备{device_id}未开启推流转发')
    
    device.enable_forward = False
    db.session.commit()
    _forwarders[device_id].stop()
    _forwarders.pop(device_id, None)

@setting('cloud.forward')
def _setting():
    return ModuleSetting({
            'cloud_host': Scope(
                'CLOUD_FORWARD_HOST',
            ),
            'cloud_port': Scope(
                'CLOUD_FORWARD_PORT',
                int,
                validator=Validator.PORT
            )
        },
        setting_callback=lambda _: [forwarder.restart() for forwarder in _forwarders.values()]  # 云端地址都变了，肯定得给转发器都重启了
    )
