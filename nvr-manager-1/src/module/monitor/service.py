import os
import psutil
import time
import threading
import re
import requests

from config import config
from base.mqtt import get_mqtt_service
from base.scheduler import scheduler
from base.init import init
from base.logger import get_logger
from base.utils import get_disks, get_disk_usage, get_npu_utilization, get_soc_temperature
from base.setting import *


_logger = get_logger('monitor')

_upload_speed = 0.
_download_speed = 0.

def _convert_bytes(bytes: float) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024.0:
            return "{:.2f} {}".format(bytes, unit)
        bytes /= 1024.0
    return "{:.2f} PB".format(bytes)

@init
def _get_speed():
    def wrapper():
        global _upload_speed, _download_speed
        _logger.debug('流量统计线程已启动')
        while True:
            #获取上行流量和下行流量
            # 获取网络接口的统计信息
            net_io_counters1 = psutil.net_io_counters(pernic=True)
            # 等待1秒钟
            time.sleep(1)
            # 再次获取网络接口的统计信息
            net_io_counters2 = psutil.net_io_counters(pernic=True)

            # 计算每个接口的接收和发送速度
            upload_speed = 0.
            download_speed = 0.
            for interface in net_io_counters2:
                if interface in net_io_counters1:
                    upload_speed += net_io_counters2[interface].bytes_sent - net_io_counters1[interface].bytes_sent  #上行流量    
                    download_speed += net_io_counters2[interface].bytes_recv - net_io_counters1[interface].bytes_recv  #下行流量

            _upload_speed = f'{_convert_bytes(upload_speed)}/s'
            _download_speed = f'{_convert_bytes(download_speed)}/s'
    threading.Thread(target=wrapper, daemon=True).start()

@init
def add_report_job():
    scheduler.add_job(_report_to_cloud, 'interval', seconds=config.MONITOR_REPORT_INTERVAL_SECONDS, id='moniter.report')
    _logger.debug('监测信息上报定时任务已添加')

def _report_to_cloud():
    if get_mqtt_service().enbale:
        get_mqtt_service().report_monitor(get_system_info())

def get_system_info() -> dict:
    # 磁盘使用情况
    disks = [get_disk_usage(disk) for disk in get_disks()]
    total_space = _convert_bytes(sum([disk.total for disk in disks]))  # 总存储空间
    used_space =  _convert_bytes(sum([disk.used for disk in disks]))  # 已用存储空间

    # 整个系统的CPU使用率
    cpu_percent = psutil.cpu_percent()

    # 内存空间信息
    mem = psutil.virtual_memory()
    total_memory = _convert_bytes(mem.total)  # 总内存
    used_memory = _convert_bytes(mem.used)  # 已用内存
    memory_utilization = mem.percent  # 内存利用率

    # npu利用率
    npu_utilization = get_npu_utilization()
    
    # 中心/NPU温度
    center_temp, npu_temp = get_soc_temperature()

    return {
        'total_space': total_space,
        'used_space': used_space,
        'cpu_percent': '%.2f%%' % cpu_percent,
        'total_memory': total_memory,
        'used_memory': used_memory,
        'memory_utilization': '%.2f%%' % memory_utilization,
        'npu_utilization': '%.2f%%'% npu_utilization,
        'upload_speed': _upload_speed,
        'download_speed': _download_speed,
        'center_temp': f'{center_temp:.2f}℃',
        'npu_temp': f'{npu_temp:.2f}℃'
    }

@setting('monitor')
def _setting():
    return ModuleSetting({
            'report_interval': Scope(
                'MONITOR_REPORT_INTERVAL_SECONDS',
                int,
                validator=Validator.INT_RANGE(0)
            )
        },
        setting_callback=lambda _: scheduler.reschedule_job('moniter.report', trigger='interval', seconds=config.MONITOR_REPORT_INTERVAL_SECONDS)
    )
