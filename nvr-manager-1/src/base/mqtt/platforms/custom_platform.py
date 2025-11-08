import json
from typing import Callable, Union

from config import config
from base.methods import methods
from base.utils import get_iface_addr
from .mqtt_service import MQTTService


class CustomPlatformMQTTService(MQTTService):

    def __init__(self):
        super().__init__()

    def connect(self):
        super().connect()
        self._login(
            config.CLOUD_MQTT_HOST, 
            config.CLOUD_MQTT_PORT,
            config._DEVICE_ID,
            config.CLOUD_MQTT_USERNAME,
            config.CLOUD_MQTT_PASSWORD
        )

    def _on_message(self, msg, callback):
        try:
            data = json.loads(msg.payload.decode())
        except:
            self._logger.info(f'从[{msg.topic}]接收到非json格式数据，将其忽略')
        callback(data)
    
    def report_alert(self, alert: dict):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/alert', alert, True)

    def report_monitor(self, status: dict):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/state', status, True)

    def report_address(self):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/address',{
            **methods.cloud_frpc_get_address(),
            'local': get_iface_addr()
        })

    def report_iot_device(self, device_id: str, channel: str, data: Union[dict, bytes]):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/iot/{device_id}/report/{channel}', data, True)

    def subscribe_iot_device_command(self, device_id: str, channel: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        return self._subscribe(f'zzu/aiedge/{config._DEVICE_ID}/iot/{device_id}/command/{channel}', callback)

    def report_iot_device_command_feedback(self, device_id: str, channel: str, feedback: dict):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/iot/{device_id}/command/{channel}/feedback', feedback, True)

    def report_syslog(self, syslog: str):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/syslog', {'log': syslog}, True)

    def subscribe_update_setting(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        return self._subscribe(f'zzu/aiedge/{config._DEVICE_ID}/updateSetting', callback)

    def report_update_setting_feedback(self, feedback: dict):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/updateSetting/feedback', feedback, True)

    def subscribe_upgrade_system(self, callback: Callable[[dict], None]) -> Callable[[], None]:
        return self._subscribe(f'zzu/aiedge/{config._DEVICE_ID}/upgradeSystem', callback)

    def report_upgrade_system_feedback(self, feedback: dict):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/upgradeSystem/feedback', feedback, True)

    def report_433_data(self, device_id: str, data: dict):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/iot433/{device_id}/report/subdata', data, True)

    def subscribe_433_command(self, device_id: str, channel: str, callback: Callable[[dict], None]) -> Callable[[], None]:
        return self._subscribe(f'zzu/aiedge/{config._DEVICE_ID}/iot433/{device_id}/command/{channel}', callback)

    def report_433_command_feedback(self, device_id: str, channel: str, feedback: dict):
        self._publish(f'zzu/aiedge/{config._DEVICE_ID}/iot433/{device_id}/command/{channel}/feedback', feedback, True)