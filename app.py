from flask import Flask, request, jsonify
import hashlib
import hmac
import base64
import time
import requests
import os
import urllib.parse

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

def get_naver_keyword_stats(keyword):
    """네이버 검색광고 API 호출"""
    
    if not NAVER_API_KEY or not NAVER_SECRET_KEY or not NAVER_CUSTOMER_ID:
        return {"success": False, "error": "API 키가 설정되지 않았습니다."}
    
    # API 설정 (공식 문서 기준)
    base_url = "https://api.searchad.naver.com"
    uri = "/keywordstool"
    method = "GET"
    
    # 타임스탬프
    timestamp = str(int(time.time() * 1000))
    
    # 시그니처 생성
    message = f"{timestamp}.{method}.{uri}"
    signature = hmac.new(
        NAVER_SECRET_KEY.encode('utf-8'),
        message.encode('utf-8'),
        hashlib.sha256
    ).digest()
    signature_base64 = base64.b64encode(signature).decode('utf-8')
    
    # 헤더
    headers = {
        "X-Timestamp": timestamp,
        "X-API-KEY": NAVER_API_KEY,
        "X-Customer": str(NAVER_CUSTOMER_ID),
        "X-Signature": signature_base64
    }
    
    # 파라미터 - siteId 추가
    params = {
        "hintKeywords": keyword,
        "showDetail": "1"
    }
    
    # 전체 URL
    full_url = base_url + uri
    
    try:
        response = requests.get(full_url, headers=headers, params=params, timeout=10)
        
        # 디버그 정보
        debug_info = f"""
        Status: {response.status_code}
        URL: {response.url}
        Response: {response.text[:500]}
        """
        
        if response.status_code == 200:
            data = response.json()
            keyword_list = data.get("keywordList", [])
            
            if keyword_list:
                kw = keyword_list[0]
                pc = parse_count(kw.get("monthlyPcQcCnt"))
                mobile = parse_count(kw.get("monthlyMobileQcCnt"))
                
                return {
                    "success": True,
                    "keyword": kw.get("relKeyword", keyword),
                    "pc": pc,
                    "mobile": mobile,
                    "total": pc + mobile,
                    "competition": kw.get("compIdx", "정보없음")
                }
            else:
                return {"success": False, "error": "검색 결과가 없습니다."}
        else:
            return {"success": False, "error": f"코드 {response.status_code}: {response.text}"}
            
    except Exception as e:
        return {"success": False, "error": f"예외 발생: {str(e)}"}

@app.route('/')
def home():
    # 환경변수 확인 (앞 4자리만 표시)
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
    result = get_naver_keyword_stats(keyword)
    
    if result["success"]:
        return f"""
        <h2>🔍 "{result['keyword']}" 검색량</h2>
        <p>📊 월간 총: {format_number(result['total'])}회</p>
        <p>📱 모바일: {format_number(result['mobile'])}회</p>
        <p>💻 PC: {format_number(result['pc'])}회</p>
        <p>📈 경쟁도: {result['competition']}</p>
        """
    else:
        return f"""
        <h2>❌ 조회 실패</h2>
        <p style="color:red; white-space:pre-wrap;">{result['error']}</p>
        """

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
        
        result = get_naver_keyword_stats(user_utterance)
        
        if result["success"]:
            response_text = f"""🔍 "{result['keyword']}" 검색량

📊 월간 총: {format_number(result['total'])}회
📱 모바일: {format_number(result['mobile'])}회
💻 PC: {format_number(result['pc'])}회
📈 경쟁도: {result['competition']}"""
        else:
            response_text = f"❌ 조회 실패\n{result['error']}"
        
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
