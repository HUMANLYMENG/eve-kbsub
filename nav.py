import asyncio
import json
import sqlite3
import aiohttp
from bs4 import BeautifulSoup
import re

async def name_ex(system_name, cursor):
    if contains_chinese(system_name):
        system_id = get_system_id(system_name)
    else:
        system_id = None

    # 查询给定 solarSystemName or ID 下的所有物品
    query = '''
    SELECT solarSystemName, solarSystemID
    FROM mapSolarSystems
    WHERE solarSystemName LIKE ? COLLATE NOCASE OR solarSystemID = ?
    '''
    cursor.execute(query, (f"{system_name}%", system_id))
    item = cursor.fetchall()
    if item[0] != []:
        en_name, sys_id = item[0]
    else:
        return None
    
    with open('zh_systems.json', 'r', encoding='utf-8') as f:
        systems = json.load(f)
    details = systems.get(str(sys_id))
    if details:
        zh_name = details[1]
    
    return zh_name, en_name


# Function to check if a string contains Chinese characters
def contains_chinese(text):
    # This regex matches any Chinese character
    return bool(re.search(r'[\u4e00-\u9fff]', text))

def get_system_id(name):
    # Load the JSON data from the file
    with open('zh_systems.json', 'r', encoding='utf-8') as f:
        eve_systems = json.load(f)

    for system_id, details in eve_systems.items():
        if details[1] == name:  # The name is the second element in the list
            return system_id

    # 如果没有完全匹配，则进行模糊匹配（检查输入是否为系统名称的一部分）
    for system_id, details in eve_systems.items():
        if details[1].startswith(name):
            return system_id
    return None  # If no system found

async def get_jump_route(ship, range_, start, end):
    conn = sqlite3.connect("mapSolarSystems.db")
    cursor = conn.cursor()

    en_names, zh_names = [], []
    for system_name in [start, end]:
        zh_name, en_name = await name_ex(system_name, cursor)
        en_names.append(en_name)
        zh_names.append(zh_name)

    url = f'https://evemaps.dotlan.net/jump/{ship},{range_}/{en_names[0]}:{en_names[1]}'
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "zh-CN,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as resp:
            html_content = await resp.text()

    soup = BeautifulSoup(html_content, 'html.parser')
    table = soup.find("table", class_="tablelist")
    if not table:
        return "无法获取路线信息，可能网址结构有变化或请求有误。"

    # 获取系统行和跳跃行
    system_rows = table.find_all("tr", class_="tlr0")
    jump_rows = table.find_all("tr", class_="tlr1")

    systems = []
    for row in system_rows:
        tds = row.find_all("td")
        if len(tds) >= 3:
            # 先尝试从 <b> 标签中获取
            b_tag = tds[2].find("b")
            system_name = ""
            if b_tag:
                a_tag = b_tag.find("a")
                if a_tag and a_tag.get_text(strip=True):
                    system_name = a_tag.get_text(strip=True)
                else:
                    system_name = b_tag.get_text(strip=True)
            # 如果依然为空，遍历所有 <a> 标签获取非空文本
            if not system_name:
                a_tags = tds[2].find_all("a")
                for a in a_tags:
                    text = a.get_text(strip=True)
                    if text:
                        system_name = text
                        break
            systems.append(system_name)

    # 提取距离和燃料数据（直接从 <b> 标签中获取）
    total_distance = 0.0
    total_fuel = 0
    for row in jump_rows:
        distance_tag = row.select_one("td[colspan='2'] b")
        fuel_tag = row.select_one("td[colspan='4'] b")
        row_distance = 0.0
        row_fuel = 0
        if distance_tag:
            distance_text = distance_tag.get_text(strip=True)
            # 提取数字部分
            distance_text = re.sub(r"[^\d.]", "", distance_text)
            try:
                row_distance = float(distance_text)
            except Exception:
                row_distance = 0.0
        if fuel_tag:
            fuel_text = fuel_tag.get_text(strip=True).replace(',', '')
            try:
                row_fuel = int(fuel_text)
            except Exception:
                row_fuel = 0
        total_distance += row_distance
        total_fuel += row_fuel

    # 转换系统名称为中英文组合（确保 name_ex 返回正确的名称）
    systems_converted = []
    for s in systems:
        zh_name, en_name = await name_ex(s, cursor)
        systems_converted.append(f"{zh_name}({en_name})")
    route_str = " --> ".join(systems_converted)

    return (route_str, total_fuel, total_distance)


# 测试调用
if __name__ == '__main__':
    ship = 'Archon'
    jump_range = '544'
    start = '4-HWWF'
    end = '耶舒尔'
    route_str, total_fuel, total_distance = asyncio.run(get_jump_route(ship, jump_range, start, end))
    output = (f"跳跃路线：{route_str}\n"
              f"总共消耗燃料：{total_fuel} 同位素\n"
              f"总共光年距离：{total_distance:.3f} ly\n"
              f"校对V 燃料节约IV 跳货IV")
    print(output)
