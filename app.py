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
        
        # 올바른 형식: key + bids 배열
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


def get_optimal_bid_analysis(estimates):
    """최적 입찰가 분석 - 효율 급락 직전 구간 찾기"""
    if not estimates:
        return None
    
    valid_estimates = [e for e in estimates if e.get('clicks', 0) > 0]
    if not valid_estimates:
        return None
    
    # 1. 최소 노출
    min_exposure = valid_estimates[0]
    
    # 2. 구간별 효율 계산
    efficiency_data = []
    for i in range(1, len(valid_estimates)):
        prev = valid_estimates[i-1]
        curr = valid_estimates[i]
        
        click_increase = curr.get('clicks', 0) - prev.get('clicks', 0)
        cost_increase = curr.get('cost', 0) - prev.get('cost', 0)
        
        if cost_increase > 0 and click_increase > 0:
            cost_per_additional_click = cost_increase / click_increase
            efficiency_data.append({
                'index': i,
                'data': curr,
                'prev_data': prev,
                'click_increase': click_increase,
                'cost_increase': cost_increase,
                'cost_per_click': cost_per_additional_click
            })
    
    # 3. 효율이 급락하는 지점 찾기
    best_efficiency = None
    
    for i, eff in enumerate(efficiency_data):
        if i + 1 < len(efficiency_data):
            next_eff = efficiency_data[i + 1]
            
            # 다음 구간의 효율이 현재보다 2배 이상 나쁘거나
            # 다음 구간의 클릭 증가가 현재의 10% 미만이면 현재 구간이 최적
            efficiency_drop = next_eff['cost_per_click'] / eff['cost_per_click'] if eff['cost_per_click'] > 0 else 999
            click_ratio = next_eff['click_increase'] / eff['click_increase'] if eff['click_increase'] > 0 else 0
            
            if efficiency_drop >= 2 or click_ratio < 0.1:
                best_efficiency = {
                    'data': eff['data'],
                    'cost_per_click': eff['cost_per_click'],
                    'reason': 'efficiency_drop'
                }
                break
        else:
            # 마지막 구간이면 이게 최적
            best_efficiency = {
                'data': eff['data'],
                'cost_per_click': eff['cost_per_click'],
                'reason': 'last_efficient'
            }
    
    # 효율 분석 실패 시 기존 로직
    if not best_efficiency:
        if len(valid_estimates) >= 3:
            mid_idx = len(valid_estimates) // 2
            best_efficiency = {
                'data': valid_estimates[mid_idx],
                'cost_per_click': None
            }
        elif valid_estimates:
            best_efficiency = {
                'data': valid_estimates[-1],
                'cost_per_click': None
            }
    
    # 4. 차선책 찾기 - 추천 클릭의 15% 이상 (최소 10회)
    alternative = None
    if best_efficiency and len(valid_estimates) >= 2:
        best_clicks = best_efficiency['data'].get('clicks', 0)
        min_alternative_clicks = max(best_clicks * 0.15, 10)
        
        best_bid = best_efficiency['data'].get('bid', 0)
        for est in valid_estimates:
            if est.get('bid', 0) < best_bid and est.get('clicks', 0) >= min_alternative_clicks:
                alternative = est
    
    # 5. 효과 동일 구간 찾기 (입찰가 올려도 클릭 안 늘어나는 지점)
    max_effective_bid = None
    if valid_estimates:
        max_clicks = valid_estimates[-1].get('clicks', 0)
        for est in valid_estimates:
            if est.get('clicks', 0) == max_clicks:
                max_effective_bid = est.get('bid', 0)
                break
    
    return {
        'min_exposure': min_exposure,
        'best_efficiency': best_efficiency,
        'alternative': alternative,
        'max_effective_bid': max_effective_bid,
        'all_estimates': valid_estimates
    }


#############################################
# 기능 1: 검색량 조회
#############################################
def get_search_volume(keyword):
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    kw = result["data"][0]
    pc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile = parse_count(kw.get("monthlyMobileQcCnt"))
    total = pc + mobile
    comp = kw.get("compIdx", "정보없음")
    
    comp_mark = {"높음": "🔴", "중간": "🟡"}.get(comp, "🟢")
    
    return f"""🔍 "{kw.get('relKeyword', keyword)}" 검색량

월간 총: {format_number(total)}회
├ 모바일: {format_number(mobile)}회
└ PC: {format_number(pc)}회

경쟁도: {comp} {comp_mark}

━━━━━━━━━━━━━━━━
※ 다른 명령어: "도움말" 입력"""


#############################################
# 기능 2: 연관 키워드 조회
#############################################
def get_related_keywords(keyword):
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    keyword_list = result["data"][:6]
    
    response = f"""🔗 "{keyword}" 연관 키워드

"""
    
    for i, kw in enumerate(keyword_list[:5], 1):
        name = kw.get("relKeyword", "")
        pc = parse_count(kw.get("monthlyPcQcCnt"))
        mobile = parse_count(kw.get("monthlyMobileQcCnt"))
        total = pc + mobile
        comp = kw.get("compIdx", "")
        
        comp_mark = {"높음": "🔴", "중간": "🟡"}.get(comp, "🟢")
        
        response += f"{i}. {name}\n   {format_number(total)}회 {comp_mark}\n\n"
    
    return response.strip()


#############################################
# 기능 3: 광고 단가 조회 (개선 버전)
#############################################
def get_ad_cost(keyword):
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    kw = result["data"][0]
    keyword_name = kw.get('relKeyword', keyword)
    
    # 키워드 도구 데이터
    pc_qc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile_qc = parse_count(kw.get("monthlyMobileQcCnt"))
    total_qc = pc_qc + mobile_qc
    
    comp = kw.get("compIdx", "정보없음")
    comp_mark = {"높음": "🔴", "중간": "🟡"}.get(comp, "🟢")
    
    # 모바일 비율 계산
    mobile_ratio = (mobile_qc * 100 // total_qc) if total_qc > 0 else 0
    pc_ratio = 100 - mobile_ratio
    
    # 헤더
    response = f"""💰 "{keyword_name}" 광고 분석

━━━━━━━━━━━━━━━━━━━━━━━━
📊 키워드 정보
━━━━━━━━━━━━━━━━━━━━━━━━

경쟁도: {comp} {comp_mark}
월간 검색량: {format_number(total_qc)}회
├ 모바일: {format_number(mobile_qc)}회 ({mobile_ratio}%)
└ PC: {format_number(pc_qc)}회 ({pc_ratio}%)

"""
    
    # Performance API 분석
    test_bids = [100, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 7000, 10000]
    mobile_perf = get_performance_estimate(keyword_name, test_bids, 'MOBILE')
    pc_perf = get_performance_estimate(keyword_name, test_bids, 'PC')
    
    mobile_success = mobile_perf.get("success", False)
    pc_success = pc_perf.get("success", False)
    
    if mobile_success:
        mobile_estimates = mobile_perf["data"].get("estimate", [])
        analysis = get_optimal_bid_analysis(mobile_estimates)
        
        if analysis:
            valid_estimates = analysis['all_estimates']
            
            response += f"""━━━━━━━━━━━━━━━━━━━━━━━━
📱 모바일 광고 단가
━━━━━━━━━━━━━━━━━━━━━━━━

입찰가별 예상 성과

"""
            
            # 입찰가별 성과 (간결하게)
            prev_clicks = 0
            for est in valid_estimates[:6]:
                bid = est.get("bid", 0)
                clicks = est.get("clicks", 0)
                cost = est.get("cost", 0)
                
                response += f"{format_number(bid)}원 → 월 {clicks}회 클릭 | {format_won(cost)}\n"
                
                # 클릭 증가 없으면 표시
                if clicks == prev_clicks and prev_clicks > 0:
                    break
                prev_clicks = clicks
            
            # 효과 동일 구간 안내
            max_effective_bid = analysis.get('max_effective_bid')
            if max_effective_bid:
                response += f"  ↑ {format_number(max_effective_bid)}원 이상은 효과 동일\n"
            
            response += "\n"
            
            # 추천 입찰가
            best_eff = analysis.get('best_efficiency')
            alternative = analysis.get('alternative')
            
            if best_eff:
                eff_data = best_eff['data']
                eff_bid = eff_data.get('bid', 0)
                eff_clicks = eff_data.get('clicks', 0)
                eff_cost = eff_data.get('cost', 0)
                eff_cpc = int(eff_cost / eff_clicks) if eff_clicks > 0 else eff_bid
                daily_budget = eff_cost / 30
                
                response += f"""━━━━━━━━━━━━━━━━━━━━━━━━
🎯 추천 입찰가
━━━━━━━━━━━━━━━━━━━━━━━━

✅ 추천: {format_number(eff_bid)}원
├ 예상 클릭: 월 {eff_clicks}회
├ 예상 비용: 월 {format_won(eff_cost)}
├ 클릭당 비용: 약 {format_number(eff_cpc)}원
└ 일 예산: 약 {format_won(daily_budget)}

"""
                
                # 효과 동일 안내
                if max_effective_bid and max_effective_bid <= eff_bid:
                    response += f"※ {format_number(eff_bid)}원 이상 올려도 클릭 증가 없음\n"
                elif max_effective_bid:
                    response += f"※ {format_number(max_effective_bid)}원 이상 올려도 클릭 증가 없음\n"
                
                # 차선책 안내
                if alternative:
                    alt_bid = alternative.get('bid', 0)
                    alt_clicks = alternative.get('clicks', 0)
                    alt_cost = alternative.get('cost', 0)
                    response += f"※ 예산 적으면 {format_number(alt_bid)}원도 가능 (월 {alt_clicks}회/{format_won(alt_cost)})\n"
                
                response += "\n"
    
    # PC 분석
    if pc_success:
        pc_estimates = pc_perf["data"].get("estimate", [])
        pc_analysis = get_optimal_bid_analysis(pc_estimates)
        
        if pc_analysis and pc_analysis.get('best_efficiency'):
            pc_eff = pc_analysis['best_efficiency']['data']
            pc_clicks = pc_eff.get('clicks', 0)
            
            if pc_clicks >= 10:
                pc_bid = pc_eff.get('bid', 0)
                pc_cost = pc_eff.get('cost', 0)
                pc_cpc = int(pc_cost / pc_clicks) if pc_clicks > 0 else pc_bid
                
                response += f"""━━━━━━━━━━━━━━━━━━━━━━━━
💻 PC 광고
━━━━━━━━━━━━━━━━━━━━━━━━

추천: {format_number(pc_bid)}원
├ 예상 클릭: 월 {pc_clicks}회
└ 예상 비용: 월 {format_won(pc_cost)}

"""
            else:
                response += f"""━━━━━━━━━━━━━━━━━━━━━━━━
💻 PC 광고
━━━━━━━━━━━━━━━━━━━━━━━━

※ PC 검색량 적어 모바일 집중 권장

"""
    
    # 운영 가이드
    if mobile_success and analysis and analysis.get('best_efficiency'):
        eff_data = analysis['best_efficiency']['data']
        eff_cost = eff_data.get('cost', 0)
        eff_bid = eff_data.get('bid', 0)
        eff_clicks = eff_data.get('clicks', 0)
        
        daily_budget = max(eff_cost / 30, 10000)
        
        response += f"""━━━━━━━━━━━━━━━━━━━━━━━━
📋 운영 가이드
━━━━━━━━━━━━━━━━━━━━━━━━

시작 설정
• 입찰가: {format_number(eff_bid)}원
• 일 예산: {format_won(daily_budget)}
• 월 예산: 약 {format_won(daily_budget * 30)}

운영 팁
• 1주일 후 CTR 확인 (1.5% 이상 목표)
• 전환 발생 시 예산 증액 검토
• 품질점수 관리로 CPC 절감 가능

━━━━━━━━━━━━━━━━━━━━━━━━"""
    
    return response


#############################################
# 기능 4: 블로그 상위 5개 제목
#############################################
def get_blog_titles(keyword):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return f"""📝 "{keyword}" 블로그 분석

블로그 검색 API가 설정되지 않았습니다."""
    
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

"""
                for i, item in enumerate(items, 1):
                    title = item.get("title", "")
                    title = title.replace("<b>", "").replace("</b>", "")
                    blogger = item.get("bloggername", "")
                    
                    result += f"""{i}. {title}
   by {blogger}

"""
                
                result += """━━━━━━━━━━━━━━━━
※ 상위 제목 패턴을 분석해보세요"""
                
                return result
            else:
                return f"'{keyword}' 블로그 검색 결과가 없습니다."
        else:
            return f"블로그 검색 오류 ({response.status_code})"
            
    except Exception as e:
        return f"블로그 검색 실패: {str(e)}"


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
        return f"조회 실패: {result['error']}"
    
    keywords = result["keywords"]
    
    response = f"""🏷️ 대표키워드 조회

플레이스 ID: {place_id}

━━━━━━━━━━━━━━━━
대표키워드 ({len(keywords)}개)
━━━━━━━━━━━━━━━━

"""
    
    for i, kw in enumerate(keywords, 1):
        response += f"{i}. {kw}\n"
    
    response += f"""
━━━━━━━━━━━━━━━━
복사용: {', '.join(keywords)}

━━━━━━━━━━━━━━━━
※ 각 키워드 검색량도 확인해보세요
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
→ 키워드만 입력
예) 맛집

🔗 연관 키워드
→ "연관" + 키워드
예) 연관 맛집

💰 광고 단가
→ "광고" + 키워드
예) 광고 맛집

📝 블로그 상위글
→ "블로그" + 키워드
예) 블로그 맛집

🏷️ 대표키워드
→ "대표" + 플레이스ID
예) 대표 37838432

━━━━━━━━━━━━━━━━
🎯 재미 기능
━━━━━━━━━━━━━━━━

🔮 운세 → "운세" 입력
🎰 로또 → "로또" 입력

━━━━━━━━━━━━━━━━"""


#############################################
# 라우트: 홈
#############################################
@app.route('/')
def home():
    return "서버 정상 작동 중"


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
        <h2>"{kw.get('relKeyword', keyword)}" 검색량</h2>
        <p>월간 총: {format_number(pc + mobile)}회</p>
        <p>모바일: {format_number(mobile)}회</p>
        <p>PC: {format_number(pc)}회</p>
        """
    else:
        return f"<h2>조회 실패</h2><p>{result['error']}</p>"


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
    test_bids = [100, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 7000, 10000]
    
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
            return create_kakao_response("검색할 키워드를 입력해주세요!")
        
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
                response_text = "플레이스 ID를 입력해주세요\n\n예) 대표 37838432"
        
        # 연관 키워드
        elif lower_input.startswith("연관 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_related_keywords(keyword)
            else:
                response_text = "키워드를 입력해주세요\n예) 연관 맛집"
        
        # 광고 단가
        elif lower_input.startswith("광고 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_ad_cost(keyword)
            else:
                response_text = "키워드를 입력해주세요\n예) 광고 맛집"
        
        # 블로그 상위글
        elif lower_input.startswith("블로그 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_blog_titles(keyword)
            else:
                response_text = "키워드를 입력해주세요\n예) 블로그 맛집"
        
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
