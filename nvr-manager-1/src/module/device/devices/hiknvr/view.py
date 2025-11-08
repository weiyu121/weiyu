from flask import request

from base.app import get_blueprint, make_nvr_manager_response
from . import service


camera = get_blueprint('hiknvr', __name__)

@camera.route('', methods=['POST'])
def register_hiknvr():
    return make_nvr_manager_response({'id': service.register_hiknvr(request.json)})

@camera.route('/<int:id>')
def get_hiknvr_info(id: int):
    return make_nvr_manager_response(service.get_hiknvr_info(id))

@camera.route('')
def get_hiknvr_list():
    return make_nvr_manager_response({'hiknvr_list': service.get_hiknvr_list()})

@camera.route('/<int:id>', methods=['DELETE'])
def delete_hiknvr(id: int):
    return make_nvr_manager_response(service.delete_hiknvr(id))

@camera.route('/<int:id>', methods=['PATCH'])
def patch_hiknvr(id: int):
    return make_nvr_manager_response(service.patch_hiknvr(id, request.json))

### HikNVR子设备接口 ###
@camera.route('/<int:nvr_id>', methods=['POST'])
def add_hiknvr_camera(nvr_id: int):
    service.add_hiknvr_camera(nvr_id, request.json)
    return make_nvr_manager_response()

@camera.route('/<int:nvr_id>/<int:nvr_channel>')
def get_hiknvr_camera_info(nvr_id: int, nvr_channel: int):
    return make_nvr_manager_response(service.get_hiknvr_camera_info(nvr_id, nvr_channel))

@camera.route('/<int:nvr_id>/<int:nvr_channel>', methods=['DELETE'])
def delete_hiknvr_camera(nvr_id: int, nvr_channel: int):
    return make_nvr_manager_response(service.delete_hiknvr_camera(nvr_id, nvr_channel))

@camera.route('/<int:nvr_id>/<int:nvr_channel>', methods=['PATCH'])
def patch_hiknvr_camera(nvr_id: int, nvr_channel: int):
    return make_nvr_manager_response(service.patch_hiknvr_camera(nvr_id, nvr_channel, request.json))
