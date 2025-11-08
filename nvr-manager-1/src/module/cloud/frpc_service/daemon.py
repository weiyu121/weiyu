import subprocess as sp
import threading
import re
import random
import io
from threading import Event
from enum import Enum

from config import config
from base.mqtt import get_mqtt_service
from base.logger import get_logger
from base.utils import exponential_backoff


_frpc_ini = '''
[common]
tls_enable = true
server_addr = {CLOUD_FRPS_HOST}
server_port = {CLOUD_FRPS_PORT}
{FRPS_TOKEN}

[{_DEVICE_ID}-http]
type = http
local_ip = 127.0.0.1
local_port = 80
subdomain = {_DEVICE_ID}

[{_DEVICE_ID}-ssh]
type = tcp
local_ip = 127.0.0.1
local_port = 22
remote_port = {REMOTE_PORT}'''

class FrpcDaemon:

    class FrpcSignal(Enum):
        RELOAD = 0
        SLEEP = 1

    def __init__(self):
        self._logger = get_logger('cloud.frpc')
        self._ssh_port = None  # ssh外网端口
        self._frpc = None  # frpc进程
        self._frpc_logs = None  # frpc日志
        self._frpc_daemon_enable = True
        self._frpc_daemon = None  # 守护进程

        # 状态
        self._wait4rerun = Event()  # 异常退出后等待一段时间在重启，如果reload就立刻重启

    def _load_ssh_port(self) -> int:
        return config.CLOUD_FRPC_SSH_PORT or random.randint(10000, 65535)
    
    def _close_frpc(self):
        if self._frpc and self._frpc.poll() is None:
            self._frpc.terminate()
        self._frpc = None
        self._frpc_logs = None

    def _generate_frpc_ini(self):
        with open(config._CLOUD_FRPC_CONFIG_PATH, 'w') as ini_file:
            ini_file.write(_frpc_ini.format(
                CLOUD_FRPS_HOST=config.CLOUD_FRPS_HOST, 
                CLOUD_FRPS_PORT=config.CLOUD_FRPS_PORT,
                FRPS_TOKEN=f'token = {config.CLOUD_FRPS_TOKEN}' if config.CLOUD_FRPS_TOKEN else '',
                _DEVICE_ID=config._DEVICE_ID,
                REMOTE_PORT=self._ssh_port))
    
    def _run_frpc(self):
        self._close_frpc()
        self._generate_frpc_ini()
        self._frpc_logs = ''
        self._frpc = frpc = sp.Popen(['frpc', '-c', config._CLOUD_FRPC_CONFIG_PATH], stdout=sp.PIPE, stderr=sp.STDOUT)
        outputs = io.TextIOWrapper(frpc.stdout)

        success_count = 0  # 穿透成功数量

        while frpc.poll() is None:
            line = outputs.readline().strip()
            if line:
                self._frpc_logs += f'{line}\n'
            '''日志：
            2023/04/19 15:12:23 [I] [service.go:299] [ee19dbd2912eddb9] login to server success, get run id [ee19dbd2912eddb9], server udp port [0]
            2023/04/19 15:12:23 [I] [proxy_manager.go:142] [ee19dbd2912eddb9] proxy added: [b33ad09f5553c30a-http b33ad09f5553c30a-ssh]
            2023/04/19 15:12:24 [I] [control.go:172] [ee19dbd2912eddb9] [b33ad09f5553c30a-http] start proxy success
            2023/04/19 15:12:24 [W] [control.go:170] [ee19dbd2912eddb9] [b33ad09f5553c30a-ssh] start error: port unavailable
            2023/04/19 15:12:57 [W] [control.go:170] [ee19dbd2912eddb9] [b33ad09f5553c30a-ssh] start error: port unavailable
            '''
            m = re.match(r'.*\[\w+-\w+\] (.*)', line)
            if m:
                if 'start proxy success' in m[1]:
                    success_count += 1
                elif 'start error' in m[1]:  # 穿透错误
                    if 'port unavailable' in m[1] or 'port already used' in m[1]:  # 端口问题
                        if config.CLOUD_FRPC_SSH_PORT is not None:
                            self._logger.info(f'SSH服务的远程frp服务器端口{self._ssh_port}被占用，正在等待重试...')
                            return FrpcDaemon.FrpcSignal.SLEEP
                        else:
                            self._logger.info(f'SSH服务的远程frp服务器端口{self._ssh_port}被占用，正在重新选择...')
                            # 进来就说明端口冲突了，改一下端口
                            self._ssh_port += 1
                            if self._ssh_port > 65535:
                                self._ssh_port = self._load_ssh_port()
                            return FrpcDaemon.FrpcSignal.RELOAD
                    return FrpcDaemon.FrpcSignal.SLEEP  # 其他问题

            if success_count == 2:
                # 两个个都启动成功了
                address = self.get_address()
                self._logger.info(f'[HTTP] -> {address["http"]}')
                self._logger.info(f'[SSH] -> {address["ssh"]}')
                def report_address(retry_interval):
                    if frpc.poll() is not None or not get_mqtt_service().enbale:  # 如果frpc都退出了，就不上报了，直接重新启动
                        return True
                    try:
                        get_mqtt_service().report_address()
                        self._logger.info('外网地址已上报')
                        return True
                    except:
                        self._logger.info(f'外网地址上报失败，等待{retry_interval}s重试...')
                        return False
                if get_mqtt_service().enbale:
                    exponential_backoff(report_address, 30)
                frpc.wait()
                return FrpcDaemon.FrpcSignal.RELOAD
        self._frpc_logs += f'{outputs.read()}'  # 把剩下的日志都读出来
        return FrpcDaemon.FrpcSignal.SLEEP

    def _daemon(self):
        delay = 10
        DELAY_MAX = 80
        while self._frpc_daemon_enable:
            signal = self._run_frpc()

            if signal == FrpcDaemon.FrpcSignal.RELOAD:
                delay = 10
            elif signal == FrpcDaemon.FrpcSignal.SLEEP:
                self._logger.warning(f'内网穿透失败，FRPC日志如下：\n{self._frpc_logs}')
                self._logger.info(f'frpc进程已退出，尝试{delay}s后重启...')
                self._wait4rerun.clear()
                self._wait4rerun.wait(delay)
                delay *= 2
                if delay > DELAY_MAX:
                    delay = DELAY_MAX

    def _start(self):
        if not self._frpc_daemon:
            self._frpc_daemon_enable = True
            self._frpc_daemon = threading.Thread(target=self._daemon, daemon=True)
            self._frpc_daemon.start()
            self._logger.info('FRPC内网穿透守护线程已开启')

    def _stop(self):
        if self._frpc_daemon:
            self._frpc_daemon_enable = False
            self._frpc_daemon = None
            self._logger.info('FRPC内网穿透守护线程已关闭')

    # (重新)加载配置
    def update(self):
        self._ssh_port = self._load_ssh_port()  # ssh外网端口
        self._close_frpc()  # 关FRPC
        # 设置是否启用的线程事件
        if config.CLOUD_FRPC_ENABLE:
            self._start()
        else:
            self._stop()
        # 如果现在正在等待重启，那么设置直接重启
        self._wait4rerun.set()
    
    # 重启frpc
    def restart(self):
        self._close_frpc()  # 关FRPC
        self._wait4rerun.set()
        self._logger.info('FRPC已重启')

    def get_address(self) -> dict:
        return {
            'http': f'http://{config._DEVICE_ID}.{config.CLOUD_FRPS_HOST}:{config.CLOUD_FRPS_HTTP_PORT}',
            'ssh': f'{config.CLOUD_FRPS_HOST}:{self._ssh_port}'
        }
