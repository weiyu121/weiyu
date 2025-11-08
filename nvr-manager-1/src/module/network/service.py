import re
import subprocess as sp
import io
from typing import Iterator
from time import sleep

from config import config
from base.mqtt import get_mqtt_service
from base.init import init
from base.logger import get_logger
from base.threadpool import thread_pool
from base.utils import netmask_to_cidr, cidr_to_netmask, get_iface_addr, check_ip_reachable
from base.scheduler import scheduler
from .reset_button_listener import ResetButtonListener
from .exception import (
    WIFIScanError,
    WIFIConnectError,
    WIFINotConnectError,
    WIFINotAvailable,
    HotspotNotAvailable,
    HotspotSetError,
    WireSwitchError,
    MobileNotAvailableError,
    MobileOpenError
)


_logger = get_logger('network')

def _run_with_stdout(cmds: list) -> sp.CompletedProcess:
    return sp.run(cmds, stdout=sp.PIPE, stderr=sp.STDOUT)

def _run(cmds: list) -> sp.CompletedProcess:
    return sp.run(cmds, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

def _set_connection_autoconnect(conn: str, autoconnect: bool):
    _run(['nmcli', 'c', 'mod', conn, 'connection.autoconnect', 'yes' if autoconnect else 'no'])

def _manipulate_connection(conn: str, enable: bool) -> bool:
    if _run(['nmcli', 'c', 'up' if enable else 'down', conn]).returncode != 0:
        return False
    _set_connection_autoconnect(conn, enable)
    return True



def _split_nmcli_output(stdout: bytes, by_line=False) -> Iterator:
    if by_line:
        return stdout.decode().removesuffix('\n').split('\n')
    return filter(None, (row.split(':') for row in stdout.decode().removesuffix('\n').split('\n') if row))

def _is_active(conn: str) -> bool:
    return _split_nmcli_output(_run_with_stdout(['nmcli', '-g', 'GENERAL.STATE', 'c', 'show', conn]).stdout, True)[0] == 'activated'

def _get_addr_and_netmask(addr_cidr: str) -> dict:
    addr, netmask = None, None
    if addr_cidr:
        addr, addr_cidr = addr_cidr.split('/')
        netmask = cidr_to_netmask(int(addr_cidr))
    return {
        'address': addr,
        'netmask': netmask
    }

# 设置连接的ipv4
def _set_connection_ipv4(conn: str, pars: dict):
    if 'ipv4' not in pars:
        return
    ipv4 = pars['ipv4']
    if ipv4 is None:
        _run(['nmcli', 'c', 'mod', conn, 'ipv4.method', 'auto', 'ipv4.addresses', '', 'ipv4.gateway', ''])
    else:
        _run(['nmcli', 'c', 'mod', conn, 'ipv4.method', 'manual', 'ipv4.addresses', f'{ipv4["address"]}/{netmask_to_cidr(ipv4["netmask"])}', 'ipv4.gateway', ipv4['gateway'], 'ipv4.dns', '114.114.114.114,180.76.76.76'])
    # 如果连接已经激活，那么为了应用设置，需要重新激活一次
    if _is_active(conn):
        _manipulate_connection(conn, True)

# 获取设置的网络信息{address, netmask, gateway, ipv4}
def _get_connection_net_info(conn: str) -> dict:
    device, method, addr_cidr, gateway = _split_nmcli_output(_run_with_stdout(['nmcli', '-g', 'connection.interface-name,ipv4.method,ipv4.addresses,ipv4.gateway', 'c', 'show', conn]).stdout, True)
    return {
        **(_get_iface_info(device) if _is_active(conn) else {'address': None, 'netmask': None, 'gateway': None}),
        'ipv4': {
            **_get_addr_and_netmask(addr_cidr),
            'gateway': gateway or None
        } if method != 'auto' else None
    }
# 用netiface获取ip、掩码和网关
def _get_iface_info(iface: str) -> dict:
    return get_iface_addr(True).get(iface) or {'address': None, 'netmask': None, 'gateway': None}

# 监测本地IP变化，有变化就重新上报
@init
def _monitor_iface_addrs():
    def monitor_iface_addrs():
        check_addr = get_iface_addr()
        if monitor_iface_addrs.local_addr != check_addr:
            # 如果ip有变化就调上报地址接口，上报地址需要外网ip，需要先获取外网ip
            try:
                get_mqtt_service().report_address()
                _logger.info(f'监测到网络变化，重新上报网络地址，当前网络地址为：{check_addr}')
            except:
                _logger.info(f'监测到网络变化，上报网络新地址[{check_addr}]失败')
            monitor_iface_addrs.local_addr = check_addr
    monitor_iface_addrs.local_addr = get_iface_addr()
    scheduler.add_job(monitor_iface_addrs, 'interval', seconds=config._NETWORK_ADDR_MONITOR_INTERVAL_SECONDS)
    _logger.debug('网络地址定时监测任务已添加')

######
# 热点
######
def _check_hotspot_available():
    if not config._WIRELESS_NETIFACE:
        raise HotspotNotAvailable('热点不可用，请检查无线网卡')

@init
def _ensure_hotspot_connection():
    if not config._WIRELESS_NETIFACE:
        _logger.info('未检测到无线网卡，WIFI连接与热点功能将无法使用')
        return
    res = _run(['nmcli', '-g', 'GENERAL.STATE', 'c', 'show', config._HOTSPOT_CONNECTION])  # 仅仅是为了确认连接是否创建了
    if res.returncode != 0:
        # 做这个判断是因为当ssid存在时，nmcli不会新建一个连接，会使用之前相同ssid的连接，导致指定名称的连接还是不存在
        # 所以在这里判断如果有ssid和默认的DEFAULT_SSID相同的连接，则直接给他id改了
        hotspot_conns = list(filter(lambda c: c[1] == 'ap' and c[2] == config._HOTSPOT_DEFAULT_SSID,
            map(lambda c: _split_nmcli_output(_run_with_stdout(['nmcli', '-g', 'connection.id,802-11-wireless.mode,802-11-wireless.ssid', 'c', 'show', c[0]]).stdout, True), 
                filter(lambda c: c[1] == '802-11-wireless', _split_nmcli_output(_run_with_stdout(['nmcli', '-g', 'NAME,TYPE', 'c']).stdout)))))
        if hotspot_conns:
            _run(['nmcli', 'c', 'mod', hotspot_conns[0][0], 'connection.id', config._HOTSPOT_CONNECTION, '802-11-wireless-security.psk', config._HOTSPOT_DEFAULT_PASSWORD])
            _logger.info(f'已更新热点连接，conn_id为[{config._HOTSPOT_CONNECTION}]，默认SSID为[{config._HOTSPOT_DEFAULT_SSID}]，密码为[{config._HOTSPOT_DEFAULT_PASSWORD}]')
        else:
            if _run(['nmcli', 'device', 'wifi', 'hotspot', 'con-name', config._HOTSPOT_CONNECTION, 'ifname', config._WIRELESS_NETIFACE, 'ssid', config._HOTSPOT_DEFAULT_SSID, 'password', config._HOTSPOT_DEFAULT_PASSWORD]).returncode:
                _logger.warning('热点创建失败，请查看板子是否支持无线网卡')
                return
            else:
                _manipulate_connection(config._HOTSPOT_CONNECTION, False)  # 创建后直接关了
                _logger.info(f'已创建热点连接，conn_id为[{config._HOTSPOT_CONNECTION}]，默认SSID为[{config._HOTSPOT_DEFAULT_SSID}]，密码为[{config._HOTSPOT_DEFAULT_PASSWORD}]')
    else:
        # 这个操作原因是，有可能网卡名称他会变...
        _run(['nmcli', 'c', 'mod', config._HOTSPOT_CONNECTION, 'connection.interface-name', config._WIRELESS_NETIFACE])
    if config.HOTSPOT_ENABLE:
        _logger.info('系统即将自启热点')
    _manipulate_connection(config._HOTSPOT_CONNECTION, config.HOTSPOT_ENABLE)

def get_hotspot_status() -> dict:
    _check_hotspot_available()
    # res = ['<ssid>', '<device>', (, 'activated')]
    res = _split_nmcli_output(_run_with_stdout(['nmcli', '-s', '-g', '802-11-wireless.ssid,connection.interface-name,ipv4.addresses,802-11-wireless-security.psk,GENERAL.STATE', 'c', 'show', config._HOTSPOT_CONNECTION]).stdout, True)
    
    # 没打开热点就不返回系统的addr，因为当前网卡连接的可鞥是wifi，那么就会返回wifi的信息
    enable = len(res) > 4
    addr_info = _get_iface_info(res[1]) if enable else {'address': None, 'netmask': None}
    addr_info.pop('gateway', None)

    return {
        'ssid': res[0],  # res[0]=ssid
        'enable': enable,  # 如果有的话res[3]=activated，否则就没有res[3]，即查不到GENERAL.STATE这个属性，会使元素少一项
        'ipv4': _get_addr_and_netmask(res[2]) if res[2] else None,
        'password': res[3],
        **addr_info
    }

def switch_hotspot():
    _check_hotspot_available()
    on_off = not _is_active(config._HOTSPOT_CONNECTION)
    _manipulate_connection(config._HOTSPOT_CONNECTION, on_off)
    config.HOTSPOT_ENABLE = on_off
    config.save_config()

def set_hotspot(pars: dict):
    _check_hotspot_available()

    if 'ssid' not in pars \
        and 'password' not in pars \
        and 'ipv4' not in pars:
        return

    try:
        if _run(['nmcli', 'c', 'mod', config._HOTSPOT_CONNECTION] \
            + (['802-11-wireless.ssid', pars['ssid']] if 'ssid' in pars else []) \
            + (['802-11-wireless-security.psk', pars['password']] if 'password' in pars else []) \
            + (['ipv4.addresses', f'{pars["ipv4"]["address"]}/{netmask_to_cidr(pars["ipv4"]["netmask"])}' if pars["ipv4"] is not None else ''] if 'ipv4' in pars else [])
        ).returncode != 0:
            raise HotspotSetError('热点设置失败，热点名称或者密码格式不符合规范')
        if get_hotspot_status()['enable']:
            _manipulate_connection(config._HOTSPOT_CONNECTION, True)
    except KeyError as e:
        raise HotspotSetError(f'热点设置失败，传入的参数[ipv4.{str(e)}]是未知参数')

def _reset_and_open_hotspot():
    try:
        set_hotspot({
            'ssid': config._HOTSPOT_DEFAULT_SSID,
            'password': config._HOTSPOT_DEFAULT_PASSWORD,
            'ipv4': None
        })
        _manipulate_connection(config._HOTSPOT_CONNECTION, True)
        _logger.info('已重置热点配置')
    except:
        pass

@init
def _register_reset_hotspot():
    ResetButtonListener(_reset_and_open_hotspot)

######
# WIFI
######
def _check_wifi_available():
    if not config._WIRELESS_NETIFACE:
        raise WIFINotAvailable('WIFI不可用，请检查无线网卡')

def scan_wifi() -> list[dict]:
    _check_wifi_available()
    if _is_active(config._HOTSPOT_CONNECTION):
        raise WIFIScanError('热点已开启，请关闭热点后再扫描WIFI')
    
    res = _run_with_stdout(['nmcli', '-g', 'SSID,CHAN,RATE,SIGNAL,SECURITY', 'dev', 'wifi', 'list', '--rescan', 'yes'])
    if res.returncode != 0:
        raise WIFIScanError('获取可用WIFI失败')
    
    return list(filter(
        lambda wifi: wifi['ssid'],
        map(
            lambda wifi: {
                'ssid': wifi[0],
                'channel': wifi[1],
                'rate': wifi[2],
                'rssi': wifi[3],
                'security': wifi[4]
            },
            _split_nmcli_output(res.stdout)
        )
    ))

def connect_wifi(pars: dict):
    _check_wifi_available()
    # NOTE: 当热点打开时是无法连接wifi的，因此如果用户真的想要连接WIFI，那这里就先把热点关了
    try:
        if get_hotspot_status()['enable']:
            switch_hotspot()
            # NOTE: 关闭热点后在新板子上不能立刻连接WIFI，需要等待一段时间，但是旧板子可以，所以为了兼容这里等4s再继续跑
            sleep(4)
    except Exception as e:
        raise WIFIConnectError(f'WIFI连接失败，错误原因为：{e}')

    try:
        res = _run_with_stdout(['nmcli', 'dev', 'wifi', 'c', pars['ssid'], 'password', pars['password']])
    except KeyError as e:
        raise WIFIConnectError(f'请传入字段{str(e)}')
    
    # HACK: “保存上一次wifi信息”
    save_last_wifi(pars)

    msg = res.stdout.decode().strip()

    if 'successfully activated' not in msg:
        if 'Secrets were required, but not provided.' in msg:
            raise WIFIConnectError('WIFI连接失败，密码错误')
        else:
            raise WIFIConnectError(f'WIFI连接失败，错误原因为：{msg.removeprefix("Error: ")}')
    _set_connection_autoconnect(pars['ssid'], True)

def disconnect_wifi():
    _check_wifi_available()
    _manipulate_connection(get_wifi_status()['ssid'], False)

def get_wifi_status() -> dict:
    _check_wifi_available()
    active_wifi = list(filter(
        lambda wifi: wifi[-1] == 'yes', 
        _split_nmcli_output(_run_with_stdout(['nmcli', '-g', 'SSID,CHAN,RATE,SIGNAL,SECURITY,ACTIVE', 'dev', 'wifi', 'list', '--rescan', 'no']).stdout)
    ))
    if not active_wifi:
        raise WIFINotConnectError('当前未连接WIFI')
    active_wifi = active_wifi[0]  # 一般来说应该不存在连接2个wifi的情况吧...

    # 判断这个连接是热点还是wifi，如果是热点说明没连wifi
    if active_wifi[0] == get_hotspot_status()['ssid']:
        raise WIFINotConnectError('当前未连接WIFI')

    return {
        'ssid': active_wifi[0],
        'channel': active_wifi[1],
        'rate': active_wifi[2],
        'rssi': active_wifi[3],
        'security': active_wifi[4],
        **_get_connection_net_info(active_wifi[0])
    }

def set_wifi(pars: dict):
    _check_wifi_available()
    _set_connection_ipv4(get_wifi_status()['ssid'], pars)

# NOTE:下面俩接口的作用有点抽象，保存/获取上一次的wifi，点击“保存”和“连接”按钮都会保存。目的是回显上一次的密码。
def save_last_wifi(pars: dict):
    try:
        config.LAST_WIFI_SSID = pars['ssid']
        config.LAST_WIFI_PASSWORD = pars['password']
        config.save_config()
    except:
        pass

def get_last_wifi() -> dict:
    return {
        'ssid': config.LAST_WIFI_SSID,
        'password': config.LAST_WIFI_PASSWORD
    }

######
# 有线
######
@init
def _ensure_wired_connection():
    res = _run(['nmcli', '-g', 'GENERAL.STATE', 'c', 'show', config._WIRED_CONNECTION])  # 仅仅是为了确认连接是否创建了
    if res.returncode != 0:
        # 这里需要找个方法获取系统里的有线连接，然后给他id改了，方便我们自己管理
        wired_conn = None

        # 先拿到所有的有线连接
        wired_conns = list(filter(
            lambda conn: conn[1] == '802-3-ethernet', 
            _split_nmcli_output(_run_with_stdout(['nmcli', '-g', 'NAME,TYPE,STATE', 'c']).stdout)  # 这里不能同时获取DEVICE，因为没有启用连接的时候DEVICE参数为空
        ))
        if not wired_conns:
            _logger.fatal('无法使用nmcli获取系统中已有的有线连接')
            exit(1)
        
        if active_conns := list(filter(lambda conn: conn[2] == 'activated', wired_conns)):
            wired_conn = active_conns[0][0]  # 先用已激活的连接
        else:
            # 然后优先选Wired connection 1
            if 'Wired connection 1' in wired_conns:
                wired_conn = 'Wired connection 1'
            # 否则随机筛一个
            else:
                # 筛选出其中一个有线连接
                # 先筛可用的有线网卡设备，设备类型必须为ethernet
                devs = [dev[0] for dev in filter(lambda dev: dev[1] == 'ethernet', _split_nmcli_output(_run_with_stdout(['nmcli', '-g', 'DEVICE,TYPE', 'dev']).stdout))]
                if not devs:
                    _logger.fatal('系统中没有获取到可用的有线网卡')
                    exit(1)
                
                # 然后遍历连接，找一个有线网卡可用的连接，当作唯一的有线连接用
                for conn in wired_conns:
                    if tuple(_split_nmcli_output(_run_with_stdout(['nmcli', '-g', 'connection.interface-name', 'c', 'show', conn[0]]).stdout, True))[0] in devs:
                        wired_conn = conn[0]
                        break
        if not wired_conn:
            _logger.fatal('无法使用nmcli获取系统中已有且可用的有线连接')
            exit(1)

        # 给有线连接改个名
        _run(['nmcli', 'c', 'mod', wired_conn, 'connection.id', config._WIRED_CONNECTION])
        _logger.info(f'已获取并修改有线连接[{config._WIRED_CONNECTION}]')

def get_wire_status() -> dict:
    return {
        'enable': _is_active(config._WIRED_CONNECTION),
        **_get_connection_net_info(config._WIRED_CONNECTION)
    }

def switch_wire():
    if get_wire_status()['enable']:
        _manipulate_connection(config._WIRED_CONNECTION, False)
    else:
        if not _manipulate_connection(config._WIRED_CONNECTION, True):
            raise WireSwitchError('有线连接开启失败，请查看网线是否连接')

def set_wire(pars: dict):
    _set_connection_ipv4(config._WIRED_CONNECTION, pars)

######
# 移动
######
_mobile_status = {
    'enable': False,
    'address': None,
    'dns': None
}

def _check_mobile_available():
    if config.is_atlas200idka2():
        raise MobileNotAvailableError('移动网络功能暂不支持该平台')

def get_mobile_status() -> dict:
    _check_mobile_available()

    iface = get_iface_addr()
    _mobile_status['enable'] = 'ppp0' in iface
    if not _mobile_status['enable']:
        _mobile_status.update({
            'address': None,
            'dns': None
        })
    elif not _mobile_status['address']:
        _mobile_status['address'] = iface['ppp0']
    return _mobile_status

def _open_mobile():
    _check_mobile_available()
    # 他这个东西很神奇，nd5g这个进程会调用pppd进程，导致的结果就是nd5g会退出，但pppd拨号进程需要一直运行
    # 两个进程的输出都会重定向到Pipe中，但nd5g在调用pppd后自己就退出了，所以没办法根据nd5g的运行情况和返回码来判断是否拨号成功，只能看日志了
    nd5g = sp.Popen(['nd5g'], stdout=sp.PIPE, stderr=sp.STDOUT) 

    # 用正则匹配pppd输出的方法来获取必要信息
    for line in io.TextIOWrapper(nd5g.stdout):
        if (m:= re.match(r'local  IP address (\d+.\d+.\d+.\d+)\t*', line)) is not None:  # 最上面是地址
            _mobile_status['address'] = m[1]
        elif (m:= re.match(r'remote IP address (\d+.\d+.\d+.\d+)\t*', line)) is not None:  # 其次是网关
            _mobile_status['gateway'] = m[1]
        elif (m:= re.match(r'primary   DNS address (\d+.\d+.\d+.\d+)\t*', line)) is not None:  # 其次是主dns
            _mobile_status['dns'] = [m[1]]
        elif (m:= re.match(r'secondary DNS address (\d+.\d+.\d+.\d+)\t*', line)) is not None:  # 再其次是副dns
            _mobile_status['dns'].append(m[1])
            _mobile_status['enable'] = True
            break
        elif 'No SIM card!' in line:  # 好像不管是因为什么，nd5g拨号失败都会输出这个，哪怕是因为执行命令没有权限的情况也是
            raise MobileOpenError('移动网络开启失败，请检查sim卡是否插好')
    
    # 要是开完之后没有ppp0连接，那就是开失败了
    if not get_mobile_status()['enable']:
        raise MobileOpenError('移动网络开启失败，请检查sim卡是否插好')
    
    # 添加默认网关
    sp.run(['route', 'add', 'default', 'gw',_mobile_status['gateway']], stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
    config.MOBILE_NETWORK_ENABLE = True  # 直接用config模块保存移动网络开关状态
    config.save_config()

def _close_mobile():
    _check_mobile_available()
    _run(['nd5g', 'stop'])
    config.MOBILE_NETWORK_ENABLE = False  # 直接用config模块保存移动网络开关状态
    config.save_config()

def switch_mobile():
    _check_mobile_available()
    if get_mobile_status()['enable']:
        _close_mobile()
    else:
        _open_mobile()

# 判断是否需要自启动移动网络
@init
def _auto_switch_mobile():
    try:
        _check_mobile_available()
        if config.MOBILE_NETWORK_ENABLE:
            def init_open_mobile():
                try:
                    _logger.info('正在尝试自启动移动网络...')
                    _open_mobile()
                except MobileOpenError:
                    _logger.warning('移动网络自启动失败')
                    _close_mobile()
            thread_pool.submit(init_open_mobile)
    except Exception as e:
        _logger.warning(str(e))

def check_internet() -> bool:
    return any(map(check_ip_reachable, ('baidu.com', 'gitee.com')))
