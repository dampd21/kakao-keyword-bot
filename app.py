from flask import Flask, request, jsonify
import hashlib
import hmac
import base64
import time
import requests
import os

app = Flask(__name__)

# 환경변수
NAVER_API_KEY = os.environ.get('NAVER_API_KEY', '')
NAVER_SECRET_KEY = os.environ.get('NAVER_SECRET_KEY', '')
NAVER_CUSTOMER_ID = os.environ.get('NAVER_CUSTOMER_ID', '')

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

def get_naver_api_headers():
    """네이버 API 헤더 생성"""
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
    """네이버 API에서 키워드 데이터 전체 가져오기"""
    
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
💡 연관 키워드: "연관 {keyword}"
💰 광고 단가: "광고 {keyword}"
📝 블로그 주제: "블로그 {keyword}" """

#############################################
# 기능 2: 연관 키워드 조회
#############################################
def get_related_keywords(keyword):
    """연관 키워드 5개 조회"""
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"❌ 조회 실패\n{result['error']}"
    
    keyword_list = result["data"][:6]  # 최대 6개 (첫번째는 원본)
    
    response = f"""🔗 "{keyword}" 연관 키워드

"""
    
    for i, kw in enumerate(keyword_list, 1):
        name = kw.get("relKeyword", "")
        pc = parse_count(kw.get("monthlyPcQcCnt"))
        mobile = parse_count(kw.get("monthlyMobileQcCnt"))
        total = pc + mobile
        
        response += f"{i}. {name}\n   📊 월간 {format_number(total)}회\n\n"
    
    response += """━━━━━━━━━━━━━━━━
💡 상세 검색량: 키워드만 입력"""
    
    return response

#############################################
# 기능 3: 광고 단가 조회
#############################################
def get_ad_cost(keyword):
    """광고 단가 정보 조회"""
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"❌ 조회 실패\n{result['error']}"
    
    kw = result["data"][0]
    
    # 광고 관련 데이터 추출
    pc_click = kw.get("monthlyAvePcClkCnt", 0)
    mobile_click = kw.get("monthlyAveMobileClkCnt", 0)
    pc_ctr = kw.get("monthlyAvePcCtr", 0)
    mobile_ctr = kw.get("monthlyAveMobileCtr", 0)
    comp = kw.get("compIdx", "정보없음")
    
    # 경쟁도에 따른 예상 단가 (대략적 추정)
    if comp == "높음":
        estimated_cpc = "500~2,000원"
        difficulty = "🔴 진입 어려움"
    elif comp == "중간":
        estimated_cpc = "200~500원"
        difficulty = "🟡 보통"
    else:
        estimated_cpc = "50~200원"
        difficulty = "🟢 진입 쉬움"
    
    # 클릭률 포맷팅
    pc_ctr_str = f"{pc_ctr:.2f}%" if isinstance(pc_ctr, (int, float)) else str(pc_ctr)
    mobile_ctr_str = f"{mobile_ctr:.2f}%" if isinstance(mobile_ctr, (int, float)) else str(mobile_ctr)
    
    return f"""💰 "{kw.get('relKeyword', keyword)}" 광고 분석

📈 경쟁도: {comp}
{difficulty}

💵 예상 클릭 단가
{estimated_cpc}

📊 평균 클릭률 (CTR)
📱 모바일: {mobile_ctr_str}
💻 PC: {pc_ctr_str}

🖱️ 월평균 클릭수
📱 모바일: {format_number(int(mobile_click))}회
💻 PC: {format_number(int(pc_click))}회

━━━━━━━━━━━━━━━━
⚠️ 실제 단가는 입찰 상황에 따라 다를 수 있습니다."""

#############################################
# 기능 4: 블로그 주제 추천
#############################################
def get_blog_topics(keyword):
    """블로그 주제 추천"""
    result = get_keyword_data(keyword)
    
    if not result["success"]:
        return f"❌ 조회 실패\n{result['error']}"
    
    keyword_list = result["data"][:10]
    
    # 검색량 기준 정렬 및 필터링
    topics = []
    for kw in keyword_list:
        name = kw.get("relKeyword", "")
        pc = parse_count(kw.get("monthlyPcQcCnt"))
        mobile = parse_count(kw.get("monthlyMobileQcCnt"))
        total = pc + mobile
        comp = kw.get("compIdx", "")
        
        topics.append({
            "name": name,
            "total": total,
            "comp": comp
        })
    
    response = f"""📝 "{keyword}" 블로그 주제 추천

🎯 추천 글감 TOP 5

"""
    
    for i, topic in enumerate(topics[:5], 1):
        # 경쟁도 이모지
        if topic["comp"] == "높음":
            comp_emoji = "🔴"
        elif topic["comp"] == "중간":
            comp_emoji = "🟡"
        else:
            comp_emoji = "🟢"
        
        response += f"""{i}. {topic['name']}
   📊 {format_number(topic['total'])}회 {comp_emoji}

"""
    
    response += """━━━━━━━━━━━━━━━━
💡 TIP: 🟢 경쟁 낮은 키워드가
   상위 노출에 유리해요!"""
    
    return response

#############################################
# 도움말
#############################################
def get_help():
    return """📖 키워드 도구 사용법

🔍 검색량 조회
   → 키워드만 입력
   예: 맛집

🔗 연관 키워드
   → "연관" + 키워드
   예: 연관 맛집

💰 광고 단가
   → "광고" + 키워드
   예: 광고 맛집

📝 블로그 주제
   → "블로그" + 키워드
   예: 블로그 맛집

━━━━━━━━━━━━━━━━
💡 아무 키워드나 입력해보세요!"""

#############################################
# 라우트
#############################################
@app.route('/')
def home():
    api_key_preview = NAVER_API_KEY[:4] + "..." if NAVER_API_KEY else "없음"
    secret_preview = NAVER_SECRET_KEY[:4] + "..." if NAVER_SECRET_KEY else "없음"
    customer_id = NAVER_CUSTOMER_ID if NAVER_CUSTOMER_ID else "없음"
    
    return f"""
    ✅ 서버 정상 작동 중!<br><br>
    환경변수 확인:<br>
    - API_KEY: {api_key_preview}<br>
    - SECRET_KEY: {secret_preview}<br>
    - CUSTOMER_ID: {customer_id}<br><br>
    <a href="/test?keyword=맛집">테스트하기</a>
    """

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
        <p>📈 경쟁도: {kw.get('compIdx', '정보없음')}</p>
        """
    else:
        return f"<h2>❌ 조회 실패</h2><p>{result['error']}</p>"

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
        if lower_input in ["도움말", "도움", "사용법", "help", "?"]:
            response_text = get_help()
        
        # 연관 키워드
        elif lower_input.startswith("연관 ") or lower_input.startswith("연관키워드 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_related_keywords(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예: 연관 맛집"
        
        # 광고 단가
        elif lower_input.startswith("광고 ") or lower_input.startswith("광고단가 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_ad_cost(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예: 광고 맛집"
        
        # 블로그 주제
        elif lower_input.startswith("블로그 ") or lower_input.startswith("블로그주제 "):
            keyword = user_utterance.split(" ", 1)[1] if " " in user_utterance else ""
            if keyword:
                response_text = get_blog_topics(keyword)
            else:
                response_text = "❌ 키워드를 입력해주세요\n예: 블로그 맛집"
        
        # 기본: 검색량 조회
        else:
            response_text = get_search_volume(user_utterance)
        
        return create_kakao_response(response_text)
        
    except Exception as e:
        return create_kakao_response(f"서버 오류: {str(e)}")

def create_kakao_response(text):
    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [{"simpleText": {"text": text}}]
        }
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
