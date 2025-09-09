import asyncio
import threading
import yaml
import sqlite3
import requests
import aiohttp
import traceback
import logging
from datetime import datetime
import time
import os
import json
from PIL import Image, ImageDraw, ImageFont
from collections import defaultdict
import csv
from io import BytesIO
import re

# 从include导入的常量
from include import *

ACHAR_SIZE = 80
WP_SIZE = 40

# 如果需要日志记录
logger = logging.getLogger("subkill")
################################################################################
# 主程序入口
################################################################################

async def get_session():
    """获取共享的aiohttp会话对象"""
    global global_session
    if global_session is None or global_session.closed:
        global_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            connector=aiohttp.TCPConnector(
                limit=10,
                ttl_dns_cache=300,
                force_close=False,
                enable_cleanup_closed=True
            )
        )
    return global_session

async def main():
    """主函数"""
    try:
        # 初始化数据库和图像管理器
        db_manager = DBManager()
        image_manager = ImageManager()
        killmail_processor = KillmailProcessor(db_manager, image_manager)
        

        # 参数设置 (从 include.py 导入)
        isk_threshold = ISK_THRESHOLD
        vip_characters = vips  # VIP角色ID列表  
        specific_kill = None  # 特定击杀ID，设为None则监控新击杀
        
        logger.info("EVE击杀监控系统启动...")
        
        if specific_kill:
            logger.info(f"获取特定击杀: {specific_kill}")
            killmail, zkb = await killmail_processor.listen_for_new_kills(specific_kill)
            if killmail and zkb:
                image, officer, system, vip, vip_kill = await killmail_processor.fetch_killmails(
                    killmail, zkb, isk_threshold, vip_characters
                )
                if image:
                    logger.info(f"成功生成击杀图片: {image}")
                    print(f"图片保存在: {image}")
                else:
                    logger.warning(f"未能生成击杀图片")
            else:
                logger.error(f"未找到击杀ID: {specific_kill}")
        else:
            # 持续监控模式
            while True:
                try:
                    logger.info("等待新击杀...")
                    killmail, zkb = await killmail_processor.listen_for_new_kills()
                    
                    if killmail and zkb:
                        logger.info(f"发现新击杀! ID: {killmail.get('killmail_id')}")
                        image, officer, system, vip, vip_kill = await killmail_processor.fetch_killmails(
                            killmail, zkb, isk_threshold, vip_characters
                        )
                        
                        if image:
                            logger.info(f"成功生成击杀图片: {image}, 系统: {system}")
                            print(f"新击杀图片: {image}")
                            
                        # 限速
                        await asyncio.sleep(2)
                    else:
                        # 没有新击杀，等待再查询
                        await asyncio.sleep(5)
                        
                except Exception as e:
                    logger.error(f"处理击杀时出错: {e}")
                    logger.error(traceback.format_exc())
                    await asyncio.sleep(10)
    finally:
        # 资源释放
        if global_session and not global_session.closed:
            await global_session.close()
        if 'db_manager' in locals():
            db_manager.close()
        logger.info("EVE击杀监控系统关闭")

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("eve_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("eve_monitor")

# 常量和配置
ID_URL = "https://esi.evetech.net/latest/universe/ids/?datasource=tranquility&language=en"
path = "/tmp/subkillmail_final.png"
output_path = os.path.dirname(__file__) + path

# 定义多个API终点以提高可靠性
ZKILLBOARD_API_ENDPOINTS = [
    f"https://zkillredisq.stream/listen.php?queueID={QUEUE_ID}&ttw=1",
]

ZKILLBOARD_5B_URL = "https://zkillboard.com/api/kills/iskValue/5000000000/"
headers = {
    'User-Agent': USER_AGENT, //Write your email here
    'Accept-Encoding': 'json'
}
params = {
    'limit': 1,  # 只取最近一条
    'use_page': '1',
    'no-Cache': 1
}

# 全局变量
global_session = None
db_lock = asyncio.Lock()

class DBManager:
    """数据库管理类，处理与SQLite的所有交互"""
    
    def __init__(self, db_path='items.db'):
        self.db_path = db_path
        self.connection = None
        self.cursor = None
        self._local = threading.local()  # 为每个线程创建独立存储
        self.initialize_db()
    
    def get_connection(self):
        """获取当前线程的数据库连接"""
        if not hasattr(self._local, 'connection') or self._local.connection is None:
            self._local.connection = sqlite3.connect(self.db_path)
            self._local.cursor = self._local.connection.cursor()
        return self._local.connection, self._local.cursor
        
    def close(self):
        """关闭所有数据库连接"""
        if hasattr(self._local, 'connection') and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
            self._local.cursor = None
        
        # 主连接也关闭
        if self.connection:
            self.connection.close()
            self.connection = None
            self.cursor = None
    
    def initialize_db(self):
        """初始化数据库连接和表结构"""
        self.connection = sqlite3.connect(self.db_path)
        self.cursor = self.connection.cursor()
    
    def import_yaml_data(self):
        """从YAML文件导入物品数据到数据库"""
        try:
            with open('sde/fsd/types.yaml', 'r', encoding='utf-8') as file:
                items_data = yaml.safe_load(file)
                
                for item_id, item in items_data.items():
                    # 获取中文名称
                    name_zh = item['name'].get('zh', '')
                    # 获取英文名称
                    name_en = item['name'].get('en', '')
                    # 将中文和英文名称存储在一个字典中
                    name = json.dumps({'zh': name_zh, 'en': name_en}, ensure_ascii=False)
                    groupid = item.get('groupID', 0)
                    market_id = item.get('marketGroupID', 0)
                    
                    self.cursor.execute('''
                    INSERT OR REPLACE INTO items (id, name, market_id, groupid)
                    VALUES (?, ?, ?, ?)
                    ''', (item_id, name, market_id, groupid))
                
                self.connection.commit()
                logger.info("已成功从YAML导入物品数据")
        except Exception as e:
            logger.error(f"导入YAML数据失败: {e}")
            self.connection.rollback()
    
    def get_groupid(self, type_id):
        """获取物品的组ID"""
        _, cursor = self.get_connection()
        cursor.execute('SELECT groupid FROM items WHERE id = ?', (type_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None
    
    def get_item_name(self, type_id):
        """获取物品名称"""
        _, cursor = self.get_connection()
        cursor.execute('SELECT name FROM items WHERE id = ?', (type_id,))
        result = cursor.fetchone()
        if result:
            return result[0]
        return None
    
    def get_item_name_zh(self, type_id):
        """获取物品的中文名称"""
        name_json = self.get_item_name(type_id)
        if name_json:
            try:
                name_dict = json.loads(name_json)
                return name_dict.get('zh', '')
            except json.JSONDecodeError:
                logger.error(f"解析物品名称JSON失败: {name_json}")
                return ""
        
        # 如果数据库中没有，尝试从API获取
        url = f"https://sde.jita.space/latest/universe/types/{type_id}"
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            name = data.get("name", "Unknown")
            zh_name = name.get("zh", "Unknown")
            return zh_name
        except Exception as e:
            logger.error(f"从API获取物品名称失败 (ID: {type_id}): {e}")
            return "Unknown Item"

class ImageManager:
    """图像管理类，处理所有图像下载和缓存"""
    
    def __init__(self, cache_dir="sde/Types"):  #SDE_ICONS_DIR
        self.cache_dir = cache_dir
        
        # 创建缓存目录
        for directory in [
            cache_dir,
            f"{cache_dir}/characters",
            f"{cache_dir}/corporations", 
            f"{cache_dir}/alliances"
        ]:
            os.makedirs(directory, exist_ok=True)
            
        logger.info(f"图像缓存目录初始化完成: {cache_dir}")
    
    def load_local_icon(self, item_type_id, icon_size=32):
        """从本地加载图标，如果不存在则返回None"""
        icon_filename = f"{item_type_id}_{icon_size}.png"
        icon_path = os.path.join(self.cache_dir, icon_filename)
        
        if os.path.exists(icon_path):
            try:
                icon_img = Image.open(icon_path)
                return icon_img
            except Exception as e:
                logger.error(f"加载图像 {icon_path} 失败: {e}")
                # 删除损坏的图像
                os.remove(icon_path)
                return None
        return None
    
    async def download_image(self, url, max_retries=3, retry_delay=1):
        """下载图像并支持本地缓存、重试机制和错误处理"""
        # 尝试从URL提取类型ID和尺寸用于缓存
        match = re.search(r'types/(\d+)/icon\?size=(\d+)', url)
        cache_path = None
        
        # 如果是EVE物品图标，创建缓存路径
        if match:
            type_id, size = match.groups()
            os.makedirs(self.cache_dir, exist_ok=True)
            cache_path = f"{self.cache_dir}/{type_id}_{size}.png"
            
            # 检查缓存
            if os.path.exists(cache_path):
                try:
                    return Image.open(cache_path).convert("RGBA")
                except Exception as e:
                    logger.warning(f"缓存图像损坏，将重新下载 {cache_path}: {e}")
                    # 缓存文件损坏，继续下载
        
        # 角色头像等其他图像类型
        elif "characters" in url or "corporations" in url or "alliances" in url:
            entity_type = "characters" if "characters" in url else "corporations" if "corporations" in url else "alliances"
            match = re.search(rf'{entity_type}/(\d+)', url)
            if match:
                entity_id = match.groups()[0]
                size_match = re.search(r'size=(\d+)', url)
                size = size_match.groups()[0] if size_match else "64"
                
                cache_subdir = f"{self.cache_dir}/{entity_type}"
                os.makedirs(cache_subdir, exist_ok=True)
                cache_path = f"{cache_subdir}/{entity_id}_{size}.png"
                
                if os.path.exists(cache_path):
                    try:
                        return Image.open(cache_path).convert("RGBA")
                    except Exception:
                        # 缓存文件损坏，继续下载
                        pass
        
        # 下载图像（带重试）
        for attempt in range(max_retries):
            try:
                session = await get_session()
                async with session.get(url, timeout=10) as r:
                    r.raise_for_status()
                    image_data = await r.read()
                    image = Image.open(BytesIO(image_data)).convert("RGBA")
                
                # 如果有缓存路径，保存图像
                if cache_path:
                    try:
                        image.save(cache_path)
                    except Exception as e:
                        logger.error(f"保存缓存图像失败 {cache_path}: {e}")
                
                return image
                
            except aiohttp.ClientError as e:
                # 网络错误，可以重试
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt)  # 指数退避
                    logger.warning(f"下载图像失败 {url}，尝试 {attempt+1}/{max_retries}，等待 {wait_time}秒: {e}")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"下载图像失败，已达最大重试次数 {url}: {e}")
                    
            except Exception as e:
                # 其他错误（如图像处理错误）
                logger.error(f"处理图像时出错 {url}: {e}")
                break
        
        # 所有尝试失败
        return None

class KillmailProcessor:
    """击杀邮件处理类，负责获取和处理击杀数据"""
    
    def __init__(self, db_manager, image_manager):
        self.db_manager = db_manager
        self.image_manager = image_manager
        
        # 加载CSV数据
        try:
            logger.info("加载EVE星系数据...")
            self.solar_systems = self.load_csv('sde/mapSolarSystems.csv', 'solarSystemID')
            self.constellations = self.load_csv('sde/mapConstellations.csv', 'constellationID')
            self.regions = self.load_csv('sde/mapRegions.csv', 'regionID')
            self.inv_types = self.load_csv('sde/invTypes.csv', 'typeID')
            logger.info(f"数据加载完成: {len(self.solar_systems)}个星系, {len(self.regions)}个区域")
        except Exception as e:
            print(f"load system fail: {e}")
    
    def load_csv(self, filename, key_field):
        """加载CSV数据到字典"""
        data = {}
        try:
            with open(filename, mode='r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    key = int(row[key_field])
                    data[key] = row
        except Exception as e:
            logger.error(f"加载CSV {filename} 失败: {e}")
        return data
    
    async def listen_for_new_kills(self, kill_id=None):
        """监听新的击杀，如果提供kill_id则获取特定击杀"""
        dns_retry_count = 0
        max_dns_retries = 5
        dns_retry_delay = 10  # 秒
        
        while dns_retry_count < max_dns_retries:
            try:
                session = await get_session()
                
                if kill_id:
                    # 获取特定击杀
                    killmail_url = f"https://zkillboard.com/api/killID/{kill_id}/"
                    async with session.get(killmail_url, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            # 假设返回的数据是一个列表，取第一个 killmail
                            killmail = data[0]
                            zkb = killmail.get("zkb")
                            return killmail, zkb
                        else:
                            logger.warning(f"获取特定击杀返回非200状态码: {response.status}")
                            text = await response.text()
                            logger.debug(f"响应文本: {text}")
                            return None, None
                else:
                    # 轮询新击杀
                    for endpoint in ZKILLBOARD_API_ENDPOINTS:
                        try:
                            logger.info(f"从 {endpoint} 获取新击杀")
                            async with session.get(endpoint, params=params, headers=headers) as response:
                                if response.status == 200:
                                    data = await response.json()
                                    package = data.get("package")
                                    if package:
                                        logger.info("检测到新击杀!")
                                        killmail = package.get("killmail")
                                        zkb = package.get("zkb")
                                        return killmail, zkb
                                    else:
                                        # 无新数据
                                        logger.debug("没有新击杀")
                                else:
                                    logger.warning(f"获取击杀返回非200状态码: {response.status}")
                        except Exception as e:
                            logger.error(f"尝试端点 {endpoint} 失败: {e}")
                            continue
                    
                    # 所有端点都失败
                    return None, None
                    
            except aiohttp.ClientConnectorDNSError as dns_err:
                dns_retry_count += 1
                logger.error(f"DNS解析失败 (尝试 {dns_retry_count}/{max_dns_retries}): {dns_err}")
                if dns_retry_count < max_dns_retries:
                    logger.info(f"等待 {dns_retry_delay} 秒后重试...")
                    await asyncio.sleep(dns_retry_delay)
                    dns_retry_delay *= 1.5  # 指数退避
                else:
                    logger.error("达到最大DNS重试次数，放弃")
                    return None, None
            except asyncio.TimeoutError:
                logger.error("请求超时")
                await asyncio.sleep(5)
                return None, None
            except Exception as e:
                logger.error(f"获取KM请求错误: {e}")
                traceback.print_exc()
                await asyncio.sleep(5)
                return None, None
    
    async def enrich_esi_killmail_data_async(self, killmail_data):
        """异步版本的enrich_esi_killmail_data，避免线程安全问题"""
        if not killmail_data:
            return {}
        
        # 获取受害者和攻击者信息
        victim = killmail_data.get('victim', {})
        attackers = killmail_data.get('attackers', [])

        # 收集所有需要解析的ID
        ids_to_resolve = set()
    
        # 收集ID的代码与原来相同...
    
        # 解析ID
        id_name_map = await asyncio.to_thread(self.resolve_names, list(ids_to_resolve))
    
        # 用异步方法获取物品名称
        victim['ship_type_name'] = await self.get_item_name_zh_async(victim.get('ship_type_id'))
    
        # 处理攻击者
        for attacker in attackers:
            attacker['character_name'] = id_name_map.get(attacker.get('character_id'))
            attacker['corporation_name'] = id_name_map.get(attacker.get('corporation_id'))
            attacker['alliance_name'] = id_name_map.get(attacker.get('alliance_id'))
            attacker['ship_type_name'] = id_name_map.get(attacker.get('ship_type_id'))
            attacker['weapon_type_name'] = id_name_map.get(attacker.get('weapon_type_id'))

        # 处理物品
        for itm in victim.get('items', []):
            itm_id = itm.get('item_type_id')
            itm['item_name'] = await self.get_item_name_zh_async(itm_id)
    
        # 返回结果
        return killmail_data

    async def get_item_name_zh_async(self, type_id):
        """异步获取物品中文名称"""
        if not type_id:
            return "Unknown Item"
    
        return await asyncio.to_thread(self.db_manager.get_item_name_zh, type_id)
    
    async def fetch_killmails(self, killmail, zkb, iskValue=None, vips=None):
        logger.info(f"Generating image")
        """处理击杀邮件数据"""
        if not killmail or not zkb:
            return None, None, None, None, None
            
        officer = False
        vip = False
        vip_kill = False
        valuable = False
        fetch_kill = False

        killmail_id = killmail.get('killmail_id')
        hash_value = zkb.get('hash')
        totalValue = zkb.get('totalValue')
        logger.info(f"ZKB: {zkb}")
        logger.info(f"KB Value: {totalValue}")

        if iskValue:
            character_id = killmail.get('victim', {}).get('character_id')

            if vips and character_id in vips:
                vip = True

            for attacker in killmail.get('attackers', []):
                ship_type_id = attacker.get('ship_type_id')
                if ship_type_id:
                    try:
                        groupId = self.db_manager.get_groupid(ship_type_id)
                        if groupId is not None:
                            groupId = int(self.db_manager.get_groupid(ship_type_id))
                            if groupId in officer_group_ids:
                                officer = True
                    except Exception as e:
                        logger.error(f"获取groupID时异常: {e}")
                
                if vips and attacker.get('character_id') in vips and attacker.get('final_blow') == True:
                    vip_kill = True
        
            if totalValue > iskValue:
                valuable = True
            else:
                logger.info(f"低价值击杀")
        else:
            fetch_kill = True

        if officer or valuable or vip or vip_kill or fetch_kill:
            if killmail_id and hash_value:
                # 使用ESI获取完整击杀信息
                esi_data = await asyncio.to_thread(self.fetch_esi_killmail, killmail_id, hash_value)
                if not esi_data:
                    return None, None, None, None, None
                    
                # 解析为名称
                enriched_data = await self.enrich_esi_killmail_data_async(esi_data)
                # enriched_data = await asyncio.to_thread(self.enrich_esi_killmail_data, esi_data)
                merged_data = enriched_data.copy()
                merged_data['zkb'] = zkb
                
                # 生成图像
                image, system = await self.format_final_output(merged_data)
                return image, officer, system, vip, vip_kill
            else:
                logger.error(f"在击杀邮件中找不到killmail_id或hash。")
                return None, None, None, None, None
        else:
            return None, None, None, None, None
    
    def fetch_esi_killmail(self, killmail_id, killmail_hash):
        """从ESI获取完整击杀邮件数据"""
        esi_url = f"https://esi.evetech.net/latest/killmails/{killmail_id}/{killmail_hash}/"
        try:
            r = requests.get(esi_url, timeout=20)
            r.raise_for_status()
            logger.info("ESI击杀邮件获取完成")
            return r.json()
        except Exception as e:
            logger.error(f"ESI击杀邮件获取失败: {e}")
            return None
    
    def get_slot_name(self, flag):
        """根据flag获取槽位名称"""
        if 27 <= flag <= 34:
            return "  高槽"
        elif 19 <= flag <= 26:
            return "  中槽"
        elif 11 <= flag <= 18:
            return "  低槽"
        elif 92 <= flag <= 99:
            return "  改装件"
        elif 125 <= flag <= 132:
            return "  子系统槽"
        elif flag in [87, 88]:
            return "  无人机舱"
        elif flag == 5:
            return "  货舱"
        elif flag == 90:
            return "  舰船维护舱"
        elif flag == 133:
            return "  燃料舱"
        elif flag == 155:
            return "  舰队机库"
        else:
            return f"  其他槽位"
    
    def enrich_esi_killmail_data(self, killmail_data):
        """丰富ESI击杀邮件数据，添加名称等信息"""
        if not killmail_data:
            return {}
            
        # 获取受害者和攻击者信息
        victim = killmail_data.get('victim', {})
        attackers = killmail_data.get('attackers', [])

        # 收集所有需要解析的ID
        ids_to_resolve = set()

        # Victim相关ID
        for key in ['character_id', 'corporation_id', 'alliance_id', 'ship_type_id']:
            if key in victim:
                ids_to_resolve.add(victim[key])

        # Attackers相关ID
        for attacker in attackers:
            for key in ['character_id', 'corporation_id', 'alliance_id', 'ship_type_id', 'weapon_type_id']:
                if key in attacker:
                    ids_to_resolve.add(attacker[key])

        # 解析受害者物品 (items)
        items = victim.get('items', [])
        item_ids = []
        for itm in items:
            # 可能是destroyed或dropped物品
            item_type_id = itm.get('item_type_id')
            if item_type_id:
                item_ids.append(item_type_id)

        # 将物品ID加入解析列表
        ids_to_resolve.update(item_ids)

        # 将ID列表转换成名称
        id_name_map = self.resolve_names(list(ids_to_resolve))

        # 给victim添加名称字段
        victim['character_name'] = id_name_map.get(victim.get('character_id'))
        victim['corporation_name'] = id_name_map.get(victim.get('corporation_id'))
        victim['alliance_name'] = id_name_map.get(victim.get('alliance_id'))
        victim['ship_type_name'] = self.db_manager.get_item_name_zh(victim.get('ship_type_id'))

        # 给attackers添加名称字段
        for attacker in attackers:
            attacker['character_name'] = id_name_map.get(attacker.get('character_id'))
            attacker['corporation_name'] = id_name_map.get(attacker.get('corporation_id'))
            attacker['alliance_name'] = id_name_map.get(attacker.get('alliance_id'))
            attacker['ship_type_name'] = id_name_map.get(attacker.get('ship_type_id'))
            attacker['weapon_type_name'] = id_name_map.get(attacker.get('weapon_type_id'))

        # 为items添加名称字段
        for itm in items:
            itm_id = itm.get('item_type_id')
            itm['item_name'] = self.db_manager.get_item_name_zh(itm_id)
            
        victim['items'] = items
        killmail_data['victim'] = victim
        killmail_data['attackers'] = attackers
        return killmail_data
    
    def resolve_names(self, ids_list):
        """使用ESI API将ID解析为名称"""
        if not ids_list:
            return {}
        
        # 去除重复的ID
        unique_ids = list(set(ids_list))
    
        url = "https://esi.evetech.net/latest/universe/names/"
        headers = {'Content-Type': 'application/json'}
    
        # 添加重试逻辑
        max_retries = 3
        retry_delay = 2  # 初始延迟秒数
        all_results = {}  # 将结果初始化移到这里
    
        for attempt in range(max_retries):
            try:
                # 分批处理，每次最多10个ID
                for i in range(0, len(unique_ids), 10):
                    batch = unique_ids[i:i+10]
                
                    # 添加日志以便调试
                    logger.debug(f"发送ID批次: {batch}")
                
                    r = requests.post(url, json=batch, headers=headers, timeout=15)
                    # 记录响应状态
                    logger.debug(f"ESI API响应状态码: {r.status_code}")
                
                    if r.status_code == 200:
                        results = r.json()
                    
                        # 确保结果是列表类型
                        if not isinstance(results, list):
                            logger.warning(f"收到非列表类型的响应: {type(results)}")
                            results = []
                    
                        try: 
                            for obj in results:
                                obj_id = obj.get('id')
                                obj_name = obj.get('name')
                                if obj_id and obj_name:
                                    all_results[obj_id] = obj_name
                        except Exception as e:
                            logger.error(f"解析名称时出错: {e}")
                
                    elif r.status_code == 400:
                        # 记录请求体以便调试
                        logger.error(f"ESI API返回400错误，请求体: {batch}")
                        logger.error(f"响应内容: {r.text}")
                    else:
                        logger.warning(f"ESI API返回非预期状态码: {r.status_code}")
                        continue  # 继续处理下一批
            
                # 如果所有批次都处理完毕，不管成功与否，跳出重试循环
                break
                    
            except Exception as e:
                logger.error(f"解析ID名称时发生异常: {e}")
                logger.error(traceback.format_exc())
            
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2  # 指数退避
    
        # 无论如何都返回结果字典，即使它是空的
        return all_results
    
    async def draw_item_with_icon(self, draw, base_img, x, y, item_name, item_type_id, qty_destroyed=0, qty_dropped=0, sub_flag=False):
        """绘制物品图标和名称"""
        # 下载图标
        icon_img = None
        if item_type_id:
            # 尝试从本地加载
            icon_img = self.image_manager.load_local_icon(item_type_id)
            if icon_img is None:
                # 从网络下载
                icon_url = f"https://images.evetech.net/types/{item_type_id}/icon?size=32"
                icon_img = await self.image_manager.download_image(icon_url)

        # 状态标识
        if qty_dropped > 0:
            qty = qty_dropped
        elif qty_destroyed > 0:
            qty = qty_destroyed
        else:
            qty = 1

        # 准备文本
        line_text = f"{item_name}"
        qty_x = 700 - 40 - draw.textlength(f"{qty}", font=SMALL_FONT)

        # 背景颜色（掉落的物品用绿色背景）
        if qty == qty_dropped:
            draw.rectangle([x - 2, y - 2, 680, y + 23], fill=DGREEN)
            
        # 子物品缩进
        if sub_flag:
            x += 20
            
        # 绘制图标
        icon_size = 24
        try:
            if icon_img:
                icon_img = icon_img.resize((icon_size, icon_size), Image.LANCZOS)
                if icon_img.mode == "RGBA":
                    base_img.paste(icon_img, (x, y), icon_img.split()[3])
                else:
                    base_img.paste(icon_img, (x, y))
        except Exception as e:
            logger.error(f"绘制物品图标失败: {e}")

        # 绘制文本
        text_x = x + icon_size + 5
        draw.text((text_x, y), line_text, font=ICONY_FONT, fill=WHITE)
        draw.text((qty_x, y), f"{qty}", font=ICON_FONT, fill=WHITE)
    
    # def resolve_names(self, ids_list):
    #     # 利用 ESI 的 /universe/names/ 接口来解析id为名称
    #     if not ids_list:
    #         return {}

    #     url = "https://esi.evetech.net/latest/universe/names/"
    #     headers = {'Content-Type': 'application/json'}
    #     r = requests.post(url, json=ids_list, headers=headers)
    #     r.raise_for_status()
    #     results = r.json()

    #     # 结果类似于 [{"category":"character","id":2112625428,"name":"Some Name"}, ...]
    #     id_name_map = {}
    #     for obj in results:
    #         obj_id = obj.get('id')
    #         obj_name = obj.get('name')
    #         if obj_id and obj_name:
    #             id_name_map[obj_id] = obj_name

    #     return id_name_map
    
    async def get_attacker_info(self, attacker, total_damage):
        """获取攻击者信息，包括图片和数据"""
        # 收集需要解析的ID
        ids_to_resolve = []
        for key in ['character_id', 'corporation_id', 'alliance_id', 'ship_type_id', 'weapon_type_id']:
            if attacker.get(key):
                ids_to_resolve.append(attacker.get(key))
    
        # 解析名称
        id_name_map = {}
        if ids_to_resolve:
            try:
                id_name_map = await asyncio.to_thread(self.resolve_names, ids_to_resolve)
            except Exception as e:
                logger.error(f"解析ID名称失败: {e}")
    
        # 获取攻击者信息
        character_id = attacker.get('character_id')
        corporation_id = attacker.get('corporation_id')
        alliance_id = attacker.get('alliance_id')
        ship_type_id = attacker.get('ship_type_id')
        weapon_type_id = attacker.get('weapon_type_id')
    
        # 从映射中获取名称，如果找不到则使用默认值
        char_name = id_name_map.get(character_id, "Unknown")
        corp_name = id_name_map.get(corporation_id, "")
        alliance_name = id_name_map.get(alliance_id, "")
        ship_name = id_name_map.get(ship_type_id, "")
        weapon_name = id_name_map.get(weapon_type_id, "Unknown Weapon")
    
        damage_done = attacker.get('damage_done', 0)
        final_blow = attacker.get('final_blow', False)
        dmg_percent = (damage_done / total_damage * 100) if total_damage else 0

        # 如果没有从ID映射获取到舰船名称，尝试从数据库获取
        if not ship_name and ship_type_id:
            try:
                ship_name = await asyncio.to_thread(self.db_manager.get_item_name_zh, ship_type_id) or "Unknown Ship"
            except Exception as e:
                logger.error(f"获取舰船名称失败 (ID: {ship_type_id}): {e}")
                ship_name = "Unknown Ship"
    
        # 如果没有角色名，使用舰船名替代
        if not char_name or char_name == "Unknown":
            char_name = ship_name or "Unknown Ship"

        # 下载舰船图片
        ship_img = None
        ship_img_64 = None
        if ship_type_id:
            # 尝试从本地加载
            ship_img = self.image_manager.load_local_icon(ship_type_id)
            ship_img_64 = self.image_manager.load_local_icon(ship_type_id, icon_size=64)
            
            # 如果本地没有，则下载
            if ship_img is None:
                # 下载64px版本
                ship_url = f"https://images.evetech.net/types/{ship_type_id}/icon?size=64"
                ship_img_64 = await self.image_manager.download_image(ship_url)
                
                # 下载32px版本
                ship_url = f"https://images.evetech.net/types/{ship_type_id}/icon?size=32"
                ship_img = await self.image_manager.download_image(ship_url)
                
                if ship_img:
                    ship_img = ship_img.resize((WP_SIZE, WP_SIZE), Image.LANCZOS)
                    ship_img_64 = ship_img  # 如果没有64px版本，使用32px版本代替
            else:
                ship_img = ship_img.resize((WP_SIZE, WP_SIZE), Image.LANCZOS)
                if ship_img_64:
                    ship_img_64 = ship_img_64.resize((ACHAR_SIZE, ACHAR_SIZE), Image.LANCZOS)
                else:
                    ship_img_64 = ship_img.resize((ACHAR_SIZE, ACHAR_SIZE), Image.LANCZOS)

        # 下载武器图片
        wp_img = None
        if attacker.get('weapon_type_id'):
            wp_img = self.image_manager.load_local_icon(attacker['weapon_type_id'])
            if wp_img is None:
                wp_url = f"https://images.evetech.net/types/{attacker['weapon_type_id']}/icon?size=32"
                wp_img = await self.image_manager.download_image(wp_url)
            
            if wp_img:
                wp_img = wp_img.resize((WP_SIZE, WP_SIZE), Image.LANCZOS)

        # 下载角色头像
        char_img = None
        if attacker.get('character_id'):
            char_url = f"https://images.evetech.net/characters/{attacker['character_id']}/portrait?size=64"
            char_img = await self.image_manager.download_image(char_url)
            
            if char_img:
                char_img = char_img.resize((ACHAR_SIZE, ACHAR_SIZE), Image.LANCZOS)
            elif ship_img_64:
                char_img = ship_img_64  # 使用舰船图片作为替代

        # 确保舰船名称有值
        ship_name = ship_name if ship_name else self.db_manager.get_item_name_zh(ship_type_id) or "Unknown Ship"
        char_name = ship_name if not char_name or char_name == 'Unknown' else char_name  # 如果没有角色名，使用舰船名
    
        
        # 打包信息为字典并返回
        return {
            'char_name': char_name or "Unknown",
            'corp_name': corp_name or "",
            'alliance_name': alliance_name or "",
            'damage_done': damage_done or 0,
            'dmg_percent': dmg_percent or 0,
            'char_img': char_img,
            'ship_img': ship_img,
            'ship_img_64': ship_img_64,
            'ship_name': ship_name or "Unknown Ship",
            'wp_img': wp_img,
            'weapon_name': weapon_name or "Unknown Weapon"
        }
    
    async def paint_attackers(self, background, draw, x, y, attacker_info):
        """绘制攻击者信息"""
        char_img = attacker_info['char_img']
        ship_img = attacker_info['ship_img']
        wp_img = attacker_info['wp_img']
        char_name = attacker_info['char_name'] or "Unknown"  # 确保有默认值
        corp_name = attacker_info['corp_name'] or ""
        alliance_name = attacker_info['alliance_name'] or ""
        damage_done = attacker_info['damage_done']
        dmg_percent = attacker_info['dmg_percent']

        # 绘制角色头像
        try:
            if char_img:
                background.paste(char_img, (x, y), char_img)
        except Exception as e:
            logger.error(f"绘制攻击者头像失败 ({char_name}): {e}")

        # 绘制舰船图标
        try:
            if ship_img:
                background.paste(ship_img, (x + ACHAR_SIZE, y))
        except Exception as e:
            logger.error(f"绘制攻击者舰船失败 ({char_name}): {e}")

        # 绘制武器图标
        try:
            if wp_img:
                if wp_img.mode == "RGBA":
                    background.paste(wp_img, (x + ACHAR_SIZE, y+WP_SIZE), wp_img.split()[3])
                else:
                    background.paste(wp_img, (x + ACHAR_SIZE, y+WP_SIZE))
        except Exception as e:
            logger.error(f"绘制攻击者武器失败 ({char_name}): {e}")
            # 如果武器图标失败，尝试使用舰船图标替代
            if ship_img:
                try:
                    background.paste(ship_img, (x + ACHAR_SIZE, y+WP_SIZE))
                except:
                    pass

        # 绘制攻击者信息文本 - 确保所有文本值都是字符串
        line1 = str(char_name) if char_name else "Unknown"
        line2 = str(corp_name) if corp_name else ""
        line3 = str(alliance_name) if alliance_name else ""
        line4 = f"{damage_done} ({dmg_percent:.1f}%)" 
    
        draw.text((x + ACHAR_SIZE + WP_SIZE + 5, y), line1, font=TEXT_FONT, fill=WHITE)
        line2_y = y + 20
        draw.text((x + ACHAR_SIZE + WP_SIZE + 5, line2_y), line2, font=SMALL_FONT, fill=WHITE)
        line3_y = line2_y + 20
        draw.text((x + ACHAR_SIZE + WP_SIZE + 5, line3_y), line3, font=SMALL_FONT, fill=WHITE)
        line4_y = line3_y + 20
        draw.text((x + ACHAR_SIZE + WP_SIZE + 5, line4_y), line4, font=SMALL_FONT, fill=GRAY)
    
    def merge_items(self, data):
        """合并相同的物品"""
        merged_data = {}
        
        for category, items in data.items():
            temp_dict = defaultdict(lambda: {'quantity_destroyed': 0, 'quantity_dropped': 0, 'item_name': '', 'sub_flag': False})
            for item in items:
                item_id = item['item_type_id']
                temp_item = temp_dict[item_id]
                
                # 更新物品名称
                temp_item['item_name'] = item.get('item_name', temp_item['item_name'])
                # 更新子物品标记
                temp_item['sub_flag'] = item.get('sub_item', temp_item['sub_flag'])
                
                # 累加摧毁数量
                if 'quantity_destroyed' in item:
                    temp_item['quantity_destroyed'] += item['quantity_destroyed']
                
                # 累加掉落数量
                if 'quantity_dropped' in item:
                    temp_item['quantity_dropped'] += item['quantity_dropped']
            
            # 转换回列表格式
            merged_items = []
            for item_id, attri in temp_dict.items():
                merged_item = {
                    'item_type_id': item_id,
                    'item_name': attri['item_name']
                }
                if attri['quantity_destroyed'] > 0:
                    merged_item['quantity_destroyed'] = attri['quantity_destroyed']
                if attri['quantity_dropped'] > 0:
                    merged_item['quantity_dropped'] = attri['quantity_dropped']
                if attri['sub_flag'] == True:
                    merged_item['sub_flag'] = attri['sub_flag']
                merged_items.append(merged_item)
            
            merged_data[category] = merged_items
        
        return merged_data
    
    def get_security_color(self, status):
        """根据安全等级获取显示颜色"""
        # 确保 security_status 在 0.0 ~ 1.0 范围内
        status = max(0.0, min(1.0, status))
        # 将 security_status 映射到颜色列表的索引 (0.0 ~ 1.0 映射到 0 ~ 10)
        index = int(status * 10)
        return SEC_COLOR[index]
    
    def generate_unique_output_path(self, killmail_id, base_dir="tmp"):
        """生成唯一的输出文件路径"""
        if not os.path.exists(base_dir):
            os.makedirs(base_dir)  # 如果目录不存在，则创建

        # 使用 killmail_id 和当前时间作为文件名，确保唯一性
        filename = f"{killmail_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        output_path = os.path.join(base_dir, filename)
        absolute_output_path = os.path.abspath(output_path)
        
        return absolute_output_path
    
    def get_system_info(self, system_id):
        """获取星系信息"""
        if not system_id:
            return (None, 0.0, None, None)

        # 首先尝试API获取
        url = f"https://esi.evetech.net/latest/universe/systems/{system_id}/?datasource=tranquility&language=zh"
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                data = response.json()
                system_name = data.get("name", None)
                security_status = data.get("security_status", 0.0)
                constellation_id = data.get("constellation_id", 0)
            else:
                # 本地查找星系信息
                system_info = self.solar_systems.get(system_id)
                if system_info:
                    system_name = system_info.get('solarSystemName', None)
                    security_status = float(system_info.get('security', 0.0))
                    constellation_id = int(system_info.get('constellationID', 0))
                else:
                    logger.error(f"获取星系信息失败，状态码: {response.status_code}")
                    return (None, 0.0, None, None)
        except Exception as e:
            # API请求失败，尝试本地数据
            logger.error(f"API获取星系信息失败: {e}")
            system_info = self.solar_systems.get(system_id)
            if system_info:
                system_name = system_info.get('solarSystemName', None)
                security_status = float(system_info.get('security', 0.0))
                constellation_id = int(system_info.get('constellationID', 0))
            else:
                return (None, 0.0, None, None)

        # 获取星座信息
        try:
            response = requests.get(f"https://esi.evetech.net/latest/universe/constellations/{constellation_id}/?datasource=tranquility&language=zh", headers=headers, timeout=10)
            if response.status_code == 200:
                cons_data = response.json()
                constellation = cons_data.get("name", None)
                region_id = cons_data.get("region_id", 0)
            else:
                # 本地查找星座信息
                constellation_info = self.constellations.get(constellation_id)
                if constellation_info:
                    constellation = constellation_info.get('constellationName', None)
                    region_id = int(constellation_info.get('regionID', 0))
                else:
                    logger.warning(f"无法找到星座信息，ID: {constellation_id}")
                    return (system_name, security_status, None, None)
        except Exception as e:
            # API请求失败，尝试本地数据
            logger.error(f"API获取星座信息失败: {e}")
            constellation_info = self.constellations.get(constellation_id)
            if constellation_info:
                constellation = constellation_info.get('constellationName', None)
                region_id = int(constellation_info.get('regionID', 0))
            else:
                return (system_name, security_status, None, None)

        # 获取区域信息
        try:
            response = requests.get(f"https://esi.evetech.net/latest/universe/regions/{region_id}/?datasource=tranquility&language=zh", headers=headers, timeout=10)
            if response.status_code == 200:
                region_data = response.json()
                region = region_data.get("name", None)
            else:
                # 本地查找区域信息
                region_info = self.regions.get(region_id)
                if region_info:
                    region = region_info.get('regionName', None)
                else:
                    logger.warning(f"无法找到区域信息，ID: {region_id}")
                    return (system_name, security_status, constellation, None)
        except Exception as e:
            # API请求失败，尝试本地数据
            logger.error(f"API获取区域信息失败: {e}")
            region_info = self.regions.get(region_id)
            if region_info:
                region = region_info.get('regionName', None)
            else:
                return (system_name, security_status, constellation, None)
                
        return (system_name, security_status, constellation, region)
    
    async def format_final_output(self, killmail_data):
        """格式化最终输出，生成图像"""
        if not killmail_data:
            return None, None
            
        #####################DRAW#################################################
        victim = killmail_data.get('victim', {})
        attackers = killmail_data.get('attackers', [])
        zkb_data = killmail_data.get('zkb', {})
        killmail_id = killmail_data.get('killmail_id', 'N/A')
        killmail_time = killmail_data.get('killmail_time', 'N/A')
        
        # 转换为 datetime 对象
        dt = datetime.strptime(killmail_time, "%Y-%m-%dT%H:%M:%SZ")
        killmail_time = dt.strftime("%Y-%m-%d %H:%M:%S")

        system_id = killmail_data.get('solar_system_id')
        system_info = await asyncio.to_thread(self.get_system_info, system_id)
        system_name, security_status, constellation, region = system_info
        
        if system_name is None:
            system_name = f"SystemID: {system_id}"
            
        # 死人信息
        victim_ids = []
        for key in ['character_id', 'corporation_id', 'alliance_id']:
            if victim.get(key):
                victim_ids.append(victim.get(key))

        # 解析名称
        victim_id_names = {}
        if victim_ids:
            try:
                victim_id_names = await asyncio.to_thread(self.resolve_names, victim_ids)
            except Exception as e:
                logger.error(f"解析死者ID名称失败: {e}")

        # 获取死者信息
        victim_char_id = victim.get('character_id')
        victim_corp_id = victim.get('corporation_id')
        victim_alliance_id = victim.get('alliance_id')
        victim_ship_id = victim.get('ship_type_id')

        # 从映射中获取名称，如果找不到则使用默认值
        victim_name = victim_id_names.get(victim_char_id, "Unknown")
        victim_corp = victim_id_names.get(victim_corp_id, "Unknown Corp")
        victim_alliance = victim_id_names.get(victim_alliance_id, "")

        # 获取舰船名称
        if victim.get('ship_type_name'):
            victim_ship = victim.get('ship_type_name')
        elif victim_ship_id:
            try:
                victim_ship = await asyncio.to_thread(self.db_manager.get_item_name_zh, victim_ship_id) or "Unknown Ship"
            except Exception as e:
                logger.error(f"获取死者舰船名称失败 (ID: {victim_ship_id}): {e}")
                victim_ship = "Unknown Ship"
        else:
            victim_ship = "Unknown Ship"

        damage_taken = victim.get('damage_taken', 0)
        
        # 处理受害者的物品清单
        items = victim.get('items', [])

        # 槽位顺序定义
        SLOT_ORDER = ["  高槽", "  中槽", "  低槽", "  改装件", "  子系统槽", "  无人机舱", "  货舱", "  燃料舱", "  舰船维护舱", "  舰队机库", "  其他槽位"]
        
        # 按槽位分组
        slot_groups = {}
        for itm in items:
            flag = itm.get('flag', -1)
            slot_name = self.get_slot_name(flag)
            if slot_name not in slot_groups:
                slot_groups[slot_name] = []
            slot_groups[slot_name].append(itm)
            sub_items = itm.get('items')
            if sub_items:
                for sub_item in sub_items:
                    sub_item_id = sub_item.get('item_type_id')
                    sub_item_name = self.db_manager.get_item_name_zh(sub_item_id)
                    sub_item.update({"item_name": sub_item_name})
                    sub_item.update({"sub_item": True})
                    slot_groups[slot_name].append(sub_item)
        
        # 合并后的数据
        merged = self.merge_items(slot_groups)
        item_num = 0
        for slot_name in merged:
            item_num += len(merged[slot_name])

        # 根据物品数量动态调整画布高度
        if item_num < 30:
            bg_height = 1000
        else:
            bg_height = item_num * 25 + 600
            
        # 生成画布
        img_width, img_height = 700, bg_height
        background = Image.new("RGB", (img_width, img_height), (30,30,30))
        draw = ImageDraw.Draw(background)

        # 批量准备图像下载任务
        image_download_tasks = []
        
        # 受害者角色头像
        victim_image_task = None
        if victim.get('character_id'):
            char_url = f"https://images.evetech.net/characters/{victim['character_id']}/portrait"
            victim_image_task = self.image_manager.download_image(char_url)
            image_download_tasks.append(('victim_image', victim_image_task))
        
        # 受害者舰船图片
        victimship_img_task = None
        if victim.get('ship_type_id'):
            ship_url = f"https://images.evetech.net/types/{victim['ship_type_id']}/icon?size=64"
            victimship_img_task = self.image_manager.download_image(ship_url)
            image_download_tasks.append(('victimship_img', victimship_img_task))
        
        # 公司图标
        corp_image_task = None
        if victim.get('corporation_id'):
            corp_url = f"https://images.evetech.net/corporations/{victim['corporation_id']}/logo?size=32"
            corp_image_task = self.image_manager.download_image(corp_url)
            image_download_tasks.append(('corp_image', corp_image_task))
        
        # 联盟图标
        allia_image_task = None
        if victim.get('alliance_id'):
            allia_url = f"https://images.evetech.net/alliances/{victim['alliance_id']}/logo?size=32"
            allia_image_task = self.image_manager.download_image(allia_url)
            image_download_tasks.append(('allia_image', allia_image_task))
        
        # 等待所有图像下载完成
        images = {}
        for name, task in image_download_tasks:
            try:
                images[name] = await task
            except Exception as e:
                logger.error(f"下载图像 {name} 失败: {e}")
                images[name] = None

        # 左上角头像及舰船图像区域
        avatar_x, avatar_y = 10, 10
        victim_size = 128
        
        ############## Left Half
        draw.rectangle([0, 0, avatar_x + victim_size*2 + 20, img_height], fill=BLACK)
        
        # 绘制受害者头像
        victim_image = images.get('victim_image')
        try:
            if victim_image:
                victim_image = victim_image.resize((victim_size, victim_size), Image.LANCZOS)
                background.paste(victim_image, (avatar_x, avatar_y), victim_image)
        except Exception as e:
            logger.error(f"绘制受害者头像失败: {e}")
        
        # 绘制受害者舰船图片
        victimship_img = images.get('victimship_img')
        try:
            if victimship_img:
                victimship_img = victimship_img.resize((victim_size, victim_size), Image.LANCZOS)
                background.paste(victimship_img, (avatar_x+130, avatar_y))
        except Exception as e:
            logger.error(f"绘制受害者舰船图片失败: {e}")

        # 绘制参与人数和伤害信息
        draw.text((avatar_x, avatar_y+victim_size+4), f"参与人数({len(attackers)})", font=SMALL_FONT, fill=GRAY)
        draw.text((avatar_x, avatar_y+victim_size+20), f"承受伤害: {damage_taken}", font=SUBTITLE_FONT, fill=RED)

        # 攻击者信息列表
        atk_x = avatar_x
        atk_y = avatar_y + 180
        
        # 计算总伤害
        total_damage = sum(a.get('damage_done', 0) for a in attackers)
        
        # 最后一击攻击者信息
        final_blow_attackers = [a for a in attackers if a.get('final_blow', False) is True]
        if final_blow_attackers:
            final_blow_line = f"最后一击:"
            draw.text((atk_x, atk_y), final_blow_line, font=SUBTITLE_FONT, fill=GRAY)
            atk_y += 30
            final_blow_info = await self.get_attacker_info(final_blow_attackers[0], total_damage)
            await self.paint_attackers(background, draw, atk_x, atk_y, final_blow_info)
            atk_y += ACHAR_SIZE + 10

        # 最高伤害攻击者信息
        if attackers:
            max_damage_attacker = max(attackers, key=lambda a: a.get('damage_done', 0))
            max_damage_line = f"最高伤害:"
            draw.text((atk_x, atk_y), max_damage_line, font=SUBTITLE_FONT, fill=GRAY)
            atk_y += 30
            max_damage_info = await self.get_attacker_info(max_damage_attacker, total_damage)
            await self.paint_attackers(background, draw, atk_x, atk_y, max_damage_info)
            atk_y += ACHAR_SIZE + 10
            
            # 分隔线
            draw.rectangle([0, atk_y, avatar_x + victim_size*2 + 10, atk_y + 2], fill=GRAY)
            atk_y += 15

            # 其他攻击者列表
            for a in sorted(attackers, key=lambda x: x.get('damage_done', 0), reverse=True):
                attacker_info = await self.get_attacker_info(a, total_damage)
                await self.paint_attackers(background, draw, atk_x, atk_y, attacker_info)
                if atk_y > bg_height - 200:
                    break
                else:
                    atk_y += ACHAR_SIZE + 10

        ############## Right Half
        info_x, info_y = avatar_x + victim_size*2 + 10, avatar_y
        draw.rectangle([info_x + 10, 0, img_width, img_height], fill=BLACK)
        
        # 受害者信息
        draw.text((info_x, info_y), f"{victim_name}", font=NAME_FONT, fill=WHITE)
        info_y += 30
        
        # 公司信息
        corp_image = images.get('corp_image')
        if corp_image:
            background.paste(corp_image, (info_x, info_y), corp_image)
        draw.text((info_x + 35, info_y), victim_corp, font=SUBTITLE_FONT, fill=GRAY)
        
        # 联盟信息
        if victim_alliance:
            info_y += 30
            draw.text((info_x + 35, info_y), victim_alliance, font=SUBTITLE_FONT, fill=GRAY)
            
            allia_image = images.get('allia_image')
            if allia_image:
                background.paste(allia_image, (info_x, info_y), allia_image)
        
        # 舰船信息
        info_y += 40
        draw.text((info_x, info_y), f"{victim_ship}", font=SHIP_FONT, fill=WHITE)
        
        # 星系信息
        info_y += 30
        status_color = self.get_security_color(security_status)
        system_length = draw.textlength(f"{system_name} ", font=TEXT_FONT)
        security_length = draw.textlength(f"({security_status:.1f})", font=TEXT_FONT)

        draw.text((info_x, info_y), f"{system_name} ", font=TEXT_FONT, fill=WHITE)
        draw.text((info_x + system_length, info_y), f"({security_status:.1f}) ", font=TEXT_FONT, fill=status_color)
        draw.text((info_x + system_length + security_length, info_y),
                f"< {constellation} " + f"< {region}" if region else "", font=SMALL_FONT, fill=WHITE)

        # 时间信息
        info_y += 20
        draw.text((info_x, info_y), f"{killmail_time}", font=TEXT_FONT, fill=GRAY)
        info_y += 25
        
        # 装备与明细
        fit_x, fit_y = info_x + 20, avatar_y + 180
        draw.text((fit_x, fit_y), "装备与明细", font=SUBTITLEY_FONT, fill=WHITE)
        fit_y += 30

        # 绘制装备信息
        slot_lines = []
        for slot_name in SLOT_ORDER:
            if slot_name in merged:
                slot_lines.append(slot_name + ":")
                draw.rectangle([fit_x - 2, fit_y, 680, fit_y + 24], fill=(37,39,41))
                draw.text((fit_x, fit_y), slot_name, font=SUBTITLEY_FONT, fill=WHITE)
                fit_y += 30

                slot_items = merged[slot_name]
                for itm in slot_items:
                    itm_name = itm.get('item_name', 'Unknown Item')
                    itm_id = itm.get('item_type_id', None)
                    sub_flag = itm.get('sub_flag', False)
                    qty_destroyed = itm.get('quantity_destroyed', 0)
                    qty_dropped = itm.get('quantity_dropped', 0)
                    qty = qty_destroyed if qty_destroyed > 0 else qty_dropped
                    if qty == 0:
                        qty = 1  # 默认数量为1

                    if sub_flag:
                        if qty_destroyed > 0:
                            await self.draw_item_with_icon(draw, background, fit_x, fit_y, itm_name, itm_id, qty_destroyed, 0, sub_flag)
                            if fit_y > bg_height - 200:
                                break
                            else:
                                fit_y += 25
                            slot_lines.append(f" - {itm_name} x{qty_destroyed} 摧毁")

                        if qty_dropped > 0:
                            await self.draw_item_with_icon(draw, background, fit_x, fit_y, itm_name, itm_id, 0, qty_dropped, sub_flag)
                            if fit_y > bg_height - 200:
                                break
                            else:
                                fit_y += 25
                            slot_lines.append(f" - {itm_name} x{qty_dropped} 掉落")
                    else:
                        if qty_destroyed > 0:
                            await self.draw_item_with_icon(draw, background, fit_x, fit_y, itm_name, itm_id, qty_destroyed, 0)
                            if fit_y > bg_height - 200:
                                break
                            else:
                                fit_y += 25
                            slot_lines.append(f" - {itm_name} x{qty_destroyed} 摧毁")

                        if qty_dropped > 0:
                            await self.draw_item_with_icon(draw, background, fit_x, fit_y, itm_name, itm_id, 0, qty_dropped)
                            if fit_y > bg_height - 200:
                                break
                            else:
                                fit_y += 25
                            slot_lines.append(f" - {itm_name} x{qty_dropped} 掉落")

                if fit_y > bg_height - 200:
                    break

        # 价值信息
        total_value = zkb_data.get('totalValue', 0)
        dropped_value = zkb_data.get('droppedValue', 0)
        destroyed_value = zkb_data.get('destroyedValue', 0)

        # 价值信息在右下角
        val_x, val_y = info_x + 150, bg_height - 100
        draw.text((val_x, val_y), f"总价值: {total_value:,.2f} ISK", font=SUBTITLE_FONT, fill=WHITE)
        val_y += 20
        draw.text((val_x, val_y), f"掉  落: {dropped_value:,.2f} ISK", font=SUBTITLE_FONT, fill=GREEN)
        val_y += 40
        draw.text((val_x, val_y), f"Kill #{killmail_id}", font=TEXT_FONT, fill=WHITE)

        # 上下分栏线
        draw.rectangle([avatar_x, avatar_y+victim_size+46, 680, avatar_y+victim_size+47], fill=GRAY)

        # 保存图像
        output_path = self.generate_unique_output_path(killmail_id)
        background.save(output_path, optimize=True)

        return output_path, system_name

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("接收到退出信号，程序关闭")
    except Exception as e:
        logger.critical(f"程序异常终止: {e}")
        logger.critical(traceback.format_exc())
