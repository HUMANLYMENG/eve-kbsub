import math
import json
import re
import sqlite3


def calc_dist(system_name):
    if contains_chinese(system_name):
        system_id = get_system_id(system_name)
    else:
        system_id = None

    # 连接到 SQLite 数据库
    conn = sqlite3.connect("mapSolarSystems.db")
    cursor = conn.cursor()

    # 查询给定 solarSystemName or ID 下的所有物品
    query = '''
    SELECT solarSystemName, solarSystemID, x, y, z
    FROM mapSolarSystems
    WHERE solarSystemName = ? OR solarSystemID = ?
    '''
    cursor.execute(query, (system_name, system_id))
    item = cursor.fetchall()
    if item[0] != []:
        en_name, sys_id, x, y, z = item[0]
    else:
        return None
    
    with open('zh_systems.json', 'r', encoding='utf-8') as f:
        systems = json.load(f)
    details = systems.get(str(sys_id))
    if details:
        zh_name = details[1]

    Aeschee = [-231903056049268000.0000000000,75700998538223600.0000000000,50369064361674896.0000000000]
    Onne = [-225099431491648000.0000000000,4527977648202990.0000000000,41145937034677904.0000000000]
    Ladi = [-255130638704832992.0000000000,17954421519958100.0000000000,53881280567900704.0000000000]
    Lis = [-235501207370811008.0000000000,61950165909771400.0000000000,44082635893030600.0000000000]
    Jov = [-231267617331988000.0000000000,54099384589729600.0000000000,60132572822748304.0000000000]
    Adi = [-238488109227715008.0000000000,62350180592973104.0000000000,27991570612544700.0000000000]
    # 遍历所有物品，计算欧氏距离
    dist_aeschee = euclidean_distance(x, y, z, Aeschee[0], Aeschee[1], Aeschee[2])
    dist_onne = euclidean_distance(x, y, z, Onne[0], Onne[1], Onne[2])
    dist_ladi = euclidean_distance(x, y, z, Ladi[0], Ladi[1], Ladi[2])
    dist_lis = euclidean_distance(x, y, z, Lis[0], Lis[1], Lis[2])
    dist_jov = euclidean_distance(x, y, z, Jov[0], Jov[1], Jov[2])
    dist_adi = euclidean_distance(x, y, z, Adi[0], Adi[1], Adi[2])

    ly_aes = dist_aeschee/9460000000000000
    ly_onne = dist_onne/9460000000000000
    ly_ladi = dist_ladi/9460000000000000
    ly_lis = dist_lis/9460000000000000
    ly_jov = dist_jov/9460000000000000
    ly_adi = dist_adi/9460000000000000

    return ly_aes, ly_onne, ly_ladi, ly_lis, ly_jov, ly_adi, en_name, zh_name

    
def euclidean_distance(x1, y1, z1, x0, y0, z0):
    return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)

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

# 调用测试
if __name__ == "__main__":
    system = "Aeschee"
    
    try:
        ly_aes, ly_onne, ly_ladi, ly_lis, ly_jov, ly_adi, en_name, zh_name = calc_dist(system)
        print(f"Aeschee: {ly_aes:.2f}")
        print(f"Onne: {ly_onne:.2f}")
        print(f"Ladi: {ly_ladi:.2f}")
        print(f"Lis: {ly_lis:.2f}")
        print(f"Jov: {ly_jov:.2f}")
        print(f"Adi: {ly_adi:.2f}")
        print(f"{en_name}, {zh_name}")
    except:
        print("Not Found")