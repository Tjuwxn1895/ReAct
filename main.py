import re
import os
import sys
from datetime import datetime
from openai import OpenAI


def safe_input():
    """从 stdin 读一行，兼容 UTF-8 与 GBK 等终端编码，避免 UnicodeDecodeError。"""
    raw = sys.stdin.buffer.readline()
    for enc in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return raw.decode(enc).rstrip("\r\n")
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace").rstrip("\r\n")

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
# 3.提示词模板（所有可用工具说明）
# 注意：下方 prompt 在 query() 中通过 Agent(prompt) 传入，实际进入 Agent.__init__(system=prompt)，
# 即作为 system 参数 → 赋给 self.system → 在 __init__ 里调用 add_message("system", self.system)，
# 从而作为「系统消息」写入 self.messages，并在每次 get_response() 时随 messages 发给 API。
TOOLS_DESCRIPTION = """
- calculate(what)：计算数学表达式。格式：Action: calculate: 表达式
  例：Action: calculate: 3+5*2

- average_dog_weight(name)：查询某品种狗的平均体重（如 Bulldog, Scottish Terrier, Border Collie, Toy Poodle）。
  格式：Action: average_dog_weight: 品种名
  例：Action: average_dog_weight: Bulldog

- get_weather(location) 或 weather_search(location)：查询某城市/地点的当前天气。
  格式：Action: get_weather: 城市或地名
  例：Action: get_weather: 天津

- generate_code(language, description)：根据编程语言和需求描述生成代码。
  格式：Action: generate_code: 编程语言, 需求描述（用英文逗号+空格分隔）
  例：Action: generate_code: python, 写一个快速排序

- save_code_to_file(code, language, description)：将已有代码保存到文件。
  格式：Action: save_code_to_file: 编程语言, 需求描述, 代码内容（代码中若有逗号可用分号;分隔前三项）
  例：先 generate_code 得到代码，再调用本工具保存。

- generate_and_save_code(language, description)：生成代码并直接保存到文件。
  格式：Action: generate_and_save_code: 编程语言, 需求描述
  例：Action: generate_and_save_code: python, 写一个斐波那契函数
""".strip()

prompt = """
You run in a loop of Thought, Action, PAUSE, Observation.
At the end of the loop you output an Answer.
Use Thought to describe your thoughts about the question you have been asked.
Use Action to run one of the actions available to you - then return PAUSE.
Observation will be the result of running those actions.

Your available actions (use exactly these names):

""" + TOOLS_DESCRIPTION + """

Example session:

Question: How much does a Bulldog weigh?
Thought: I should look the dogs weight using average_dog_weight
Action: average_dog_weight: Bulldog
PAUSE

You will be called again with this:

Observation: A Bulldog weights 51 lbs

You then output:

Answer: A bulldog weights 51 lbs

Weather example:
Action: get_weather: 天津
""".strip()

# 2.工具准备
# 2.1 计算器工具
def calculate(what):
    return eval(what)

#print(calculate("3 + 7 * 2"))   # 返回 17
#print(calculate("10 / 4"))      # 返回 2.5

# 2.2 天气查询工具（使用 Open-Meteo 免费 API，无需 key）
import requests
import time

def _get_json(url, params=None, timeout=(5, 25), retries=2, backoff=0.6):
    """
    简单的 GET + JSON + 重试封装。
    :param timeout: (connect_timeout, read_timeout)
    """
    last_err = None
    headers = {"User-Agent": "ReAct-WeatherTool/1.0"}
    for i in range(retries + 1):
        try:
            resp = requests.get(url, params=params, timeout=timeout, headers=headers)
            resp.raise_for_status()
            return resp.json()
        except (requests.exceptions.RequestException, ValueError) as e:
            last_err = e
            if i < retries:
                time.sleep(backoff * (2 ** i))
                continue
            raise last_err

def get_weather(location):
    """
    查询指定城市/地点的当前天气。
    :param location: 城市名或地名，如 "北京"、"上海"、"Tokyo"
    :return: 天气信息 dict，失败时含 error 键
    """
    location = (location or "").strip()
    if not location:
        return {"error": "location 不能为空"}

    # 先尝试 Open-Meteo（更结构化）
    try:
        # 支持直接传入 "lat,lon" 来跳过地名解析
        lat = lon = None
        name = location
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$", location)
        if m:
            lat, lon = float(m.group(1)), float(m.group(2))
        else:
            geo_url = "https://geocoding-api.open-meteo.com/v1/search"
            geo_params = {"name": location, "count": 1, "language": "zh"}
            geo_data = _get_json(geo_url, params=geo_params, timeout=(5, 25), retries=2)
            results = geo_data.get("results") or []
            if not results:
                raise ValueError(f"未找到地点：{location}")
            lat = results[0]["latitude"]
            lon = results[0]["longitude"]
            name = results[0].get("name", location)

        weather_url = "https://api.open-meteo.com/v1/forecast"
        weather_params = {
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
        }
        weather_data = _get_json(weather_url, params=weather_params, timeout=(5, 25), retries=2)
        w = (weather_data or {}).get("current", {}) or {}
        summary = (
            f"{name}：当前气温 {w.get('temperature_2m', '—')}°C，"
            f"湿度 {w.get('relative_humidity_2m', '—')}%，"
            f"风速 {w.get('wind_speed_10m', '—')} km/h"
        )
        return {
            "provider": "open-meteo",
            "summary": summary,
            "location": name,
            "temperature": w.get("temperature_2m"),
            "humidity": w.get("relative_humidity_2m"),
            "wind_speed_kmh": w.get("wind_speed_10m"),
        }
    except Exception as e:
        open_meteo_err = str(e)

    # Open-Meteo 失败则降级到 wttr.in（通常在受限网络更容易通）
    try:
        wttr_url = f"https://wttr.in/{location}"
        wttr_params = {"format": "j1", "lang": "zh"}
        data = _get_json(wttr_url, params=wttr_params, timeout=(5, 25), retries=2)
        cur = ((data or {}).get("current_condition") or [{}])[0] or {}
        desc = (((cur.get("weatherDesc") or [{}])[0]) or {}).get("value")
        summary = (
            f"{location}：当前气温 {cur.get('temp_C', '—')}°C，"
            f"湿度 {cur.get('humidity', '—')}%，"
            f"风速 {cur.get('windspeedKmph', '—')} km/h"
            + (f"，天气 {desc}" if desc else "")
        )
        return {
            "provider": "wttr.in",
            "summary": summary,
            "location": location,
            "temperature": float(cur["temp_C"]) if "temp_C" in cur and str(cur["temp_C"]).strip() != "" else None,
            "humidity": int(cur["humidity"]) if "humidity" in cur and str(cur["humidity"]).strip() != "" else None,
            "wind_speed_kmh": float(cur["windspeedKmph"]) if "windspeedKmph" in cur and str(cur["windspeedKmph"]).strip() != "" else None,
            "desc": desc,
            "open_meteo_error": open_meteo_err,
        }
    except Exception as e:
        return {"error": f"天气查询失败（open-meteo: {open_meteo_err}；wttr.in: {e}）"}
#print(get_weather("北京"))

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
                    "content": "你是一个代码生成助手。根据用户给出的编程语言和需求描述，只输出可运行的完整代码。要求：1）不要用 markdown 代码块（不要用 ``` 包裹）；2）不要任何解释说明；3）必须输出从第一行到最后一行的全部代码，不能只写头文件或开头几行就结束。"
                },
                {
                    "role": "user",
                    "content": f"编程语言：{language}\n需求描述：{description}"
                }
            ],
            max_tokens=8192,
            temperature=0.2,
        )
        code = response.choices[0].message.content.strip()
        # 若返回过短（疑似被截断），尝试再请求一次
        if len(code) < 150 and ("include" in code or "import" in code):
            response2 = client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "你只输出完整可运行代码，不要 markdown 包裹，不要解释，必须输出全部代码不能省略。"},
                    {"role": "user", "content": f"编程语言：{language}\n需求：{description}\n请输出完整代码，不要只写头文件或前几行。"},
                ],
                max_tokens=8192,
                temperature=0.2,
            )
            code = response2.choices[0].message.content.strip()
        return code
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

# 2.4 查询列表小狗体重
def average_dog_weight(name):
    if name in "Scottish Terrier": 
        return("Scottish Terriers average 20 lbs")
    elif name in "Border Collie":
        return("a Border Collies average weight is 37 lbs")
    elif name in "Toy Poodle":
        return("a toy poodles average weight is 7 lbs")
    else:
        return("An average dog weights 50 lbs")


# 2.5 供 ReAct 单字符串调用的包装（Action 行只支持「名称: 一个字符串」）
def _generate_code_single(s):
    s = (s or "").strip()
    idx = s.find(", ")
    if idx >= 0:
        return generate_code(s[:idx].strip(), s[idx + 2 :].strip())
    return generate_code(s, "")


def _generate_and_save_code_single(s):
    s = (s or "").strip()
    idx = s.find(", ")
    if idx >= 0:
        return generate_and_save_code(s[:idx].strip(), s[idx + 2 :].strip())
    return generate_and_save_code(s, "")


def _save_code_to_file_single(s):
    parts = (s or "").split(", ", 2)
    if len(parts) < 3:
        return save_code_to_file("", parts[0] if parts else "python", parts[1] if len(parts) > 1 else "")
    return save_code_to_file(parts[2].strip(), parts[0].strip(), parts[1].strip())


known_actions = {
    "calculate": calculate,
    "average_dog_weight": average_dog_weight,
    "get_weather": get_weather,
    "weather_search": get_weather,  # 别名：模型有时会输出 weather_search
    "generate_code": _generate_code_single,
    "save_code_to_file": _save_code_to_file_single,
    "generate_and_save_code": _generate_and_save_code_single,
}

# 4.ReAct 循环
action_re = re.compile('^Action: (\w+): (.*)$') #正则表达式定义（识别 Action 行）
def query(question, max_turns=5): # max_turns 是最多允许模型推理的轮数，用于避免死循环
    i = 0
    # prompt 作为第一个参数传入 Agent，即 Agent.__init__(self, system=prompt)；
    # 在 __init__ 内赋给 self.system，并执行 add_message("system", self.system)，
    # 因此 prompt 作为「系统消息」加入 self.messages，在 get_response() 时随 messages 发给 API。
    bot = Agent(prompt)
    next_prompt = question #初始提示词
    while i < max_turns:
        i+=1
        res=bot.run(next_prompt)
        print(res)
        actions = [
            action_re.match(a) 
            for a in res.split('\n') 
            if action_re.match(a) #action_re.match(a) 匹配 Action 行
        ]
        if actions: #如果存在 Action 行
            # There is an action to run
            action, action_input = actions[0].groups() # 如果 actions 列表非空，则获取 Action 名称和 Action 输入的参数
            if action not in known_actions: # 如果 Action 名称不在 known_actions 列表中，则抛出异常
                raise Exception("Unknown action: {}: {}".format(action, action_input))
            print(" -- running {} {}".format(action, action_input)) # 打印正在运行的 Action 名称和 Action 输入的参数
            observation = known_actions[action](action_input) # 调用 Action 函数，并获取返回值
            print("Observation:", observation) # 打印 Observation 返回值
            next_prompt = "Observation: {}".format(observation) #将 Observation 返回模型,作为下一轮对话的内容
        else:
            return res #如果不存在 Action 行，则返回结果

print("请输入问题：")
question = safe_input()
query(question)