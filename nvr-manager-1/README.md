# 系统需求

* 硬件开发板：RK3588
* 架构：arrch64
* OS：Ubuntu 20.04(Focal)/Ubuntu 22.04(Jammy)/Debian 11


# 默认账号密码
- neardi
- lindikeji

# 软件安装

提升至root权限：

```bash
sudo su
# 或su root
```

## 软件下载

在线下载和压缩包二选一即可，当开发板容易安装git命令时可以使用在线下载方式，否则也可以使用压缩包。

### 在线下载

用git命令在线拉取项目：

```bash
# 安装git命令
apt-get update && apt-get install git

# 进行git设置
git config --global http.sslverify false
git config --global https.sslverify false

# 这一步可能需要Gitee账号密码
git clone https://gitee.com/research-group-2022/nvr-manager.git && cd nvr-manager
```

### 压缩包

从gitee上获取zip压缩包后，自行上传到开发板中，确保系统内有unzip命令：

```bash
unzip nvr-manager*.zip && cd nvr-manager*
```

## 安装

建议使用自动校时方式安装。

### 自动校时

这种方式使用ntp自动与阿里云ntp服务器校时，需要当前网络支持ntp校时	：

```bash
# 自动校准时间安装
./scripts/setup.sh
```

### 手动校时

只有当前网络无法使用ntp校时时，才建议使用手动校时方式安装：

```bash
# (当因网络问题导致自动校准时间安装失败时，需要)手动校准时间安装：
# 当前时间按照[年-月-日 时:分:秒]的格式传入，如 2023-6-7 14:07:00

./scripts/setup.sh "<当前时间>"
# ./scripts/setup.sh "2023-6-7 14:07:00"
```

*另：若显示xxx安装失败，可能是因为系统时间与网络时间相差过大，需要先行根据真实网络时间手动调整一下系统时间。可用 `data -s "<年>-<月>-<日> <时>:<分>:<秒>"`命令校准时间，再执行自动校准时间安装；或直接手动校准时间安装（但安装完成后系统时间不如自动校准的精确）*

# 软件升级

假如你有本地最新版本安装包，除了通过接口与页面进行升级外，也可以登陆进板子系统内进行手动升级（需root权限）：

```bash
./scripts/upgrade.sh
```

可以在如下场景使用：系统内的git方式下载的安装包没删，此时可进入项目目录内手动使用 `git pull`更新为最新版本，然后使用上述命令升级系统，好处就是更新快。

# 默认密码

`11d6d3b38cb8e05e006cec88e992c237d327c3e0`

# 查看状态

```
systemctl status nvr-manager
systemctl status nginx
```

# 查看日志

```
journalctl -u nvr-manager -n 99
```

# 32路台位灯测试
```
# 远程登录ssh终端
cd nvr-manager

sudo ./test_led.out

```
