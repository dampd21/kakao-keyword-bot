from flask import Flask, request, jsonify
import hashlib
import hmac
import base64
import time
import requests
import os

app = Flask(__name__)

#############################################
# 네이버 API 설정 (환경변수에서 가져옴)
#############################################
NAVER_API_KEY = os.environ.get('NAVER_API_KEY', '')
NAVER_SECRET_KEY = os.environ.get('NAVER_SECRET_KEY', '')
NAVER_CUSTOMER_ID = os.environ.get('NAVER_CUSTOMER_ID', '')

#############################################
# 유틸리티 함수
#############################################
def format_number(num):
    """숫자에 콤마 추가"""
    if isinstance(num, int):
        return "{:,}".format(num)
    return str(num)

def parse_count(value):
    """검색량 숫자 파싱"""
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
# 네이버 키워드 API 호출
#############################################
def get_naver_keyword_stats(keyword):
    """네이버 검색광고 API로 키워드 검색량 조회"""
    
    # API 설정 확인
    if not NAVER_API_KEY or not NAVER_SECRET_KEY or not NAVER_CUSTOMER_ID:
        return {
            "success": False,
            "error": "API 키가 설정되지 않았습니다."
        }
    
    # API URL
    base_url = "https://api.naver.com"
    uri = "/keywordstool"
    url = base_url + uri
    method = "GET"
    
    # 타임스탬프
    timestamp = str(int(time.time() * 1000))
    
    # 시그니처 생성
    message = f"{timestamp}.{method}.{uri}"
    signing_key = NAVER_SECRET_KEY.encode('utf-8')
    message_bytes = message.encode('utf-8')
    signature = hmac.new(signing_key, message_bytes, hashlib.sha256).digest()
    signature_base64 = base64.b64encode(signature).decode('utf-8')
    
    # 요청 헤더
    headers = {
        "Content-Type": "application/json; charset=UTF-8",
        "X-Timestamp": timestamp,
        "X-API-KEY": NAVER_API_KEY,
        "X-Customer": str(NAVER_CUSTOMER_ID),
        "X-Signature": signature_base64
    }
    
    # 요청 파라미터
    params = {
        "hintKeywords": keyword,
        "showDetail": "1"
    }
    
    try:
        # API 호출
        response = requests.get(url, headers=headers, params=params, timeout=10)
        
        # 응답 확인
        if response.status_code == 200:
            data = response.json()
            keyword_list = data.get("keywordList", [])
            
            if keyword_list and len(keyword_list) > 0:
                # 첫 번째 결과 사용
                kw_data = keyword_list[0]
                
                pc_count = parse_count(kw_data.get("monthlyPcQcCnt"))
                mobile_count = parse_count(kw_data.get("monthlyMobileQcCnt"))
                total_count = pc_count + mobile_count
                
                return {
                    "success": True,
                    "keyword": kw_data.get("relKeyword", keyword),
                    "pc": pc_count,
                    "mobile": mobile_count,
                    "total": total_count,
                    "competition": kw_data.get("compIdx", "정보없음")
                }
            else:
                return {
                    "success": False,
                    "error": "검색 결과가 없습니다."
                }
        else:
            return {
                "success": False,
                "error": f"API 응답 오류 (코드: {response.status_code})"
            }
            
    except requests.exceptions.Timeout:
        return {
            "success": False,
            "error": "API 응답 시간 초과"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"오류 발생: {str(e)}"
        }

#############################################
# 라우트: 홈 (서버 상태 확인용)
#############################################
@app.route('/')
def home():
    return "✅ 키워드 조회 봇 서버가 정상 작동 중입니다!"

#############################################
# 라우트: 직접 테스트용 (GET 방식)
#############################################
@app.route('/test')
def test():
    """브라우저에서 직접 테스트"""
    keyword = request.args.get('keyword', '맛집')
    result = get_naver_keyword_stats(keyword)
    
    if result["success"]:
        return f"""
        <h2>🔍 "{result['keyword']}" 검색량</h2>
        <p>📊 월간 총 검색량: {format_number(result['total'])}회</p>
        <p>📱 모바일: {format_number(result['mobile'])}회</p>
        <p>💻 PC: {format_number(result['pc'])}회</p>
        <p>📈 경쟁도: {result['competition']}</p>
        <hr>
        <p>다른 키워드 테스트: /test?keyword=검색어</p>
        """
    else:
        return f"""
        <h2>❌ 조회 실패</h2>
        <p>{result['error']}</p>
        <hr>
        <p>API 키가 올바르게 설정되었는지 확인하세요.</p>
        """

#############################################
# 라우트: 카카오 스킬 서버 (POST 방식)
#############################################
@app.route('/skill', methods=['POST'])
def kakao_skill():
    """카카오톡 챗봇 스킬 서버"""
    
    try:
        # 요청 데이터 받기
        request_data = request.get_json()
        
        # 요청 데이터가 없는 경우
        if request_data is None:
            return create_kakao_response("요청 데이터를 받지 못했습니다.")
        
        # 사용자 발화 추출
        user_utterance = ""
        
        if "userRequest" in request_data:
            user_request = request_data["userRequest"]
            if "utterance" in user_request:
                user_utterance = user_request["utterance"].strip()
        
        # 발화가 없는 경우
        if not user_utterance:
            return create_kakao_response("🔍 검색할 키워드를 입력해주세요!\n\n예시: 맛집, 다이어트, 여행")
        
        # 도움말 요청
        if user_utterance in ["도움말", "사용법", "help", "?"]:
            help_text = """🔍 키워드 검색량 조회 봇

키워드를 입력하면 네이버 월간 검색량을 알려드려요!

📝 사용 예시:
• 맛집
• 다이어트 식단
• 아이폰15 케이스

💡 한 번에 하나의 키워드만 입력해주세요."""
            return create_kakao_response(help_text)
        
        # 네이버 API 호출
        result = get_naver_keyword_stats(user_utterance)
        
        # 결과 생성
        if result["success"]:
            response_text = f"""🔍 "{result['keyword']}" 검색량 분석

📊 월간 총 검색량
{format_number(result['total'])}회

📱 모바일: {format_number(result['mobile'])}회
💻 PC: {format_number(result['pc'])}회

📈 경쟁도: {result['competition']}

━━━━━━━━━━━━━━━━
💡 다른 키워드도 검색해보세요!"""
        else:
            response_text = f"""❌ 조회 실패

{result['error']}

다시 시도해주세요!"""
        
        return create_kakao_response(response_text)
        
    except Exception as e:
        error_text = f"서버 오류가 발생했습니다.\n잠시 후 다시 시도해주세요."
        return create_kakao_response(error_text)

#############################################
# 카카오 응답 형식 생성
#############################################
def create_kakao_response(text):
    """카카오톡 스킬 응답 형식으로 반환"""
    response = {
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleText": {
                        "text": text
                    }
                }
            ]
        }
    }
    return jsonify(response)

#############################################
# 서버 실행
#############################################
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
