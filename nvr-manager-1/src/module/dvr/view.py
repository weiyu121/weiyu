from flask import request
from . import service

from base.app import get_blueprint, make_nvr_manager_response, make_send_file_response
from .exception import (
    DVRPlaybackGettingError,
    DVRPlaybackNotExistsError
)


playback = get_blueprint('dvr', __name__)

@playback.route('/callback/on_dvr', methods=['POST'])
def on_dvr_callback():
    try:
        service.store_playback(request.json)
    except:
        pass
    return make_nvr_manager_response()

@playback.route('/callback/on_publish', methods=['POST'])
def on_publish_callback():
    try:
        service.on_publish(request.json)
    except:
        pass
    return make_nvr_manager_response()

@playback.route('/date')
def get_playback_date():
    return make_nvr_manager_response({'time': service.get_playback_date(request.args)})

@playback.route('/records')
def get_playback_records():
    return make_nvr_manager_response({'records': service.get_playback_records(request.args)})

@playback.route('/playback')
def get_playback():
    return make_send_file_response(request.args.get('path'), DVRPlaybackGettingError, DVRPlaybackNotExistsError)
