from flask import Flask, request, jsonify
import hashlib
import hmac
import base64
import time
import requests
import os
import random
from datetime import datetime

app = Flask(__name__)

# 검색광고 API 환경변수
NAVER_API_KEY = os.environ.get('NAVER_API_KEY', '')
NAVER_SECRET_KEY = os.environ.get('NAVER_SECRET_KEY', '')
NAVER_CUSTOMER_ID = os.environ.get('NAVER_CUSTOMER_ID', '')

# 검색 API 환경변수 (블로그용)
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')

# Gemini API 환경변수 (운세/로또용)
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')


#############################################
# 유틸리티 함수
#############################################
def format_number(num):
    if isinstance(num, int):
        return "{:,}".format(num)
    return str(num)

def parse_count(value):
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        if value == "< 10":
            return 5
        try:
            return int(str(value).replace(",", ""))
        except:
            return 0
    return 0


#############################################
# 네이버 검색광고 API
#############################################
def get_naver_api_headers():
    """검색광고 API 헤더 생성"""
    timestamp = str(int(time.time() * 1000))
    method = "GET"
    uri = "/keywordstool"
    
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        NAVER_SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_base64 = base64.b64encode(signature).decode('utf-8')
    
    return {
        "X-Timestamp": timestamp,
        "X-API-KEY": NAVER_API_KEY,
        "X-Customer": str(NAVER_CUSTOMER_ID),
        "X-Signature": signature_base64
    }

def get_keyword_data(keyword):
    """키워드 검색량 데이터 가져오기"""
    
    if not NAVER_API_KEY or not NAVER_SECRET_KEY or not NAVER_CUSTOMER_ID:
        return {"success": False, "error": "API 키가 설정되지 않았습니다."}
    
    base_url = "https://api.searchad.naver.com"
    uri = "/keywordstool"
    
    headers = get_naver_api_headers()
    params = {
        "hintKeywords": keyword,
        "showDetail": "1"
    }
    
    try:
        response = requests.get(base_url + uri, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            keyword_list = data.get("keywordList", [])
            
            if keyword_list:
                return {"success": True, "data": keyword_list}
            else:
                return {"success": False, "error": "검색 결과가 없습니다."}
        else:
            return {"success": False, "error": f"API 오류 ({response.status_code})"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}


#############################################
# 기능 1: 검색량 조회
#############################################
def get_search_volume(keyword):
    """키워드 검색량 조회"""
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"❌ 조회 실패\n{result['error']}"
    
    kw = result["data"][0]
    pc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile = parse_count(kw.get("monthlyMobileQcCnt"))
    total = pc + mobile
    comp = kw.get("compIdx", "정보없음")
    
    return f"""🔍 "{kw.get('relKeyword', keyword)}" 검색량

📊 월간 총: {format_number(total)}회
📱 모바일: {format_number(mobile)}회
💻 PC: {format_number(pc)}회
📈 경쟁도: {comp}

━━━━━━━━━━━━━━━━
💡 다른 명령어: "도움말" 입력"""


#############################################
# 기능 2: 연관 키워드 조회
#############################################
def get_related_keywords(keyword):
    """연관 키워드 5개 조회"""
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"❌ 조회 실패\n{result['error']}"
    
    keyword_list = result["data"][:6]
    
    response = f"""🔗 "{keyword}" 연관 키워드 TOP 5

"""
    
    for i, kw in enumerate(keyword_list[:5], 1):
        name = kw.get("relKeyword", "")
        pc = parse_count(kw.get("monthlyPcQcCnt"))
        mobile = parse_count(kw.get("monthlyMobileQcCnt"))
        total = pc + mobile
        comp = kw.get("compIdx", "")
        
        if comp == "높음":
            comp_emoji = "🔴"
        elif comp == "중간":
            comp_emoji = "🟡"
        else:
            comp_emoji = "🟢"
        
        response += f"{i}. {name}\n   📊 {format_number(total)}회 {comp_emoji}\n\n"
    
    return response


#############################################
# 기능 3: 광고 단가 조회 (실제 시장 기준)
#############################################
def get_ad_cost(keyword):
    """광고 단가 정보 조회"""
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"❌ 조회 실패\n{result['error']}"
    
    kw = result["data"][0]
    
    # 실제 API 데이터
    pc_click = float(kw.get("monthlyAvePcClkCnt", 0) or 0)
    mobile_click = float(kw.get("monthlyAveMobileClkCnt", 0) or 0)
    total_click = pc_click + mobile_click
    
    pc_ctr = kw.get("monthlyAvePcCtr", 0) or 0
    mobile_ctr = kw.get("monthlyAveMobileCtr", 0) or 0
    
    comp = kw.get("compIdx", "정보없음")
    ad_count = kw.get("plAvgDepth", 0) or 0
    
    # 검색량
    pc_qc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile_qc = parse_count(kw.get("monthlyMobileQcCnt"))
    total_qc = pc_qc + mobile_qc
    
    # 경쟁도별 기본 단가 설정 (실제 시장 기준)
    if comp == "높음":
        base_cpc_min = 5000
        base_cpc_max = 20000
        comp_emoji = "🔴"
        difficulty = "진입 어려움"
        tip = "💡 롱테일 키워드 공략 추천"
    elif comp == "중간":
        base_cpc_min = 500
        base_cpc_max = 5000
        comp_emoji = "🟡"
        difficulty = "보통"
        tip = "💡 틈새 키워드 발굴 추천"
    else:
        base_cpc_min = 100
        base_cpc_max = 1000
        comp_emoji = "🟢"
        difficulty = "진입 쉬움"
        tip = "💡 적극 공략 추천!"
    
    # 검색량에 따른 조정
    if total_qc > 500000:
        volume_multiplier = 1.5
    elif total_qc > 100000:
        volume_multiplier = 1.3
    elif total_qc > 50000:
        volume_multiplier = 1.2
    elif total_qc > 10000:
        volume_multiplier = 1.1
    else:
        volume_multiplier = 1.0
    
    # 광고수에 따른 조정
    if ad_count >= 15:
        ad_multiplier = 1.4
    elif ad_count >= 10:
        ad_multiplier = 1.2
    elif ad_count >= 5:
        ad_multiplier = 1.1
    else:
        ad_multiplier = 1.0
    
    # 최종 예상 CPC 계산
    estimated_cpc_min = int(base_cpc_min * volume_multiplier)
    estimated_cpc_max = int(base_cpc_max * volume_multiplier * ad_multiplier)
    
    # 범위 제한
    estimated_cpc_min = max(100, estimated_cpc_min)
    estimated_cpc_max = min(50000, estimated_cpc_max)
    
    # 월 예상 광고비 계산
    if total_click > 0:
        monthly_cost_min = int(total_click * estimated_cpc_min)
        monthly_cost_max = int(total_click * estimated_cpc_max)
        monthly_cost_str = format_cost_range(monthly_cost_min, monthly_cost_max)
    else:
        monthly_cost_str = "데이터 부족"
    
    return f"""💰 "{kw.get('relKeyword', keyword)}" 광고 분석

{comp_emoji} 경쟁도: {comp} ({difficulty})

💵 예상 클릭 단가 (CPC)
약 {format_number(estimated_cpc_min)}원 ~ {format_number(estimated_cpc_max)}원

💸 월 예상 광고비
{monthly_cost_str}

📊 광고 경쟁 현황
├ 평균 노출 광고수: {ad_count}개
└ 월평균 총 클릭: {format_number(int(total_click))}회

🖱️ 월평균 클릭수
├ 📱 모바일: {format_number(int(mobile_click))}회
└ 💻 PC: {format_number(int(pc_click))}회

📈 평균 클릭률 (CTR)
├ 📱 모바일: {mobile_ctr}%
└ 💻 PC: {pc_ctr}%

━━━━━━━━━━━━━━━━
{tip}

⚠️ 실제 단가는 입찰 경쟁에 따라 달라집니다."""


def format_cost_range(min_cost, max_cost):
    """광고비를 읽기 쉽게 포맷"""
    def format_won(value):
        if value >= 100000000:
            return f"{value / 100000000:.1f}억원"
        elif value >= 10000000:
            return f"{value / 10000:.0f}만원"
        elif value >= 1000000:
            return f"{value / 10000:.0f}만원"
        else:
            return f"{format_number(value)}원"
    
    return f"{format_won(min_cost)} ~ {format_won(max_cost)}"


#############################################
# 기능 4: 블로그 상위 5개 제목
#############################################
def get_blog_titles(keyword):
    """네이버 블로그 상위 5개 제목 가져오기"""
    
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return f"""📝 "{keyword}" 블로그 분석

⚠️ 블로그 검색 API가 설정되지 않았습니다.

연관 키워드 기반 주제를 추천해드릴게요!

""" + get_blog_topics_fallback(keyword)
    
    url = "https://openapi.naver.com/v1/search/blog.json"
    
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    
    params = {
        "query": keyword,
        "display": 5,
        "sort": "sim"
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            
            if items:
                result = f"""📝 "{keyword}" 블로그 상위 5개

🏆 현재 상위 노출 제목

"""
                for i, item in enumerate(items, 1):
                    title = item.get("title", "")
                    title = title.replace("<b>", "").replace("</b>", "")
                    blogger = item.get("bloggername", "")
                    
                    result += f"""{i}. {title}
   ✍️ {blogger}

"""
                
                result += """━━━━━━━━━━━━━━━━
💡 TIP: 상위 제목 패턴을 분석해보세요!
• 숫자 사용 (TOP 10, 5가지 등)
• 후기/리뷰 키워드
• 연도 표기 (2024, 2025)"""
                
                return result
            else:
                return f"❌ '{keyword}' 블로그 검색 결과가 없습니다."
        else:
            return f"❌ 블로그 검색 오류 ({response.status_code})"
            
    except Exception as e:
        return f"❌ 블로그 검색 실패: {str(e)}"

def get_blog_topics_fallback(keyword):
    """블로그 API 없을 때 연관 키워드 기반 추천"""
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return ""
    
    keyword_list = result["data"][:5]
    response = ""
    
    for i, kw in enumerate(keyword_list, 1):
        name = kw.get("relKeyword", "")
        total = parse_count(kw.get("monthlyPcQcCnt")) + parse_count(kw.get("monthlyMobileQcCnt"))
        response += f"{i}. {name} ({format_number(total)}회)\n"
    
    return response


#############################################
# 기능 5: 오늘의 운세 (Gemini) - 생년월일 기반
#############################################
def parse_birthday(birthday_str):
    """생년월일 파싱 (YYMMDD 또는 YYYYMMDD)"""
    birthday_str = birthday_str.strip().replace("-", "").replace(".", "").replace("/", "")
    
    if len(birthday_str) == 6:
        # YYMMDD 형식
        year = int(birthday_str[:2])
        month = int(birthday_str[2:4])
        day = int(birthday_str[4:6])
        
        # 년도 보정 (00~29는 2000년대, 30~99는 1900년대)
        if year <= 29:
            year += 2000
        else:
            year += 1900
            
    elif len(birthday_str) == 8:
        # YYYYMMDD 형식
        year = int(birthday_str[:4])
        month = int(birthday_str[4:6])
        day = int(birthday_str[6:8])
    else:
        return None
    
    # 유효성 검사
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return None
    if year < 1920 or year > 2020:
        return None
        
    return {"year": year, "month": month, "day": day}


def get_zodiac_sign(month, day):
    """별자리 계산"""
    zodiac = [
        (1, 20, "염소자리", "♑"), (2, 19, "물병자리", "♒"), (3, 20, "물고기자리", "♓"),
        (4, 20, "양자리", "♈"), (5, 21, "황소자리", "♉"), (6, 21, "쌍둥이자리", "♊"),
        (7, 22, "게자리", "♋"), (8, 23, "사자자리", "♌"), (9, 23, "처녀자리", "♍"),
        (10, 23, "천칭자리", "♎"), (11, 22, "전갈자리", "♏"), (12, 22, "사수자리", "♐"),
        (12, 31, "염소자리", "♑")
    ]
    
    for end_month, end_day, sign, symbol in zodiac:
        if (month < end_month) or (month == end_month and day <= end_day):
            return sign, symbol
    
    return "염소자리", "♑"


def get_chinese_zodiac(year):
    """띠 계산"""
    zodiacs = [
        ("원숭이", "🐵"), ("닭", "🐔"), ("개", "🐶"), ("돼지", "🐷"),
        ("쥐", "🐭"), ("소", "🐮"), ("호랑이", "🐯"), ("토끼", "🐰"),
        ("용", "🐲"), ("뱀", "🐍"), ("말", "🐴"), ("양", "🐑")
    ]
    return zodiacs[year % 12]


def calculate_age(year):
    """나이 계산 (한국 나이)"""
    current_year = datetime.now().year
    return current_year - year + 1


def get_fortune(birthday_str=None):
    """생년월일 기반 오늘의 운세 생성"""
    
    # 생년월일 파싱
    if birthday_str:
        birthday = parse_birthday(birthday_str)
        if not birthday:
            return """❌ 생년월일 형식이 올바르지 않습니다.

📝 올바른 형식:
• 운세 860214 (YYMMDD)
• 운세 19860214 (YYYYMMDD)

예) 운세 901225"""
    else:
        birthday = None
    
    # 생년월일 정보 구성
    if birthday:
        zodiac_sign, zodiac_symbol = get_zodiac_sign(birthday["month"], birthday["day"])
        chinese_zodiac, chinese_emoji = get_chinese_zodiac(birthday["year"])
        age = calculate_age(birthday["year"])
        today = datetime.now().strftime("%Y년 %m월 %d일")
        
        birth_info = f"""생년월일: {birthday["year"]}년 {birthday["month"]}월 {birthday["day"]}일
나이: {age}세
별자리: {zodiac_symbol} {zodiac_sign}
띠: {chinese_emoji} {chinese_zodiac}띠
오늘 날짜: {today}"""
    else:
        birth_info = None
        zodiac_sign = None
        zodiac_symbol = None
        chinese_zodiac = None
        chinese_emoji = None
    
    if not GEMINI_API_KEY:
        return get_fortune_fallback(birthday)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    if birthday:
        prompt = f"""다음 사람의 오늘 운세를 자세하고 구체적으로 알려줘.

{birth_info}

이 사람의 별자리({zodiac_sign})와 띠({chinese_zodiac}띠)의 특성을 고려해서,
오늘 날짜의 운세를 구체적이고 개인화된 느낌으로 작성해줘.

다음 형식으로 작성해줘:

🔮 {birthday["year"]}년 {birthday["month"]}월 {birthday["day"]}일생 오늘의 운세

{zodiac_symbol} {zodiac_sign} | {chinese_emoji} {chinese_zodiac}띠

✨ 총운 (상/중/하 중 택1)
(3줄 이내, 구체적인 조언 포함)

💕 애정운
(2줄 이내, 구체적)

💰 금전운
(2줄 이내, 구체적)

💼 직장/학업운
(2줄 이내, 구체적)

⚠️ 오늘 주의할 점
(1줄)

🍀 행운의 숫자: (1-45 사이 숫자 3개, 생년월일과 연관지어)
🎨 행운의 색: (색상 1개)
⏰ 행운의 시간: (시간대)

💬 오늘의 조언
"(별자리/띠 특성에 맞는 맞춤 조언)"

이모지를 적절히 사용하고, 긍정적이면서도 현실적인 조언을 해줘."""

    else:
        prompt = """오늘의 운세를 재미있고 긍정적으로 알려줘.

다음 형식으로 작성해줘:

🔮 오늘의 운세

✨ 총운
(2줄 이내)

💕 애정운
(1줄)

💰 금전운
(1줄)

💼 직장/학업운
(1줄)

🍀 행운의 숫자: (1-45 사이 숫자 3개)
🎨 행운의 색: (색상 1개)

💬 오늘의 한마디
"(짧은 격언이나 응원 메시지)"

━━━━━━━━━━━━━━━━
💡 TIP: "운세 생년월일" 입력시 맞춤 운세!
예) 운세 860214

이모지를 적절히 사용하고, 전체 15줄 이내로 작성해줘."""

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 800
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return text
        else:
            return get_fortune_fallback(birthday)
            
    except Exception as e:
        return get_fortune_fallback(birthday)


def get_fortune_fallback(birthday=None):
    """Gemini 없을 때 기본 운세"""
    
    today = datetime.now()
    
    if birthday:
        zodiac_sign, zodiac_symbol = get_zodiac_sign(birthday["month"], birthday["day"])
        chinese_zodiac, chinese_emoji = get_chinese_zodiac(birthday["year"])
        age = calculate_age(birthday["year"])
        
        # 생년월일 + 오늘 날짜 기반 시드 (같은 날 같은 생일은 같은 운세)
        seed = birthday["year"] * 10000 + birthday["month"] * 100 + birthday["day"]
        seed += today.year * 10000 + today.month * 100 + today.day
        random.seed(seed)
        
        header = f"""🔮 {birthday["year"]}년 {birthday["month"]}월 {birthday["day"]}일생
   오늘의 운세

{zodiac_symbol} {zodiac_sign} | {chinese_emoji} {chinese_zodiac}띠 | {age}세

"""
    else:
        random.seed()
        header = """🔮 오늘의 운세

"""
    
    # 운세 등급
    grades = ["상", "중상", "중", "중하"]
    grade = random.choice(grades)
    
    fortunes = [
        "오늘은 새로운 기회가 찾아오는 날입니다.",
        "좋은 소식이 들려올 예정이에요.",
        "작은 행운이 당신을 따라다닐 거예요.",
        "긍정적인 에너지가 가득한 하루!",
        "뜻밖의 만남이 행운을 가져다줄 수 있어요.",
        "차분하게 하루를 보내면 좋은 결과가 있을 거예요.",
        "적극적으로 행동하면 원하는 것을 얻을 수 있어요."
    ]
    
    love = [
        "설레는 만남이 있을 수 있어요 💕", 
        "소중한 사람과 대화를 나눠보세요", 
        "사랑이 피어나는 하루",
        "상대방의 마음을 이해하는 시간을 가져보세요",
        "진심을 표현하면 좋은 반응이 있을 거예요"
    ]
    
    money = [
        "작은 횡재수가 있어요 💰", 
        "절약이 미덕인 날", 
        "투자보다는 저축을 추천",
        "예상치 못한 수입이 생길 수 있어요",
        "충동구매는 자제하세요"
    ]
    
    work = [
        "집중력이 높아지는 시간 💼", 
        "새 프로젝트에 도전해보세요", 
        "동료와의 협업이 좋아요",
        "꾸준한 노력이 빛을 발하는 날",
        "중요한 결정은 오후에 하세요"
    ]
    
    # 생년월일 기반 행운의 숫자
    if birthday:
        base_nums = [birthday["day"], birthday["month"], (birthday["year"] % 45) + 1]
        lucky_numbers = []
        for n in base_nums:
            adjusted = ((n + today.day) % 45) + 1
            while adjusted in lucky_numbers:
                adjusted = (adjusted % 45) + 1
            lucky_numbers.append(adjusted)
        lucky_numbers.sort()
    else:
        lucky_numbers = random.sample(range(1, 46), 3)
        lucky_numbers.sort()
    
    colors = ["빨간색", "파란색", "노란색", "초록색", "보라색", "주황색", "분홍색", "하늘색", "금색"]
    times = ["오전 9-11시", "오후 12-2시", "오후 3-5시", "저녁 6-8시"]
    
    quotes = [
        "오늘 하루도 화이팅! 💪",
        "웃으면 복이 와요 😊",
        "당신은 할 수 있어요!",
        "좋은 일이 생길 거예요 ✨",
        "포기하지 마세요, 거의 다 왔어요!",
        "작은 것에 감사하는 하루 되세요",
        "당신의 노력은 빛날 거예요"
    ]
    
    result = header + f"""✨ 총운: {grade}
{random.choice(fortunes)}

💕 애정운: {random.choice(love)}
💰 금전운: {random.choice(money)}
💼 직장/학업운: {random.choice(work)}

🍀 행운의 숫자: {lucky_numbers[0]}, {lucky_numbers[1]}, {lucky_numbers[2]}
🎨 행운의 색: {random.choice(colors)}
⏰ 행운의 시간: {random.choice(times)}

━━━━━━━━━━━━━━━━
💬 "{random.choice(quotes)}"
"""
    
    if not birthday:
        result += """
💡 TIP: "운세 생년월일" 입력시 맞춤 운세!
예) 운세 860214"""
    
    return result


#############################################
# 기능 6: 로또 번호 추천 (Gemini)
#############################################
def get_lotto():
    """Gemini로 로또 번호 추천"""
    
    if not GEMINI_API_KEY:
        return get_lotto_fallback()
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    prompt = """로또 번호 5세트를 추천해줘.

규칙:
- 1~45 사이 숫자만 사용
- 각 세트는 6개 번호 (중복 없이)
- 번호는 오름차순으로 정렬

다음 형식으로 작성:

🎰 이번 주 로또 번호 추천!

1️⃣ ○○, ○○, ○○, ○○, ○○, ○○
2️⃣ ○○, ○○, ○○, ○○, ○○, ○○
3️⃣ ○○, ○○, ○○, ○○, ○○, ○○
4️⃣ ○○, ○○, ○○, ○○, ○○, ○○
5️⃣ ○○, ○○, ○○, ○○, ○○, ○○

━━━━━━━━━━━━━━━━
🍀 행운을 빕니다!
(재미있는 응원 한마디)

⚠️ 로또는 재미로만 즐겨주세요!"""

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 400
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return text
        else:
            return get_lotto_fallback()
            
    except Exception as e:
        return get_lotto_fallback()


def get_lotto_fallback():
    """Gemini 없을 때 기본 로또 번호 생성"""
    
    result = """🎰 이번 주 로또 번호 추천!

"""
    
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    
    for i, emoji in enumerate(emojis):
        numbers = random.sample(range(1, 46), 6)
        numbers.sort()
        numbers_str = ", ".join(str(n).zfill(2) for n in numbers)
        result += f"{emoji} {numbers_str}\n"
    
    messages = [
        "이번 주는 당신 차례!",
        "대박을 기원합니다!",
        "당첨되시면 저도 생각해주세요 😄",
        "행운이 따르길!",
        "부자 되세요!"
    ]
    
    result += f"""
━━━━━━━━━━━━━━━━
🍀 {random.choice(messages)}

⚠️ 로또는 재미로만 즐겨주세요!"""
    
    return result


#############################################
# 도움말
#############################################
def get_help():
    return """📖 사용 설명서

━━━━━━━━━━━━━━━━
📊 키워드 분석
━━━━━━━━━━━━━━━━

🔍 검색량 조회
👉 키워드만 입력
예) 인천맛집

🔗 연관 키워드
👉 "연관" + 키워드
예) 연관 인천맛집

💰 광고 단가
👉 "광고" + 키워드
예) 광고 인천맛집

📝 블로그 상위글
👉 "블로그" + 키워드
예) 블로그 인천맛집

━━━━━━━━━━━━━━━━
🎯 재미 기능
━━━━━━━━━━━━━━━━

🔮 오늘의 운세
👉 "운세" (일반 운세)
👉 "운세 860214" (맞춤 운세)
   생년월일 6자리로 맞춤 운세!

🎰 로또 번호 추천
👉 "로또" 입력

━━━━━━━━━━━━━━━━
💬 원하는 기능을 이용해보세요!"""


#############################################
# 라우트: 홈
#############################################
@app.route('/')
def home():
    return "✅ 서버 정상 작동 중!"


#############################################
# 라우트: 테스트
#############################################
@app.route('/test')
def test():
    keyword = request.args.get('keyword', '맛집')
    result = get_keyword_data(keyword)
    
    if result["success"]:
        kw = result["data"][0]
        pc = parse_count(kw.get("monthlyPcQcCnt"))
        mobile = parse_count(kw.get("monthlyMobileQcCnt"))
        return f"""
        <h2>🔍 "{kw.get('relKeyword', keyword)}" 검색량</h2>
        <p>📊 월간 총: {format_number(pc + mobile)}회</p>
        <p>📱 모바일: {format_number(mobile)}회</p>
        <p>💻 PC: {format_number(pc)}회</p>
        """
    else:
        return f"<h2>❌ 조회 실패</h2><p>{result['error']}</p>"


#############################################
# 라우트: 카카오 스킬
#############################################
@app.route('/skill', methods=['POST'])
def kakao_skill():
    try:
        request_data = request.get_json()
        
        if request_data is None:
            return create_kakao_response("요청 데이터를 받지 못했습니다.")
        
        user_utterance = ""
        if "userRequest" in request_data:
            user_utterance = request_data["userRequest"].get("utterance", "").strip()
        
        if not user_utterance:
            return create_kakao_response("🔍 검색할 키워드를 입력해주세요!")
        
        # 명령어 처리
        lower_input = user_utterance.lower()
        
        # 도움말
        if lower_input in ["도움말", "도움", "사용법", "help", "?", "메뉴"]:
            response_text = get_help()
        
        # 운세 (생년월일 포함 가능)
        elif lower_input.startswith("운세"):
            parts = user_utterance.split()
            if len(parts) >= 2:
                # "운세 860214" 형태
                birthday_str = parts[1]
                response_text = get_fortune(birthday_str)
            else:
                # "운세"만 입력
                response_text = get_fortune()
        
        elif lower_input in ["오늘의운세", "오늘운세", "오늘의 운세", "fortune"]:
            response_text = get_fortune()
        
        # 로또
        elif lower_input in ["로또", "로또번호", "로또 번호", "lotto", "번호추천", "번호 추천"]:
            response_text = get_lotto()
        
        # 연관 키워드
        elif lower_input.startswith("연관 ") or lower_input.startswith("연관키워드 "):
            parts = user_utterance.split(" ", 1)
            keyword = parts[1] if len(parts) > 1 else ""
            if keyword:
                keyword = keyword.replace(" ", "")
                response_text = get_related_keywords(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예) 연관 맛집"
        
        # 광고 단가
        elif lower_input.startswith("광고 ") or lower_input.startswith("광고단가 "):
            parts = user_utterance.split(" ", 1)
            keyword = parts[1] if len(parts) > 1 else ""
            if keyword:
                keyword = keyword.replace(" ", "")
                response_text = get_ad_cost(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예) 광고 맛집"
        
        # 블로그 상위글
        elif lower_input.startswith("블로그 "):
            parts = user_utterance.split(" ", 1)
            keyword = parts[1] if len(parts) > 1 else ""
            if keyword:
                keyword = keyword.replace(" ", "")
                response_text = get_blog_titles(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예) 블로그 맛집"
        
        # 기본: 검색량 조회
        else:
            keyword = user_utterance.replace(" ", "")
            response_text = get_search_volume(keyword)
        
        return create_kakao_response(response_text)
        
    except Exception as e:
        return create_kakao_response(f"서버 오류: {str(e)}")


#############################################
# 카카오 응답 생성
#############################################
def create_kakao_response(text):
    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}]
        }
    })


#############################################
# 서버 실행
#############################################
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
