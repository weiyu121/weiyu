import cv2
import io
from func_timeout import func_set_timeout, FunctionTimedOut

from base.methods import register_method, methods_noerror
from base.ext import db
from .devices.onvif.service import get_camera_list
from .devices.hiknvr.service import get_hiknvr_list
from .devices.source.service import get_source_list
from .model.device import Device
from .exception import (
    DeviceNotExistsError,
    DeviceCaptureFailed
)


_device_scope = (
    'id',
    'name',

    'source',
    'ai_rtmp_stream',
    'ai_http_stream',
    'ai_rtc_stream',
    'stream',

    # AI任务相关参数也返回
    'ai_project_id',
    'ai_task_enable',
    'ai_task_args',

    # 转发开启参数
    'enable_forward'
)

def _truncate_scope(device, scopes):
    return dict(filter(lambda scope: scope[0] in scopes, device.items()))

def get_device_list() -> dict:
    device_list = [_truncate_scope(camera, (*_device_scope, 'online')) for camera in get_camera_list()] \
        + [{**_truncate_scope(camera, _device_scope), 'online': hiknvr['online']} for hiknvr in get_hiknvr_list() for camera in hiknvr['cameras']] \
        + [{**_truncate_scope(source, _device_scope), 'online': True} for source in get_source_list()]  # 不知道怎么兼容了，默认它在线吧
    return {
        'device_list': device_list,
        'total_num': len(device_list),
        'online_num': len(list(filter(lambda dev: dev['online'], device_list))),
        'enable_num': len(list(filter(lambda dev: dev['ai_task_enable'], device_list)))
    }

def get_device_info(id: str) -> dict:
    device_list = list(filter(lambda device: device['id'] == id, get_device_list()['device_list']))
    if not device_list:
        raise DeviceNotExistsError(f'设备[{id}]不存在')
    return device_list[0]

def get_device_capture(id: str) -> io.BytesIO:
    device = Device.query.get(id)
    if not device:
        raise DeviceNotExistsError(f'设备[{id}]不存在')

    try:
        @func_set_timeout(15)
        def get_cap():
            return cv2.VideoCapture(int(device.ai_rtmp_stream) if device.ai_rtmp_stream.isdigit() else device.ai_rtmp_stream)
        cap = get_cap()
        if not cap.isOpened():
            cap.release()
            cap = None
    except FunctionTimedOut:
        cap = None
    if not cap:
        raise DeviceCaptureFailed(f'设备[{id}]连接失败，请检查摄像头是否开启，且能否正常联通')

    try:
        @func_set_timeout(5)
        def read():
            return cap.read()
        try:
            ok, frame = read()
            if ok:
                ok, buffer = cv2.imencode('.jpg', frame)
                if ok:
                    return io.BytesIO(buffer)
        except FunctionTimedOut:
            pass
    finally:
        cap.release()
    raise DeviceCaptureFailed(f'设备[{id}]连接成功但获取当前画面失败')

# 所有device删除请调用这个函数，它会同时关闭ai任务以及推流转发，最后从数据库删除记录
@register_method('device_delete_device')
def delete_device(device: Device):
    methods_noerror.ai_task_stop_ai_task(device.id)
    methods_noerror.cloud_forward_stop_forward(device.id)
    db.session.delete(device)
    db.session.commit()
