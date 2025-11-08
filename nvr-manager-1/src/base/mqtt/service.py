# 从cloud模块移动到base中的，因为mqtt是纯内部接口，被用的太多了，所以作为基础模块了
from config import config
from base.init import init
from base.logger import get_logger
from base.setting import *
from .platforms import MQTTService, ZZUIOTPlatformMQTTService, CustomPlatformMQTTService


def _create_mqtt_service() -> MQTTService:
    if config.CLOUD_MQTT_ZZUIOT_PLATFORM:
        return ZZUIOTPlatformMQTTService()
    return CustomPlatformMQTTService()

_mqtt_service: MQTTService = _create_mqtt_service()
_logger = get_logger('cloud.mqtt')

def get_mqtt_service():
    return _mqtt_service

def on_connected(func):
    MQTTService.on_connected(func)
    return func

# 不能再模块里调connect，不然数据库更新的时候也有mqtt的log...
@init
def _connect():
    if config.CLOUD_MQTT_ENABLE:
        _mqtt_service.connect()
    else:
        _logger.info('MQTT功能已关闭')

def _reconnect():
    global _mqtt_service
    _mqtt_service.disconnect()
    _mqtt_service = _create_mqtt_service()
    if config.CLOUD_MQTT_ENABLE:
        _mqtt_service.connect()

@setting('cloud.mqtt')
def _setting():
    return ModuleSetting({
            'enable': Scope(
                'CLOUD_MQTT_ENABLE',
                cast_bool
            ),
            'cloud_host': Scope(
                'CLOUD_MQTT_HOST',
            ),
            'cloud_port': Scope(
                'CLOUD_MQTT_PORT',
                int,
                validator=Validator.PORT
            ),
            'zzuiot_platform': Scope(
                'CLOUD_MQTT_ZZUIOT_PLATFORM',
                cast_bool
            ),
            'cloud_username': Scope(
                'CLOUD_MQTT_USERNAME'
            ),
            'cloud_password': Scope(
                'CLOUD_MQTT_PASSWORD'
            )
        },
        setting_callback=lambda _: _reconnect()
    )
