import logging
import json
import re
import os
import base64
import subprocess as sp
from datetime import timedelta
from threading import Lock
from pathlib import Path
from netifaces import interfaces


_config_file_lock = Lock()

# FLASK配置
class FlaskConfig:
    # db配置
    SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://nvr-manager:000000@localhost/nvr-manager'

    PERMANENT_SESSION_LIFETIME = timedelta(days=1)
    SECRET_KEY = str(base64.b64encode(os.urandom(32)), 'utf8')

# 1. 配置必须全大写
# 2. 可以修改的配置不以_开头
class Config:
    # 系统版本，每次提交代码都改一下
    _VERSION = 'v1.9.0-dev-20240726'

    # 开发板平台的类型
    _PLATFORM = None

    # 配置存储文件位置
    _CONFIG_PATH = '/usr/local/nvr-manager/config.json'
    
    ALERT_IMAGE_DIR = 'data/alert_images'
    # 每天什么时候执行报警清理
    ALERT_CLEANUP_TIME = '04:00:00'
    # 清理几天前的报警，设为0表示不清理
    ALERT_CLEANUP_DAYS = 30
    # 当存放报警的磁盘剩余空间达到阈值后是否滚动删除该磁盘上较早的报警
    ALERT_SCROLL_DELETION = True
    # 磁盘阈值（剩多少字节）
    _ALERT_SCROLL_DELETION_THRESHHOLD = 3 * 1024 * 1024 * 1024

    AIPROJECT_DIR = 'data/ai_projects'
    AITASK_LOG_DIR = 'data/aitask_logs'

    # 每个进程存满多少日志就清空一次，这也决定了接口返回的日志数据最大量
    _AITASK_LOG_MAX_BYTES = 1024 * 1024  # 1MB
    # AI任务异常退出后等待重启的时间间隔(秒)
    _AITASK_RESTART_INTERVAL_SECONDS = 10

    # 服务器端口是什么，必须与实际服务端口对应，用于创建AI任务时填充报警地址
    _SERVER_PORT = 5000

    # 每隔多少秒扫描一次摄像头
    CAMERA_DISCOVERY_INTERVAL_SECONDS = 60
    # 每隔多少秒测试一下摄像头是否联通，不可小于1秒
    _CAMERA_ONLINE_STATUS_TEST_INTERVAL = 10

    # 每隔多少秒测试一下海康NVR是否联通，不可小于1秒
    _HIKNVR_ONLINE_STATUS_TEST_INTERVAL = 10

    _LOGGER_LEVEL = logging.INFO

    # 设备ID，使用CPU序列号
    _DEVICE_ID = None

    CLOUD_MQTT_ENABLE = True
    CLOUD_MQTT_HOST = 'mqtt.yun.gdatacloud.com'
    CLOUD_MQTT_PORT = 31854
    # 选择mqtt平台
    CLOUD_MQTT_ZZUIOT_PLATFORM = True
    # 账号密码仅当ZZUIOT_PLATFORM为False时有效
    CLOUD_MQTT_USERNAME = None
    CLOUD_MQTT_PASSWORD = None

    # 内网穿透参数
    CLOUD_FRPC_ENABLE = True
    _CLOUD_FRPC_CONFIG_PATH = 'frpc.ini'
    CLOUD_FRPS_HOST = 'penetrate.cn'  # 必须填域名，并且该frp服务器需要配置http以及域名相关配置
    CLOUD_FRPS_PORT = 7000
    # 下面的参数是为了生成url
    CLOUD_FRPS_HTTP_PORT = 8080  # frp服务器http代理端口
    CLOUD_FRPS_TOKEN = '11d6d3b38cb8e05e006cec88e992c237d327c3e0'

    # 远程SSH端口，设为None表示自动搜索可用端口，否则将只使用指定端口
    CLOUD_FRPC_SSH_PORT = None
    # 每天重启frpc（具体问题见cloud.frpc内的ISSUE）
    _CLOUD_FRPC_RESTART_TIME = '04:00:00'

    # 推流转发
    CLOUD_FORWARD_HOST = 'rtmp.video.gdatacloud.com'
    CLOUD_FORWARD_PORT = 30312
    _CLOUD_FORWARD_CBR = '512k'  # 定码率
    # 异常退出后等待重启的时间间隔(秒)
    _CLOUD_FORWARD_RESTART_INTERVAL_SECONDS = 10

    # 监测信息间隔多少秒上报一次
    MONITOR_REPORT_INTERVAL_SECONDS = 30

    _DVR_SRS_COFIG_PATH = '/usr/local/srs/conf/srs.conf'
    # DVR回放存储路径
    DVR_PLAYBACK_DIR = 'data/dvr_playbacks'
    # DVR回放录制片段时长（大致时长，具体会有些偏差）
    DVR_PLAYBACK_SEGMENT_DURATION = 30
    # 每天什么时候执行回放清理
    DVR_PLAYBACK_CLEANUP_TIME = '04:00:00'
    # 清理几天前的回放，设为0表示不清理
    DVR_PLAYBACK_CLEANUP_DAYS = 7
    # 当存放回放的磁盘剩余空间达到阈值后是否滚动删除该磁盘上较早的回放
    DVR_PLAYBACK_SCROLL_DELETION = True
    # 磁盘阈值（剩多少字节）
    _DVR_PLAYBACK_SCROLL_DELETION_THRESHHOLD = 3 * 1024 * 1024 * 1024

    # 升级日志
    _SYSTEM_UPGRADE_LOG_PATH = 'upgrade.log'
    # 系统标题
    SYSTEM_TITLE = '智能安全预警系统'

    _AUTH_SUPER_PASSWORD = '11d6d3b38cb8e05e006cec88e992c237d327c3e0'
    _AUTH_PASSWORD_PATH = 'auth.password'

    # 网络配置
    _WIRELESS_NETIFACE = None
    # 热点连接名
    _HOTSPOT_CONNECTION = 'NVR-Manager-Hotspot'
    # 有线连接名
    _WIRED_CONNECTION = 'NVR-Manager-Wire'

    # 网络IP变化检测间隔
    _NETWORK_ADDR_MONITOR_INTERVAL_SECONDS = 30

    # 热点默认SSID和密码
    _HOTSPOT_DEFAULT_SSID = 'AI-{DEVICE_ID}'
    _HOTSPOT_DEFAULT_PASSWORD = '123456789'
    # 当这个为True时，启动系统时会尝试自启动热点，无需修改，该参数由/network/hotspot管理
    HOTSPOT_ENABLE = False
    # 当这个为True时，启动系统时会尝试自启动移动网络，无需修改，该参数由/network/mobile管理
    MOBILE_NETWORK_ENABLE = False
    # 上一次保存/连接的wifi名称与密码，该参数由/network/wifi管理
    LAST_WIFI_SSID = None
    LAST_WIFI_PASSWORD = None

    # 物联网设备驱动代码
    IOT_DEVICE_DRIVER_CODE = None
    # 物联网设备驱动是否开启
    IOT_DEVICE_DRIVER_ENABLE = False

    # 433设备上报频率
    _IOT433_REPORT_DATA_INTERVAL = 10

    # 重置按钮的GPIO索引
    _RESET_BUTTON_GPIO_INDEX = 139
    # 重置按钮按住生效的时间
    _RESET_BUTTON_PRESSING_SECONDS = 5

    def __init__(self):
        # 判断平台类型
        try:
            if Path('/sys/kernel/debug/rknpu').exists():
                self._PLATFORM = 'rk3588'
            elif not os.system('type npu-smi 1>&2 > /dev/null'):
                self._PLATFORM = 'atlas200idka2'
            else:
                raise RuntimeError('目前只支持rk3588和atlas200idka2平台，其他暂不支持')
        except PermissionError:
            raise RuntimeError('请以root身份运行程序')

        if os.path.exists(self._CONFIG_PATH):
            self.load_config()

        if self.is_rk3588():
            with open('/proc/cpuinfo', 'r') as f_cpuinfo:
                line = f_cpuinfo.readline()
                while line:
                    m = re.search(r'\s*Serial\s*:\s*(\w+)\s*', line)
                    if m:
                        self._DEVICE_ID = m[1]
                        break
                    line = f_cpuinfo.readline()
            if 'wlan0' in interfaces():
                self._WIRELESS_NETIFACE = 'wlan0'
        elif self.is_atlas200idka2():
            if m:= re.search(
                r'Product Name\s*:\s*(\w+)\s*Serial Number\s*:\s*(\w+)\s*', 
                sp.run(['npu-smi', 'info', '-i', '0', '-l'], 
                    stdout=sp.PIPE, 
                    stderr=sp.STDOUT).stdout.decode()
                ):
                self._DEVICE_ID = m[1] + m[2]
            else:
                raise RuntimeError('无法获取Atlas200I DK A2开发版的0号NPU序列号')
            
            # 先找wlan0在不在，不在的话再查wlx啥的
            if 'wlan0' in interfaces():
                self._WIRELESS_NETIFACE = 'wlan0'
            else:
                for netiface in interfaces():
                    if netiface.startswith('wlx'):
                        self._WIRELESS_NETIFACE = netiface
                        break
        
        if not self._DEVICE_ID:
            raise RuntimeError('未获取到CPU序列号作为设备ID')

        self._HOTSPOT_DEFAULT_SSID = self._HOTSPOT_DEFAULT_SSID.format(DEVICE_ID=self._DEVICE_ID)

    def load_config(self):
        with open(self._CONFIG_PATH, 'r') as cf:
            config = json.load(cf)
        for k, v in config.items():
            setattr(self, k, v)

    def save_config(self):
        with _config_file_lock:
            with open(self._CONFIG_PATH, 'w') as cf:
                json.dump({
                    k: getattr(self, k) \
                        for k in filter(lambda k: not k.startswith('_') and k.isupper(), dir(config))
                }, cf)
    
    def is_atlas200idka2(self):
        return self._PLATFORM == 'atlas200idka2'
    
    def is_rk3588(self):
        return self._PLATFORM == 'rk3588'

config = Config()