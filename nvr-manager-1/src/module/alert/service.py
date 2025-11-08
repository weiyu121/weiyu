import os
import base64
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm.query import Query
from werkzeug.exceptions import NotFound
from threading import Lock

from config import config
from base.ext import db
from base.scheduler import scheduler
from base.init import init
from base.logger import get_logger
from base.threadpool import thread_pool
from base.setting import *
from base.utils import cleanup_by_expire_day, get_disk_usage, scroll_insert
from base.mqtt import get_mqtt_service
from base.methods import register_method
from .model.alert import Alert
from ..device.model.device import Device
from .exception import (
    AlertCollectingError,
    AlertNotExistsError,
    AlertCountGettingError
)


_logger = get_logger('alert')

@init
def _makedirs():
    os.makedirs(config.ALERT_IMAGE_DIR, exist_ok=True)  

scroll_lock = Lock()
def add_alert(alert_info: dict):
    try:
        alert_info['device_name'] = Device.query.get(alert_info['device_id']).name,  # 其实有个逻辑漏洞，如果报警之后立刻给这条device删了，那就查不到了，不过想想应该不会发生吧
        alert = Alert(**alert_info, time=datetime.now())
        # NOTE: 简单兼容一下旧报警格式，并做一个obj是否为空的判断
        if not alert.object:
            alert.object = alert_info.get('type') or '未知'
        if not alert.event:
            alert.event = alert_info.get('target') or '未知'
    except Exception as e:
        raise AlertCollectingError(f'警报收集信息收集失败，错误为：{str(e)}')

    image = alert_info.get('image')
    if image:
        image_path = os.path.join(config.ALERT_IMAGE_DIR, alert.object, str(alert.time.year), str(alert.time.month), str(alert.time.day), f'{uuid.uuid1()}.{image["ext"]}')
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        with open(image_path, 'wb') as fimg:
            fimg.write(base64.b64decode(image['base64']))
        alert.image_path = image_path
    
        if get_disk_usage(image_path).free < config._ALERT_SCROLL_DELETION_THRESHHOLD:
            if config.ALERT_SCROLL_DELETION:
                with scroll_lock:
                    ok, del_count = scroll_insert(alert, Alert, 'image_path')
                if not ok:
                    # 用户没开滚动删除并且磁盘空间真的不够了，没法滚动删除回放来释放这么多空间，那就不要这段录像了
                    _logger.info(f'磁盘空间不足，报警{image_path}将不会被存储')
                    os.remove(image_path)
                    return
                else:
                    _logger.debug(f'已滚动删除{del_count}条报警记录')
            else:
                # 用户没开滚动删除并且磁盘空间真的不够了，没法滚动删除回放来释放这么多空间，那就不要这段录像了
                _logger.info(f'磁盘空间不足，并且未启用滚动删除，报警{image_path}将不会被存储')
                os.remove(image_path)
                return
    db.session.add(alert)
    db.session.commit()

def _get_alert_filter_query(args: dict) -> Query:
    query: Query = Alert.query
    if 'object' in args:
        query = query.filter(Alert.object == args['object'])
    if 'event' in args:
        query = query.filter(Alert.event == args['event'])
    if 'device_id' in args:
        query = query.filter(Alert.device_id == args['device_id'])
    if 'begin_datetime' in args:
        query = query.filter(Alert.time >= datetime.strptime(args['begin_datetime'], '%Y-%m-%d %H:%M:%S'))
    if 'end_datetime' in args:
        query = query.filter(Alert.time <= datetime.strptime(args['end_datetime'], '%Y-%m-%d %H:%M:%S'))
    return query

def get_alert_list(args: dict) -> dict:
    query = _get_alert_filter_query(args).order_by(Alert.time.desc())
    
    if 'page_size' in args:
        try:
            paginate = query.paginate(page=int(args.get('page_index') or 1), per_page=int(args['page_size']))
            return {
                'alert_list': [alert.to_dict() for alert in paginate.items], 
                'current_page': paginate.page,
                'total_page': paginate.pages,
                'total_count': paginate.total
            }
        except NotFound:
            raise AlertNotExistsError('未查询到当前分页的报警信息')
    else:
        return {'alert_list': [alert.to_dict() for alert in query.all()]}
    
def get_alert_count(args: dict) -> dict:
    query = _get_alert_filter_query(args)

    if 'group' in args:
        group = None
        if args['group'] == 'date':
            group = db.func.DATE(Alert.time)
        elif args['group'] == 'device':
            group = Alert.device_id
        elif args['group'] == 'object':
            group = Alert.object
        else:
            raise AlertCountGettingError('group参数必须为[date/device/object]中的一个')
        
        count_list = [
            {
                'value': col[0].strftime('%Y-%m-%d') if args['group'] == 'date' else col[0], 
                'count': col[1]
            } for col in query.with_entities(group, db.func.count()).group_by(group).all()
        ]
        
        return {'count_list': count_list, 'total_count': sum(map(lambda group: group['count'], count_list))}
    else:
        return {'count_list': None, 'total_count': query.count()}

@register_method('alert_patch_alerts_record')
def patch_alerts_record(dvr_info: dict):
    begin_time = datetime.strptime(dvr_info['event_time'], '%Y-%m-%d %H:%M:%S')
    end_time = begin_time + timedelta(seconds=dvr_info['duration'])
    alerts = Alert.query.filter(Alert.time >= begin_time, Alert.time <= end_time, Alert.device_id == dvr_info['device_id'], Alert.record_path == None).all()
    if alerts:
        dvr_path = dvr_info['file_path']
        for alert in alerts:
            alert.record_path = dvr_path
            # 云端上报
            thread_pool.submit(get_mqtt_service().report_alert, alert.to_dict())
        db.session.commit()

def _timing_cleanup():
    if config.ALERT_CLEANUP_DAYS <= 0:
        return
    data_count, file_count = cleanup_by_expire_day(config.ALERT_CLEANUP_DAYS, Alert, 'time', ('image_path', 'record_path'))
    _logger.info(f'定时回放删除任务完成，已删除{data_count}条报警记录以及{file_count}个报警相关文件')

@init
def _add_cleanup_job():
    if config.ALERT_CLEANUP_DAYS:
        time = datetime.strptime(config.ALERT_CLEANUP_TIME, '%H:%M:%S').time()
        scheduler.add_job(_timing_cleanup, trigger='cron', id='alert.timing_cleanup', hour=time.hour, minute=time.minute, second=time.second)
        _logger.debug(f'报警定时删除任务已添加')

def _update_settings(settings: dict):
    if 'image_dir' in settings:
        os.makedirs(settings['image_dir'], exist_ok=True)

    if 'cleanup_time' in settings:
        time = datetime.strptime(settings['cleanup_time'], '%H:%M:%S')
        scheduler.reschedule_job('alert.timing_cleanup', trigger='cron', hour=time.hour, minute=time.minute, second=time.second)

@setting('alert')
def _setting():
    return ModuleSetting({
            'image_dir': Scope(
                'ALERT_IMAGE_DIR', 
                cast_path
            ),
            'cleanup_time': Scope(
                'ALERT_CLEANUP_TIME',
                validator=Validator.TIME,
            ),
            'cleanup_days': Scope(
                'ALERT_CLEANUP_DAYS',
                int,
                validator=Validator.INT_RANGE(0),
            ),
            'scroll_deletion': Scope(
                'ALERT_SCROLL_DELETION',
                cast_bool
            )
        },
        setting_callback=_update_settings
    )