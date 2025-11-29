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
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
DATA_GO_KR_API_KEY = os.environ.get('DATA_GO_KR_API_KEY', '')


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
    if comp == "높음":
        return "[높음]"
    elif comp == "중간":
        return "[중간]"
    else:
        return "[낮음]"

def is_guide_message(text):
    guide_indicators = ["사용 가이드", "키워드 검색량", "연관 검색어", "CPC 광고", "블로그 상위글", "자동완성어", "대표키워드", "재미 기능"]
    count = sum(1 for indicator in guide_indicators if indicator in text)
    return count >= 4


#############################################
# 지역별 상권 특성 데이터
#############################################
REGION_DATA = {
    "부평": {
        "code": "2832000000",
        "name": "인천 부평구",
        "population": "4~5만명",
        "sales": {"min": 2000, "max": 3000},
        "price": {"min": 18000, "max": 22000},
        "weekday_ratio": 70,
        "peak_time": "점심 위주 (직장인)",
        "age_group": "2030",
        "characteristics": "직장인 밀집, 주거 복합"
    },
    "계양": {
        "code": "2824500000",
        "name": "인천 계양구",
        "population": "2~3만명",
        "sales": {"min": 1500, "max": 2500},
        "price": {"min": 15000, "max": 20000},
        "weekday_ratio": 65,
        "peak_time": "저녁 위주 (가족)",
        "age_group": "3040",
        "characteristics": "주거 중심, 가족 단위"
    },
    "송도": {
        "code": "2826000000",
        "name": "인천 연수구",
        "population": "3~4만명",
        "sales": {"min": 2500, "max": 4000},
        "price": {"min": 20000, "max": 28000},
        "weekday_ratio": 60,
        "peak_time": "저녁/주말 (데이트)",
        "age_group": "2030",
        "characteristics": "신도시, 젊은 가족, 고소득"
    },
    "강남": {
        "code": "1168000000",
        "name": "서울 강남구",
        "population": "8~10만명",
        "sales": {"min": 4000, "max": 7000},
        "price": {"min": 25000, "max": 40000},
        "weekday_ratio": 55,
        "peak_time": "점심/저녁 균등",
        "age_group": "2040",
        "characteristics": "고소득, 직장인, 유흥"
    },
    "홍대": {
        "code": "1144000000",
        "name": "서울 마포구",
        "population": "7~9만명",
        "sales": {"min": 3000, "max": 5000},
        "price": {"min": 15000, "max": 25000},
        "weekday_ratio": 45,
        "peak_time": "저녁/야간 (유흥)",
        "age_group": "1020",
        "characteristics": "유흥, 트렌드, 외국인"
    },
    "서초": {
        "code": "1165000000",
        "name": "서울 서초구",
        "population": "6~8만명",
        "sales": {"min": 3500, "max": 6000},
        "price": {"min": 22000, "max": 35000},
        "weekday_ratio": 60,
        "peak_time": "점심 (직장인)",
        "age_group": "3040",
        "characteristics": "고소득, 가족, 법조타운"
    },
    "잠실": {
        "code": "1171000000",
        "name": "서울 송파구",
        "population": "7~9만명",
        "sales": {"min": 3000, "max": 5000},
        "price": {"min": 20000, "max": 30000},
        "weekday_ratio": 50,
        "peak_time": "저녁/주말 (가족)",
        "age_group": "3040",
        "characteristics": "가족, 쇼핑, 롯데월드"
    },
    "해운대": {
        "code": "2626000000",
        "name": "부산 해운대구",
        "population": "5~7만명",
        "sales": {"min": 3000, "max": 5000},
        "price": {"min": 22000, "max": 35000},
        "weekday_ratio": 40,
        "peak_time": "저녁/주말 (관광)",
        "age_group": "전연령",
        "characteristics": "관광, 고급, 해변"
    },
    "서면": {
        "code": "2617000000",
        "name": "부산 부산진구",
        "population": "6~8만명",
        "sales": {"min": 2500, "max": 4000},
        "price": {"min": 18000, "max": 25000},
        "weekday_ratio": 55,
        "peak_time": "점심/저녁 균등",
        "age_group": "2030",
        "characteristics": "부산 중심, 유흥, 쇼핑"
    },
    "분당": {
        "code": "4113500000",
        "name": "경기 성남시",
        "population": "5~6만명",
        "sales": {"min": 3000, "max": 5000},
        "price": {"min": 22000, "max": 32000},
        "weekday_ratio": 60,
        "peak_time": "저녁 (가족)",
        "age_group": "3050",
        "characteristics": "고소득, 가족, IT기업"
    },
    "일산": {
        "code": "4128700000",
        "name": "경기 고양시",
        "population": "4~5만명",
        "sales": {"min": 2000, "max": 3500},
        "price": {"min": 18000, "max": 25000},
        "weekday_ratio": 55,
        "peak_time": "저녁/주말 (가족)",
        "age_group": "3040",
        "characteristics": "베드타운, 가족, 호수공원"
    },
    "수원": {
        "code": "4111100000",
        "name": "경기 수원시",
        "population": "5~6만명",
        "sales": {"min": 2500, "max": 4000},
        "price": {"min": 18000, "max": 25000},
        "weekday_ratio": 60,
        "peak_time": "점심/저녁 균등",
        "age_group": "2040",
        "characteristics": "삼성, 직장인, 역사"
    },
}

# 기본값 (지역 미특정)
DEFAULT_REGION_DATA = {
    "name": "전국",
    "population": "데이터 없음",
    "sales": {"min": 2000, "max": 3500},
    "price": {"min": 18000, "max": 25000},
    "weekday_ratio": 60,
    "peak_time": "점심/저녁",
    "age_group": "전연령",
    "characteristics": "지역 특성 미상"
}

REGION_KEYWORDS = list(REGION_DATA.keys())


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

def get_keyword_data(keyword):
    if not NAVER_API_KEY or not NAVER_SECRET_KEY or not NAVER_CUSTOMER_ID:
        return {"success": False, "error": "API 키가 설정되지 않았습니다."}
    
    base_url = "https://api.searchad.naver.com"
    uri = "/keywordstool"
    headers = get_naver_api_headers("GET", uri)
    params = {"hintKeywords": keyword, "showDetail": "1"}
    
    try:
        response = requests.get(base_url + uri, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            keyword_list = data.get("keywordList", [])
            if keyword_list:
                return {"success": True, "data": keyword_list}
            return {"success": False, "error": "검색 결과가 없습니다."}
        return {"success": False, "error": f"API 오류 ({response.status_code})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


#############################################
# CPC API
#############################################
def get_performance_estimate(keyword, bids, device='MOBILE'):
    try:
        uri = '/estimate/performance/keyword'
        url = f'https://api.searchad.naver.com{uri}'
        headers = get_naver_api_headers('POST', uri)
        payload = {"device": device, "keywordplus": False, "key": keyword, "bids": bids if isinstance(bids, list) else [bids]}
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code == 200:
            return {"success": True, "data": response.json()}
        return {"success": False, "error": response.text}
    except Exception as e:
        return {"success": False, "error": str(e)}

def get_optimal_bid_analysis(estimates):
    if not estimates:
        return None
    valid_estimates = [e for e in estimates if e.get('clicks', 0) > 0]
    if not valid_estimates:
        return None
    
    efficiency_data = []
    for i in range(1, len(valid_estimates)):
        prev, curr = valid_estimates[i-1], valid_estimates[i]
        click_inc = curr.get('clicks', 0) - prev.get('clicks', 0)
        cost_inc = curr.get('cost', 0) - prev.get('cost', 0)
        if cost_inc > 0 and click_inc > 0:
            efficiency_data.append({'data': curr, 'cost_per_click': cost_inc / click_inc})
    
    best_efficiency = None
    for i, eff in enumerate(efficiency_data):
        if i + 1 < len(efficiency_data):
            next_eff = efficiency_data[i + 1]
            if next_eff['cost_per_click'] / eff['cost_per_click'] >= 2:
                best_efficiency = eff
                break
        else:
            best_efficiency = eff
    
    if not best_efficiency and valid_estimates:
        best_efficiency = {'data': valid_estimates[len(valid_estimates)//2], 'cost_per_click': None}
    
    max_effective_bid = None
    if valid_estimates:
        max_clicks = valid_estimates[-1].get('clicks', 0)
        for est in valid_estimates:
            if est.get('clicks', 0) == max_clicks:
                max_effective_bid = est.get('bid', 0)
                break
    
    return {'best_efficiency': best_efficiency, 'max_effective_bid': max_effective_bid, 'all_estimates': valid_estimates}


#############################################
# DataLab 트렌드 API
#############################################
def get_datalab_trend(keyword):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"success": False, "error": "DataLab API 키 미설정"}
    
    url = "https://openapi.naver.com/v1/datalab/search"
    end_date = date.today() - timedelta(days=1)
    start_date = end_date - timedelta(days=365)
    
    payload = {
        "startDate": start_date.strftime("%Y-%m-%d"),
        "endDate": end_date.strftime("%Y-%m-%d"),
        "timeUnit": "month",
        "keywordGroups": [{"groupName": keyword, "keywords": [keyword]}]
    }
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            if results and results[0].get("data"):
                return {"success": True, "data": results[0]["data"]}
        return {"success": False, "error": "트렌드 데이터 없음"}
    except Exception as e:
        return {"success": False, "error": str(e)}


#############################################
# 네이버 지역검색 API (수정)
#############################################
def get_local_businesses(keyword, display=10):
    """네이버 지역검색 API - total 값 정확히 가져오기"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return {"success": False, "error": "API 키 미설정"}
    
    url = "https://openapi.naver.com/v1/search/local.json"
    headers = {
        "X-Naver-Client-Id": NAVER_CLIENT_ID,
        "X-Naver-Client-Secret": NAVER_CLIENT_SECRET
    }
    params = {
        "query": keyword,
        "display": display,
        "sort": "comment"  # 리뷰 많은 순
    }
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        logger.info(f"지역검색 API 응답: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            total = data.get("total", 0)
            items = data.get("items", [])
            
            logger.info(f"키워드: {keyword}, total: {total}, items: {len(items)}")
            
            return {
                "success": True,
                "data": items,
                "total": total,
                "display": data.get("display", 0)
            }
        return {"success": False, "error": f"API 오류 ({response.status_code})"}
    except Exception as e:
        logger.error(f"지역검색 API 오류: {str(e)}")
        return {"success": False, "error": str(e)}


#############################################
# 키워드에서 지역 추출
#############################################
def extract_region(keyword):
    """키워드에서 지역명 추출"""
    for region in REGION_KEYWORDS:
        if region in keyword:
            return region, REGION_DATA[region]
    return None, DEFAULT_REGION_DATA


#############################################
# 상권분석 통합 함수
#############################################
def get_commercial_analysis(keyword):
    """키워드 기반 상권 분석"""
    
    # 지역 추출
    region, region_data = extract_region(keyword)
    
    result = {
        "keyword": keyword,
        "region": region,
        "region_data": region_data,
        "search_data": None,
        "trend_data": None,
        "local_data": None
    }
    
    # 1. 검색량 데이터
    search_result = get_keyword_data(keyword)
    if search_result["success"]:
        kw = search_result["data"][0]
        pc = parse_count(kw.get("monthlyPcQcCnt"))
        mobile = parse_count(kw.get("monthlyMobileQcCnt"))
        total = pc + mobile
        result["search_data"] = {
            "total": total,
            "mobile": mobile,
            "pc": pc,
            "mobile_ratio": (mobile * 100 // total) if total > 0 else 0,
            "comp_idx": kw.get("compIdx", "")
        }
    
    # 2. 트렌드 데이터
    trend_result = get_datalab_trend(keyword)
    if trend_result["success"]:
        series = trend_result["data"]
        change = 0
        if len(series) >= 6:
            last3 = sum(p.get("ratio", 0) for p in series[-3:]) / 3
            prev3 = sum(p.get("ratio", 0) for p in series[-6:-3]) / 3
            change = ((last3 - prev3) / prev3) * 100 if prev3 > 0 else 0
        result["trend_data"] = {"series": series, "change": change}
    
    # 3. 지역검색 데이터 (업체 수, TOP 10)
    local_result = get_local_businesses(keyword, display=10)
    if local_result["success"]:
        result["local_data"] = {
            "total": local_result["total"],
            "items": local_result["data"]
        }
    
    return result


#############################################
# 상권분석 포맷팅 (지역별 차등 적용)
#############################################
def format_commercial_analysis(analysis):
    """상권분석 결과 포맷팅 - 지역별 데이터 차등 적용"""
    
    keyword = analysis["keyword"]
    region = analysis["region"]
    region_data = analysis["region_data"]
    
    lines = [f"[상권분석] {keyword}", ""]
    
    # ▶ 검색 데이터
    lines.append("▶ 검색 데이터")
    if analysis["search_data"]:
        sd = analysis["search_data"]
        lines.append(f"월 검색량: {format_number(sd['total'])}회")
        lines.append(f"모바일 {sd['mobile_ratio']}% / PC {100-sd['mobile_ratio']}%")
        lines.append(f"광고경쟁: {get_comp_text(sd['comp_idx'])}")
        
        if analysis["trend_data"]:
            change = analysis["trend_data"]["change"]
            if change >= 10:
                trend = f"상승 (+{change:.0f}%)"
            elif change <= -10:
                trend = f"하락 ({change:.0f}%)"
            else:
                trend = f"유지 ({change:+.0f}%)"
            lines.append(f"트렌드: {trend}")
    else:
        lines.append("검색량 데이터 없음")
    lines.append("")
    
    # ▶ 지역 상권
    lines.append("▶ 지역 상권")
    if region:
        lines.append(f"지역: {region} ({region_data['name']})")
        lines.append(f"특성: {region_data['characteristics']}")
    else:
        lines.append("지역: 전국 (특정 지역 미포함)")
    
    # 업체 수 (API에서 가져온 실제 값)
    if analysis["local_data"]:
        total = analysis["local_data"]["total"]
        if total > 0:
            lines.append(f"검색 업체: 약 {format_number(total)}개")
        else:
            lines.append("검색 업체: 데이터 없음")
    lines.append("")
    
    # ▶ TOP 10 업체
    if analysis["local_data"] and analysis["local_data"]["items"]:
        items = analysis["local_data"]["items"]
        lines.append(f"▶ TOP {len(items)} 업체")
        for i, item in enumerate(items, 1):
            title = re.sub(r'<[^>]+>', '', item.get("title", ""))
            category = item.get("category", "")
            # 카테고리 간략화
            if ">" in category:
                category = category.split(">")[-1].strip()
            lines.append(f"{i}. {title}" + (f" ({category})" if category else ""))
        lines.append("")
    
    # ▶ 매출 분석 (지역별 차등)
    lines.append("▶ 매출 분석 (업종 평균)")
    sales = region_data["sales"]
    price = region_data["price"]
    
    avg_sales = (sales["min"] + sales["max"]) // 2
    avg_price = (price["min"] + price["max"]) // 2
    avg_count = (avg_sales * 10000) // avg_price  # 대략적인 결제 건수
    
    lines.append(f"평균매출: 월 {sales['min']:,}~{sales['max']:,}만원")
    lines.append(f"결제건수: 월 {avg_count-200:,}~{avg_count+200:,}건")
    lines.append(f"객단가: {price['min']:,}~{price['max']:,}원")
    lines.append("")
    
    # ▶ 요일/시간대 (지역별 차등)
    lines.append("▶ 요일/시간대")
    weekday = region_data["weekday_ratio"]
    weekend = 100 - weekday
    lines.append(f"주중 {weekday}% / 주말 {weekend}%")
    lines.append(f"피크: {region_data['peak_time']}")
    lines.append("")
    
    # ▶ 고객층 (검색데이터 + 지역특성 결합)
    lines.append("▶ 고객층")
    
    # 연령대 (모바일 비율 + 지역 특성 결합)
    if analysis["search_data"]:
        mobile_ratio = analysis["search_data"]["mobile_ratio"]
        age_group = region_data["age_group"]
        
        if mobile_ratio >= 85:
            lines.append(f"연령: {age_group} 중심 (모바일 {mobile_ratio}%)")
            if "20" in age_group:
                lines.append("20대 35~40% / 30대 35~40%")
            elif "30" in age_group or "40" in age_group:
                lines.append("30대 35~40% / 40대 30~35%")
            else:
                lines.append("20대 30% / 30대 30% / 40대 25%")
        elif mobile_ratio >= 70:
            lines.append(f"연령: {age_group} 중심 (모바일 {mobile_ratio}%)")
            lines.append("20대 25% / 30대 35% / 40대 25%")
        else:
            lines.append(f"연령: 전 연령대 (PC 비중 높음)")
            lines.append("30대 25% / 40대 30% / 50대 25%")
    else:
        lines.append(f"연령: {region_data['age_group']}")
    
    # 성별 (업종에 따라)
    if "카페" in keyword or "디저트" in keyword or "브런치" in keyword:
        lines.append("성별: 여성 65~70%")
    elif "고기" in keyword or "삼겹살" in keyword or "갈비" in keyword:
        lines.append("성별: 남성 55~60%")
    else:
        lines.append("성별: 여성 52~55%")
    lines.append("")
    
    # ▶ 유동인구 (지역별)
    lines.append("▶ 유동인구")
    lines.append(f"일평균: 약 {region_data['population']}")
    lines.append("피크: 금/토요일, 점심/저녁")
    lines.append("")
    
    # ▶ 마케팅 인사이트 (데이터 기반 동적 생성)
    lines.append("▶ 마케팅 인사이트")
    insights = generate_insights(analysis, region_data)
    lines.extend(insights)
    
    return "\n".join(lines)


def generate_insights(analysis, region_data):
    """데이터 기반 인사이트 동적 생성"""
    insights = []
    
    # 검색량 기반
    if analysis["search_data"]:
        total = analysis["search_data"]["total"]
        mobile_ratio = analysis["search_data"]["mobile_ratio"]
        
        if total >= 100000:
            insights.append("• 검색량 매우 많음 → 플레이스 최적화 필수")
        elif total >= 50000:
            insights.append("• 검색량 많음 → SEO + 광고 병행 권장")
        elif total >= 10000:
            insights.append("• 검색량 중간 → 틈새 공략 가능")
        else:
            insights.append("• 검색량 적음 → 롱테일 키워드 활용")
        
        if mobile_ratio >= 85:
            insights.append("• 모바일 집중 → 모바일 최적화 필수")
    
    # 트렌드 기반
    if analysis["trend_data"]:
        change = analysis["trend_data"]["change"]
        if change >= 15:
            insights.append("• 급상승 트렌드 → 지금이 진입 적기!")
        elif change <= -15:
            insights.append("• 하락 트렌드 → 차별화/리브랜딩 필요")
        elif -5 <= change <= 5:
            insights.append("• 안정적 수요 → 꾸준한 운영 적합")
    
    # 경쟁 기반
    if analysis["local_data"]:
        total = analysis["local_data"]["total"]
        if total >= 5000:
            insights.append("• 경쟁 매우 치열 → 리뷰 관리 필수")
        elif total >= 1000:
            insights.append("• 경쟁 치열 → 차별화 포인트 필요")
        elif total >= 300:
            insights.append("• 경쟁 적당 → 품질로 승부 가능")
        else:
            insights.append("• 경쟁 낮음 → 선점 효과 기대")
    
    # 지역 특성 기반
    if region_data.get("characteristics"):
        char = region_data["characteristics"]
        if "직장인" in char:
            insights.append("• 점심 특선/런치 메뉴 효과적")
        if "가족" in char:
            insights.append("• 가족 단위 메뉴/좌석 준비")
        if "유흥" in char or "데이트" in char:
            insights.append("• 분위기/인테리어 중요")
        if "관광" in char:
            insights.append("• 외국어 메뉴/결제 준비")
    
    # 기본 인사이트
    if len(insights) < 3:
        insights.append("• 블로그 체험단 효과적")
        insights.append("• 네이버 플레이스 리뷰 확보")
    
    return insights[:6]  # 최대 6개

#############################################
# 기능 1: 검색량 조회 (깔끔한 다중 키워드)
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
    """다중 키워드 - 깔끔한 포맷"""
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
# 기능 2: 연관 키워드
#############################################
def get_related_keywords(keyword):
    try:
        url = f"https://search.naver.com/search.naver?where=nexearch&query={requests.utils.quote(keyword)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "ko-KR,ko;q=0.9"}
        response = requests.get(url, headers=headers, timeout=10)
        
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
        comp = get_comp_text(kw.get("compIdx", ""))
        response += f"{i}. {name} ({format_number(total)}) {comp}\n"
    
    return response.strip()


#############################################
# 기능 3: 광고 단가
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
    
    response = f"""[광고분석] {keyword_name}

▶ 키워드 정보
월간 검색량: {format_number(total_qc)}회
모바일 {mobile_ratio}% / PC {100-mobile_ratio}%

"""
    
    test_bids = [100, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 7000, 10000]
    mobile_perf = get_performance_estimate(keyword_name, test_bids, 'MOBILE')
    
    has_ad_data = False
    analysis = None
    
    if mobile_perf.get("success"):
        mobile_estimates = mobile_perf["data"].get("estimate", [])
        analysis = get_optimal_bid_analysis(mobile_estimates)
        
        if analysis and analysis.get('all_estimates'):
            has_ad_data = True
            response += "▶ 모바일 입찰가별 성과\n"
            
            prev_clicks = 0
            for est in analysis['all_estimates'][:6]:
                bid = est.get("bid", 0)
                clicks = est.get("clicks", 0)
                cost = est.get("cost", 0)
                response += f"{format_number(bid)}원 → 월 {clicks}회 / {format_won(cost)}\n"
                if clicks == prev_clicks and prev_clicks > 0:
                    break
                prev_clicks = clicks
            
            response += "\n"
            
            if analysis.get('best_efficiency'):
                eff = analysis['best_efficiency']['data']
                eff_bid = eff.get('bid', 0)
                eff_clicks = eff.get('clicks', 0)
                eff_cost = eff.get('cost', 0)
                eff_cpc = int(eff_cost / eff_clicks) if eff_clicks > 0 else eff_bid
                
                response += f"""▶ 추천 입찰가
{format_number(eff_bid)}원
ㄴ 예상 클릭: 월 {eff_clicks}회
ㄴ 예상 비용: {format_won(eff_cost)}
ㄴ 클릭당: {format_number(eff_cpc)}원

▶ 운영 가이드
시작 입찰가: {format_number(eff_bid)}원
일 예산: {format_won(max(eff_cost/30, 10000))}
CTR 목표: 1.5% 이상"""
    
    if not has_ad_data:
        response += f"""▶ 광고 정보
검색량이 적어 예상 데이터가 없습니다.

가이드:
- 입찰가: 100~500원 시작
- 일 예산: 5,000~10,000원
- 1-2주 운영 후 조정"""
    
    return response


#############################################
# 기능 4: 블로그 상위글
#############################################
def get_blog_titles(keyword):
    try:
        url = f"https://search.naver.com/search.naver?where=blog&query={requests.utils.quote(keyword)}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36", "Accept-Language": "ko-KR,ko;q=0.9"}
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            titles = []
            pattern = re.findall(r'sds-comps-text-type-headline1[^>]*>(.*?)</span>', response.text, re.DOTALL)
            for match in pattern:
                title = re.sub(r'<[^>]+>', '', match).strip()
                if title and len(title) > 3 and title not in titles:
                    titles.append(title)
                    if len(titles) >= 5:
                        break
            
            if titles:
                result = f"[블로그] {keyword} 상위 5개\n\n"
                for i, title in enumerate(titles, 1):
                    result += f"{i}. {title}\n"
                return result.strip()
        
        return get_blog_titles_api(keyword)
    except:
        return get_blog_titles_api(keyword)


def get_blog_titles_api(keyword):
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return f"[블로그] {keyword}\n\n블로그 API 미설정"
    
    url = "https://openapi.naver.com/v1/search/blog.json"
    headers = {"X-Naver-Client-Id": NAVER_CLIENT_ID, "X-Naver-Client-Secret": NAVER_CLIENT_SECRET}
    params = {"query": keyword, "display": 5, "sort": "sim"}
    
    try:
        response = requests.get(url, headers=headers, params=params, timeout=5)
        if response.status_code == 200:
            items = response.json().get("items", [])
            if items:
                result = f"[블로그] {keyword} 상위 5개\n\n"
                for i, item in enumerate(items, 1):
                    title = item.get("title", "").replace("<b>", "").replace("</b>", "")
                    result += f"{i}. {title}\n"
                return result.strip()
        return f"'{keyword}' 블로그 검색 결과가 없습니다."
    except Exception as e:
        return f"블로그 검색 실패: {str(e)}"


#############################################
# 기능 5: 운세
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

오늘의 조언: "(한마디)"

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

오늘의 한마디: "(격언)"

재미있고 긍정적으로. 이모티콘 없이."""
    
    try:
        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.9, "maxOutputTokens": 500}}, timeout=4)
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        pass
    return get_fortune_fallback(birthdate)


def get_fortune_fallback(birthdate=None):
    fortunes = ["오늘은 새로운 기회가 찾아오는 날!", "좋은 소식이 들려올 예정이에요.", "작은 행운이 당신을 따라다녀요."]
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
# 기능 6: 로또
#############################################
def get_lotto():
    if not GEMINI_API_KEY:
        return get_lotto_fallback()
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"
    prompt = """로또 번호 5세트 추천. 1~45, 각 6개, 오름차순.
형식:
[로또 번호 추천]

1) 00, 00, 00, 00, 00, 00
2) 00, 00, 00, 00, 00, 00
3) 00, 00, 00, 00, 00, 00
4) 00, 00, 00, 00, 00, 00
5) 00, 00, 00, 00, 00, 00

행운을 빕니다!
※ 재미로만 즐기세요!"""
    
    try:
        response = requests.post(url, json={"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 1.0, "maxOutputTokens": 400}}, timeout=4)
        if response.status_code == 200:
            return response.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        pass
    return get_lotto_fallback()


def get_lotto_fallback():
    result = "[로또 번호 추천]\n\n"
    for i in range(1, 6):
        numbers = sorted(random.sample(range(1, 46), 6))
        result += f"{i}) {', '.join(str(n).zfill(2) for n in numbers)}\n"
    result += "\n행운을 빕니다!\n※ 재미로만 즐기세요!"
    return result


#############################################
# 기능 7: 대표키워드
#############################################
def extract_place_id_from_url(url_or_id):
    url_or_id = url_or_id.strip()
    if url_or_id.isdigit():
        return url_or_id
    
    patterns = [r'/restaurant/(\d+)', r'/place/(\d+)', r'/cafe/(\d+)', r'/hospital/(\d+)', r'/beauty/(\d+)', r'place/(\d+)', r'=(\d{10,})']
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match and len(match.group(1)) >= 7:
            return match.group(1)
    
    match = re.search(r'\d{7,}', url_or_id)
    return match.group(0) if match else None


def get_place_keywords(place_id):
    headers = {"User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X)", "Accept-Language": "ko-KR,ko;q=0.9"}
    
    for category in ['restaurant', 'place', 'cafe', 'hospital', 'beauty']:
        try:
            url = f"https://m.place.naver.com/{category}/{place_id}/home"
            response = requests.get(url, headers=headers, timeout=10)
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
        return f"""[대표키워드] 조회 실패

플레이스 ID를 찾을 수 없습니다.

사용법:
대표 1529801174
대표 place.naver.com/restaurant/1529801174"""
    
    result = get_place_keywords(place_id)
    
    if not result["success"]:
        return f"""[대표키워드] 조회 실패

플레이스 ID: {place_id}
{result['error']}"""
    
    keywords = result["keywords"]
    response = f"[대표키워드] {place_id}\n\n"
    for i, kw in enumerate(keywords, 1):
        response += f"{i}. {kw}\n"
    response += f"\n복사용: {', '.join(keywords)}"
    
    return response


#############################################
# 기능 8: 자동완성
#############################################
def get_autocomplete(keyword):
    try:
        params = {"q": keyword, "con": "1", "frm": "nv", "ans": "2", "r_format": "json", "r_enc": "UTF-8", "r_unicode": "0", "t_koreng": "1", "run": "2", "rev": "4", "q_enc": "UTF-8", "st": "100"}
        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://www.naver.com/"}
        response = requests.get("https://ac.search.naver.com/nx/ac", params=params, headers=headers, timeout=5)
        
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
                result += f"\n※ 띄어쓰기에 따라 결과 다름"
                return result
    except:
        pass
    
    return f"[자동완성] {keyword}\n\n결과 없음"


#############################################
# 도움말
#############################################
def get_help():
    return """[사용 가이드]

▶ 키워드 검색량 (최대 5개)
예) 인천맛집
예) 인천맛집,강남맛집,서울맛집

▶ 상권분석 (트렌드+매출+고객)
예) 상권 부평맛집
예) 상권 강남카페

▶ 연관 검색어
예) 연관 인천맛집

▶ CPC 광고 단가
예) 광고 인천맛집

▶ 블로그 상위글
예) 블로그 인천맛집

▶ 자동완성어
예) 자동 인천맛집

▶ 대표키워드
예) 대표 12345678

▶ 재미 기능
운세 → 운세 870114
로또 → 로또

경쟁도: [높음] [중간] [낮음]"""


#############################################
# 테스트 라우트 (디버깅용)
#############################################
@app.route('/')
def home():
    return "서버 정상 작동 중"


@app.route('/test-local')
def test_local():
    """지역검색 API 테스트"""
    keyword = request.args.get('q', '부평맛집')
    
    result = get_local_businesses(keyword, display=10)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>지역검색 테스트</title></head>
<body>
<h2>키워드: {keyword}</h2>
<h3>API 결과</h3>
<p><b>성공:</b> {result.get('success')}</p>
<p><b>total:</b> {result.get('total', 'N/A')}</p>
<p><b>items 개수:</b> {len(result.get('data', []))}</p>
"""
    
    if result.get('success') and result.get('data'):
        html += "<h3>상위 업체</h3><ol>"
        for item in result['data']:
            title = re.sub(r'<[^>]+>', '', item.get('title', ''))
            category = item.get('category', '')
            html += f"<li>{title} ({category})</li>"
        html += "</ol>"
    
    if result.get('error'):
        html += f"<p style='color:red'>오류: {result['error']}</p>"
    
    html += "</body></html>"
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/test-place')
def test_place():
    place_id = request.args.get('id', '37838432')
    result = get_place_keywords(place_id)
    
    html = f"<h2>ID: {place_id}</h2><h3>{'성공' if result['success'] else '실패'}</h3>"
    if result['success']:
        html += "<ul>" + "".join(f"<li>{kw}</li>" for kw in result['keywords']) + "</ul>"
    else:
        html += f"<p>{result.get('error')}</p>"
    
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


#############################################
# 카카오 스킬
#############################################
@app.route('/skill', methods=['POST'])
def kakao_skill():
    try:
        request_data = request.get_json()
        if request_data is None:
            return create_kakao_response("요청 데이터를 받지 못했습니다.")
        
        user_utterance = request_data.get("userRequest", {}).get("utterance", "").strip()
        if not user_utterance:
            return create_kakao_response("검색할 키워드를 입력해주세요!")
        
        if is_guide_message(user_utterance):
            return create_kakao_response("가이드를 참고해서 명령어를 입력해주세요!")
        
        lower_input = user_utterance.lower()
        
        # 도움말
        if lower_input in ["도움말", "도움", "사용법", "help", "?", "메뉴"]:
            return create_kakao_response(get_help())
        
        # 운세
        if lower_input.startswith("운세 "):
            birthdate = ''.join(filter(str.isdigit, user_utterance))
            if birthdate and len(birthdate) in [6, 8]:
                return create_kakao_response(get_fortune(birthdate))
            return create_kakao_response("생년월일 6자리/8자리 입력\n예) 운세 870114")
        
        if lower_input in ["운세", "오늘의운세", "오늘운세"]:
            return create_kakao_response(get_fortune())
        
        # 로또
        if lower_input in ["로또", "로또번호", "lotto"]:
            return create_kakao_response(get_lotto())
        
        # 상권분석 (상권, 상세, 인사이트, 트렌드)
        if any(lower_input.startswith(cmd) for cmd in ["상권 ", "상세 ", "인사이트 ", "트렌드 "]):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                analysis = get_commercial_analysis(keyword)
                return create_kakao_response(format_commercial_analysis(analysis))
            return create_kakao_response("예) 상권 부평맛집")
        
        # 자동완성
        if lower_input.startswith("자동 ") or lower_input.startswith("자동완성 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if keyword:
                return create_kakao_response(get_autocomplete(keyword))
            return create_kakao_response("예) 자동 부평맛집")
        
        # 대표키워드
        if lower_input.startswith("대표 ") or lower_input.startswith("대표키워드 "):
            input_text = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if input_text:
                return create_kakao_response(format_place_keywords(input_text))
            return create_kakao_response("예) 대표 37838432")
        
        # 연관키워드
        if lower_input.startswith("연관 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_related_keywords(keyword))
            return create_kakao_response("예) 연관 맛집")
        
        # 광고
        if lower_input.startswith("광고 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_ad_cost(keyword))
            return create_kakao_response("예) 광고 맛집")
        
        # 블로그
        if lower_input.startswith("블로그 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_blog_titles(keyword))
            return create_kakao_response("예) 블로그 맛집")
        
        # 기본: 검색량
        keyword = user_utterance.strip()
        if "," in keyword:
            return create_kakao_response(get_search_volume(keyword))
        else:
            return create_kakao_response(get_search_volume(clean_keyword(keyword)))
    
    except Exception as e:
        logger.error(f"스킬 오류: {str(e)}")
        return create_kakao_response(f"오류: {str(e)}")


def create_kakao_response(text):
    if len(text) > 1000:
        text = text[:997] + "..."
    return jsonify({"version": "2.0", "template": {"outputs": [{"simpleText": {"text": text}}]}})


#############################################
# 서버 실행
#############################################
if __name__ == '__main__':
    print("=== 환경변수 확인 ===")
    print(f"검색광고 API: {'✅' if NAVER_API_KEY else '❌'}")
    print(f"DataLab API: {'✅' if NAVER_CLIENT_ID else '❌'}")
    print(f"Gemini API: {'✅' if GEMINI_API_KEY else '❌'}")
    print(f"공공데이터 API: {'✅' if DATA_GO_KR_API_KEY else '❌'}")
    print("====================")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)