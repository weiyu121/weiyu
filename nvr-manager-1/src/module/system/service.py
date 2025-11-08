import os
import re
import sys
import threading
import tempfile
import subprocess as sp
import time
import requests
from datetime import datetime
from pathlib import Path

from config import config
from base.setting import *
from base.utils import get_iface_addr
from base.init import init
from base.mqtt import get_mqtt_service, on_connected
from base.ext import db
from base.methods import methods_noerror
from module.device.model.device import Device
from module.alert.model.alert import Alert
from module.dvr.model.playback import Playback
from .exception import (
    SystemInUpgrading,
    SetSystemTimeError,
    SystemUpgradeCheckError,
    SystemAlreadyUptodate,
    SystemGetUpgradeLog
)


_git_url = 'git@gitee.com:research-group-2022/nvr-manager.git'
# 用这个记录升级状态与给用户看的日志，具体的日志扔文件里
_upgrade_status = {
    'upgrading': False,
    'log': ''
}

def check_upgrade() -> dict:
    # 获得一个按字典序排列的tag名称列表
    res = sp.run(['git', 'ls-remote', '--refs', '--tags', '-q', _git_url], stdout=sp.PIPE, stderr=sp.STDOUT)
    if res.returncode != 0:
        raise SystemUpgradeCheckError('检查更新失败，请检查网络')
    # 处理成tag名称的列表
    tag_list = [re.search(r'refs/tags/(.*)$', tag)[1] for tag in res.stdout.decode().strip().split('\n') if tag]
    # 按照主版本号、功能版本号、修订版本号三级排序
    tag_list.sort(key=lambda x: [int(v) for v in re.search('^[vV](\d+.\d+.\d+)', x)[1].split('.')], reverse=True)
    if tag_list and config._VERSION != tag_list[0]:  # 如果自己的版本不是最新版本的话
        return {
            'has_new_version': True,
            'new_version': tag_list[0]
        }
    return {
        'has_new_version': False,
        'new_version': None
    }

def system_upgrade(args: dict):
    if _upgrade_status['upgrading']:
        raise SystemInUpgrading('系统正在更新，请等待...')

    _upgrade_status['upgrading'] = True

    branch = args.get('branch')
    # 如果是主分支则检查更新，否则不查直接升级
    if not branch or branch == 'master':
        if not check_upgrade()['has_new_version']:
            raise SystemAlreadyUptodate('系统已经是最新版本')

    def upgrade():
        with open(Path(config._SYSTEM_UPGRADE_LOG_PATH), 'w') as log_f:
            def log_write(msg):
                log_f.write(msg)
                log_f.flush()
            with tempfile.TemporaryDirectory() as project_dir:
                git_cmd = ['git', 'clone', _git_url]
                _upgrade_status['log'] = '# 开始更新，更新中可以离开此页面操作其他功能。\n'
                if branch and branch != 'master':
                    _upgrade_status['log'] += f'# 程序即将升级为开发版本[{branch}]...\n'
                    log_write(f'# 已切换到分支：{branch}\n')
                    git_cmd += ['-b', branch]

                _upgrade_status['log'] += '# 正在下载安装包，请稍后...\n'
                log_write('# 正在下载最新程序...\n')
                if sp.run(git_cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL, cwd=project_dir).returncode != 0:
                    _upgrade_status['log'] += '# 下载失败，请检查网络连接是否正常！'
                    _upgrade_status['upgrading'] = False
                    log_write('# 拉取失败，请检查网络以及拉取参数是否正确')
                    return

                _upgrade_status['log'] += '# 即将更新完成，准备重启系统。'
                if sp.run([
                    sys.executable, 
                    str(Path(__file__).parent / 'script' / 'upgrade.py'),
                ], cwd=str(Path(project_dir, 'nvr-manager')), stdout=log_f, stderr=log_f).returncode != 0:
                    _upgrade_status['log'] += '# 更新失败，请联系技术人员查看。'
                    log_write('# 更新失败！')
                _upgrade_status['upgrading'] = False
    
    threading.Thread(target=upgrade, daemon=True).start()

def get_upgrade_log():
    try:
        return requests.get(
            'http://aigateway.penetrate.cn:32091/Upgrade_Log.json', 
            headers={'User-Agent': 'Apifox/1.0.0 (https://apifox.com)'}  # UA不能为requests库，不然不让获取，随便设置一个就行
        ).json()
    except json.decoder.JSONDecodeError:
        raise SystemGetUpgradeLog(f'获取升级日志失败，更新日志解析异常')
    except Exception as e:
        raise SystemGetUpgradeLog(f'获取升级日志失败，错误异常为:{e}')
    
def get_modelhub_list():
    try:
        response = requests.get(
            'http://aimodel.yun.gdatacloud.com:20082/api/modelServe/aiModel?chipModel=rk3588&edgePlatform=rockchip&runEnvironment=1.4.0', 
        ).json()
        print(response)
        return {'model_list':response.get('content', [])}
    except json.decoder.JSONDecodeError:
        raise SystemGetUpgradeLog(f'获取AI应用列表异常')
    except Exception as e:
        raise SystemGetUpgradeLog(f'获取AI应用列表异常:{e}')

@init
@on_connected
def subscribe_system_upgrade():
    def mqtt_system_upgrade(args: dict):
        try:
            system_upgrade(args)
            def continue_report_status():
                while True:
                    status = get_system_upgrade_status()
                    get_mqtt_service().report_upgrade_system_feedback(status)
                    if not status['upgrading']:
                        return
                    time.sleep(5)
            threading.Thread(target=continue_report_status, daemon=True).start()
        except Exception as e:
            get_mqtt_service().report_upgrade_system_feedback({
                'upgrading': False,
                'log': str(e)
            })

    get_mqtt_service().subscribe_upgrade_system(mqtt_system_upgrade)

def get_system_upgrade_status() -> dict:
    return _upgrade_status

def get_system_info() -> dict:
    info = {
        'version': config._VERSION,
        'device_id': config._DEVICE_ID,
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    info['local_addrs'] = [{'iface': iface, 'addr': addr} for iface, addr in get_iface_addr().items()]
    return info

def set_system_time(args: dict):
    apply_time = args.get('time')

    if apply_time:
        if os.system(f'date -s "{apply_time}" >/dev/null 2>&1') != 0:
            raise SetSystemTimeError('时间格式传入错误，请按照[年-月-日 时:分:秒]的格式传入')
    else:
        if os.system('ntpdate ntp.aliyun.com >/dev/null 2>&1') != 0:
            raise SetSystemTimeError('自动同步时间失败，服务器源为ntp.aliyun.com，请检查网络能否进行NTP时间校准')
    
    if os.system('hwclock -w >/dev/null 2>&1') != 0:
        os.system(f'hwclock -s')
        raise SetSystemTimeError('系统时间设置失败，设定的系统时间与真实时间误差过大')

def reboot():
    os.system('reboot')

def reset_data():
    # 删除设备
    for device in Device.query.all():
        methods_noerror.device_delete_device(device)

    # 删除告警信息
    for alert in Alert.query.all():
        try:
            os.remove(alert.image_path)
        except:
            pass
        db.session.delete(alert)
    # 删除视频回放
    for playback in Playback.query.all():
        try:
            os.remove(playback.file_path)
        except:
            pass
        db.session.delete(playback)
    db.session.commit()

    # 删除密码
    if Path(config._AUTH_PASSWORD_PATH).exists():
        os.remove(config._AUTH_PASSWORD_PATH)

@setting('system')
def _setting():
    return ModuleSetting({
            'system_title': Scope(
                'SYSTEM_TITLE',
                validator=Validator.STR_NOT_EMPTY
            )
        }
    )
