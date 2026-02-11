import re
import os
from datetime import datetime
from openai import OpenAI

client = OpenAI(
    api_key="sk-6e09b2f6b8d143b1ad6ea1299913583e",
    base_url="https://api.deepseek.com/v1"
)

# 1.构建一个支持 LLM 对话的类，用于与大语言模型进行交互，同时记录完整的对话信息
class Agent:
    def __init__(self,system="You are a helpful assistant."):
        self.system=system
        self.messages=[]
        if self.system:
            self.add_message("system",system) #添加系统提示词

    def add_message(self,role,content):
        self.messages.append({"role":role,"content":content})
        return self.messages

    def get_response(self):
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=self.messages
        )
        return response.choices[0].message.content #response.choices：所有候选回复的列表（不指定 n 时通常长度为 1）。
    
    def run(self,input):
        self.add_message("user",input)
        response=self.get_response()
        self.add_message("assistant",response)
        return response

"""
abot=Agent()
res=abot.run("请为我介绍一下currency-ai的最新研究成果")
print(res)
"""
# 3.提示词模板
prompt = """
You run in a loop of Thought, Action, PAUSE, Observation.
At the end of the loop you output an Answer
Use Thought to describe your thoughts about the question you have been asked.
Use Action to run one of the actions available to you - then return PAUSE.
Observation will be the result of running those actions.
Your available actions are:
{known_actions}

Example session:

Question: How much does a Bulldog weigh?
Thought: I should look the dogs weight using average_dog_weight
Action: average_dog_weight: Bulldog
PAUSE

You will be called again with this:

Observation: A Bulldog weights 51 lbs

You then output:

Answer: A bulldog weights 51 lbs
""".strip()

# 2.工具准备
# 2.1 计算器工具
def calculate(what):
    return eval(what)

#print(calculate("3 + 7 * 2"))   # 返回 17
#print(calculate("10 / 4"))      # 返回 2.5

# 2.2 天气查询工具（使用 Open-Meteo 免费 API，无需 key）
import requests

def get_weather(location):
    """
    查询指定城市/地点的当前天气。
    :param location: 城市名或地名，如 "北京"、"上海"、"Tokyo"
    :return: 天气信息 dict，失败时含 error 键
    """
    try:
        # 1. 根据地名获取经纬度
        geo_url = "https://geocoding-api.open-meteo.com/v1/search"
        geo_params = {"name": location, "count": 1, "language": "zh"}
        geo_resp = requests.get(geo_url, params=geo_params, timeout=10)
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()
        results = geo_data.get("results") or []
        if not results:
            return {"error": f"未找到地点：{location}"}
        lat = results[0]["latitude"]
        lon = results[0]["longitude"]
        name = results[0].get("name", location)
        # 2. 获取天气
        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        }
        weather_resp = requests.get(weather_url, params=weather_params, timeout=10)
        weather_resp.raise_for_status()
        w = weather_resp.json().get("current", {})
        summary = (
            f"{name}：当前气温 {w.get('temperature_2m', '—')}°C，"
            f"湿度 {w.get('relative_humidity_2m', '—')}%，"
            f"风速 {w.get('wind_speed_10m', '—')} km/h"
        )
        return {"summary": summary, "location": name, "temperature": w.get("temperature_2m"), "humidity": w.get("relative_humidity_2m")}
    except requests.exceptions.RequestException as e:
        return {"error": f"请求失败：{e}"}
print(get_weather("北京"))

# 2.3 代码生成工具：根据编程语言和需求描述，调用 LLM 生成代码
def generate_code(language, description):
    """
    :param language: 编程语言，如 "python", "javascript", "java"
    :param description: 需求描述，如 "写一个快速排序"、"读取 CSV 并求平均值"
    :return: 生成的代码字符串，若失败返回包含 error 的 dict
    """
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {
                    "role": "system",
                    "content": "你是一个代码生成助手。根据用户给出的编程语言和需求描述，只输出可运行的代码，不要用 markdown 代码块包裹，不要多余解释。若需要多行，直接输出代码本身。"
                },
                {
                    "role": "user",
                    "content": f"编程语言：{language}\n需求描述：{description}"
                }
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        return {"error": str(e), "language": language, "description": description}


# 语言别名 -> 规范键（用于查扩展名）
_LANG_ALIASES = {
    "c++": "cpp",
    "c#": "cs",
    "csharp": "cs",
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
}

# 规范语言 -> 默认文件名（用于保存）
_LANG_FILENAMES = {
    "python": "main.py",
    "javascript": "main.js",
    "java": "Main.java",
    "go": "main.go",
    "rust": "main.rs",
    "cpp": "main.cpp",
    "c": "main.c",
    "cs": "Main.cs",
    "typescript": "main.ts",
    "ruby": "main.rb",
    "php": "main.php",
}


def _language_to_filename(language):
    """根据编程语言（含别名如 C++、c#）返回默认文件名。"""
    key = (language or "").strip().lower()
    key = _LANG_ALIASES.get(key, key)
    return _LANG_FILENAMES.get(key, f"main.{key}" if key else "main.txt")


def _strip_markdown_code_block(text):
    """去掉 LLM 可能返回的 ```lang ... ``` 包裹，只保留中间代码。"""
    if not text or "```" not in text:
        return text.strip()
    # 匹配 ```lang 或 ``` 开头的块
    m = re.search(r"^```[\w]*\s*\n?(.*?)```", text.strip(), re.DOTALL)
    if m:
        return m.group(1).strip()
    # 只有开头 ``` 没有结尾
    if text.strip().startswith("```"):
        return re.sub(r"^```[\w]*\s*\n?", "", text.strip())
    return text.strip()


def save_code_to_file(code, language, description="", base_dir="generated_code"):
    """
    将生成的代码保存到「base_dir/新建子文件夹/新建文件」中。
    :param code: 代码字符串
    :param language: 编程语言，用于确定扩展名和默认文件名
    :param description: 需求描述，用于子文件夹命名（会做安全化处理）
    :param base_dir: 根目录，相对于当前工作目录
    :return: 保存后的绝对路径，失败时返回 None 或抛出异常
    """
    # 新建子文件夹名：时间戳 + 描述前 20 字（去掉非法字符）
    safe_desc = re.sub(r"[^\w\u4e00-\u9fff\-]", "_", description or "code")[:20]
    folder_name = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + (safe_desc or "code")
    folder_path = os.path.join(base_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    # 根据语言（含 C++、c# 等别名）决定后缀
    filename = _language_to_filename(language)
    file_path = os.path.join(folder_path, filename)
    # 去掉可能被 LLM 包上的 ```lang ... ```
    code = _strip_markdown_code_block(code)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(code)
    return os.path.abspath(file_path)


def generate_and_save_code(language, description, base_dir="generated_code"):
    """
    生成代码并保存到「base_dir/新建文件夹/新建文件」。
    :return: {"code": 代码, "saved_path": 保存的绝对路径}，失败时含 "error" 键
    """
    result = generate_code(language, description)
    if isinstance(result, dict) and "error" in result:
        return result
    try:
        saved_path = save_code_to_file(result, language, description, base_dir)
        return {"code": result, "saved_path": saved_path}
    except Exception as e:
        return {"code": result, "error": str(e), "saved_path": None}


# 简单测试（取消注释运行）：language 传 "C++" 会保存为 main.cpp，传 "python" 为 main.py
# print(generate_code("python", "写一个函数，计算斐波那契数列第 n 项"))
# r = generate_and_save_code("C++", "写一个C++程序，计算斐波那契数列第 n 项")
# print(r.get("saved_path"), r.get("code", "")[:200])

def average_dog_weight(name):
    if name in "Scottish Terrier": 
        return("Scottish Terriers average 20 lbs")
    elif name in "Border Collie":
        return("a Border Collies average weight is 37 lbs")
    elif name in "Toy Poodle":
        return("a toy poodles average weight is 7 lbs")
    else:
        return("An average dog weights 50 lbs")

known_actions = {
    "calculate": calculate,
    "average_dog_weight": average_dog_weight,
    "get_weather": get_weather,
    "generate_code": generate_code,
    "save_code_to_file": save_code_to_file,
    "generate_and_save_code": generate_and_save_code
}