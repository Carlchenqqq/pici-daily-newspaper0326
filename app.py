import logging
from flask import Flask, render_template, jsonify, request
from data_processor import DataProcessor, clean_dict, sanitize_batch_id, validate_positive_int
import os
import time
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB 请求体限制

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"success": False, "message": "请求数据过大，最大允许10MB"}), 413

@app.errorhandler(404)
def not_found(error):
    return jsonify({"success": False, "message": "接口不存在"}), 404

@app.errorhandler(500)
def internal_error(error):
    logger.error(f"服务器内部错误: {error}", exc_info=True)
    return jsonify({"success": False, "message": "服务器内部错误，请稍后重试"}), 500

DATA_ROOT = os.path.dirname(os.path.abspath(__file__))
processor = DataProcessor(DATA_ROOT)

# =============================================
# CACHE SYSTEM
# =============================================
_CACHE = {}
_CACHE_TTL = 3600  # 1 hour for production

def get_cache(key):
    if key in _CACHE:
        cached_time, cached_value = _CACHE[key]
        if time.time() - cached_time < _CACHE_TTL:
            return cached_value
    return None

def set_cache(key, value):
    _CACHE[key] = (time.time(), value)

def clear_cache():
    global _CACHE
    _CACHE = {}

def get_default_batch_id():
    batches = processor.get_all_batches()
    if not batches:
        return None
    return batches[0].get("batch_id")

def resolve_batch_id(provided_batch_id=None):
    batch_id = provided_batch_id or request.args.get('batch_id')
    if not batch_id:
        return get_default_batch_id()
    try:
        return sanitize_batch_id(batch_id)
    except ValueError:
        return get_default_batch_id()

def get_valid_batch_or_error(batch_id):
    if not batch_id:
        return None, (jsonify({"success": False, "message": "No batches available"}), 404)

    batch = processor.get_batch_info(batch_id)
    if not batch:
        return None, (jsonify({"success": False, "message": f"Batch not found: {batch_id}"}), 404)

    return batch, None

def get_report_cached(batch_id, date):
    """Get report with caching"""
    cache_key = f"report:{batch_id}:{date}"
    cached = get_cache(cache_key)
    if cached is not None:
        return cached
    report = processor.generate_batch_report(batch_id, date)
    set_cache(cache_key, report)
    return report

@app.route('/')
def index():
    batches = processor.get_all_batches()
    return render_template('index.html', batches=batches)

@app.route('/api/batches')
def get_batches():
    batches = processor.get_all_batches()
    return jsonify({"success": True, "data": batches})

@app.route('/api/batch/<batch_id>')
def get_batch_info(batch_id):
    batch = processor.get_batch_info(batch_id)
    if batch:
        return jsonify({"success": True, "data": batch})
    return jsonify({"success": False, "message": "Batch not found"}), 404

@app.route('/api/batch/update-field', methods=['POST'])
def update_batch_field():
    data = request.get_json()
    if not data:
        return jsonify({"success": False, "message": "无效的请求数据"}), 400
    
    batch_id = data.get('batch_id')
    field = data.get('field')
    value = data.get('value')
    
    if not batch_id or not field:
        return jsonify({"success": False, "message": "Missing batch_id or field"}), 400
    
    allowed_fields = ['batch_name', 'farm_name', 'entry_date', 'target_temp', 
                      'total_pig_count', 'feeding_count', 'feed_ratio_130kg', 'qualified_rate']
    if field not in allowed_fields:
        return jsonify({"success": False, "message": f"不允许修改的字段: {field}"}), 400
    
    try:
        batch_id = sanitize_batch_id(batch_id)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    
    result = processor.update_batch_field(batch_id, field, value)
    return jsonify(result)

@app.route('/api/report')
def get_report():
    batch_id = resolve_batch_id()
    date = request.args.get('date', '2026-03-10')

    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response

    report = get_report_cached(batch_id, date)

    if "error" in report:
        return jsonify({"success": False, "message": report["error"]}), 404

    return jsonify({"success": True, "data": clean_dict(report)})

@app.route('/api/dashboard')
def get_dashboard():
    batch_id = resolve_batch_id()
    date = request.args.get('date', '2026-03-10')

    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response

    report = get_report_cached(batch_id, date)

    if "error" in report:
        return jsonify({"success": False, "message": report["error"]}), 404

    return jsonify({"success": True, "data": clean_dict(report)})

@app.route('/api/deep-analysis')
def get_deep_analysis():
    batch_id = resolve_batch_id()
    date = request.args.get('date', '2026-03-10')

    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response

    analysis = processor.deep_analysis(batch_id, date)

    if "error" in analysis:
        return jsonify({"success": False, "message": analysis["error"]}), 404

    return jsonify({"success": True, "data": clean_dict(analysis)})

@app.route('/api/trend')
def get_trend():
    batch_id = resolve_batch_id()
    date = request.args.get('date', '2026-03-10')
    page = validate_positive_int(request.args.get('page', 1), default=1, max_value=1000)
    page_size = validate_positive_int(request.args.get('page_size', 7), default=7, max_value=100)

    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response

    # Also cache trend data
    cache_key = f"trend:{batch_id}:{date}:{page}:{page_size}"
    cached = get_cache(cache_key)
    if cached is not None:
        return jsonify({"success": True, "data": clean_dict(cached)})
    
    trend_data = processor.get_trend_data(batch_id, date, page, page_size)
    set_cache(cache_key, trend_data)
    
    return jsonify({"success": True, "data": clean_dict(trend_data)})

@app.route('/api/death-culling', methods=['POST'])
def save_death_culling():
    data = request.json
    if not data:
        return jsonify({"success": False, "message": "无效的请求数据"}), 400
    
    batch_id = data.get('batch_id')
    date = data.get('date')
    records = data.get('records', [])
    
    if not batch_id or not date:
        return jsonify({"success": False, "message": "缺少必要参数: batch_id 或 date"}), 400
    
    if not isinstance(records, list) or len(records) > 1000:
        return jsonify({"success": False, "message": "records 参数格式错误或超过限制"}), 400
    
    try:
        batch_id = sanitize_batch_id(batch_id)
    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    
    processor.save_death_culling_data(batch_id, date, records)
    clear_cache()  # Clear cache after data change
    
    return jsonify({"success": True})

@app.route('/api/import-death', methods=['POST'])
def import_death():
    data = request.json
    batch_id = resolve_batch_id(data.get('batch_id') if data else None)

    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response

    result = processor.import_death_data_from_excel(batch_id)
    clear_cache()  # Clear cache after data change
    
    return jsonify(result)

@app.route('/api/cache/clear', methods=['POST', 'GET'])
def api_clear_cache():
    clear_cache()
    return jsonify({"success": True, "message": "Cache cleared"})

@app.route('/api/cache/refresh', methods=['POST', 'GET'])
def api_refresh_cache():
    batch_id = request.args.get('batch_id')
    print(f'[API /api/cache/refresh] GET batch_id: {batch_id}')
    
    if not batch_id and request.is_json:
        batch_id = request.json.get('batch_id')
        print(f'[API /api/cache/refresh] POST JSON batch_id: {batch_id}')
    
    if not batch_id:
        print(f'[API /api/cache/refresh] ERROR: batch_id is required')
        return jsonify({"success": False, "error": "batch_id is required"}), 400
    
    try:
        print(f'[API /api/cache/refresh] 开始刷新批次: {batch_id}')
        result = processor.refresh_cache(batch_id)
        print(f'[API /api/cache/refresh] 刷新成功: {result}')
        return jsonify(result)
    except Exception as e:
        print(f'[API /api/cache/refresh] 刷新失败: {e}')
        return jsonify({"success": False, "error": str(e)}), 500

# =============================================
# HISTORICAL DATA API (NEW)
# =============================================

@app.route('/api/batch-dates')
def get_batch_dates():
    """获取批次所有可用日期列表"""
    batch_id = resolve_batch_id()
    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response
    dates = processor.find_all_dates_for_batch(batch_id)
    return jsonify({"success": True, "data": dates})

@app.route('/api/historical-report')
def get_historical_report():
    """获取历史周期报表"""
    batch_id = resolve_batch_id()
    end_date = request.args.get('end_date')
    start_date = request.args.get('start_date')
    days = request.args.get('days', type=int)
    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response
    
    # 忽略 _t 时间戳参数（用于绕过缓存）
    _t = request.args.get('_t')
    
    start_time = time.time()
    
    # Auto-detect dates when not provided
    available_dates = processor.find_all_dates_for_batch(batch_id)
    if not available_dates:
        return jsonify({"success": False, "message": "No data found for batch"}), 404
    
    if not end_date and days:
        # 有天数限制：使用最新日期作为结束日期
        end_date = available_dates[-1]
    elif not end_date and not days:
        # 全部历史模式：使用最早和最晚日期
        # end_date 留空，让 generate_historical_report 内部处理
        pass
    
    # 不使用 _t 参数做缓存key，避免缓存失效
    cache_key = f"historical:{batch_id}:{start_date}:{end_date}:{days}"
    
    # 有 _t 参数时强制重新计算，跳过缓存
    use_cache = _t is None
    cached = get_cache(cache_key) if use_cache else None
    if use_cache and cached is not None:
        return jsonify({"success": True, "data": cached})
    
    report = processor.generate_historical_report(batch_id, end_date, start_date, days)
    
    if "error" in report:
        return jsonify({"success": False, "message": report["error"]}), 404
    
    result = clean_dict(report)
    set_cache(cache_key, result)
    
    return jsonify({"success": True, "data": result})

@app.route('/api/trend-history')
def get_trend_history():
    """获取历史趋势数据（用于图表）"""
    batch_id = resolve_batch_id()
    end_date = request.args.get('end_date', '2026-03-10')
    days = request.args.get('days', 30, type=int)
    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response
    
    cache_key = f"trend-history:{batch_id}:{end_date}:{days}"
    cached = get_cache(cache_key)
    if cached is not None:
        return jsonify({"success": True, "data": cached})
    
    report = processor.generate_historical_report(batch_id, end_date, days=days)
    
    if "error" in report:
        return jsonify({"success": False, "message": report["error"]}), 404
    
    trend_data = report.get("trend_data", {})
    death_analysis = report.get("death_analysis", {})
    
    result = {
        "dates": trend_data.get("dates", []),
        "temperature": trend_data.get("temperature", {}),
        "humidity": trend_data.get("humidity", {}),
        "co2": trend_data.get("co2", {}),
        "death_trend": death_analysis.get("cumulative_trend", [])
    }
    
    result = clean_dict(result)
    set_cache(cache_key, result)
    
    return jsonify({"success": True, "data": result})

@app.route('/api/period-stats')
def get_period_stats():
    """获取周期统计数据"""
    batch_id = resolve_batch_id()
    end_date = request.args.get('end_date', '2026-03-10')
    days = request.args.get('days', 30, type=int)
    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response
    
    cache_key = f"period-stats:{batch_id}:{end_date}:{days}"
    cached = get_cache(cache_key)
    if cached is not None:
        return jsonify({"success": True, "data": cached})
    
    report = processor.generate_historical_report(batch_id, end_date, days=days)
    
    if "error" in report:
        return jsonify({"success": False, "message": report["error"]}), 404
    
    result = {
        "date_range": report.get("date_range", {}),
        "period_statistics": report.get("period_statistics", {}),
        "death_analysis": report.get("death_analysis", {})
    }
    
    result = clean_dict(result)
    set_cache(cache_key, result)
    
    return jsonify({"success": True, "data": result})

@app.route('/export-template')
def get_export_template():
    """返回离线导出报告的 HTML 模板内容"""
    return render_template('export_report.html')


@app.route('/api/export-package')
def get_export_package():
    """获取用于离线导出的全量数据包（JSON），供前端生成自包含 HTML 报告"""
    batch_id = resolve_batch_id()
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    _, error_response = get_valid_batch_or_error(batch_id)
    if error_response:
        return error_response

    # 与 /api/historical-report 相同的缓存逻辑
    cache_key = f"export-package:{batch_id}:{start_date}:{end_date}"
    cached = get_cache(cache_key)
    if cached is not None:
        return jsonify({"success": True, "data": cached})

    report = processor.generate_historical_report(batch_id, end_date, start_date)

    if "error" in report:
        return jsonify({"success": False, "message": report["error"]}), 404

    result = clean_dict(report)
    set_cache(cache_key, result)
    return jsonify({"success": True, "data": result})


if __name__ == '__main__':
    import os
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_mode, host='0.0.0.0', port=5000)
