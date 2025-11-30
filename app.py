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
        logger.warning(f"⚠️  Missing required keys: {', '.join(missing)}")
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

def get_keyword_data(keyword, retry=2):
    """키워드 데이터 조회 (재시도 로직 포함)"""
    if not validate_required_keys():
        return {"success": False, "error": "API 키가 설정되지 않았습니다."}
    
    base_url = "https://api.searchad.naver.com"
    uri = "/keywordstool"
    params = {"hintKeywords": keyword, "showDetail": "1"}
    
    for attempt in range(retry + 1):
        try:
            headers = get_naver_api_headers("GET", uri)
            response = requests.get(base_url + uri, headers=headers, params=params, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                keyword_list = data.get("keywordList", [])
                if keyword_list:
                    return {"success": True, "data": keyword_list}
                return {"success": False, "error": "검색 결과가 없습니다."}
            
            if attempt < retry:
                logger.debug(f"재시도 {attempt + 1}/{retry}: {keyword}")
                time.sleep(0.5)
                continue
            
            return {"success": False, "error": f"API 오류 ({response.status_code})"}
            
        except requests.Timeout:
            if attempt < retry:
                logger.debug(f"타임아웃 재시도 {attempt + 1}/{retry}")
                time.sleep(0.5)
                continue
            return {"success": False, "error": "요청 시간 초과"}
        except Exception as e:
            logger.error(f"키워드 조회 오류: {str(e)}")
            if attempt < retry:
                time.sleep(0.5)
                continue
            return {"success": False, "error": str(e)}


#############################################
# CPC API
#############################################
def get_performance_estimate(keyword, bids, device='MOBILE', retry=2):
    """성과 예측 API (재시도 로직 포함)"""
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
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            
            if attempt < retry:
                logger.debug(f"성과 예측 재시도 {attempt + 1}/{retry}")
                time.sleep(0.5)
                continue
            
            return {"success": False, "error": response.text}
            
        except requests.Timeout:
            if attempt < retry:
                logger.debug(f"타임아웃 재시도 {attempt + 1}/{retry}")
                time.sleep(0.5)
                continue
            return {"success": False, "error": "요청 시간 초과"}
        except Exception as e:
            logger.error(f"성과 예측 오류: {str(e)}")
            if attempt < retry:
                time.sleep(0.5)
                continue
            return {"success": False, "error": str(e)}


#############################################
# DataLab 트렌드 API
#############################################
def get_datalab_trend(keyword, retry=2):
    """트렌드 데이터 조회 (재시도 로직 포함)"""
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
    
    for attempt in range(retry + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=5)
            
            if response.status_code == 200:
                data = response.json()
                results = data.get("results", [])
                if results and results[0].get("data"):
                    return {"success": True, "data": results[0]["data"]}
            
            if attempt < retry:
                logger.debug(f"트렌드 재시도 {attempt + 1}/{retry}")
                time.sleep(0.5)
                continue
            
            return {"success": False, "error": "트렌드 데이터 없음"}
            
        except requests.Timeout:
            if attempt < retry:
                time.sleep(0.5)
                continue
            return {"success": False, "error": "요청 시간 초과"}
        except Exception as e:
            logger.error(f"트렌드 조회 오류: {str(e)}")
            if attempt < retry:
                time.sleep(0.5)
                continue
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
    
    COMP_RATIO = {
        '높음': 0.08,
        '중간': 0.05,
        '낮음': 0.03
    }
    
    base_ratio = COMP_RATIO.get(comp_idx, 0.05)
    estimated = int(search_volume * base_ratio)
    
    REGION_MULTIPLIER = {
        '강남': 1.3, '홍대': 1.3, '잠실': 1.3, '해운대': 1.3,
        '계양': 0.7, '일산': 0.7
    }
    
    if region and region in REGION_MULTIPLIER:
        estimated = int(estimated * REGION_MULTIPLIER[region])
    
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
    
    COMP_MULTIPLIER = {'높음': 1.2, '낮음': 0.8}
    multiplier = COMP_MULTIPLIER.get(comp_idx, 1.0)
    
    avg_review = int(avg_review * multiplier)
    avg_blog = int(avg_blog * multiplier)
    
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
    
    test_bids = [
        100, 200, 300, 400, 500, 600, 700, 800, 900, 1000,
        1200, 1500, 1800, 2000, 2200, 2500, 3000, 3500, 4000, 5000,
        6000, 7000, 8000, 10000, 15000
    ]
    
    mobile_perf = get_performance_estimate(keyword_name, test_bids, 'MOBILE')
    
    efficient_bid = None
    efficient_clicks = 0
    efficient_cost = 0
    daily_budget = 10000
    unique_selected = []
    
    if mobile_perf.get("success"):
        mobile_estimates = mobile_perf["data"].get("estimate", [])
        valid_estimates = [e for e in mobile_estimates if e.get('clicks', 0) > 0]
        
        if valid_estimates:
            lines.append("━━━━━━━━━━━━━━")
            lines.append("📱 모바일 성과 분석")
            lines.append("━━━━━━━━━━━━━━")
            lines.append("")
            lines.append("입찰가별 예상 성과")
            lines.append("")
            
            max_clicks = max(e.get('clicks', 0) for e in valid_estimates)
            
            first_max_bid = None
            for e in sorted(valid_estimates, key=lambda x: x.get('bid', 0)):
                if e.get('clicks', 0) == max_clicks:
                    first_max_bid = e.get('bid', 0)
                    break
            
            target_ratios = [0.2, 0.4, 0.6, 0.8, 1.0]
            selected_bids = []

            for i, ratio in enumerate(target_ratios):
                target_clicks = int(max_clicks * ratio)
                closest = min(valid_estimates, 
                            key=lambda x: abs(x.get('clicks', 0) - target_clicks))
                selected_bids.append(closest)

            seen_bids = set()
            unique_selected = []
            for e in selected_bids:
                bid = e.get('bid', 0)
                if bid not in seen_bids:
                    seen_bids.add(bid)
                    unique_selected.append(e)

            max_clicks_in_selected = max(e.get('clicks', 0) for e in unique_selected) if unique_selected else 0

            attempt_count = 0
            while len(unique_selected) < 5 and attempt_count < len(valid_estimates):
                for e in sorted(valid_estimates, key=lambda x: x.get('bid', 0)):
                    bid = e.get('bid', 0)
                    clicks = e.get('clicks', 0)
                    
                    if bid in seen_bids:
                        continue
                    
                    if clicks == max_clicks_in_selected:
                        continue
                    
                    if any(e2.get('clicks', 0) == clicks for e2 in unique_selected):
                        continue
                    
                    unique_selected.append(e)
                    seen_bids.add(bid)
                    break
                else:
                    break
                attempt_count += 1

            first_max_bid_in_selected = None
            for e in sorted(unique_selected, key=lambda x: x.get('bid', 0)):
                if e.get('clicks', 0) == max_clicks_in_selected:
                    first_max_bid_in_selected = e.get('bid', 0)
                    break

            if first_max_bid_in_selected:
                candidates = [e for e in valid_estimates 
                            if e.get('clicks', 0) == max_clicks_in_selected
                            and e.get('bid', 0) > first_max_bid_in_selected]
                if candidates:
                    next_bid = min(candidates, key=lambda x: x.get('bid', 0))
                    if next_bid.get('bid', 0) not in seen_bids:
                        unique_selected.append(next_bid)

            unique_selected.sort(key=lambda x: x.get('bid', 0))
            
            efficient_est = None
            if len(unique_selected) >= 5:
                efficient_est = unique_selected[4]
            elif len(unique_selected) >= 3:
                efficient_est = unique_selected[-1]
            elif len(unique_selected) > 0:
                efficient_est = unique_selected[0]
            
            if efficient_est:
                efficient_bid = efficient_est.get('bid', 0)
                efficient_clicks = efficient_est.get('clicks', 0)
                efficient_cost = efficient_est.get('cost', 0)
                
                if efficient_cost == 0:
                    efficient_cost = int(efficient_clicks * efficient_bid * 0.8)
            
            for est in unique_selected:
                bid = est.get('bid', 0)
                clicks = est.get('clicks', 0)
                cost = est.get('cost', 0)
                
                if cost == 0:
                    cost = int(clicks * bid * 0.8)
                
                lines.append(f"{format_number(bid)}원 → 월 {clicks}회 클릭 | {format_won(cost)}")
            
            if first_max_bid_in_selected:
                lines.append(f"  ↑ {format_number(first_max_bid_in_selected)}원 이상은 효과 동일")
            
            if len(unique_selected) < 5:
                lines.append("")
                lines.append("※ 입찰가 데이터 부족으로 일부만 표시")
            
            lines.append("")
    
    if efficient_bid:
        lines.append("━━━━━━━━━━━━━━")
        lines.append("🎯 추천 입찰가")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        lines.append(f"✅ 추천: {format_number(efficient_bid)}원")
        lines.append(f"├ 예상 클릭: 월 {efficient_clicks}회")
        lines.append(f"├ 예상 비용: 월 {format_won(efficient_cost)}")
        
        cpc = int(efficient_cost / efficient_clicks) if efficient_clicks > 0 else 0
        lines.append(f"├ 클릭당 비용: 약 {format_number(cpc)}원")
        
        daily_budget = max(efficient_cost / 30, 10000)
        lines.append(f"└ 일 예산: 약 {format_won(daily_budget)}")
        lines.append("")
        
        if len(unique_selected) >= 4:
            lower_est = unique_selected[max(0, len(unique_selected) - 3)]
            lower_bid = lower_est.get('bid', 0)
            lower_clicks = lower_est.get('clicks', 0)
            lower_cost = lower_est.get('cost', 0)
            
            if lower_cost == 0:
                lower_cost = int(lower_clicks * lower_bid * 0.8)
            
            if lower_bid < efficient_bid:
                lines.append(f"※ 예산 적으면 {format_number(lower_bid)}원도 가능 (월 {lower_clicks}회/{format_won(lower_cost)})")
        
        lines.append("")
    
    pc_perf = get_performance_estimate(keyword_name, test_bids, 'PC')
    
    if pc_perf.get("success"):
        pc_estimates = pc_perf["data"].get("estimate", [])
        valid_pc = [e for e in pc_estimates if e.get('clicks', 0) > 0]
        
        if valid_pc:
            best_pc = max(valid_pc, key=lambda x: x.get('clicks', 0))
            pc_bid = best_pc.get('bid', 0)
            pc_clicks = best_pc.get('clicks', 0)
            pc_cost = best_pc.get('cost', 0)
            
            if pc_cost == 0:
                pc_cost = int(pc_clicks * pc_bid * 0.8)
            
            lines.append("━━━━━━━━━━━━━━")
            lines.append("💻 PC 예상 성과")
            lines.append("━━━━━━━━━━━━━━")
            lines.append("")
            lines.append(f"추천: {format_number(pc_bid)}원")
            lines.append(f"├ 예상 클릭: 월 {pc_clicks}회")
            lines.append(f"└ 예상 비용: 월 {format_won(pc_cost)}")
            lines.append("")
    
    if efficient_bid:
        lines.append("━━━━━━━━━━━━━━")
        lines.append("📋 운영 가이드")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        lines.append("시작 설정")
        lines.append(f"• 입찰가: {format_number(efficient_bid)}원")
        lines.append(f"• 일 예산: {format_won(daily_budget)}")
        lines.append(f"• 월 예산: 약 {format_won(efficient_cost)}")
        lines.append("")
        lines.append("운영 팁")
        lines.append("• 1주일 후 CTR 확인 (1.5% 이상 목표)")
        lines.append("• 전환 발생 시 예산 증액 검토")
        lines.append("• 품질점수 관리로 CPC 절감 가능")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
    
    return "\n".join(lines)


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
# 기능 8: 네이버 자동완성
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
# 기능 9: 유튜브 자동완성어 (신규)
#############################################
def get_youtube_autocomplete(keyword):
    """유튜브 자동완성 키워드 수집"""
    try:
        url = "https://suggestqueries.google.com/complete/search"
        params = {
            "client": "youtube",
            "ds": "yt",
            "q": keyword,
            "hl": "ko",
            "gl": "kr"
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=5)
        
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
                    for i, s in enumerate(suggestions[:15], 1):
                        result += f"{i}. {s}\n"
                    result += f"\n총 {len(suggestions[:15])}개"
                    return result
        
        return f"[유튜브 자동완성] {keyword}\n\n결과 없음"
        
    except Exception as e:
        logger.error(f"유튜브 자동완성 오류: {str(e)}")
        return f"[유튜브 자동완성] {keyword}\n\n조회 실패: {str(e)}"


#############################################
# 기능 10: 플레이스 순위 조회 (신규)
#############################################
def get_place_ranking(keyword, place_id):
    """네이버 플레이스에서 특정 업체의 순위 조회"""
    
    headers = {
        "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "ko-KR,ko;q=0.9",
        "Referer": "https://m.place.naver.com/"
    }
    
    try:
        search_url = f"https://map.naver.com/v5/api/search?caller=pcweb&query={quote(keyword)}&type=all&page=1&displayCount=100"
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        place_ids = []
        place_names = {}
        
        if response.status_code == 200:
            try:
                data = response.json()
                
                if "result" in data and "place" in data["result"]:
                    place_list = data["result"]["place"].get("list", [])
                    for item in place_list:
                        pid = str(item.get("id", ""))
                        name = item.get("name", "")
                        if pid:
                            place_ids.append(pid)
                            place_names[pid] = name
            except:
                pass
        
        if len(place_ids) < 10:
            mobile_url = f"https://m.search.naver.com/search.naver?where=m_local&query={quote(keyword)}"
            response2 = requests.get(mobile_url, headers=headers, timeout=10)
            
            if response2.status_code == 200:
                html = response2.text
                
                patterns = [
                    r'place/(\d{7,})',
                    r'restaurant/(\d{7,})',
                    r'cafe/(\d{7,})',
                    r'"id"\s*:\s*"?(\d{7,})"?',
                    r'data-id="(\d{7,})"'
                ]
                
                for pattern in patterns:
                    matches = re.findall(pattern, html)
                    for match in matches:
                        if match not in place_ids:
                            place_ids.append(match)
        
        seen = set()
        unique_ids = []
        for pid in place_ids:
            if pid not in seen:
                seen.add(pid)
                unique_ids.append(pid)
        
        place_ids = unique_ids[:100]
        
        target_id = str(place_id).strip()
        
        if target_id in place_ids:
            rank = place_ids.index(target_id) + 1
            place_name = place_names.get(target_id, "")
            
            if rank == 1:
                rank_emoji = "🥇"
            elif rank == 2:
                rank_emoji = "🥈"
            elif rank == 3:
                rank_emoji = "🥉"
            elif rank <= 5:
                rank_emoji = "⭐"
            elif rank <= 10:
                rank_emoji = "✅"
            elif rank <= 20:
                rank_emoji = "📍"
            else:
                rank_emoji = "📌"
            
            result = f"[플레이스 순위] {keyword}\n\n"
            result += f"{rank_emoji} 현재 순위: {rank}위\n\n"
            result += f"플레이스 ID: {target_id}\n"
            if place_name:
                result += f"업체명: {place_name}\n"
            result += f"\n총 검색 업체: {len(place_ids)}개\n"
            
            if rank > 1:
                result += f"\n▸ 상위 업체\n"
                start = max(0, rank - 4)
                for i in range(start, rank - 1):
                    pid = place_ids[i]
                    name = place_names.get(pid, pid)
                    result += f"  {i+1}위: {name[:15]}\n"
            
            result += f"\n▸ 내 업체\n"
            result += f"  ➤ {rank}위: {place_name if place_name else target_id}\n"
            
            if rank < len(place_ids):
                result += f"\n▸ 하위 업체\n"
                end = min(len(place_ids), rank + 3)
                for i in range(rank, end):
                    pid = place_ids[i]
                    name = place_names.get(pid, pid)
                    result += f"  {i+1}위: {name[:15]}\n"
            
            result += "\n━━━━━━━━━━━━━━\n"
            if rank <= 3:
                result += "💡 상위권 유지 중! 리뷰 관리 필수"
            elif rank <= 10:
                result += "💡 10위권! 리뷰 10개 추가로 순위 상승 가능"
            elif rank <= 20:
                result += "💡 20위권, 블로그+리뷰 병행 필요"
            else:
                result += "💡 집중 마케팅 필요 (리뷰/블로그/광고)"
            
            return result
        
        else:
            result = f"[플레이스 순위] {keyword}\n\n"
            result += f"❌ 순위권 외 (100위 밖)\n\n"
            result += f"플레이스 ID: {target_id}\n"
            result += f"검색된 업체 수: {len(place_ids)}개\n"
            result += "\n━━━━━━━━━━━━━━\n"
            result += "💡 100위 밖은 노출 효과 거의 없음\n"
            result += "💡 플레이스 광고 또는 리뷰 확보 필요"
            
            if place_ids[:5]:
                result += "\n\n▸ 현재 상위 5개 업체\n"
                for i, pid in enumerate(place_ids[:5], 1):
                    name = place_names.get(pid, pid)
                    result += f"  {i}위: {name[:20]}\n"
            
            return result
    
    except Exception as e:
        logger.error(f"순위 조회 오류: {str(e)}")
        return f"[플레이스 순위] 조회 실패\n\n오류: {str(e)}"


def parse_ranking_input(user_input):
    """순위 조회 입력 파싱: '순위 키워드 플레이스ID'"""
    
    text = user_input.strip()
    if text.startswith("순위 "):
        text = text[3:].strip()
    elif text.startswith("순위"):
        text = text[2:].strip()
    
    words = text.split()
    
    place_id = None
    keyword_parts = []
    
    for i, word in enumerate(reversed(words)):
        extracted = extract_place_id_from_url(word)
        if extracted:
            place_id = extracted
            keyword_parts = words[:len(words) - i - 1]
            break
        elif word.isdigit() and len(word) >= 7:
            place_id = word
            keyword_parts = words[:len(words) - i - 1]
            break
    
    keyword = " ".join(keyword_parts).strip()
    
    return keyword, place_id


#############################################
# 도움말
#############################################
def get_help():
    return """[사용 가이드]

▶ 키워드 검색량 (최대 5개)
예) 인천맛집,강남맛집,서울맛집

▶ 상권분석 (트렌드+매출+고객)
예) 상권 강남맛집

▶ 연관 검색어
예) 연관 인천맛집

▶ 자동완성어 (네이버)
예) 자동 인천맛집

▶ 유튜브 자동완성어
예) 유튜브 인천맛집

▶ CPC 광고 단가
예) 광고 인천맛집

▶ 대표 키워드
예) 대표 12345678

▶ 플레이스 순위 조회
예) 순위 부평맛집 12345678

▶ 재미 기능
예) 운세 870114
예) 로또"""


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


@app.route('/test-youtube')
def test_youtube():
    keyword = request.args.get('q', '부평맛집')
    result = get_youtube_autocomplete(keyword)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>유튜브 자동완성 테스트</title></head>
<body>
<h2>키워드: {keyword}</h2>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}


@app.route('/test-ranking')
def test_ranking():
    keyword = request.args.get('q', '부평맛집')
    place_id = request.args.get('id', '1234567890')
    result = get_place_ranking(keyword, place_id)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>플레이스 순위 테스트</title></head>
<body>
<h2>키워드: {keyword}</h2>
<h3>플레이스 ID: {place_id}</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
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
        
        # 상권분석
        if any(lower_input.startswith(cmd) for cmd in ["상권 ", "상세 ", "인사이트 ", "트렌드 "]):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                analysis = get_commercial_analysis(keyword)
                return create_kakao_response(format_commercial_analysis(analysis))
            return create_kakao_response("예) 상권 부평맛집")
        
        # 유튜브 자동완성 (신규)
        if lower_input.startswith("유튜브 ") or lower_input.startswith("yt "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if keyword:
                return create_kakao_response(get_youtube_autocomplete(keyword))
            return create_kakao_response("예) 유튜브 부평맛집")
        
        # 네이버 자동완성
        if lower_input.startswith("자동 ") or lower_input.startswith("자동완성 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if keyword:
                return create_kakao_response(get_autocomplete(keyword))
            return create_kakao_response("예) 자동 부평맛집")
        
        # 플레이스 순위 조회 (신규)
        if lower_input.startswith("순위 "):
            keyword, place_id = parse_ranking_input(user_utterance)
            if keyword and place_id:
                return create_kakao_response(get_place_ranking(keyword, place_id))
            return create_kakao_response("예) 순위 부평맛집 1234567890\n예) 순위 강남맛집 place.naver.com/restaurant/12345")
        
        # 대표키워드
        if lower_input.startswith("대표 ") or lower_input.startswith("대표키워드 "):
            input_text = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if input_text:
                return create_kakao_response(format_place_keywords(input_text))
            return create_kakao_response("예) 대표 37838432")
        
        # 연관 키워드
        if lower_input.startswith("연관 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_related_keywords(keyword))
            return create_kakao_response("예) 연관 맛집")
        
        # 광고 단가
        if lower_input.startswith("광고 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_ad_cost(keyword))
            return create_kakao_response("예) 광고 맛집")
        
        # 기본: 검색량 조회
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
    
    if validate_required_keys():
        print("✅ 필수 API 키 확인 완료")
    else:
        print("⚠️  일부 기능이 제한될 수 있습니다")
    
    print("====================")
    
    if os.environ.get('PRODUCTION') == 'true':
        logging.basicConfig(level=logging.WARNING)
        logger.setLevel(logging.WARNING)
        print("운영 모드: WARNING 레벨 로그")
    else:
        print("개발 모드: INFO 레벨 로그")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

