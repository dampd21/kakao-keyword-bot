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
    emojis = ["[A]", "[B]", "[C]", "[D]", "[E]"]
    
    for emoji in emojis:
        numbers = random.sample(range(1, 46), 6)
        numbers.sort()
        numbers_str = ", ".join(str(n).zfill(2) for n in numbers)
        result += f"{emoji} {numbers_str}\n"
    
    result += """
━━━━━━━━━━━━━━━━
🍀 행운을 빕니다!

⚠️ 로또로 인생대박 나세요!"""
    
    return result


#############################################
# 기능 7: 대표키워드 조회 (네이버 플레이스)
#############################################
def get_place_keywords(place_id):
    """네이버 플레이스 대표키워드 추출"""
    
    url = f"https://m.place.naver.com/restaurant/{place_id}/home?entry=pll"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.encoding = 'utf-8'  # 인코딩 명시적 설정
        
        if response.status_code == 200:
            html = response.text
            
            # keywordList 찾기 (유니코드 이스케이프 처리)
            pattern = r'"keywordList"\s*:\s*\[(.*?)\]'
            match = re.search(pattern, html)
            
            if match:
                keywords_raw = match.group(1)
                
                # 유니코드 이스케이프 시퀀스 디코딩
                try:
                    # \\uXXXX 형태를 실제 유니코드로 변환
                    keywords_decoded = keywords_raw.encode('utf-8').decode('unicode_escape')
                except:
                    keywords_decoded = keywords_raw
                
                # 따옴표 안의 내용 추출
                keywords = re.findall(r'"([^"]+)"', keywords_decoded)
                
                # 여전히 깨진 경우 다른 방법 시도
                if not keywords or any(ord(c) > 0xFFFF for kw in keywords for c in kw if len(kw) > 0):
                    # JSON 파싱 방식 시도
                    import json
                    try:
                        keywords_json = f'[{keywords_raw}]'
                        keywords = json.loads(keywords_json)
                    except:
                        pass
                
                if keywords and len(keywords) > 0:
                    # 최종 정리 (빈 문자열 제거)
                    keywords = [kw.strip() for kw in keywords if kw.strip()]
                    
                    if keywords:
                        return {
                            "success": True,
                            "place_id": place_id,
                            "keywords": keywords
                        }
            
            return {
                "success": False,
                "error": "대표키워드를 찾을 수 없습니다.\n\n가능한 원인:\n• 잘못된 플레이스 ID\n• 음식점이 아닌 업종\n• 대표키워드 미등록 업체"
            }
        
        elif response.status_code == 404:
            return {
                "success": False,
                "error": "존재하지 않는 플레이스 ID입니다."
            }
        else:
            return {
                "success": False,
                "error": f"페이지 조회 실패 (코드: {response.status_code})"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": f"오류 발생: {str(e)}"
        }


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

💰 광고 단가
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
