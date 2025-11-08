import time
import os
import sys
import threading
import psutil
import netifaces
import re
import subprocess as sp
from pathlib import Path
from typing import Optional, Iterable
from contextlib import contextmanager
from datetime import datetime, timedelta

from config import config
from base.threadpool import wait_muti_run
from base.app import app
from base.ext import BaseModel, db


# 指数退避执行某个函数
# 当函数func返回False或者None时，认为函数运行失败会重试运行该函数，会将下一次重试的间隔传给函数，方便打印日志
def exponential_backoff(func: callable, max_interval: Optional[int]=120):
    interval = 1
    while not func(interval):
        time.sleep(interval)
        interval = min(interval*2, max_interval)

# 获取所有的磁盘的挂载路径
def get_disks() -> list[str]:
    return [disk.mountpoint for disk in psutil.disk_partitions()]

# 获取某个文件的所在磁盘
def get_disk_path(file_path) -> str:
    disks = get_disks()
    match_str_count = [len(disk) if file_path.find(disk) == 0 else -1 for disk in disks]
    return disks[match_str_count.index(max(match_str_count))]

# 输入该磁盘的根路径或者该磁盘中某个文件的路径，返回该磁盘的sdiskusage
def get_disk_usage(disk_or_file_path: str):
    return psutil.disk_usage(get_disk_path(disk_or_file_path))

# 丢弃stderr的输出，可以实现丢弃opencv的错误信息，原理是把stderr的文件描述符重定向到devnull里，代码执行完后再给原来的描述符换回去
# FIXME: 但要注意，web的log也是stderr输出的，在这个环境管理器的上下文里，web的日志不会输出，解决思路：让web的logger输出到stdout上
_devnull = open(os.devnull, 'wb')
@contextmanager
def suppress_stderr():
    original_stderr_fd = sys.stderr.fileno()
    saved_stderr_fd = os.dup(original_stderr_fd)
    os.dup2(_devnull.fileno(), original_stderr_fd)
    yield
    os.dup2(saved_stderr_fd, original_stderr_fd)
    os.close(saved_stderr_fd)

def check_ip_reachable(ip: str) -> bool:
    return os.system(f'ping -w 1 {ip} >/dev/null 2>&1') == 0

# 检测ip是否能ping通，开个线程隔若干秒测试一次，可用于判断在线状态
class IpOnlineMonitor:

    class _Monitor:
        def __init__(self, ip: str):
            self.ip = ip
            self.online = check_ip_reachable(ip)

    def __init__(self, interval_seconds: Optional[int]=10):
        '''interval_seconds: 测试完一轮后，下一次测试要sleep几秒'''
        self._monitors: dict[str, IpOnlineMonitor._Monitor] = {}
        self._alive = True
        self._interval_sec = interval_seconds

        def monitor_online_thread():
            def test_online(monitor: IpOnlineMonitor._Monitor):
                monitor.online = check_ip_reachable(monitor.ip)

            while self._alive:
                wait_muti_run(test_online, self._monitors.values())
                time.sleep(self._interval_sec)
        threading.Thread(target=monitor_online_thread, daemon=True).start()

    def update(self, name: str, ip: str) -> bool:
        '''添加监控，该接口调用会立刻检查是否能ping通，所以可能会卡1s，返回是否在线，'''
        monitor = IpOnlineMonitor._Monitor(ip)
        self._monitors[name] = monitor
        return monitor.online
    
    def delete(self, name: str):
        self._monitors.pop(name, None)

    def is_online(self, name: str) -> bool:
        return self._monitors[name].online

    def is_watching(self, name: str) -> bool:
        return name in self._monitors

    def stop(self):
        self._alive = False
        del self._monitors

    def set_interval_time(self, sec: int):
        self._interval_sec = sec

# 实现
def cleanup_by_expire_day(
        expire_days: int,  # 超过多少天的数据会被列入清理范围
        table: BaseModel,  # 清理哪个表
        time_scope: str,  # 这个表记录时间的字段是啥
        file_scopes: Optional[Iterable[str]]=None,  # 这个表包含的文件字段是什么，列出来之后可以连带着关联的文件一起删除
        *filter_conds  # 过滤表时可以加入自定义的过滤条件
    ) -> tuple[int, int]:  # 返回删除的记录条数、删除的文件数
    '''定时清理功能，超过一定天数的记录连带着关联的文件都会被删除
    @expire_days: 超过多少天的数据会被列入清理范围
    @table: 清理哪个表
    @time_scope: 这个表记录时间的字段是啥
    @file_scopes: 这个表包含的文件字段是什么，列出来之后可以连带着关联的文件一起删除
    @filter_conds: 过滤表时可以加入自定义的过滤条件，满足条件的数据才会被删除

    -> 返回删除的记录条数、删除的文件数
    '''
    if expire_days <= 0:
        return 0, 0
    with app.app_context():
        items = table.query.filter(
            # 删除N天前 的所有记录
            getattr(table, time_scope) < datetime.now() - timedelta(expire_days),  # 今天-N天前的日期
            *filter_conds
        ).all()
        
        files = set()
        files.update((getattr(item, file_scope) for item in items for file_scope in file_scopes))
        removed_file_count = 0
        for file in files:
            if file and os.path.exists(file):
                os.remove(file)
                removed_file_count += 1
        for item in items:
            db.session.delete(item)
        db.session.commit()
    return len(items), removed_file_count

# 同一个表并发的时候记得加个锁，不然多次操作在删除前会查询到同一批记录
def scroll_insert(
        new: BaseModel,
        table: BaseModel,
        file_scope: str,
        orderby_scope: Optional[str]='id',  # 这个表包含的文件字段是什么，列出来之后可以连带着关联的文件一起删除
        *filter_conds
    ) -> tuple[bool, int]:
    '''数据库滚动插入记录，插入一条记录需要预留出这条记录所关联的文件大小的空缺才能插入，也就是需要删除一条或多条记录及其所关联的文件
    @new: 新纪录对象
    @table: 表的类
    @file_scope: 文件字段是什么，只支持一个字段
    @orderby_scope: 怎么才能知道哪些数据较早，哪些数据较晚，默认按照id排序，也可以改成时间
    @filter_conds: 过滤表时可以加入自定义的过滤条件，满足条件的数据才参与滚动删除

    -> 返回是否成功滚动删除并插入新数据、删除的数据条数/文件数
    '''
    file_path = getattr(new, file_scope)
    disk_path = get_disk_path(file_path)
    size = os.path.getsize(file_path)
    deletions = []
    page = None
    while size > 0:
        # 一次查少点，可能一条记录就满足了，没必要查那么多
        if page is None:
            query = table.query.order_by(getattr(table, orderby_scope))
            if filter_conds:
                query.filter(*filter_conds)
            page = query.paginate(page=1, per_page=20)
        elif page.has_next:
            page = page.next()
        else:
            return False, 0
        
        # 看这一页需要删几个
        for item in page.items:
            # 需要判断这条记录是不是在这个磁盘上，sql语句不好判断，就在这里判断了
            item_file_path = getattr(item, file_scope)
            if get_disk_path(item_file_path) == disk_path and os.path.exists(item_file_path):
                size -= os.path.getsize(item_file_path)
                deletions.append(item)
                if size <= 0:
                    break
    
    for item in deletions:
        db.session.delete(item)
        item_file_path = getattr(item, file_scope)
        if os.path.exists(item_file_path):
            os.remove(item_file_path)
    
    db.session.add(new)
    db.session.commit()
    return True, len(deletions)

# detail为True时返回IP、掩码、网关等信息
def get_iface_addr(detail=False) -> dict:
    gateways = {}
    for iface in (netifaces.gateways().get(netifaces.AF_INET) or []):
        gateways[iface[1]] = iface[0]
    
    nets = {}
    for iface_name in netifaces.interfaces():
        ifaddr = netifaces.ifaddresses(iface_name)
        if iface_name != 'lo' and netifaces.AF_INET in ifaddr and ifaddr[netifaces.AF_INET]:
            if detail:
                info = ifaddr[netifaces.AF_INET][0]
                nets[iface_name] = {
                    'address': info['addr'],
                    'netmask': info['netmask'],
                    'gateway': gateways[iface_name] if iface_name in gateways else None
                }
            else:
                nets[iface_name] = ifaddr[netifaces.AF_INET][0]['addr']
    return nets

def get_npu_utilization() -> float:
    if config.is_rk3588():
        cores = re.findall(r"\d+(?=%)", Path('/sys/kernel/debug/rknpu/load').read_text())
        return sum(map(int, cores)) / len(cores)
    elif config.is_atlas200idka2():
        return float(re.search(
            r'Aicore Usage Rate\(%\)\s*:\s*(\w+)',
            sp.run(
                ['npu-smi', 'info', '-i', '0', '-t', 'usages'], 
                stdout=sp.PIPE, 
                stderr=sp.STDOUT).stdout.decode()
        )[1])
    return 0.

# 返回芯片中心温度、npu温度
def get_soc_temperature() -> tuple[float, float]:
    if config.is_rk3588():
        def get_rk3588_temperature(zone: int) -> float:
            return float(Path(f'/sys/class/thermal/thermal_zone{zone}/temp').read_text().strip()) / 1000
        return get_rk3588_temperature(0), get_rk3588_temperature(6)
    return 0., 0.

def netmask_to_cidr(netmask: str) -> int:
    return sum(map(lambda x: bin(int(x)).count('1'), netmask.split('.')))

def cidr_to_netmask(cidr: int) -> str:
    mask = (0xffffffff >> (32 - cidr)) << (32 - cidr)
    return '.'.join((str((0xff000000 & mask) >> 24), str((0x00ff0000 & mask) >> 16), str((0x0000ff00 & mask) >> 8), str((0x000000ff & mask))))