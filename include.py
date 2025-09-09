from PIL import ImageFont, Image
import os

# 1. zKillboard RedisQ 队列ID
#    请访问 https://zkillboard.com/api/redisq/ 并登录，获取你自己的 personal queueID
QUEUE_ID = "12344321"  # <--- 在这里填入你的 QUEUE_ID

# 2. ESI 请求的用户代理 (User-Agent)
#    建议填入你的联系方式，例如GitHub项目地址或邮箱，方便EVE官方联系
USER_AGENT = "QQ-EveBot (Contact: your-email@example.com)" # <--- 在这里填入你的联系方式

# 3. 重点监控的角色ID列表
#    在这里添加你想特别关注的角色ID，可以是你的盟友、VIP或敌人
VIP_User=95988132   #Here to use character ID from ESI

vips = [
    VIP_User
]

# 4. 击杀价值阈值 (ISK)
#    只有当击杀报告的总价值超过这个数值时，程序才会生成图片（除非涉及VIP或官员）
ISK_THRESHOLD = 1000000000  # 当前设置为 1b ISK (10亿)

# ==============================================================================
#                            路径与样式配置 (通常无需修改)
# ==============================================================================

# 1. 字体文件路径 (需要保证 "fonts" 文件夹和字体文件存在)

BOLD_PATH = "fonts/OPPOSans-Bold.ttf"
MEDIUM_PATH = "fonts/OPPOSans-Medium.ttf"
TEXT_PATH = "fonts/OPPOSans-Regular.ttf"
YAHEI_PATH = "fonts/yahei.ttf"
NAME_FONT = ImageFont.truetype(BOLD_PATH, 20)
SHIP_FONT = ImageFont.truetype(MEDIUM_PATH, 20)
TEXT_FONT = ImageFont.truetype(MEDIUM_PATH, 16)
SMALL_FONT = ImageFont.truetype(MEDIUM_PATH, 14)
ICON_FONT = ImageFont.truetype(TEXT_PATH, 14)
ICONY_FONT = ImageFont.truetype(YAHEI_PATH, 16)
SUBTITLE_FONT = ImageFont.truetype(MEDIUM_PATH, 18)
SUBTITLEY_FONT = ImageFont.truetype(YAHEI_PATH, 18)

# 2. EVE SDE 静态数据路径 (需要保证 "sde" 文件夹和数据存在)
SDE_DIR = "sde"
SDE_ICONS_DIR = os.path.join(SDE_DIR, 'Types') # 图标缓存目录

WHITE = (255,255,255)
GREEN = (34,139,34)
RED = (220, 4, 4)
NULL_SEC = (153, 53, 108)
GRAY = (135, 135, 135)
YELLOW = (255,255,0)
BLACK = (25,25,25)
GRAY_L = (37,39,41)
DGREEN = (23,51,27)
SEC_COLOR = [(145,46,107), (107,33,39), (188,18,18), (208,69,14), (222,107,11), (238,255,134), (113,228,82), (97,218,166), (75,206,240), (56,156,243), (46,116,219)]

##Officer GroupID:
BloodRaidersOfficer =559
BloodRaidersOfficerCruiser=4797
BloodRaidersOfficerFrigate=4798
SerpentisOfficer    =574
SerpentisOfficerCruiser=4803
SerpentisOfficerFrigate=4804
AngelCartelOfficer  =553
AngelCartelOfficerCruiser=4795
AngelCartelOfficerFrigate=4796
GuristasOfficer =564
GuristasOfficerCruiser =4799
GuristasOfficerFrigate =4800
SanshaOfficer =569
SanshaOfficerCruiser =4801
SanshaOfficerFrigate =4802


# Officers group ids
officer_group_ids = [
    BloodRaidersOfficer,
    BloodRaidersOfficerCruiser,
    BloodRaidersOfficerFrigate,
    SerpentisOfficer,
    SerpentisOfficerCruiser,
    SerpentisOfficerFrigate,
    AngelCartelOfficer,
    AngelCartelOfficerCruiser,
    AngelCartelOfficerFrigate,
    GuristasOfficer,
    GuristasOfficerCruiser,
    GuristasOfficerFrigate,
    SanshaOfficer,
    SanshaOfficerCruiser,
    SanshaOfficerFrigate
]



# 加载本地图标图片
def load_local_icon(item_type_id, icon_size=32, icon_dir='sde/Types'):
    # 构造本地文件路径
    icon_filename = f"{item_type_id}_{icon_size}.png"
    icon_path = os.path.join(icon_dir, icon_filename)

    # 检查文件是否存在
    if os.path.exists(icon_path):
        try:
            # 加载图标图片
            icon_img = Image.open(icon_path)
            return icon_img
        except Exception as e:
            print(f"Error loading image {icon_path}: {e}")
            return None
    else:
        print(f"Icon file {icon_path} not found.")
        return None
