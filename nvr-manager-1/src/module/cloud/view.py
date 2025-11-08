from base.app import get_blueprint, make_nvr_manager_response
from . import frpc_service
from . import forward_service


cloud = get_blueprint('cloud', __name__)

@cloud.route('/forward/<device_id>/start', methods=['POST'])
def start_forward(device_id):
    forward_service.start_forward(device_id)
    return make_nvr_manager_response()

@cloud.route('/forward/<device_id>/stop', methods=['POST'])
def stop_forward(device_id):
    forward_service.stop_forward(device_id)
    return make_nvr_manager_response()

@cloud.route('/address')
def get_address():
    return make_nvr_manager_response(frpc_service.get_address())
