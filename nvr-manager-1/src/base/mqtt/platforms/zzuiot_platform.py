import json
from typing import Callable, Union

from config import config
from base.methods import methods
from base.utils import get_iface_addr
from .mqtt_service import MQTTService


class ZZUIOTPlatformMQTTService(MQTTService):

    def __init__(self):
        super().__init__()
        self._cloud_client = None  # 临时使用，用于从平台获取DeviceSecret
        self._device_secret = None

        # 为啥会有个这个东西呢，是因为订阅那个topic里需要device_secret，而这个东西它需要一段时间才能获取，不然topic里那个字段就被格式化成None了
        self._delay_description = {}

    def connect(self):
        super().connect()
        def on_cloud_connected(client, userdata, flags, rc):
            self._logger.info("成功连接物联网平台，设备登录中...")
            def on_message(client, userdata, msg):
                self._device_secret = json.loads(msg.payload.decode())['deviceSecret']
                self._cloud_client.disconnect()
                self._cloud_client = None
                self._login(
                    config.CLOUD_MQTT_HOST,
                    config.CLOUD_MQTT_PORT,
                    f'device-{config._DEVICE_ID}',
                    config._DEVICE_ID, 
                    self._device_secret,
                )
                for topic_fmt, callback in self._delay_description.items():
                    # 将所有callback全部替换成unsub函数
                    self._delay_description[topic_fmt] = self._subscribe(topic_fmt.format(DEVICE_SECRET=self._device_secret), callback)
                # self._update_setting_topic = f'cmd/{self._device_secret}/updateSetting'
            # 发送话题进行登录以获取密码
            client.on_message = on_message
            client.subscribe(f"/ext/register/{config._DEVICE_ID}")

        self._cloud_client = self._login_mqtt(
            config.CLOUD_MQTT_HOST, 
            config.CLOUD_MQTT_PORT,
            f'register-{config._DEVICE_ID}',
            'pevr6zh1',
            'f44dc2de78e78e225eda11e46f2f81e402c0a1e9',
            on_cloud_connected
        )
    
    def disconnect(self):
        super().disconnect()
        if self._cloud_client:
            self._cloud_client.disconnect()
        self._cloud_client = self._device_secret = None
    
    def _on_message(self, msg, callback):
        try:
            data = json.loads(msg.payload.decode())['data']
        except:
            self._logger.info(f'从[{msg.topic}]接收到非json格式数据，将其忽略')
        callback(data)

    # 等到获取DeviceSecret后再订阅，如果已经获取了，则立刻订阅
    def _delay_subscribe(self, topic_fmt: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        if self._device_secret is not None:
            return self._subscribe(topic_fmt.format(DEVICE_SECRET=self._device_secret), callback)
        else:
            self._delay_description[topic_fmt] = callback
            def unsubscribe():
                if self._device_secret is not None:
                    self._delay_description[topic_fmt]()  # 已经超过sub过了，现在里面被替换成了unsub函数
                else:
                    self._delay_description.pop(topic_fmt)  # 还没正式sub，直接不让正式sub即可
            return unsubscribe

    def _report(self, topic: str, data: Union[dict, bytes], ignore_error=False):
        if self._device_secret is None and not ignore_error:
            raise ConnectionError('尚未登录物联网平台，请稍后...')
        self._publish(topic, json.dumps({
            'id': config._DEVICE_ID,
            'data': data
        }) if isinstance(data, dict) else data, ignore_error)
    
    def report_alert(self, alert: dict):
        alert['information'] = json.dumps(alert['information'], ensure_ascii=False)
        self._report(f'g_event/{self._device_secret}/alert/{alert["device_id"]}', alert, True)

    def report_monitor(self, status: dict):
        self._report(f'event/{self._device_secret}/state', status, True)

    def report_address(self):
        self._report(f'event/{self._device_secret}/address', {
            **methods.cloud_frpc_get_address(),
            'local': json.dumps(get_iface_addr())
        })

    def report_iot_device(self, device_id: str, channel: str, data: Union[dict, bytes]):
        self._report(f'g_event/{self._device_secret}/{channel}/{device_id}', data, True)

    def subscribe_iot_device_command(self, device_id: str, channel: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        return self._delay_subscribe(f'g_cmd/{"{DEVICE_SECRET}"}/{channel}/{device_id}', callback)

    def report_iot_device_command_feedback(self, device_id: str, channel: str, feedback: dict):
        self._report(f'g_event/{self._device_secret}/{channel}Feedback/{device_id}', feedback, True)

    def report_syslog(self, syslog: str):
        self._report(f'event/{self._device_secret}/syslog', {'log': syslog}, True)

    def subscribe_update_setting(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        return self._delay_subscribe(f'cmd/{"{DEVICE_SECRET}"}/updateSetting', callback)

    def report_update_setting_feedback(self, feedback: dict):
        feedback['setting'] = json.dumps(feedback['setting'], ensure_ascii=False)
        self._report(f'event/{self._device_secret}/updateSettingFeedback', feedback, True)

    def subscribe_upgrade_system(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        return self._delay_subscribe(f'cmd/{"{DEVICE_SECRET}"}/upgradeSystem', callback)

    def report_upgrade_system_feedback(self, feedback: dict):
        self._report(f'event/{self._device_secret}/upgradeSystemFeedback', feedback, True)

    def report_433_data(self, device_id: str, data: dict):
        self._report(f'g_event/{self._device_secret}/subdata/{device_id}', data, True)

    def subscribe_433_command(self, device_id: str, channel: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        return self._delay_subscribe(f'g_cmd/{"{DEVICE_SECRET}"}/{channel}/{device_id}', callback)

    def report_433_command_feedback(self, device_id: str, channel: str, feedback: dict):
        self._report(f'g_event/{self._device_secret}/{channel}Feedback/{device_id}', feedback, True)
