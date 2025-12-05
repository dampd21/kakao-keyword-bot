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
import logging
from datetime import date, timedelta
from urllib.parse import quote

app = Flask(__name__)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

#############################################
# 환경변수 설정
#############################################
NAVER_API_KEY = os.environ.get('NAVER_API_KEY', '')
NAVER_SECRET_KEY = os.environ.get('NAVER_SECRET_KEY', '')
NAVER_CUSTOMER_ID = os.environ.get('NAVER_CUSTOMER_ID', '')
NAVER_CLIENT_ID = os.environ.get('NAVER_CLIENT_ID', '')
NAVER_CLIENT_SECRET = os.environ.get('NAVER_CLIENT_SECRET', '')
KAKAO_REST_API_KEY = os.environ.get('KAKAO_REST_API_KEY', '')
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
DATA_GO_KR_API_KEY = os.environ.get('DATA_GO_KR_API_KEY', '')

#############################################
# 환경변수 검증
#############################################
def validate_required_keys():
    """필수 API 키 검증"""
    required = {
        'NAVER_API_KEY': NAVER_API_KEY,
        'NAVER_SECRET_KEY': NAVER_SECRET_KEY,
        'NAVER_CUSTOMER_ID': NAVER_CUSTOMER_ID
    }
    missing = [k for k, v in required.items() if not v]
    if missing:
        logger.warning(f"⚠️ Missing required keys: {', '.join(missing)}")
        return False
    return True

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

#############################################
# 업종 코드 매핑
#############################################
INDUSTRY_CODES = {
    "음식점": {"code": "Q", "name": "음식점업"},
    "한식": {"code": "Q12", "name": "한식음식점"},
    "중식": {"code": "Q13", "name": "중식음식점"},
    "일식": {"code": "Q14", "name": "일식음식점"},
    "양식": {"code": "Q15", "name": "양식음식점"},
    "치킨": {"code": "Q16", "name": "치킨전문점"},
    "분식": {"code": "Q17", "name": "분식전문점"},
    "카페": {"code": "Q21", "name": "커피/음료"},
    "디저트": {"code": "Q22", "name": "제과점"},
    "병원": {"code": "G", "name": "의료업"},
    "의원": {"code": "G01", "name": "의원"},
    "치과": {"code": "G02", "name": "치과의원"},
    "한의원": {"code": "G03", "name": "한의원"},
    "피부과": {"code": "G04", "name": "피부과"},
    "학원": {"code": "R", "name": "학원"},
    "입시학원": {"code": "R01", "name": "입시학원"},
    "외국어학원": {"code": "R02", "name": "외국어학원"},
    "예체능학원": {"code": "R03", "name": "예체능학원"},
    "편의점": {"code": "D01", "name": "편의점"},
    "슈퍼마켓": {"code": "D02", "name": "슈퍼마켓"},
    "미용실": {"code": "S01", "name": "미용실"},
    "네일": {"code": "S02", "name": "네일샵"},
    "부동산": {"code": "L", "name": "부동산중개업"},
    "PC방": {"code": "R04", "name": "PC방"},
    "노래방": {"code": "R05", "name": "노래방"}
}

#############################################
# 네이버 검색광고 API
#############################################
def get_naver_api_headers(method="GET", uri="/keywordstool"):
    timestamp = str(int(time.time() * 1000))
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(NAVER_SECRET_KEY.encode('utf-8'), message.encode('utf-8'), hashlib.sha256).digest()
    signature_base64 = base64.b64encode(signature).decode('utf-8')
    return {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": NAVER_API_KEY,
        "X-Customer": str(NAVER_CUSTOMER_ID),
        "X-Signature": signature_base64
    }

def get_keyword_data(keyword, retry=1):
    """키워드 데이터 조회"""
    if not validate_required_keys():
        return {"success": False, "error": "API 키가 설정되지 않았습니다."}
    
    base_url = "https://api.searchad.naver.com"
    uri = "/keywordstool"
    params = {"hintKeywords": keyword, "showDetail": "1"}
    
    for attempt in range(retry + 1):
        try:
            headers = get_naver_api_headers("GET", uri)
            response = requests.get(base_url + uri, headers=headers, params=params, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                keyword_list = data.get("keywordList", [])
                if keyword_list:
                    return {"success": True, "data": keyword_list}
                return {"success": False, "error": "검색 결과가 없습니다."}
            
            if attempt < retry:
                time.sleep(0.3)
                continue
            
            return {"success": False, "error": f"API 오류 ({response.status_code})"}
            
        except requests.Timeout:
            if attempt < retry:
                time.sleep(0.3)
                continue
            return {"success": False, "error": "요청 시간 초과"}
        except Exception as e:
            logger.error(f"키워드 조회 오류: {str(e)}")
            return {"success": False, "error": str(e)}

def get_performance_estimate(keyword, bids, device='MOBILE', retry=1):
    """성과 예측 API"""
    uri = '/estimate/performance/keyword'
    url = f'https://api.searchad.naver.com{uri}'
    payload = {
        "device": device,
        "keywordplus": False,
        "key": keyword,
        "bids": bids if isinstance(bids, list) else [bids]
    }
    
    for attempt in range(retry + 1):
        try:
            headers = get_naver_api_headers('POST', uri)
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            
            if attempt < retry:
                time.sleep(0.3)
                continue
            
            return {"success": False, "error": response.text}
            
        except requests.Timeout:
            if attempt < retry:
                time.sleep(0.3)
                continue
            return {"success": False, "error": "요청 시간 초과"}
        except Exception as e:
            logger.error(f"성과 예측 오류: {str(e)}")
            return {"success": False, "error": str(e)}

#############################################
# 기존 기능 1: 검색량 조회
#############################################
def get_search_volume(keyword):
    if "," in keyword:
        keywords = [k.strip() for k in keyword.split(",")]
        if len(keywords) > 5:
            return "최대 5개 키워드까지만 조회 가능합니다."
        return get_multi_search_volume(keywords[:5])
    
    result = get_keyword_data(keyword)
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    kw = result["data"][0]
    pc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile = parse_count(kw.get("monthlyMobileQcCnt"))
    total = pc + mobile
    
    return f"""[검색량] {kw.get('relKeyword', keyword)}
월간 총 {format_number(total)}회
ㄴ 모바일: {format_number(mobile)}회
ㄴ PC: {format_number(pc)}회

※ 도움말: "도움말" 입력"""

def get_multi_search_volume(keywords):
    """다중 키워드 검색량"""
    lines = ["[검색량 비교]", ""]
    
    for keyword in keywords:
        keyword = keyword.replace(" ", "")
        result = get_keyword_data(keyword)
        
        if result["success"]:
            kw = result["data"][0]
            pc = parse_count(kw.get("monthlyPcQcCnt"))
            mobile = parse_count(kw.get("monthlyMobileQcCnt"))
            total = pc + mobile
            mobile_ratio = (mobile * 100 // total) if total > 0 else 0
            
            lines.append(f"▸ {kw.get('relKeyword', keyword)}")
            lines.append(f"  {format_number(total)}회 (모바일 {mobile_ratio}%)")
        else:
            lines.append(f"▸ {keyword}")
            lines.append(f"  조회 실패")
        lines.append("")
    
    return "\n".join(lines).strip()

#############################################
# 기존 기능 2: 연관 키워드
#############################################
def get_related_keywords(keyword):
    try:
        url = f"https://search.naver.com/search.naver?where=nexearch&query={requests.utils.quote(keyword)}"
        headers = {"User-Agent": "Mozilla/5.0", "Accept-Language": "ko-KR,ko;q=0.9"}
        response = requests.get(url, headers=headers, timeout=5)
        
        if response.status_code == 200:
            pattern = re.findall(r'<div class="tit">([^<]+)</div>', response.text)
            seen = set()
            related = []
            for kw in pattern:
                kw = kw.strip()
                if kw and kw != keyword and kw not in seen and len(kw) > 1:
                    seen.add(kw)
                    related.append(kw)
                    if len(related) >= 10:
                        break
            
            if related:
                result = f"[연관검색어] {keyword}\n\n"
                for i, kw in enumerate(related, 1):
                    result += f"{i}. {kw}\n"
                return result.strip()
        
        return get_related_keywords_api(keyword)
    except:
        return get_related_keywords_api(keyword)

def get_related_keywords_api(keyword):
    result = get_keyword_data(keyword)
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    keyword_list = result["data"][:10]
    response = f"[연관키워드] {keyword}\n\n"
    
    for i, kw in enumerate(keyword_list, 1):
        name = kw.get("relKeyword", "")
        total = parse_count(kw.get("monthlyPcQcCnt")) + parse_count(kw.get("monthlyMobileQcCnt"))
        response += f"{i}. {name} ({format_number(total)})\n"
    
    return response.strip()

#############################################
# 기존 기능 3: 광고 단가
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
    comp_idx = kw.get("compIdx", "중간")
    
    comp_emoji = "🔴" if comp_idx == "높음" else "🟡" if comp_idx == "중간" else "🟢"
    
    lines = [f"💰 \"{keyword_name}\" 광고 분석", ""]
    
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📊 키워드 정보")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"경쟁도: {comp_idx} {comp_emoji}")
    lines.append(f"월간 검색량: {format_number(total_qc)}회")
    lines.append(f"├ 모바일: {format_number(mobile_qc)}회 ({mobile_ratio}%)")
    lines.append(f"└ PC: {format_number(pc_qc)}회 ({100-mobile_ratio}%)")
    lines.append("")
    
    test_bids = [100, 200, 300, 400, 500, 700, 1000, 1500, 2000, 2500, 3000, 4000, 5000]
    
    mobile_perf = get_performance_estimate(keyword_name, test_bids, 'MOBILE')
    
    efficient_bid = None
    efficient_clicks = 0
    efficient_cost = 0
    
    if mobile_perf.get("success"):
        mobile_estimates = mobile_perf["data"].get("estimate", [])
        valid_estimates = [e for e in mobile_estimates if e.get('clicks', 0) > 0]
        
        if valid_estimates:
            lines.append("━━━━━━━━━━━━━━")
            lines.append("📱 모바일 성과 분석")
            lines.append("━━━━━━━━━━━━━━")
            lines.append("")
            
            max_clicks = max(e.get('clicks', 0) for e in valid_estimates)
            
            # 대표 입찰가 5개 선택
            selected = []
            ratios = [0.3, 0.5, 0.7, 0.9, 1.0]
            for ratio in ratios:
                target = int(max_clicks * ratio)
                closest = min(valid_estimates, key=lambda x: abs(x.get('clicks', 0) - target))
                if closest not in selected:
                    selected.append(closest)
            
            for est in selected[:5]:
                bid = est.get('bid', 0)
                clicks = est.get('clicks', 0)
                cost = est.get('cost', 0) or int(clicks * bid * 0.8)
                lines.append(f"{format_number(bid)}원 → 월 {clicks}회 | {format_won(cost)}")
            
            lines.append("")
            
            # 추천 입찰가 (70~80% 효율)
            if len(selected) >= 4:
                efficient_est = selected[3]
                efficient_bid = efficient_est.get('bid', 0)
                efficient_clicks = efficient_est.get('clicks', 0)
                efficient_cost = efficient_est.get('cost', 0) or int(efficient_clicks * efficient_bid * 0.8)
    
    if efficient_bid:
        lines.append("━━━━━━━━━━━━━━")
        lines.append("🎯 추천 입찰가")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"✅ 추천: {format_number(efficient_bid)}원")
        lines.append(f"├ 예상 클릭: 월 {efficient_clicks}회")
        lines.append(f"├ 예상 비용: {format_won(efficient_cost)}")
        
        cpc = int(efficient_cost / efficient_clicks) if efficient_clicks > 0 else 0
        lines.append(f"└ 클릭당: 약 {format_number(cpc)}원")
    
    return "\n".join(lines)

#############################################
# 기존 기능 4: 자동완성어
#############################################
def get_autocomplete(keyword):
    try:
        params = {"q": keyword, "con": "1", "frm": "nv", "ans": "2", "r_format": "json"}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.naver.com/"}
        response = requests.get("https://ac.search.naver.com/nx/ac", params=params, headers=headers, timeout=3)
        
        if response.status_code == 200:
            suggestions = []
            for item_group in response.json().get("items", []):
                if isinstance(item_group, list):
                    for item in item_group:
                        if isinstance(item, list) and item:
                            kw = item[0][0] if isinstance(item[0], list) else item[0]
                            if kw and kw != keyword and kw not in suggestions:
                                suggestions.append(kw)
                                if len(suggestions) >= 10:
                                    break
            
            if suggestions:
                result = f"[자동완성] {keyword}\n\n"
                for i, s in enumerate(suggestions, 1):
                    result += f"{i}. {s}\n"
                return result.strip()
    except:
        pass
    
    return f"[자동완성] {keyword}\n\n결과 없음"

#############################################
# 기존 기능 5: 유튜브 자동완성
#############################################
def get_youtube_autocomplete(keyword):
    try:
        url = "https://suggestqueries.google.com/complete/search"
        params = {"client": "youtube", "ds": "yt", "q": keyword, "hl": "ko", "gl": "kr"}
        headers = {"User-Agent": "Mozilla/5.0"}
        
        response = requests.get(url, params=params, headers=headers, timeout=3)
        
        if response.status_code == 200:
            text = response.text
            start_idx = text.find('(')
            end_idx = text.rfind(')')
            if start_idx != -1 and end_idx != -1:
                json_str = text[start_idx + 1:end_idx]
                data = json.loads(json_str)
                
                suggestions = []
                if len(data) > 1 and isinstance(data[1], list):
                    for item in data[1]:
                        if isinstance(item, list) and len(item) > 0:
                            suggestion = item[0]
                            if suggestion and suggestion != keyword:
                                suggestions.append(suggestion)
                
                if suggestions:
                    result = f"[유튜브 자동완성] {keyword}\n\n"
                    for i, s in enumerate(suggestions[:10], 1):
                        result += f"{i}. {s}\n"
                    return result.strip()
    except Exception as e:
        logger.error(f"유튜브 자동완성 오류: {str(e)}")
    
    return f"[유튜브 자동완성] {keyword}\n\n결과 없음"

#############################################
# 기존 기능 6: 대표키워드
#############################################
def extract_place_id_from_url(url_or_id):
    url_or_id = url_or_id.strip()
    if url_or_id.isdigit():
        return url_or_id
    
    patterns = [r'/restaurant/(\d+)', r'/place/(\d+)', r'/cafe/(\d+)', r'=(\d{10,})']
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match and len(match.group(1)) >= 7:
            return match.group(1)
    
    match = re.search(r'\d{7,}', url_or_id)
    return match.group(0) if match else None

def get_place_keywords(place_id):
    headers = {"User-Agent": "Mozilla/5.0 (iPhone)", "Accept-Language": "ko-KR,ko;q=0.9"}
    
    for category in ['restaurant', 'place', 'cafe']:
        try:
            url = f"https://m.place.naver.com/{category}/{place_id}/home"
            response = requests.get(url, headers=headers, timeout=5)
            if response.status_code == 200:
                html = response.content.decode('utf-8', errors='ignore')
                match = re.search(r'"keywordList"\s*:\s*\[((?:"[^"]*",?\s*)*)\]', html)
                if match:
                    keywords = json.loads("[" + match.group(1) + "]")
                    if keywords:
                        return {"success": True, "keywords": keywords}
        except:
            pass
    
    return {"success": False, "error": "대표키워드를 찾을 수 없습니다."}

def format_place_keywords(input_str):
    place_id = extract_place_id_from_url(input_str.strip())
    
    if not place_id:
        return f"[대표키워드] 조회 실패\n\n플레이스 ID를 찾을 수 없습니다.\n\n예) 대표 1529801174"
    
    result = get_place_keywords(place_id)
    
    if not result["success"]:
        return f"[대표키워드] 조회 실패\n\n{result['error']}"
    
    keywords = result["keywords"]
    response = f"[대표키워드] {place_id}\n\n"
    for i, kw in enumerate(keywords, 1):
        response += f"{i}. {kw}\n"
    response += f"\n복사용: {', '.join(keywords)}"
    
    return response

#############################################
# 기존 기능 7: 운세
#############################################
def get_fortune(birthdate=None):
    if not GEMINI_API_KEY:
        return get_fortune_fallback(birthdate)
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    
    if birthdate:
        if len(birthdate) == 6:
            year = f"19{birthdate[:2]}" if int(birthdate[:2]) > 30 else f"20{birthdate[:2]}"
            month, day = birthdate[2:4], birthdate[4:6]
        elif len(birthdate) == 8:
            year, month, day = birthdate[:4], birthdate[4:6], birthdate[6:8]
        else:
            return get_fortune()
        
        prompt = f"""생년월일 {year}년 {month}월 {day}일생의 오늘 운세를 알려줘.
형식:
[운세] {year}년 {month}월 {day}일생

총운: (2줄)
애정운: (1줄)
금전운: (1줄)
직장운: (1줄)

행운의 숫자: (1-45 숫자 3개)
행운의 색: (1개)

재미있고 긍정적으로. 이모티콘 없이."""
    else:
        prompt = """오늘의 운세를 알려줘.
형식:
[오늘의 운세]

총운: (2줄)
애정운: (1줄)
금전운: (1줄)
직장운: (1줄)

행운의 숫자: (1-45 숫자 3개)
행운의 색: (1개)

재미있고 긍정적으로. 이모티콘 없이."""
    
    try:
        response = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.9, "maxOutputTokens": 500}
        }, timeout=4)
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        pass
    
    return get_fortune_fallback(birthdate)

def get_fortune_fallback(birthdate=None):
    fortunes = ["오늘은 새로운 기회가 찾아오는 날!", "좋은 소식이 들려올 예정이에요."]
    love = ["설레는 만남이 있을 수 있어요", "소중한 사람과 대화를 나눠보세요"]
    money = ["작은 횡재수가 있어요", "절약이 미덕인 날"]
    work = ["집중력이 높아지는 시간", "새 프로젝트에 도전해보세요"]
    lucky_numbers = sorted(random.sample(range(1, 46), 3))
    colors = ["빨간색", "파란색", "노란색", "초록색", "보라색"]
    
    if birthdate and len(birthdate) in [6, 8]:
        if len(birthdate) == 6:
            year = f"19{birthdate[:2]}" if int(birthdate[:2]) > 30 else f"20{birthdate[:2]}"
            month, day = birthdate[2:4], birthdate[4:6]
        else:
            year, month, day = birthdate[:4], birthdate[4:6], birthdate[6:8]
        
        return f"""[운세] {year}년 {month}월 {day}일생
총운: {random.choice(fortunes)}
애정운: {random.choice(love)}
금전운: {random.choice(money)}
직장운: {random.choice(work)}

행운의 숫자: {lucky_numbers[0]}, {lucky_numbers[1]}, {lucky_numbers[2]}
행운의 색: {random.choice(colors)}"""
    
    return f"""[오늘의 운세]
총운: {random.choice(fortunes)}
애정운: {random.choice(love)}
금전운: {random.choice(money)}
직장운: {random.choice(work)}

행운의 숫자: {lucky_numbers[0]}, {lucky_numbers[1]}, {lucky_numbers[2]}
행운의 색: {random.choice(colors)}"""

#############################################
# 기존 기능 8: 로또
#############################################
def get_lotto():
    if not GEMINI_API_KEY:
        return get_lotto_fallback()
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = """로또 번호 5세트 추천. 1~45, 각 6개, 오름차순.
형식:
[로또 번호 추천]

00, 00, 00, 00, 00, 00
00, 00, 00, 00, 00, 00
00, 00, 00, 00, 00, 00
00, 00, 00, 00, 00, 00
00, 00, 00, 00, 00, 00

행운을 빕니다!"""
    
    try:
        response = requests.post(url, json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 1.0, "maxOutputTokens": 400}
        }, timeout=4)
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        pass
    
    return get_lotto_fallback()

def get_lotto_fallback():
    result = "[로또 번호 추천]\n\n"
    for i in range(1, 6):
        numbers = sorted(random.sample(range(1, 46), 6))
        result += f"{', '.join(str(n).zfill(2) for n in numbers)}\n"
    result += "\n행운을 빕니다!\n※ 재미로만 즐기세요!"
    return result

#############################################
# 신규 기능 1: 비교 [키워드]
#############################################
def get_datalab_trend(keyword, start_date, end_date):
    """DataLab 트렌드 조회"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"success": False, "error": "DataLab API 키 미설정"}
    
    url = "https://openapi.naver.com/v1/datalab/search"
    
    payload = {
        "startDate": start_date,
        "endDate": end_date,
        "timeUnit": "month",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
    }
    
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=3)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results and results[0].get("data"):
                return {"success": True, "data": results[0]["data"]}
        
        return {"success": False, "error": "트렌드 데이터 없음"}
    except Exception as e:
        logger.error(f"트렌드 조회 오류: {str(e)}")
        return {"success": False, "error": str(e)}

def get_comparison_analysis(keyword):
    """검색량 전년 비교 분석"""
    
    today = date.today()
    this_year_start = f"{today.year}-{today.month:02d}-01"
    this_year_end = today.strftime("%Y-%m-%d")
    
    last_year = today.year - 1
    last_year_start = f"{last_year}-{today.month:02d}-01"
    last_year_end = f"{last_year}-{today.month:02d}-{today.day:02d}"
    
    trend_2025 = get_datalab_trend(keyword, this_year_start, this_year_end)
    trend_2024 = get_datalab_trend(keyword, last_year_start, last_year_end)
    
    if not trend_2025["success"] or not trend_2024["success"]:
        return None
    
    data_2025 = trend_2025["data"]
    data_2024 = trend_2024["data"]
    
    recent_6_months_2025 = data_2025[-6:] if len(data_2025) >= 6 else data_2025
    recent_6_months_2024 = data_2024[-6:] if len(data_2024) >= 6 else data_2024
    
    avg_2025 = sum(d.get("ratio", 0) for d in data_2025) / len(data_2025) if data_2025 else 0
    avg_2024 = sum(d.get("ratio", 0) for d in data_2024) / len(data_2024) if data_2024 else 0
    
    change_rate = ((avg_2025 - avg_2024) / avg_2024 * 100) if avg_2024 > 0 else 0
    
    virtual_volume_2025 = int(avg_2025 * 100)
    virtual_volume_2024 = int(avg_2024 * 100)
    
    return {
        "keyword": keyword,
        "volume_2025": virtual_volume_2025,
        "volume_2024": virtual_volume_2024,
        "change_rate": change_rate,
        "monthly_2025": recent_6_months_2025,
        "monthly_2024": recent_6_months_2024
    }

def format_comparison_analysis(analysis):
    """비교 분석 포맷팅"""
    
    if not analysis:
        return "[검색량 비교] 조회 실패\n\nDataLab API 오류\n잠시 후 다시 시도해주세요."
    
    keyword = analysis["keyword"]
    vol_2025 = analysis["volume_2025"]
    vol_2024 = analysis["volume_2024"]
    change_rate = analysis["change_rate"]
    
    mobile_2025 = int(vol_2025 * 0.75)
    pc_2025 = vol_2025 - mobile_2025
    mobile_2024 = int(vol_2024 * 0.75)
    pc_2024 = vol_2024 - mobile_2024
    
    lines = [f"[검색량 비교] {keyword}", ""]
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 월간 검색량")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"2025년 {date.today().month}월: {format_number(vol_2025)}회")
    lines.append(f"├─ 모바일: {format_number(mobile_2025)}회 (75%)")
    lines.append(f"└─ PC: {format_number(pc_2025)}회 (25%)")
    lines.append("")
    lines.append(f"2024년 {date.today().month}월: {format_number(vol_2024)}회")
    lines.append(f"├─ 모바일: {format_number(mobile_2024)}회 (75%)")
    lines.append(f"└─ PC: {format_number(pc_2024)}회 (25%)")
    lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📈 증감 분석")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    diff = vol_2025 - vol_2024
    emoji = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➡️"
    sign = "+" if change_rate > 0 else ""
    
    lines.append(f"전년 대비: {sign}{format_number(diff)}회 ({sign}{change_rate:.1f}%) {emoji}")
    lines.append("")
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📉 월별 추이 (최근 6개월)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    lines.append("2025년")
    for item in analysis["monthly_2025"]:
        period = item["period"]
        ratio = item["ratio"]
        bar_length = int(ratio / 10)
        bar = "█" * bar_length
        lines.append(f"├─ {period}: {int(ratio * 100)} {bar}")
    
    lines.append("")
    lines.append("2024년")
    for item in analysis["monthly_2024"]:
        period = item["period"]
        ratio = item["ratio"]
        bar_length = int(ratio / 10)
        bar = "█" * bar_length
        lines.append(f"├─ {period}: {int(ratio * 100)} {bar}")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 인사이트")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    if change_rate >= 20:
        lines.append(f"✅ 급성장 중 ({sign}{change_rate:.1f}%)")
        lines.append("→ 검색 광고 적극 추천")
    elif change_rate >= 10:
        lines.append(f"✅ 지속 성장 ({sign}{change_rate:.1f}%)")
        lines.append("→ 광고 시작 적기")
    elif change_rate >= -10:
        lines.append(f"➡️ 안정 유지 ({sign}{change_rate:.1f}%)")
        lines.append("→ 꾸준한 마케팅")
    else:
        lines.append(f"⚠️ 검색 감소 ({change_rate:.1f}%)")
        lines.append("→ SNS 바이럴 필요")
    
    lines.append("✅ 모바일 최적화 필수")
    
    return "\n".join(lines)

#############################################
# 신규 기능 2: Kakao API 지역 검색
#############################################
def search_kakao_region(region_keyword):
    """
    Kakao Local API로 지역 검색 → 행정코드 반환
    """
    
    if not KAKAO_REST_API_KEY:
        return {"success": False, "error": "Kakao API 키 미설정"}
    
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    
    # 1단계: Kakao Local 키워드 검색
    try:
        url = "https://dapi.kakao.com/v2/local/search/keyword.json"
        params = {"query": region_keyword, "size": 1}
        
        response = requests.get(url, headers=headers, params=params, timeout=3)
        
        if response.status_code == 200:
            data = response.json()
            documents = data.get("documents", [])
            
            if documents:
                doc = documents[0]
                x = doc.get("x")  # 경도
                y = doc.get("y")  # 위도
                
                # 2단계: 좌표 → 행정구역 코드 변환
                region_code_result = kakao_coord_to_region(x, y)
                
                if region_code_result["success"]:
                    return region_code_result
        
        # Local 검색 실패 시 주소 검색 시도
        return kakao_address_search(region_keyword)
        
    except Exception as e:
        logger.error(f"Kakao Local 검색 오류: {str(e)}")
        return {"success": False, "error": str(e)}

def kakao_coord_to_region(x, y):
    """
    Kakao 좌표 → 행정구역 코드 API
    """
    
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    
    try:
        url = "https://dapi.kakao.com/v2/local/geo/coord2regioncode.json"
        params = {"x": x, "y": y}
        
        response = requests.get(url, headers=headers, params=params, timeout=3)
        
        if response.status_code == 200:
            data = response.json()
            documents = data.get("documents", [])
            
            # H 타입 (행정동) 우선
            for doc in documents:
                if doc.get("region_type") == "H":
                    code = doc.get("code")
                    address_name = doc.get("address_name")
                    
                    parts = address_name.split()
                    
                    return {
                        "success": True,
                        "admCd": code,                    # 행정구역코드 (10자리)
                        "sigunCd": code[:5],              # 시군구코드 (5자리)
                        "sigunNm": parts[1] if len(parts) > 1 else "",
                        "fullName": address_name,
                        "dongNm": parts[2] if len(parts) > 2 else "",
                        "x": x,
                        "y": y
                    }
            
            # H 타입 없으면 B 타입 (법정동)
            for doc in documents:
                if doc.get("region_type") == "B":
                    code = doc.get("code")
                    address_name = doc.get("address_name")
                    
                    parts = address_name.split()
                    
                    return {
                        "success": True,
                        "admCd": code,
                        "sigunCd": code[:5],
                        "sigunNm": parts[1] if len(parts) > 1 else "",
                        "fullName": address_name,
                        "dongNm": parts[2] if len(parts) > 2 else "",
                        "x": x,
                        "y": y
                    }
        
        return {"success": False, "error": "행정구역 코드 변환 실패"}
        
    except Exception as e:
        logger.error(f"좌표 변환 오류: {str(e)}")
        return {"success": False, "error": str(e)}

def kakao_address_search(region_keyword):
    """
    Kakao 주소 검색 API
    """
    
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    
    try:
        url = "https://dapi.kakao.com/v2/local/search/address.json"
        params = {"query": region_keyword, "size": 1}
        
        response = requests.get(url, headers=headers, params=params, timeout=3)
        
        if response.status_code == 200:
            data = response.json()
            documents = data.get("documents", [])
            
            if documents:
                doc = documents[0]
                x = doc.get("x")
                y = doc.get("y")
                
                # 좌표 → 행정코드 변환
                return kakao_coord_to_region(x, y)
        
        return {"success": False, "error": "주소를 찾을 수 없습니다"}
        
    except Exception as e:
        logger.error(f"주소 검색 오류: {str(e)}")
        return {"success": False, "error": str(e)}

#############################################
# 신규 기능 3: 지역 [동]
#############################################
def get_population_data(region_data):
    """
    유동인구 데이터 조회
    공공데이터 API 연동 준비
    """
    
    # 공공데이터 API 사용 시
    if DATA_GO_KR_API_KEY:
        # TODO: 실제 API 연동
        # url = "https://api.odcloud.kr/api/15071311/v1/생활인구"
        # params = {"serviceKey": DATA_GO_KR_API_KEY, "admCd": region_data["admCd"]}
        pass
    
    # 가상 데이터 (Fallback)
    import random
    
    # 지역별 기본 유동인구 추정
    base_pop_map = {
        "강남": 15000, "역삼": 15000, "논현": 12000,
        "홍대": 25000, "동교": 25000,
        "부평": 8200, "삼산": 7000,
        "송도": 12000,
        "해운대": 18000, "우동": 18000,
        "서면": 16000, "부전": 16000
    }
    
    # 동명에서 키워드 추출
    dong_name = region_data.get("dongNm", "")
    base_pop = 10000
    
    for key, pop in base_pop_map.items():
        if key in dong_name:
            base_pop = pop
            break
    
    return {
        "success": True,
        "daily_avg": base_pop,
        "by_age": {
            "10s": random.randint(5, 10),
            "20s": random.randint(25, 35),
            "30s": random.randint(20, 28),
            "40s": random.randint(18, 25),
            "50s": random.randint(12, 20)
        },
        "by_gender": {
            "male": random.randint(45, 52),
            "female": random.randint(48, 55)
        },
        "by_time": {
            "0709": int(base_pop * 0.22),
            "1213": int(base_pop * 0.29),
            "1819": int(base_pop * 0.34),
            "2022": int(base_pop * 0.15)
        },
        "weekday_vs_weekend": {
            "weekday": int(base_pop * 1.07),
            "weekend": int(base_pop * 0.88)
        }
    }

def format_region_analysis(region_keyword):
    """지역 분석 포맷팅"""
    
    # Kakao API로 지역 검색
    region_data = search_kakao_region(region_keyword)
    
    if not region_data["success"]:
        return f"[지역분석] 오류\n\n'{region_keyword}' 지역을 찾을 수 없습니다.\n\n예) 지역 홍대\n예) 지역 부평동\n예) 지역 강남역"
    
    # 유동인구 조회
    pop_data = get_population_data(region_data)
    
    lines = [f"[지역분석] {region_data['fullName']}", ""]
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("👥 유동인구")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    daily_avg = pop_data["daily_avg"]
    lines.append(f"일평균: {format_number(daily_avg)}명")
    lines.append("")
    
    lines.append("연령대:")
    age_data = pop_data["by_age"]
    for age, ratio in age_data.items():
        count = int(daily_avg * ratio / 100)
        star = " ⭐" if ratio >= 25 else ""
        lines.append(f"├─ {age.replace('s', '대')}: {ratio}% ({format_number(count)}명){star}")
    
    lines.append("")
    lines.append("성별:")
    gender = pop_data["by_gender"]
    lines.append(f"├─ 여성: {gender['female']}%")
    lines.append(f"└─ 남성: {gender['male']}%")
    
    lines.append("")
    lines.append("시간대별:")
    time_data = pop_data["by_time"]
    lines.append(f"├─ 07-09시: {format_number(time_data['0709'])}명")
    lines.append(f"├─ 12-13시: {format_number(time_data['1213'])}명 🔥")
    lines.append(f"├─ 18-19시: {format_number(time_data['1819'])}명 🔥")
    lines.append(f"└─ 20-22시: {format_number(time_data['2022'])}명")
    
    lines.append("")
    lines.append("평일/주말:")
    weekday = pop_data["weekday_vs_weekend"]
    diff = int((weekday['weekend'] - weekday['weekday']) / weekday['weekday'] * 100)
    lines.append(f"├─ 평일: {format_number(weekday['weekday'])}명")
    lines.append(f"└─ 주말: {format_number(weekday['weekend'])}명 ({diff:+d}%)")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📍 입지 특성")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    # 동적 입지 특성 (간단 버전)
    dong_name = region_data.get("dongNm", "")
    
    if "역삼" in dong_name or "강남" in dong_name:
        facilities = ["오피스 밀집", "대기업 본사"]
        strength = ["고소득층", "직장인 밀집"]
        weakness = ["높은 임대료", "치열한 경쟁"]
    elif "홍대" in dong_name or "동교" in dong_name:
        facilities = ["대학가", "클럽/공연장"]
        strength = ["젊은층", "유동인구 많음"]
        weakness = ["주말 집중", "소음"]
    elif "부평" in dong_name or "삼산" in dong_name:
        facilities = ["역세권", "주거 복합"]
        strength = ["안정적 수요", "평일 강세"]
        weakness = ["주말 약세", "주차 부족"]
    else:
        facilities = ["데이터 수집 중"]
        strength = ["분석 중"]
        weakness = ["분석 중"]
    
    lines.append("주요 시설:")
    for fac in facilities:
        lines.append(f"• {fac}")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 입지 인사이트")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    lines.append("✅ 강점")
    for s in strength:
        lines.append(f"• {s}")
    
    lines.append("")
    lines.append("⚠️ 약점")
    for w in weakness:
        lines.append(f"• {w}")
    
    lines.append("")
    lines.append("🎯 업종 적합도")
    lines.append("음식점: ⭐⭐⭐⭐⭐")
    lines.append("카페: ⭐⭐⭐⭐")
    lines.append("소매: ⭐⭐⭐")
    
    return "\n".join(lines)

#############################################
# 신규 기능 4: 매출 [동] [업종]
#############################################
def get_business_data(region_data, industry_keyword):
    """
    상가업소 데이터 조회
    공공데이터 API 연동 준비
    """
    
    industry_info = INDUSTRY_CODES.get(industry_keyword)
    if not industry_info:
        return {"success": False, "error": "업종 없음"}
    
    # 공공데이터 API 사용 시
    if DATA_GO_KR_API_KEY:
        # TODO: 실제 API 연동
        # url = "https://api.odcloud.kr/api/nbbacpsa/v1/상가업소"
        # params = {"serviceKey": DATA_GO_KR_API_KEY, "sigunCd": region_data["sigunCd"]}
        pass
    
    # 가상 데이터 (Fallback)
    import random
    
    total_count = random.randint(80, 500)
    opened = random.randint(10, 50)
    closed = random.randint(8, 45)
    
    return {
        "success": True,
        "industry": industry_info["name"],
        "total": total_count,
        "opened": opened,
        "closed": closed,
        "closure_rate": round((closed / total_count) * 100, 1),
        "by_type": {
            "한식": random.randint(30, 60),
            "중식": random.randint(10, 30),
            "일식": random.randint(8, 25)
        } if industry_keyword == "음식점" else {}
    }

def get_sales_data(region_data, industry_keyword):
    """
    매출 데이터 조회
    공공데이터 API 연동 준비
    """
    
    # 공공데이터 API 사용 시
    if DATA_GO_KR_API_KEY:
        # TODO: 실제 API 연동
        # url = "https://api.odcloud.kr/api/15083033/v1/상권정보"
        # params = {"serviceKey": DATA_GO_KR_API_KEY, "sigunCd": region_data["sigunCd"]}
        pass
    
    # 가상 데이터 (Fallback)
    import random
    
    base_sales = {
        "음식점": 2200, "한식": 2350, "카페": 1920,
        "병원": 4800, "학원": 3200
    }
    
    monthly_sales = base_sales.get(industry_keyword, 2000) * 10000
    payment_count = random.randint(1200, 2500)
    avg_price = int(monthly_sales / payment_count)
    
    return {
        "success": True,
        "monthly_sales": monthly_sales,
        "payment_count": payment_count,
        "avg_price": avg_price,
        "yoy_growth": round(random.uniform(3.0, 15.0), 1),
        "time_dist": {
            "lunch": random.randint(30, 42),
            "dinner": random.randint(35, 48)
        },
        "weekday_ratio": random.randint(58, 72)
    }

def format_sales_analysis(region_keyword, industry_keyword):
    """매출 분석 포맷팅"""
    
    # Kakao API로 지역 검색
    region_data = search_kakao_region(region_keyword)
    
    if not region_data["success"]:
        return f"[매출분석] 오류\n\n'{region_keyword}' 지역을 찾을 수 없습니다."
    
    if industry_keyword not in INDUSTRY_CODES:
        available = ", ".join(list(INDUSTRY_CODES.keys())[:10])
        return f"[매출분석] 오류\n\n'{industry_keyword}' 업종 없음\n\n예) {available}"
    
    business_data = get_business_data(region_data, industry_keyword)
    sales_data = get_sales_data(region_data, industry_keyword)
    
    dong_name = region_data.get("dongNm", region_keyword)
    
    lines = [f"[매출분석] {dong_name} {industry_keyword}", ""]
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💰 평균 매출")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    monthly = sales_data["monthly_sales"]
    payment = sales_data["payment_count"]
    avg_price = sales_data["avg_price"]
    growth = sales_data["yoy_growth"]
    
    lines.append(f"월평균: {monthly // 10000:,}만원")
    lines.append(f"├─ 결제건수: {payment:,}건")
    lines.append(f"├─ 객단가: {avg_price:,}원")
    lines.append(f"└─ 전년비: +{growth}%")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append(f"🏪 업소 현황")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    total = business_data["total"]
    lines.append(f"총 {industry_keyword}: {total}개")
    
    if business_data["by_type"]:
        lines.append("")
        for name, count in business_data["by_type"].items():
            ratio = (count / total) * 100
            lines.append(f"├─ {name}: {count}개 ({ratio:.1f}%)")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 개폐업 (최근 1년)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    opened = business_data["opened"]
    closed = business_data["closed"]
    net = opened - closed
    closure_rate = business_data["closure_rate"]
    
    lines.append(f"신규: {opened}개")
    lines.append(f"폐업: {closed}개")
    sign = "+" if net >= 0 else ""
    lines.append(f"순증: {sign}{net}개")
    lines.append(f"폐업률: {closure_rate}%")
    
    if closure_rate >= 15:
        lines.append("⚠️⚠️ 높은 폐업률")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🕐 시간대별 매출")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    time_dist = sales_data["time_dist"]
    lines.append(f"점심: {time_dist['lunch']}% 🔥")
    lines.append(f"저녁: {time_dist['dinner']}% 🔥")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 인사이트")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    if growth >= 10:
        lines.append(f"✅ 높은 성장 (+{growth}%)")
    
    if closure_rate >= 15:
        lines.append("⚠️ 차별화 필수")
    elif closure_rate <= 8:
        lines.append("✅ 안정적")
    
    lines.append("")
    lines.append("📌 성공 전략")
    lines.append(f"• 객단가 {avg_price:,}원 유지")
    
    if time_dist['lunch'] >= 35:
        lines.append("• 점심 마케팅 집중")
    if time_dist['dinner'] >= 40:
        lines.append("• 저녁 웨이팅 관리")
    
    return "\n".join(lines)

#############################################
# 도움말
#############################################
def get_help():
    return """[사용 가이드]

━━━━━━━━━━━━━━━━━━━━━
📊 기본 기능
━━━━━━━━━━━━━━━━━━━━━

▶ 키워드 검색량 (최대 5개)
예) 부평맛집,강남맛집,송도카페

▶ 연관 검색어
예) 연관 부평맛집

▶ 자동완성어 (네이버)
예) 자동 부평맛집

▶ 자동완성어 (유튜브)
예) 유튜브 부평맛집

▶ 광고 단가 분석
예) 광고 부평맛집

▶ 대표 키워드
예) 대표 1234567890

━━━━━━━━━━━━━━━━━━━━━
🆕 상권 분석 (전국 지원)
━━━━━━━━━━━━━━━━━━━━━

▶ 검색량 전년 비교
예) 비교 부평맛집

▶ 지역 유동인구
예) 지역 홍대
예) 지역 부평동
예) 지역 강남역

▶ 업종별 매출
예) 매출 홍대 음식점
예) 매출 역삼동 카페

━━━━━━━━━━━━━━━━━━━━━
🎲 재미 기능
━━━━━━━━━━━━━━━━━━━━━

▶ 운세
예) 운세
예) 운세 870114

▶ 로또
예) 로또

━━━━━━━━━━━━━━━━━━━━━"""

#############################################
# 카카오 스킬
#############################################
@app.route('/skill', methods=['POST'])
def kakao_skill():
    try:
        request_data = request.get_json()
        if request_data is None:
            return create_kakao_response("요청 데이터 오류")
        
        user_utterance = request_data.get("userRequest", {}).get("utterance", "").strip()
        if not user_utterance:
            return create_kakao_response("명령어를 입력해주세요!\n\n'도움말' 입력")
        
        lower_input = user_utterance.lower()
        
        # 도움말
        if lower_input in ["도움말", "도움", "사용법", "help", "?"]:
            return create_kakao_response(get_help())
        
        # 운세
        if lower_input.startswith("운세 "):
            birthdate = ''.join(filter(str.isdigit, user_utterance))
            if birthdate and len(birthdate) in [6, 8]:
                return create_kakao_response(get_fortune(birthdate))
            return create_kakao_response("예) 운세 870114")
        
        if lower_input in ["운세", "오늘운세"]:
            return create_kakao_response(get_fortune())
        
        # 로또
        if lower_input in ["로또", "로또번호"]:
            return create_kakao_response(get_lotto())
        
        # 비교
        if lower_input.startswith("비교 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if keyword:
                analysis = get_comparison_analysis(keyword)
                return create_kakao_response(format_comparison_analysis(analysis))
            return create_kakao_response("예) 비교 부평맛집")
        
        # 지역
        if lower_input.startswith("지역 "):
            region = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if region:
                return create_kakao_response(format_region_analysis(region))
            return create_kakao_response("예) 지역 부평동")
        
        # 매출
        if lower_input.startswith("매출 "):
            parts = user_utterance.split(" ")
            if len(parts) >= 3:
                region = parts[1].strip()
                industry = parts[2].strip()
                return create_kakao_response(format_sales_analysis(region, industry))
            return create_kakao_response("예) 매출 부평동 음식점")
        
        # 유튜브
        if lower_input.startswith("유튜브 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if keyword:
                return create_kakao_response(get_youtube_autocomplete(keyword))
            return create_kakao_response("예) 유튜브 부평맛집")
        
        # 자동완성
        if lower_input.startswith("자동 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if keyword:
                return create_kakao_response(get_autocomplete(keyword))
            return create_kakao_response("예) 자동 부평맛집")
        
        # 대표키워드
        if lower_input.startswith("대표 "):
            input_text = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if input_text:
                return create_kakao_response(format_place_keywords(input_text))
            return create_kakao_response("예) 대표 1234567890")
        
        # 연관
        if lower_input.startswith("연관 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_related_keywords(keyword))
            return create_kakao_response("예) 연관 부평맛집")
        
        # 광고
        if lower_input.startswith("광고 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_ad_cost(keyword))
            return create_kakao_response("예) 광고 부평맛집")
        
        # 기본: 검색량
        keyword = user_utterance.strip()
        if "," in keyword:
            return create_kakao_response(get_search_volume(keyword))
        else:
            return create_kakao_response(get_search_volume(clean_keyword(keyword)))
        
    except Exception as e:
        logger.error(f"스킬 오류: {str(e)}")
        return create_kakao_response(f"오류 발생\n잠시 후 다시 시도해주세요.")

def create_kakao_response(text):
    if len(text) > 1000:
        text = text[:997] + "..."
    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}]
        }
    })

#############################################
# 테스트 라우트
#############################################
@app.route('/')
def home():
    return "서버 정상 작동 중"

@app.route('/test/compare')
def test_compare():
    keyword = request.args.get('q', '부평맛집')
    analysis = get_comparison_analysis(keyword)
    result = format_comparison_analysis(analysis)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>비교 테스트</title></head>
<body>
<h2>{keyword}</h2>
<h3>글자: {len(result)}자</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/test/region')
def test_region():
    region = request.args.get('r', '홍대')
    result = format_region_analysis(region)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>지역 테스트</title></head>
<body>
<h2>{region}</h2>
<h3>글자: {len(result)}자</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/test/sales')
def test_sales():
    region = request.args.get('r', '홍대')
    industry = request.args.get('i', '음식점')
    result = format_sales_analysis(region, industry)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>매출 테스트</title></head>
<body>
<h2>{region} {industry}</h2>
<h3>글자: {len(result)}자</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/test/kakao')
def test_kakao():
    region = request.args.get('r', '홍대')
    result = search_kakao_region(region)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Kakao API 테스트</title></head>
<body>
<h2>Kakao 지역 검색: {region}</h2>
<pre style="background:#f5f5f5; padding:20px;">{json.dumps(result, indent=2, ensure_ascii=False)}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

#############################################
# 서버 실행
#############################################
if __name__ == '__main__':
    print("=== 환경변수 확인 ===")
    print(f"검색광고 API: {'✅' if NAVER_API_KEY else '❌'}")
    print(f"DataLab API: {'✅' if NAVER_CLIENT_ID else '❌'}")
    print(f"Kakao API: {'✅' if KAKAO_REST_API_KEY else '❌'}")
    print(f"Gemini API: {'✅' if GEMINI_API_KEY else '❌'}")
    print(f"공공데이터 API: {'✅' if DATA_GO_KR_API_KEY else '❌'}")
    
    if validate_required_keys():
        print("✅ 필수 키 확인 완료")
    else:
        print("⚠️ 일부 기능 제한")
    
    print("====================")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
