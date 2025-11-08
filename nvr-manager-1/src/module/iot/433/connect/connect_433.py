from driver.driver_433 import SerialInterface
import time
import threading

Gatewayid = 0xFFFF
UsartInitFlag = False
# /***** CRC余式表 *****/
crc_table = [
    0x0000, 0xc0c1, 0xc181, 0x0140, 0xc301, 0x03c0, 0x0280, 0xc241,
    0xc601, 0x06c0, 0x0780, 0xc741, 0x0500, 0xc5c1, 0xc481, 0x0440,
    0xcc01, 0x0cc0, 0x0d80, 0xcd41, 0x0f00, 0xcfc1, 0xce81, 0x0e40,
    0x0a00, 0xcac1, 0xcb81, 0x0b40, 0xc901, 0x09c0, 0x0880, 0xc841,
    0xd801, 0x18c0, 0x1980, 0xd941, 0x1b00, 0xdbc1, 0xda81, 0x1a40,
    0x1e00, 0xdec1, 0xdf81, 0x1f40, 0xdd01, 0x1dc0, 0x1c80, 0xdc41,
    0x1400, 0xd4c1, 0xd581, 0x1540, 0xd701, 0x17c0, 0x1680, 0xd641,
    0xd201, 0x12c0, 0x1380, 0xd341, 0x1100, 0xd1c1, 0xd081, 0x1040,
    0xf001, 0x30c0, 0x3180, 0xf141, 0x3300, 0xf3c1, 0xf281, 0x3240,
    0x3600, 0xf6c1, 0xf781, 0x3740, 0xf501, 0x35c0, 0x3480, 0xf441,
    0x3c00, 0xfcc1, 0xfd81, 0x3d40, 0xff01, 0x3fc0, 0x3e80, 0xfe41,
    0xfa01, 0x3ac0, 0x3b80, 0xfb41, 0x3900, 0xf9c1, 0xf881, 0x3840,
    0x2800, 0xe8c1, 0xe981, 0x2940, 0xeb01, 0x2bc0, 0x2a80, 0xea41,
    0xee01, 0x2ec0, 0x2f80, 0xef41, 0x2d00, 0xedc1, 0xec81, 0x2c40,
    0xe401, 0x24c0, 0x2580, 0xe541, 0x2700, 0xe7c1, 0xe681, 0x2640,
    0x2200, 0xe2c1, 0xe381, 0x2340, 0xe101, 0x21c0, 0x2080, 0xe041,
    0xa001, 0x60c0, 0x6180, 0xa141, 0x6300, 0xa3c1, 0xa281, 0x6240,
    0x6600, 0xa6c1, 0xa781, 0x6740, 0xa501, 0x65c0, 0x6480, 0xa441,
    0x6c00, 0xacc1, 0xad81, 0x6d40, 0xaf01, 0x6fc0, 0x6e80, 0xae41,
    0xaa01, 0x6ac0, 0x6b80, 0xab41, 0x6900, 0xa9c1, 0xa881, 0x6840,
    0x7800, 0xb8c1, 0xb981, 0x7940, 0xbb01, 0x7bc0, 0x7a80, 0xba41,
    0xbe01, 0x7ec0, 0x7f80, 0xbf41, 0x7d00, 0xbdc1, 0xbc81, 0x7c40,
    0xb401, 0x74c0, 0x7580, 0xb541, 0x7700, 0xb7c1, 0xb681, 0x7640,
    0x7200, 0xb2c1, 0xb381, 0x7340, 0xb101, 0x71c0, 0x7080, 0xb041,
    0x5000, 0x90c1, 0x9181, 0x5140, 0x9301, 0x53c0, 0x5280, 0x9241,
    0x9601, 0x56c0, 0x5780, 0x9741, 0x5500, 0x95c1, 0x9481, 0x5440,
    0x9c01, 0x5cc0, 0x5d80, 0x9d41, 0x5f00, 0x9fc1, 0x9e81, 0x5e40,
    0x5a00, 0x9ac1, 0x9b81, 0x5b40, 0x9901, 0x59c0, 0x5880, 0x9841,
    0x8801, 0x48c0, 0x4980, 0x8941, 0x4b00, 0x8bc1, 0x8a81, 0x4a40,
    0x4e00, 0x8ec1, 0x8f81, 0x4f40, 0x8d01, 0x4dc0, 0x4c80, 0x8c41,
    0x4400, 0x84c1, 0x8581, 0x4540, 0x8701, 0x47c0, 0x4680, 0x8641,
    0x8201, 0x42c0, 0x4380, 0x8341, 0x4100, 0x81c1, 0x8081, 0x4040,
]


def IsCompletion(index, templen, result):
    # 判断接收到的数据是否完整
    # 判断index索引位置开始templen长度的数据的CRC校验码是否是result
    crc = 0xFFFF            # 存储计算的校验码
    global ReceiveBuffer    # 存储接收数据的循环数组
    global BufferSize
    global crc_table
    for i in range(templen):
        crc = (crc >> 8) ^ crc_table[(crc ^ ReceiveBuffer[index]) & 0xff]
        index = (index+1) % BufferSize
    if crc == result:       # 判断计算的校验码和接收的校验码是否相同
        return True
    else:
        print("CRC %d Result %d" % (crc, result))
        return False


def GetCRC(checkdata):
    # 查表法计算crc
    crc = 0xFFFF
    templen = len(checkdata)
    for i in range(templen):
        crc = (crc >> 8) ^ crc_table[(crc ^ checkdata[i]) & 0xff]
    return crc

def SaveReceive():
    global dv
    global run_flag         # 用于结束接收线程的标志
    global ReceiveBuffer    # 存储接收数据的循环数组
    global Receive_Place    # 存储下一个新接收数据的存放位置
    global Decode_Place     # 存储未处理接收数据的存放位置
    global Timeout_Count    # 定义变量供GetOnceFrame函数使用
    global BufferSize       # 定义接收循环数组的大小
    # 初始化时会定义，用于挂起接收线程
    # 如果不挂起接收线程，无法判定是否初始化成功
    global ReceiveThreadSuspendFlag
    BufferSize = 8192
    ReceiveBuffer = [0]*BufferSize
    Receive_Place = 0
    Decode_Place = 0
    Timeout_Count = 0
    run_flag = True
    # print('Receive 433 Thread Start')
    if 'dv' in globals():   # 已经定义
        while run_flag:
            time.sleep(0.01)   # 1个字节发送用时约1ms，则5ms内一定没有收到一帧
            if not ReceiveThreadSuspendFlag:   # 切换信道的时候需要暂停接收线程接收数据
                if dv.ser.in_waiting != 0:
                    tempdata = dv.read(dv.ser.in_waiting)
                    templen = len(tempdata)
                    # print('receive len', templen)  调试用
                    for i in range(templen):
                        if (Receive_Place+1) % BufferSize == Decode_Place:
                            print('Server Busy!!!!')
                            time.sleep(0.5)  # 防止log输出频率过高
                        else:
                            ReceiveBuffer[Receive_Place] = tempdata[i]
                            Receive_Place = (Receive_Place+1) % BufferSize
        else:
            print('Receive Thread Stop Running!!!')


def GetCleanChannel(timeout=2):  # 默认每个信道的检测事件为2s
    global dv, UsartInitFlag     # 全局对象用于最后关闭资源
    if 'dv' not in globals():
        dv = SerialInterface()
        dv.open()
        UsartInitFlag = True
    elif not UsartInitFlag:
        dv.open()
        UsartInitFlag = True
    ListenCount = int(timeout/0.01) # 设置监听多长时间视为干净信道
    if ListenCount < 1:
        ListenCount = 1
    for channel_id in range(1,40):  # 从1开始，因为0信号为全局信道
        ChangeChannel(channel_id)   # 切换到信道channel_id
        tempdatalen = 0
        for i in range(ListenCount):
            time.sleep(0.01)
            if dv.ser.in_waiting != 0:
                tempdatalen = tempdatalen+len(dv.read(dv.ser.in_waiting))
                if tempdatalen > 50:    # 在监听时间内(默认2秒)收到50个字节，视为信道不干净
                    break
        else:
            return channel_id  # 检测时间内信道无数据
    return None


def ChangeChannel(channel_id=0x00):
    # 切换信道，用于多网关
    # 第12个字节 RF 信道 1Byte(0~40),每500kHZ为一个信道，即423.92至443.92MHZ,默认为20,即433.92
    print("Channel change to %d" %channel_id)
    cmd = [0xAA, 0x5A, 0x00, 0x00, 0x03, 0x30, 0x00, 0x1E, 0x00,
           0x04, 0x00, 0x00, 0x00, 0x00, 0x00, 0x12, 0x00]
    if channel_id < 0 or not isinstance(channel_id, int) or channel_id >= 40:
        print('channel is out of range, change to default 0')
        channel_id = 0
    cmd[11] = channel_id
    cmd.append(sum(cmd) % 256)  # CheckSum 1Byte(以上所有字节相加)保留低 8 位
    global ReceiveThreadSuspendFlag # 挂起接收线程，后续代码才能收到模块返回数据判断是否切换成功
    ReceiveThreadSuspendFlag = True

    global dv, UsartInitFlag     # 全局对象用于最后关闭资源
    if 'dv' not in globals():
        dv = SerialInterface()
        dv.open()
        UsartInitFlag = True
    elif not UsartInitFlag:
        dv.open()
        UsartInitFlag = True
    dv.setMode(0)
    while True:
        dv.write(cmd)
        time.sleep(0.5)
        if dv.ser.in_waiting != 0:
            data = dv.read(dv.ser.in_waiting)
            if (cmd[-1]+1) % 256 == data[-1]:   # 蜂鸟模块设置成功后，最后一个设置码会加1
                # print('433 module channel init success!!!!')
                break
            else:
                # print('433 module channel init fail, try again!!!')
                print(hex(cmd[-1]), data[-1])
    dv.setMode(1)
    ReceiveThreadSuspendFlag = False
    time.sleep(0.5)   # 延时0.5s让模块准备好(否则会出现接收不完整数据)，后面测试是否需要


def SendConflictBoardCast():
    # 当广播查询设备时，设备回复可能冲突，导致网关接收到不完整帧
    # 网关接收到不完整帧指令时，将会发出重传指令
    # 设备收到重传指令，重传1秒内发过的指令
    global Gatewayid
    senddata = [0xA5, 0xA5, 0x00, 0x0C, Gatewayid //
                256, Gatewayid % 256, 0x00, 0x00, 0x03, 0x05]
    crc = GetCRC(senddata)
    senddata.append(crc//256)
    senddata.append(crc % 256)
    global dv
    dv.write(senddata)
    # 	head length sender receiver 0x0104 CRC
    pass


def GetOnceFrame(CheckClash=False):
    global dv, UsartInitFlag     # 全局对象用于最后关闭资源
    if 'dv' not in globals():
        dv = SerialInterface()
        dv.open()
        UsartInitFlag = True
    elif not UsartInitFlag:
        dv.open()
        UsartInitFlag = True
    global ReceiveBuffer
    global Receive_Place    # 下一个接收数据存放位置，即最后一个接收数据的下一个位置
    global Decode_Place     # 第一个未解析的接收数据的位置
    global Timeout_Count    # 用于计时当前不完整帧持续的时间
    global BufferSize
    LastPlace = Decode_Place
    if Decode_Place == Receive_Place:
        return None  # 未收到指令不用处理
    LastPlace += 1  # 后面会判断遇见帧头终止，而当前位置恰好有个帧头，所以会出现问题，需要避免检查当前帧头
    tempcount = 0
    while LastPlace != Receive_Place :
        if ((LastPlace+BufferSize)-Decode_Place)%BufferSize==8:
            # 需要避免第[2,7]个字节出现A5A5,即数据长度，发送地址，接收地址
            tempcount=ReceiveBuffer[LastPlace]//16		# 求出帧数据中出现了几次A5A5
            if tempcount != 0:
                print("This Frame has %d 0xA5 0xA5!!!" %tempcount)
        if ReceiveBuffer[LastPlace]==0xA5 and ReceiveBuffer[(LastPlace+1)%BufferSize]==0xA5:
            if tempcount>0 :
                tempcount-=1
            else:
                break   # 找到下一帧帧头，终止while循环
        LastPlace = (LastPlace+1) % BufferSize
    FrameLen = ((LastPlace+BufferSize)-Decode_Place) % BufferSize
    # FrameLen < ReceiveBuffer[(Decode_Place+2) % BufferSize]*256+ReceiveBuffer[(Decode_Place+3) % BufferSize]是帧格式中length的值
    # a or b    a为false的时候才会去判断b
    if (FrameLen !=0 and FrameLen < 12) or FrameLen < ReceiveBuffer[(Decode_Place+2) % BufferSize]*256+ReceiveBuffer[(Decode_Place+3) % BufferSize]:
        Timeout_Count = Timeout_Count+1
        if Timeout_Count >= 50:  # 500ms还没有收到完整的帧
            Timeout_Count = 0
            Decode_Place = (Decode_Place+FrameLen) % BufferSize
            # 超时收到不完整数据,发冲突广播
            print("Receive data not complited, length ", FrameLen)
            if CheckClash:
                # 只有广播入网信息时处理冲突，其余情况忽略
                SendConflictBoardCast()
    else:
        Timeout_Count = 0
        length = ReceiveBuffer[(Decode_Place+2) % BufferSize] * \
            256+ReceiveBuffer[(Decode_Place+3) % BufferSize]
        if length > 1024:
            Decode_Place = (Decode_Place+FrameLen) % BufferSize
            # 帧数据长度过长
            print("Receive data too long!!!")
        crc = ReceiveBuffer[(Decode_Place+length-2) % BufferSize] * \
            256+ReceiveBuffer[(Decode_Place+length-1) % BufferSize]
        # length > 2 and length <= FrameLen防止错误帧，没有格式length的值不确定，导致length-2为负数
        if length > 2 and length <= FrameLen and IsCompletion(Decode_Place, length-2, crc):
            # 处理指令
            # print("Receive a cmd len %d  buf receive %d decode %d" %
            #      (length, Receive_Place, Decode_Place))
            FrameData = []
            for i in range(length):
                FrameData.append(ReceiveBuffer[(Decode_Place+i) % BufferSize])
            FrameData[8]=FrameData[8]%16  # *****操作码的高字节中高四位非操作码，所以进行剔除
            Decode_Place = (Decode_Place+FrameLen) % BufferSize
            # print("Receive frame data:", list(map(hex, FrameData)))
            return FrameData
        else:
            # 丢弃CRC错误数据
            # 超时收到不完整数据,发冲突广播
            print("Receive data CRC check fail!!!")
            time.sleep(0.1)  # 等冲突结束
            SendConflictBoardCast()
        Decode_Place = (Decode_Place+FrameLen) % BufferSize
    return None


def SendFrame(senddata):
    """
        senddata是将要发送的数据不包括CRC校验码
    """
    global dv, UsartInitFlag     # 全局对象用于最后关闭资源
    if 'dv' not in globals():
        dv = SerialInterface()
        dv.open()
        UsartInitFlag = True
    elif not UsartInitFlag:
        dv.open()
        UsartInitFlag = True
    tempcount = 0 # 统计帧数据中A5A5出现的次数
    templen = len(senddata)
    tempi = 2
    # 需要避免第[2,7]个字节出现A5A5,即数据长度，发送地址，接收地址中出现A5A5
    while tempi < templen-1 :
        if senddata[tempi] == 0xA5 and senddata[tempi+1] == 0xA5:
            tempcount+=1
            tempi+=2
            if tempi<8:
                print('illegal Frame Data, Pleace Avoid!!!!!!!!!!!!!!!')
                print('Send Fail!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
                return
        else:
            tempi+=1
    if tempcount>7:
        print('Frame Data has too many 0xA5 0xA5 Frame Head!!!!!!!')
        print('Send Fail!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!')
        return
    senddata[8] += tempcount*16  # 指令的第九个字节的高四位中低三位添加A5A5出现的次数
    crc = GetCRC(senddata)
    if crc == 0xA5A5:
        senddata[8]+=128   # CRC为A5A5通过修改第九个字节的最高位进行避免
        crc = GetCRC(senddata)
    senddata.append(crc//256)
    senddata.append(crc % 256)
    dv.write(senddata)


def init_433(gateway_id=0xFFFF, channel_id=0x00):
    # 第12个字节 RF 信道 1Byte(0~40),每500kHZ为一个信道，即423.92至443.92MHZ,默认为20,即433.92
    cmd = [0xAA, 0x5A, 0x00, 0x00, 0x03, 0x30, 0x00, 0x1E, 0x00,
           0x04, 0x00, 0x14, 0x00, 0x00, 0x00, 0x12, 0x00]
    if channel_id < 0 or not isinstance(channel_id, int) or channel_id >= 40:
        print('channel is out of range, change to default 00')
        channel_id = 0x00
    cmd[11] = channel_id
    cmd.append(sum(cmd) % 256)  # CheckSum 1Byte(以上所有字节相加)保留低 8 位
    global dv, UsartInitFlag     # 全局对象用于最后关闭资源
    if 'dv' not in globals():
        dv = SerialInterface()
        dv.open()
        UsartInitFlag = True
    elif not UsartInitFlag:
        dv.open()
        UsartInitFlag = True
    dv.setMode(0)
    global Gatewayid
    Gatewayid = gateway_id
    i = 0
    for i in range(10):
        dv.write(cmd)
        time.sleep(0.5)
        if dv.ser.in_waiting != 0:
            data = dv.read(dv.ser.in_waiting)
            if (cmd[-1]+1) % 256 == data[-1]:   # 蜂鸟模块设置成功后，最后一个设置码会加1
                # print('init success!!!!')
                break
            else:
                pass
                # print('init fail, try again!!!')
                # print(hex(cmd[-1]), data[-1])
    if i == 10:
        return False
        
    dv.setMode(1)
    time.sleep(1)   # 延时1s让模块准备好
    global ReceiveThread, run_flag
    global ReceiveThreadSuspendFlag
    ReceiveThread = threading.Thread(target=SaveReceive)
    ReceiveThreadSuspendFlag = False
    run_flag = True
    ReceiveThread.start()
    return True



def close_433():
    global dv,UsartInitFlag
    global ReceiveThread, run_flag
    # 注意关闭的先后顺序不能颠倒
    if 'ReceiveThread' in globals() and 'run_flag' in globals():   # 已经定义
        run_flag = False
        while ReceiveThread.is_alive(): # 等待接收线程释放
            time.sleep(0.1)
    if 'dv' in globals():   # 已经定义
        dv.close()
    UsartInitFlag = False
    print("Close 433 module, Release ReceiveThread!!!")


def TestRun():
    # 测试使用
    global run_flag
    time.sleep(10)
    run_flag = False


if __name__ == '__main__':
    """
    init_433(1)
    threading.Thread(target=TestRun).start()
    global run_flag
    while run_flag:
        time.sleep(0.1)
        tempdata = GetOnceFrame()
        if tempdata != None:
            print('GetFrame:', tempdata)
    """
    init_433(1)
    threading.Thread(target=TestRun).start()
    global run_flag
    while run_flag:
        time.sleep(0.1)
        tempdata = GetOnceFrame()
        if tempdata != None:
            print('GetFrame:', tempdata)
    print('please use me as a module')

    '''
    testFrame = [[0xA5, 0xA5, 0x00, 0x14, 0x00, 0x01, 0x00, 0x02, 0x00, 0x01, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x1A, 0xC8],
                [0xA5, 0xA5, 0x00, 0x14, 0x00, 0x01, 0x00, 0x02,
                    0x00, 0x01, 0x01, 0x02, 0x03, 0x04, 0x05],
                [0xA5, 0xA5, 0x00, 0x14, 0x00, 0x01, 0x00, 0x02, 0x00, 0x01,
                    0x02, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x1A, 0xC8],
                [0xA5, 0xA5, 0x00, 0x14, 0x00, 0x01, 0x00, 0x02, 0x00, 0x01,
                    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x1A, 0xC8],
                [0xA5, 0xA5, 0x00, 0x14, 0x00, 0x01, 0x00, 0x02, 0x00, 0x01,
                    0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x1A, 0xC9],
                [0xA5, 0xA5, 0x00, 0x14, 0x00, 0x01, 0x00, 0x02, 0x00, 0x01, 0x01,
                    0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x1A, 0xC8, 0x01],
                [0xA5, 0xA5, 0x00, 0x15, 0x00, 0x01, 0x00, 0x02, 0x00, 0x01, 0x01,
                    0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x09, 0x00, 0x1A],
                [0x00, 0x14, 0x00, 0x01, 0x00, 0x02, 0x00, 0x01, 0x01,
                    0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x1A, 0xC8]
                ]
    len_testFrame = len(testFrame)
        print('*****', len_testFrame)
        i = 0
        while True:
            time.sleep(0.5)
            print(i, testFrame[i])
            dv.write(testFrame[i])
            i = i + 1
            if i >= len_testFrame:
                i = 0
            if dv.ser.in_waiting != 0:
                dv.read(dv.ser.in_waiting)
    '''
