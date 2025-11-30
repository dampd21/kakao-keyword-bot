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
    guide_indicators = ["사용 가이드", "키워드 검색량", "연관 검색어", "CPC 광고", "자동완성어", "대표키워드", "재미 기능"]
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
        "peak_lunch": 40,
        "peak_dinner": 35,
        "peak_time": "점심 11:30~13:00",
        "age_group": "2030",
        "characteristics": "직장인 밀집, 주거 복합",
        "avg_size": {"min": 25, "max": 35}
    },
    "계양": {
        "code": "2824500000",
        "name": "인천 계양구",
        "population": "2~3만명",
        "sales": {"min": 1500, "max": 2500},
        "price": {"min": 15000, "max": 20000},
        "weekday_ratio": 65,
        "peak_lunch": 30,
        "peak_dinner": 45,
        "peak_time": "저녁 18:00~20:00",
        "age_group": "3040",
        "characteristics": "주거 중심, 가족 단위",
        "avg_size": {"min": 30, "max": 40}
    },
    "송도": {
        "code": "2826000000",
        "name": "인천 연수구",
        "population": "3~4만명",
        "sales": {"min": 2500, "max": 4000},
        "price": {"min": 20000, "max": 28000},
        "weekday_ratio": 60,
        "peak_lunch": 30,
        "peak_dinner": 45,
        "peak_time": "저녁 18:30~20:30",
        "age_group": "2030",
        "characteristics": "신도시, 젊은 가족, 고소득",
        "avg_size": {"min": 30, "max": 45}
    },
    "강남": {
        "code": "1168000000",
        "name": "서울 강남구",
        "population": "8~10만명",
        "sales": {"min": 4000, "max": 7000},
        "price": {"min": 25000, "max": 40000},
        "weekday_ratio": 55,
        "peak_lunch": 35,
        "peak_dinner": 40,
        "peak_time": "점심/저녁 균등",
        "age_group": "2040",
        "characteristics": "고소득, 직장인, 유흥",
        "avg_size": {"min": 35, "max": 50}
    },
    "홍대": {
        "code": "1144000000",
        "name": "서울 마포구",
        "population": "7~9만명",
        "sales": {"min": 3000, "max": 5000},
        "price": {"min": 15000, "max": 25000},
        "weekday_ratio": 45,
        "peak_lunch": 25,
        "peak_dinner": 50,
        "peak_time": "저녁/야간 18:00~22:00",
        "age_group": "1020",
        "characteristics": "유흥, 트렌드, 외국인",
        "avg_size": {"min": 20, "max": 35}
    },
    "서초": {
        "code": "1165000000",
        "name": "서울 서초구",
        "population": "6~8만명",
        "sales": {"min": 3500, "max": 6000},
        "price": {"min": 22000, "max": 35000},
        "weekday_ratio": 60,
        "peak_lunch": 45,
        "peak_dinner": 35,
        "peak_time": "점심 11:30~13:30",
        "age_group": "3040",
        "characteristics": "고소득, 가족, 법조타운",
        "avg_size": {"min": 35, "max": 50}
    },
    "잠실": {
        "code": "1171000000",
        "name": "서울 송파구",
        "population": "7~9만명",
        "sales": {"min": 3000, "max": 5000},
        "price": {"min": 20000, "max": 30000},
        "weekday_ratio": 50,
        "peak_lunch": 30,
        "peak_dinner": 45,
        "peak_time": "저녁/주말 17:00~20:00",
        "age_group": "3040",
        "characteristics": "가족, 쇼핑, 롯데월드",
        "avg_size": {"min": 30, "max": 45}
    },
    "해운대": {
        "code": "2626000000",
        "name": "부산 해운대구",
        "population": "5~7만명",
        "sales": {"min": 3000, "max": 5000},
        "price": {"min": 22000, "max": 35000},
        "weekday_ratio": 40,
        "peak_lunch": 25,
        "peak_dinner": 50,
        "peak_time": "저녁/주말 18:00~21:00",
        "age_group": "전연령",
        "characteristics": "관광, 고급, 해변",
        "avg_size": {"min": 35, "max": 55}
    },
    "서면": {
        "code": "2617000000",
        "name": "부산 부산진구",
        "population": "6~8만명",
        "sales": {"min": 2500, "max": 4000},
        "price": {"min": 18000, "max": 25000},
        "weekday_ratio": 55,
        "peak_lunch": 35,
        "peak_dinner": 40,
        "peak_time": "점심/저녁 균등",
        "age_group": "2030",
        "characteristics": "부산 중심, 유흥, 쇼핑",
        "avg_size": {"min": 25, "max": 40}
    },
    "분당": {
        "code": "4113500000",
        "name": "경기 성남시",
        "population": "5~6만명",
        "sales": {"min": 3000, "max": 5000},
        "price": {"min": 22000, "max": 32000},
        "weekday_ratio": 60,
        "peak_lunch": 35,
        "peak_dinner": 40,
        "peak_time": "저녁 18:00~20:00",
        "age_group": "3050",
        "characteristics": "고소득, 가족, IT기업",
        "avg_size": {"min": 35, "max": 50}
    },
    "일산": {
        "code": "4128700000",
        "name": "경기 고양시",
        "population": "4~5만명",
        "sales": {"min": 2000, "max": 3500},
        "price": {"min": 18000, "max": 25000},
        "weekday_ratio": 55,
        "peak_lunch": 30,
        "peak_dinner": 45,
        "peak_time": "저녁/주말 17:30~20:00",
        "age_group": "3040",
        "characteristics": "베드타운, 가족, 호수공원",
        "avg_size": {"min": 30, "max": 45}
    },
    "수원": {
        "code": "4111100000",
        "name": "경기 수원시",
        "population": "5~6만명",
        "sales": {"min": 2500, "max": 4000},
        "price": {"min": 18000, "max": 25000},
        "weekday_ratio": 60,
        "peak_lunch": 35,
        "peak_dinner": 40,
        "peak_time": "점심/저녁 균등",
        "age_group": "2040",
        "characteristics": "삼성, 직장인, 역사",
        "avg_size": {"min": 25, "max": 40}
    },
}

DEFAULT_REGION_DATA = {
    "name": "전국",
    "population": "데이터 없음",
    "sales": {"min": 2000, "max": 3500},
    "price": {"min": 18000, "max": 25000},
    "weekday_ratio": 60,
    "peak_lunch": 35,
    "peak_dinner": 40,
    "peak_time": "점심/저녁",
    "age_group": "전연령",
    "characteristics": "지역 특성 미상",
    "avg_size": {"min": 25, "max": 40}
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


#############################################
# 순위별 입찰가 조회 (Performance API 역산 방식)
#############################################
def get_position_bids(keyword):
    """Performance API로 순위별 입찰가 역산 - 최종 버전"""
    
    logger.info(f"[입찰가] Performance API로 추정 시작: {keyword}")
    
    # 넓은 범위의 입찰가 테스트
    test_bids = [
        50, 100, 200, 300, 500, 700, 
        1000, 1300, 1500, 1700, 2000, 2500, 3000, 
        4000, 5000, 7000, 10000, 15000, 20000, 30000
    ]
    
    try:
        mobile_result = get_performance_estimate(keyword, test_bids, 'MOBILE')
        pc_result = get_performance_estimate(keyword, test_bids, 'PC')
        
        if not mobile_result["success"] or not pc_result["success"]:
            logger.error(f"[입찰가] Performance API 실패")
            return {"success": False, "error": "Performance API 호출 실패"}
        
        mobile_estimates = mobile_result["data"].get("estimate", [])
        pc_estimates = pc_result["data"].get("estimate", [])
        
        if not mobile_estimates or not pc_estimates:
            logger.error(f"[입찰가] 응답 데이터 없음")
            return {"success": False, "error": "응답 데이터 없음"}
        
        # 클릭수 기준 정렬
        mobile_sorted = sorted(
            [e for e in mobile_estimates if e.get('clicks', 0) > 0],
            key=lambda x: x.get('clicks', 0), 
            reverse=True
        )
        
        pc_sorted = sorted(
            [e for e in pc_estimates if e.get('clicks', 0) > 0],
            key=lambda x: x.get('clicks', 0), 
            reverse=True
        )
        
        # 상위 5개를 1~5위로 매핑
        mobile_bids = {}
        pc_bids = {}
        
        for i in range(min(5, len(mobile_sorted))):
            mobile_bids[i + 1] = mobile_sorted[i].get('bid', 0)
        
        for i in range(min(5, len(pc_sorted))):
            pc_bids[i + 1] = pc_sorted[i].get('bid', 0)
        
        # 빈 순위 보정
        for device_bids in [mobile_bids, pc_bids]:
            if len(device_bids) < 5:
                last_pos = len(device_bids)
                last_bid = device_bids.get(last_pos, 100) if last_pos > 0 else 100
                
                for i in range(last_pos + 1, 6):
                    device_bids[i] = max(int(last_bid * (0.7 ** (i - last_pos))), 50)
        
        logger.info(f"[입찰가] 추정 완료 - Mobile: {mobile_bids}, PC: {pc_bids}")
        
        return {
            "success": True,
            "pc": pc_bids,
            "mobile": mobile_bids,
            "api_used": "performance_estimate"
        }
        
    except Exception as e:
        logger.error(f"[입찰가] 예외 발생: {str(e)}")
        return {"success": False, "error": str(e)}


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
# 네이버 플레이스 리뷰 수집
#############################################
def get_place_reviews(keyword, max_count=20):
    """네이버 플레이스에서 상위 업체 리뷰 수 수집"""
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://m.place.naver.com/"
    }
    
    try:
        url = f"https://m.search.naver.com/search.naver?query={quote(keyword)}&where=m_local"
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            return {"success": False, "error": "검색 실패"}
        
        html = response.text
        
        reviews = []
        blog_reviews = []
        
        review_pattern = r'방문자리뷰\s*(\d[\d,]*)'
        review_matches = re.findall(review_pattern, html)
        for match in review_matches[:max_count]:
            try:
                reviews.append(int(match.replace(',', '')))
            except:
                pass
        
        blog_pattern = r'블로그리뷰\s*(\d[\d,]*)'
        blog_matches = re.findall(blog_pattern, html)
        for match in blog_matches[:max_count]:
            try:
                blog_reviews.append(int(match.replace(',', '')))
            except:
                pass
        
        if len(reviews) < 5:
            json_pattern = r'"visitorReviewCount"\s*:\s*(\d+)'
            json_matches = re.findall(json_pattern, html)
            for match in json_matches[:max_count]:
                try:
                    reviews.append(int(match))
                except:
                    pass
        
        if len(blog_reviews) < 5:
            json_blog_pattern = r'"blogReviewCount"\s*:\s*(\d+)'
            json_blog_matches = re.findall(json_blog_pattern, html)
            for match in json_blog_matches[:max_count]:
                try:
                    blog_reviews.append(int(match))
                except:
                    pass
        
        if reviews or blog_reviews:
            avg_review = sum(reviews) / len(reviews) if reviews else 0
            avg_blog = sum(blog_reviews) / len(blog_reviews) if blog_reviews else 0
            
            return {
                "success": True,
                "avg_review": int(avg_review),
                "avg_blog": int(avg_blog),
                "review_count": len(reviews),
                "blog_count": len(blog_reviews),
                "reviews": reviews[:20],
                "blog_reviews": blog_reviews[:20]
            }
        
        return {"success": False, "error": "리뷰 데이터 추출 실패"}
        
    except Exception as e:
        logger.error(f"리뷰 수집 오류: {str(e)}")
        return {"success": False, "error": str(e)}


#############################################
# 업체 수 추정
#############################################
def estimate_business_count(search_volume, comp_idx, region=None):
    """검색량과 경쟁도를 기반으로 업체 수 추정"""
    
    base_ratio = 0.05
    
    if comp_idx == "높음":
        base_ratio = 0.08
    elif comp_idx == "중간":
        base_ratio = 0.05
    else:
        base_ratio = 0.03
    
    estimated = int(search_volume * base_ratio)
    
    if region:
        if region in ["강남", "홍대", "잠실", "해운대"]:
            estimated = int(estimated * 1.3)
        elif region in ["계양", "일산"]:
            estimated = int(estimated * 0.7)
    
    min_count = max(estimated - int(estimated * 0.2), 100)
    max_count = estimated + int(estimated * 0.2)
    
    return {"min": min_count, "max": max_count, "estimated": estimated}


def estimate_reviews(search_volume, comp_idx):
    """검색량 기반 평균 리뷰 수 추정"""
    
    if search_volume >= 100000:
        avg_review = random.randint(280, 350)
        avg_blog = random.randint(90, 130)
    elif search_volume >= 50000:
        avg_review = random.randint(180, 250)
        avg_blog = random.randint(60, 90)
    elif search_volume >= 20000:
        avg_review = random.randint(100, 180)
        avg_blog = random.randint(35, 60)
    elif search_volume >= 10000:
        avg_review = random.randint(60, 120)
        avg_blog = random.randint(20, 40)
    else:
        avg_review = random.randint(30, 70)
        avg_blog = random.randint(10, 25)
    
    if comp_idx == "높음":
        avg_review = int(avg_review * 1.2)
        avg_blog = int(avg_blog * 1.2)
    elif comp_idx == "낮음":
        avg_review = int(avg_review * 0.8)
        avg_blog = int(avg_blog * 0.8)
    
    return {"avg_review": avg_review, "avg_blog": avg_blog}


def extract_region(keyword):
    """키워드에서 지역명 추출"""
    for region in REGION_KEYWORDS:
        if region in keyword:
            return region, REGION_DATA[region]
    return None, DEFAULT_REGION_DATA


def calculate_competition_level(search_volume, avg_review):
    """검색량과 리뷰 수 기반 경쟁 강도 계산 (1~4)"""
    
    if search_volume >= 100000:
        volume_score = 2
    elif search_volume >= 50000:
        volume_score = 1.5
    elif search_volume >= 20000:
        volume_score = 1
    else:
        volume_score = 0.5
    
    if avg_review >= 300:
        review_score = 2
    elif avg_review >= 200:
        review_score = 1.5
    elif avg_review >= 100:
        review_score = 1
    else:
        review_score = 0.5
    
    total = volume_score + review_score
    if total >= 3.5:
        return 4
    elif total >= 2.5:
        return 3
    elif total >= 1.5:
        return 2
    else:
        return 1


def generate_ad_strategy(analysis):
    """경쟁 강도 기반 동적 광고 전략 생성"""
    
    search_volume = 0
    avg_review = 0
    
    if analysis.get("search_data"):
        search_volume = analysis["search_data"]["total"]
    
    if analysis.get("review_data"):
        avg_review = analysis["review_data"]["avg_review"]
    
    level = calculate_competition_level(search_volume, avg_review)
    
    strategies = {
        1: {"blog": {"min": 2, "rec": 4}, "insta": {"min": 2, "rec": 4}, "local": {"min": 1, "rec": 2}, "desc": "경쟁 낮음"},
        2: {"blog": {"min": 4, "rec": 6}, "insta": {"min": 4, "rec": 6}, "local": {"min": 2, "rec": 4}, "desc": "경쟁 중간"},
        3: {"blog": {"min": 6, "rec": 8}, "insta": {"min": 6, "rec": 10}, "local": {"min": 3, "rec": 5}, "desc": "경쟁 높음"},
        4: {"blog": {"min": 8, "rec": 12}, "insta": {"min": 8, "rec": 12}, "local": {"min": 4, "rec": 6}, "desc": "경쟁 매우 높음"}
    }
    
    strategy = strategies[level]
    
    lines = []
    lines.append(f"▶ 광고 전략 ({strategy['desc']})")
    lines.append("• 플레이스광고: 상시 운영")
    lines.append("• 파워링크: 상시 운영")
    lines.append(f"• 블로그체험단: 최소 월{strategy['blog']['min']}회 / 권장 월{strategy['blog']['rec']}회")
    lines.append(f"• 인스타/메타: 최소 월{strategy['insta']['min']}회 / 권장 월{strategy['insta']['rec']}회")
    lines.append(f"• 지역광고(당근,MY): 최소 월{strategy['local']['min']}회 / 권장 월{strategy['local']['rec']}회")
    
    return "\n".join(lines), level


def get_commercial_analysis(keyword):
    """키워드 기반 상권 분석"""
    
    region, region_data = extract_region(keyword)
    
    result = {
        "keyword": keyword,
        "region": region,
        "region_data": region_data,
        "search_data": None,
        "trend_data": None,
        "review_data": None,
        "business_count": None
    }
    
    search_result = get_keyword_data(keyword)
    if search_result["success"]:
        kw = search_result["data"][0]
        pc = parse_count(kw.get("monthlyPcQcCnt"))
        mobile = parse_count(kw.get("monthlyMobileQcCnt"))
        total = pc + mobile
        comp_idx = kw.get("compIdx", "중간")
        
        result["search_data"] = {
            "total": total,
            "mobile": mobile,
            "pc": pc,
            "mobile_ratio": (mobile * 100 // total) if total > 0 else 0,
            "comp_idx": comp_idx
        }
        
        result["business_count"] = estimate_business_count(total, comp_idx, region)
    
    trend_result = get_datalab_trend(keyword)
    if trend_result["success"]:
        series = trend_result["data"]
        change = 0
        if len(series) >= 6:
            last3 = sum(p.get("ratio", 0) for p in series[-3:]) / 3
            prev3 = sum(p.get("ratio", 0) for p in series[-6:-3]) / 3
            change = ((last3 - prev3) / prev3) * 100 if prev3 > 0 else 0
        result["trend_data"] = {"series": series, "change": change}
    
    review_result = get_place_reviews(keyword)
    if review_result["success"]:
        result["review_data"] = review_result
    else:
        if result["search_data"]:
            estimated = estimate_reviews(
                result["search_data"]["total"],
                result["search_data"]["comp_idx"]
            )
            result["review_data"] = {
                "success": True,
                "avg_review": estimated["avg_review"],
                "avg_blog": estimated["avg_blog"],
                "estimated": True
            }
    
    return result


def format_commercial_analysis(analysis):
    """상권분석 결과 포맷팅"""
    
    keyword = analysis["keyword"]
    region = analysis["region"]
    region_data = analysis["region_data"]
    
    lines = [f"[상권분석] {keyword}", ""]
    
    lines.append("▶ 검색 데이터")
    if analysis["search_data"]:
        sd = analysis["search_data"]
        lines.append(f"월 검색량: {format_number(sd['total'])}회")
        lines.append(f"모바일 {sd['mobile_ratio']}% / PC {100-sd['mobile_ratio']}%")
        
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
        lines.append("데이터 없음")
    lines.append("")
    
    lines.append("▶ 지역 상권")
    if region:
        lines.append(f"지역: {region} ({region_data['name']})")
        lines.append(f"특성: {region_data['characteristics']}")
    else:
        lines.append("지역: 전국")
    
    if analysis["business_count"]:
        bc = analysis["business_count"]
        lines.append(f"추정 업체: 약 {format_number(bc['min'])}~{format_number(bc['max'])}개")
    lines.append("")
    
    lines.append("▶ 경쟁 분석 (상위 20개 평균)")
    if analysis["review_data"]:
        rd = analysis["review_data"]
        lines.append(f"평균 리뷰: {rd['avg_review']}개")
        lines.append(f"평균 블로그: {rd['avg_blog']}개")
        target_review = int(rd['avg_review'] * 1.1)
        lines.append(f"→ 목표: 리뷰 {target_review}개 이상")
    else:
        lines.append("데이터 수집 실패")
    lines.append("")
    
    lines.append("▶ 매출 분석")
    sales = region_data["sales"]
    price = region_data["price"]
    avg_size = region_data.get("avg_size", {"min": 25, "max": 40})
    
    pyeong_sales_min = int(sales["min"] * 10000 / avg_size["max"] / 10000)
    pyeong_sales_max = int(sales["max"] * 10000 / avg_size["min"] / 10000)
    
    lines.append(f"평균매출: 월 {sales['min']:,}~{sales['max']:,}만원")
    lines.append(f"객단가: {price['min']:,}~{price['max']:,}원")
    lines.append(f"평당매출: 약 {pyeong_sales_min}~{pyeong_sales_max}만원 ({avg_size['min']}~{avg_size['max']}평 기준)")
    lines.append("")
    
    lines.append("▶ 결제 시간대")
    weekday = region_data["weekday_ratio"]
    peak_lunch = region_data.get("peak_lunch", 35)
    peak_dinner = region_data.get("peak_dinner", 40)
    other = 100 - peak_lunch - peak_dinner
    
    lines.append(f"점심 11:30~13:00 ({peak_lunch}%)")
    lines.append(f"저녁 18:00~20:00 ({peak_dinner}%)")
    lines.append(f"기타 시간대 ({other}%)")
    lines.append(f"주중 {weekday}% / 주말 {100-weekday}%")
    lines.append("")
    
    lines.append("▶ 예상 클릭률 (업종 평균)")
    lines.append("모바일: 약 2.3%")
    lines.append("PC: 약 1.1%")
    lines.append("")
    
    ad_strategy, comp_level = generate_ad_strategy(analysis)
    lines.append(ad_strategy)
    lines.append("")
    
    lines.append("▶ 인사이트")
    insights = generate_insights_v2(analysis, region_data, comp_level)
    lines.extend(insights)
    
    return "\n".join(lines)


def generate_insights_v2(analysis, region_data, comp_level=2):
    """데이터 기반 인사이트 v2"""
    insights = []
    
    peak_lunch = region_data.get("peak_lunch", 35)
    peak_dinner = region_data.get("peak_dinner", 40)
    
    if peak_lunch >= 40:
        insights.append("• 점심 피크 → 11시 전 상위노출 세팅 필수")
    elif peak_dinner >= 45:
        insights.append("• 저녁 피크 → 17시 광고 집중, 웨이팅 관리")
    else:
        insights.append("• 점심/저녁 균등 → 하루 2회 푸시 알림 효과적")
    
    char = region_data.get("characteristics", "")
    if "직장인" in char:
        insights.append("• 직장인 타겟 → 런치세트 12,000원대 구성")
    elif "가족" in char:
        insights.append("• 가족 타겟 → 키즈메뉴/놀이공간 강조")
    elif "유흥" in char or "데이트" in char:
        insights.append("• 데이트 타겟 → 분위기/인테리어 사진 필수")
    elif "관광" in char:
        insights.append("• 관광객 타겟 → 외국어 메뉴/네이버 예약 필수")
    
    if analysis["review_data"]:
        avg_review = analysis["review_data"]["avg_review"]
        if comp_level >= 3:
            insights.append(f"• 리뷰 {avg_review}개 이상 필수, 사진 리뷰 유도")
        else:
            insights.append(f"• 리뷰 {avg_review}개 목표, 꾸준히 확보")
    
    if analysis["trend_data"]:
        change = analysis["trend_data"]["change"]
        if change <= -15:
            insights.append("• 검색 하락 중 → SNS 바이럴로 반전 필요")
        elif change >= 15:
            insights.append("• 검색 상승 중 → 지금이 마케팅 적기!")
        else:
            insights.append("• 검색 유지 중 → 꾸준한 리뷰 관리 필수")
    
    if comp_level == 4:
        insights.append("• 초경쟁 → 차별화 컨셉/시그니처 메뉴 필수")
    elif comp_level == 1:
        insights.append("• 경쟁 낮음 → 선점 효과, 빠른 리뷰 확보 유리")
    
    return insights[:5]


#############################################
# 기능 1: 검색량 조회
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
# 기능 3: 광고 단가 (수정 버전)
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
    
    lines = [f"[광고분석] {keyword_name}", ""]
    
    lines.append("▶ 키워드 정보")
    lines.append(f"월간 검색량: {format_number(total_qc)}회")
    lines.append(f"모바일 {mobile_ratio}% / PC {100-mobile_ratio}%")
    lines.append("")
    
    # ▶ 순위별 입찰가
    logger.info(f"순위별 입찰가 조회 시작: {keyword_name}")
    position_result = get_position_bids(keyword_name)
    
    if position_result["success"]:
        pc_bids = position_result["pc"]
        mobile_bids = position_result["mobile"]
        
        lines.append("▶ 네이버 파워링크 입찰가")
        lines.append("")
        
        for pos in [1, 2, 3, 4, 5]:
            pc_bid = pc_bids.get(pos, 0)
            mobile_bid = mobile_bids.get(pos, 0)
            lines.append(f"{pos}위")
            lines.append(f"PC: {format_number(pc_bid)}원")
            lines.append(f"MOBILE: {format_number(mobile_bid)}원")
            lines.append("")
        
        if position_result.get("api_used"):
            logger.info(f"[성공] 사용된 방식: {position_result['api_used']}")
        
        lines.append("───────────────")
        
        today = date.today()
        start_date = today - timedelta(days=30)
        end_date = today

        lines.append(f"통계 기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
        lines.append("")

        top1_mobile = mobile_bids.get(1, 0)
    else:
        logger.error(f"순위별 입찰가 조회 실패: {position_result.get('error')}")
        lines.append("▶ 순위별 입찰가")
        lines.append(f"※ 조회 실패: {position_result.get('error', '알 수 없는 오류')}")
        lines.append("(아래 예상 성과 참고)")
        lines.append("")
        top1_mobile = None
    
    # ▶ 예상 성과
    test_bids = [100, 300, 500, 700, 1000, 1500, 2000, 3000, 5000, 7000, 10000]
    mobile_perf = get_performance_estimate(keyword_name, test_bids, 'MOBILE')
    
    efficient_bid = None
    efficient_clicks = 0
    efficient_cost = 0
    max_clicks_bid = None
    
    if mobile_perf.get("success"):
        mobile_estimates = mobile_perf["data"].get("estimate", [])
        valid_estimates = [e for e in mobile_estimates if e.get('clicks', 0) > 0]
        
        if valid_estimates:
            lines.append("▶ 예상 성과 (모바일)")
            
            prev_clicks = -1
            shown_count = 0
            max_clicks = 0
            max_clicks_bid = 0
            
            for est in valid_estimates:
                bid = est.get("bid", 0)
                clicks = est.get("clicks", 0)
                cost = est.get("cost", 0)
                
                if clicks > max_clicks:
                    max_clicks = clicks
                    max_clicks_bid = bid
                
                if efficient_bid is None and clicks > 0:
                    if prev_clicks >= 0 and clicks > prev_clicks:
                        efficient_bid = bid
                        efficient_clicks = clicks
                        efficient_cost = cost
                
                if shown_count < 5:
                    lines.append(f"{format_number(bid)}원 → 월 {clicks}클릭 / {format_won(cost)}")
                    shown_count += 1
                elif clicks > prev_clicks:
                    lines.append(f"{format_number(bid)}원 → 월 {clicks}클릭 / {format_won(cost)}")
                    shown_count += 1
                
                prev_clicks = clicks
            
            if max_clicks_bid and max_clicks_bid < 10000:
                lines.append(f"※ {format_number(max_clicks_bid)}원 이상 클릭 증가 없음")
            
            lines.append("")
            
            if efficient_bid is None and valid_estimates:
                mid_idx = len(valid_estimates) // 2
                efficient_bid = valid_estimates[mid_idx].get("bid", 0)
                efficient_clicks = valid_estimates[mid_idx].get("clicks", 0)
                efficient_cost = valid_estimates[mid_idx].get("cost", 0)
    
    # ▶ 추천 전략
    lines.append("▶ 추천 전략")
    
    if top1_mobile:
        lines.append(f"• 1위 목표: {format_number(top1_mobile)}원 이상 입찰")
    
    if efficient_bid:
        lines.append(f"• 효율 입찰: {format_number(efficient_bid)}원 (월 {efficient_clicks}클릭)")
        
        start_min = int(efficient_bid * 0.5)
        start_max = int(efficient_bid * 0.7)
        start_min = max(start_min, 100)
        lines.append(f"• 시작가: {format_number(start_min)}~{format_number(start_max)}원 권장")
        
        daily_budget = max(efficient_cost / 30, 10000)
        lines.append(f"• 일 예산: {format_won(daily_budget)}")
    else:
        lines.append("• 시작가: 100~500원")
        lines.append("• 일 예산: 5,000~10,000원")
    
    lines.append("• 예상 CTR: 모바일 2.3% / PC 1.1%")
    
    return "\n".join(lines)


# ===== 나머지 함수들 (운세, 로또, 대표키워드, 자동완성, 도움말 등) =====
# (기존 코드 그대로 유지 - 너무 길어서 생략)

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


def get_help():
    return """[사용 가이드]

▶ 키워드 검색량 (최대 5개)
방법) 키워드1, 키워드2, 키워드3, 키워드4, 키워드5
예) 인천맛집,강남맛집,서울맛집,부산맛집,전주맛집

▶ 상권분석 (트렌드+매출+고객)
방법) 상권+키워드
예) 상권 강남맛집

▶ 연관 검색어
방법) 연관+키워드
예) 연관 인천맛집

▶ 자동완성어
방법) 자동+키워드
예) 자동 인천맛집

▶ CPC 파워링크 광고 단가
방법) 광고+키워드
예) 광고 인천맛집

▶ 대표 키워드
방법) 대표+플레이스ID
방법) 대표+플레이스 주소
예) 대표 12345678
예) 대표 m.place.naver.com/restaurant/1309812619/home

▶ 재미 기능
운세 → 운세 870114
로또 → 로또

기능 추가를 원하시면 소식에 댓글 남겨주세요."""


#############################################
# 테스트 라우트
#############################################
@app.route('/')
def home():
    return "서버 정상 작동 중"


@app.route('/test-review')
def test_review():
    keyword = request.args.get('q', '부평맛집')
    result = get_place_reviews(keyword)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>리뷰 수집 테스트</title></head>
<body>
<h2>키워드: {keyword}</h2>
<p><b>성공:</b> {result.get('success')}</p>
<p><b>평균 리뷰:</b> {result.get('avg_review', 'N/A')}</p>
<p><b>평균 블로그:</b> {result.get('avg_blog', 'N/A')}</p>
<p><b>수집 개수:</b> 리뷰 {result.get('review_count', 0)}개 / 블로그 {result.get('blog_count', 0)}개</p>
"""
    if result.get('reviews'):
        html += f"<p><b>리뷰 리스트:</b> {result['reviews']}</p>"
    if result.get('error'):
        html += f"<p style='color:red'>오류: {result['error']}</p>"
    html += "</body></html>"
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/test-commercial')
def test_commercial():
    keyword = request.args.get('q', '부평맛집')
    analysis = get_commercial_analysis(keyword)
    result = format_commercial_analysis(analysis)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>상권분석 테스트</title></head>
<body>
<h2>키워드: {keyword}</h2>
<h3>글자 수: {len(result)}자</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
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


@app.route('/test-ad')
def test_ad():
    keyword = request.args.get('q', '부평맛집')
    result = get_ad_cost(keyword)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>광고분석 테스트</title></head>
<body>
<h2>키워드: {keyword}</h2>
<h3>글자 수: {len(result)}자</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/test-position')
def test_position():
    keyword = request.args.get('q', '부평맛집')
    
    logger.info(f"========== 순위별 입찰가 테스트 시작: {keyword} ==========")
    result = get_position_bids(keyword)
    logger.info(f"========== 테스트 종료 ==========")
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>순위별 입찰가 테스트</title></head>
<body style="font-family: monospace; padding: 20px;">
<h2>키워드: {keyword}</h2>
<h3 style="color: {'green' if result.get('success') else 'red'}">
    {'✅ 성공' if result.get('success') else '❌ 실패'}
</h3>
"""
    
    if result.get('api_used'):
        html += f"<p><b>사용된 방식:</b> <code>{result['api_used']}</code></p>"
    
    html += f"""
<div style="background: #f5f5f5; padding: 15px; margin: 10px 0;">
    <h4>원본 응답:</h4>
    <pre>{json.dumps(result, ensure_ascii=False, indent=2)}</pre>
</div>
"""
    
    if result.get('success'):
        html += """
<div style="background: white; padding: 20px; margin: 20px 0; border: 1px solid #ddd;">
<h3>네이버 파워링크 입찰가</h3>
<br>
"""
        for pos in [1, 2, 3, 4, 5]:
            pc_bid = result['pc'].get(pos, 0)
            mobile_bid = result['mobile'].get(pos, 0)
            html += f"""
<div style="margin-bottom: 15px;">
    <b>{pos}위</b><br>
    PC: {format_number(pc_bid)}원<br>
    MOBILE: {format_number(mobile_bid)}원
</div>
"""
        
        today = date.today()
        if today.month == 1:
            start_date = date(today.year - 1, 12, 1)
            end_date = date(today.year, 1, 1)
        else:
            start_date = date(today.year, today.month - 1, 1)
            end_date = date(today.year, today.month, 1)
        
        html += f"""
<div style="border-top: 1px solid #ddd; padding-top: 10px; margin-top: 10px;">
통계 기간: {start_date.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}
</div>
</div>
"""
    else:
        html += f"""
<div style="background: #ffebee; padding: 15px; margin: 10px 0; color: #c62828;">
    <h4>오류 메시지:</h4>
    <p>{result.get('error', '알 수 없는 오류')}</p>
</div>
"""
    
    html += "</body></html>"
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
        
        if lower_input in ["도움말", "도움", "사용법", "help", "?", "메뉴"]:
            return create_kakao_response(get_help())
        
        if lower_input.startswith("운세 "):
            birthdate = ''.join(filter(str.isdigit, user_utterance))
            if birthdate and len(birthdate) in [6, 8]:
                return create_kakao_response(get_fortune(birthdate))
            return create_kakao_response("생년월일 6자리/8자리 입력\n예) 운세 870114")
        
        if lower_input in ["운세", "오늘의운세", "오늘운세"]:
            return create_kakao_response(get_fortune())
        
        if lower_input in ["로또", "로또번호", "lotto"]:
            return create_kakao_response(get_lotto())
        
        if any(lower_input.startswith(cmd) for cmd in ["상권 ", "상세 ", "인사이트 ", "트렌드 "]):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                analysis = get_commercial_analysis(keyword)
                return create_kakao_response(format_commercial_analysis(analysis))
            return create_kakao_response("예) 상권 부평맛집")
        
        if lower_input.startswith("자동 ") or lower_input.startswith("자동완성 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if keyword:
                return create_kakao_response(get_autocomplete(keyword))
            return create_kakao_response("예) 자동 부평맛집")
        
        if lower_input.startswith("대표 ") or lower_input.startswith("대표키워드 "):
            input_text = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if input_text:
                return create_kakao_response(format_place_keywords(input_text))
            return create_kakao_response("예) 대표 37838432")
        
        if lower_input.startswith("연관 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_related_keywords(keyword))
            return create_kakao_response("예) 연관 맛집")
        
        if lower_input.startswith("광고 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_ad_cost(keyword))
            return create_kakao_response("예) 광고 맛집")
        
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
