import importlib
import traceback
import sys
import base64
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Callable, Union, Iterator

from config import config
from base.mqtt import get_mqtt_service, on_connected
from base.logger import get_logger
from base.scheduler import scheduler
from .exception import IOTDeviceDriverCodeError


class IOTDeviceDriver:

    class _Reporter:
        def __init__(self, interval: float, device_id: str, channel: Union[str, Union[tuple[str], list[str]]], report_func: Callable[[], Union[Union[dict, bytes], tuple[Union[dict, bytes]]]]):
            assert (isinstance(interval, float) or isinstance(interval, int)) and interval > 0, 'interval参数必须为正数'
            assert isinstance(device_id, str) and device_id, 'device_id参数必须为字符串且不能为空'
            assert isinstance(channel, str) or (isinstance(channel, tuple) or isinstance(channel, list)) and len(channel) > 0, 'channel参数必须为非空字符串或非空字符串列表或非空字符串元组'
            
            self.interval = interval
            self.device_id = device_id
            self.channel = channel if isinstance(channel, str) else tuple(channel)
            self.report_func = report_func

            self._data = None
            self._status = {'ok': False, 'message': '尚未收集到任何数据'}

            self._id = f'iot.{self.device_id}.{self.channel if isinstance(self.channel, str) else "&".join(self.channel)}'
            assert scheduler.get_job(self._id) is None, f'设备{self.device_id}与通道{self.channel}的数据已被其他函数采集'

        def _report(self):
            try:
                self._data = self.report_func()
                if isinstance(self._data, tuple) and isinstance(self.channel, tuple):
                    if len(self._data) != len(self.channel):
                        raise ValueError(f'数据上报函数{self.report_func.__name__}的返回值数量[{len(self._data)}]与通道数[{len(self.channel)}]不对应')
                    for i in range(len(self._data)):
                        if not isinstance(self._data[i], dict) and not isinstance(self._data[i], bytes):
                            raise ValueError(f'上报函数{self.report_func.__name__}的第{i + 1}个返回值不是dict或bytes类型')
                        get_mqtt_service().report_iot_device(self.device_id, self.channel[i], self._data[i])
                else:
                    if not isinstance(self._data, dict) and not isinstance(self._data, bytes):
                        raise ValueError(f'上报函数{self.report_func.__name__}的返回值不是dict或bytes类型')
                    get_mqtt_service().report_iot_device(self.device_id, self.channel, self._data)
                self._status = {'ok': True, 'message': None}
            except Exception as e:
                self._status = {'ok': False, 'message': str(e)}

        def start(self):
            scheduler.add_job(self._report, 'interval', seconds=self.interval, id=self._id, max_instances=1)

        def stop(self):
            scheduler.remove_job(self._id)

        @property
        def status(self):
            return self._status
        
        @property
        def data(self):
            return self._data
        
        @staticmethod
        def _encode_data_to_json(data):
            if isinstance(data, dict):
                return data
            return str(base64.b64encode(data), 'utf8')
        
        @property
        def json_data(self):
            if self._data is None:
                return None
            if isinstance(self._data, tuple):
                return tuple(map(self._encode_data_to_json, self._data))
            return self._encode_data_to_json(self._data)

    class _Commander:
        def __init__(self, device_id: str, channel: str, command_func: Callable[[dict], None]):
            assert isinstance(device_id, str) and device_id, 'device_id参数必须为字符串且不能为空'
            assert isinstance(channel, str) and channel, 'channel参数必须为字符串且不能为空'

            self.device_id = device_id
            self.channel = channel
            self.command_func = command_func

            self._status = {'ok': True, 'message': None}
            self._unsubscribe = None

        def _command(self, data: dict):
            try:
                self.command_func(data)
                self._status = {'ok': True, 'message': None}
            except Exception as e:
                self._status = {'ok': False, 'message': str(e)}
            get_mqtt_service().report_iot_device_command_feedback(self.device_id, self.channel, self._status)

        def start(self):
            self._unsubscribe = get_mqtt_service().subscribe_iot_device_command(self.device_id, self.channel, self._command)

        def stop(self):
            self._unsubscribe()

        @property
        def status(self):
            return self._status
    
    def __init__(self):
        self._logger = get_logger('iot')
        self._enable = False
        self._driver_module = None
        self._reporters = []
        self._commanders = []
        self._init = None
        self._release = None

        @on_connected
        def resub():  # 当需要重新订阅时，重新调用所有cmder的订阅，不然不订阅
            if self.enable:
                for commander in self._commanders:
                    commander.start()

    def start(self):
        if self.enable:
            return
        
        if not config.IOT_DEVICE_DRIVER_CODE:
            raise IOTDeviceDriverCodeError(f'传感器驱动代码为空')

        # 初始化装饰器
        def init(func):
            self._init = func
            return func
        
        # 资源释放装饰器
        def release(func):
            self._release = func
            return func
        
        def report(interval: float, device_id: str, channel: Union[str, Iterator[str]]):
            def deco(func):
                self._reporters.append(self._Reporter(interval, device_id, channel, func))
                return func
            return deco
        
        def command(device_id: str, channel: str):
            def deco(func):
                self._commanders.append(self._Commander(device_id, channel, func))
                return func
            return deco

        # 加载驱动器代码
        # 为了把新的驱动器代码当成新的模块导入，这里做了一堆大胆的事情
        with TemporaryDirectory() as tmp_dir:
            # 建立临时目录，并将该目录放到python导入路径里，这样才能以模块的方式导入驱动代码
            sys.path.append(tmp_dir)
            # 将驱动代码临时存放到一个py文件里
            (Path(tmp_dir) / '_driver.py').write_text(config.IOT_DEVICE_DRIVER_CODE)

            # 这里获取需要注入到驱动器上下文的装饰器函数
            inject_funcs = {
                'init': init,
                'release': release,
                'report': report,
                'command': command,
            }
            # 因为__import__我试了没法通过指定globals和locals参数将装饰器函数注入到模块上下文中，给当前的globals()拓展新的字段也不管用，但是确实会将当前的globals传入新模块
            # 所以我修改内置函数字典，让新模块以用内置函数的方式用装饰器函数（上面那几个函数名称不在Python3.9内置函数中）
            __builtins__.update(inject_funcs)
            try:
                # 导入驱动器模块，导入的驱动器模块上下文中，内置函数里有上面的装饰器函数
                if not self._driver_module:
                    self._driver_module = importlib.import_module('_driver')
                else:
                    importlib.reload(self._driver_module)
            except:
                msg = f'传感器驱动代码导入失败，报错信息如下：\n{traceback.format_exc()}'
                self._logger.debug(msg)
                raise IOTDeviceDriverCodeError(msg) 
            finally:
                # 导入完后把sys.path改回去
                sys.path.remove(tmp_dir)
                # 再把内置函数改回去
                for func in inject_funcs:
                    __builtins__.pop(func)

        try:
            if self._init:
                self._init()
        except:
            msg = f'传感器驱动初始化失败，报错信息如下：\n{traceback.format_exc()}'
            self._logger.debug(msg)
            raise IOTDeviceDriverCodeError(msg) 

        for executer in self._reporters + self._commanders:
            executer.start()

        self._enable = True

        config.IOT_DEVICE_DRIVER_ENABLE = True
        config.save_config()

    def stop(self):
        if not self.enable:
            return
        
        for executer in self._reporters + self._commanders:
            executer.stop()
        
        try:
            if self._release:
                self._release()
        except:
            msg = f'传感器驱动释放资源失败，报错信息如下：\n{traceback.format_exc()}'
            self._logger.debug(msg)
            raise IOTDeviceDriverCodeError(msg)
        finally:
            self._reporters = []
            self._commanders = []
            self._init = None
            self._release = None
            self._enable = False

            config.IOT_DEVICE_DRIVER_ENABLE = False
            config.save_config()

    @property
    def code(self):
        return config.IOT_DEVICE_DRIVER_CODE
    
    @code.setter
    def code(self, new_code):
        config.IOT_DEVICE_DRIVER_CODE = new_code
        config.save_config()

    @property
    def enable(self) -> bool:
        return self._enable

    @property
    def status(self) -> dict:
        # 先构造下面这个格式的数据
        # {
        #   device1: {
        #       report: [{
        #           'channel': x, 
        #           'interval': x, 
        #           'data': x, 
        #           'status': x
        #       }, ...], 
        #       command: [{
        #           'channel': x, 
        #           'status': x
        #       }, ...],
        #   }, 
        #   device2: ...
        # }
        iot_devices = None
        def get_device(device_id):
            dev = iot_devices.get(device_id)
            if dev is None:
                dev = {'report': [], 'command': []}
                iot_devices[device_id] = dev
            return dev
        if self.enable:
            iot_devices = {}
            for reporter in self._reporters:
                report_list = get_device(reporter.device_id)['report']
                if isinstance(reporter.channel, str):
                    report_list.append({
                        'channel': reporter.channel, 
                        'interval': reporter.interval, 
                        'data': reporter.json_data, 
                        'status': reporter.status
                    })
                else:
                    json_data = reporter.json_data
                    for i in range(len(reporter.channel)):
                        report_list.append({
                            'channel': reporter.channel[i], 
                            'interval': reporter.interval, 
                            'data': json_data[i] if json_data is not None else None, 
                            'status': reporter.status
                        })
            for commander in self._commanders:
                commander_list = get_device(commander.device_id)['command']
                if isinstance(reporter.channel, str):
                    commander_list.append({
                        'channel': commander.channel, 
                        'status': commander.status
                    })
            iot_devices = [{'device_id': name, 'device_status': status} for name, status in iot_devices.items()]

        return iot_devices
    
    @property
    def json_data(self):
        if not self.enable:
            return None
        iot_devices = {}
        for reporter in self._reporters:
            device = iot_devices.get(reporter.device_id)
            if device is None:
                device = {}
                iot_devices[reporter.device_id] = device
            
            if isinstance(reporter.channel, str):
                device[reporter.channel] = reporter.json_data
            else:
                json_data = reporter.json_data
                for i in range(len(reporter.channel)):
                    device[reporter.channel[i]] = json_data[i]
        return iot_devices
