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
# CPC API 함수들
#############################################
def get_exposure_minimum_bid(keyword, device='PC'):
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


def get_performance_estimate(keyword, bids, device='MOBILE'):
    """입찰가별 예상 실적 조회"""
    try:
        uri = '/estimate/performance/keyword'
        url = f'https://api.searchad.naver.com{uri}'
        headers = get_naver_api_headers('POST', uri)
        
        payload = {
            "device": device,
            "keywordplus": False,
            "key": keyword,
            "bids": bids if isinstance(bids, list) else [bids]
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        return {"success": False, "status": response.status_code, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_optimal_bid_info(estimates):
    """입찰가 효율 분석 - 최적 구간 찾기"""
    if not estimates:
        return None
    
    best_value = None
    min_exposure = None
    
    for est in estimates:
        bid = est.get("bid", 0)
        clicks = est.get("clicks", 0)
        impressions = est.get("impressions", 0)
        cost = est.get("cost", 0)
        
        if clicks == 0:
            continue
        
        # 노출 시작 구간
        if min_exposure is None and impressions > 0:
            min_exposure = est
        
        # 가성비 계산 (클릭당 비용 대비 노출수)
        actual_cpc = cost / clicks if clicks > 0 else bid
        value_score = impressions / actual_cpc if actual_cpc > 0 else 0
        
        if best_value is None or value_score > best_value.get('score', 0):
            best_value = {
                'bid': bid,
                'clicks': clicks,
                'impressions': impressions,
                'cost': cost,
                'cpc': actual_cpc,
                'score': value_score
            }
    
    return {
        'min_exposure': min_exposure,
        'best_value': best_value,
        'max_performance': estimates[-1] if estimates else None
    }


#############################################
# 기능 1: 검색량 조회
#############################################
def get_search_volume(keyword):
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
# 기능 3: 광고 단가 조회 (대폭 개선)
#############################################
def get_ad_cost(keyword):
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"❌ 조회 실패\n{result['error']}"
    
    kw = result["data"][0]
    keyword_name = kw.get('relKeyword', keyword)
    
    # 키워드 도구 데이터
    pc_click = int(float(kw.get("monthlyAvePcClkCnt", 0) or 0))
    mobile_click = int(float(kw.get("monthlyAveMobileClkCnt", 0) or 0))
    total_click = pc_click + mobile_click
    
    pc_qc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile_qc = parse_count(kw.get("monthlyMobileQcCnt"))
    total_qc = pc_qc + mobile_qc
    
    comp = kw.get("compIdx", "정보없음")
    comp_emoji = {"높음": "🔴", "중간": "🟡"}.get(comp, "🟢")
    
    # 헤더
    response = f"""💰 "{keyword_name}" 광고 완전 분석

{'='*32}
📊 기본 정보
{'='*32}

{comp_emoji} 경쟁도: {comp}
📱 월간 검색: {format_number(total_qc)}회
   ├ 모바일: {format_number(mobile_qc)}회 ({mobile_qc*100//total_qc if total_qc > 0 else 0}%)
   └ PC: {format_number(pc_qc)}회 ({pc_qc*100//total_qc if total_qc > 0 else 0}%)

"""
    
    # 노출 최소 입찰가
    pc_min_bid = get_exposure_minimum_bid(keyword_name, 'PC')
    mobile_min_bid = get_exposure_minimum_bid(keyword_name, 'MOBILE')
    
    response += f"""{'='*32}
💵 노출 최소 입찰가
{'='*32}

📱 모바일: {format_number(mobile_min_bid)}원
💻 PC: {format_number(pc_min_bid)}원

"""
    
    # Performance API 분석 (모바일)
    test_bids = [100, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 7000, 10000]
    mobile_perf = get_performance_estimate(keyword_name, test_bids, 'MOBILE')
    pc_perf = get_performance_estimate(keyword_name, test_bids, 'PC')
    
    mobile_success = mobile_perf.get("success", False)
    pc_success = pc_perf.get("success", False)
    
    if mobile_success:
        mobile_estimates = mobile_perf["data"].get("estimate", [])
        mobile_optimal = get_optimal_bid_info(mobile_estimates)
        
        response += f"""{'='*32}
📱 모바일 광고 상세 분석
{'='*32}

"""
        
        # 주요 입찰가만 표시 (0원 제외)
        display_estimates = [e for e in mobile_estimates if e.get('clicks', 0) > 0]
        
        if display_estimates:
            response += "📊 입찰가별 예상 성과\n\n"
            
            for est in display_estimates[:6]:  # 최대 6개만
                bid = est.get("bid", 0)
                clicks = est.get("clicks", 0)
                impressions = est.get("impressions", 0)
                cost = est.get("cost", 0)
                actual_cpc = int(cost / clicks) if clicks > 0 else bid
                
                response += f"""💵 {format_number(bid)}원
   노출 {format_number(impressions)}회 → 클릭 {clicks}회
   실제CPC {format_number(actual_cpc)}원 | 월비용 {format_won(cost)}

"""
            
            # 최적 입찰가 추천
            if mobile_optimal and mobile_optimal.get('best_value'):
                best = mobile_optimal['best_value']
                min_exp = mobile_optimal.get('min_exposure')
                max_perf = mobile_optimal.get('max_performance')
                
                response += f"""{'='*32}
🎯 입찰가 추천 (모바일)
{'='*32}

"""
                
                # 최소 노출 시작
                if min_exp:
                    min_bid = min_exp.get('bid', 0)
                    response += f"""🟢 최소 노출: {format_number(min_bid)}원
   └ 광고 노출 시작 구간

"""
                
                # 가성비 최고
                response += f"""🟡 추천 입찰가: {format_number(best['bid'])}원 ⭐
   ├ 월 클릭: 약 {best['clicks']}회
   ├ 실제 CPC: {format_number(int(best['cpc']))}원
   └ 월 예산: {format_won(best['cost'])}
   
   💡 가성비가 가장 좋은 구간!

"""
                
                # 최대 성과
                if max_perf:
                    max_bid = max_perf.get('bid', 0)
                    max_clicks = max_perf.get('clicks', 0)
                    max_cost = max_perf.get('cost', 0)
                    max_cpc = int(max_cost / max_clicks) if max_clicks > 0 else max_bid
                    
                    response += f"""🔴 최대 노출: {format_number(max_bid)}원
   ├ 월 클릭: 약 {max_clicks}회
   ├ 실제 CPC: {format_number(max_cpc)}원
   └ 월 예산: {format_won(max_cost)}
   
   ⚠️ 이상 올려도 효과 동일

"""
    
    # PC 분석
    if pc_success:
        pc_estimates = pc_perf["data"].get("estimate", [])
        pc_optimal = get_optimal_bid_info(pc_estimates)
        
        display_pc = [e for e in pc_estimates if e.get('clicks', 0) > 0]
        
        if display_pc and pc_optimal and pc_optimal.get('best_value'):
            best_pc = pc_optimal['best_value']
            
            response += f"""{'='*32}
💻 PC 광고 요약
{'='*32}

🎯 추천 입찰가: {format_number(best_pc['bid'])}원
├ 월 클릭: 약 {best_pc['clicks']}회
├ 실제 CPC: {format_number(int(best_pc['cpc']))}원
└ 월 예산: {format_won(best_pc['cost'])}

"""
    
    # 키워드 도구 클릭수와 비교
    if total_click > 0:
        api_clicks = 0
        if mobile_success and mobile_optimal and mobile_optimal.get('max_performance'):
            api_clicks = mobile_optimal['max_performance'].get('clicks', 0)
        
        diff_percent = ((total_click - api_clicks) / total_click * 100) if api_clicks > 0 else 0
        
        response += f"""{'='*32}
📈 실제 vs API 예측 비교
{'='*32}

📊 키워드도구 월평균 클릭: {format_number(total_click)}회
🔮 Performance API 예측: {format_number(api_clicks)}회

"""
        
        if api_clicks < total_click * 0.5:
            response += f"""⚠️ API 예측이 {abs(int(diff_percent))}% 낮음
💡 실제 클릭수는 더 많을 수 있음!

"""
        elif api_clicks > total_click * 1.5:
            response += f"""⚠️ API 예측이 {int(diff_percent)}% 높음
💡 실제 클릭수는 더 적을 수 있음!

"""
        else:
            response += "✅ API 예측이 평균과 유사함\n\n"
    
    # 실전 운영 가이드
    if mobile_success and mobile_optimal and mobile_optimal.get('best_value'):
        best = mobile_optimal['best_value']
        daily_budget = best['cost'] / 30
        weekly_budget = best['cost'] / 4
        
        response += f"""{'='*32}
💼 실전 운영 가이드
{'='*32}

📅 추천 예산 (가성비 기준)
├ 일 예산: {format_won(daily_budget)}
├ 주 예산: {format_won(weekly_budget)}
└ 월 예산: {format_won(best['cost'])}

🎯 시작 전략
1️⃣ 입찰가: {format_number(best['bid'])}원으로 시작
2️⃣ 일예산: {format_won(daily_budget * 1.2)} 설정
3️⃣ 3일 후 성과 확인
4️⃣ CTR 2% 이상이면 입찰가 상향

⚠️ 주의사항
• 경쟁 상황에 따라 실제 비용 변동
• 광고 품질에 따라 CPC 달라짐
• 최소 1주일 테스트 후 최적화

"""
    
    response += f"""{'='*32}
✨ 분석 완료
{'='*32}"""
    
    return response


#############################################
# 기능 4: 블로그 상위 5개 제목
#############################################
def get_blog_titles(keyword):
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
# 기능 7: 대표키워드 조회
#############################################
def get_place_keywords(place_id):
    url = "https://pcmap-api.place.naver.com/graphql"
    
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
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
        "variables": {"input": {"id": place_id}}
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
                        return {"success": True, "place_id": place_id, "keywords": keywords}
        
        return get_place_keywords_html(place_id)
            
    except:
        return get_place_keywords_html(place_id)


def get_place_keywords_html(place_id):
    url = f"https://m.place.naver.com/restaurant/{place_id}/home"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "ko-KR,ko;q=0.9",
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {"success": False, "error": f"페이지 조회 실패 (코드: {response.status_code})"}
        
        html = response.content.decode('utf-8', errors='ignore')
        
        next_data_pattern = r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>'
        next_match = re.search(next_data_pattern, html, re.DOTALL)
        
        if next_match:
            try:
                json_str = next_match.group(1)
                data = json.loads(json_str)
                keywords = find_keywords_in_json(data)
                
                if keywords:
                    return {"success": True, "place_id": place_id, "keywords": keywords}
            except:
                pass
        
        return {"success": False, "error": "대표키워드를 찾을 수 없습니다."}
            
    except Exception as e:
        return {"success": False, "error": f"오류 발생: {str(e)}"}


def find_keywords_in_json(obj, depth=0):
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
# 라우트: 상세 CPC 분석 (JSON)
#############################################
@app.route('/analyze-cpc')
def analyze_cpc():
    keyword = request.args.get('keyword', '맛집')
    
    results = {
        "keyword": keyword,
        "min_bid": {},
        "performance": {}
    }
    
    # 노출 최소 입찰가
    results["min_bid"]["PC"] = get_exposure_minimum_bid(keyword, 'PC')
    results["min_bid"]["MOBILE"] = get_exposure_minimum_bid(keyword, 'MOBILE')
    
    # 입찰가별 예상 성과
    test_bids = [70, 100, 200, 500, 1000, 2000, 3000, 5000, 7000, 10000]
    
    for device in ["PC", "MOBILE"]:
        perf = get_performance_estimate(keyword, test_bids, device)
        if perf["success"]:
            results["performance"][device] = perf["data"]
        else:
            results["performance"][device] = {"error": perf.get("error", "Failed")}
    
    return jsonify(results)


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
                response_text = "❌ 플레이스 ID를 입력해주세요\n\n예) 대표 37838432"
        
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
