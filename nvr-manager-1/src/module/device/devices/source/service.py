import time

from base.ext import db
from base.methods import methods_noerror
from ...model.device import Device
from .exception import (
    SourceRegisterError,
    SourceNotExistsError
)


def _get_source(id: str) -> Device:
    if (source:= Device.query.get(id)) is None:
        raise SourceNotExistsError('该源不存在')
    return source

def _get_source_list() -> list[Device]:
    return Device.query.filter(Device.mac == None, Device.nvr_id == None).all()

def register_source(args: dict):
    id = args.get('id')
    if id is None:
        id = str(time.time_ns())
    if Device.query.get(id):
        raise SourceRegisterError('视频源ID重复，请更改ID并重新添加')

    try:
        default_aipro_id = methods_noerror.ai_project_get_default_ai_project()['id']
    except:
        default_aipro_id = None
        
    try:
        source = Device(
            id=id,
            name=args.get('name'), 
            source=args['source'],
            ai_rtmp_stream=f"rtmp://localhost/live/{id}",
            ai_http_stream=f"http://localhost/live/{id}.flv",
            ai_rtc_stream=f"webrtc://localhost/live/{id}",
            stream=None, 
            ai_project_id=default_aipro_id
        )
    except KeyError as e:
        raise SourceRegisterError(f'缺少参数{str(e)}')
    db.session.add(source)
    db.session.commit()
    return id

def patch_source(id: str, args: dict):
    source = _get_source(id)

    for k, v in args.items():
        setattr(source, k, v)

    db.session.commit()

    # 直接重启AI任务
    methods_noerror.ai_task_restart_ai_task(id)

def get_source(id: str):
    return _get_source(id).source_to_dict()

def get_source_list():
    return [source.source_to_dict() for source in _get_source_list()]

def delete_source(id: str):
    methods_noerror.device_delete_device(_get_source(id))
