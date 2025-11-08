from datetime import datetime

from base.methods import register_method
from base.init import init
from base.scheduler import scheduler
from base.setting import *
from .daemon import FrpcDaemon


_frpc = FrpcDaemon()

@init
def _launch_frpc():
    _frpc.update()

# ISSUE: 不知道为啥有时候frpc会掉线，此时frpc日志和进程都没有异常，无法判断是否掉线了，所以只能定时重启了，避免一直掉线的情况
# 定时重启frpc，避免它自己管理不好重连让设备掉线之后一直连不上
@init
def _add_restart_frpc_job():
    time = datetime.strptime(config._CLOUD_FRPC_RESTART_TIME, '%H:%M:%S').time()
    scheduler.add_job(_frpc.restart, trigger='cron', id='cloud.restart_frpc', hour=time.hour, minute=time.minute, second=time.second)

@register_method('cloud_frpc_get_address')
def get_address():
    return _frpc.get_address()

@setting('cloud.frpc')
def _setting():
    return ModuleSetting({
            'enable': Scope(
                'CLOUD_FRPC_ENABLE',
                cast_bool
            ),
            'server_host': Scope(
                'CLOUD_FRPS_HOST',
            ),
            'server_port': Scope(
                'CLOUD_FRPS_PORT',
                int,
                validator=Validator.PORT
            ),
            'server_http_port': Scope(
                'CLOUD_FRPS_HTTP_PORT',
                int,
                validator=Validator.PORT
            ),
            'server_token': Scope(
                'CLOUD_FRPS_TOKEN',
                ignore_none=False
            ),
            'remote_ssh_port': Scope(
                'CLOUD_FRPC_SSH_PORT',
                int,
                validator=Validator.PORT,
                ignore_none=False
            )
        },
        setting_callback=lambda _: _frpc.update()
    )
