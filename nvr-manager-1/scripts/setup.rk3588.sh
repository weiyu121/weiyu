# !/bin/bash
dpkg -i softwares/nd5g/utilneardi-nd5g1.0_arm64.deb
if [ $? -ne 0 ];then
    echo 'nd5g安装失败...'
    exit 1
fi

# 安装rk-ffmpeg（/usr/bin + /usr/lib）(https://github.com/jjm2473/ffmpeg-rk)
# 怕它系统里有个官方的ffmpeg，先执行命令卸载了再说
apt-get remove ffmpeg -y
if [ -e "/usr/bin/ffmpeg" ]; then
    echo "# rk-ffmpeg已安装，跳过..."
else
    echo "# 正在安装rk-ffmpeg..."
    cp softwares/ffmpeg/bin/* /usr/bin/ -r
    cp softwares/ffmpeg/lib/* /usr/lib/ -r
fi

# 安装npu运行时环境
cp softwares/rknpu/librknnrt.so /usr/lib/

# 安装miniconda（/usr/local/conda）
if [ -d $CONDA_HOME ]; then
    echo "# Miniconda已安装，跳过..."
else
    echo "# 正在安装Miniconda..."
    bash softwares/conda/Miniconda3-latest-Linux-aarch64.sh -b -p $CONDA_HOME 
    export PATH="$CONDA_HOME/bin:$PATH"
    conda init
    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/free/
    conda config --add channels https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main/
    conda config --set show_channel_urls yes
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple/
fi

# AI程序环境
conda create -y -n nvrpro python=3.9

AIPROJECT_FORWARD=git@gitee.com:research-group-2022/nvrpro-forward.git
AIPROJECT_DEFAULT=git@gitee.com:research-group-2022/nvrpro-airockchip-yolov7-rknn.git