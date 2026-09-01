# tans_to_zh

# 1. 安装 Ollama
brew install ollama
// 启动服务端（首选，注册为后台服务）
brew services start ollama
// 启动后检查服务状态：应显示 started
brew services list | grep ollama
// 验证服务端已就绪
curl http://localhost:11434/api/tags
// 常用命令：
ollama list                     # 查看已下载的模型列表
ollama pull translategemma:12b  # 下载模型（等价于 run 时自动拉取）
ollama rm translategemma:4b     # 删除某个模型
ollama show translategemma:12b  # 查看模型详情（参数量、量化档、上下文长度等）
ollama cp a b                   # 复制模型（改名）
ollama run translategemma:12b              # 进入交互式对话
ollama run translategemma:12b "Hello"      # 单次提问，返回后退出
ollama run translategemma:12b < file.txt   # 从文件输入
ollama serve                    # 前台启动服务（终端保持打开）
brew services start ollama      # 注册为后台服务，开机自启（macOS 推荐）
brew services stop ollama       # 停止后台服务
brew services list | grep ollama  # 查看服务状态
ollama ps   # 确认模型已加载、占用多少内存




# 2. 按内存拉取对应模型
ollama run translategemma:4b    # 8GB 内存
ollama run translategemma:12b   # 16GB 内存
ollama run translategemma:27b   # 24GB+ 内存

# 3.用conda添加Python环境
conda create -n tans_to_zh python=3.11（3.11为python版本号）
conda activate tans_to_zh
删除指定环境：conda env remove -n tans_to_zh


# 4.将创建的环境放到pycharm
用conda env list查看创建环境所在路径，在pycharm上配置【pycharm软件右下角配置解释器，即当前使用的python版本】


# 5.安装包
(1)命令行执行；
conda install 包名
(2)用pycharm终端安装
pip install 包名
(3)pycharm左下角【python软件包】中搜索安装
包有 torch,transformers,sentencepiece,fastapi,uvicorn,sacremoses

# 6.常用命令
创建环境	conda create --name <env_name>	可指定 Python 版本，如 conda create -n myenv python=3.10
激活环境	conda activate <env_name>	
退出环境	conda deactivate	回到 base 环境
列出所有环境	conda env list 或 conda info --envs	当前激活的环境前会有 * 标记
删除环境	conda remove --name <env_name> --all	
克隆环境	conda create --clone <old_env> -n <new_env>	
重命名环境	conda rename -n <old_name> <new_name>	
导出环境	conda env export > environment.yml	导出为 YAML 文件，便于分享
导入环境	conda env create -f environment.yml	从 YAML 文件创建环境


# 7.本项目安装包：
pip install requests beautifulsoup4 fastapi "uvicorn[standard]" pydantic


# 8.启动命令：
python trans_to_zh.py


curl -X POST http://localhost:8882/translate -H 'Content-Type: application/json' -d '{"text": "Hello world"}'


