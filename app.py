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
from datetime import date
from urllib.parse import quote
import urllib.parse
import threading
from concurrent.futures import ThreadPoolExecutor

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

#############################################
# 사용자 세션 저장소 (메모리 기반)
#############################################
user_sessions = {}

#############################################
# API 캐시 (5분 유효)
#############################################
api_cache = {}
cache_lock = threading.Lock()

#############################################
# 순위별 노출 점유율 데이터
#############################################
IMPRESSION_SHARE_BY_RANK = {
    1: 85,   # 1위는 검색 10회 중 8~9회 노출
    2: 70,
    3: 55,
    4: 40,
    5: 30,
    6: 20,
    7: 15,
    8: 10
}

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
# 캐시 함수
#############################################
def get_with_cache(key, fetch_func, *args, ttl=300):
    """캐시 조회 → 없으면 fetch_func 실행"""
    with cache_lock:
        if key in api_cache:
            data, ts = api_cache[key]
            if time.time() - ts < ttl:
                logger.info(f"✅ 캐시 히트: {key}")
                return data
    
    logger.info(f"📡 API 호출: {key}")
    data = fetch_func(*args)
    
    with cache_lock:
        api_cache[key] = (data, time.time())
    
    return data

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
            response = requests.get(base_url + uri, headers=headers, params=params, timeout=2)
            
            if response.status_code == 200:
                data = response.json()
                keyword_list = data.get("keywordList", [])
                if keyword_list:
                    return {"success": True, "data": keyword_list}
                return {"success": False, "error": "검색 결과가 없습니다."}
            
            if attempt < retry:
                time.sleep(0.2)
                continue
            
            return {"success": False, "error": f"API 오류 ({response.status_code})"}
            
        except requests.Timeout:
            if attempt < retry:
                time.sleep(0.2)
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
            response = requests.post(url, headers=headers, json=payload, timeout=3)
            
            if response.status_code == 200:
                return {"success": True, "data": response.json()}
            
            if attempt < retry:
                time.sleep(0.2)
                continue
            
            return {"success": False, "error": response.text}
            
        except requests.Timeout:
            if attempt < retry:
                time.sleep(0.2)
                continue
            return {"success": False, "error": "요청 시간 초과"}
        except Exception as e:
            logger.error(f"성과 예측 오류: {str(e)}")
            return {"success": False, "error": str(e)}

#############################################
# 실시간 순위별 입찰가 API
#############################################
def get_real_rank_bids(keyword):
    """실시간 순위별 최소 입찰가 조회"""
    
    if not validate_required_keys():
        return {"success": False, "error": "API 키가 설정되지 않았습니다."}
    
    uri = '/estimate/bid-landscape'
    url = f'https://api.searchad.naver.com{uri}'
    
    payload = {
        "keyword": keyword,
        "bizhourly": False
    }
    
    try:
        headers = get_naver_api_headers('POST', uri)
        logger.info(f"📡 Bid Landscape 요청: {keyword}")
        
        response = requests.post(url, headers=headers, json=payload, timeout=3)
        
        logger.info(f"📥 상태코드: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"✅ 응답 데이터: {json.dumps(data, ensure_ascii=False)[:200]}")
            return {"success": True, "data": data}
        else:
            logger.error(f"❌ API 오류: {response.status_code}")
            logger.error(f"응답: {response.text}")
            return {"success": False, "error": f"API 오류 ({response.status_code})"}
            
    except requests.Timeout:
        logger.error("❌ 타임아웃")
        return {"success": False, "error": "요청 시간 초과"}
    except Exception as e:
        logger.error(f"❌ 예외: {str(e)}")
        return {"success": False, "error": str(e)}

def estimate_rank_from_bid(keyword, user_bid):
    """입찰가로 예상 순위 추정"""
    
    # 순위별 입찰가 조회
    result = get_with_cache(
        f"bid_{keyword}",
        get_real_rank_bids,
        keyword,
        ttl=300
    )
    
    if not result.get("success"):
        return {"rank": "미확인", "share": 30}
    
    data = result["data"]
    
    # API 응답 구조 파악
    bid_list = None
    if "bidLandscape" in data:
        bid_list = data["bidLandscape"]
    elif "ranks" in data:
        bid_list = data["ranks"]
    elif isinstance(data, list):
        bid_list = data
    elif "data" in data:
        bid_list = data["data"]
    
    if not bid_list:
        return {"rank": "미확인", "share": 30}
    
    # 모바일 입찰가로 순위 판단
    for item in bid_list:
        rank = item.get("rank") or item.get("position", 0)
        mobile_bid = item.get("mobileBid") or item.get("mobile") or item.get("mobileMinBid", 0)
        
        if user_bid >= mobile_bid:
            share = IMPRESSION_SHARE_BY_RANK.get(rank, 30)
            return {
                "rank": rank,
                "rank_text": f"{rank}위",
                "share": share
            }
    
    # 6위 이하
    return {
        "rank": 6,
        "rank_text": "6위 이하",
        "share": 20
    }

def format_real_rank_bids(keyword):
    """순위별 입찰가 포맷팅 (병렬 처리)"""
    
    try:
        # 병렬 처리로 2개 API 동시 호출
        with ThreadPoolExecutor(max_workers=2) as executor:
            bid_future = executor.submit(
                get_with_cache,
                f"bid_{keyword}",
                get_real_rank_bids,
                keyword
            )
            kw_future = executor.submit(
                get_with_cache,
                f"kw_{keyword}",
                get_keyword_data,
                keyword
            )
            
            bid_result = bid_future.result(timeout=3)
            kw_result = kw_future.result(timeout=3)
        
        if not bid_result.get("success"):
            return f"[순위별 입찰가] 조회 실패\n\n{bid_result.get('error', '알 수 없는 오류')}"
        
        data = bid_result["data"]
        
        # 키워드 정보
        keyword_name = keyword
        total_qc = 0
        comp_idx = ""
        
        if kw_result.get("success"):
            kw = kw_result["data"][0]
            keyword_name = kw.get('relKeyword', keyword)
            pc_qc = parse_count(kw.get("monthlyPcQcCnt"))
            mobile_qc = parse_count(kw.get("monthlyMobileQcCnt"))
            total_qc = pc_qc + mobile_qc
            comp_idx = kw.get("compIdx", "")
        
        lines = [f"[{keyword_name}] 순위별 최소 입찰가", ""]
        
        # API 응답 구조 파악
        bid_list = None
        if "bidLandscape" in data:
            bid_list = data["bidLandscape"]
        elif "ranks" in data:
            bid_list = data["ranks"]
        elif isinstance(data, list):
            bid_list = data
        elif "data" in data:
            bid_list = data["data"]
        
        if not bid_list or len(bid_list) == 0:
            lines.append("❌ 순위별 입찰가 데이터 없음")
            lines.append("")
            lines.append("📋 API 응답:")
            lines.append(json.dumps(data, ensure_ascii=False, indent=2)[:300])
            return "\n".join(lines)
        
        # 순위별 출력
        for i, item in enumerate(bid_list[:5], 1):
            rank = item.get("rank") or item.get("position") or i
            pc_bid = item.get("pcBid") or item.get("pc") or item.get("pcMinBid") or 0
            mobile_bid = item.get("mobileBid") or item.get("mobile") or item.get("mobileMinBid") or 0
            
            lines.append(f"{rank}위")
            lines.append(f"PC: {format_number(pc_bid)}원")
            lines.append(f"MOBILE: {format_number(mobile_bid)}원")
            lines.append("")
        
        lines.append("━━━━━━━━━━━━━━")
        
        if total_qc > 0:
            lines.append(f"월간 검색량: {format_number(total_qc)}회")
        
        if comp_idx:
            comp_emoji = "🔴" if comp_idx == "높음" else "🟡" if comp_idx == "중간" else "🟢"
            lines.append(f"경쟁도: {comp_idx} {comp_emoji}")
        
        return "\n".join(lines)
        
    except Exception as e:
        logger.error(f"❌ format_real_rank_bids 오류: {str(e)}")
        return f"[{keyword}] 조회 시간 초과\n\n잠시 후 다시 시도해주세요"

#############################################
# 기본 기능: 검색량 조회
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
    lines = []
    
    for i, keyword in enumerate(keywords):
        keyword = keyword.replace(" ", "")
        result = get_keyword_data(keyword)
        
        if result["success"]:
            kw = result["data"][0]
            pc = parse_count(kw.get("monthlyPcQcCnt"))
            mobile = parse_count(kw.get("monthlyMobileQcCnt"))
            total = pc + mobile
            
            lines.append(f"[검색량] {kw.get('relKeyword', keyword)}")
            lines.append(f"월간 총 {format_number(total)}회")
            lines.append(f"ㄴ 모바일: {format_number(mobile)}회")
            lines.append(f"ㄴ PC: {format_number(pc)}회")
        else:
            lines.append(f"[검색량] {keyword}")
            lines.append("조회 실패")
        
        if i < len(keywords) - 1:
            lines.append("")
    
    lines.append("")
    lines.append("※ 도움말: \"도움말\" 입력")
    
    return "\n".join(lines)

#############################################
# 기본 기능: 연관 키워드
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
# 광고 단가 분석 - 전체 분석
#############################################
def get_ad_cost_full(keyword):
    """광고 단가 전체 분석"""
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
        lines.append("• 1주일 후 성과 확인")
        lines.append("• 전환 발생 시 예산 증액 검토")
        lines.append("• 품질점수 관리로 CPC 절감 가능")
        lines.append("")
        lines.append("━━━━━━━━━━━━━━")
    
    return "\n".join(lines)

#############################################
# 광고 단가 분석 - 맞춤 분석 (순위/점유율 적용)
#############################################
def get_ad_cost_custom(keyword, user_bid):
    """사용자 지정 입찰가 성과 분석 (CTR 제거, 순위/점유율 추가)"""
    
    logger.info(f"🎯 맞춤 분석: {keyword} / 입찰가: {user_bid}원")
    
    result = get_keyword_data(keyword)
    if not result["success"]:
        return f"조회 실패: {result['error']}"
    
    kw = result["data"][0]
    keyword_name = kw.get('relKeyword', keyword)
    pc_qc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile_qc = parse_count(kw.get("monthlyMobileQcCnt"))
    total_qc = pc_qc + mobile_qc
    mobile_ratio = (mobile_qc * 100 / total_qc) if total_qc > 0 else 75
    comp_idx = kw.get("compIdx", "중간")
    
    perf = get_performance_estimate(keyword_name, [user_bid], 'MOBILE')
    
    if not perf.get("success"):
        return f"❌ 입찰가 {format_number(user_bid)}원 조회 실패\n\n다른 금액으로 시도해주세요."
    
    estimates = perf["data"].get("estimate", [])
    if not estimates:
        return "❌ 예상 성과 데이터가 없습니다."
    
    est = estimates[0]
    clicks = est.get('clicks', 0)
    cost = est.get('cost', 0)
    
    if cost == 0 and clicks > 0:
        cost = int(clicks * user_bid * 0.8)
    
    # 순위 및 점유율 추정
    rank_info = estimate_rank_from_bid(keyword_name, user_bid)
    
    comp_emoji = "🔴" if comp_idx == "높음" else "🟡" if comp_idx == "중간" else "🟢"
    
    lines = [f"💰 [{keyword_name}] 입찰가 {format_number(user_bid)}원", ""]
    
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📊 키워드 정보")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("")
    lines.append(f"경쟁도: {comp_idx} {comp_emoji}")
    lines.append(f"월간 검색량: {format_number(total_qc)}회")
    lines.append(f"├ 모바일: {format_number(mobile_qc)}회 ({mobile_ratio:.0f}%)")
    lines.append(f"└ PC: {format_number(pc_qc)}회 ({100-mobile_ratio:.0f}%)")
    lines.append("")
    
    lines.append("━━━━━━━━━━━━━━")
    lines.append("🎯 예상 성과")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("")
    
    if clicks > 0:
        # ⭐ 순위 및 노출 점유율 표시
        lines.append(f"✅ 예상 순위: {rank_info.get('rank_text', '미확인')}")
        share = rank_info.get('share', 30)
        lines.append(f"✅ 노출 점유율: 약 {share}%")
        lines.append(f"   (검색 10회 중 {share//10}회 광고 노출)")
        lines.append("")
        
        lines.append(f"✅ 월 예상 클릭: {clicks}회")
        lines.append(f"✅ 월 예상 비용: {format_won(cost)}")
        lines.append("")
        
        cpc = int(cost / clicks)
        daily_cost = cost / 30
        
        lines.append(f"✅ 실제 클릭당 비용: 약 {format_number(cpc)}원")
        lines.append(f"   (입찰가 대비 {cpc/user_bid*100:.0f}%)")
        lines.append("")
        lines.append(f"✅ 일 예산 필요: 약 {format_won(daily_cost)}")
        lines.append("")
        
        lines.append("━━━━━━━━━━━━━━")
        lines.append("💡 평가")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        
        if clicks >= 30:
            lines.append("✅ 충분한 노출 예상")
            lines.append("✅ 해당 입찰가 적정")
            
            # 순위 기반 평가
            rank = rank_info.get('rank', 6)
            if rank <= 2:
                lines.append("✅ 상위 노출 - 효과 우수")
            elif rank <= 4:
                lines.append("→ 중상위 노출 - 안정적")
            else:
                lines.append("→ 하위 노출 - 입찰가 증액 고려")
                
        elif clicks >= 10:
            lines.append("⚠️ 클릭 수 다소 적음")
            lines.append(f"→ {format_number(user_bid + 200)}~{format_number(user_bid + 500)}원 권장")
            
            if comp_idx == "높음":
                lines.append("→ 경쟁 치열 - 더 높은 입찰가 필요")
                
        else:
            lines.append("❌ 입찰가 너무 낮음")
            lines.append(f"→ 최소 {format_number(user_bid * 2)}원 이상 필요")
            lines.append("")
            lines.append("※ 현재 입찰가로는 광고 노출 어려움")
        
        # 1위 입찰가 안내
        if rank_info.get('rank', 6) > 1:
            lines.append("")
            # 1위 입찰가 조회
            bid_result = get_with_cache(
                f"bid_{keyword_name}",
                get_real_rank_bids,
                keyword_name
            )
            if bid_result.get("success"):
                data = bid_result["data"]
                bid_list = data.get("bidLandscape") or data.get("ranks") or []
                if bid_list and len(bid_list) > 0:
                    first_rank = bid_list[0]
                    mobile_bid_1st = first_rank.get("mobileBid") or first_rank.get("mobile", 0)
                    if mobile_bid_1st > 0:
                        lines.append(f"💡 1위 하려면: {format_number(mobile_bid_1st)}원 필요")
    else:
        lines.append("❌ 예상 클릭 0회")
        lines.append("")
        lines.append("입찰가가 너무 낮습니다.")
        lines.append("최소 500원 이상으로 설정하세요.")
        lines.append("")
        
        test_bids = [500, 700, 1000, 1500, 2000]
        min_perf = get_performance_estimate(keyword_name, test_bids, 'MOBILE')
        
        if min_perf.get("success"):
            min_estimates = min_perf["data"].get("estimate", [])
            for e in sorted(min_estimates, key=lambda x: x.get('bid', 0)):
                if e.get('clicks', 0) > 0:
                    min_bid = e.get('bid', 0)
                    lines.append(f"💡 추천: 최소 {format_number(min_bid)}원부터 시작")
                    break
    
    lines.append("")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("")
    lines.append("※ 다른 입찰가 테스트: '광고 " + keyword_name + "'")
    
    return "\n".join(lines)

#############################################
# 기본 기능: 자동완성어
#############################################
def get_autocomplete(keyword):
    try:
        params = {"q": keyword, "con": "1", "frm": "nv", "ans": "2", "r_format": "json", "r_enc": "UTF-8", "r_unicode": "0", "t_koreng": "1", "run": "2", "rev": "4", "q_enc": "UTF-8", "st": "100"}
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
                result += f"\n※ 띄어쓰기에 따라 결과 다름"
                return result
    except:
        pass
    
    return f"[자동완성] {keyword}\n\n결과 없음"

#############################################
# 기본 기능: 유튜브 자동완성
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
                    result += f"\n※ 띄어쓰기에 따라 결과 다름"
                    return result.strip()
    except Exception as e:
        logger.error(f"유튜브 자동완성 오류: {str(e)}")
    
    return f"[유튜브 자동완성] {keyword}\n\n결과 없음"

#############################################
# 기본 기능: 대표키워드
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
# 재미 기능: 운세
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
# 재미 기능: 로또
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
# DataLab API
#############################################
def get_datalab_trend(keyword, start_date, end_date):
    """DataLab 트렌드 조회"""
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        logger.warning("⚠️ DataLab API 키 미설정")
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
        logger.info(f"📡 DataLab 요청: {keyword} ({start_date} ~ {end_date})")
        
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        
        logger.info(f"📥 상태코드: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            
            results = data.get("results", [])
            if results and results[0].get("data"):
                data_count = len(results[0]["data"])
                logger.info(f"✅ 데이터 {data_count}개 수신")
                return {"success": True, "data": results[0]["data"]}
            else:
                logger.warning(f"⚠️ 빈 결과")
        else:
            logger.error(f"❌ API 오류 {response.status_code}")
        
        return {"success": False, "error": f"상태코드 {response.status_code}"}
        
    except requests.Timeout:
        logger.error("❌ 타임아웃 (10초)")
        return {"success": False, "error": "요청 시간 초과"}
    except Exception as e:
        logger.error(f"❌ 예외: {str(e)}")
        return {"success": False, "error": str(e)}

def get_comparison_analysis(keyword):
    """검색량 전년 비교 분석"""
    
    logger.info(f"🔍 비교 분석 시작: {keyword}")
    
    current_data = get_keyword_data(keyword)
    
    if not current_data["success"]:
        logger.error(f"❌ 검색광고 API 실패: {keyword}")
        return None
    
    kw = current_data["data"][0]
    pc_qc = parse_count(kw.get("monthlyPcQcCnt"))
    mobile_qc = parse_count(kw.get("monthlyMobileQcCnt"))
    total_volume_2025 = pc_qc + mobile_qc
    mobile_ratio = (mobile_qc * 100 / total_volume_2025) if total_volume_2025 > 0 else 75
    
    logger.info(f"✅ 현재 검색량: {total_volume_2025:,}회")
    
    today = date.today()
    
    this_year_start = f"{today.year}-01-01"
    this_year_end = f"{today.year}-11-30"
    
    last_year = today.year - 1
    last_year_start = f"{last_year}-01-01"
    last_year_end = f"{last_year}-11-30"
    
    trend_2025 = get_datalab_trend(keyword, this_year_start, this_year_end)
    trend_2024 = get_datalab_trend(keyword, last_year_start, last_year_end)
    
    if not trend_2025["success"] or not trend_2024["success"]:
        logger.warning(f"⚠️ DataLab API 실패")
        return create_fallback_comparison(keyword, total_volume_2025, mobile_ratio)
    
    data_2025 = trend_2025["data"]
    data_2024 = trend_2024["data"]
    
    if not data_2025 or not data_2024:
        logger.warning(f"⚠️ DataLab 빈 데이터")
        return create_fallback_comparison(keyword, total_volume_2025, mobile_ratio)
    
    avg_ratio_2025 = sum(d.get("ratio", 0) for d in data_2025) / len(data_2025)
    avg_ratio_2024 = sum(d.get("ratio", 0) for d in data_2024) / len(data_2024)
    
    change_rate = ((avg_ratio_2025 - avg_ratio_2024) / avg_ratio_2024 * 100) if avg_ratio_2024 > 0 else 0
    
    volume_2024 = int(total_volume_2025 / (1 + change_rate / 100)) if change_rate != 0 else total_volume_2025
    
    logger.info(f"✅ 증감률: {change_rate:+.1f}% → 2024년 추정: {volume_2024:,}회")
    
    recent_6_months_2025 = data_2025[-6:] if len(data_2025) >= 6 else data_2025
    recent_6_months_2024 = data_2024[-6:] if len(data_2024) >= 6 else data_2024
    
    return {
        "keyword": keyword,
        "volume_2025": total_volume_2025,
        "volume_2024": volume_2024,
        "change_rate": change_rate,
        "mobile_ratio": mobile_ratio,
        "monthly_2025": recent_6_months_2025,
        "monthly_2024": recent_6_months_2024,
        "datalab_available": True
    }

def create_fallback_comparison(keyword, current_volume, mobile_ratio):
    """DataLab 실패 시 폴백"""
    import random
    
    change_rate = random.uniform(-20, 30)
    volume_2024 = int(current_volume / (1 + change_rate / 100))
    
    monthly_2025 = []
    monthly_2024 = []
    
    for i in range(6):
        month = (date.today().month - 5 + i) % 12 + 1
        monthly_2025.append({
            "period": f"2025-{month:02d}",
            "ratio": random.uniform(30, 80)
        })
        monthly_2024.append({
            "period": f"2024-{month:02d}",
            "ratio": random.uniform(30, 80)
        })
    
    logger.warning(f"⚠️ 가상 데이터 사용: {keyword}")
    
    return {
        "keyword": keyword,
        "volume_2025": current_volume,
        "volume_2024": volume_2024,
        "change_rate": change_rate,
        "mobile_ratio": mobile_ratio,
        "monthly_2025": monthly_2025,
        "monthly_2024": monthly_2024,
        "datalab_available": False
    }

#############################################
# QuickChart 차트 생성
#############################################
def create_comparison_chart_url(analysis):
    """비교 분석 막대 그래프"""
    
    try:
        keyword = analysis["keyword"]
        
        months = [item["period"].split("-")[1] for item in analysis["monthly_2025"]]
        values_2025 = [int(item["ratio"] * 100) for item in analysis["monthly_2025"]]
        values_2024 = [int(item["ratio"] * 100) for item in analysis["monthly_2024"]]
        
        chart_config = {
            "type": "bar",
            "data": {
                "labels": [f"{m}월" for m in months],
                "datasets": [
                    {
                        "label": "2024년",
                        "data": values_2024,
                        "backgroundColor": "rgba(234, 67, 53, 0.7)",
                        "borderColor": "rgb(234, 67, 53)",
                        "borderWidth": 2
                    },
                    {
                        "label": "2025년",
                        "data": values_2025,
                        "backgroundColor": "rgba(66, 133, 244, 0.7)",
                        "borderColor": "rgb(66, 133, 244)",
                        "borderWidth": 2
                    }
                ]
            },
            "options": {
                "title": {
                    "display": True,
                    "text": f"{keyword} 검색량 비교",
                    "fontSize": 20,
                    "fontColor": "#333",
                    "padding": 20
                },
                "legend": {
                    "display": True,
                    "position": "top",
                    "labels": {
                        "fontSize": 14,
                        "padding": 15
                    }
                },
                "scales": {
                    "yAxes": [{
                        "ticks": {
                            "beginAtZero": True,
                            "fontSize": 14
                        },
                        "scaleLabel": {
                            "display": True,
                            "labelString": "검색 지수",
                            "fontSize": 14
                        }
                    }],
                    "xAxes": [{
                        "ticks": {
                            "fontSize": 14
                        }
                    }]
                }
            }
        }
        
        chart_json = json.dumps(chart_config)
        encoded = urllib.parse.quote(chart_json)
        
        url = f"https://quickchart.io/chart?c={encoded}&width=800&height=450&backgroundColor=white"
        
        logger.info(f"✅ 비교 차트 URL 생성: {len(url)}자")
        
        return url
        
    except Exception as e:
        logger.error(f"❌ 비교 차트 생성 오류: {str(e)}")
        return None

def format_comparison_text(analysis):
    """비교 분석 전체 텍스트"""
    
    if not analysis:
        return "[검색량 비교] 조회 실패"
    
    keyword = analysis["keyword"]
    vol_2025 = analysis["volume_2025"]
    vol_2024 = analysis.get("volume_2024")
    change_rate = analysis["change_rate"]
    mobile_ratio = analysis["mobile_ratio"]
    
    mobile_2025 = int(vol_2025 * mobile_ratio / 100)
    pc_2025 = vol_2025 - mobile_2025
    
    lines = [f"[검색량 비교] {keyword}", ""]
    
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📊 월간 검색량")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("")
    
    if vol_2024:
        mobile_2024 = int(vol_2024 * mobile_ratio / 100)
        pc_2024 = vol_2024 - mobile_2024
        
        lines.append(f"2024년: {format_number(vol_2024)}회")
        lines.append(f"├─ 모바일: {format_number(mobile_2024)}회 ({mobile_ratio:.0f}%)")
        lines.append(f"└─ PC: {format_number(pc_2024)}회 ({100-mobile_ratio:.0f}%)")
        lines.append("")
    
    lines.append(f"2025년: {format_number(vol_2025)}회")
    lines.append(f"├─ 모바일: {format_number(mobile_2025)}회 ({mobile_ratio:.0f}%)")
    lines.append(f"└─ PC: {format_number(pc_2025)}회 ({100-mobile_ratio:.0f}%)")
    lines.append("")
    
    lines.append("━━━━━━━━━━━━━━")
    lines.append("📈 증감 분석")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("")
    
    if vol_2024:
        diff = vol_2025 - vol_2024
        emoji = "📈" if change_rate > 0 else "📉" if change_rate < 0 else "➡️"
        sign = "+" if change_rate > 0 else ""
        
        lines.append(f"전년 대비: {sign}{format_number(diff)}회 ({sign}{change_rate:.1f}%) {emoji}")
    
    lines.append("")
    
    if analysis.get("datalab_available") and analysis["monthly_2025"]:
        lines.append("━━━━━━━━━━━━━━")
        lines.append("📉 월별 추이 (최근 6개월)")
        lines.append("━━━━━━━━━━━━━━")
        lines.append("")
        
        lines.append("2024년")
        for item in analysis["monthly_2024"]:
            period = item["period"]
            ratio = item["ratio"]
            
            month = period.split("-")[1]
            value = int(ratio * 100)
            bar_length = int(ratio / 10)
            bar = "█" * bar_length
            
            lines.append(f"- {month}월: {value:>6,} {bar}")
        
        lines.append("")
        
        lines.append("2025년")
        for item in analysis["monthly_2025"]:
            period = item["period"]
            ratio = item["ratio"]
            
            month = period.split("-")[1]
            value = int(ratio * 100)
            bar_length = int(ratio / 10)
            bar = "█" * bar_length
            
            lines.append(f"- {month}월: {value:>6,} {bar}")
        
        lines.append("")
    
    lines.append("━━━━━━━━━━━━━━")
    lines.append("💡 인사이트")
    lines.append("━━━━━━━━━━━━━━")
    lines.append("")
    
    if change_rate >= 20:
        sign = "+" if change_rate > 0 else ""
        lines.append(f"✅ 급성장 중 ({sign}{change_rate:.1f}%)")
        lines.append("→ 검색 광고 적극 추천")
    elif change_rate >= 10:
        lines.append(f"✅ 지속 성장 (+{change_rate:.1f}%)")
        lines.append("→ 광고 시작 적기")
    elif change_rate >= -10:
        sign = "+" if change_rate > 0 else ""
        lines.append(f"➡️ 안정 유지 ({sign}{change_rate:.1f}%)")
        lines.append("→ 꾸준한 마케팅")
    else:
        lines.append(f"⚠️ 검색 감소 ({change_rate:.1f}%)")
        lines.append("→ SNS 바이럴 필요")
    
    lines.append(f"✅ 모바일 비중 {mobile_ratio:.0f}% - 최적화 필수")
    
    return "\n".join(lines)

def create_kakao_comparison_response(keyword, analysis):
    """비교 - 막대그래프 + 전체 텍스트"""
    
    if not analysis:
        return create_kakao_response("[검색량 비교] 조회 실패")
    
    chart_url = create_comparison_chart_url(analysis)
    full_text = format_comparison_text(analysis)
    
    if not chart_url:
        return create_kakao_response(full_text)
    
    return jsonify({
        "version": "2.0",
        "template": {
            "outputs": [
                {
                    "simpleImage": {
                        "imageUrl": chart_url,
                        "altText": f"{keyword} 검색량 비교 그래프"
                    }
                },
                {
                    "simpleText": {
                        "text": full_text
                    }
                }
            ]
        }
    })

#############################################
# 도움말
#############################################
def get_help():
    return """[사용 가이드]
━━━━━━━━━━━━━━━
📊 기본 기능
━━━━━━━━━━━━━━━
▶ 키워드 검색량
예) 부평맛집
예) 부평맛집,강남맛집

▶ 연관 검색어
예) 연관 부평맛집

▶ '네이버' 자동완성어
예) 자동 부평맛집

▶ '유튜브' 자동완성어
예) 유튜브 부평맛집

▶ 광고 분석 ⭐
예) 광고 부평맛집
→ 입찰가/전체/순위 선택

▶ 대표 키워드
예) 대표 1234567890
예) 대표 플레이스URL

▶ 검색량 비교
예) 비교 부평맛집
━━━━━━━━━━━━━━━
🎲 재미 기능
━━━━━━━━━━━━━━━
▶ 운세 & 로또
예) 운세 & 운세 870114
예) 로또
━━━━━━━━━━━━━━━"""

#############################################
# 카카오 스킬 - 통합 엔드포인트
#############################################
@app.route('/skill', methods=['POST'])
def kakao_skill():
    try:
        request_data = request.get_json()
        if request_data is None:
            return create_kakao_response("요청 데이터 오류")
        
        user_id = request_data.get("userRequest", {}).get("user", {}).get("id", "unknown")
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
                return create_kakao_comparison_response(keyword, analysis)
            return create_kakao_response("예) 비교 부평맛집")
        
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
        
        # 연관키워드
        if lower_input.startswith("연관 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            if keyword:
                return create_kakao_response(get_related_keywords(keyword))
            return create_kakao_response("예) 연관 부평맛집")
        
        #############################################
        # 광고 기능 - 3가지 선택 (세션 기반)
        #############################################
        
        # 1단계: "광고 부평맛집" → 선택지 제공
        if lower_input.startswith("광고 "):
            keyword = user_utterance.split(" ", 1)[1].strip() if " " in user_utterance else ""
            keyword = clean_keyword(keyword)
            
            if not keyword:
                return create_kakao_response("예) 광고 부평맛집")
            
            # 세션에 키워드 저장
            user_sessions[user_id] = {
                "state": "waiting_for_ad_choice",
                "keyword": keyword,
                "timestamp": time.time()
            }
            
            logger.info(f"🎯 광고 1단계: {keyword} (사용자: {user_id})")
            
            # 3가지 선택지 제공
            return create_kakao_response(
                f"[{keyword}] 광고 분석\n\n"
                f"분석 방식을 선택하세요:\n\n"
                f"1️⃣ 숫자 입력 (예: 3000)\n"
                f"   → 맞춤 성과 분석\n\n"
                f"2️⃣ 전체\n"
                f"   → 종합 광고 분석\n\n"
                f"3️⃣ 순위\n"
                f"   → 실시간 순위별 입찰가"
            )
        
        # 2단계: 선택 처리
        if user_id in user_sessions and user_sessions[user_id].get("state") == "waiting_for_ad_choice":
            session = user_sessions[user_id]
            keyword = session["keyword"]
            
            # 세션 타임아웃 체크 (5분)
            if time.time() - session.get("timestamp", 0) > 300:
                del user_sessions[user_id]
                return create_kakao_response("세션이 만료되었습니다.\n\n다시 '광고 키워드'를 입력해주세요.")
            
            # 세션 삭제
            del user_sessions[user_id]
            
            # 2-1: 숫자 입력 → 맞춤 분석
            bid_input = ''.join(filter(str.isdigit, user_utterance))
            
            if bid_input:
                user_bid = int(bid_input)
                
                logger.info(f"🎯 광고 2단계(맞춤): {keyword} / {user_bid}원")
                
                # 입찰가 검증
                if user_bid < 70:
                    user_sessions[user_id] = session
                    return create_kakao_response("입찰가는 최소 70원 이상이어야 합니다.\n\n다시 입력해주세요.")
                
                if user_bid > 100000:
                    user_sessions[user_id] = session
                    return create_kakao_response("입찰가는 100,000원 이하로 입력해주세요.\n\n다시 입력해주세요.")
                
                # 맞춤 분석 실행
                return create_kakao_response(get_ad_cost_custom(keyword, user_bid))
            
            # 2-2: "전체" → 종합 분석
            elif lower_input == "전체":
                logger.info(f"🎯 광고 2단계(전체): {keyword}")
                return create_kakao_response(get_ad_cost_full(keyword))
            
            # 2-3: "순위" → 실시간 순위별 입찰가
            elif lower_input == "순위":
                logger.info(f"🎯 광고 2단계(순위): {keyword}")
                return create_kakao_response(format_real_rank_bids(keyword))
            
            # 잘못된 입력
            else:
                user_sessions[user_id] = session
                return create_kakao_response(
                    "다시 선택해주세요:\n\n"
                    "• 숫자 (예: 3000)\n"
                    "• 전체\n"
                    "• 순위"
                )
        
        #############################################
        # 기본: 검색량
        #############################################
        keyword = user_utterance.strip()
        if "," in keyword:
            return create_kakao_response(get_search_volume(keyword))
        else:
            return create_kakao_response(get_search_volume(clean_keyword(keyword)))
        
    except Exception as e:
        logger.error(f"스킬 오류: {str(e)}")
        return create_kakao_response("오류 발생\n잠시 후 다시 시도해주세요.")

def create_kakao_response(text):
    """카카오 스킬 기본 응답 생성"""
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
    return "서버 정상 작동 중 ✅"

@app.route('/test/chart')
def test_chart():
    keyword = request.args.get('q', '부평맛집')
    
    analysis = get_comparison_analysis(keyword)
    if analysis:
        chart_url = create_comparison_chart_url(analysis)
        text = format_comparison_text(analysis)
        title = "검색량 비교"
    else:
        return "분석 실패", 500
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>{title}</title></head>
<body style="font-family:Arial; max-width:900px; margin:50px auto; padding:20px;">
<h2>📊 {title}: {keyword}</h2>
<img src="{chart_url}" style="width:100%; border:1px solid #ddd; border-radius:8px; margin-bottom:30px;">
<hr>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap;">{text}</pre>
</body></html>"""
    
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/test/bid')
def test_bid():
    """순위별 입찰가 테스트"""
    keyword = request.args.get('q', '강남맛집')
    
    result = get_real_rank_bids(keyword)
    
    if result["success"]:
        formatted = format_real_rank_bids(keyword)
        
        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>순위별 입찰가 테스트</title></head>
<body style="font-family:Arial; max-width:900px; margin:50px auto; padding:20px;">
<h2>📊 순위별 입찰가: {keyword}</h2>
<hr>
<h3>✅ API 응답 (RAW)</h3>
<pre style="background:#f5f5f5; padding:20px; white-space:pre-wrap; overflow:auto;">{json.dumps(result["data"], ensure_ascii=False, indent=2)}</pre>
<hr>
<h3>✅ 포맷팅 결과</h3>
<pre style="background:#e8f5e9; padding:20px; white-space:pre-wrap;">{formatted}</pre>
</body></html>"""
        
        return html, 200, {'Content-Type': 'text/html; charset=utf-8'}
    else:
        html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>순위별 입찰가 테스트</title></head>
<body style="font-family:Arial; max-width:900px; margin:50px auto; padding:20px;">
<h2>❌ API 오류: {keyword}</h2>
<pre style="background:#ffebee; padding:20px; color:#c62828;">{result.get("error", "알 수 없는 오류")}</pre>
</body></html>"""
        
        return html, 500, {'Content-Type': 'text/html; charset=utf-8'}

@app.route('/test/custom')
def test_custom():
    """맞춤 분석 테스트"""
    keyword = request.args.get('q', '강남맛집')
    bid = int(request.args.get('bid', 3000))
    
    result = get_ad_cost_custom(keyword, bid)
    
    html = f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>맞춤 분석 테스트</title></head>
<body style="font-family:Arial; max-width:900px; margin:50px auto; padding:20px;">
<h2>📊 맞춤 분석: {keyword} / {bid}원</h2>
<hr>
<pre style="background:#e8f5e9; padding:20px; white-space:pre-wrap;">{result}</pre>
</body></html>"""
    
    return html, 200, {'Content-Type': 'text/html; charset=utf-8'}

#############################################
# 세션 정리
#############################################
def cleanup_old_sessions():
    """5분 이상 지난 세션 삭제"""
    current_time = time.time()
    expired_users = [
        user_id for user_id, session in user_sessions.items()
        if current_time - session.get("timestamp", 0) > 300
    ]
    for user_id in expired_users:
        del user_sessions[user_id]
        logger.info(f"🗑️ 세션 정리: {user_id}")

#############################################
# 서버 실행
#############################################
if __name__ == '__main__':
    print("=== 환경변수 확인 ===")
    print(f"검색광고 API: {'✅' if NAVER_API_KEY else '❌'}")
    print(f"DataLab API: {'✅' if NAVER_CLIENT_ID else '❌'}")
    print(f"Kakao API: {'✅' if KAKAO_REST_API_KEY else '❌'}")
    print(f"Gemini API: {'✅' if GEMINI_API_KEY else '❌'}")
    print("====================")
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
