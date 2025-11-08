import time
import requests

from config import config
from base.init import init
from base.logger import get_logger
from base.ext import db
from base.utils import IpOnlineMonitor
from base.threadpool import wait_muti_run
from base.methods import methods_noerror
from ...model.device import Device
from .model.hiknvr import HikNVR
from .exception import (
    HikNVRRegisterError,
    HikNVRNotExistsError,
    HikNVRCameraAddingError,
    HikNVRCameraStreamChangingError,
    HikNVRCameraNotExistsError
)


_logger = get_logger('device.hiknvr')
_monitor = IpOnlineMonitor(config._HIKNVR_ONLINE_STATUS_TEST_INTERVAL)  # 用这个检测摄像头是否都在线，每隔一段时间都会更新数据

@init
def _add_online_monitor():
    for hiknvr in HikNVR.query.all():
        _monitor.update(hiknvr.id, hiknvr.ip)
    _logger.debug('NVR在线状态监视器已添加')

# 传入stream为null/0或者1都是主码流，2是子码流，其他暂不支持
def _get_stream(hiknvr: HikNVR, channel: int, stream: int) -> str:
    if not stream or stream == 1:
        stream = 1
    elif stream > 2 or stream < 0:
        raise HikNVRCameraStreamChangingError('海康NVR子摄像头目前只支持 0[默认码流(主码流)]、1[主码流]、2[子码流]')
    return 'rtsp://{}:{}@{}:554/Streaming/Channels/{}{}'.format(hiknvr.username, hiknvr.password, hiknvr.ip, channel, "%02d" % stream)
      
def register_hiknvr(register_info: dict) -> int:
    try:
        hiknvr = HikNVR(
            ip=register_info['ip'], 
            username=register_info['username'], 
            password=register_info['password'],
            model=register_info.get('model')
        )
    except KeyError as e:
        raise HikNVRRegisterError('海康NVR注册失败：' + str(e))
    
    hiknvr.name = register_info.get('name')

    hiknvr_cameras = register_info.get('cameras')
    if hiknvr_cameras and type(hiknvr_cameras) != list:
        raise HikNVRRegisterError('海康NVR注册失败，参数cameras不是数组')

    db.session.add(hiknvr)
    db.session.commit()
    _monitor.update(hiknvr.id, hiknvr.ip)
    return hiknvr.id

def _get_hiknvr_info(hiknvr: HikNVR) -> dict:
    '''将hiknvr转换成dict，并且在返回信息中删除username和password'''
    hiknvr_info = hiknvr.to_dict()
    hiknvr_info.pop('username')
    hiknvr_info.pop('password')
    # 查子摄像头
    hiknvr_info['cameras'] = [camera.hikcam_to_dict() for camera in Device.query.filter(Device.nvr_id == hiknvr_info['id']).all()]
    hiknvr_info['online'] = _monitor.is_online(hiknvr_info['id'])  # 在线状态
    hiknvr_info['manufacturer'] = 'HIKVISION'  # 填充制造商
    return hiknvr_info

def get_hiknvr_info(id: int) -> dict:
    '''获取海康NVR基本信息'''
    hiknvr = HikNVR.query.get(id)
    if not hiknvr:
        raise HikNVRNotExistsError(f'海康NVR[{id}]不存在')
    info = _get_hiknvr_info(hiknvr)
    info.pop('id')
    return info

def get_hiknvr_list() -> list:
    '''获取海康NVR列表'''
    return [_get_hiknvr_info(hiknvr) for hiknvr in HikNVR.query.all()]

def delete_hiknvr(id: int):
    '''删除海康NVR'''
    hiknvr = HikNVR.query.get(id)
    if not hiknvr:
        raise HikNVRNotExistsError(f'海康NVR[{id}]不存在')
    
    # 先给所有的AI任务都停了再删
    wait_muti_run(methods_noerror.ai_task_stop_ai_task, (camera.id for camera in Device.query.filter(Device.nvr_id == id).all()))
    db.session.delete(hiknvr)
    db.session.commit()
    _monitor.delete(hiknvr.id)

def patch_hiknvr(id: int, patch_info: dict):
    '''修改海康NVR'''
    hiknvr = HikNVR.query.get(id)
    if not hiknvr:
        raise HikNVRNotExistsError(f'海康NVR[{id}]不存在')

    patch_info = dict(filter(lambda item: item[1] is not None, patch_info.items()))

    for attr_name, attr_value in patch_info.items():
        setattr(hiknvr, attr_name, attr_value)

    if 'ip' in patch_info:
        _monitor.update(id, patch_info['ip'])

    dev_list = Device.query.filter(Device.nvr_id == hiknvr.id).all()
    for camera in dev_list:
        camera.source = _get_stream(hiknvr, camera.nvr_channel, camera.stream)

    db.session.commit()

    # 直接重启AI任务
    wait_muti_run(methods_noerror.ai_task_restart_ai_task, (camera.id for camera in dev_list))

### HikNVR子设备接口 ###
def add_hiknvr_camera(nvr_id: int, args: dict) -> str:
    '''添加海康NVR子摄像头'''
    hiknvr = HikNVR.query.get(nvr_id)
    if not hiknvr:
        raise HikNVRNotExistsError(f'海康NVR[{nvr_id}]不存在')
    
    nvr_channel = args.get('nvr_channel')
    if not nvr_channel or type(nvr_channel) != int or nvr_channel <=0:
        raise HikNVRCameraAddingError('请传入正确的通道编号，通道编号必须大于0')

    id = args.get('id')
    if id is None:
        id = str(time.time_ns())

    if Device.query.get(id):
        raise HikNVRCameraAddingError('子摄像头ID重复，请更改ID并重新添加')
    try:
        # 设置为默认的AI算法
        try:
            default_aipro_id = methods_noerror.ai_project_get_default_ai_project()['id']
        except:
            default_aipro_id = None
            
        stream = args.get('stream')
        db.session.add(Device(
            id=id,
            nvr_id=nvr_id,
            nvr_channel=nvr_channel,
            name=args.get('name'),
            source=_get_stream(hiknvr, nvr_channel, stream),
            ai_rtmp_stream=f"rtmp://localhost/live/{id}",
            ai_http_stream=f"http://localhost/live/{id}.flv",
            ai_rtc_stream=f"webrtc://localhost/live/{id}",
            stream=stream,
            ai_project_id=default_aipro_id
        ))
    except KeyError as e:
        _logger.warning(f'海康NVR[{hiknvr.id}]添加摄像头通道失败，没有传入字段：{str(e)}，信息为：{args}')
    db.session.commit()

def _get_hiknvr_camera(nvr_id: int, nvr_channel: int) -> Device:
    camera = Device.query.filter(Device.nvr_id == nvr_id, Device.nvr_channel == nvr_channel).one_or_none()
    if not camera:
        raise HikNVRCameraNotExistsError(f'海康NVR子摄像头不存在')
    return camera

def get_hiknvr_camera_info(nvr_id: int, nvr_channel: int) -> dict:
    '''获取海康NVR子摄像头'''
    return _get_hiknvr_camera(nvr_id, nvr_channel).hikcam_to_dict()

def delete_hiknvr_camera(nvr_id: int, nvr_channel: int) -> dict:
    '''获取海康NVR子摄像头'''
    methods_noerror.device_delete_device(_get_hiknvr_camera(nvr_id, nvr_channel))

def patch_hiknvr_camera(nvr_id: int, nvr_channel: int, patch_info: dict) -> dict:
    '''获取海康NVR子摄像头'''
    camera = _get_hiknvr_camera(nvr_id, nvr_channel)
    
    patch_info = dict(filter(lambda item: item[1] is not None, patch_info.items()))
    for attr_name, attr_value in patch_info.items():
        setattr(camera, attr_name, attr_value)

    if 'stream' in patch_info:
        hiknr = HikNVR.query.get(nvr_id)
        camera.source = _get_stream(hiknr, nvr_channel, patch_info['stream'])  # 尝试更改live_rtsp的码流
    db.session.commit()

    # 直接重启AI任务
    methods_noerror.ai_task_restart_ai_task(camera.id)
