import re
import logging
import time
from wsdiscovery import WSDiscovery, Scope
from func_timeout import func_set_timeout
from func_timeout.exceptions import FunctionTimedOut
from onvif.exceptions import ONVIFError

from base.logger import get_logger
from base.ext import db
from base.app import app
from base.init import init
from base.scheduler import scheduler
from base.threadpool import thread_pool
from base.utils import IpOnlineMonitor
from base.methods import methods_noerror
from config import config
from .camera import OnvifCamera
from ...model.device import Device
from .exception import (
    OnvifRegisterError,
    OnvifExistsError,
    OnvifNotExistsError,
    OnvifOfflineError,
    OnvifStreamChangingError
)


_onvif_cameras = {}
_monitor = IpOnlineMonitor(config._CAMERA_ONLINE_STATUS_TEST_INTERVAL)  # 用这个检测摄像头是否都在线，每隔一段时间都会更新数据
_logger = get_logger('device.camera')

# 从缓存中或者重新创建onvif camera对象
def _get_onvif_camera(id: str) -> OnvifCamera:
    onvif_cam = _onvif_cameras.get(id)
    if not onvif_cam:
        camera = _get_camera(id)
        if not camera:
            raise OnvifNotExistsError(f'Onvif摄像头{id}不存在')
        try:
            onvif_cam = _create_onvif_camera_from_orm(camera)
        except OnvifConnectionError as e:
            raise OnvifOfflineError(f'摄像头{id}连接失败：{str(e)}')
    return onvif_cam

# 如果检测到onvif camera对象已过期，可以更新一下
def _update_onvif_camera(id: str) -> OnvifCamera:
    if id in _onvif_cameras:
        _onvif_cameras.pop(id)
    return _get_onvif_camera(id)

# 重新创建onvif camera对象并且加到缓存中
def _create_onvif_camera_from_orm(camera: Device) -> OnvifCamera:
    return _create_onvif_camera(camera.id, camera.ip, camera.port, camera.username, camera.password)

# 下面那个函数连接摄像头失败，就会抛这个异常
class OnvifConnectionError(Exception):
    pass

# 重新创建onvif camera对象并且加到缓存中
def _create_onvif_camera(camera_id, *args, **kwargs) -> OnvifCamera:
    @func_set_timeout(5)
    def wrapper():
        onvif_cam = OnvifCamera(*args, **kwargs)
        _onvif_cameras[camera_id] = onvif_cam
        return onvif_cam

    # 我想在这个函数里就处理完异常情况，包括超时，如果创建失败就抛异常
    try:
        return wrapper()
    except FunctionTimedOut:
        raise OnvifConnectionError('摄像头连接超时')
    except ONVIFError as e:
        raise OnvifConnectionError(str(e).removeprefix('Unknown error: '))

# 获取单个摄像头的orm最好都用这个函数，不然外面得自己判断获取的摄像头是不是onvif摄像头
def _get_camera(id: str) -> Device:
    camera = Device.query.get(id)
    if not camera or camera.mac is None:
        return None
    return camera

def _get_cameras() -> list[Device]:
    return Device.query.filter(Device.mac != None).all()

def _to_dict(camera: Device) -> dict:
    return {
        **camera.onvif_to_dict(),
        'online': _monitor.is_online(camera.id)
    }

@init
def _add_online_monitor():
    for camera in _get_cameras():
        _monitor.update(camera.id, camera.ip)
    _logger.debug('摄像头在线状态监视器已添加')

def _discovery_cameras() -> list:
    _wsd = WSDiscovery()
    _wsd.start()
    onvif_cameras = []

    # 下面的写法很丑陋，但是确实需要一个字段一个字段的判断，ip必须有，其他两个可以没有
    for svc in _wsd.searchServices(scopes=[Scope("onvif://www.onvif.org/Profile")], timeout=2):
        try:
            ip = tuple(
                m[1]
                    for m in filter(None, (re.search(r'(\d+.\d+.\d+.\d+)', xaddrs) for xaddrs in svc.getXAddrs()))
                )[0]
        except:
            continue

        try:
            mac = tuple(
                str(mac).removeprefix('onvif://www.onvif.org/MAC/') 
                    for mac in filter(lambda scope: str(scope).startswith('onvif://www.onvif.org/MAC/'), svc.getScopes())
                )[0]
        except:
            mac = None

        try:
            hardware_name = tuple(
                str(name_scope).removeprefix('onvif://www.onvif.org/name/')
                    for name_scope in filter(lambda scope: str(scope).startswith('onvif://www.onvif.org/name/'), svc.getScopes())
                )[0]
        except:
            hardware_name = None

        onvif_cameras.append({
            'mac': mac,
            'ip': ip,
            'hardware_name': hardware_name
        })
    _wsd.stop()
    _wsd._stopThreads()
    return onvif_cameras

def _update_camera_ip(camera: Device, ip: str):
    camera.ip = ip
    onvif_camera = _create_onvif_camera_from_orm(camera)
    camera.__init__(**onvif_camera.get_info())
    if camera.stream is not None:
        try:
            camera.source = _get_stream(camera.source, camera.stream)  # 尝试更改live_rtsp的码流
        except OnvifStreamChangingError:
            camera.stream = None
    _monitor.update(camera.id, camera.ip)
    db.session.commit()

def refresh_camera():
    dis_cameras = _discovery_cameras()
    with app.app_context():
        for dis_cam in dis_cameras:
            if not dis_cam['mac']:  # 没mac地址的爬
                continue
            ip = dis_cam['ip']
            camera = Device.query.filter(Device.mac == dis_cam["mac"]).one_or_none()
            if camera and camera.ip != ip:
                # 更新数据库摄像头信息
                _update_camera_ip(camera, ip)
                _logger.info(f'摄像头{camera.id}的ip地址已改变，已将其替换为新的ip地址[{ip}]')

def search_camera() -> list:
    return _discovery_cameras() 

@init
def _start_search():
    # 这东西有时候有警告，但不知道啥意思，给他关掉
    ws_daemon_logger = logging.getLogger('daemon')
    ws_daemon_logger.setLevel(logging.ERROR)

    scheduler.add_job(refresh_camera, 'interval', seconds=config.CAMERA_DISCOVERY_INTERVAL_SECONDS)
    _logger.debug('摄像头扫描定时任务已添加')

@init
def _init_all_cameras():
    # 创建缓存
    [thread_pool.submit(_create_onvif_camera_from_orm, camera) for camera in _get_cameras()]

def _get_stream(rtsp_url: str, stream: int) -> str:
    if stream is None:
        return rtsp_url
    if re.match(r'rtsp://[^/]*/Streaming/Channels/10\d.*', rtsp_url):
        # 识别是否为海康摄像头的格式，如果是的话则可以调整码流
        if stream == 0:  # 默认就是主码流，所以如果stream是0，代表换回默认的主码流
            stream = 1
        elif not (stream >= 1 and stream <= 3):
            raise OnvifStreamChangingError('海康摄像头目前只支持 0[默认码流(主码流)]、1[主码流]、2[子码流]、3[第三码流]')
        return re.sub(r'Channels/10\d', f'Channels/10{stream}', rtsp_url)
    elif re.match(r'rtsp://[^/]*/cam/realmonitor\?channel=\d+&subtype=\d+.*', rtsp_url):
        # 识别是否为大华摄像头的格式，如果是的话则可以调整码流
        if stream == 0:  # 默认就是主码流，所以如果stream是0，代表换回默认的主码流
            stream = 1
        elif not (stream >= 1 and stream <= 2):
            raise OnvifStreamChangingError('大华摄像头目前只支持 0[默认码流(主码流)]、1[主码流]、2[辅码流]')
        return re.sub(r'subtype=\d', f'subtype={stream - 1}', rtsp_url)
    raise OnvifStreamChangingError('目前只支持海康和大华摄像头更改码流，其余产品暂不支持')

def register_camera(register_info: dict) -> str:
    '''注册摄像头到数据库并返回id'''
    id = register_info.get('id')
    if id is None:
        id = str(time.time_ns())
    if _get_camera(id):
        raise OnvifExistsError('摄像头ID重复，请更改ID并重新添加')

    try:
        onvif_cam = _create_onvif_camera(id, register_info['ip'], register_info['port'], register_info['username'], register_info['password'])
    except OnvifConnectionError as e:
        raise OnvifRegisterError('摄像头注册失败：' + str(e))
    except KeyError as e:
        raise OnvifRegisterError('摄像头注册失败，缺少必要字段：' + str(e))
    
    # 设置为默认的AI算法
    try:
        default_aipro_id = methods_noerror.ai_project_get_default_ai_project()['id']
    except:
        default_aipro_id = None

    camera = Device(
        **onvif_cam.get_info(), 
        id=id,
        ai_rtmp_stream=f"rtmp://localhost/live/{id}",
        ai_http_stream=f"http://localhost/live/{id}.flv",
        ai_rtc_stream=f"webrtc://localhost/live/{id}",
        name=register_info.get('name'), 
        stream=register_info.get('stream'), 
        ai_project_id=default_aipro_id
    )
    if register_info.get('stream') is not None:
        camera.source = _get_stream(camera.source, register_info['stream'])  # 尝试更改live_rtsp的码流

    db.session.add(camera)
    db.session.commit()
    _monitor.update(camera.id, camera.ip)
    return id

def get_camera_info(id: str) -> dict:
    '''获取摄像头基本信息'''
    camera = _get_camera(id)
    if not camera:
        raise OnvifNotExistsError(f'获取信息失败，摄像头不存在，请先注册')
    info = _to_dict(camera)
    info.pop('id')
    return info

def get_camera_list() -> list:
    return [_to_dict(camera) for camera in _get_cameras()]

def patch_camera(id: str, patch_info: dict):
    camera = _get_camera(id)
    if not camera:
        raise OnvifNotExistsError(f'修改失败，摄像头不存在，请先注册')
    
    patch_info = dict(filter(lambda item: item[1] is not None, patch_info.items()))
    for k, v in patch_info.items():
        setattr(camera, k, v)

    if 'stream' in patch_info:
        camera.source = _get_stream(camera.source, patch_info['stream'])  # 尝试更改live_rtsp的码流
    
    if 'ip' in patch_info:
        try:
            _update_camera_ip(camera, patch_info['ip'])
        except:
            raise OnvifOfflineError('修改摄像头ip失败，无法连接到该ip地址')
    
    db.session.commit()

    # 直接重启AI任务
    methods_noerror.ai_task_restart_ai_task(camera.id)

# FIXME: 删除摄像头有bug，没删成功
def delete_camera(id: str):
    camera = _get_camera(id)
    if not camera:
        raise OnvifNotExistsError(f'删除失败，摄像头不存在，请先注册')
    methods_noerror.device_delete_device(camera)
    _monitor.delete(camera.id)

def move_camera_ptz(id: str, pars: dict):
    onvif_cam = _get_onvif_camera(id)
    translation = (pars.get('x') or 0, pars.get('y') or 0, pars.get('z') or 0)
    
    @func_set_timeout(1)
    def move():
        onvif_cam.move(translation)
        
    try:
        move()
    except FunctionTimedOut:
        # 超时说明摄像头离线，重新连接一下试试
        onvif_cam = _update_onvif_camera(id)
        move()
        # 还不行的话就寄
        raise OnvifOfflineError('移动失败，摄像头不在线')
