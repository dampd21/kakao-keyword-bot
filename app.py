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

def clean_keyword(keyword):
    return keyword.replace(" ", "")

def get_comp_text(comp):
    """경쟁도 텍스트 반환"""
    if comp == "높음":
        return "[높음]"
    elif comp == "중간":
        return "[중간]"
    else:
        return "[낮음]"

def is_guide_message(text):
    """사용 가이드 메시지인지 확인"""
    guide_indicators = [
        "사용 가이드", "사용가이드", "──────",
        "키워드 검색량", "연관 검색어", "CPC",
        "블로그 상위글", "자동완성어", "대표키워드",
        "재미 기능", "경쟁도:", "키워드만 입력"
    ]
    
    count = sum(1 for indicator in guide_indicators if indicator in text)
    
    if count >= 3:
        return True
    if len(text) > 200 and "──" in text:
        return True
    
    return False


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
        response = requests.get(base_url + uri, headers=headers, params=params, timeout=5)
        
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
def get_performance_estimate(keyword, bids, device='MOBILE'):
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
        
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        return {"success": False, "status": response.status_code, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}


def get_optimal_bid_analysis(estimates):
    if not estimates:
        return None
    
    valid_estimates = [e for e in estimates if e.get('clicks', 0) > 0]
    if not valid_estimates:
        return None
    
    min_exposure = valid_estimates[0]
    
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
    
    best_efficiency = None
    
    for i, eff in enumerate(efficiency_data):
        if i + 1 < len(efficiency_data):
            next_eff = efficiency_data[i + 1]
            
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
            best_efficiency = {
                'data': eff['data'],
                'cost_per_click': eff['cost_per_click'],
                'reason': 'last_efficient'
            }
    
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
    
    alternative = None
    if best_efficiency and len(valid_estimates) >= 2:
        best_clicks = best_efficiency['data'].get('clicks', 0)
        min_alternative_clicks = max(best_clicks * 0.15, 10)
        
        best_bid = best_efficiency['data'].get('bid', 0)
        for est in valid_estimates:
            if est.get('bid', 0) < best_bid and est.get('clicks', 0) >= min_alternative_clicks:
                alternative = est
    
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
# 기능 1: 검색량 조회 (다중 키워드 지원)
#############################################
def get_search_volume(keyword):
    if "," in keyword:
        keywords = [k.strip() for k in keyword.split(",")][:5]
        return get_multi_search_volume(keywords)
    
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    kw = result["data"][0]
    pc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile = parse_count(kw.get("monthlyMobileQcCnt"))
    total = pc + mobile
    
    return f"""[검색량] {kw.get('relKeyword', keyword)}

──────────────
월간 검색량 (최근 1개월)
──────────────

총 검색량: {format_number(total)}회
ㄴ 모바일: {format_number(mobile)}회
ㄴ PC: {format_number(pc)}회

──────────────
※ 다른 명령어: "도움말" 입력"""


def get_multi_search_volume(keywords):
    """다중 키워드 검색량 조회"""
    response_parts = []
    
    for idx, keyword in enumerate(keywords):
        keyword = keyword.replace(" ", "")
        result = get_keyword_data(keyword)
        
        if result["success"]:
            kw = result["data"][0]
            pc = parse_count(kw.get("monthlyPcQcCnt"))
            mobile = parse_count(kw.get("monthlyMobileQcCnt"))
            total = pc + mobile
            
            part = f"""[검색량] {kw.get('relKeyword', keyword)}

──────────────
월간 검색량 (최근 1개월)
──────────────

총 검색량: {format_number(total)}회
ㄴ 모바일: {format_number(mobile)}회
ㄴ PC: {format_number(pc)}회"""
            
            response_parts.append(part)
        else:
            part = f"""[검색량] {keyword}

조회 실패"""
            response_parts.append(part)
    
    return "\n\n──────────────\n\n".join(response_parts) + "\n\n──────────────"


#############################################
# 기능 2: 연관 키워드 조회 (10개 + 검색량)
#############################################
def get_related_keywords(keyword):
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    keyword_list = result["data"][:10]
    
    response = f"""[연관키워드] {keyword}

──────────────
"""
    
    for i, kw in enumerate(keyword_list, 1):
        name = kw.get("relKeyword", "")
        pc = parse_count(kw.get("monthlyPcQcCnt"))
        mobile = parse_count(kw.get("monthlyMobileQcCnt"))
        total = pc + mobile
        comp = kw.get("compIdx", "")
        comp_text = get_comp_text(comp)
        
        response += f"{i}. {name} ({format_number(total)}) {comp_text}\n"
    
    response += """
──────────────
※ 괄호 안은 월간 검색량
※ 경쟁도: [높음] [중간] [낮음]"""
    
    return response


#############################################
# 기능 3: 광고 단가 조회
#############################################
def get_ad_cost(keyword):
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    kw = result["data"][0]
    keyword_name = kw.get('relKeyword', keyword)
    
    pc_qc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile_qc = parse_count(kw.get("monthlyMobileQcCnt"))
    total_qc = pc_qc + mobile_qc
    
    mobile_ratio = (mobile_qc * 100 // total_qc) if total_qc > 0 else 0
    pc_ratio = 100 - mobile_ratio
    
    response = f"""[광고분석] {keyword_name}

──────────────
키워드 정보
──────────────

월간 검색량: {format_number(total_qc)}회
ㄴ 모바일: {format_number(mobile_qc)}회 ({mobile_ratio}%)
ㄴ PC: {format_number(pc_qc)}회 ({pc_ratio}%)

"""
    
    test_bids = [100, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 7000, 10000]
    mobile_perf = get_performance_estimate(keyword_name, test_bids, 'MOBILE')
    pc_perf = get_performance_estimate(keyword_name, test_bids, 'PC')
    
    mobile_success = mobile_perf.get("success", False)
    pc_success = pc_perf.get("success", False)
    
    has_ad_data = False
    analysis = None
    
    if mobile_success:
        mobile_estimates = mobile_perf["data"].get("estimate", [])
        analysis = get_optimal_bid_analysis(mobile_estimates)
        
        if analysis:
            has_ad_data = True
            valid_estimates = analysis['all_estimates']
            
            response += f"""──────────────
모바일 광고 단가
──────────────

입찰가별 예상 성과

"""
            
            prev_clicks = 0
            for est in valid_estimates[:6]:
                bid = est.get("bid", 0)
                clicks = est.get("clicks", 0)
                cost = est.get("cost", 0)
                
                response += f"{format_number(bid)}원 > 월 {clicks}회 클릭 | {format_won(cost)}\n"
                
                if clicks == prev_clicks and prev_clicks > 0:
                    break
                prev_clicks = clicks
            
            max_effective_bid = analysis.get('max_effective_bid')
            if max_effective_bid:
                response += f"  * {format_number(max_effective_bid)}원 이상은 효과 동일\n"
            
            response += "\n"
            
            best_eff = analysis.get('best_efficiency')
            alternative = analysis.get('alternative')
            
            if best_eff:
                eff_data = best_eff['data']
                eff_bid = eff_data.get('bid', 0)
                eff_clicks = eff_data.get('clicks', 0)
                eff_cost = eff_data.get('cost', 0)
                eff_cpc = int(eff_cost / eff_clicks) if eff_clicks > 0 else eff_bid
                daily_budget = eff_cost / 30
                
                response += f"""──────────────
추천 입찰가
──────────────

추천: {format_number(eff_bid)}원
ㄴ 예상 클릭: 월 {eff_clicks}회
ㄴ 예상 비용: 월 {format_won(eff_cost)}
ㄴ 클릭당 비용: 약 {format_number(eff_cpc)}원
ㄴ 일 예산: 약 {format_won(daily_budget)}

"""
                
                if max_effective_bid and max_effective_bid <= eff_bid:
                    response += f"* {format_number(eff_bid)}원 이상 올려도 클릭 증가 없음\n"
                elif max_effective_bid:
                    response += f"* {format_number(max_effective_bid)}원 이상 올려도 클릭 증가 없음\n"
                
                if alternative:
                    alt_bid = alternative.get('bid', 0)
                    alt_clicks = alternative.get('clicks', 0)
                    alt_cost = alternative.get('cost', 0)
                    response += f"* 예산 적으면 {format_number(alt_bid)}원도 가능 (월 {alt_clicks}회/{format_won(alt_cost)})\n"
                
                response += "\n"
    
    if pc_success:
        pc_estimates = pc_perf["data"].get("estimate", [])
        pc_analysis = get_optimal_bid_analysis(pc_estimates)
        
        if pc_analysis and pc_analysis.get('best_efficiency'):
            has_ad_data = True
            pc_eff = pc_analysis['best_efficiency']['data']
            pc_clicks = pc_eff.get('clicks', 0)
            
            if pc_clicks >= 10:
                pc_bid = pc_eff.get('bid', 0)
                pc_cost = pc_eff.get('cost', 0)
                
                response += f"""──────────────
PC 광고
──────────────

추천: {format_number(pc_bid)}원
ㄴ 예상 클릭: 월 {pc_clicks}회
ㄴ 예상 비용: 월 {format_won(pc_cost)}

"""
            else:
                response += f"""──────────────
PC 광고
──────────────

* PC 검색량 적어 모바일 집중 권장

"""
    
    if not has_ad_data:
        response += f"""──────────────
광고 단가 정보
──────────────

검색량이 적어 예상 클릭 데이터가 없습니다.

참고 가이드:
- 검색량 {format_number(total_qc)}회 기준
- 예상 입찰가: 100~500원 시작 권장
- 일 예산: 5,000~10,000원 시작
- 1-2주 운영 후 데이터 보고 조정

──────────────"""
    elif mobile_success and analysis and analysis.get('best_efficiency'):
        eff_data = analysis['best_efficiency']['data']
        eff_cost = eff_data.get('cost', 0)
        eff_bid = eff_data.get('bid', 0)
        
        daily_budget = max(eff_cost / 30, 10000)
        
        response += f"""──────────────
운영 가이드
──────────────

시작 설정
- 입찰가: {format_number(eff_bid)}원
- 일 예산: {format_won(daily_budget)}
- 월 예산: 약 {format_won(daily_budget * 30)}

운영 팁
- 1주일 후 CTR 확인 (1.5% 이상 목표)
- 전환 발생 시 예산 증액 검토
- 품질점수 관리로 CPC 절감 가능

──────────────"""
    
    return response


#############################################
# 기능 4: 블로그 상위 5개 제목
#############################################
def get_blog_titles(keyword):
    """실제 네이버 블로그 탭 상위 블로그 조회"""
    try:
        url = f"https://m.search.naver.com/search.naver?where=m_blog&query={requests.utils.quote(keyword)}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9"
        }
        
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            html = response.text
            
            titles = []
            
            pattern1 = re.findall(r'class="title_area"[^>]*>.*?<a[^>]*>([^<]+)</a>', html, re.DOTALL)
            pattern2 = re.findall(r'class="total_tit"[^>]*>([^<]+)</a>', html)
            pattern3 = re.findall(r'class="api_txt_lines[^"]*"[^>]*>([^<]+)</a>', html)
            pattern4 = re.findall(r'<a[^>]*class="[^"]*tit[^"]*"[^>]*>([^<]+)</a>', html)
            
            all_titles = pattern1 + pattern2 + pattern3 + pattern4
            
            seen = set()
            for title in all_titles:
                title = title.strip()
                title = re.sub(r'<[^>]+>', '', title)
                title = re.sub(r'\s+', ' ', title)
                if title and len(title) > 5 and title not in seen:
                    seen.add(title)
                    titles.append(title)
                    if len(titles) >= 5:
                        break
            
            if titles:
                result = f"""[블로그] {keyword} 상위 5개

──────────────
"""
                for i, title in enumerate(titles[:5], 1):
                    result += f"{i}. {title}\n\n"
                
                result += """──────────────
※ 실제 네이버 블로그 탭 기준"""
                return result
        
        return get_blog_titles_api(keyword)
        
    except Exception as e:
        return get_blog_titles_api(keyword)


def get_blog_titles_api(keyword):
    """네이버 검색 API로 블로그 조회 (백업)"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return f"""[블로그] {keyword}

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
        response = requests.get(url, headers=headers, params=params, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            
            if items:
                result = f"""[블로그] {keyword} 상위 5개

──────────────
"""
                for i, item in enumerate(items, 1):
                    title = item.get("title", "")
                    title = title.replace("<b>", "").replace("</b>", "")
                    blogger = item.get("bloggername", "")
                    
                    result += f"""{i}. {title}
   by {blogger}

"""
                
                result += """──────────────
※ 네이버 검색 API 기준"""
                
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
def get_fortune(birthdate=None):
    if not GEMINI_API_KEY:
        return get_fortune_fallback(birthdate)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    headers = {"Content-Type": "application/json"}
    
    if birthdate:
        if len(birthdate) == 6:
            year = birthdate[:2]
            month = birthdate[2:4]
            day = birthdate[4:6]
            year_full = f"19{year}" if int(year) > 30 else f"20{year}"
        elif len(birthdate) == 8:
            year_full = birthdate[:4]
            month = birthdate[4:6]
            day = birthdate[6:8]
        else:
            return get_fortune()
        
        prompt = f"""생년월일 {year_full}년 {month}월 {day}일생의 오늘 운세를 알려줘.

다음 형식으로 작성해줘:

[운세] {year_full}년 {month}월 {day}일생

총운
(2줄 이내로 오늘의 전체적인 운세)

애정운: (1줄)
금전운: (1줄)
직장/학업운: (1줄)
건강운: (1줄)

행운의 숫자: (1-45 사이 숫자 3개)
행운의 색: (색상 1개)

오늘의 조언
"(이 생년월일에 맞는 오늘의 조언)"

재미있고 긍정적으로 작성해줘. 이모티콘은 사용하지 마."""
    else:
        prompt = """오늘의 운세를 재미있고 긍정적으로 알려줘.

다음 형식으로 작성해줘:

[오늘의 운세]

총운
(2줄 이내)

애정운: (1줄)
금전운: (1줄)
직장/학업운: (1줄)

행운의 숫자: (1-45 사이 숫자 3개)
행운의 색: (색상 1개)

오늘의 한마디
"(짧은 격언이나 응원 메시지)"

이모티콘은 사용하지 마."""

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.9,
            "maxOutputTokens": 500
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=4)
        
        if response.status_code == 200:
            result = response.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return text
        else:
            return get_fortune_fallback(birthdate)
            
    except:
        return get_fortune_fallback(birthdate)

def get_fortune_fallback(birthdate=None):
    fortunes = ["오늘은 새로운 기회가 찾아오는 날!", "좋은 소식이 들려올 예정이에요.", "작은 행운이 당신을 따라다녀요."]
    love = ["설레는 만남이 있을 수 있어요", "소중한 사람과 대화를 나눠보세요"]
    money = ["작은 횡재수가 있어요", "절약이 미덕인 날"]
    work = ["집중력이 높아지는 시간", "새 프로젝트에 도전해보세요"]
    
    lucky_numbers = random.sample(range(1, 46), 3)
    lucky_numbers.sort()
    colors = ["빨간색", "파란색", "노란색", "초록색", "보라색"]
    quotes = ["오늘 하루도 화이팅!", "웃으면 복이 와요", "당신은 할 수 있어요!"]
    
    if birthdate:
        if len(birthdate) == 6:
            year = birthdate[:2]
            month = birthdate[2:4]
            day = birthdate[4:6]
            year_full = f"19{year}" if int(year) > 30 else f"20{year}"
        elif len(birthdate) == 8:
            year_full = birthdate[:4]
            month = birthdate[4:6]
            day = birthdate[6:8]
        else:
            year_full, month, day = "????", "??", "??"
        
        return f"""[운세] {year_full}년 {month}월 {day}일생

총운
{random.choice(fortunes)}

애정운: {random.choice(love)}
금전운: {random.choice(money)}
직장/학업운: {random.choice(work)}

행운의 숫자: {lucky_numbers[0]}, {lucky_numbers[1]}, {lucky_numbers[2]}
행운의 색: {random.choice(colors)}

──────────────
"{random.choice(quotes)}"
"""
    else:
        return f"""[오늘의 운세]

총운
{random.choice(fortunes)}

애정운: {random.choice(love)}
금전운: {random.choice(money)}
직장/학업운: {random.choice(work)}

행운의 숫자: {lucky_numbers[0]}, {lucky_numbers[1]}, {lucky_numbers[2]}
행운의 색: {random.choice(colors)}

──────────────
"{random.choice(quotes)}"
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

[로또 번호 추천]

1) 00, 00, 00, 00, 00, 00
2) 00, 00, 00, 00, 00, 00
3) 00, 00, 00, 00, 00, 00
4) 00, 00, 00, 00, 00, 00
5) 00, 00, 00, 00, 00, 00

──────────────
행운을 빕니다!

※ 로또는 재미로만 즐겨주세요!

이모티콘은 사용하지 마."""

    data = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1.0,
            "maxOutputTokens": 400
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=4)
        
        if response.status_code == 200:
            result = response.json()
            text = result["candidates"][0]["content"]["parts"][0]["text"]
            return text
        else:
            return get_lotto_fallback()
            
    except:
        return get_lotto_fallback()

def get_lotto_fallback():
    result = """[로또 번호 추천]

"""
    
    for i in range(1, 6):
        numbers = random.sample(range(1, 46), 6)
        numbers.sort()
        numbers_str = ", ".join(str(n).zfill(2) for n in numbers)
        result += f"{i}) {numbers_str}\n"
    
    result += """
──────────────
행운을 빕니다!

※ 로또는 재미로만 즐기세요!"""
    
    return result


#############################################
# 기능 7: 대표키워드 조회
#############################################
def extract_place_id_from_url(url_or_id):
    """URL에서 플레이스 ID 추출"""
    url_or_id = url_or_id.strip()
    
    if url_or_id.isdigit():
        return url_or_id
    
    patterns = [
        r'/restaurant/(\d+)',
        r'/place/(\d+)',
        r'/cafe/(\d+)',
        r'/hospital/(\d+)',
        r'/beauty/(\d+)',
        r'/accommodation/(\d+)',
        r'/leisure/(\d+)',
        r'/shopping/(\d+)',
        r'/entry/place/(\d+)',
        r'place/(\d+)',
        r'=(\d{10,})',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            place_id = match.group(1)
            if len(place_id) >= 7 and place_id.isdigit():
                return place_id
    
    number_match = re.search(r'\d{7,}', url_or_id)
    if number_match:
        return number_match.group(0)
    
    return None


def get_place_keywords(place_id):
    """대표키워드 조회"""
    debug_info = []
    
    api_url = f"https://m.place.naver.com/restaurant/{place_id}/home"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Accept-Encoding": "identity"
    }
    
    try:
        response = requests.get(api_url, headers=headers, timeout=10)
        debug_info.append(f"status: {response.status_code}")
        
        if response.status_code == 200:
            try:
                html = response.content.decode('utf-8')
            except:
                html = response.content.decode('utf-8', errors='ignore')
            
            debug_info.append(f"html 길이: {len(html)}")
            
            match = re.search(r'"keywordList"\s*:\s*\[((?:"[^"]*",?\s*)*)\]', html)
            if match:
                debug_info.append("keywordList 발견")
                try:
                    keywords_str = "[" + match.group(1) + "]"
                    keywords = json.loads(keywords_str)
                    if keywords and len(keywords) > 0:
                        debug_info.append(f"첫번째 키워드: {keywords[0]}")
                        return {"success": True, "place_id": place_id, "keywords": keywords, "debug": debug_info}
                except Exception as e:
                    debug_info.append(f"파싱 오류: {str(e)}")
            
            match2 = re.search(r'"keywords"\s*:\s*\[((?:"[^"]*",?\s*)*)\]', html)
            if match2:
                debug_info.append("keywords 발견")
                try:
                    keywords_str = "[" + match2.group(1) + "]"
                    keywords = json.loads(keywords_str)
                    if keywords and len(keywords) > 0:
                        return {"success": True, "place_id": place_id, "keywords": keywords, "debug": debug_info}
                except Exception as e:
                    debug_info.append(f"파싱 오류: {str(e)}")
            
            debug_info.append("키워드 패턴 없음")
                    
    except Exception as e:
        debug_info.append(f"오류: {str(e)}")
    
    categories = ['place', 'cafe', 'hospital', 'beauty']
    for category in categories:
        try:
            alt_url = f"https://m.place.naver.com/{category}/{place_id}/home"
            response = requests.get(alt_url, headers=headers, timeout=5)
            
            if response.status_code == 200:
                try:
                    html = response.content.decode('utf-8')
                except:
                    html = response.content.decode('utf-8', errors='ignore')
                
                match = re.search(r'"keywordList"\s*:\s*\[((?:"[^"]*",?\s*)*)\]', html)
                if match:
                    try:
                        keywords_str = "[" + match.group(1) + "]"
                        keywords = json.loads(keywords_str)
                        if keywords:
                            debug_info.append(f"{category}에서 발견")
                            return {"success": True, "place_id": place_id, "keywords": keywords, "debug": debug_info}
                    except:
                        pass
        except:
            pass
    
    return {"success": False, "error": "대표키워드를 찾을 수 없습니다.", "debug": debug_info}


def format_place_keywords(input_str):
    """플레이스 ID 또는 URL을 받아서 대표키워드 조회"""
    input_str = input_str.strip().replace('\n', '').replace('\r', '')
    
    place_id = extract_place_id_from_url(input_str)
    
    if not place_id:
        display_input = input_str[:100] + "..." if len(input_str) > 100 else input_str
        
        return f"""[대표키워드] 조회 실패

입력값: {display_input}
플레이스 ID를 찾을 수 없습니다.

──────────────
사용 방법:
1. 플레이스 ID만 입력
   예) 대표 1529801174

2. 네이버 플레이스 URL 입력
   예) 대표 place.naver.com/restaurant/1529801174"""
    
    result = get_place_keywords(place_id)
    
    if not result["success"]:
        return f"""[대표키워드] 조회 실패

플레이스 ID: {place_id}
오류: {result['error']}

──────────────
다음을 확인해주세요:
- 올바른 플레이스 ID인지 확인
- 해당 가게가 존재하는지 확인"""
    
    keywords = result["keywords"]
    
    response = f"""[대표키워드] 조회 완료

플레이스 ID: {place_id}

──────────────
대표키워드 ({len(keywords)}개)
──────────────

"""
    
    for i, kw in enumerate(keywords, 1):
        response += f"{i}. {kw}\n"
    
    response += f"""
──────────────
복사용: {', '.join(keywords)}

──────────────
검색량 확인 > "{keywords[0]}" 입력"""
    
    return response


#############################################
# 기능 8: 자동완성 키워드 조회
#############################################
def get_autocomplete(keyword):
    """네이버 자동완성 키워드 조회"""
    try:
        ac_url = "https://ac.search.naver.com/nx/ac"
        
        params = {
            "q": keyword,
            "con": "1",
            "frm": "nv",
            "ans": "2",
            "r_format": "json",
            "r_enc": "UTF-8",
            "r_unicode": "0",
            "t_koreng": "1",
            "run": "2",
            "rev": "4",
            "q_enc": "UTF-8",
            "st": "100"
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9",
            "Referer": "https://www.naver.com/"
        }
        
        response = requests.get(ac_url, params=params, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            
            suggestions = []
            
            items = data.get("items", [])
            
            for item_group in items:
                if isinstance(item_group, list):
                    for item in item_group:
                        if isinstance(item, list) and len(item) > 0:
                            kw = item[0]
                            if isinstance(kw, list) and len(kw) > 0:
                                suggestions.append(kw[0])
                            elif isinstance(kw, str):
                                suggestions.append(kw)
            
            query_items = data.get("query", [])
            if isinstance(query_items, list):
                for q in query_items:
                    if isinstance(q, str):
                        suggestions.append(q)
            
            seen = set()
            unique_suggestions = []
            for s in suggestions:
                s = str(s).strip()
                if s and s not in seen and s != keyword:
                    seen.add(s)
                    unique_suggestions.append(s)
                    if len(unique_suggestions) >= 10:
                        break
            
            if unique_suggestions:
                result = f"""[자동완성] {keyword}

──────────────
"""
                for i, suggestion in enumerate(unique_suggestions, 1):
                    result += f"{i}. {suggestion}\n"
                
                result += f"""
──────────────
총 {len(unique_suggestions)}개 자동완성어
※ 띄어쓰기에 따라 결과가 다릅니다"""
                
                return result
        
        return get_autocomplete_mobile(keyword)
        
    except Exception as e:
        return get_autocomplete_mobile(keyword)


def get_autocomplete_mobile(keyword):
    """모바일 자동완성 API (백업)"""
    try:
        url = "https://mac.search.naver.com/mobile/ac"
        
        params = {
            "q": keyword,
            "st": 111111,
            "frm": "mobile_nv",
            "r_format": "json",
            "r_enc": "UTF-8",
            "r_unicode": "0",
            "t_koreng": "1"
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)",
            "Referer": "https://m.naver.com/"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        
        if response.status_code == 200:
            data = response.json()
            suggestions = []
            
            items = data.get("items", [])
            for item in items:
                if isinstance(item, list):
                    for subitem in item:
                        if isinstance(subitem, list) and len(subitem) > 0:
                            kw = subitem[0][0] if isinstance(subitem[0], list) else subitem[0]
                            suggestions.append(kw)
            
            seen = set()
            unique_suggestions = []
            for s in suggestions:
                if s not in seen and s != keyword:
                    seen.add(s)
                    unique_suggestions.append(s)
                    if len(unique_suggestions) >= 10:
                        break
            
            if unique_suggestions:
                result = f"""[자동완성] {keyword}

──────────────
"""
                for i, suggestion in enumerate(unique_suggestions, 1):
                    result += f"{i}. {suggestion}\n"
                
                result += f"""
──────────────
총 {len(unique_suggestions)}개 자동완성어"""
                
                return result
    except:
        pass
    
    return f"""[자동완성] {keyword}

자동완성 결과가 없습니다.

──────────────
다른 키워드로 시도해보세요"""


#############################################
# 도움말
#############################################
def get_help():
    return """[사용 가이드]

──────────────
키워드 검색량 (최대 5개)
──────────────
> 키워드만 입력
예) 인천맛집
예) 인천맛집,강남맛집,서울맛집

──────────────
연관 검색어
──────────────
> 연관 + 키워드
예) 연관 인천맛집

──────────────
CPC 광고 단가
──────────────
> 광고 + 키워드
예) 광고 인천맛집

──────────────
블로그 상위글
──────────────
> 블로그 + 키워드
예) 블로그 인천맛집

──────────────
자동완성어
──────────────
> 자동 + 키워드
예) 자동 인천맛집
주의) 띄어쓰기 중요

──────────────
대표키워드
──────────────
> 대표 + 플레이스ID
예) 대표 12345678

──────────────
재미 기능
──────────────
운세 > 운세 870114
로또 > 로또

──────────────
경쟁도: [높음] [중간] [낮음]"""


#############################################
# 라우트: 홈
#############################################
@app.route('/')
def home():
    return "서버 정상 작동 중"


#############################################
# 라우트: 대표키워드 테스트
#############################################
@app.route('/test-place')
def test_place():
    place_id = request.args.get('id', '37838432')
    result = get_place_keywords(place_id)
    
    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>플레이스 테스트</title>
</head>
<body>
    <h2>플레이스 ID: {place_id}</h2>
    <h3>결과: {'성공' if result['success'] else '실패'}</h3>
"""
    
    if result['success']:
        html += f"<h4>키워드 ({len(result['keywords'])}개):</h4><ul>"
        for kw in result['keywords']:
            html += f"<li>{kw}</li>"
        html += "</ul>"
    else:
        html += f"<p>오류: {result.get('error', 'Unknown')}</p>"
    
    html += "<h4>디버그 로그:</h4><pre>"
    for log in result.get('debug', []):
        html += f"{log}\n"
    html += "</pre></body></html>"
    
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


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
        
        # 사용 가이드 메시지 감지
        if is_guide_message(user_utterance):
            return create_kakao_response(get_help())
        
        lower_input = user_utterance.lower()
        
        # 도움말
        if lower_input in ["도움말", "도움", "사용법", "help", "?", "메뉴"]:
            return create_kakao_response(get_help())
        
        # 운세 (생년월일 포함)
        if lower_input.startswith("운세 "):
            birthdate = ''.join(filter(str.isdigit, user_utterance))
            if birthdate and len(birthdate) in [6, 8]:
                response_text = get_fortune(birthdate)
            else:
                response_text = """[운세] 생년월일 입력

생년월일을 6자리 또는 8자리로 입력해주세요

──────────────
예) 운세 870114
예) 운세 19870114

──────────────
일반 운세: "운세" 만 입력"""
            return create_kakao_response(response_text)
        
        # 운세 (일반)
        if lower_input in ["운세", "오늘의운세", "오늘운세", "오늘의 운세", "fortune"]:
            return create_kakao_response(get_fortune())
        
        # 로또
        if lower_input in ["로또", "로또번호", "로또 번호", "lotto", "번호추천", "번호 추천"]:
            return create_kakao_response(get_lotto())
        
        # 자동완성 키워드
        if lower_input.startswith("자동 ") or lower_input.startswith("자동완성 "):
            if lower_input.startswith("자동완성 "):
                keyword = user_utterance[5:].strip()
            else:
                keyword = user_utterance[3:].strip()
            
            if keyword:
                response_text = get_autocomplete(keyword)
            else:
                response_text = """[자동완성] 키워드 입력

키워드를 입력해주세요

──────────────
예) 자동 부평맛집
예) 자동 부평 맛집

──────────────
띄어쓰기에 따라 결과가 다릅니다"""
            return create_kakao_response(response_text)
        
        # 대표키워드
        if lower_input.startswith("대표 ") or lower_input.startswith("대표키워드 "):
            if lower_input.startswith("대표키워드 "):
                input_text = user_utterance[6:].strip()
            else:
                input_text = user_utterance[3:].strip()
            
            if input_text:
                response_text = format_place_keywords(input_text)
            else:
                response_text = """[대표키워드] ID 입력

플레이스 ID 또는 URL을 입력해주세요

──────────────
예) 대표 37838432
예) 대표 place.naver.com/restaurant/37838432"""
            return create_kakao_response(response_text)
        
        # 연관 키워드
        if lower_input.startswith("연관 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                response_text = get_related_keywords(keyword)
            else:
                response_text = "키워드를 입력해주세요\n예) 연관 맛집"
            return create_kakao_response(response_text)
        
        # 광고 단가
        if lower_input.startswith("광고 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                response_text = get_ad_cost(keyword)
            else:
                response_text = "키워드를 입력해주세요\n예) 광고 맛집"
            return create_kakao_response(response_text)
        
        # 블로그 상위글
        if lower_input.startswith("블로그 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                response_text = get_blog_titles(keyword)
            else:
                response_text = "키워드를 입력해주세요\n예) 블로그 맛집"
            return create_kakao_response(response_text)
        
        # 기본: 검색량 조회
        keyword = user_utterance.strip()
        if "," in keyword:
            response_text = get_search_volume(keyword)
        else:
            keyword = clean_keyword(keyword)
            response_text = get_search_volume(keyword)
        
        return create_kakao_response(response_text)
        
    except Exception as e:
        return create_kakao_response(f"오류 발생: {str(e)}")


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
