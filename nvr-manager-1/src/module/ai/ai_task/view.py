from flask import request

from base.app import get_blueprint, make_nvr_manager_response
from . import service


ai_task = get_blueprint('ai-task', __name__)

@ai_task.route('/<device_id>/start', methods=['POST'])
def run_ai_task(device_id: str):
    service.run_ai_task(device_id)
    return make_nvr_manager_response()

@ai_task.route('/<device_id>/restart', methods=['POST'])
def restart_ai_task(device_id: str):
    service.restart_ai_task(device_id)
    return make_nvr_manager_response()

@ai_task.route('/<device_id>/stop', methods=['POST'])
def stop_ai_task(device_id: str):
    service.stop_ai_task(device_id)
    return make_nvr_manager_response()

@ai_task.route('/<device_id>/status')
def get_ai_task_status(device_id: str):
    return make_nvr_manager_response(service.get_ai_task_status(device_id, request.args))

@ai_task.route('/<device_id>')
def get_ai_task_info(device_id: str):
    return make_nvr_manager_response(service.get_ai_task_info(device_id))

@ai_task.route('/<device_id>', methods=['PATCH'])
def patch_ai_task(device_id: str):
    service.patch_ai_task(device_id, request.json)
    return make_nvr_manager_response()

@ai_task.route('/<device_id>/region')
def get_region(device_id: str):
    return make_nvr_manager_response(service.get_region(device_id))

@ai_task.route('/<device_id>/region', methods=['PATCH'])
def set_region(device_id: str):
    service.set_region(device_id, request.json)
    return make_nvr_manager_response()

@ai_task.route('/<device_id>/alert')
def get_alert(device_id: str):
    return make_nvr_manager_response(service.get_alert(device_id))

@ai_task.route('/<device_id>/alert', methods=['PATCH'])
def set_alert(device_id: str):
    service.set_alert(device_id, request.json)
    return make_nvr_manager_response()