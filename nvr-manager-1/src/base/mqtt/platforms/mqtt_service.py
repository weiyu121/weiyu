import json
from typing import Callable, Union
from paho.mqtt.client import Client

from config import config
from base.logger import get_logger


class MQTTService:

    _logger = get_logger('cloud.mqtt')
    _on_connected_callbacks = []

    @staticmethod
    def _login_mqtt(
        mqtt_host: str,
        mqtt_port: int,
        client_id: str, 
        username: str, 
        password: str, 
        on_succeess: Callable=None, 
        on_failure: Callable=None
    ) -> Client:
        # on_connect会在第一次连接到mqtt时调用，之后如果掉线重连也不会再次调用
        # 有一种情况on_connect会被反复调用，就是物联网平台那边断开连接（因为一个设备不能登录多次不然会被挤掉）后这边重新登录，此时连接上时会重新调用on_connect
        # 总之如果需要订阅，那么需要用这个函数回调
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                if on_succeess:
                    on_succeess(client, userdata, flags, rc)
            else:
                err_msg = ('协议版本错误', '无效的客户端标识', '服务器无法使用', '错误的用户名或密码', '未经授权')
                MQTTService._logger.warning(f"MQTT连接失败，原因为{err_msg[rc - 1]}，尝试重连...")
                if on_failure:
                    on_failure(client, userdata, flags, rc)
        client = Client(client_id)
        client.username_pw_set(username, password)
        client.on_connect = on_connect
        client.reconnect_delay_set(min_delay=1, max_delay=60)
        client.connect_async(mqtt_host, mqtt_port)
        client.loop_start()
        return client

    def __init__(self) -> None:
        self._client = None
        self._subscriptions = {}

    # 登录通讯用的mqtt_client
    def _login(
        self, 
        mqtt_host: str,
        mqtt_port: int,
        client_id: str, 
        username: str, 
        password: str
    ):
        def on_succeess(*_):
            self._logger.info(f"登陆MQTT平台成功")
            self._client.on_message = self.__on_message
            # 有个小问题，初始化时调完这个之后，订阅会被调两次，不过因为键时topic两次都一样，就忽略这个问题
            for on_connected_callback in self._on_connected_callbacks:
                on_connected_callback()
            for topic in self._subscriptions:
                self._client.subscribe(topic)
        
        self._client = self._login_mqtt(
            mqtt_host,
            mqtt_port,
            client_id,
            username,
            password,
            on_succeess
        )

    # 断线情况调用publish也会返回成功，但是数据实际没有发出去，数据会被缓存等到上线时一起发出去
    # 发布话题
    def _publish(self, topic: str, data: Union[dict, bytes], ignore_error=False):
        if not self._client:
            if not ignore_error:
                raise ConnectionError('与云端通信失败，尚未登陆到设备')
            return
        
        if self._client.publish(topic, json.dumps(data, ensure_ascii=False) if type(data) == dict else data)[0] != 0 and not ignore_error:
            raise ConnectionError('数据上报失败，无法与云端通信')

    # topic不支持通配符
    # 返回一个取消订阅函数，调用该函数即可取消订阅
    def _subscribe(self, topic: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        if topic.endswith('#'):
            raise ValueError('topic不支持通配符')
        self._subscriptions[topic] = callback
        if self._client and self._client.is_connected():
            self._client.subscribe(topic)
        
        def unsubscribe():
            self._subscriptions.pop(topic)
            if self._client:
                self._client.unsubscribe(topic)
        return unsubscribe
    
    def __on_message(self, client, userdata, msg):
        callback = self._subscriptions.get(msg.topic)
        if callback:
            self._on_message(msg, callback)
    
    # 当接收到订阅时，会调用该函数将msg和callback传进去交给子类进一步处理
    def _on_message(self, msg, callback):
        raise NotImplementedError()
    
    @property
    def enbale(self) -> bool:
        return config.CLOUD_MQTT_ENABLE
    
    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected()
    
    # 这东西当装饰器用
    @staticmethod
    def on_connected(func):
        MQTTService._on_connected_callbacks.append(func)
        return func

    def connect(self):
        self.disconnect()

    def disconnect(self):
        if self._client:
            self._client.disconnect()

    def report_alert(self, alert: dict):
        raise NotImplementedError()

    def report_monitor(self, status: dict):
        raise NotImplementedError()

    def report_address(self):
        raise NotImplementedError()

    def report_iot_device(self, device_id: str, channel: str, data: Union[dict, bytes]):
        raise NotImplementedError()

    def subscribe_iot_device_command(self, device_id: str, channel: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        raise NotImplementedError()
    
    def report_iot_device_command_feedback(self, device_id: str, channel: str, feedback: dict):
        raise NotImplementedError()

    def report_syslog(self, log: str):
        raise NotImplementedError()

    def subscribe_update_setting(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        raise NotImplementedError()

    def report_update_setting_feedback(self, feedback: dict):
        raise NotImplementedError()

    def subscribe_upgrade_system(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        raise NotImplementedError()

    def report_upgrade_system_feedback(self, feedback: dict):
        raise NotImplementedError()

    def report_433_data(self, device_id: str, data: dict):
        raise NotImplementedError()
    
    def subscribe_433_command(self, device_id: str, channel: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        raise NotImplementedError()

    def report_433_command_feedback(self, device_id: str, channel: str, feedback: dict):
        raise NotImplementedError()