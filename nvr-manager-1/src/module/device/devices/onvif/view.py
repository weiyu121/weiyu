from flask import request

from base.app import get_blueprint, make_nvr_manager_response
from . import service


camera = get_blueprint('camera', __name__)
camera_search = get_blueprint('camera-search', __name__)

@camera.route('', methods=['POST'])
def register_camera():
    return make_nvr_manager_response({'id': service.register_camera(request.json)})
    
@camera.route('/<id>')
def get_camera_info(id: str):
    return make_nvr_manager_response(service.get_camera_info(id))

@camera.route('')
def get_camera_list():
    return make_nvr_manager_response({'camera_list': service.get_camera_list()})

@camera.route('/<id>', methods=['PATCH'])
def patch_camera(id: str):
    return make_nvr_manager_response(service.patch_camera(id, request.json))

@camera_search.route('')
def search_camera():
    return make_nvr_manager_response({'camera_list' :service.search_camera()})

@camera_search.route('', methods=['PATCH'])
def refresh_camera():
    service.refresh_camera()
    return make_nvr_manager_response()

@camera.route('/<id>', methods=['DELETE'])
def delete_camera(id: str):
    return make_nvr_manager_response(service.delete_camera(id))

@camera.route('/<id>/ptz', methods=['POST'])
def move_camera(id: str):
    return make_nvr_manager_response(service.move_camera_ptz(id, request.json))
