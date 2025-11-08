import os
import datetime
import json

from config import config
from base.init import init
from base.scheduler import scheduler
from base.mqtt import get_mqtt_service
from base.logger import get_logger

from .connect.connect_433 import *
from .connect.data_process import *



'''
connect.connect_433函数说明:
    def GetOnceFrame(CheckClash=False)
        功能:获取一帧收到的数据
        参数:
            CheckClash 是否在冲突后发送冲突广播
            因为紧急情况(非入网时)下可能会一直检测到冲突，不需要处理
        返回值:
            None 433模块未收到数据
            list 存储一帧数据的列表,一个元素对应帧中的一个字节
    def SendFrame(senddata)
        功能:通过433模块发送一帧数据
        senddata:
            list 存储一帧数据的列表,一个元素对应帧中的一个字节,不包括CRC校验码
    def init_433(gateway_id=0xFFFF, channel_id=0x00)
        功能:初始化433模块,启动接收监听线程
        参数:
            gateway_id:指定网关ID,即网关在组网中的地址
            channel_id:指定网关初始化信道,即网关在组网中的地址
    def GetCleanChannel(timeout=2):
        功能:获取433模块的一个干净信道
        timeout:
            检测一个信道是否干净的时间,从该信道timeout秒没有收到数据,则视为干净
    def ChangeChannel(channel_id=0x00):
        功能:切换433模块的信道
        channel_id:
            0~40代表蜂鸟433所有信道
            0表示选择最低频率信道,多网关时为默认信道(单网关节点设备的默认信道是0)
    def close_433()
        功能:关闭433模块,释放接收监听线程

帧格式:
	帧头       帧长度    发送设备地址码    接收设备地址码   操作码(帧类型)   数据(帧负载)	 CRC校验码
	head       length       sender         receiver        operator         data          CRC
  (0xA5A5)    (2bytes)     (2bytes)        (2bytes)        (2bytes)        帧长-12      (2bytes)

'''
CmdLock = threading.Lock()  # 发送指令的函数执行前一定要先获取锁
GatewayType = 0             # 0:单网关 1:多网关
GatewayId = 0xFFFF          # 网关ID
ChannelID = 0x00            # 433通信模块当前信道
NearbyDeviceList = []       # 存储未入网设备:设备类型(0~256)和设备号(0~256)
NetDeviceList = []          # 已入网设备ID:设备在组网中编号(地址0~1000，暂时只支持1000设备)
NetDeviceMap = [None]*1000  # key:已入网设备ID value:设备类型和设备号
NetAddressList = [False]*1000   # False表示该NetId尚未使用(分配)
HeartCountList = [None]*1000    # key:已入网设备ID value:入网设备未回复心跳数,30次未回复删除设备
NetDeviceElectricityList = [None]*1000  # 临时存储设备电量
HeartFlag = False   #用于结束心跳线程的标志位
NetDeviceNewestDataMap = {}

InitFlag = False
_logger = get_logger('iot433')

def SendHeartBeat(DeviceAddress):
    # 向一个设备发送心跳，会被心跳保持线程(KeepHeart)调用
    # head length sender receiver 0x0300 CRC
    # head length sender receiver 0x0301 电量(2byte) 设备状态(2byte) CRC
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, 0x00, 12, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x03, 0x00]
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300)
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()   # 获取锁，同一时刻433模块只能进行一种指令操作
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)    # 延时10ms
        data = GetOnceFrame()   # 获取此时接收到的一帧完整数据
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x03 and data[9] == 0x01:
                CmdLock.release()   # 释放锁，让433模块能够执行其他操作
                # print('device %d keep heartbeat!!!' % (DeviceAddress))
                del data[:10:]   # 去除帧头
                data.pop()       # 去除CRC校验
                data.pop()
                return data      # 包含电量和设备状态的四字节数据，在KeepHeart线程中会处理
    CmdLock.release()
    return None


def SendTransparentData(DeviceAddress, Data):
    # 向设备透传数据，DeviceAddress是设备网络号
    # head length sender receiver 0x0700 Data CRC
    # head length sender receiver 0x0701 CRC
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, (12+len(Data))//256, (12+len(Data))%256, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x07, 0x00]
#     cmd = [0xA5, 0xA5, 0x00, 15, GatewayId//256, GatewayId %
#            256, DeviceAddress//256, DeviceAddress % 256, 0x05, 0x02,
#            SwitchType, SwitchId, Operate]
    cmd = cmd + Data
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300) + 3000
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x07 and data[9] == 0x01:
                CmdLock.release()
                return True
    CmdLock.release()
    return False


def GetSensorData(DeviceAddress, SensorType, SensorId):
    # 获取设备传感器数据，DeviceAddress是设备网络号 注:SensorId{1,2}表示设备的485编号
    # head length sender receiver 0x0400 传感器设备类型(2bytes) 设备编号(2bytes) CRC
    # head length sender receiver 0x0401 数据长度(2bytes) 传感器数据(length-12) CRC
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, 0x00, 16, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x04, 0x00,
           SensorType//256, SensorType % 256,
           SensorId//256, SensorId % 256]
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300) + 3000
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x04 and data[9] == 0x01:
                CmdLock.release()
                del data[:10:]   # 去除帧头
                data.pop()   # 去除CRC校验
                data.pop()
                # 返回值格式 数据长度(2bytes) 传感器数据(length-12)
                return data
    CmdLock.release()
    return None


def SetSensorConfigure(DeviceAddress, SensorType, SensorId, SensorPeriod):
    # 设置传感器参数，目前只有周期(大多数情况下无需调用，使用默认参数即可)
    # head length sender receiver 0x0402 传感器设备类型(2bytes) 设备编号(2bytes) 采样周期(2bytes) CRC
    # head length sender receiver 0x0403 CRC
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, 0x00, 18, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x04, 0x02,
           SensorType//256, SensorType % 256, SensorId//256, SensorId % 256,
           SensorPeriod//256, SensorPeriod % 256]
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300)
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x04 and data[9] == 0x03:
                CmdLock.release()
                return True
    CmdLock.release()
    return False

def SwitchOperate(DeviceAddress, SwitchType, SwitchId, Operate):
    # 	开关类型:	0: 电磁阀     1: 强电开关
	#	开关编号:	0: 所有开关   n: 第n个开关
	#	开关操作:	0: 关 		  1: 开 
	#	开关状态:	0: 关         1: 开
    # head length sender receiver 0x0502 开关类型(1byte) 开关编号(1byte) 开关操作(1byte) CRC
    # head length sender receiver 0x0503 CRC
    global GatewayId, CmdLock
    # print("开关")
    cmd = [0xA5, 0xA5, 0x00, 15, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x05, 0x02,
           SwitchType, SwitchId, Operate]
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300) + 3000
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x05 and data[9] == 0x03:
                CmdLock.release()
                return True
            else:
                print('receive', data)
    else:
        print('chaoshi')
    CmdLock.release()
    return False


def GetSwitchState(DeviceAddress, SwitchType, SwitchId):
    # 	开关类型:	0: 电磁阀     1: 强电开关
	#	开关编号:	0: 所有开关   n: 第n个开关
	#	开关操作:	0: 关 		  1: 开
	#	开关状态:	0: 关         1: 开
    # head length sender receiver 0x0500 开关类型(1byte) 开关编号(1byte) CRC
    # head length sender receiver 0x0501 CRC
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, 0x00, 14, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x05, 0x00,
           SwitchType, SwitchId]
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300) + 3000
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x05 and data[9] == 0x01:
                CmdLock.release()
                del data[:10:]   # 去除帧头
                data.pop()   # 去除CRC校验
                data.pop()
                # len(data)表示一共有多少个开关,data[i]表示第i个开关的状态
                return data
    else:
        print('****************chaoshi')
    CmdLock.release()
    return None


def SetOTAInfo(DeviceAddress, OTAVersion, OTALength, OTAMd5Check):
    # 在设备接收升级包之前发送升级包版本号,长度,校验码等信息
    # *******无需直接调用会被DeviceOTAUpdate调用
    # head length sender receiver 0x0600 版本号(4bytes) 总长度byte(4bytes) md5校验码(32bytes) CRC
    # head length sender receiver 0x0601 CRC
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, 0x00, 52, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x06, 0x00]
    # 如果OTAVersion是四字节数组 则运算为 cmd=cmd+OTAVersion
    cmd.append(OTAVersion//(2 ** 24))
    OTAVersion = OTAVersion % (2 ** 24)
    cmd.append(OTAVersion//(2 ** 16))
    OTAVersion = OTAVersion % (2 ** 16)
    cmd.append(OTAVersion//(2 ** 8))
    cmd.append(OTAVersion % (2 ** 8))
    # 如果OTALength是四字节数组 则运算为 cmd=cmd+OTALength
    cmd.append(OTALength//(2 ** 24))
    OTALength = OTALength % (2 ** 24)
    cmd.append(OTALength//(2 ** 16))
    OTALength = OTALength % (2 ** 16)
    cmd.append(OTALength//(2 ** 8))
    cmd.append(OTALength % (2 ** 8))
    # 添加校验和
    # list(map(ord, list(OTAMd5Check))) 将字符串转化为二进制数
    cmd = cmd+list(map(ord, list(OTAMd5Check)))
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300)
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x06 and data[9] == 0x01:
                CmdLock.release()
                # Stm32设备Flash擦除需要时间比较长
                # 因为设备执行Flash操作,此时好像关闭了中断，无法接收433数据，所以要等1S等设备完成Flash操作
                # 让设备反映一段时间再执行OTA升级的后续部分
                time.sleep(3)
                return True
    CmdLock.release()
    return False


def SendOTAOnceFrame(DeviceAddress, OTAOffset, OTAFrameLength, OTAFrameData):
    # 向设备发送升级包的一帧数据长度是512 bytes,设备会对比偏移和自身偏移不符合则丢弃
    # ******无需直接调用会被DeviceOTAUpdate调用
    # head length sender receiver 0x0602 偏移bytes(4bytes) 大小bytes(4bytes) data(length-20bytes) CRC
    # head length sender receiver 0x0603 CRC
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, (OTAFrameLength+20)//256, (OTAFrameLength+20) % 256, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x06, 0x02]
    # 如果OTAOffset是四字节数组 则运算为 cmd=cmd+OTAOffset
    cmd.append(OTAOffset//(2 ** 24))
    OTAOffset = OTAOffset % (2 ** 24)
    cmd.append(OTAOffset//(2 ** 16))
    OTAOffset = OTAOffset % (2 ** 16)
    cmd.append(OTAOffset//(2 ** 8))
    cmd.append(OTAOffset % (2 ** 8))
    # 如果OTAFrameLength是四字节数组 则运算为 cmd=cmd+OTAFrameLength
    cmd.append(OTAFrameLength//(2 ** 24))
    OTAFrameLength = OTAFrameLength % (2 ** 24)
    cmd.append(OTAFrameLength//(2 ** 16))
    OTAFrameLength = OTAFrameLength % (2 ** 16)
    cmd.append(OTAFrameLength//(2 ** 8))
    cmd.append(OTAFrameLength % (2 ** 8))
    # 添加校验和
    cmd = cmd+list(OTAFrameData)
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300)
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x06 and data[9] == 0x03:
                CmdLock.release()
                return True
    CmdLock.release()
    return False


def CheckOTAInfo(DeviceAddress):
    #   向设备发送完升级包后，咨询设备升级包是否正确
    #   在设备发送接收正确后，重启升级
    #   *******无需直接调用会被DeviceOTAUpdate调用
    # 	head length sender receiver 0x0604  CRC
    # 	head length sender receiver 0x0605 结果码 CRC
    # 	结果码: 0 未收到完整升级包或Md5校验码不符合
    #           1 收到完整升级包并且Md5校验码符合，回复后开始升级
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, 0x00, 12, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x06, 0x04]
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300)
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x06 and data[9] == 0x05:
                CmdLock.release()
                del data[:10:]   # 去除帧头
                data.pop()       # 去除CRC校验
                data.pop()
                return data  # 返回结果码 0:设备未准备好升级 1:设备准备好升级
    CmdLock.release()
    return None


def GetDeviceVersion(DeviceAddress):    # GetOTAVersion
    #   查询设备版本号，新烧录的版本号默认是1.0.0
    # 	head length sender receiver 0x0606 CRC
    # 	head length sender receiver 0x0607 版本号(4 bytes) CRC
    global GatewayId, CmdLock
    cmd = [0xA5, 0xA5, 0x00, 12, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x06, 0x06]
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300)
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x06 and data[9] == 0x07:
                CmdLock.release()
                del data[:10:]   # 去除帧头
                data.pop()       # 去除CRC校验
                data.pop()
                return data  # 版本号(4 bytes)
    CmdLock.release()
    return None


def DeviceOTAUpdate(DeviceAddress, OTAVersion, OTALength, OTAMd5Check, OTAData):
    # 执行设备升级的操作，返回True升级成功 False则升级失败
    """
    ****************升级示意代码****************
    file_contents = None
    with open(r'OTA.bin', 'rb') as f:
        file_contents = f.read()
    if file_contents != None:
        file_len = len(file_contents)
        md5sum = hashlib.md5(file_contents).hexdigest()
        print(file_len, md5sum, len(md5sum))
        BeforeOTATime = datetime.datetime.now()
        # 默认版本号1.0.0 所以如果升级后，注意版本号一定要比旧版本号大
        # 第一个参数是设备网络ID,第二个参数是升级包版本号
        DeviceOTAUpdate(0, 0x00010001, file_len, md5sum, file_contents)
        print("Before OTA Update:", BeforeOTATime)
        print("After OTA Update:", datetime.datetime.now())
    """
    RunVersion = GetDeviceVersion(DeviceAddress)    # 获取设备版本号
    tempRunVersion = 0
    for i in RunVersion:
        tempRunVersion = tempRunVersion*256+i
    if tempRunVersion >= OTAVersion:    # 比较OTA版本和设备版本
        print('OTA Version %s is not higher than device Run Version %s, Update exit!!!' %(OTAVersion, tempRunVersion))
        return False
    # 在传送OTA升级包之前，向设备发送OTA版本号，数据长度，校验码等信息
    if not SetOTAInfo(DeviceAddress, OTAVersion, OTALength, OTAMd5Check):
        print('OTA Info Set False, Update exit!!!!')
        return False
    OTATryCount = 0
    OTAOffset = 0
    while OTALength != 0:
        if OTATryCount >= 5:
            print('OTA Send Frame timeout, Update exit!!!!')
            return False
        FrameLen = OTALength     # 剩余长度小于512个字节直接发剩余的所有字节
        if OTALength >= 512:    # 剩余长度大于512个字节直接发512个字节
            FrameLen = 512
        if SendOTAOnceFrame(DeviceAddress, OTAOffset, FrameLen, OTAData[OTAOffset:OTAOffset+FrameLen:]):
            OTALength = OTALength-FrameLen
            OTAOffset = OTAOffset+FrameLen
            OTATryCount = 0
        else:
            OTATryCount += 1
    # 因为设备接收完最后一帧后需要执行Flash(进行写OTA信息到Flash参数区域)操作,
    # 此时好像关闭了中断，无法接收433数据，所以要等1S等设备完成Flash操作
    time.sleep(1)
    # 询问设备是否收到完整且校验正确的升级包
    ret = CheckOTAInfo(DeviceAddress)
    if ret == None or ret == 0:
        print('OTA Deivce info is error , Update False!!!!')
        return False
    else:
        print('OTA %d Device update success!!!' % DeviceAddress)
        return True
    return False


def FindNearbyDevice(timeout=5):
    # 默认广播5S发现新设备，如果老是发生冲突(设备较多)，应该将timeout的值设置大一些
    # head length sender receiver 0x0100 广播等待时间(2bytes) CRC
    # head length sender receiver 0x0101 设备类型(2byte) 设备号(2byte) CRC
    global GatewayId, CmdLock, NearbyDeviceList
    global ChannelID, GatewayType
    global KeepHeartThreadSuspendFlag
    KeepHeartThreadSuspendFlag = True   # 挂起心跳位置线程(因为多网关要把设备切换到最低频率)
    if ChannelID != 0:
        ChangeChannel()  # 将通信信道切换到最低频率信道，即设备重置后的信道
    cmd = [0xA5, 0xA5, 0x00, 14, GatewayId//256, GatewayId %
           256, 0x00, 0x00, 0x01, 0x00, timeout//256, timeout % 256]
    if GatewayType == 1:
        cmd[8] = 0x02
    timeout = timeout*100  # 求出需要多少个10ms
    NearbyDeviceList.clear()  # 清空附近设备列表
    tempDeviceList = []  # 临时设备列表
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        # 广播查找未入网设备时，开启冲突检测(检测到冲突后发送冲突广播)
        data = GetOnceFrame(CheckClash=True)
        # if data != None:  # 调试使用
        #     print('data:', data)
        if data != None:
            if data[6]*256+data[7] == GatewayId and (data[8] == 0x01 or data[8] == 0x02) and data[9] == 0x01:
                devicetype = data[10]*256+data[11]
                deviceid = data[12]*256+data[13]
                # 因为广播冲突后，设备可能重复发送设备信息，所以网关需要过滤掉
                if devicetype*65536+deviceid not in NearbyDeviceList: # 65536=256*256
                    result = {'deviceId':devicetype*65536+deviceid,'devicetype':devicetype}
                    tempDeviceList.append(result)
                    NearbyDeviceList.append(devicetype*65536+deviceid)  
    CmdLock.release()
    if ChannelID != 0:
        ChangeChannel(ChannelID)  # 添加失败，恢复为多网关通信信道
    KeepHeartThreadSuspendFlag = False   # 恢复挂起心跳位置线程
    return tempDeviceList

def AddDeviceToNet(NearbyDevice):
    # 将附近设备列表中的设备添加到433网络中
    # head length sender receiver 0x0102 设备类型(2byte) 设备号(2byte) 设备地址 CRC
    # head length sender receiver 0x0103 CRC
    global NetAddressList, NearbyDeviceList, NetDeviceList, NetDeviceMap
    global ChannelID, GatewayType, NetDeviceNewestDataMap
    if NearbyDevice not in NearbyDeviceList:
        print('NearbyDevice %d not in NearbyDeviceList' %NearbyDevice)  # 所有网络编号都已经被分配给设备
        return
    NetId = 0
    for i in range(1000):
        if not NetAddressList[i]:
            NetId = i
            break
    else:
        print('All NetId are used!!!')  # 所有网络编号都已经被分配给设备
        return
    global KeepHeartThreadSuspendFlag
    KeepHeartThreadSuspendFlag = True
    if ChannelID != 0:
        ChangeChannel()  # 将通信信道切换到最低频率信道，即设备重置后的信道
        time.sleep(0.3)    # 加个延时,不然会出现节点设备已经发送，网关接收不到
    devicetype = NearbyDevice//65536  # 65536=256*256
    deviceid = NearbyDevice % 65536
    print(deviceid)
    print(NearbyDevice)
    cmd = [0xA5, 0xA5, 0x00, 18, GatewayId//256, GatewayId %
           256, 0x00, 0x00, 0x01, 0x02, devicetype//256, devicetype % 256,
           deviceid//256, deviceid % 256, NetId//256, NetId % 256]
    if GatewayType == 1:
        cmd[8] = 0x02
        cmd[3] = 19
        cmd.append(ChannelID)
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加500ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+500) + 3000
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == NetId and data[6]*256+data[7] == GatewayId and (data[8] == 0x01 or data[8] == 0x02) and data[9] == 0x03:
                CmdLock.release()
                NearbyDeviceList.remove(NearbyDevice)  # 从未入网设备中删除当前设备
                NetAddressList[NetId] = True   # 当前网络ID标为已分配
                NetDeviceList.append(NetId)  # 将当前网路ID加入到入网设备列表
                NetDeviceMap[NetId] = NearbyDevice  # 添加网络ID到设备的映射
                HeartCountList[NetId] = 0
                NetDeviceNewestDataMap[str(NearbyDevice)] = {'DeviceId':NearbyDevice}
                data = {}
                data['485_1']=[]
                data['485_2']=[]
                NetDeviceNewestDataMap[str(NearbyDevice)]['time'] = str(datetime.datetime.now())
                NetDeviceNewestDataMap[str(NearbyDevice)]['data'] = data
                if GatewayType == 1:
                    ChangeChannel(ChannelID)  # 添加失败，恢复为多网关通信信道
                KeepHeartThreadSuspendFlag = False
                add_device(NearbyDevice)
                return True   # 添加至网络
    CmdLock.release()
    if ChannelID != 0:
        ChangeChannel(ChannelID)  # 添加失败，恢复为多网关通信信道
    KeepHeartThreadSuspendFlag = False
    return False  # 超时未回复


def DeleteDeviceFromNet(DeviceAddress):
    #  从433网络中删除设备
    #  GatewayType: 0 单网关  1 多网关
    #  head length sender receiver 0x0106 CRC
    #  head length sender receiver 0x0107 CRC
    global GatewayId, CmdLock, GatewayType, NetDeviceMap
    cmd = [0xA5, 0xA5, 0x00, 12, GatewayId//256, GatewayId %
           256, DeviceAddress//256, DeviceAddress % 256, 0x03, 0x06]
    # 发送一个字节需要1.5ms 收发需要(len(cmd)+2)*1.5*2ms,再加300ms的单片机处理时间
    timeout = int((len(cmd)+2)*1.5*2+300)
    timeout = timeout//10  # 求出需要多少个10ms
    CmdLock.acquire()
    SendFrame(cmd)
    for i in range(timeout):
        time.sleep(0.01)
        data = GetOnceFrame()
        if data != None:
            if data[4]*256+data[5] == DeviceAddress and data[6]*256+data[7] == GatewayId and data[8] == 0x03 and data[9] == 0x07:
                CmdLock.release()
                NetAddressList[DeviceAddress] = False   # 当前网络ID标为已分配
                NetDeviceList.remove(DeviceAddress)  # 将当前网路ID加入到入网设备列表
                HeartCountList[DeviceAddress] = 0
                NetDeviceNewestDataMap.pop(str(NetDeviceMap[DeviceAddress]))
                remove_device(GatewayId)
                return True
    CmdLock.release()
    return False

def KeepHeart():
    global HeartFlag
    global NetAddressList, NearbyDeviceList, NetDeviceList
    global HeartCountList, NetDeviceMap, NetDeviceNewestDataMap
    global KeepHeartThreadSuspendFlag
    # print('KeepHeart Thread Start')
    timecount = 0
    while HeartFlag:    # HeartFlag被设置为False是结束线程
        timecount = timecount + 1
        if timecount == 60:
            timecount = 0
            for device in NetDeviceList:
                data = {}
                data['485_1']=[]
                data['485_2']=[]
                # 获取设备485_1的传感器编号
                SensorId=GetSensorId(NetDeviceMap[device]//65536, 1)
                if  SensorId!=None:
                    # print("**************1*********************", SensorId)
                    # print(GetSensorData(device, SensorId, 1))
                    data['485_1'] = DataProcess(SensorId,GetSensorData(device, SensorId, 1))
                # print("******************2*****************")
                # print(data['485_1'])
                # 获取设备485_2的传感器编号
                SensorId=GetSensorId(NetDeviceMap[device]//65536, 2)
                if  SensorId!=None:
                    data['485_2'] = DataProcess(SensorId,GetSensorData(device, SensorId, 2))
                if data['485_1'] != []  or data['485_2'] != []:
                    # device 属于[0,1000]网络号
                    # NetDeviceMap(device) = 设备类型*2^16+设备编号
                    NetDeviceNewestDataMap[str(NetDeviceMap[device])]['time'] = str(datetime.datetime.now())
                    NetDeviceNewestDataMap[str(NetDeviceMap[device])]['data'] = data
                    pass
        if len(NetDeviceList) == 0:
            time.sleep(1)
            # print('no device send heart')
        else:
            # 多网关搜索设备和添加设备入网时将会把设备切换到最低频段
            # 所以此时挂起线程
            if not KeepHeartThreadSuspendFlag:
                for device in NetDeviceList:
                    # 心跳之间的延时控制在所有设备总延时1s
                    time.sleep(1/len(NetDeviceList))
                    data = SendHeartBeat(device)
                    if data != None:
                        HeartCountList[device] = 0
                        NetDeviceElectricityList[device] = data[0]*256+data[1]
                        if data[2]*256+data[3] != 0:
                            # 设备状态码不为0
                            # 处理异常信息
                            pass
                    else:
                        HeartCountList[device] = HeartCountList[device]+1
                        # print('heart count %d is %d' %(device, HeartCountList[device]))
                        if HeartCountList[device] >= 20:  # 20次未回复,20秒(因为升级需要十几秒)
                            print('heart count %d is %d, and remove device!!!' %
                                (device, HeartCountList[device]))
                            NetAddressList[device] = False   # 当前网络ID标为已分配
                            NetDeviceList.remove(device)  # 将当前网路ID加入到入网设备列表
                            HeartCountList[device] = 0
                        pass  # data为设备电量
    else:
        print('KeepHeart Thread Stop Running!!!')

def Init(gateway_id=0xFFFF, gatewaytype=0):
    #  gatewaytype: 0 单网关  1 多网关
    global KeepHeartThread, HeartFlag
    global KeepHeartThreadSuspendFlag
    global GatewayId, ChannelID, GatewayType
    if 'KeepHeartThread' in globals():
        close() # 如果已经初始化过，则关闭之前初始化的内容
    GatewayType=gatewaytype
    if not isinstance(gateway_id, int) or gateway_id < 0 or gateway_id > 0xFFFF:
        print('网关ID不合法,请选择0~0xFFFF之间的数字!!!!!!!!!')
        gateway_id = 0xFFFF
    GatewayId = gateway_id
    if GatewayType == 0:
        if init_433(GatewayId) == False:  # 初始化433模块
            return False
    else:
        ChannelID = GetCleanChannel() # 监听并找到一个干净的信道作为组网通信信道
        print("Get clear channel %d" %ChannelID)
        if init_433(GatewayId, ChannelID) == False:
            return False

    HeartFlag = True
    KeepHeartThreadSuspendFlag = False # 初始为不挂起
    KeepHeartThread = threading.Thread(target=KeepHeart)
    KeepHeartThread.start()  # 调试代码，暂时关闭心跳
    return True

def close():
    global NetDeviceList
    # 获取已入网的设备列表
    TempNetDeviceList = NetDeviceList.copy()
    print("Delete Devices From Net:",TempNetDeviceList)
    for i in TempNetDeviceList:
        DeleteDeviceFromNet(i)  # 删除已入网设备，让设备恢复初始化状态
    global HeartFlag,KeepHeartThread
    if 'KeepHeartThread' in globals() and 'HeartFlag' in globals():   # 已经定义
        HeartFlag = False
        while KeepHeartThread.is_alive():
            time.sleep(0.1)
    print("Close Gateway, Release KeepHeartThread!!!")
    close_433() # 关闭串口和接收线程

@init
def _init():
    global InitFlag
    os.system('chmod 777  /dev/ttyS6')
    os.system('chmod 777  /sys/class/gpio/export')
    os.system('chmod 777 /sys/class/gpio/unexport')
    os.system('echo 141 > /sys/class/gpio/export > /dev/null 2>&1')
    os.system('echo 140 > /sys/class/gpio/export > /dev/null 2>&1')
    os.system('chmod 777  /sys/class/gpio/gpio141/direction')
    os.system('chmod 777  /sys/class/gpio/gpio140/direction')
    os.system('chmod 777  /sys/class/gpio/gpio141/value')
    os.system('chmod 777  /sys/class/gpio/gpio140/value')
    InitFlag = Init()
    print('InitFlag', InitFlag)

def FindDevice(Timeout):
    result = []
    if Timeout is not None:
        result=FindNearbyDevice(int(Timeout))
    else:
        result=FindNearbyDevice()
    return result

def NetDevice():
    result=[]
    global NetDeviceList, NetDeviceMap
    for i in NetDeviceList:
        devicetype = NetDeviceMap[i]//65536  # 65536=256*256
        deviceid = NetDeviceMap[i] % 65536
        result.append({'deviceId':devicetype*65536+deviceid,'devicetype':devicetype})
    return result

def AddDevice(DeviceId):
    result = []
    DeviceId = int(DeviceId)
    if DeviceId != None:
        for i in NetDeviceList:
            if NetDeviceMap[i]==DeviceId:  # 设备号DeviceId转化为网络号i
                # 设备已连接
                result.append(True)
                return result
        if AddDeviceToNet(DeviceId):
            result.append(True)
        else:
            result.append(False)
    else:
        result.append(False)
    return result

def DelDevice(DeviceId):
    global NetDeviceList,NetDeviceMap
    result=[]
    DeviceId = int(DeviceId)    # 设备号
    if DeviceId != None:
        for i in NetDeviceList:
            if NetDeviceMap[i]==DeviceId:  # 设备号DeviceId转化为网络号i
                if DeleteDeviceFromNet(i):
                    result.append(True)
                else:
                    result.append(False)
                break
    else:
        result.append(False)
    return result

def SendData(jsonData):
    global NetDeviceList,NetDeviceMap
    result=[]
    DeviceId = int(jsonData['DeviceId'])    # 设备号
    serveMark = int(jsonData['serveMark']) # 通道
    Data = jsonData['Data']    # 数据
    if DeviceId != None:
        for i in NetDeviceList:
            if NetDeviceMap[i]==DeviceId:  # 设备号DeviceId转化为网络号i
                if type(Data) == list and SendTransparentData(i, Data):
                    result.append(True)
                else:
                    result.append(False)
                break
    else:
        result.append(False)
    return result

def GetDeviceData(DeviceId):
    global NetDeviceList,NetDeviceMap, NetDeviceNewestDataMap
    DeviceId = int(DeviceId)    # 设备号
    if DeviceId != None:
        for i in NetDeviceList:
            if NetDeviceMap[i]==DeviceId:  # 设备号DeviceId转化为网络号i
                # switch_states = GetSwitchState(i, 0, 0)
                # NetDeviceNewestDataMap['switch1'] = switch_states[0]
                # NetDeviceNewestDataMap['switch2'] = switch_states[1]
                temp = NetDeviceNewestDataMap[str(DeviceId)]
                temp['switchstate'] = GetSwitchState(i, 0, 0)
                print('test***********', temp['switchstate'])
                json_str = json.dumps(temp)
                # print(temp)
                # print(json_str)
                _logger.warning(f'发送json消息 {json_str}')
                new_data ={
                    'data':json_str
                }
                return new_data
    else:
        return {}
    return {}

def _report_data():
    for dev in NetDevice():
        devid = dev['deviceId']
        get_mqtt_service().report_433_data(devid, GetDeviceData(devid))

@init
def _add_report_job():
    _logger.debug('433数据定时上报任务已添加')
    scheduler.add_job(_report_data, 'interval', max_instances=1, seconds=config._IOT433_REPORT_DATA_INTERVAL)
    _logger.warning(f'发送mqtt消息{_report_data}')



# 这里面保存取消订阅函数
unsub_funcs = {}

# 接收mqtt消息 device_id = 设备号
def add_device(device_id):
    global NetDeviceList, NetDeviceMap

    channel = 'cmd'
    # 处理消息
    def process_command(data: dict):
    # 从消息中获取设备地址、开关类型、开关编号和操作
        _logger.warning(f'收到mqtt消息{data}')
        print(device_id,'收到命令：',data)

        for i in NetDeviceList:
            # devicetype = NetDeviceMap[i]//65536  # 65536=256*256
            # deviceid = NetDeviceMap[i] % 65536
         
            if NetDeviceMap[i] == device_id:
                print(f"deivceid: {device_id} 索引: {i}")
                SwitchType = data.get('switch_type')
                SwitchId = data.get('switch_id')
                Operate = data.get('operate')
                CmdId = data.get('cmdId')
                # 调用SwitchOperate函数处理消息
                result = SwitchOperate(i, SwitchType, SwitchId, Operate)
                response = None
                if result: 
                    response = {
                        "id": CmdId,
                        "code": 200,
                        "data":{}
                    }
                else:
                    response = {
                        "id": CmdId,
                        "code": 500,
                        "data":{}
                    }
                print("回复命令:",response)
                get_mqtt_service().report_433_command_feedback(device_id, channel, response)
                return json.dumps(response)
        print("处理结束")

    #订阅函数，用on connected装饰器是为了能在切换MQTT协议时自动重新订阅
    @get_mqtt_service().on_connected
    def subdevice():
        # 订阅函数的返回值是取消订阅函数的回调函数
        # unsub_funcs[device_id] = get_mqtt_service().subscribe_433_command(device_id, channel, process_command)
        
        result = get_mqtt_service().subscribe_433_command(device_id, channel, process_command)
        print(f"回调函数返回值：{result}")
        unsub_funcs[device_id] = result

    # print("消息结束")
    subdevice()

def remove_device(device_id):
    unsub_funcs[device_id]()
