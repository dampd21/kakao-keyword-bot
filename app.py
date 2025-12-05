from flask import Flask, request, jsonify
import hashlib
import hmac
import base64
import time
import requests
import os
import re
import json
import logging
import asyncio
from datetime import date, timedelta
from urllib.parse import quote
from functools import wraps

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

#############################################
# 지역 데이터
#############################################
REGION_DATA = {
    "부평동": {
        "sigunCd": "28260",
        "sigunNm": "부평구",
        "admCd": "2826010100",
        "fullName": "인천광역시 부평구 부평동",
        "commercial_area": "2826051500"
    },
    "부개동": {
        "sigunCd": "28260",
        "sigunNm": "부평구",
        "admCd": "2826010200",
        "fullName": "인천광역시 부평구 부개동",
        "commercial_area": "2826051500"
    },
    "계산동": {
        "sigunCd": "28245",
        "sigunNm": "계양구",
        "admCd": "2824510100",
        "fullName": "인천광역시 계양구 계산동",
        "commercial_area": "2824551500"
    },
    "송도동": {
        "sigunCd": "28185",
        "sigunNm": "연수구",
        "admCd": "2818510800",
        "fullName": "인천광역시 연수구 송도동",
        "commercial_area": "2818551500"
    },
    "역삼동": {
        "sigunCd": "11680",
        "sigunNm": "강남구",
        "admCd": "1168010100",
        "fullName": "서울특별시 강남구 역삼동",
        "commercial_area": "1168051000"
    },
    "논현동": {
        "sigunCd": "11680",
        "sigunNm": "강남구",
        "admCd": "1168010600",
        "fullName": "서울특별시 강남구 논현동",
        "commercial_area": "1168051000"
    },
    "홍대": {
        "sigunCd": "11440",
        "sigunNm": "마포구",
        "admCd": "1144012400",
        "fullName": "서울특별시 마포구 동교동",
        "commercial_area": "1144051000"
    },
    "서초동": {
        "sigunCd": "11650",
        "sigunNm": "서초구",
        "admCd": "1165010100",
        "fullName": "서울특별시 서초구 서초동",
        "commercial_area": "1165051000"
    },
    "잠실동": {
        "sigunCd": "11710",
        "sigunNm": "송파구",
        "admCd": "1171010100",
        "fullName": "서울특별시 송파구 잠실동",
        "commercial_area": "1171051000"
    },
    "우동": {
        "sigunCd": "26260",
        "sigunNm": "해운대구",
        "admCd": "2626010200",
        "fullName": "부산광역시 해운대구 우동",
        "commercial_area": "2626051000"
    },
    "서면": {
        "sigunCd": "26170",
        "sigunNm": "부산진구",
        "admCd": "2617010400",
        "fullName": "부산광역시 부산진구 부전동",
        "commercial_area": "2617051000"
    },
    "분당동": {
        "sigunCd": "41135",
        "sigunNm": "성남시 분당구",
        "admCd": "4113510300",
        "fullName": "경기도 성남시 분당구 분당동",
        "commercial_area": "4113551000"
    },
    "백석동": {
        "sigunCd": "41287",
        "sigunNm": "고양시 일산동구",
        "admCd": "4128710100",
        "fullName": "경기도 고양시 일산동구 백석동",
        "commercial_area": "4128751000"
    },
    "인계동": {
        "sigunCd": "41111",
        "sigunNm": "수원시 팔달구",
        "admCd": "4111110700",
        "fullName": "경기도 수원시 팔달구 인계동",
        "commercial_area": "4111151000"
    }
}

#############################################
# 업종 코드
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
# 네이버 API 헤더
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

#############################################
# 기능 1: 비교 [키워드]
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
    
    # 올해 데이터
    today = date.today()
    this_year_start = f"{today.year}-{today.month:02d}-01"
    this_year_end = today.strftime("%Y-%m-%d")
    
    # 작년 데이터
    last_year = today.year - 1
    last_year_start = f"{last_year}-{today.month:02d}-01"
    last_year_end = f"{last_year}-{today.month:02d}-{today.day:02d}"
    
    # 병렬 조회는 간단히 순차로 처리 (동기)
    trend_2025 = get_datalab_trend(keyword, this_year_start, this_year_end)
    trend_2024 = get_datalab_trend(keyword, last_year_start, last_year_end)
    
    if not trend_2025["success"] or not trend_2024["success"]:
        return None
    
    # 월별 데이터 계산
    data_2025 = trend_2025["data"]
    data_2024 = trend_2024["data"]
    
    # 최근 6개월
    recent_6_months_2025 = data_2025[-6:] if len(data_2025) >= 6 else data_2025
    recent_6_months_2024 = data_2024[-6:] if len(data_2024) >= 6 else data_2024
    
    # 평균 계산 (ratio 기반, 실제 검색량은 비율로만 제공됨)
    avg_2025 = sum(d.get("ratio", 0) for d in data_2025) / len(data_2025) if data_2025 else 0
    avg_2024 = sum(d.get("ratio", 0) for d in data_2024) / len(data_2024) if data_2024 else 0
    
    # 증감률
    change_rate = ((avg_2025 - avg_2024) / avg_2024 * 100) if avg_2024 > 0 else 0
    
    # 가상 검색량 (ratio를 100배 스케일링)
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
        return "[검색량 비교] 조회 실패\n\nDataLab API 오류가 발생했습니다.\n잠시 후 다시 시도해주세요."
    
    keyword = analysis["keyword"]
    vol_2025 = analysis["volume_2025"]
    vol_2024 = analysis["volume_2024"]
    change_rate = analysis["change_rate"]
    
    # 모바일/PC 비율 (가정: 모바일 75%)
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
        lines.append("✅ 검색 광고 적극 추천")
    elif change_rate >= 10:
        lines.append(f"✅ 지속 성장 중 ({sign}{change_rate:.1f}%)")
        lines.append("→ 검색 광고 시작 적기")
    elif change_rate >= -10:
        lines.append(f"➡️ 안정적 유지 ({sign}{change_rate:.1f}%)")
        lines.append("→ 꾸준한 마케팅 필요")
    else:
        lines.append(f"⚠️ 검색 감소 중 ({change_rate:.1f}%)")
        lines.append("→ SNS 바이럴 필요")
    
    lines.append("✅ 모바일 최적화 필수 (75%)")
    
    return "\n".join(lines)

#############################################
# 기능 2: 지역 [동]
#############################################
def get_population_data(region_data):
    """유동인구 데이터 조회 (가상 데이터)"""
    
    # 실제 공공데이터 API 호출 시뮬레이션
    # 실제로는 API 호출 필요
    
    import random
    
    # 지역별 기본 유동인구 (가상)
    base_population = {
        "부평동": 8200,
        "역삼동": 15000,
        "홍대": 25000,
        "송도동": 12000
    }
    
    region_name = region_data.get("fullName", "").split()[-1]
    daily_avg = base_population.get(region_name, 10000)
    
    return {
        "success": True,
        "daily_avg": daily_avg,
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
            "0709": int(daily_avg * 0.22),
            "1213": int(daily_avg * 0.29),
            "1819": int(daily_avg * 0.34),
            "2022": int(daily_avg * 0.15)
        },
        "weekday_vs_weekend": {
            "weekday": int(daily_avg * 1.07),
            "weekend": int(daily_avg * 0.88)
        }
    }

def format_region_analysis(region_name):
    """지역 분석 포맷팅"""
    
    if region_name not in REGION_DATA:
        available = ", ".join(list(REGION_DATA.keys())[:10])
        return f"[지역분석] 오류\n\n'{region_name}' 지역을 찾을 수 없습니다.\n\n사용 가능한 지역:\n{available}\n\n예) 지역 부평동"
    
    region_data = REGION_DATA[region_name]
    pop_data = get_population_data(region_data)
    
    if not pop_data["success"]:
        return "[지역분석] 조회 실패\n\n유동인구 데이터를 가져올 수 없습니다."
    
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
    lines.append(f"├─ 07-09시: {format_number(time_data['0709'])}명 (출근)")
    lines.append(f"├─ 12-13시: {format_number(time_data['1213'])}명 (점심) 🔥")
    lines.append(f"├─ 18-19시: {format_number(time_data['1819'])}명 (퇴근) 🔥")
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
    
    # 지역별 특성 (하드코딩)
    characteristics = {
        "부평동": {
            "facilities": ["부평역 300m", "부평문화의거리", "오피스 빌딩 밀집"],
            "nature": "직장인 중심",
            "strength": ["역세권", "20-30대 58%", "평일 집중"],
            "weakness": ["주말 유동인구 감소", "주차 부족"]
        }
    }
    
    char = characteristics.get(region_name, {
        "facilities": ["상권 정보 수집 중"],
        "nature": "분석 중",
        "strength": ["데이터 분석 중"],
        "weakness": ["데이터 분석 중"]
    })
    
    lines.append("주요 시설:")
    for fac in char["facilities"]:
        lines.append(f"• {fac}")
    
    lines.append("")
    lines.append("상권 성격:")
    lines.append(f"• {char['nature']}")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 입지 인사이트")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    lines.append("✅ 강점")
    for s in char["strength"]:
        lines.append(f"• {s}")
    
    lines.append("")
    lines.append("⚠️ 약점")
    for w in char["weakness"]:
        lines.append(f"• {w}")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🎯 업종별 입지 적합도")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("음식점: ⭐⭐⭐⭐⭐")
    lines.append("• 점심/저녁 피크 강함")
    lines.append("")
    lines.append("카페: ⭐⭐⭐⭐")
    lines.append("• 오전 TO-GO 수요")
    lines.append("")
    lines.append("소매: ⭐⭐⭐")
    lines.append("• 퇴근시간 활용")
    
    return "\n".join(lines)

#############################################
# 기능 3: 매출 [동] [업종]
#############################################
def get_business_data(region_data, industry_keyword):
    """상가업소 데이터 조회 (가상)"""
    
    import random
    
    # 업종 코드 매칭
    industry_info = INDUSTRY_CODES.get(industry_keyword)
    if not industry_info:
        return {"success": False, "error": "업종을 찾을 수 없습니다"}
    
    # 가상 데이터
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
            "일식": random.randint(8, 25),
            "치킨": random.randint(15, 40)
        } if industry_keyword == "음식점" else {}
    }

def get_sales_data(region_data, industry_keyword):
    """매출 데이터 조회 (가상)"""
    
    import random
    
    # 업종별 기본 매출 (만원)
    base_sales = {
        "음식점": 2200,
        "한식": 2350,
        "카페": 1920,
        "병원": 4800,
        "학원": 3200
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
            "dinner": random.randint(35, 48),
            "other": 25
        },
        "weekday_ratio": random.randint(58, 72)
    }

def format_sales_analysis(region_name, industry_keyword):
    """매출 분석 포맷팅"""
    
    if region_name not in REGION_DATA:
        return f"[매출분석] 오류\n\n'{region_name}' 지역을 찾을 수 없습니다."
    
    if industry_keyword not in INDUSTRY_CODES:
        available = ", ".join(list(INDUSTRY_CODES.keys())[:15])
        return f"[매출분석] 오류\n\n'{industry_keyword}' 업종을 찾을 수 없습니다.\n\n사용 가능:\n{available}"
    
    region_data = REGION_DATA[region_name]
    business_data = get_business_data(region_data, industry_keyword)
    sales_data = get_sales_data(region_data, industry_keyword)
    
    lines = [f"[매출분석] {region_name} {industry_keyword}", ""]
    
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💰 평균 매출 현황")
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
    lines.append(f"🏪 업소 현황 ({region_name})")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    total = business_data["total"]
    lines.append(f"총 {industry_keyword}: {total}개")
    
    if business_data["by_type"]:
        lines.append("")
        lines.append("세부 업종:")
        for name, count in business_data["by_type"].items():
            ratio = (count / total) * 100
            lines.append(f"├─ {name}: {count}개 ({ratio:.1f}%)")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📊 개폐업 현황 (최근 1년)")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    opened = business_data["opened"]
    closed = business_data["closed"]
    net = opened - closed
    closure_rate = business_data["closure_rate"]
    
    lines.append(f"신규 개업: {opened}개")
    lines.append(f"폐업: {closed}개")
    sign = "+" if net >= 0 else ""
    lines.append(f"순증감: {sign}{net}개 ({sign}{(net/total)*100:.1f}%)")
    lines.append("")
    lines.append(f"폐업률: {closure_rate}%")
    
    if closure_rate >= 15:
        lines.append("⚠️⚠️ 높은 폐업률 주의")
    elif closure_rate >= 10:
        lines.append("⚠️ 경쟁 치열")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("🕐 시간대별 매출")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    time_dist = sales_data["time_dist"]
    lines.append(f"점심 (11-14시): {time_dist['lunch']}% 🔥")
    lines.append(f"저녁 (17-22시): {time_dist['dinner']}% 🔥")
    lines.append(f"기타: {time_dist['other']}%")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("📅 요일별 매출")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    weekday = sales_data["weekday_ratio"]
    weekend = 100 - weekday
    lines.append(f"평일: {weekday}%")
    lines.append(f"주말: {weekend}%")
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("💡 매출 인사이트")
    lines.append("━━━━━━━━━━━━━━━━━━━━━")
    lines.append("")
    
    if growth >= 10:
        lines.append(f"✅ 높은 성장세 (+{growth}%)")
    else:
        lines.append(f"➡️ 안정적 성장 (+{growth}%)")
    
    if closure_rate >= 15:
        lines.append("⚠️ 높은 폐업률 주의")
        lines.append("→ 차별화 전략 필수")
    elif closure_rate <= 8:
        lines.append("✅ 낮은 폐업률 (안정적)")
    
    lines.append("")
    lines.append("📌 성공 전략")
    
    if time_dist['lunch'] >= 35:
        lines.append("• 점심 시간대 집중 마케팅")
    if time_dist['dinner'] >= 40:
        lines.append("• 저녁 웨이팅 관리 필수")
    if weekday >= 65:
        lines.append("• 주말 배달 강화 필요")
    
    lines.append(f"• 객단가 {avg_price:,}원 이상 유지")
    
    return "\n".join(lines)

#############################################
# 도움말
#############################################
def get_help():
    return """[사용 가이드]

━━━━━━━━━━━━━━━━━━━━━
📊 1. 검색량 전년 비교
━━━━━━━━━━━━━━━━━━━━━

명령어: 비교 [키워드]

예시:
• 비교 부평맛집
• 비교 강남카페
• 비교 송도치킨

기능:
- 전년 동월 검색량 비교
- 월별 트렌드 그래프
- 성장률 분석

━━━━━━━━━━━━━━━━━━━━━
🗺️ 2. 지역 유동인구 분석
━━━━━━━━━━━━━━━━━━━━━

명령어: 지역 [동이름]

예시:
• 지역 부평동
• 지역 역삼동
• 지역 홍대

기능:
- 일평균 유동인구
- 연령/성별 분포
- 시간대별 유동량
- 입지 특성 분석

━━━━━━━━━━━━━━━━━━━━━
💰 3. 업종별 매출 분석
━━━━━━━━━━━━━━━━━━━━━

명령어: 매출 [동이름] [업종]

예시:
• 매출 부평동 음식점
• 매출 부평동 카페
• 매출 역삼동 병원
• 매출 홍대 학원

기능:
- 평균 매출/객단가
- 업소 개폐업 현황
- 시간대별 매출 분포
- 성공 전략 제시

━━━━━━━━━━━━━━━━━━━━━
📍 지원 지역
━━━━━━━━━━━━━━━━━━━━━

인천: 부평동, 부개동, 계산동, 송도동
서울: 역삼동, 논현동, 홍대, 서초동, 잠실동
부산: 우동, 서면
경기: 분당동, 백석동, 인계동

━━━━━━━━━━━━━━━━━━━━━
🏪 지원 업종
━━━━━━━━━━━━━━━━━━━━━

음식: 음식점, 한식, 중식, 일식, 치킨, 카페
의료: 병원, 치과, 한의원
교육: 학원, 입시학원, 외국어학원
기타: 편의점, 미용실, 부동산

━━━━━━━━━━━━━━━━━━━━━"""

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
            return create_kakao_response("명령어를 입력해주세요!\n\n도움말을 보려면 '도움말' 입력")
        
        lower_input = user_utterance.lower()
        
        # 도움말
        if lower_input in ["도움말", "도움", "사용법", "help", "?", "메뉴"]:
            return create_kakao_response(get_help())
        
        # 1. 비교 [키워드]
        if lower_input.startswith("비교 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if keyword:
                analysis = get_comparison_analysis(keyword)
                return create_kakao_response(format_comparison_analysis(analysis))
            return create_kakao_response("예) 비교 부평맛집")
        
        # 2. 지역 [동]
        if lower_input.startswith("지역 "):
            region = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            if region:
                return create_kakao_response(format_region_analysis(region))
            return create_kakao_response("예) 지역 부평동")
        
        # 3. 매출 [동] [업종]
        if lower_input.startswith("매출 "):
            parts = user_utterance.split(" ")
            if len(parts) >= 3:
                region = parts[1].strip()
                industry = parts[2].strip()
                return create_kakao_response(format_sales_analysis(region, industry))
            return create_kakao_response("예) 매출 부평동 음식점")
        
        # 기본 응답
        return create_kakao_response("명령어를 확인해주세요.\n\n도움말: '도움말' 입력")
        
    except Exception as e:
        logger.error(f"스킬 오류: {str(e)}")
        return create_kakao_response(f"오류가 발생했습니다.\n잠시 후 다시 시도해주세요.")

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
    return "상권분석 API 서버 정상 작동 중"

@app.route('/test/compare')
def test_compare():
    keyword = request.args.get('q', '부평맛집')
    analysis = get_comparison_analysis(keyword)
    result = format_comparison_analysis(analysis)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>비교 테스트</title></head>
<body>
<h2>키워드: {keyword}</h2>
<h3>글자 수: {len(result)}자</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/test/region')
def test_region():
    region = request.args.get('r', '부평동')
    result = format_region_analysis(region)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>지역 테스트</title></head>
<body>
<h2>지역: {region}</h2>
<h3>글자 수: {len(result)}자</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/test/sales')
def test_sales():
    region = request.args.get('r', '부평동')
    industry = request.args.get('i', '음식점')
    result = format_sales_analysis(region, industry)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>매출 테스트</title></head>
<body>
<h2>{region} {industry}</h2>
<h3>글자 수: {len(result)}자</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

#############################################
# 서버 실행
#############################################
if __name__ == '__main__':
    print("=== 환경변수 확인 ===")
    print(f"검색광고 API: {'✅' if NAVER_API_KEY else '❌'}")
    print(f"DataLab API: {'✅' if NAVER_CLIENT_ID else '❌'}")
    print(f"공공데이터 API: {'✅' if DATA_GO_KR_API_KEY else '❌'}")
    
    if validate_required_keys():
        print("✅ 필수 API 키 확인 완료")
    else:
        print("⚠️ 일부 기능이 제한될 수 있습니다")
    
    print("====================")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
