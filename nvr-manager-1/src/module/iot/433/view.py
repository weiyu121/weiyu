from flask import request
from base.app import get_blueprint, make_nvr_manager_response

from . import service


iot_433 = get_blueprint('iot/433', __name__)

@iot_433.route('/FindDevice')
def FindDevice():
    return make_nvr_manager_response({"result": service.FindDevice(request.args.get('Timeout'))})

@iot_433.route('/NetDevice')
def NetDevice():
    return make_nvr_manager_response({"result": service.NetDevice()})

@iot_433.route('/AddDevice')
def AddDevice():
    return make_nvr_manager_response({"result": service.AddDevice(request.args.get('DeviceId'))})

@iot_433.route('/DelDevice')
def DelDevice():
    return make_nvr_manager_response({"result": service.DelDevice(request.args.get('DeviceId'))})

@iot_433.route('/SendData',methods=['POST'])
def SendData():
    return make_nvr_manager_response({"result": service.SendData(request.json)})

@iot_433.route('/GetDeviceData')
def GetDeviceData():
    return make_nvr_manager_response({"result": service.GetDeviceData(request.args.get('DeviceId'))})