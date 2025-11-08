def GetSensorId(DeviceClass, Id_485):
    if DeviceClass==1 :
        if Id_485==1:
            return 1
        elif Id_485==2:
            return 1
    elif DeviceClass==2 :
        if Id_485==1:
            return 3
        elif Id_485==2:
            return 4
    elif DeviceClass==3 :
        if Id_485==1:
            return 4
        elif Id_485==2:
            return None
    else:
        pass
    return None


def DataProcess(SensorId, Data):
    # 没有收到数据或者收到的数据长度为0
    result=[]
    if Data==None or len(Data)==2:
        return result
    if SensorId==1:
        if Data[0]*256+Data[1]==4:
            Data=Data[2::]
            result.append((Data[0]*256+Data[1])/10)
            if Data[2]>128:
                result.append((Data[2]*256+Data[3]-0xFFFF-1)/10)
            else:
                result.append((Data[2]*256+Data[3])/10)
            return result
    elif SensorId==2:
        pass
    elif SensorId==3:
        if Data[0]*256+Data[1]==18:
            Data=Data[2::]
            result.append((Data[0]*256+Data[1])/100)
            result.append((Data[2]*256+Data[3])/100)
            result.append((Data[4]*256+Data[5])/100)
            result.append((Data[6]*256+Data[7])/100)
            result.append(Data[8]*256+Data[9])
            result.append((Data[10]*256*256*256+Data[11]*256*256+Data[12]*256+Data[13])/100)
            result.append(Data[14]*256*256*256+Data[15]*256*256+Data[16]*256+Data[17])
            return result
    elif SensorId==4:
        if Data[0]*256+Data[1]==14:
            Data=Data[2::]
            result.append((Data[0]*256+Data[1])/10)
            result.append((Data[2]*256+Data[3])/10)
            result.append(Data[4]*256+Data[5])
            result.append((Data[6]*256+Data[7])/10)
            result.append(Data[8]*256+Data[9])
            result.append(Data[10]*256+Data[11])
            result.append(Data[12]*256+Data[13])
            return result
    else:
        pass
    return result

"""
sensor1:
0-1 	uint16 土壤湿度 0.1%
2-3 	int16 土壤湿度 0.1℃
			当温度低于 0 ℃ 时温度数据以补码的形式上传。
			eg:FF9B  -101 => 温度=-10.1℃
			   0xFF9B-0xFFFF-1(16进制)=-101(10进制)

sensor3:
0-1   温度   int16   单位:0.01℃   范围：-40~80℃
2-3   湿度   uint16  单位:0.01%    范围:0~100%
4-5   气压   uint16  单位:0.01Kpa  范围:30-110kPa
6-7   风速   uint16  单位:0.01m/s
8-9   风向   uint16  单位:°        范围:0~360°  北偏多少度
10-13 风速   uint32  单位:0.01mm
14-17 光照   uint32   Lux

sensor4:
0-1   int 土壤温度 0.1℃
2-3   int 土壤湿度 0.1%
4-5   int 土壤EC   0ms/cm
6-7   int PH(酸碱度)数据 0.1  4~9
8-9   int 土壤氮含量  mg/kg
10-11 int 土壤磷含量  mg/kg
12-13 int 土壤钾含量  mg/kg
"""







