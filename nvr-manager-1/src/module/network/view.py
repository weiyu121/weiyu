from flask import request

from base.app import get_blueprint, make_nvr_manager_response
from base.exception import NVRManagerError
from . import service


network = get_blueprint('network', __name__)

@network.route('/wifi')
def scan_wifi():
    try:
        return make_nvr_manager_response({'wifi_list': service.scan_wifi()})
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wifi', methods=['POST'])
def connect_wifi():
    try:
        return make_nvr_manager_response(service.connect_wifi(request.json))
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wifi/status')
def get_wifi_status():
    try:
        return make_nvr_manager_response(service.get_wifi_status())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wifi', methods=['PATCH'])
def set_wifi():
    try:
        return make_nvr_manager_response(service.set_wifi(request.json))
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wifi', methods=['DELETE'])
def disconnect_wifi():
    try:
        return make_nvr_manager_response(service.disconnect_wifi())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wifi/last', methods=['POST'])
def save_last_wifi():
    try:
        return make_nvr_manager_response(service.save_last_wifi(request.json))
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wifi/last')
def get_last_wifi():
    try:
        return make_nvr_manager_response(service.get_last_wifi())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/hotspot')
def get_hotspot_status():
    try:
        return make_nvr_manager_response(service.get_hotspot_status())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/hotspot', methods=['POST'])
def switch_hotspot():
    try:
        return make_nvr_manager_response(service.switch_hotspot())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/hotspot', methods=['PATCH'])
def set_hotspot():
    try:
        return make_nvr_manager_response(service.set_hotspot(request.json))
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wire')
def get_wire_status():
    try:
        return make_nvr_manager_response(service.get_wire_status())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wire', methods=['POST'])
def switch_wire():
    try:
        return make_nvr_manager_response(service.switch_wire())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/wire', methods=['PATCH'])
def set_wire():
    try:
        return make_nvr_manager_response(service.set_wire(request.json))
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/mobile')
def get_mobile_status():
    try:
        return make_nvr_manager_response(service.get_mobile_status())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/mobile', methods=['POST'])
def switch_mobile():
    try:
        return make_nvr_manager_response(service.switch_mobile())
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)

@network.route('/check')
def check_internet():
    try:
        return make_nvr_manager_response({'reachable': service.check_internet()})
    except NVRManagerError as e:
        return make_nvr_manager_response(error=e)
