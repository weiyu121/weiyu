import os
import requests
import cv2
import re
import traceback
from datetime import datetime
from threading import Lock
from sqlalchemy import extract, func
from func_timeout import func_set_timeout, FunctionTimedOut

from config import config
from base.logger import get_logger
from base.scheduler import scheduler
from base.ext import db
from base.init import init
from base.utils import exponential_backoff, get_disk_usage, cleanup_by_expire_day, scroll_insert
from base.setting import *
from base.methods import methods
from .model.playback import Playback
from ..device.model.device import Device


_logger = get_logger('dvr')
_device_name_cache = {}

@init
def _make_playback_dir():
    os.makedirs(config.DVR_PLAYBACK_DIR, exist_ok=True)

def _get_video_duration(filename: str) -> int:
    cap = cv2.VideoCapture(filename)
    return int(cap.get(7) / cap.get(5)) if cap.isOpened() else None

@init
def _init_srs():
    @func_set_timeout(60)
    def timeout_wrapper():
        _reload_srs()
    try:
        timeout_wrapper()
    except FunctionTimedOut:
        _logger.fatal('无法调用srs api以及重载srs配置')
        exit(1)

def _reload_srs():
    with open(os.path.join(os.path.dirname(__file__), 'resources', 'srs.conf'), 'r') as srs_conf_fm_file:
        with open(config._DVR_SRS_COFIG_PATH, 'w') as srs_config_file:
            # 一个问题：给127.0.0.1改成localhost就不行，不知道为啥
            srs_config_file.write(srs_conf_fm_file.read()\
                .replace('{DVR_PLAYBACK_DIR}', os.path.realpath(config.DVR_PLAYBACK_DIR))\
                .replace('{DVR_PLAYBACK_SEGMENT_DURATION}', str(config.DVR_PLAYBACK_SEGMENT_DURATION))\
                .replace('{ONDVR_CALLBACK_URL}', f'http://127.0.0.1:{config._SERVER_PORT}/dvr/callback/on_dvr')\
                .replace('{ONPUBLISH_CALLBACK_URL}', f'http://127.0.0.1:{config._SERVER_PORT}/dvr/callback/on_publish'))
    def srs_reload(interval):
        err_msg = None
        try:
            code = requests.get('http://localhost:1985/api/v1/raw?rpc=reload').json()['code']
            if code != 0:
                err_msg = '调用srs api失败，srs配置可能被篡改了'
            else:
                return True
        except Exception:
            err_msg = '调用srs api失败，srs可能没有开启'
        _logger.warning(f'{err_msg}，{interval}s后重试')
        return False
    exponential_backoff(srs_reload, 4)

def on_publish(data: dict):
    _device_name_cache[data['stream']] = Device.query.get(data['stream']).name
    # 这里进行缓存的清除操作，给已经不在数据库的device的缓存删掉，此时肯定录完了所以大概率没关系
    for did in _device_name_cache.keys():
        if did != data['stream'] and Device.query.get(did) is None:
            _device_name_cache.pop(did)

scroll_lock = Lock()
# 注意：海康摄像头当主码流设置为H265编码，并且AI算法推流时（原始流直接转播没事），srs的分段录制功能会失效。子码流和第三码流设置H265没事。
# （UPDATE：这好像取决于系统里有没有安装x265库，反正挺奇怪的）
def store_playback(playback_info: dict):
    file_path = playback_info['file']
    m = re.search(r'(\d+).flv', file_path)
    if not m:
        _logger.warning(f'视频录制格式不符合规范，无法将视频[{file_path}]加入数据库')
        return
    
    duration = _get_video_duration(file_path)
    if not duration or duration < 0:  # 当duration为0或负数也不行
        _logger.warning(f'无法获取视频[{file_path}]的持续时长，无法将视频]加入数据库')
        os.remove(file_path)
        return
    
    device_id = playback_info['stream']
    device_name = _device_name_cache.get(device_id)
    if not device_name:
        device = Device.query.get(device_id)
        if not device:
            device_name = '未知设备'
        else:
            device_name = device.name
            _device_name_cache[device_id] = device_name

    playback = Playback(
        file_path=file_path,
        device_id=device_id,
        device_name=device_name,
        event_time=datetime.fromtimestamp(int(m[1])/1000),
        duration=duration
    )
    
    if get_disk_usage(file_path).free < config._DVR_PLAYBACK_SCROLL_DELETION_THRESHHOLD:
        if config.DVR_PLAYBACK_SCROLL_DELETION:
            with scroll_lock:
                ok, del_count = scroll_insert(playback, Playback, 'file_path')
            if not ok:
                # 用户没开滚动删除并且磁盘空间真的不够了，没法滚动删除回放来释放这么多空间，那就不要这段录像了
                _logger.info(f'磁盘空间不足，回放{file_path}将不会被存储')
                os.remove(file_path)
                return
            else:
                _logger.debug(f'已滚动删除{del_count}条回放记录')
        else:
            # 用户没开滚动删除并且磁盘空间真的不够了，没法滚动删除回放来释放这么多空间，那就不要这段录像了
            _logger.info(f'磁盘空间不足，并且未启用滚动删除，回放{file_path}将不会被存储')
            os.remove(file_path)
            return
    else:
        try:
            db.session.add(playback)
            db.session.commit()
        except Exception:
            _logger.warning(f'回放[{file_path}]存储失败：\n{traceback.format_exc()}')
    
    # 通知报警，一个回放录好了
    try:
        methods.alert_patch_alerts_record(playback.to_dict())
    except Exception:
        _logger.warning(f'修改报警录像路径失败：\n{traceback.format_exc()}')

def get_playback_date(args: dict) -> list:
    '''返回某个设备有dvr记录的日期'''
    return list(map(lambda row: row[0], Playback.query.filter(
        Playback.device_id == args['device_id'],
    ).with_entities(func.date_format(Playback.event_time, "%Y-%m-%d")).distinct().order_by(func.date_format(Playback.event_time, "%Y-%m-%d")).all()))

def get_playback_records(args: dict) -> list:
    '''返回某个设备某一天的所有记录'''
    query = Playback.query
    if device_id:= args.get('device_id'):
        query = query.filter(Playback.device_id == device_id)
    if date:= args.get('time'):
        query = query.filter(
            func.date(Playback.event_time) == datetime.strptime(date, "%Y-%m-%d").date()
        )
    return [record.to_dict() for record in query.order_by(Playback.event_time.desc()).all()]

def _timing_cleanup_playback():
    if config.DVR_PLAYBACK_CLEANUP_DAYS <= 0:
        return
    data_count, file_count = cleanup_by_expire_day(config.DVR_PLAYBACK_CLEANUP_DAYS, Playback, 'event_time', ('file_path',))
    _logger.info(f'定时回放删除任务完成，已删除{data_count}条回放记录以及{file_count}个回放视频')

@init
def _add_playback_cleanup_job():
    time = datetime.strptime(config.DVR_PLAYBACK_CLEANUP_TIME, '%H:%M:%S').time()
    scheduler.add_job(_timing_cleanup_playback, trigger='cron', id='dvr.timing_cleanup_playback', hour=time.hour, minute=time.minute, second=time.second)
    _logger.debug(f'回放定时删除任务已添加')

def _update_settings(settings: dict):

    if 'playback_dir' in settings:
        os.makedirs(settings['playback_dir'], exist_ok=True)

    if 'cleanup_time' in settings:
        time = datetime.strptime(settings['cleanup_time'], '%H:%M:%S')
        scheduler.reschedule_job('dvr.timing_cleanup_playback', trigger='cron', hour=time.hour, minute=time.minute, second=time.second)
    
    # 配置修改涉及到srs，需要让srs重新加载配置
    if 'segment_duration' in settings or 'playback_dir' in settings:
        @func_set_timeout(5)
        def timeout_wrapper():
            _reload_srs()
        try:
            timeout_wrapper()
        except FunctionTimedOut:
            _logger.error('无法调用srs api以及重载srs配置，srs可能处于不可用状态')

@setting('dvr')
def _setting():
    return ModuleSetting({
            'playback_dir': Scope(
                'DVR_PLAYBACK_DIR',
                cast_path,
            ),
            'segment_duration': Scope(
                'DVR_PLAYBACK_SEGMENT_DURATION',
                int,
                validator=Validator.INT_RANGE(10)
            ),
            'cleanup_time': Scope(
                'DVR_PLAYBACK_CLEANUP_TIME',
                validator=Validator.TIME
            ),
            'cleanup_days': Scope(
                'DVR_PLAYBACK_CLEANUP_DAYS',
                int,
                validator=Validator.INT_RANGE(0),
            ),
            'scroll_deletion': Scope(
                'DVR_PLAYBACK_SCROLL_DELETION',
                cast_bool
            )
        },
        setting_callback=_update_settings
    )
