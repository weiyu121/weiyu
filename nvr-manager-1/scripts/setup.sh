has_root() {
    if [ "$(id -u)" != "0" ]; then
        echo "请由root用户执行，或者使用sudo bash来执行该脚本" 1>&2
		exit 1
    fi
}
has_root

# 安装必要的linux软件
OS_NOT_SUPPORT=false
if [ -f /etc/os-release ]; then
	source /etc/os-release
    if [ ${ID,,} == "ubuntu" ]; then
        if [ ${VERSION_ID,,} == "20.04" ]; then
            SOURCE_LIST=sources.focal.list
        elif [ ${VERSION_ID,,} == "22.04" ]; then
            SOURCE_LIST=sources.jammy.list
        else
            OS_NOT_SUPPORT=true
        fi
    elif [ ${ID,,} == "debian" ]; then
        if [ ${VERSION_ID,,} == "11" ]; then
            SOURCE_LIST=sources.focal.list
            echo '# 正在添加ubuntu apt-key...'
            apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 3B4FE6ACC0B21F32
            apt-key adv --keyserver keyserver.ubuntu.com --recv-keys 871920D1991BC93C
            sleep 5
        else
            OS_NOT_SUPPORT=true
        fi
    else
        OS_NOT_SUPPORT=true
    fi
else
    OS_NOT_SUPPORT=true
fi

if $OS_NOT_SUPPORT; then
    echo 系统不支持，系统必须为下面的一种：ubuntu 20.04、ubuntu 22.04、Debian 11
    exit 1
fi

echo "# 正在设置当前系统时区..."
ln -s -f /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
echo Asia/Shanghai > /etc/timezone
if [ -n "$1" ]; then
    date -s "$1" >/dev/null 2>&1
    if [ $? -ne 0 ]; then
        echo '时间矫正失败，请按照正确格式传入当前时间'
        exit 1
    fi
    hwclock -w
    echo "# 当前系统时间矫正为："
    timedatectl
fi

echo "# 正在安装必要的Linux软件..."
cp -f etc/$SOURCE_LIST /etc/apt/sources.list
apt-get update
apt-get install aptitude -y
if [ $? -ne 0 ];then
    echo 'aptitude安装失败...'
    exit 1
fi
apt-get install gcc -y
type gcc >/dev/null 2>&1
if [ $? -ne 0 ];then
    echo 'apt-get安装gcc失败，正在尝试使用aptitude自动安装gcc...'
    aptitude install gcc -y
    type gcc >/dev/null 2>&1
    if [ $? -ne 0 ];then
        echo 'gcc安装失败，请手动运行[aptitude install gcc]命令来进行交互式安装'
        exit 1
    fi
fi
aptitude install ntpdate curl mysql-server nginx x264 x265 git -y
if [ $? -ne 0 ];then
    echo 'Linux软件安装失败...'
    exit 1
fi

git config --global http.sslverify false
git config --global https.sslverify false

# mysql配置
echo "# 正在配置MySQL.."
mysql -uroot < etc/nvr-manager.sql

if [ ! -n "$1" ]; then
    echo '正在自动同步时间，请稍后...'
    ntpdate ntp.aliyun.com
    if [ $? -ne 0 ]; then
        echo '由于网络原因导致时间自动同步失败，将忽略时间同步，如想继续同步时间则请手动按照 "年-月-日 时:分:秒" 的格式传入正确的当前时间，如"1999-12-31 23:59:59"！'
    else
        hwclock -w
        echo "# 当前系统时间矫正为："
        timedatectl
    fi
fi

# 安装frp（/usr/bin）(https://github.com/fatedier/frp)
if [ -e "/usr/bin/frpc" ]; then
    echo "# frp已安装，跳过..."
else
    echo "# 正在安装frp..."
    cp softwares/frp/frpc /usr/bin/
fi

# 安装srs（/usr/local/srs）(https://ossrs.net/lts/zh-cn/docs/v5/doc/service)
export SRS_HOME="/usr/local/srs"
if [ -d $SRS_HOME ]; then
    echo "# srs已安装，跳过..."
else
    echo "# 正在安装srs..."
    cp softwares/srs $SRS_HOME -r
    ln -sf $SRS_HOME/etc/init.d/srs /etc/init.d/srs
    cp -f $SRS_HOME/usr/lib/systemd/system/srs.service /usr/lib/systemd/system/srs.service
    systemctl daemon-reload
    systemctl enable srs --now
fi

# 禁止core文件生成
ulimit -c 0

export CONDA_HOME="/usr/local/conda"
export PYTHON="$CONDA_HOME/envs/nvr-manager/bin/python"

# 判断板子型号
dir=$(dirname "$0")
if command -v npu-smi &> /dev/null; then
    echo "检测到开发板为Atlas200IDKA2..."
    source ${dir}/setup.atlas200.sh
elif [ -d /sys/kernel/debug/rknpu ]; then
    echo "检测到开发板为RK3588..."
    source ${dir}/setup.rk3588.sh
else
    echo "无法继续安装软件环境，请在RK3588开发板或者Atlas200IDKA2开发板上安装..."
    exit 1
fi

# 当没有conda命令时才修改PATH，不然会导致冲突
if ! command -v conda &> /dev/null; then
    ln -s -f /usr/local/conda/bin/conda /bin/conda
    export PATH="$CONDA_HOME/bin:$PATH"
fi

# 安装软件环境（/usr/local/nvr-manager）
export NVR_MANAGER_HOME="/usr/local/nvr-manager"
if [ -d $NVR_MANAGER_HOME ]; then
    echo "# 软件后端已安装，跳过..."
else
    echo "# 正在安装软件后端以及相关环境..."
    # 安装创建nvr-manager所需要的环境
    conda create -y -n nvr-manager python=3.9
    conda run --no-capture-output -n nvr-manager pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --no-cache-dir
    # 安装程序
    mkdir $NVR_MANAGER_HOME
    cp src $NVR_MANAGER_HOME/ -r
    chown root:root $NVR_MANAGER_HOME -R
    chmod 660 $NVR_MANAGER_HOME -R
    # 加入systemd服务
    cp etc/nvr-manager.service /usr/lib/systemd/system/
    # 登录gitee，以在线升级
    mkdir -p /root/.ssh
    cp etc/id_ed25519 /root/.ssh/id_ed25519
    chmod 600 /root/.ssh/id_ed25519
    ssh -o "StrictHostKeyChecking no" -T git@gitee.com
    # 运行后端程序
    systemctl daemon-reload
    systemctl enable nvr-manager --now
    
    # 初始化数据库组件
    cd $NVR_MANAGER_HOME
    if [ -d "migrations" ]; then
        echo "# 数据库更新组件已初始化，跳过..."
    else
        echo "# 正在初始化数据库更新组件..."
        $PYTHON -m flask --app src/migration.py db init
    fi
    cd - >/dev/null 2>&1
fi

# 安装软件前端（/usr/local/nvr-manager-web）
export NVR_MANAGER_WEB_HOME="/usr/local/nvr-manager-web"
if [ -d $NVR_MANAGER_WEB_HOME ]; then
    echo "# 软件前端已安装，跳过..."
else
    echo "# 正在安装软件前端..."
    cp web $NVR_MANAGER_WEB_HOME -r
    cp etc/nvr-manager.conf /etc/nginx/conf.d/
    # 删除nginx默认欢迎页，不然直接访问不会出现前端页面
    rm -rf /etc/nginx/sites-enabled/default
    systemctl enable nginx --now && systemctl reload nginx
fi

function test-nvr-manager() {
    $PYTHON -c "
import requests
try:    
    if requests.get('http://localhost:5000/').ok:
        exit(0)
    else:
        exit(1)
except Exception as e:
    exit(1)
    raise e
"
}

MAX_RETRIES=30  # 最大重试次数
RETRY_INTERVAL=2  # 重试间隔（秒）
retries=0
test-nvr-manager
while [ $? -ne 0 ]; do
    retries=$((retries+1))
    if [ $retries -gt $MAX_RETRIES ]; then
        echo "无法连接到服务，安装失败，请用[systemctl status nvr-manager]或者[journalctl -u nvr-manager -r]命令查看日志..."
        exit 1
    fi
    sleep $RETRY_INTERVAL
    test-nvr-manager
done

echo "# 正在安装摄像头画面转播程序..."
$($PYTHON -c "
import requests
requests.post('http://localhost:5000/ai-project', data={'git_url': '${AIPROJECT_FORWARD}', 'default': True})
")

echo "# 正在安装默认样例AI算法..."
$($PYTHON -c "
import requests
requests.post('http://localhost:5000/ai-project', data={'git_url': '${AIPROJECT_DEFAULT}'})
")

echo "# 安装完成!"