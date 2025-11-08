# MQTT

软件会使用MQTT进行一些必要数据的上报以及可以接受一些来自MQTT的命令以进行MQTT控制的某些操作。协议分为两个版本：物联网平台以及第三方MQTT平台，这两个平台尽管使用不同的Topic规则，但上报或者下发的内容是相同的。

下面对topic中的公共变量进行说明：

* DEVICE_SECRET：物联网平台设备密钥
* NVR_DEVICE_ID：板子ID
* DEVICE_ID：子监控设备ID

下面功能标题中：

* UP：表示上报信息
* DOWN：表示下发指令+上报指令执行结果

参数类型：

* json：Json对象
* str：字符串
* str-json：字符串类型的json对象，这种类型只对物联网平台生效，第三方平台接收到的是普通Json对象
* int：整数
* null：空
* bool：true/false

# [UP]上报报警信息

* 物联网平台：`g_event/<DEVICE_SECRET>/alert/<DEVICE_ID>`
* 第三方MQTT平台：`zzu/aiedge/<NVR_DEVICE_ID>/alert`

上报内容：

```json
{
    "id": <(int)报警记录的ID>,
    "event": <(str)事件名称>,
    "object": <(str)报警对象>,
    "information": <(str-json/json)报警信息，对于目标检测类AI服务，该包含{对象ID:[x1, y1, x2, y2], ...}格式的当前画面中该类型所有物体的位置信息，其中对象ID是标识某个物体的唯一ULID，[x1, y1, x2, y2]包含该物体在画面中左上角和右下角的坐标>,
    "time": <(str)报警时间>,
    "device_id": <(str)报警监控设备ID>,
    "device_name": <(str)报警设备名称>,
    "image_path": <(str)报警截图路径>,
    "record_path": <(str)报警录像路径>
}
```

字段详情请参考该HTTP接口所描述的报警信息描述：[获取报警列表 - nvr-manager (apifox.com)](https://apifox.com/apidoc/shared-188b42be-8dc6-4d6c-95d1-c5c539a130a4/api-73210966)

# [UP]上报性能监测信息

* 物联网平台：`event/<DEVICE_SECRET>/state`
* 第三方MQTT平台：`zzu/aiedge/<NVR_DEVICE_ID>/state`

上报内容：

```json
{
    "total_space": <(str)总存储空间>,
    "used_space": <(str)已用存储空间>,
    "cpu_percent": <(str)cpu使用率>,
    "total_memory": <(str)总内存空间>,
    "used_memory": <(str)已用内存空间>,
    "memory_utilization": <(str)内存使用率>,
    "npu_utilization": <(str)npu利用率>,
    "upload_speed": <(str)上行带宽>,
    "download_speed": <(str)下行带宽>
}
```

样例：

```json
{
    "cpu_percent": "1.30%",
    "download_speed": "230.00 B/s",
    "memory_utilization": "19.50%",
    "npu_utilization": "0.00%",
    "total_memory": "15.33 GB",
    "total_space": "1.04 TB",
    "upload_speed": "292.00 B/s",
    "used_memory": "2.81 GB",
    "used_space": "49.51 GB"
}
```

字段详情请参考该HTTP接口所描述：[性能详情 - nvr-manager (apifox.com)](https://apifox.com/apidoc/shared-188b42be-8dc6-4d6c-95d1-c5c539a130a4/api-64375362)

# [UP]上报网络地址

* 物联网平台：`event/<DEVICE_SECRET>/address`
* 第三方MQTT平台：`zzu/aiedge/<NVR_DEVICE_ID>/address`

上报内容：

```json
{
    "http": <(str)HTTP外网地址>,
    "ssh": <(str)SSH外网地址>,
    "local": <(str-json/json)所有网卡的本地网络地址，是一整个字符串的Json对象，格式为{网卡名称: 地址, ...}>
}
```

样例：

```json
{
    "http": "http://b33ad09f5553c30a.penetrate.cn:8080",
    "ssh": "penetrate.cn:46791",
    "local": {"enP2p33s0": "192.168.1.240", "wlan0": "10.42.0.1"}
}
```

# [UP/DOWN]物联网设备上报数据/下发指令

请参考该文档：[IOT驱动器设计 - nvr-manager (apifox.com)](https://apifox.com/apidoc/shared-188b42be-8dc6-4d6c-95d1-c5c539a130a4/doc-3160387)

# [UP]上报系统日志

* 物联网平台：`event/<DEVICE_SECRET>/syslog`
* 第三方MQTT平台：`zzu/aiedge/<NVR_DEVICE_ID>/syslog`

上报内容：

```json
{
    "log": <(str)日志>
}
```

样例：

```json
{
    "log": "[INFO] [2023-11-08 10:38:05,012] [nvr-manager.cloud.mqtt] 登陆MQTT平台成功"
}
```

# [DOWN]系统设置

命令：

* 物联网平台：`cmd/<DEVICE_SECRET>/updateSetting`
* 第三方MQTT平台：`zzu/aiedge/<NVR_DEVICE_ID>/updateSetting`

反馈：

* 物联网平台：`event/<DEVICE_SECRET>/updateSettingFeedback`
* 第三方MQTT平台：`zzu/aiedge/<NVR_DEVICE_ID>/updateSetting/feedback`

## 命令

命令内容：

```json
{
    "setting": <(str/json)设置内容，为Json格式的字符串或Json对象>
}
```

样例（关闭外网穿透）：

```json
{
    "setting":"{\"cloud\":{\"frpc\":{\"enable\":false}}}"
}
```

或：

```json
{
    "setting": {"cloud": {"frpc":{"enable":false}}}
}
```

设置内容的详情参考HTTP系统设置接口：[更新设置 - nvr-manager (apifox.com)](https://apifox.com/apidoc/shared-188b42be-8dc6-4d6c-95d1-c5c539a130a4/api-76490213)

## 反馈

反馈内容：

```json
{
    "ok": <(bool)是否成功>,
    "message": <(str/null)报错信息，如果执行成功则为null>,
    "setting": <(str-json/json)当前的系统设置>
}
```

样例：

```json
{
    "ok": true,
    "message": null,
    "setting":"{\"cloud\": {\"mqtt\": {\"enable\": true, \"cloud_host\": \"mqtt.yun.gdatacloud.com\", \"cloud_port\": 31854, \"zzuiot_platform\": true, \"cloud_username\": null, \"cloud_password\": null}, \"frpc\": {\"enable\": false, \"server_host\": \"penetrate.cn\", \"server_port\": 7000, \"server_http_port\": 8080, \"server_token\": \"11d6d3b38cb8e05e006cec88e992c237d327c3e0\", \"remote_ssh_port\": null}, \"forward\": {\"cloud_host\": \"rtmp.video.gdatacloud.com\", \"cloud_port\": 30312}}, \"monitor\": {\"report_interval\": 30}, \"system\": {\"system_title\": \"智能安全预警系统\"}, \"ai\": {\"ai_project\": {\"project_dir\": \"data/ai_projects\"}, \"ai_task\": {\"logs_dir\": \"data/aitask_logs\"}}, \"dvr\": {\"playback_dir\": \"data/dvr_playbacks\", \"segment_duration\": 30, \"cleanup_time\": \"04:00:00\", \"cleanup_days\": 7, \"scroll_deletion\": true}, \"alert\": {\"image_dir\": \"data/alert_images\", \"cleanup_time\": \"04:00:00\", \"cleanup_days\": 30, \"scroll_deletion\": true}}"
}
```

设置内容的详情参考HTTP系统设置接口：[更新设置 - nvr-manager (apifox.com)](https://apifox.com/apidoc/shared-188b42be-8dc6-4d6c-95d1-c5c539a130a4/api-76490213)

# [DOWN]系统更新

命令：

* 物联网平台：`cmd/<DEVICE_SECRET>/upgradeSystem`
* 第三方MQTT平台：`zzu/aiedge/<NVR_DEVICE_ID>/upgradeSystem`

反馈：

* 物联网平台：`event/<DEVICE_SECRET>/upgradeSystemFeedback`
* 第三方MQTT平台：`zzu/aiedge/<NVR_DEVICE_ID>/upgradeSystem/feedback`

## 命令

命令内容：

```json
{
    "branch": <[*非必填](str/null)更新通道，如填写null或不传入该参数，则从默认通道升级>
}
```

样例：

```json
{
    "branch": null
}
```

更新系统的详情参考接口：[更新系统 - nvr-manager (apifox.com)](https://apifox.com/apidoc/shared-188b42be-8dc6-4d6c-95d1-c5c539a130a4/api-81307910)

## 反馈

*当发出系统升级指令后，系统会每隔5s上报一次当前的更新进度/更新状态。*

反馈内容：

```json
{
    "upgrading": <(bool)系统目前是否正在升级，为false时表示更新成功或者失败，具体情况需要从message字段中查看)>,
    "log": <(str)当前系统更新的进度>
}
```

样例：

```json
{
    "upgrading": true,
    "log": "# 已切换到软件升级通道：666\n# 正在下载最新程序，需要花费较长时间，请等候...\n"
}
```

返回的内容可参考接口：[获取系统更新状态 - nvr-manager (apifox.com)](https://apifox.com/apidoc/shared-188b42be-8dc6-4d6c-95d1-c5c539a130a4/api-81419670)

*文档系统版本：v1.2.0-dev-20231109-ResetData*
