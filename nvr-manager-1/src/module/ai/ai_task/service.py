import os
from distutils.util import strtobool

from config import config
from base.ext import db
from base.init import init
from base.logger import get_logger
from base.setting import *
from base.methods import register_method
from .daemon import AITaskDeamon
from ..ai_project.model.ai_project import AIProject
from ..ai_project.exception import AIProjectNotExistsError
from ...device.model.device import Device
from ...device.exception import DeviceNotExistsError
from .exception import (
    AITaskAlreadyRunnigError,
    AITaskNotRunnigError,
    AITaskLaunchError,
    SetAITaskRegionError,
    GetAITaskRegionError,
    SetAITaskAlertError
)


_aitask_deamons: dict[str, AITaskDeamon] = {}  # 保存当前正在运行的所有进程对象
_logger = get_logger('ai.ai_task')

def _get_log_file_path(device_id: str) -> str:
    return os.path.join(config.AITASK_LOG_DIR, f'{device_id}.output')

def _run_ai_task(device: Device):
    ai_pro = AIProject.query.get(device.ai_project_id) if device.ai_project_id else None
    if not ai_pro:
        raise AITaskLaunchError(f'AI任务启动失败，监控设备[{device.id}]并没有关联任何AI项目')
    if not ai_pro.env_ok:
        raise AITaskLaunchError(f'AI任务启动失败，关联的AI项目尚未初始化成功')
    _aitask_deamons[device.id] = AITaskDeamon(device.id)
    device.ai_task_enable = True
    db.session.commit()

def _get_device(device_id: str) -> Device:
    device = Device.query.get(device_id)
    if not device:
        raise DeviceNotExistsError(f'监控设备[{device_id}]不存在')
    return device

@init
def _makedirs():
    os.makedirs(config.AITASK_LOG_DIR, exist_ok=True)

# 给所有设为“启动”的AI任务启动了
@init
def _launch_aitasks():
    for device in Device.query.filter(Device.ai_project_id != None, Device.ai_task_enable == True).all():
        _run_ai_task(device)
        _logger.debug(f'{device.id}的AI任务已启动')

@register_method('ai_task_run_ai_task')
def run_ai_task(device_id: str):
    device = _get_device(device_id)

    if device.ai_task_enable:
        raise AITaskAlreadyRunnigError(f'该AI任务已在运行')
    
    _run_ai_task(device)

@register_method('ai_task_restart_ai_task')
def restart_ai_task(device_id: str):
    device = _get_device(device_id)
    
    if not device.ai_task_enable:
        raise AITaskNotRunnigError(f'该监控设备的AI任务没有在运行，无法重启')
    
    _aitask_deamons[device_id].restart()

@register_method('ai_task_stop_ai_task')
def stop_ai_task(device_id: str):
    device = _get_device(device_id)
    
    if not device.ai_task_enable:
        raise AITaskNotRunnigError(f'该监控设备的AI任务没有在运行，无需停止')

    _aitask_deamons[device_id].stop()
    _aitask_deamons.pop(device_id)
    log_file_path = _get_log_file_path(device_id)
    # 顺便给他日志删咯，这样就不用单独提供一个清理AI任务资源的接口了
    if os.path.exists(log_file_path):
        os.remove(log_file_path)
    device.ai_task_enable = False
    db.session.commit()

def get_ai_task_status(device_id: str, params: dict) -> dict:
    device = _get_device(device_id)
    
    status = {
        'running': device.ai_task_enable
    }

    # 处理是否获取日志
    get_logs = bool(strtobool(params.get('get_log'))) if 'get_log' in params else False
    status['log'] = None

    if get_logs:
        log_file_path = _get_log_file_path(device_id)
        if os.path.exists(log_file_path):
            with open(log_file_path, 'r') as log_file:
                status['log'] = log_file.read()
    
    return status

def _to_dict(device: Device) -> dict:
    return dict(filter(lambda scope: scope[0] in (
        'ai_project_id',
        'ai_task_enable',
        'ai_task_args'
    ), device.to_dict().items()))

def get_ai_task_info(device_id: str) -> dict:
    return _to_dict(_get_device(device_id))

def patch_ai_task(device_id: str, pars: dict):
    device = _get_device(device_id)
    
    ai_pro = None
    
    # 这里分两个情况
    new_aipro_id = pars.get('ai_project_id')
    if new_aipro_id is not None and new_aipro_id != device.ai_project_id:
        # 一个是换了个AI项目，此时丢弃所有旧的参数
        ai_pro = AIProject.query.get(new_aipro_id)
        if not ai_pro:
            raise AIProjectNotExistsError('修改AI任务失败，所指定的AI项目不存在')
        if not ai_pro.env_ok:
            raise AIProjectNotExistsError('修改AI任务失败，所指定的AI项目未初始化成功')
        device.ai_project_id = new_aipro_id
        ai_task_args = pars.get('ai_task_args')
        device.ai_alert_config = None  # NOTE: 注意在这里丢弃之前的报警参数
    else:
        # 否则在原来参数基础上修改
        ai_pro = AIProject.query.get(device.ai_project_id)
        if not ai_pro:
            raise AIProjectNotExistsError('修改AI任务失败，其关联的AI项目不存在了，请手动更改')
        ai_task_args = device['ai_task_args'] or {}  # 原参数
        if 'ai_task_args' in pars: # 修改参数
            ai_task_args = pars['ai_task_args']
    
    if ai_task_args:
        # 直接写x[1] is not Fasle会出警告，虽然感觉没问题
        ai_task_args = dict(filter(lambda x: x[1] is not None and x[1] != '' and not (type(x[1])==list and not len(x[1])) and not (type(x[1])==bool and not x[1]), ai_task_args.items()))
    device.ai_task_args = ai_task_args or None
    db.session.commit()

    # 修改了参数或者AI项目，需要给现有的AI任务重启了
    if device_id in _aitask_deamons:
        _aitask_deamons[device_id].restart()

def get_region(device_id: str) -> dict:
    device = _get_device(device_id)
    
    info = device.to_dict()

    if info['ai_region'] and not isinstance(info['ai_region'][0], dict):
        raise GetAITaskRegionError('区域设置已过时，请重新设置区域')

    return {
        'regions': info['ai_region']
    }

def set_region(device_id: str, region_info: dict):
    device = _get_device(device_id)

    if 'regions' in region_info:
        regions = region_info['regions']
        if regions:
            region_names = set()
            for region in regions:
                if region['name'] in region_names:
                    raise SetAITaskRegionError(f'区域名称[{region["name"]}]重复，请修改')
                if len(region['region']) % 2 != 0:
                    raise SetAITaskRegionError('区域必须是2*N个归一化的浮点数表示多边形的区域。传入格式为数组：[x1, y1, x2, y2, ...]，按顺序传入N个点的坐标')
                region_names.add(region['name'])
            device.ai_region = regions
        else:
            device.ai_region = None

    db.session.commit()
    
    # 修改了参数或者AI项目，需要给现有的AI任务重启了
    if device_id in _aitask_deamons:
        _aitask_deamons[device_id].restart()

def get_alert(device_id: str) -> dict:
    return {
        'alert': _get_device(device_id)['ai_alert_config']
    }

def set_alert(device_id: str, args: dict) -> dict:
    device = _get_device(device_id)
    if 'alert' not in args:
        raise SetAITaskAlertError('请传入参数alert')
    # 验证参数
    if alert := args['alert']:
        for event in alert:
            if not isinstance(event.get('event'), str):
                raise SetAITaskAlertError('alert配置中要包含event字符串参数')
            if not isinstance(event.get('object'), str):
                raise SetAITaskAlertError('alert配置中要包含object字符串参数')
            if not isinstance(event.get('condition'), str):
                raise SetAITaskAlertError('alert配置中要包含condition字符串参数')
            if (args:= event.get('args')) is not None and not isinstance(args, list):
                raise SetAITaskAlertError('alert配置中要包含args参数，且该参数类型需要为null或列表')
            if args and not all((isinstance(arg, int) \
                or isinstance(arg, float) \
                or isinstance(arg, str) for arg in args)):
                raise SetAITaskAlertError('条件参数的类型只能是整数、小数或字符串')
    device.ai_alert_config = alert or None
    db.session.commit()
    if device_id in _aitask_deamons:
        _aitask_deamons[device_id].restart()

@setting('ai.ai_task')
def _setting():
    return ModuleSetting({
            'logs_dir': Scope(
                'AITASK_LOG_DIR', 
                cast_path,
                validator=Validator.PATH_NOT_EMPTY
        )},
        setting_callback=lambda settings: os.system(f'mv {config.AITASK_LOG_DIR} {settings["logs_dir"]}')
    )
