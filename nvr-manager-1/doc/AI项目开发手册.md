# 项目要求

视觉AI项目的基本目的就是处理某一个摄像头的输入流（比如RTSP流），处理后再向流媒体服务器（比如SRS）上推流（比如推RTMP流）。与此同时，在检测过程中可能会触发某些事件（比如我们检测到了火灾），当我们想要提醒用户事件发生的时候，我们需要向管理系统进行“报警”。

因此，有两个基本功能需要我们来处理并实现：

* 视频推流
* 事件报警

如流程图所示：

![1685352025320](image/AI项目开发手册/1685352025320.png)

当我们实现这两个基础功能之后，管理系统会为我们提供许多额外的增强功能，比如：

* 视频流直播
* 视频回放
* 报警存储
* 报警展示
* 报警录像
* ...

## 系统参数

如何获取摄像头的流地址？处理后的视频流推到哪？以及如何向管理系统报警？

这一切都是通过命令行参数实现的，在用户启动AI程序之后，管理系统会开启一个进程运行我们的AI程序，并且向我们的程序提供一系列的命令行参数。

命令行参数接收样例：

```python
import argparse

parser = argparse.ArgumentParser()
# 流地址
_parser.add_argument('--input', type=str, default='rtsp://admin:a123456789@192.168.1.65:554/Streaming/Channels/101?transportmode=unicast&profile=Profile_1', help="输入视频流（OpenCV参数）")
_parser.add_argument('--output', type=str, default='rtmp://localhost/live/1699323368155858390', help="输出视频流（FFMpeg参数）")
# 报警参数
_parser.add_argument('--alert_collect_url', type=str, help="报警的url", default='http://localhost:5000/alert/collect/1699323368155858390')
_parser.add_argument('--alert_sensitivity', type=float, help='报警的灵敏度，数值越高越灵敏', default=0.3)
_parser.add_argument('--alert', type=json.loads, nargs='+', help='报警事件，传入规定格式的Json字符串', default=None)
# 区域入侵参数
_parser.add_argument('--region', type=json.loads, nargs='+', help='报警的区域，按照传入规定格式的Json字符串', default=None)
# 转播参数
_parser.add_argument('--resolution', type=str, help="转播的分辨率(宽*高)，如640*480", default=None)
_parser.add_argument('--cbr', type=int, help='转播的码率(单位为kbps)，如1024', default=1024)
_parser.add_argument('--fps', type=int, help='转播的帧率，如20', default=None)
# 画面参数
_parser.add_argument('--enable_draw_video_box', action='store_true', help="启用视频画面绘制识别框")
_parser.add_argument('--enable_draw_alert_box', action='store_true', help="启用报警图像绘制识别框")
# 多进程参数
_parser.add_argument('--enable_multiprocess', action='store_true', help="开启多进程检测，占用资源会更多，但画面会更流畅。如不开启，默认会使用单进程预测与补帧算法")
_parser.add_argument('--mutiprocess_worker_num', type=int, help="检测进程数量，如果设为1则与不开启多进程检测效果相同，默认为3", default=3)

# 推荐用parse_known_args来解析，因为如果传递的某些参数我们不想接收（比如不想提供区域检测功能），这样的解析方式至少启动时不会报错
config, _ = parser.parse_known_args()
```

### 基本参数

这些参数是一定会传递给我们的AI程序的，离开了这些参数，我们没办法编写最基本的程序功能。

参数如下：

| 参数名称          | 说明                                                                                                                                                                                                                                             |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| input             | 摄像头的输入流地址，一般为RTSP流地址，我们的程序需要读取这个流进行取帧操作（如用Opencv读取视频流）。                                                                                                                                             |
| output            | 推流的地址，这个参数代表我们的程序应该向哪里推流，一般为RTMP流地址，这个地址指向的地方为流媒体服务器，我们程序需要将处理过的帧组成视频流后再推向这个地址（如用FFmpeg）。                                                                         |
| alert_collect_url | 报警的HTTP地址，想报警就需要向这个地址发送POST请求，请求所需要的参数请参考API接口文档（Path参数中的device_id不用管）：[收集报警信息 - nvr-manager (apifox.com)](https://apifox.com/apidoc/shared-188b42be-8dc6-4d6c-95d1-c5c539a130a4/api-62376497) |

传给程序的参数形式类似于：

```bash
--input rtsp://admin:soft8h8h@172.16.202.100:554/Streaming/Channels/702 \
--output rtmp://localhost/live/hiknvr-87 \
--alert_collect_url http://localhost:5000/alert/collect/camera-xxx
```

### 额外参数

这些参数代表额外我们需要实现的功能，如果我们不想实现，那么忽略这些参数即可，但如果实现，用户就可以使用到额外的功能。

#### 检测区域（区域入侵）

用户会用多个点画出他想检测的多边形区域，我们可以根据用户的需求实现只检测这块区域的功能。

比如：

![1685355895202](image/AI项目开发手册/1685355895202.png)

参数如下：

| 参数名称            | 说明                                                                                   |
| ------------------- | -------------------------------------------------------------------------------------- |
| ai_region           | 报警的区域，报警的区域，按照传入规定格式的Json字符串 |

每个区域包含如下部分：
* name：区域的名称
* region：按照[x1,y1,y2,y2,...]的顺序传入n个点的坐标，表示一个多边形区域

传给程序的参数形式类似于：

```bash
--ai_region "{\"name\": \"大门\", \"region\": [0.1, 0.1, 0.45, 0.2, 0.48, 0.45, 0.2, 0.69]}" "{\"name\": \"广场\", \"region\": [0.1, 0.1, 0.45, 0.2, 0.48, 0.45, 0.2, 0.69]}"
```

*提示：这样的参数可以在argparse中以如下方式接收*

```python
parser.add_argument('--ai_region', type=json.loads, nargs='+')
```

## 用户参数

除了上面所说的由管理系统传递进来的参数（用户无法插手）外，如果我们想让用户直接指定程序参数，比如想让用户可以在页面上指定报警的类别或者转播的分辨率该怎么办？

其实很简单，就两个步骤：

1. AI程序中解析自己想要的参数。
2. 在项目配置的**可选参数**中声明这些参数。

具体用法请参考[可选参数](#可选参数描述 "可选参数")。

## 程序退出

这里需要讨论一下AI程序的退出问题，当管理系统启动AI程序时，会将AI程序作为管理系统的子进程启动。当用户点击停止时，管理系统需要关闭我们的AI程序，此时管理系统会向AI程序发送SIGTERM（15）信号。我们需要做的就是当接收到这个信号时关闭AI程序的所有子进程并退出主进程，比如AI程序使用ffmpeg作为子进程进行推流，那么我们需要在退出函数中结束这个进程，并退出主进程。

Python代码样例如下：

```python
import signal

ffmpeg = ...
def exit_proc():
    ffmpeg.terminate()  # 向ffmpeg子进程发送SIGTERM信号，以关闭ffmpeg
    exit(0)  # 直接退出主进程

# 当进程接收到SIGTERM信号时，执行exit_proc函数
signal.signal(signal.SIGTERM, lambda _1, _2: exit_proc())
```

不过，还有一种情况，就是程序异常退出。不过，当程序出现bug导致AI任务异常退出后，管理系统的守护线程会将AI仍程序重启，日志则可以在管理系统的页面上查看，因此如果bug不严重，异常退出的问题倒也不必太担心。

# 项目配置

在项目的根目录中需要存在一个名为 `nvrpro.yaml`的配置文件，该文件记录着该AI项目的描述与配置。
可以参考这个项目的样例：[nvrpro.yaml](https://gitee.com/research-group-2022/nvrpro-airockchip-yolov7-rknn/blob/master/nvrpro.yaml)。
下面是对该配置文件参数的说明。

## 参数说明

* 必填：该参数是否是必须填写的
* 描述性：该参数的值不会对项目产生影响，是为了描述该项目的相关信息而存在的

| 参数名          | 类型        | 必填 | 描述性 | 限制                     | 说明                                                                                                                                                        |
| --------------- | ----------- | ---- | ------ | ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| nvrpro          | 整数        | √   |       |                         | 固定为2文                                                                                                                            |
| name            | 字符串      | √   | √     | 最多20个字符             | 该项目的名称，建议使用简短的中文                                                                                                                            |
| description     | 字符串      | √   | √     | 最多50个字符             | 该项目的描述与说明                                                                                                                                          |
| version         | 字符串      | √   |        | 最多20个字符             | 该项目代码的版本，用户点击更新时，如果比较发现原来的本地版本和更新项目中的版本一致，则不会进行更新操作（因此每次更新项目代码后，版本号都要变更一下）        |
| deploy.root        | 字符串      | √   |        | 无                       | 部署的根目录，正式部署时只会将该目录部署到系统中                                                                                                                      |
| deploy.entrypoint  | 字符串      | √   |        | 最多50个字符             | 入口程序代码文件相对于代码根目录的相对路径，可以是.py、.sh或者不带后缀名的二进制文件                                                                                                                  |
| git_url         | 字符串      | √   |        | 无                       | 本项目的Git地址，用于判断项目的唯一性，在线升级项目会根据该地址来进行升级                                                                                   |
| optional_args   | 键值对      |      |        | 无                       | 用于描述该程序的可选参数，在[用户可选参数](#可选参数描述)会详细介绍                                                                                            |
| alert           | 键值对      |      |        | 无                       | 用于描述该程序的报警配置，在[报警配置](#报警配置)会详细介绍                                                                                                    |
| python.requirements    | 字符串/数组 |      |        | 无                       | 项目的pip依赖，有两种用法：1.在项目目录下建立一个requiremens.txt文件，然后将依赖写在里面，这个参数指定该文件的路径。2.直接利用这个参数填写一个依赖列表。    |
| python.index_url       | 字符串      |      |        | 无                       | pip的主索引源，默认是清华源                                                                                                                                 |
| python.extra_index_url | 字符串/数组 |      |        | 无                       | pip的额外索引源，可以指定一个字符串作为一个额外索引源，或者也可以指定一个额外索引源列表，默认为空                                                           |
| python.new_env         | 字符串      |      |        | 必须为某一个Python的版本 | 所有项目都会用同一个Python3.9的虚拟环境，但如果你的某些依赖和其他项目有冲突，无法公用同一个环境，你也可以使用该字段来创建一个新的虚拟环境，其值为Python版本 |

## 用户可选参数

这部分存在的意义是为了使用户可以以可视化的方式向你的程序选择并传递参数（命令行参数），指定了这部分选项后管理系统前端可以根据你的可选参数配置，在参数选择界面为你生成相应的控件。
该选项的配置规则如下：

```yaml
optional_args:
  - <参数组名>: 
    - id: <参数名>
      name: 参数显示给用户的名称
      help: 参数的描述信息，可以告诉用户该参数的作用，如何选择等
      # 限制选项：
      # 不指定: 普通的文本框（文本框）
      # choices: 单选（下拉框）
      # muti_choices: 多选（多选框）
      # switch: 开关（开关按钮）
      # alert: 报警（正在开发）
```

如：

```yaml
optional_args:
  - 转播设置: 
    - id: resolution
      name: 转播分辨率
      help: 指定转播的分辨率，默认与原摄像头的分辨率一致，可以强制指定更低的分辨率用于降低原摄像头转播的分辨率，以节省网络带宽
      choices:
        - 720*640
        - 1280*720
        - 1280*960
        - 1920*1080
        - 2560*1440
    - id: cbr
      name: 码率
      help: 指定转播的固定码率(Kbps)，码率越高视频越清晰，但会占用更多的网络带宽，默认为1024Kb
      choices:
        - 256
        - 512
        - 1024
        - 1536
        - 2048
        - 3072
        - 4096
        - 6144
        - 8192
        - 12288
        - 16384
    - id: fps
      name: 转播帧率
      help: 指定转播的帧率(fps)，默认与原摄像头的帧率一致
      choices:
        - 1
        - 2
        - 4
        - 6
        - 8
        - 10
        - 12
        - 15
        - 16
        - 18
        - 20
        - 22
        - 25
  - 基础设置:
    - id: enable_draw_video_box
      name: 预览视频预测框
      help: 视频画面绘制识别框
      switch: true
    - id: enable_draw_alert_box
      name: 报警结果识别框
      help: 报警图像绘制识别框
      switch: true
    - id: enable_multiprocess
      name: 性能模式
      help: 开启多进程检测，占用资源会更多，但画面会更流畅。如不开启，默认会使用单进程预测与补帧算法
      switch: true
    - id: mutiprocess_worker_num
      name: 检测进程数量
      help: 检测进程数量，如果设为1则与不开启多进程检测效果相同，默认为3
```

下面介绍每个限制选项的用法。

### 不指定

不指定任何限制选项会为你生成一个普通的文本输入框，用户可以输入任何文本数据作为参数。

![1685349927939](image/AI项目开发手册/1685349927939.png)

规则如下：

```yaml
id: xxx
name: xxx
help: xxx
```

如：

```yaml
id: mutiprocess_worker_num
name: 检测进程数量
help: 检测进程数量，如果设为1则与不开启多进程检测效果相同，默认为3
```

此时，假如用户输入了 `3`，那么会向你的程序传入如下命令行参数：

```bash
--mutiprocess_worker_num 3
```

### choices

这个选项会为用户生成一个单选的下拉框。

![1685349950249](image/AI项目开发手册/1685349950249.png)

规则如下：

```yaml
id: xxx
name: xxx
help: xxx
choices: 选项列表
```

如：

```yaml
id: resolution
name: 转播分辨率
help: 指定转播的分辨率，默认与原摄像头的分辨率一致，可以强制指定更低的分辨率用于降低原摄像头转播的分辨率，以节省网络带宽
choices:
  - 720*640
  - 1280*720
  - 1280*960
  - 1920*1080
  - 2560*1440
```

此时，假如用户选择了 `720*640`，那么会向你的程序传入如下命令行参数：

```bash
--resolution 720*640
```

### muti_choices

这个选项会为用户生成一个多选框。

![1685349972244](image/AI项目开发手册/1685349972244.png)

规则如下：

```yaml
id: xxx
name: xxx
help: xxx
muti_choices: 选项列表
```

如：

```yaml
id: filter_classes
name: 过滤物体类型
help: 过滤识别出的物体类型，在这里指定的类型都会在识别后被过滤掉，默认什么也不过滤
muti_choices:
  - person
  - cat
  - dog
  - horse
  - bus
```

此时，假如用户选择了 `person`、`cat`和 `bus`，那么会向你的程序传入如下命令行参数：

```bash
--filter_classes person cat bus
```

*提示：这样的参数可以在argparse中以如下方式接收*

```python
parser.add_argument('--filter_classes', type=str, nargs='+')
```

### switch

这个选项会为用户生成一个开关。

![1685349990025](image/AI项目开发手册/1685349990025.png)

规则如下：

```yaml
id: xxx
name: xxx
help: xxx
switch: true  # 将switch指定为true即可，
```

如：

```yaml
id: enable_letter_box
name: 启用LetterBox
help: 在进行resize时保持原图的长度比，不足的部分采用黑色进行填充
switch: true
```

此时，假如用户开启了该选项，那么会向你的程序传入如下命令行参数：

```bash
--enable_letter_box
```

*提示：这样的参数可以在argparse中以如下方式接收*

```python
parser.add_argument('--enable_letter_box', action='store_true')
```

## 报警配置

报警指的是我们的AI程序检测到了某个对象触发了某种行为，我们需要将这种异常行为推送给管理系统。我们可以将报警称之为“事件”，对于某个事件来说，其组成部分有：

* event：事件名称（比如堵车）
* object：被报警的物体名称（比如汽车）
* condition：该物体报警的条件（比如大于）
* region：该事件对应的区域
* args：该条件所附带的参数（比如10）

每一条报警配置中都应该包含上面四个部分，报警条件如果不带参数的话，args参数也可以为空。我们需要在nvrpro.yaml中进行报警的配置，然后在AI程序中进行报警的处理。

首先我们需要让用户知道我们的AI程序支持什么物体以及每个物体支持什么样的报警的方式，这需要我们在nvrpro.yaml中配置，其格式如下：

```yaml
alert:
  objects: 
    - 物体1
    - 物体2
    - ...
  conditions: 
    - name: 条件1
      args: null
    - name: 条件2
      args:
        - name: <条件参数名称>
          description: <条件参数描述>
          type: <条件参数类型，当前支持integer（整形）、number（小数）、string（字符串）>
    - ...
```

比如：

```yaml
# 报警设置
alert:
  objects:
    - 人
    - 自行车
    - 汽车
  conditions:
    - name: 出现
      args: null
    - name: 离开
      args: null
    - name: 向上经过
      args: null
    - name: 向下经过
      args: null
    - name: 向左经过
      args: null
    - name: 向右经过
      args: null
    - name: 滞留
      args:
        - name: 时间
          description: 对象停留在画面中的时间（秒）
          type: number
    - name: 等于
      args: &op_cond_args
        - name: 数量
          description: 画面中该对象的存在的数量
          type: integer
    - name: 不等于
      args: *op_cond_args
    - name: 大于
      args: *op_cond_args
    - name: 大于等于
      args: *op_cond_args
    - name: 小于
      args: *op_cond_args
    - name: 小于等于
      args: *op_cond_args
```

在配置文件中配置完成后，用户就可以根据<物体>+<条件>(+<条件参数>)的方式来组合出他想要的事件了。当用户设置完他需要的事件后，会通过命令行参数传给我们的AI程序，为了不同语言程序的兼容性，将参数类型定为Json，比如用户配置了下面的事件：

* 事件1
  * event：堵车
  * object：汽车
  * condition：大于
  * region：大门口
  * args：
    * 10
* 事件2：
  * event：非法停留
  * object：人
  * condition：滞留
  * region：广场
  * args：
    * 10
* 事件3：
  * event：消防栓被偷
  * object：消防栓
  * condition：离开
  * region：道路边
  * args：null

此时会向AI程序传递如下参数：

```bash
--alert "{\"event\": \"堵车\", \"object\": \"汽车\", \"condition\": \"大于\", \"condition\": \"大门口\", \"args\": [10]}" "{\"event\": \"非法停留\", \"object\": \"人\", \"condition\": \"滞留\", \"region\": \"广场\", \"args\": [10]}" "{\"event\": \"消防栓被偷\", \"object\": \"消防栓\", \"condition\": \"离开\", \"region\": \"道路边\", \"args\": null}"
```

*提示：这样的参数可以在argparse中以如下方式接收*

```python
parser.add_argument('--alert', type=json.loads, nargs='+')
```

# 样例

[[RKNN]Yolov7-目标检测AI项目模板](https://gitee.com/research-group-2022/nvrpro-airockchip-yolov7-rknn "[RKNN]Yolov7-目标检测AI项目模板")
