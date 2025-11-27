from flask import Flask, request, jsonify
import hashlib
import hmac
import base64
import time
import requests
import os
import random
import re
import json

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

def format_won(value):
    """금액을 읽기 쉽게 포맷"""
    if value >= 100000000:
        return f"{value / 100000000:.1f}억원"
    elif value >= 10000:
        return f"{value / 10000:.1f}만원"
    else:
        return f"{format_number(int(value))}원"


#############################################
# 네이버 검색광고 API
#############################################
def get_naver_api_headers(method="GET", uri="/keywordstool"):
    """검색광고 API 헤더 생성"""
    timestamp = str(int(time.time() * 1000))
    
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        NAVER_SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_base64 = base64.b64encode(signature).decode('utf-8')
    
    return {
        "Content-Type": "application/json; charset=UTF-8",
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
    
    headers = get_naver_api_headers("GET", uri)
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
# 기능 3: 광고 단가 조회 (순위별 입찰가 기반)
#############################################
def get_exposure_minimum_bid(keyword, device='PC'):
    """노출 최소 입찰가 조회 (참고용)"""
    try:
        uri = '/npc-estimate/exposure-minimum-bid/keyword'
        url = f'https://api.searchad.naver.com{uri}'
        
        headers = get_naver_api_headers('POST', uri)
        payload = {"device": device, "items": [keyword]}
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'estimate' in data:
                for est in data.get('estimate', []):
                    if est.get('keyword') == keyword:
                        return est.get('bid', 0)
        return 0
    except:
        return 0


def get_median_bid(keyword, device='PC'):
    """중간값 입찰가 조회 (경쟁자 평균, 참고용)"""
    try:
        uri = '/npc-estimate/median-bid/keyword'
        url = f'https://api.searchad.naver.com{uri}'
        
        headers = get_naver_api_headers('POST', uri)
        payload = {"device": device, "items": [keyword]}
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'estimate' in data:
                for est in data.get('estimate', []):
                    if est.get('keyword') == keyword:
                        return est.get('bid', 0)
        return 0
    except:
        return 0


def get_position_bids(keyword, device='PC'):
    """순위별 예상 입찰가 조회 (1~5위) - 실제 계산에 사용"""
    try:
        uri = '/npc-estimate/average-position-bid/keyword'
        url = f'https://api.searchad.naver.com{uri}'
        
        headers = get_naver_api_headers('POST', uri)
        
        # 1위, 2위, 3위, 5위 조회
        items = [{"keyword": keyword, "position": pos} for pos in [1, 2, 3, 5]]
        payload = {"device": device, "items": items}
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            position_bids = {}
            if 'estimate' in data:
                for est in data.get('estimate', []):
                    if est.get('keyword') == keyword:
                        pos = est.get('position')
                        bid = est.get('bid', 0)
                        if bid and bid > 0:
                            position_bids[pos] = bid
            return position_bids if position_bids else None
        return None
    except Exception as e:
        print(f"순위별 입찰가 오류: {e}")
        return None


def get_ad_cost(keyword):
    """광고 단가 정보 조회 (순위별 입찰가 × 클릭수 기반)"""
    
    # 1. 기본 키워드 정보 조회
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"❌ 조회 실패\n{result['error']}"
    
    kw = result["data"][0]
    keyword_name = kw.get('relKeyword', keyword)
    
    # 기본 데이터
    pc_click = int(float(kw.get("monthlyAvePcClkCnt", 0) or 0))
    mobile_click = int(float(kw.get("monthlyAveMobileClkCnt", 0) or 0))
    total_click = pc_click + mobile_click
    
    pc_qc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile_qc = parse_count(kw.get("monthlyMobileQcCnt"))
    total_qc = pc_qc + mobile_qc
    
    comp = kw.get("compIdx", "정보없음")
    ad_count = kw.get("plAvgDepth", 0) or 0
    
    # 경쟁도 이모지
    comp_emoji = {"높음": "🔴", "중간": "🟡"}.get(comp, "🟢")
    
    # 2. 순위별 입찰가 조회 (PC, 모바일 각각)
    pc_bids = get_position_bids(keyword_name, 'PC')
    mobile_bids = get_position_bids(keyword_name, 'MOBILE')
    
    # 참고용 데이터
    min_bid = get_exposure_minimum_bid(keyword_name, 'MOBILE')
    median_bid = get_median_bid(keyword_name, 'MOBILE')
    
    # API 성공 여부
    api_success = (pc_bids and len(pc_bids) > 0) or (mobile_bids and len(mobile_bids) > 0)
    
    # 3. 결과 포맷팅
    response = f"""💰 "{keyword_name}" 광고 분석

{comp_emoji} 경쟁도: {comp}
📊 월간 검색량: {format_number(total_qc)}회

━━━━━━━━━━━━━━━━
"""
    
    if api_success:
        # 순위별 입찰 단가 표시
        response += """
💵 순위별 입찰 단가 (네이버 API)

"""
        medal = {1: '🥇 1위', 2: '🥈 2위', 3: '🥉 3위', 5: '📍 5위'}
        
        if pc_bids:
            response += "💻 PC\n"
            for pos in sorted(pc_bids.keys()):
                response += f"├ {medal.get(pos, f'{pos}위')}: {format_number(pc_bids[pos])}원\n"
            response += "\n"
        
        if mobile_bids:
            response += "📱 모바일\n"
            for pos in sorted(mobile_bids.keys()):
                response += f"├ {medal.get(pos, f'{pos}위')}: {format_number(mobile_bids[pos])}원\n"
            response += "\n"
        
        # 월평균 클릭수
        response += f"""━━━━━━━━━━━━━━━━

📊 월 예상 광고비 (클릭 기반)

🖱️ 월평균 클릭수
├ 💻 PC: {format_number(pc_click)}회
└ 📱 모바일: {format_number(mobile_click)}회

"""
        
        # 목표 순위별 예상 비용 계산
        if total_click > 0:
            response += "💸 목표 순위별 예상 비용\n\n"
            
            # 사용할 입찰가 (모바일 우선, 없으면 PC)
            bids_to_use = mobile_bids if mobile_bids else pc_bids
            
            for pos in [1, 3, 5]:
                if pos not in bids_to_use:
                    continue
                    
                bid = bids_to_use[pos]
                pc_bid = pc_bids.get(pos, bid) if pc_bids else bid
                mo_bid = mobile_bids.get(pos, bid) if mobile_bids else bid
                
                pc_cost = pc_click * pc_bid
                mo_cost = mobile_click * mo_bid
                total_cost = pc_cost + mo_cost
                
                pos_emoji = {1: '🥇 1위', 3: '🥉 3위', 5: '📍 5위'}.get(pos, f'{pos}위')
                
                response += f"{pos_emoji} 노출 목표\n"
                if pc_click > 0:
                    response += f"├ 💻 PC: {format_number(pc_click)}회 × {format_number(pc_bid)}원 = {format_won(pc_cost)}\n"
                if mobile_click > 0:
                    response += f"├ 📱 모바일: {format_number(mobile_click)}회 × {format_number(mo_bid)}원 = {format_won(mo_cost)}\n"
                response += f"└ 💰 합계: {format_won(total_cost)}/월\n\n"
            
            # 3위 기준 일일 예산 추천
            if 3 in bids_to_use:
                bid_3 = bids_to_use[3]
                pc_bid_3 = pc_bids.get(3, bid_3) if pc_bids else bid_3
                mo_bid_3 = mobile_bids.get(3, bid_3) if mobile_bids else bid_3
                monthly_cost_3 = (pc_click * pc_bid_3) + (mobile_click * mo_bid_3)
                daily_budget = monthly_cost_3 / 30
                
                response += f"""━━━━━━━━━━━━━━━━

💡 3위 기준 추천 일일 예산
└ 약 {format_won(daily_budget)}"""
        else:
            response += "⚠️ 클릭 데이터가 부족하여 비용 예측 불가\n"
        
        # 참고 정보
        if min_bid > 0 or median_bid > 0:
            response += f"""

━━━━━━━━━━━━━━━━

📌 참고 정보"""
            if min_bid > 0:
                response += f"\n├ 노출 최소 입찰가: {format_number(min_bid)}원"
            if median_bid > 0:
                response += f"\n└ 경쟁자 평균 입찰가: {format_number(median_bid)}원"
    
    else:
        # API 실패시 추정값 사용
        response += """
⚠️ 입찰가 API 조회 실패 (추정값 표시)

"""
        if comp == "높음":
            est_min, est_max = 5000, 20000
        elif comp == "중간":
            est_min, est_max = 500, 5000
        else:
            est_min, est_max = 100, 1000
        
        response += f"""💵 예상 CPC (추정)
├ 최소: {format_number(est_min)}원
├ 평균: {format_number((est_min + est_max) // 2)}원
└ 최대: {format_number(est_max)}원

🖱️ 월평균 클릭수
├ 💻 PC: {format_number(pc_click)}회
└ 📱 모바일: {format_number(mobile_click)}회
"""
        
        if total_click > 0:
            avg_cpc = (est_min + est_max) // 2
            monthly_cost = total_click * avg_cpc
            response += f"""
💸 월 예상 광고비 (추정)
└ 약 {format_won(monthly_cost)}"""
    
    return response


#############################################
# 기능 4: 블로그 상위 5개 제목
#############################################
def get_blog_titles(keyword):
    """네이버 블로그 상위 5개 제목 가져오기"""
    
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return f"""📝 "{keyword}" 블로그 분석

⚠️ 블로그 검색 API가 설정되지 않았습니다."""
    
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
💡 TIP: 상위 제목 패턴을 분석해보세요!"""
                
                return result
            else:
                return f"❌ '{keyword}' 블로그 검색 결과가 없습니다."
        else:
            return f"❌ 블로그 검색 오류 ({response.status_code})"
            
    except Exception as e:
        return f"❌ 블로그 검색 실패: {str(e)}"


#############################################
# 기능 5: 오늘의 운세 (Gemini)
#############################################
def get_fortune():
    """Gemini로 오늘의 운세 생성"""
    
    if not GEMINI_API_KEY:
        return get_fortune_fallback()
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    prompt = """오늘의 운세를 재미있고 긍정적으로 알려줘.

다음 형식으로 작성해줘:

🔮 오늘의 운세

✨ 총운
(2줄 이내)

💕 애정운: (1줄)
💰 금전운: (1줄)
💼 직장/학업운: (1줄)

🍀 행운의 숫자: (1-45 사이 숫자 3개)
🎨 행운의 색: (색상 1개)

💬 오늘의 한마디
"(짧은 격언이나 응원 메시지)"

이모지를 적절히 사용해줘."""

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 500
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=15)
        
        if response.status_code == 200:
            result = response.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return text
        else:
            return get_fortune_fallback()
            
    except:
        return get_fortune_fallback()

def get_fortune_fallback():
    """기본 운세"""
    fortunes = ["오늘은 새로운 기회가 찾아오는 날!", "좋은 소식이 들려올 예정이에요.", "작은 행운이 당신을 따라다녀요."]
    love = ["설레는 만남이 있을 수 있어요 💕", "소중한 사람과 대화를 나눠보세요"]
    money = ["작은 횡재수가 있어요 💰", "절약이 미덕인 날"]
    work = ["집중력이 높아지는 시간 💼", "새 프로젝트에 도전해보세요"]
    
    lucky_numbers = random.sample(range(1, 46), 3)
    lucky_numbers.sort()
    colors = ["빨간색", "파란색", "노란색", "초록색", "보라색"]
    quotes = ["오늘 하루도 화이팅! 💪", "웃으면 복이 와요 😊", "당신은 할 수 있어요!"]
    
    return f"""🔮 오늘의 운세

✨ 총운
{random.choice(fortunes)}

💕 애정운: {random.choice(love)}
💰 금전운: {random.choice(money)}
💼 직장/학업운: {random.choice(work)}

🍀 행운의 숫자: {lucky_numbers[0]}, {lucky_numbers[1]}, {lucky_numbers[2]}
🎨 행운의 색: {random.choice(colors)}

━━━━━━━━━━━━━━━━
💬 "{random.choice(quotes)}"
"""


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
            
    except:
        return get_lotto_fallback()

def get_lotto_fallback():
    """기본 로또 번호 생성"""
    result = """🎰 이번 주 로또 번호 추천!

"""
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    
    for emoji in emojis:
        numbers = random.sample(range(1, 46), 6)
        numbers.sort()
        numbers_str = ", ".join(str(n).zfill(2) for n in numbers)
        result += f"{emoji} {numbers_str}\n"
    
    result += """
━━━━━━━━━━━━━━━━
🍀 행운을 빕니다!

⚠️ 로또는 재미로만 즐기세요!"""
    
    return result


#############################################
# 기능 7: 대표키워드 조회 (네이버 플레이스)
#############################################
def get_place_keywords(place_id):
    """네이버 플레이스 대표키워드 추출"""
    
    # 네이버 플레이스 GraphQL API 사용
    url = "https://pcmap-api.place.naver.com/graphql"
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": f"https://pcmap.place.naver.com/restaurant/{place_id}/home",
        "Origin": "https://pcmap.place.naver.com"
    }
    
    query = """
    query getRestaurant($input: RestaurantInput) {
        restaurant(input: $input) {
            keywords
        }
    }
    """
    
    payload = {
        "operationName": "getRestaurant",
        "query": query,
        "variables": {
            "input": {
                "id": place_id
            }
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            if "data" in data and "restaurant" in data["data"]:
                restaurant = data["data"]["restaurant"]
                if restaurant and "keywords" in restaurant:
                    keywords = restaurant["keywords"]
                    if keywords and len(keywords) > 0:
                        return {
                            "success": True,
                            "place_id": place_id,
                            "keywords": keywords
                        }
        
        return get_place_keywords_html(place_id)
            
    except:
        return get_place_keywords_html(place_id)


def get_place_keywords_html(place_id):
    """HTML 파싱 방식 (백업)"""
    
    url = f"https://m.place.naver.com/restaurant/{place_id}/home"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {
                "success": False,
                "error": f"페이지 조회 실패 (코드: {response.status_code})"
            }
        
        content = response.content
        
        try:
            html = content.decode('utf-8')
        except:
            html = content.decode('utf-8', errors='ignore')
        
        next_data_pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        next_match = re.search(next_data_pattern, html, re.DOTALL)
        
        if next_match:
            try:
                json_str = next_match.group(1)
                data = json.loads(json_str)
                keywords = find_keywords_in_json(data)
                
                if keywords:
                    return {
                        "success": True,
                        "place_id": place_id,
                        "keywords": keywords
                    }
            except:
                pass
        
        patterns = [
            r'"keywordList"\s*:\s*\[(.*?)\]',
            r'"keywords"\s*:\s*\[(.*?)\]',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, html, re.DOTALL)
            if match:
                try:
                    keywords_str = match.group(1)
                    keywords_json = f'[{keywords_str}]'
                    keywords = json.loads(keywords_json)
                    
                    if keywords:
                        return {
                            "success": True,
                            "place_id": place_id,
                            "keywords": keywords
                        }
                except:
                    continue
        
        return {
            "success": False,
            "error": "대표키워드를 찾을 수 없습니다.\n\n가능한 원인:\n• 잘못된 플레이스 ID\n• 음식점이 아닌 업종\n• 대표키워드 미등록 업체"
        }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"오류 발생: {str(e)}"
        }


def find_keywords_in_json(obj, depth=0):
    """JSON 객체에서 keywords 재귀적으로 찾기"""
    
    if depth > 20:
        return None
    
    if isinstance(obj, dict):
        if "keywordList" in obj and isinstance(obj["keywordList"], list):
            if len(obj["keywordList"]) > 0 and isinstance(obj["keywordList"][0], str):
                return obj["keywordList"]
        
        if "keywords" in obj and isinstance(obj["keywords"], list):
            if len(obj["keywords"]) > 0 and isinstance(obj["keywords"][0], str):
                return obj["keywords"]
        
        for key, value in obj.items():
            result = find_keywords_in_json(value, depth + 1)
            if result:
                return result
    
    elif isinstance(obj, list):
        for item in obj:
            result = find_keywords_in_json(item, depth + 1)
            if result:
                return result
    
    return None


def format_place_keywords(place_id):
    """대표키워드 결과 포맷팅"""
    
    result = get_place_keywords(place_id)
    
    if not result["success"]:
        return f"❌ 조회 실패\n\n{result['error']}"
    
    keywords = result["keywords"]
    
    response = f"""🏷️ 대표키워드 조회 결과

📍 플레이스 ID: {place_id}

━━━━━━━━━━━━━━━━
🔑 대표키워드 ({len(keywords)}개)
━━━━━━━━━━━━━━━━

"""
    
    for i, kw in enumerate(keywords, 1):
        response += f"{i}. {kw}\n"
    
    response += f"""
━━━━━━━━━━━━━━━━

📋 복사용
{', '.join(keywords)}

━━━━━━━━━━━━━━━━
💡 TIP: 각 키워드의 검색량도 확인해보세요!
예) {keywords[0]}"""
    
    return response


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
예) 맛집

🔗 연관 키워드
👉 "연관" + 키워드
예) 연관 맛집

💰 광고 단가 (CPC)
👉 "광고" + 키워드
예) 광고 맛집
※ 순위별 실제 입찰가!

📝 블로그 상위글
👉 "블로그" + 키워드
예) 블로그 맛집

🏷️ 대표키워드
👉 "대표" + 플레이스ID
예) 대표 37838432

━━━━━━━━━━━━━━━━
🎯 재미 기능
━━━━━━━━━━━━━━━━

🔮 오늘의 운세
👉 "운세" 입력

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
        
        lower_input = user_utterance.lower()
        
        # 도움말
        if lower_input in ["도움말", "도움", "사용법", "help", "?", "메뉴"]:
            response_text = get_help()
        
        # 운세
        elif lower_input in ["운세", "오늘의운세", "오늘운세", "오늘의 운세", "fortune"]:
            response_text = get_fortune()
        
        # 로또
        elif lower_input in ["로또", "로또번호", "로또 번호", "lotto", "번호추천", "번호 추천"]:
            response_text = get_lotto()
        
        # 대표키워드
        elif lower_input.startswith("대표 ") or lower_input.startswith("대표키워드 "):
            place_id = ''.join(filter(str.isdigit, user_utterance))
            if place_id:
                response_text = format_place_keywords(place_id)
            else:
                response_text = "❌ 플레이스 ID를 입력해주세요\n\n예) 대표 37838432\n\n💡 플레이스 ID 찾는 법:\n네이버 지도에서 업체 검색 → URL에서 숫자 확인"
        
        # 연관 키워드
        elif lower_input.startswith("연관 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_related_keywords(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예) 연관 맛집"
        
        # 광고 단가
        elif lower_input.startswith("광고 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_ad_cost(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예) 광고 맛집"
        
        # 블로그 상위글
        elif lower_input.startswith("블로그 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_blog_titles(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예) 블로그 맛집"
        
        # 기본: 검색량 조회
        else:
            response_text = get_search_volume(user_utterance)
        
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
