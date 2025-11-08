import onvif
import time
import logging

import threading
from typing import Any, Iterable, Optional


# 去除掉root上的所有hdlr，不然日志很乱
for hdlr in logging.root.handlers:
    logging.root.removeHandler(hdlr)

class _BasePTZController:

    def __init__(self, ptz_svc: onvif.ONVIFService, token: str, support_move: bool, support_zoom: bool):
        self._ptz_svc = ptz_svc
        self._token = token
        self._support_move = support_move
        self._support_zoom = support_zoom
    
    def move(self, translation: Iterable[float]):
        pass

    def support_move(self) -> bool:
        return self._support_move 

    def support_zoom(self) -> bool:
        return self._support_zoom 
    
    def _generate_ptzvector(self, translation: Iterable[float]) -> dict:
        if translation is None or not any(translation):
            return None
        
        ptzvector = {}
        if self.support_move() and any(translation[:2]):
            ptzvector['PanTilt'] = {
                'x': translation[0],
                'y': translation[1]
            }

        if self.support_zoom() and translation[2]:
            ptzvector['Zoom'] = {
                'x': translation[2]
            }

        return ptzvector or None

class _RelativePTZController(_BasePTZController):

    def __init__(self, ptz_svc: onvif.ONVIFService, token: str, support_move: bool, support_zoom: bool):
        super().__init__(ptz_svc, token, support_move, support_zoom)
        
    def move(self, translation: Iterable[float]):
        if translation is None or not any(translation):
            return
        
        ptzvector = self._generate_ptzvector(translation)
        if not ptzvector:
            return

        self._ptz_svc.RelativeMove({
            'ProfileToken': self._token,
            'Translation': ptzvector,
            'Speed': self._generate_ptzvector([1., 1., 1.])  # 全部都以最大速度移动
        })

class _ContinuousPTZController(_BasePTZController):

    def __init__(self, ptz_svc: onvif.ONVIFService, token: str, support_move: bool, support_zoom: bool):
        super().__init__(ptz_svc, token, support_move, support_zoom)
        
    def move(self, translation: Iterable[float]):
        if translation is None or not any(translation):
            return
        
        def continuous_move():
            # 这里处理一个以最大速度移动的逻辑
            # 比如移动向量(0.4, 0.6, 0.4)需要1s移动完成，那么设scale=1/0.6，(0.4*scale, 0.6*scale, 0.4*scale)可以在保证三维移动方向不变的同时，缩短移动时间为1/scale，即0.6
            second = max(map(abs, translation))
            scale = 1 / second
        
            ptzvector = self._generate_ptzvector(tuple(map(lambda x: x*scale, translation)))
            if not ptzvector:
                return
            
            self._ptz_svc.ContinuousMove({
                'ProfileToken': self._token,
                'Velocity': ptzvector
            })
            time.sleep(second)
            self._ptz_svc.Stop({'ProfileToken': self._token})
        
        threading.Thread(target=continuous_move).start()

class _PTZService:

    def __init__(self, ptz_svc: Optional[onvif.ONVIFService]=None, ptz_token: Optional[str]=None, media_token: Optional[str]=None):
        self._ptz_controller = None

        if ptz_svc is None:
            return

        self._ptz_svc = ptz_svc
        self._media_token = media_token

        conf_opt_sapce = ptz_svc.GetConfigurationOptions({
            'ConfigurationToken': ptz_token
        }).Spaces

        # 判断以移动(pt)优先
        if conf_opt_sapce.ContinuousPanTiltVelocitySpace or conf_opt_sapce.ContinuousZoomVelocitySpace:
            self._ptz_controller = _ContinuousPTZController(
                ptz_svc, 
                media_token, 
                True if conf_opt_sapce.ContinuousPanTiltVelocitySpace else False, 
                True if conf_opt_sapce.ContinuousZoomVelocitySpace else False
            )
        elif conf_opt_sapce.RelativePanTiltTranslationSpace or conf_opt_sapce.RelativeZoomTranslationSpace:
            self._ptz_controller = _RelativePTZController(
                ptz_svc, 
                media_token, 
                True if conf_opt_sapce.RelativePanTiltTranslationSpace else False, 
                True if conf_opt_sapce.RelativeZoomTranslationSpace else False
            )

    def support_move(self) -> bool:
        return self._ptz_controller is not None

    def support_zoom(self) -> bool:
        return self._ptz_controller is not None and self._ptz_controller.support_zoom()
    
    def move(self, translation: Iterable[float]):
        if not self.support_move() and not self.support_zoom():
            return
        
        try:
            status = self._ptz_svc.GetStatus({'ProfileToken': self._media_token}).MoveStatus
            if all((status is None or status.lower() == 'idle' for status in (status.PanTilt, status.Zoom))):
                self._ptz_controller.move(translation)
        except:
            pass

class OnvifCamera:

    def __init__(self, ip: str, port: Any, username: str, password: str):
        # adjust_time认证时时间同步，不然即使账号密码都对，也会得到没有认证的异常
        self._camera = onvif.ONVIFCamera(ip, port, username, password, adjust_time=True)
        self._ip = ip
        self._port = int(port)
        self._username = username
        self._password = password
        self._mac = self._camera.devicemgmt.GetNetworkInterfaces()[0].Info.HwAddress  # 按理说可以获取到多张网卡，这里取第一张

        # 媒体服务
        self._media_svc = self._camera.create_media_service()
        media_profile = self._media_svc.GetProfiles()[0]
        self._media_token = media_profile.token

        # PTZ服务
        try:
            self._ptz_service = _PTZService(self._camera.create_ptz_service(), media_profile.PTZConfiguration.token, self._media_token)
        except onvif.ONVIFError:
            self._ptz_service = _PTZService()  # 连ptz_service都没有，直接建个空的对象

    def get_info(self) -> dict:
        # 设备信息
        dev_info = self._camera.devicemgmt.GetDeviceInformation()

        stream_uri = self._media_svc.GetStreamUri({
            'StreamSetup': {'Stream': 'RTP-Unicast', 'Transport': {'Protocol': 'RTSP'}},
            'ProfileToken': self._media_token
        })['Uri']

        return {
            'ip': self._ip,
            'port': self._port,
            'username': self._username,
            'password': self._password,

            # 设备信息
            'mac': self._mac,
            'manufacturer': dev_info.Manufacturer,
            'model': dev_info.Model,
            'firmware_version': dev_info.FirmwareVersion,
            'serial_number': dev_info.SerialNumber,
            'hardware_id': dev_info.HardwareId,

            # 视频流
            'source': f"rtsp://{self._username}:{self._password}@{stream_uri.replace('rtsp://', '')}" if self._username else stream_uri,

            'support_move': self._ptz_service.support_move(),
            'support_zoom': self._ptz_service.support_zoom()
        }

    def move(self, translation: Iterable[float]):
        self._ptz_service.move(translation)
