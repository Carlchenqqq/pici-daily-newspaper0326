import pandas as pd
import os
from pathlib import Path
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
import json
import math
import time
import re
import numpy as np
import warnings
warnings.filterwarnings('ignore', category=UserWarning, module='openpyxl')

_cache = {}
_CACHE_TTL = 300

def clean_nan(value):
    if value is None:
        return None
    if isinstance(value, (np.bool_,)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value

def clean_dict(data):
    if isinstance(data, dict):
        return {k: clean_dict(v) for k, v in data.items()}
    elif isinstance(data, (list, np.ndarray)):
        items = data.tolist() if isinstance(data, np.ndarray) else data
        return [clean_dict(item) for item in items]
    else:
        return clean_nan(data)

def get_cached(key: str, func, *args):
    now = time.time()
    if key in _cache:
        cached_time, cached_value = _cache[key]
        if now - cached_time < _CACHE_TTL:
            return cached_value
    result = func(*args)
    _cache[key] = (now, result)
    return result

def clear_cache():
    global _cache
    _cache = {}

class DataProcessor:
    def __init__(self, data_root: str):
        self.data_root = Path(data_root)
        self._env_cache = {}
        self._device_cache = {}
        self._sheet_cache = {}
        self._report_cache = {}
        self._file_index_cache = {}
        self._file_index_time = 0
        self._daily_summaries_cache = {}
        self._daily_summaries_cache_time = {}
        self._daily_summaries_ttl = 3600
        self._outdoor_temp_cache = {}
        self._batch_config_cache = None
        self._batch_config_time = 0
        self.batch_config = self._load_batch_config()
        self._cache_dir = self.data_root / "cache"
        self._cache_dir.mkdir(exist_ok=True)
        self._load_all_caches_from_files()

    def _get_cache_file_path(self, batch_id: str) -> Path:
        safe_batch_id = batch_id.replace('/', '_').replace('\\', '_')
        return self._cache_dir / f"historical_report_{safe_batch_id}.json"

    def _load_all_caches_from_files(self):
        if not self._cache_dir.exists():
            return
        for cache_file in self._cache_dir.glob("historical_report_*.json"):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                batch_id = data.get('batch_info', {}).get('batch_id', '')
                if batch_id:
                    cache_key_prefix = f"{batch_id}:"
                    for key in list(self._daily_summaries_cache.keys()):
                        if key.startswith(cache_key_prefix):
                            pass
                    batch_info = data.get('batch_info', {})
                    start_date = data.get('date_range', {}).get('start_date', '')
                    end_date = data.get('date_range', {}).get('end_date', '')
                    if start_date and end_date:
                        cache_key = f"{batch_id}:{start_date}:{end_date}"
                        daily_summaries = data.get('daily_summaries', [])
                        if daily_summaries:
                            self._daily_summaries_cache[cache_key] = (time.time(), daily_summaries)
                            print(f"[缓存加载] 从文件加载批次 {batch_id} ({start_date} ~ {end_date}), {len(daily_summaries)} 条记录")
            except Exception as e:
                print(f"[缓存加载失败] {cache_file.name}: {e}")

    def _save_report_to_cache_file(self, batch_id: str, report_data: Dict):
        cache_file = self._get_cache_file_path(batch_id)
        try:
            clean_data = self._clean_report_data(report_data)
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(clean_data, f, ensure_ascii=False, indent=2)
            print(f"[缓存保存] 批次 {batch_id} -> {cache_file.name}")
        except Exception as e:
            print(f"[缓存保存失败] {cache_file.name}: {e}")

    def _clean_report_data(self, data: Any) -> Any:
        if isinstance(data, dict):
            result = {}
            for k, v in data.items():
                if v is None:
                    continue
                if isinstance(v, (np.bool_, np.integer, np.floating)):
                    v = clean_nan(v)
                elif isinstance(v, (list, tuple)):
                    v = self._clean_report_data(v)
                elif isinstance(v, dict):
                    v = self._clean_report_data(v)
                result[k] = v
            return result
        elif isinstance(data, list):
            return [self._clean_report_data(item) for item in data]
        elif isinstance(data, (np.bool_, np.integer, np.floating)):
            return clean_nan(data)
        return data

    def refresh_cache(self, batch_id: str, start_date: str = None, end_date: str = None, days: int = None) -> Dict:
        batch_info = self.get_batch_info(batch_id)
        if not batch_info:
            return {"success": False, "error": f"批次 {batch_id} 不存在"}

        if not start_date and not end_date and not days:
            days = 365

        if end_date is None:
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime('%Y-%m-%d')

        if start_date is None:
            from datetime import datetime, timedelta
            start_dt = datetime.now() - timedelta(days=days)
            start_date = start_dt.strftime('%Y-%m-%d')

        cache_key = f"{batch_id}:{start_date}:{end_date}"
        if cache_key in self._daily_summaries_cache:
            del self._daily_summaries_cache[cache_key]

        result = self.generate_historical_report(batch_id, end_date, start_date)
        if "error" not in result:
            cache_file = self._get_cache_file_path(batch_id)
            if cache_file.exists():
                cache_file.unlink()
                print(f"[缓存刷新] 删除旧缓存文件: {cache_file.name}")

        return {"success": True, "message": f"批次 {batch_id} 缓存已刷新"}

    def _get_file_index(self, batch_id: str) -> Dict[str, List[Dict]]:
        cache_key = f"file_index:{batch_id}"
        now = time.time()
        
        if cache_key in self._file_index_cache:
            cached_time, cached_index = self._file_index_cache[cache_key]
            if now - cached_time < 10:
                return cached_index
        
        batch = self.get_batch_info(batch_id)
        if not batch:
            return {}
        
        units = batch.get("units", [])
        data_dir = self.data_root / batch_id
        if not data_dir.exists():
            return {}
        
        file_index = {"environment": [], "device": []}
        for f in data_dir.iterdir():
            if not f.is_file() or f.name.startswith('~'):
                continue
            unit_num = self.parse_unit_number(f.name)
            if unit_num and unit_num in units:
                file_info = {"unit": unit_num, "path": str(f), "filename": f.name}
                if "环境数据" in f.name:
                    file_index["environment"].append(file_info)
                elif "设备数据" in f.name:
                    file_index["device"].append(file_info)
        
        self._file_index_cache[cache_key] = (now, file_index)
        return file_index
    
    def _load_batch_config(self) -> Dict:
        now = time.time()
        if self._batch_config_cache is not None and now - self._batch_config_time < 10:
            return self._batch_config_cache
        
        config_path = self.data_root / "batch_config.json"
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self._batch_config_cache = config
                self._batch_config_time = now
                return config
        
        config = self._default_batch_config()
        self._batch_config_cache = config
        self._batch_config_time = now
        return config
    
    def _default_batch_config(self) -> Dict:
        """自动扫描data_root目录下的文件夹作为批次"""
        batches = []
        data_dir = self.data_root
        
        if data_dir.exists():
            for item in data_dir.iterdir():
                if item.is_dir() and not item.name.startswith('.'):
                    batch_id = item.name
                    batch_name = batch_id
                    units = []
                    unit_types = {}
                    
                    for f in item.iterdir():
                        if f.is_file() and not f.name.startswith('~') and '环境数据' in f.name:
                            unit_num = self.parse_unit_number(f.name)
                            if unit_num and unit_num not in units:
                                units.append(unit_num)
                                try:
                                    df = pd.read_excel(f, sheet_name=0, nrows=1)
                                    if not df.empty:
                                        unit_type = str(df.iloc[0].get('单元类型', '')).strip().lower()
                                        unit_types[unit_num] = unit_type
                                except:
                                    pass
                    
                    if units:
                        batches.append({
                            "batch_id": batch_id,
                            "batch_name": batch_name,
                            "farm_name": "",
                            "entry_date": batch_id,
                            "target_temp": 0,
                            "units": sorted(units, key=lambda x: (int(x.split('-')[0]) if x.split('-')[0].isdigit() else 0, int(x.split('-')[1]) if len(x.split('-')) > 1 and x.split('-')[1].isdigit() else 0)),
                            "unit_types": unit_types,
                            "total_pig_count": 0
                        })
        
        return {"batches": batches}
    
    def get_all_batches(self) -> List[Dict]:
        return self.batch_config.get("batches", [])
    
    def get_batch_info(self, batch_id: str) -> Optional[Dict]:
        for batch in self.get_all_batches():
            if batch["batch_id"] == batch_id:
                return batch
        return None
    
    def update_batch_field(self, batch_id: str, field: str, value: Any) -> Dict[str, Any]:
        config_path = self.data_root / "batch_config.json"
        
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            config = {"batches": []}
        
        batch_found = False
        for batch in config.get("batches", []):
            if batch["batch_id"] == batch_id:
                batch[field] = value
                batch_found = True
                break
        
        if not batch_found:
            for batch in self.get_all_batches():
                if batch["batch_id"] == batch_id:
                    config["batches"].append(batch)
                    batch[field] = value
                    batch_found = True
                    break
        
        if not batch_found:
            return {"success": False, "message": f"批次不存在: {batch_id}"}
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        
        self._batch_config_cache = None
        
        return {"success": True, "message": "更新成功"}
    
    def get_units_for_batch(self, batch_id: str) -> List[str]:
        batch = self.get_batch_info(batch_id)
        if batch:
            return batch.get("units", [])
        return []
    
    def parse_unit_number(self, filename: str) -> Optional[str]:
        match = re.search(r'(育肥舍|保育舍)(\d+)-(\d+)', filename)
        if match:
            unit_type = '育肥' if match.group(1) == '育肥舍' else '保育'
            return f"{unit_type}{match.group(2)}-{match.group(3)}"
        match = re.search(r'(育肥舍|保育舍)(\d+)', filename)
        if match:
            unit_type = '育肥' if match.group(1) == '育肥舍' else '保育'
            return f"{unit_type}{match.group(2)}-1"
        return None
    
    def parse_date_from_filename(self, filename: str) -> Optional[str]:
        """从文件名中提取日期，格式：YYYY-MM-DD"""
        match = re.search(r'(\d{4})-(\d{2})-(\d{2})\s+\d{2}_\d{2}_\d{2}', filename)
        if match:
            return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
        return None
    
    def parse_date_range_from_filename(self, filename: str) -> Optional[tuple]:
        """从文件名中提取日期范围，返回 (start_date, end_date) 或 None
        支持格式：2025-12-18 00_00_00 至 2026-02-05 23_59_59
        """
        pattern = r'(\d{4})-(\d{2})-(\d{2})\s+\d{2}_\d{2}_\d{2}\s+至\s+(\d{4})-(\d{2})-(\d{2})'
        match = re.search(pattern, filename)
        if match:
            start = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
            end = f"{match.group(4)}-{match.group(5)}-{match.group(6)}"
            return (start, end)
        return None
    
    def find_all_dates_for_batch(self, batch_id: str) -> List[str]:
        """发现批次所有可用的日期"""
        batch = self.get_batch_info(batch_id)
        if not batch:
            return []
        
        data_dir = self.data_root / batch_id
        if not data_dir.exists():
            return []
        
        dates = set()
        for f in data_dir.iterdir():
            if not f.is_file() or f.name.startswith('~'):
                continue
            
            # 先检查是否是日期范围（包含"至"）
            if '至' in f.name:
                date_range = self.parse_date_range_from_filename(f.name)
                if date_range:
                    start, end = date_range
                    from datetime import datetime, timedelta
                    s = datetime.strptime(start, '%Y-%m-%d')
                    e = datetime.strptime(end, '%Y-%m-%d')
                    current = s
                    while current <= e:
                        dates.add(current.strftime('%Y-%m-%d'))
                        current += timedelta(days=1)
                continue
            
            # 尝试匹配单个日期
            date = self.parse_date_from_filename(f.name)
            if date:
                dates.add(date)
        
        return sorted(list(dates))
    
    def get_date_range_files(self, batch_id: str, start_date: str, end_date: str) -> Dict[str, Dict[str, List[Dict]]]:
        """获取日期范围内所有单元的数据文件
        Returns:
            Dict[date_str, Dict[str, List[Dict]]] - 按日期分组的文件信息
        """
        batch = self.get_batch_info(batch_id)
        if not batch:
            return {}
        
        units = batch.get("units", [])
        data_dir = self.data_root / batch_id
        if not data_dir.exists():
            return {}
        
        # 解析日期范围
        from datetime import datetime, timedelta
        start = datetime.strptime(start_date, '%Y-%m-%d')
        end = datetime.strptime(end_date, '%Y-%m-%d')
        
        result = {}
        current = start
        while current <= end:
            date_str = current.strftime('%Y-%m-%d')
            result[date_str] = {"environment": [], "device": []}
            current += timedelta(days=1)
        
        # 扫描文件并分类
        for f in data_dir.iterdir():
            if not f.is_file() or f.name.startswith('~'):
                continue
            
            # 只处理 Excel 文件，忽略 CSV 文件
            if f.suffix.lower() != '.xlsx':
                continue
            
            unit_num = self.parse_unit_number(f.name)
            if not unit_num or unit_num not in units:
                continue
            
            date_range = self.parse_date_range_from_filename(f.name)
            if date_range:
                start_d, end_d = date_range
                s = datetime.strptime(start_d, '%Y-%m-%d')
                e = datetime.strptime(end_d, '%Y-%m-%d')
                current = s
                while current <= e:
                    date_str = current.strftime('%Y-%m-%d')
                    if date_str in result:
                        file_info = {"unit": unit_num, "path": str(f), "filename": f.name, "date": date_str}
                        if "环境数据" in f.name:
                            result[date_str]["environment"].append(file_info)
                        elif "设备数据" in f.name:
                            result[date_str]["device"].append(file_info)
                    current += timedelta(days=1)
            else:
                date = self.parse_date_from_filename(f.name)
                if date and date in result:
                    file_info = {"unit": unit_num, "path": str(f), "filename": f.name, "date": date}
                    if "环境数据" in f.name:
                        result[date]["environment"].append(file_info)
                    elif "设备数据" in f.name:
                        result[date]["device"].append(file_info)
        
        return result
    
    def find_data_files(self, batch_id: str, date: str) -> Dict[str, List[Dict]]:
        cache_key = f"find_data_files:{batch_id}:{date}"
        
        if cache_key in self._report_cache:
            return self._report_cache[cache_key]
        
        batch = self.get_batch_info(batch_id)
        if not batch:
            return {}
        
        units = batch.get("units", [])
        result = {"environment": [], "device": []}
        
        data_dir = self.data_root / batch_id
        if not data_dir.exists():
            return result
        
        for f in data_dir.iterdir():
            if not f.is_file() or f.name.startswith('~'):
                continue
            parsed_date = self.parse_date_from_filename(f.name)
            if parsed_date != date:
                continue
            unit_num = self.parse_unit_number(f.name)
            if unit_num and unit_num in units:
                file_info = {"unit": unit_num, "path": str(f), "filename": f.name}
                if "环境数据" in f.name:
                    result["environment"].append(file_info)
                elif "设备数据" in f.name:
                    result["device"].append(file_info)
        
        self._report_cache[cache_key] = result
        return result
    
    def _load_sheet(self, file_path: str, sheet_name: str, usecols: Optional[List[str]] = None) -> pd.DataFrame:
        key = f"{file_path}::{sheet_name}"
        if usecols is None and key in self._sheet_cache:
            return self._sheet_cache[key]  # type: ignore

        cache_key = key if usecols is None else f"{key}::{','.join(usecols) if usecols else ''}"
        
        # 检查file_path是否已经是CSV文件
        file_path_obj = Path(file_path)
        if file_path_obj.suffix.lower() == '.csv':
            try:
                df = pd.read_csv(file_path, encoding='utf-8-sig')
                if usecols:
                    available_cols = [col for col in usecols if col in df.columns]
                    df = df[available_cols] if available_cols else df
                if usecols is None:
                    self._sheet_cache[key] = df
                return df
            except Exception as e:
                print(f"Warning: Failed to read CSV {file_path}: {e}")
                return pd.DataFrame()
        
        # 优先读取CSV文件（速度快5-10倍）
        csv_path = Path(file_path).parent / (Path(file_path).stem + f"_{sheet_name}.csv")
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path, encoding='utf-8-sig')
                if usecols:
                    available_cols = [col for col in usecols if col in df.columns]
                    df = df[available_cols] if available_cols else df
                if usecols is None:
                    self._sheet_cache[key] = df
                return df  # type: ignore
            except Exception as e:
                print(f"Warning: Failed to read CSV {csv_path}: {e}, falling back to Excel")
        
        # CSV不存在，读取Excel文件
        try:
            if usecols:
                df = pd.read_excel(file_path, sheet_name=sheet_name, usecols=usecols, engine='openpyxl')
            else:
                df = pd.read_excel(file_path, sheet_name=sheet_name, engine='openpyxl')
            
            if usecols is None:
                self._sheet_cache[key] = df
            return df
        except Exception as e:
            print(f"Error loading {sheet_name} from {file_path}: {e}")
            return pd.DataFrame()
    
    def _load_sheet_columns(self, file_path: str, sheet_name: str, columns: List[str]) -> pd.DataFrame:
        key = f"{file_path}::{sheet_name}::{','.join(columns)}"
        if key in self._sheet_cache:
            return self._sheet_cache[key]
        
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, usecols=columns, engine='openpyxl')
            self._sheet_cache[key] = df
            return df
        except Exception as e:
            print(f"Error loading {sheet_name} from {file_path}: {e}")
            return pd.DataFrame()
    
    def load_environment_data(self, file_path: str) -> pd.DataFrame:
        return self._load_sheet(file_path, '单元信息')
    
    def load_device_data(self, file_path: str) -> pd.DataFrame:
        return self._load_sheet(file_path, '设备信息')
    
    # ====== Death Data Methods ======
    def get_death_culling_data(self, batch_id: str, date: str) -> List[Dict]:
        death_config_path = self.data_root / "death_culling.json"
        if death_config_path.exists():
            with open(death_config_path, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
                return all_data.get(batch_id, {}).get(date, [])
        return []
    
    def get_all_death_data(self, batch_id: str) -> Dict[str, List[Dict]]:
        # 先尝试导入最新的死亡报表
        self.import_death_data_from_excel(batch_id)
        
        death_config_path = self.data_root / "death_culling.json"
        if death_config_path.exists():
            with open(death_config_path, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
                return all_data.get(batch_id, {})
        return {}
    
    def import_death_data_from_excel(self, batch_id: str) -> Dict[str, Any]:
        result = {"success": False, "imported": 0, "message": ""}
        
        # 查找批次文件夹
        batch_dir = self.data_root / batch_id
        if not batch_dir.exists():
            # 批次文件夹不存在，尝试查找包含该批次号的文件夹
            found_batch_id = None
            for item in self.data_root.iterdir():
                if item.is_dir() and not item.name.startswith('.') and batch_id in item.name:
                    found_batch_id = item.name
                    batch_dir = item
                    break
            
            if not found_batch_id:
                result["message"] = f"批次文件夹不存在: {batch_id}"
                return result
            
            # 更新批次ID为实际文件夹名称
            batch_id = found_batch_id
            print(f"自动修正批次ID: {batch_id}")
        
        # 查找所有包含"死亡"的Excel文件
        death_files = list(batch_dir.glob("*死亡*.xlsx"))
        death_files = [f for f in death_files if not f.name.startswith('~$')]
        if not death_files:
            result["message"] = "未找到死亡报表文件"
            return result
        
        # 按修改时间排序，取最新的文件
        death_files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
        death_file = death_files[0]
        
        print(f"使用最新的死亡报表文件: {death_file.name}")
        
        try:
            df = pd.read_excel(death_file, sheet_name='批次猪死亡', header=1)
            
            # 尝试获取批次信息，如果精确匹配失败则模糊匹配
            batch_info = self.get_batch_info(batch_id)
            if not batch_info:
                # 尝试模糊匹配：查找包含该批次号的文件夹
                for item in self.data_root.iterdir():
                    if item.is_dir() and not item.name.startswith('.') and batch_id in item.name:
                        batch_info = self.get_batch_info(item.name)
                        if batch_info:
                            batch_id = item.name
                            print(f"自动修正批次ID: {batch_id}")
                            break
            
            if not batch_info:
                result["message"] = f"批次不存在: {batch_id}"
                return result
            
            batch_name = batch_info.get("batch_name", "")
            df = df[df['批次号'].astype(str).str.contains(batch_id, na=False)]
            df = df[df['栋舍'].notna()]  # type: ignore

            death_records = {}
            for _, row in df.iterrows():  # type: ignore
                unit_raw = str(row.get('栋舍', '')).strip()
                unit_num = unit_raw.replace('育肥舍', '')
                date_val = row.get('单据日期', '')
                if pd.isna(date_val):  # type: ignore
                    continue
                if isinstance(date_val, str):
                    record_date = date_val.split()[0]
                else:
                    record_date = pd.to_datetime(date_val).strftime('%Y-%m-%d')  # type: ignore

                reason = row.get('死亡原因', '未知')
                if pd.isna(reason):  # type: ignore
                    reason = '未知'
                
                key = (record_date, unit_num, reason)
                if key not in death_records:
                    death_records[key] = {
                        "date": record_date, "unit_name": unit_num,
                        "death_count": 0, "culling_count": 0, "reason": reason
                    }
                death_records[key]["death_count"] += int(row.get('死亡数量', 1) or 1)
            
            death_config_path = self.data_root / "death_culling.json"
            all_data = {}
            if death_config_path.exists():
                try:
                    with open(death_config_path, 'r', encoding='utf-8') as f:
                        all_data = json.load(f)
                except:
                    all_data = {}
            all_data[batch_id] = {}
            for record in death_records.values():
                date = record["date"]
                if date not in all_data[batch_id]:
                    all_data[batch_id][date] = []
                all_data[batch_id][date].append(record)
            
            with open(death_config_path, 'w', encoding='utf-8') as f:
                json.dump(all_data, f, ensure_ascii=False, indent=2)
            
            result["success"] = True
            result["imported"] = len(death_records)
            result["message"] = f"成功导入 {len(death_records)} 条记录"
        except Exception as e:
            result["message"] = str(e)
        return result
    
    def save_death_culling_data(self, batch_id: str, date: str, data: List[Dict]):
        death_config_path = self.data_root / "death_culling.json"
        all_data = {}
        if death_config_path.exists():
            with open(death_config_path, 'r', encoding='utf-8') as f:
                all_data = json.load(f)
        if batch_id not in all_data:
            all_data[batch_id] = {}
        all_data[batch_id][date] = data
        with open(death_config_path, 'w', encoding='utf-8') as f:
            json.dump(all_data, f, ensure_ascii=False, indent=2)
    
    # ====== Comprehensive Report Generation ======
    def generate_batch_report(self, batch_id: str, date: str) -> Dict[str, Any]:
        """Generate a comprehensive batch-level report"""
        files = self.find_data_files(batch_id, date)
        batch_info = self.get_batch_info(batch_id)
        if not batch_info:
            return {"error": "Batch not found"}
        death_records = self.get_death_culling_data(batch_id, date)
        all_death_data = self.get_all_death_data(batch_id)
        
        total_deaths = 0
        for date_records in all_death_data.values():
            for record in date_records:
                total_deaths += record.get('death_count', 0)
        
        # Collect per-unit deep analysis
        unit_reports = []
        for env_file in sorted(files.get("environment", []), key=lambda x: x["unit"]):
            unit_name = env_file["unit"]
            device_file = self._find_device_file_for_unit(files.get("device", []), unit_name)
            report = self._analyze_unit_comprehensive(
                env_file["path"], device_file, unit_name, date, death_records
            )
            unit_reports.append(report)
        
        # Build batch-level summary
        batch_summary = self._build_batch_summary(unit_reports, batch_info, death_records, total_deaths)
        
        # Build cross-unit comparison
        cross_comparison = self._build_cross_unit_comparison(unit_reports)
        
        # Build trend data
        trend_data = self._build_trend_data(files, date)
        
        # Build fan operation timeline
        fan_timeline = self._build_fan_timeline(files, date)
        
        # Build death correlation analysis
        death_analysis = self._build_death_analysis(unit_reports, death_records, all_death_data, batch_info)
        
        # Build device logic anomaly detection
        device_anomalies = self._detect_device_logic_anomalies(unit_reports)
        
        # Build hourly analysis
        hourly = self._build_hourly_analysis(files, date)
        
        # Build recommendations
        recommendations = self._build_recommendations(unit_reports, device_anomalies, death_analysis)
        
        unit_types = batch_info.get("unit_types", {})
        
        return {
            "batch_info": batch_info,
            "batch_summary": batch_summary,
            "unit_reports": unit_reports,
            "cross_comparison": cross_comparison,
            "trend_data": trend_data,
            "fan_timeline": fan_timeline,
            "death_analysis": death_analysis,
            "device_anomalies": device_anomalies,
            "hourly_analysis": hourly,
            "recommendations": recommendations,
            "unit_types": unit_types
        }
    
    def _find_device_file_for_unit(self, device_files: List[Dict], unit_name: str) -> Optional[str]:
        for f in device_files:
            if f["unit"] == unit_name:
                return f["path"]
        return None
    
    def _analyze_unit_comprehensive(self, env_path: str, device_path: Optional[str], 
                                     unit_name: str, date: str, death_records: List[Dict]) -> Dict:
        """Comprehensive analysis for a single unit"""
        unit_info_df = self._load_sheet(env_path, '单元信息')
        temp_detail_df = self._load_sheet(env_path, '温度明细')
        humi_detail_df = self._load_sheet(env_path, '湿度明细')
        pressure_df = self._load_sheet(env_path, '压差明细')
        co2_df = self._load_sheet(env_path, '二氧化碳')
        fan_var_df = self._load_sheet(env_path, '变频风机')
        fan_fixed_df = self._load_sheet(env_path, '定速风机')
        alarm_df = self._load_sheet(env_path, '告警阈值')
        sensor_config_df = self._load_sheet(env_path, '传感器配置')
        
        result = {
            "unit_name": unit_name,
            "basic_info": {},
            "environment": {},
            "device_operation": {},
            "sensor_health": {},
            "anomalies": [],
            "device_issues": [],
            "risk_level": "正常",
            "risk_score": 0,
            "death_info": None,
            "recommendations": []
        }
        
        if unit_info_df.empty:
            return result
        
        # === Basic Info ===
        row0 = unit_info_df.iloc[0]
        result["basic_info"] = {
            "pig_count": int(row0.get('装猪数量', 0)),
            "pig_weight": float(row0.get('猪只体重(Kg)', 0)),
            "day_age": int(row0.get('日龄', 0)),
            "target_temp": float(row0.get('目标温度(℃)', 0)),
            "target_humidity": float(row0.get('目标湿度(%)', 0)),
            "vent_season": str(row0.get('通风季节', '')),
            "vent_mode": str(row0.get('通风模式', '')),
            "work_mode": str(row0.get('工作模式', '')),
            "unit_type": str(row0.get('单元类型', '')).strip().lower(),
            "feed_conversion_ratio": float(row0.get('料肉比', 0)),
            "daily_weight_gain": float(row0.get('日增重(Kg)', 0)),
            "feed_intake_per_day": float(row0.get('日采食量(Kg)', 0)),
        }
        
        # === Environment Analysis ===
        env = {}
        
        # Temperature
        temp_col = '舍内温度(℃)'
        if temp_col in unit_info_df.columns:
            temp_data = pd.to_numeric(unit_info_df[temp_col], errors='coerce').dropna()
            if len(temp_data) > 0:
                target_t = result["basic_info"]["target_temp"]
                temp_min = target_t - 3
                temp_max = target_t + 3
                within_target = (temp_data >= temp_min) & (temp_data <= temp_max)
                temp_avg = float(temp_data.mean())
                env["temperature"] = {
                    "avg": round(temp_avg, 1),
                    "max": round(float(temp_data.max()), 1),
                    "min": round(float(temp_data.min()), 1),
                    "std": round(float(temp_data.std()), 2),
                    "target": target_t,
                    "deviation": round(temp_avg - target_t, 1),
                    "above_target_pct": round(float((temp_data > target_t).mean()) * 100, 1),
                    "within_target_pct": round(float(within_target.mean()) * 100, 1),
                    "target_range": f"{temp_min}~{temp_max}",
                    "range": round(float(temp_data.max() - temp_data.min()), 1),
                }
        
        # Temperature sensor detail
        active_temp_sensors = []
        inactive_temp_sensors = []
        sensor_temps = {}
        for col in temp_detail_df.columns:
            if '温度传感器' in col and '℃' in col:
                non_null = pd.to_numeric(temp_detail_df[col], errors='coerce').dropna()
                if len(non_null) > 0:
                    sensor_name = col.replace('(℃)', '')
                    active_temp_sensors.append(sensor_name)
                    sensor_temps[sensor_name] = {
                        "avg": round(float(non_null.mean()), 1),
                        "max": round(float(non_null.max()), 1),
                        "min": round(float(non_null.min()), 1)
                    }
                else:
                    inactive_temp_sensors.append(col.replace('(℃)', ''))
        
        env["temp_sensors"] = {
            "active": active_temp_sensors,
            "inactive_count": len(inactive_temp_sensors),
            "total_count": len(active_temp_sensors) + len(inactive_temp_sensors),
            "sensor_data": sensor_temps,
        }
        
        # Temperature uniformity
        if len(sensor_temps) >= 2:
            avgs = [v["avg"] for v in sensor_temps.values()]
            env["temp_uniformity"] = {
                "max_diff": round(max(avgs) - min(avgs), 1),
                "is_uniform": (max(avgs) - min(avgs)) < 3.0
            }
        
        # Humidity
        humi_col = '舍内湿度(%)'
        if humi_col in unit_info_df.columns:
            humi_data = pd.to_numeric(unit_info_df[humi_col], errors='coerce').dropna()
            if len(humi_data) > 0:
                target_h = result["basic_info"]["target_humidity"]
                humi_avg = float(humi_data.mean())
                env["humidity"] = {
                    "avg": round(humi_avg, 1),
                    "max": round(float(humi_data.max()), 1),
                    "min": round(float(humi_data.min()), 1),
                    "target": target_h,
                    "deviation": round(humi_avg - target_h, 1),
                    "below_target_pct": round(float((humi_data < target_h).mean()) * 100, 1),
                }

        # CO2
        co2_col = '二氧化碳均值(ppm)'
        if co2_col in unit_info_df.columns:
            co2_data = pd.to_numeric(unit_info_df[co2_col], errors='coerce').dropna()
            if len(co2_data) > 0:
                env["co2"] = {
                    "avg": round(float(co2_data.mean()), 0),
                    "max": round(float(co2_data.max()), 0),
                    "min": round(float(co2_data.min()), 0),
                    "above_1000_pct": round(float((co2_data > 1000).mean()) * 100, 1),
                    "above_2000_pct": round(float((co2_data > 2000).mean()) * 100, 1),
                }
        
        # Humidity sensor detail
        active_humi_sensors = []
        inactive_humi_sensors = []
        sensor_humis = {}
        for col in humi_detail_df.columns:
            if '湿度传感器' in col:
                non_null = pd.to_numeric(humi_detail_df[col], errors='coerce').dropna()
                if len(non_null) > 0:
                    sensor_name = col.replace('传感器', '')
                    active_humi_sensors.append(sensor_name)
                    sensor_humis[sensor_name] = {
                        "avg": round(float(non_null.mean()), 1),
                        "max": round(float(non_null.max()), 1),
                        "min": round(float(non_null.min()), 1)
                    }
                else:
                    inactive_humi_sensors.append(col)
        
        if sensor_humis:
            env["humi_sensors"] = {
                "active": active_humi_sensors,
                "inactive_count": len(inactive_humi_sensors),
                "total_count": len(active_humi_sensors) + len(inactive_humi_sensors),
                "sensor_data": sensor_humis,
            }
            if len(sensor_humis) >= 2:
                avgs = [v["avg"] for v in sensor_humis.values()]
                env["humi_uniformity"] = {
                    "max_diff": round(max(avgs) - min(avgs), 1),
                    "is_uniform": (max(avgs) - min(avgs)) < 5.0
                }
        
        # CO2 sensor detail
        active_co2 = []
        for col in co2_df.columns:
            if '二氧化碳' in col:
                non_null = pd.to_numeric(co2_df[col], errors='coerce').dropna()
                if len(non_null) > 0:
                    active_co2.append({
                        "name": col.replace('(ppm)', ''),
                        "avg": round(float(non_null.mean()), 0),
                        "max": round(float(non_null.max()), 0),
                    })
        env["co2_sensors"] = active_co2
        
        # Pressure
        pressure_col = '压差均值(pa)'
        vent_mode = result["basic_info"].get("vent_mode", "")
        if pressure_col in unit_info_df.columns:
            p_data = pd.to_numeric(unit_info_df[pressure_col], errors='coerce').dropna()
            if len(p_data) > 0:
                negative_count = (p_data < 0).sum()

                if '负压' in vent_mode:
                    within_target_pct = round(float((p_data < 0).mean()) * 100, 1)
                    compliance_type = "负压"
                else:
                    within_target_pct = round(float((p_data > 0).mean()) * 100, 1)
                    compliance_type = "微正压"

                p_avg = float(p_data.mean())
                env["pressure"] = {
                    "avg": round(p_avg, 1),
                    "max": round(float(p_data.max()), 1),
                    "min": round(float(p_data.min()), 1),
                    "std": round(float(p_data.std()), 2),
                    "within_target_pct": within_target_pct,
                    "negative_events": int(negative_count),
                    "negative_pct": round(negative_count / len(p_data) * 100, 1),
                    "vent_mode": vent_mode,
                    "compliance_type": compliance_type,
                    "stability": "稳定" if p_data.std() < 10 else ("波动较大" if p_data.std() < 20 else "极不稳定"),
                }

        # Outdoor data
        outdoor_df = self._load_sheet(env_path, '室外数据')
        if not outdoor_df.empty and '温度' in outdoor_df.columns:
            outdoor_temp = pd.to_numeric(outdoor_df['温度'], errors='coerce').dropna()
            if len(outdoor_temp) > 0:
                out_avg = float(outdoor_temp.mean())
                env["outdoor"] = {
                    "temp_avg": round(out_avg, 1),
                    "temp_max": round(float(outdoor_temp.max()), 1),
                    "temp_min": round(float(outdoor_temp.min()), 1),
                }
                if "temperature" in env:
                    env["indoor_outdoor_diff"] = round(env["temperature"]["avg"] - out_avg, 1)

        # Ventilation level
        vent_col = '通风等级'
        if vent_col in unit_info_df.columns:
            vent_data = pd.to_numeric(unit_info_df[vent_col], errors='coerce').dropna()
            if len(vent_data) > 0:
                env["ventilation"] = {
                    "avg_level": round(float(vent_data.mean()), 1),
                    "max_level": int(vent_data.max()),
                    "min_level": int(vent_data.min()),
                }
        
        # Alarm thresholds
        if not alarm_df.empty:
            env["alarm_thresholds"] = {
                "temp_low": alarm_df.get('温度低限阈值', pd.Series([None])).iloc[0],
                "temp_high": alarm_df.get('温度高限阈值', pd.Series([None])).iloc[0],
                "humidity_high": alarm_df.get('湿度高限阈值', pd.Series([None])).iloc[0],
                "co2_high": alarm_df.get('二氧化碳高限阈值', pd.Series([None])).iloc[0],
            }
        
        # Sensor config from 传感器配置 sheet (new template)
        sensor_config = {}
        if not sensor_config_df.empty:
            row = sensor_config_df.iloc[0]
            for col in sensor_config_df.columns:
                if '实际安装' in col:
                    val = row[col]
                    if pd.notna(val):
                        sensor_config[col] = int(val) if isinstance(val, (int, float)) else str(val)
        
        result["environment"] = env
        
        # === Device Operation Analysis ===
        device_ops = {"sensor_config": sensor_config}
        
        # Variable frequency fans
        var_fans = []
        for col in fan_var_df.columns:
            if '风机组' in col:
                vals = fan_var_df[col].dropna()
                if len(vals) > 0:
                    pcts = vals.apply(lambda x: int(str(x).split('%')[0]) if '%' in str(x) else 0)
                    types = vals.apply(lambda x: str(x).split('|')[-1] if '|' in str(x) else '未知')
                    modes = vals.apply(lambda x: str(x).split('|')[1] if '|' in str(x) and len(str(x).split('|')) > 1 else '未知')
                    fan_type = types.iloc[0]
                    fan_mode = modes.iloc[0]
                    pcts_mean = float(pcts.mean())
                    is_active = pcts_mean > 0
                    var_fans.append({
                        "name": col,
                        "type": fan_type,
                        "mode": fan_mode,
                        "avg_speed": round(pcts_mean, 1),
                        "max_speed": int(pcts.max()),
                        "min_speed": int(pcts.min()),
                        "is_active": is_active,
                        "always_zero": pcts.max() == 0,
                    })
        device_ops["variable_fans"] = var_fans
        
        # Fixed speed fans
        fixed_fans = []
        for col in fan_fixed_df.columns:
            if '风机组' in col:
                vals = fan_fixed_df[col].dropna()
                if len(vals) > 0:
                    on_count = vals.apply(lambda x: 1 if '开' in str(x) else 0).sum()
                    on_rate = on_count / len(vals) * 100
                    fan_type = vals.iloc[0].split('|')[-1] if '|' in str(vals.iloc[0]) else '未知'
                    fixed_fans.append({
                        "name": col,
                        "type": fan_type,
                        "on_rate": round(on_rate, 1),
                        "is_active": on_rate > 0,
                    })
        device_ops["fixed_fans"] = fixed_fans
        
        # Device info from device file
        if device_path:
            dev_info_df = self._load_sheet(device_path, '设备信息')
            if not dev_info_df.empty:
                def safe_get_col(df, col, default=''):
                    if col in df.columns and len(df) > 0 and pd.notna(df[col].iloc[0]):
                        return str(df[col].iloc[0])
                    return default
                
                def safe_get_numeric(df, col, default=0):
                    if col in df.columns and len(df) > 0:
                        vals = pd.to_numeric(df[col], errors='coerce').dropna()
                        if len(vals) > 0:
                            return round(float(vals.mean()), 0)
                    return default
                
                result["device_info"] = {
                    "ip": safe_get_col(dev_info_df, '设备IP地址'),
                    "model": safe_get_col(dev_info_df, '设备型号'),
                    "firmware_version": safe_get_col(dev_info_df, '固件版本'),
                    "memory_usage": safe_get_numeric(dev_info_df, '内存使用率'),
                    "uptime": safe_get_col(dev_info_df, '累计运行时长'),
                    "installation_date": safe_get_col(dev_info_df, '安装日期'),
                }
            
            # Equipment installation
            install_df = self._load_sheet(device_path, '设备安装配置')
            if not install_df.empty:
                row = install_df.iloc[0]
                installed = {}
                not_installed = []
                for col in install_df.columns:
                    if '安装情况' in col:
                        device_name = col.replace('安装情况', '')
                        status = str(row[col])
                        installed[device_name] = status
                        if '未' in status:
                            not_installed.append(device_name)
                device_ops["installation"] = installed
                device_ops["not_installed"] = not_installed
            
            # Sensor config
            sensor_df = self._load_sheet(device_path, '传感器配置')
            if not sensor_df.empty:
                row = sensor_df.iloc[0]
                sensor_config = {}
                for col in sensor_df.columns:
                    if '配置安装' in col or '实际安装' in col:
                        val = row[col]
                        if pd.notna(val):
                            sensor_config[col] = int(val) if isinstance(val, (int, float)) else str(val)
                device_ops["sensor_config"] = sensor_config
            
            # 进风幕帘
            curtain_df = self._load_sheet(device_path, '进风幕帘配置')
            if not curtain_df.empty and '当前开度' in curtain_df.columns:
                open_data = pd.to_numeric(curtain_df['当前开度'], errors='coerce').dropna()
                if len(open_data) > 0:
                    device_ops["inlet_curtain"] = {
                        "avg_opening": round(float(open_data.mean()), 1),
                        "max_opening": round(float(open_data.max()), 1),
                    }
            
            # 水帘配置
            water_df = self._load_sheet(device_path, '水帘配置')
            if not water_df.empty:
                device_ops["water_curtain"] = {
                    "mode": str(water_df['水帘工作模式'].iloc[0]) if '水帘工作模式' in water_df.columns else None,
                    "status": str(water_df['工作状态'].iloc[0]) if '工作状态' in water_df.columns else None,
                }
        
        result["device_operation"] = device_ops
        
        # === Sensor Health Analysis ===
        sensor_health = {
            "temp_sensors_active": len(active_temp_sensors),
            "temp_sensors_total": len(active_temp_sensors) + len(inactive_temp_sensors),
            "humi_sensors_active": len(active_humi_sensors),
            "humi_sensors_total": len(active_humi_sensors) + len(inactive_humi_sensors),
            "co2_sensors_active": len(active_co2),
            "issues": []
        }
        
        if len(active_temp_sensors) < 3:
            sensor_health["issues"].append({
                "type": "温度传感器不足",
                "detail": f"仅{len(active_temp_sensors)}个在线（建议≥4个），温度监测可能不全面",
                "severity": "中"
            })
        
        if len(active_humi_sensors) < 2:
            sensor_health["issues"].append({
                "type": "湿度传感器不足",
                "detail": f"仅{len(active_humi_sensors)}个在线（建议≥2个），湿度监测可能不全面",
                "severity": "中"
            })
        
        temp_config = device_ops.get("sensor_config", {})
        temp_installed = temp_config.get("温度传感器实际安装", 0)
        humi_installed = temp_config.get("湿度传感器实际安装", 0)
        co2_installed = temp_config.get("CO2传感器实际安装", 0)
        
        if isinstance(temp_installed, (int, float)) and temp_installed < len(active_temp_sensors):
            sensor_health["issues"].append({
                "type": "温度传感器异常",
                "detail": f"配置{int(temp_installed)}个，实际在线{len(active_temp_sensors)}个",
                "severity": "低"
            })
        
        if isinstance(humi_installed, (int, float)) and humi_installed < len(active_humi_sensors):
            sensor_health["issues"].append({
                "type": "湿度传感器异常",
                "detail": f"配置{int(humi_installed)}个，实际在线{len(active_humi_sensors)}个",
                "severity": "低"
            })
        
        result["sensor_health"] = sensor_health
        
        # === Anomaly Detection ===
        anomalies = []
        risk_score = 0
        
        # Dynamic threshold adjustment based on day age
        day_age = result["basic_info"]["day_age"]
        temp_target = result["basic_info"]["target_temp"]
        dynamic_temp_range = self._calculate_dynamic_temp_threshold(day_age, temp_target)
        
        # Temperature anomalies
        temp_env = env.get("temperature", {})
        if temp_env:
            # Use dynamic thresholds
            temp_deviation = abs(temp_env.get("deviation") or 0)
            if temp_deviation > dynamic_temp_range["high"]:
                severity = "高" if temp_deviation > dynamic_temp_range["critical"] else "中"
                anomalies.append({
                    "category": "环境参数",
                    "type": "温度偏离目标",
                    "severity": severity,
                    "value": f'{temp_env["avg"]}℃',
                    "threshold": f'目标{temp_env["target"]}℃±{dynamic_temp_range["high"]}℃',
                    "description": f'实际均温{temp_env["avg"]}℃，偏离目标{temp_deviation}℃，{temp_env["above_target_pct"]}%时段超标',
                    "impact": "影响猪只舒适度和采食量，可能增加应激反应"
                })
                risk_score += 15 if severity == "高" else 10
            
            if temp_env.get("range", 0) > dynamic_temp_range["daily_variation"]:
                severity = "高" if temp_env["range"] > dynamic_temp_range["daily_variation"] * 1.5 else "中"
                anomalies.append({
                    "category": "环境参数",
                    "type": "日内温差过大",
                    "severity": severity,
                    "value": f'{temp_env["range"]}℃',
                    "threshold": f'{dynamic_temp_range["daily_variation"]}℃',
                    "description": f'温度波动范围{temp_env["min"]}~{temp_env["max"]}℃，温差{temp_env["range"]}℃',
                    "impact": "温差大易导致猪只应激，增加发病风险"
                })
                risk_score += 12 if severity == "高" else 8
        
        # Humidity anomalies
        humi_env = env.get("humidity", {})
        if humi_env:
            # Dynamic humidity thresholds based on day age
            humi_target = result["basic_info"]["target_humidity"]
            humi_deviation = abs(humi_env.get("deviation", 0))
            if humi_deviation > 15:  # Fixed threshold for humidity
                anomalies.append({
                    "category": "环境参数",
                    "type": "湿度偏离目标",
                    "severity": "中",
                    "value": f'{humi_env["avg"]}%',
                    "threshold": f'目标{humi_target}%±15%',
                    "description": f'实际湿度{humi_env["avg"]}%，偏离目标{abs(humi_env["deviation"])}%',
                    "impact": "目标设定值与实际值差距大，需检查加湿设备或调整目标"
                })
                risk_score += 8
        
        # Pressure anomalies
        pressure_env = env.get("pressure", {})
        if pressure_env:
            if pressure_env.get("negative_pct", 0) > 10:
                severity = "高" if pressure_env["negative_pct"] > 30 else "中"
                anomalies.append({
                    "category": "环境参数",
                    "type": "负压事件频发",
                    "severity": severity,
                    "value": f'{pressure_env["negative_pct"]}%时段',
                    "threshold": "10%",
                    "description": f'负压事件占比{pressure_env["negative_pct"]}%，最低{pressure_env["min"]}Pa',
                    "impact": "负压导致冷空气倒灌，局部温度骤降引发应激"
                })
                risk_score += 15 if severity == "高" else 10
            
            if pressure_env.get("stability", "") == "极不稳定":
                anomalies.append({
                    "category": "环境参数",
                    "type": "压差波动剧烈",
                    "severity": "中",
                    "value": f'标准差{pressure_env["std"]}Pa',
                    "threshold": "20Pa",
                    "description": f'压差标准差{pressure_env["std"]}Pa，通风气流不稳定',
                    "impact": "通风不均匀可能导致局部空气质量差"
                })
                risk_score += 8
        
        # CO2 anomalies
        co2_env = env.get("co2", {})
        if co2_env:
            # Dynamic CO2 thresholds based on day age and density
            co2_threshold = self._calculate_dynamic_co2_threshold(day_age, result["basic_info"]["pig_count"])
            if co2_env.get("avg", 0) > co2_threshold["medium"]:
                severity = "高" if co2_env["avg"] > co2_threshold["high"] else "中"
                anomalies.append({
                    "category": "环境参数",
                    "type": "CO2浓度偏高",
                    "severity": severity,
                    "value": f'{co2_env["avg"]}ppm',
                    "threshold": f'{co2_threshold["medium"]}ppm',
                    "description": f'CO2均值{co2_env["avg"]}ppm，最高{co2_env["max"]}ppm',
                    "impact": "CO2过高表明通风不足，影响猪只呼吸"
                })
                risk_score += 15 if severity == "高" else 8
        
        # Device logic anomalies
        inactive_var_fans = [f for f in var_fans if f.get("always_zero")]
        if inactive_var_fans:
            for fan in inactive_var_fans:
                anomalies.append({
                    "category": "设备运行",
                    "type": f'{fan["name"]}全天未运行',
                    "severity": "中",
                    "value": "0%",
                    "threshold": "应运行",
                    "description": f'{fan["name"]}({fan["type"]})全天频率为0%，可能故障或未配置',
                    "impact": "减少有效通风量，影响空气质量"
                })
                risk_score += 5
        
        # Temperature above target but fans not at max
        if temp_env and temp_deviation > dynamic_temp_range["high"]:
            active_var_fans = [f for f in var_fans if f.get("is_active")]
            low_speed_fans = [f for f in active_var_fans if f.get("avg_speed", 100) < 80]
            if low_speed_fans:
                fan_names = ", ".join([f["name"] for f in low_speed_fans])
                anomalies.append({
                    "category": "设备运行逻辑",
                    "type": "温度超标但风机未满负荷",
                    "severity": "高",
                    "value": f'温度偏高{temp_deviation}℃',
                    "threshold": "应增加通风",
                    "description": f'舍温持续高于目标，但{fan_names}平均频率较低，通风策略可能不当',
                    "impact": "温度无法有效降低，加重热应激"
                })
                risk_score += 12
        
        # Sensor coverage issues
        for issue in sensor_health.get("issues", []):
            anomalies.append({
                "category": "传感器监测",
                "type": issue["type"],
                "severity": issue["severity"],
                "value": "",
                "threshold": "",
                "description": issue["detail"],
                "impact": "监测盲区可能导致问题发现不及时"
            })
            risk_score += 10 if issue["severity"] == "高" else 5
        
        # Alarm threshold issues
        thresholds = env.get("alarm_thresholds", {})
        if thresholds:
            co2_threshold = thresholds.get("co2_high")
            if co2_threshold and isinstance(co2_threshold, (int, float)) and co2_threshold > 3000:
                anomalies.append({
                    "category": "配置问题",
                    "type": "CO2告警阈值设置过高",
                    "severity": "中",
                    "value": f'{int(co2_threshold)}ppm',
                    "threshold": "建议≤2000ppm",
                    "description": f'CO2告警阈值{int(co2_threshold)}ppm，远高于行业推荐值，可能导致CO2超标时无法及时告警',
                    "impact": "告警机制失效，空气质量隐患"
                })
                risk_score += 5
        
        # Death data
        unit_deaths = [d for d in death_records if d.get("unit_name") == unit_name]
        if unit_deaths:
            death_count = sum(d.get("death_count", 0) for d in unit_deaths)
            reasons = list(set(d.get("reason", "未知") for d in unit_deaths))
            
            result["death_info"] = {
                "death_count": death_count,
                "reasons": reasons,
                "possible_env_cause": self._correlate_death_env(reasons, anomalies),
            }
            
            anomalies.append({
                "category": "死亡记录",
                "type": "当日存在死亡",
                "severity": "高",
                "value": f'{death_count}头',
                "threshold": "0",
                "description": f'死亡{death_count}头，原因: {", ".join(reasons)}',
                "impact": "需排查是否与环境因素相关"
            })
            risk_score += 20
        
        result["anomalies"] = anomalies
        result["risk_score"] = min(risk_score, 100)
        
        # Calculate risk level
        if risk_score >= 50:
            result["risk_level"] = "高"
        elif risk_score >= 25:
            result["risk_level"] = "中"
        else:
            result["risk_level"] = "低"
        
        return result
    
    def _correlate_death_env(self, reasons: List[str], anomalies: List[Dict]) -> List[str]:
        correlations = []
        anomaly_types = [a.get("type", "") for a in anomalies]
        
        for reason in reasons:
            r = reason.lower()
            if "苍白" in r:
                if any("温度" in t for t in anomaly_types):
                    correlations.append(f"'{reason}': 可能与温度异常导致的慢性应激有关")
                else:
                    correlations.append(f"'{reason}': 可能与慢性消耗性疾病或内部寄生虫有关，建议临床排查")
            elif "胀气" in r:
                if any("温度" in t for t in anomaly_types):
                    correlations.append(f"'{reason}': 温度偏高可能影响消化功能导致胀气")
                elif any("压差" in t for t in anomaly_types):
                    correlations.append(f"'{reason}': 通风不稳定可能加重腹胀症状")
                else:
                    correlations.append(f"'{reason}': 建议检查饲料质量和饲喂制度")
            elif "弱" in r or "不食" in r:
                correlations.append(f"'{reason}': 可能与环境应激、密度或疾病因素综合作用有关")
            else:
                correlations.append(f"'{reason}': 建议结合临床检查综合判断")
        
        return correlations
    
    def _calculate_dynamic_temp_threshold(self, day_age: int, target_temp: float) -> Dict[str, float]:
        """Calculate dynamic temperature thresholds based on pig day age"""
        # Base thresholds
        base = {"low": 2, "high": 3, "critical": 5, "daily_variation": 5}
        
        # Adjust based on day age
        if day_age <= 30:
            # Young pigs need tighter control
            base["high"] = 2.5
            base["critical"] = 4
            base["daily_variation"] = 4
        elif day_age <= 60:
            base["high"] = 2.8
            base["critical"] = 4.5
            base["daily_variation"] = 4.5
        elif day_age <= 120:
            # Mid-stage pigs can tolerate slightly more variation
            base["high"] = 3.2
            base["critical"] = 5.5
            base["daily_variation"] = 5.5
        else:
            # Older pigs can handle more variation
            base["high"] = 3.5
            base["critical"] = 6
            base["daily_variation"] = 6
        
        return base
    
    def _calculate_dynamic_co2_threshold(self, day_age: int, pig_count: int) -> Dict[str, float]:
        """Calculate dynamic CO2 thresholds based on day age and pig density"""
        # Base thresholds
        base = {"medium": 1000, "high": 2000}
        
        # Adjust based on day age and density
        density_factor = pig_count / 1000  # Normalize to 1000 pigs
        age_factor = 1.0
        
        if day_age <= 30:
            age_factor = 0.8  # Younger pigs produce less CO2
        elif day_age <= 60:
            age_factor = 0.9
        elif day_age <= 120:
            age_factor = 1.0
        else:
            age_factor = 1.1  # Older pigs produce more CO2
        
        base["medium"] = int(base["medium"] * density_factor * age_factor)
        base["high"] = int(base["high"] * density_factor * age_factor)
        
        return base
    
    def _build_batch_summary(self, unit_reports: List[Dict], batch_info: Dict, 
                              death_records: List[Dict], total_deaths: int) -> Dict:
        """Build batch-level summary from unit reports"""
        total_pigs = sum(u["basic_info"].get("pig_count", 0) for u in unit_reports)
        avg_weight = sum(u["basic_info"].get("pig_weight", 0) for u in unit_reports) / max(len(unit_reports), 1)
        avg_day_age = sum(u["basic_info"].get("day_age", 0) for u in unit_reports) / max(len(unit_reports), 1)
        
        temps = [u["environment"].get("temperature", {}).get("avg") for u in unit_reports]
        temps = [t for t in temps if t is not None]
        humis = [u["environment"].get("humidity", {}).get("avg") for u in unit_reports]
        humis = [h for h in humis if h is not None]
        co2s = [u["environment"].get("co2", {}).get("avg") for u in unit_reports]
        co2s = [c for c in co2s if c is not None]
        
        risk_scores = [u.get("risk_score", 0) for u in unit_reports]
        high_risk_units = [u["unit_name"] for u in unit_reports if u.get("risk_level") == "高"]
        total_anomalies = sum(len(u.get("anomalies", [])) for u in unit_reports)
        
        today_deaths = sum(d.get("death_count", 0) for d in death_records)
        entry_pigs = batch_info.get("feeding_count", 0) if batch_info else 0
        mortality_rate = round(total_deaths / entry_pigs * 100, 2) if entry_pigs > 0 else 0
        
        batch_risk = "高" if any(r >= 50 for r in risk_scores) else ("中" if any(r >= 25 for r in risk_scores) else "低")
        
        outdoor = None
        for u in unit_reports:
            if u["environment"].get("outdoor"):
                outdoor = u["environment"]["outdoor"]
                break
        
        return {
            "total_pigs": total_pigs,
            "avg_weight": round(avg_weight, 1),
            "avg_day_age": round(avg_day_age),
            "unit_count": len(unit_reports),
            "batch_avg_temp": round(sum(temps) / len(temps), 1) if temps else None,
            "batch_avg_humidity": round(sum(humis) / len(humis), 1) if humis else None,
            "batch_avg_co2": round(sum(co2s) / len(co2s), 0) if co2s else None,
            "target_temp": unit_reports[0]["basic_info"]["target_temp"] if unit_reports else None,
            "target_humidity": unit_reports[0]["basic_info"]["target_humidity"] if unit_reports else None,
            "outdoor": outdoor,
            "today_deaths": today_deaths,
            "total_deaths": total_deaths,
            "mortality_rate": mortality_rate,
            "total_anomalies": total_anomalies,
            "high_risk_units": high_risk_units,
            "batch_risk_level": batch_risk,
            "avg_risk_score": round(sum(risk_scores) / max(len(risk_scores), 1), 0),
        }
    
    def _build_cross_unit_comparison(self, unit_reports: List[Dict]) -> Dict:
        """Build comparison data across units"""
        comparison = {
            "units": [],
            "best_unit": None,
            "worst_unit": None,
            "key_differences": []
        }
        
        for u in unit_reports:
            env = u.get("environment", {})
            device = u.get("device_operation", {})
            
            active_var_fans = [f for f in device.get("variable_fans", []) if f.get("is_active")]
            avg_fan_speed = round(sum(f.get("avg_speed", 0) for f in active_var_fans) / max(len(active_var_fans), 1), 1)
            
            comparison["units"].append({
                "unit": u["unit_name"],
                "risk_score": u.get("risk_score", 0),
                "risk_level": u.get("risk_level", "低"),
                "temp_avg": env.get("temperature", {}).get("avg"),
                "temp_deviation": env.get("temperature", {}).get("deviation"),
                "humidity_avg": env.get("humidity", {}).get("avg"),
                "co2_avg": env.get("co2", {}).get("avg"),
                "pressure_avg": env.get("pressure", {}).get("avg"),
                "pressure_negative_pct": env.get("pressure", {}).get("negative_pct"),
                "avg_fan_speed": avg_fan_speed,
                "temp_sensor_count": env.get("temp_sensors", {}).get("active", []),
                "anomaly_count": len(u.get("anomalies", [])),
                "death_count": u.get("death_info", {}).get("death_count", 0) if u.get("death_info") else 0,
            })
        
        if comparison["units"]:
            sorted_by_risk = sorted(comparison["units"], key=lambda x: x["risk_score"])
            comparison["best_unit"] = sorted_by_risk[0]["unit"]
            comparison["worst_unit"] = sorted_by_risk[-1]["unit"]
            
            # Key differences
            temps = [u["temp_avg"] for u in comparison["units"] if u["temp_avg"] is not None]
            if temps:
                temp_range = max(temps) - min(temps)
                if temp_range > 1:
                    comparison["key_differences"].append({
                        "metric": "温度",
                        "description": f'单元间温差{temp_range:.1f}℃',
                        "concern": temp_range > 2
                    })
            
            pressures = [u["pressure_negative_pct"] for u in comparison["units"] if u["pressure_negative_pct"] is not None]
            if pressures:
                max_neg = max(pressures)
                min_neg = min(pressures)
                if max_neg - min_neg > 10:
                    comparison["key_differences"].append({
                        "metric": "压差稳定性",
                        "description": f'负压事件占比差异最大{max_neg - min_neg:.1f}%',
                        "concern": True
                    })
        
        return comparison
    
    def _build_trend_data(self, files: Dict, date: str) -> Dict:
        """Build time-series trend data for charts"""
        result = {
            "time_labels": [],
            "temperature": [],
            "humidity": [],
            "co2": [],
            "pressure": [],
            "outdoor_temp": [],
            "ventilation_level": [],
        }
        
        time_labels_set = False
        
        for env_file in sorted(files.get("environment", []), key=lambda x: x["unit"]):
            unit = env_file["unit"]
            
            # Unit info for main metrics
            unit_df = self._load_sheet(env_file["path"], '单元信息')
            if not unit_df.empty and '时间' in unit_df.columns:
                if not time_labels_set:
                    time_series = pd.to_datetime(unit_df['时间'], errors='coerce')
                    step = max(1, len(time_series) // 144)  # ~10 min intervals
                    result["time_labels"] = [t.strftime('%H:%M') if pd.notna(t) else '' for t in time_series.iloc[::step].tolist()]
                    time_labels_set = True
                    
                    # Outdoor temp (same for all units)
                    outdoor_df = self._load_sheet(env_file["path"], '室外数据')
                    if not outdoor_df.empty and '温度' in outdoor_df.columns:
                        outdoor_vals = pd.to_numeric(outdoor_df['温度'], errors='coerce')
                        result["outdoor_temp"] = outdoor_vals.iloc[::step].tolist()
                
                step = max(1, len(unit_df) // 144)
                
                if '舍内温度(℃)' in unit_df.columns:
                    vals = pd.to_numeric(unit_df['舍内温度(℃)'], errors='coerce')
                    result["temperature"].append({"unit": unit, "values": vals.iloc[::step].tolist()})
                
                if '舍内湿度(%)' in unit_df.columns:
                    vals = pd.to_numeric(unit_df['舍内湿度(%)'], errors='coerce')
                    result["humidity"].append({"unit": unit, "values": vals.iloc[::step].tolist()})
                
                if '二氧化碳均值(ppm)' in unit_df.columns:
                    vals = pd.to_numeric(unit_df['二氧化碳均值(ppm)'], errors='coerce')
                    result["co2"].append({"unit": unit, "values": vals.iloc[::step].tolist()})
                
                if '压差均值(pa)' in unit_df.columns:
                    vals = pd.to_numeric(unit_df['压差均值(pa)'], errors='coerce')
                    result["pressure"].append({"unit": unit, "values": vals.iloc[::step].tolist()})
                
                if '通风等级' in unit_df.columns:
                    vals = pd.to_numeric(unit_df['通风等级'], errors='coerce')
                    result["ventilation_level"].append({"unit": unit, "values": vals.iloc[::step].tolist()})
        
        return result
    
    def _build_fan_timeline(self, files: Dict, date: str) -> Dict:
        """Build fan operation timeline data"""
        result = {"units": []}
        
        for env_file in sorted(files.get("environment", []), key=lambda x: x["unit"]):
            unit = env_file["unit"]
            fan_df = self._load_sheet(env_file["path"], '变频风机')
            
            if fan_df.empty:
                continue
            
            unit_type = ""
            try:
                unit_info_df = self._load_sheet(env_file["path"], '单元信息')
                if not unit_info_df.empty:
                    unit_type = str(unit_info_df.iloc[0].get('单元类型', '')).strip().lower()
            except:
                pass
            
            unit_fans = {"unit": unit, "unit_type": unit_type, "variable_fans": [], "time_labels": []}
            
            if '时间' in fan_df.columns:
                time_series = pd.to_datetime(fan_df['时间'], errors='coerce')
                step = max(1, len(time_series) // 144)
                unit_fans["time_labels"] = [t.strftime('%H:%M') if pd.notna(t) else '' for t in time_series.iloc[::step].tolist()]
            
            for col in fan_df.columns:
                if '风机组' in col:
                    vals = fan_df[col].dropna()
                    if len(vals) > 0:
                        pcts = vals.apply(lambda x: int(str(x).split('%')[0]) if '%' in str(x) else 0)
                        fan_type = vals.apply(lambda x: str(x).split('|')[-1] if '|' in str(x) else '').iloc[0]
                        step = max(1, len(pcts) // 144)
                        unit_fans["variable_fans"].append({
                            "name": f'{col}({fan_type})',
                            "values": pcts.iloc[::step].tolist()
                        })
            
            result["units"].append(unit_fans)
        
        return result
    
    def _build_death_analysis(self, unit_reports: List[Dict], death_records: List[Dict], 
                               all_death_data: Dict, batch_info: Dict = None) -> Dict:
        """Build detailed death-environment correlation analysis"""
        result = {
            "today_summary": [],
            "correlations": [],
            "risk_factors": [],
        }
        
        for record in death_records:
            unit = record.get("unit_name")
            report = next((u for u in unit_reports if u["unit_name"] == unit), None)
            
            entry = {
                "unit": unit,
                "unit_type": "",
                "death_count": record.get("death_count", 0),
                "reason": record.get("reason", "未知"),
                "env_context": {},
                "correlation_assessment": "",
            }
            
            if batch_info:
                entry["unit_type"] = batch_info.get("unit_types", {}).get(unit, "")
            
            if report:
                env = report.get("environment", {})
                entry["env_context"] = {
                    "temp_avg": env.get("temperature", {}).get("avg"),
                    "temp_deviation": env.get("temperature", {}).get("deviation"),
                    "humidity_avg": env.get("humidity", {}).get("avg"),
                    "co2_avg": env.get("co2", {}).get("avg"),
                    "pressure_negative_pct": env.get("pressure", {}).get("negative_pct"),
                    "risk_level": report.get("risk_level"),
                    "anomaly_count": len(report.get("anomalies", [])),
                }
                
                anomaly_types = [a.get("type", "") for a in report.get("anomalies", [])]
                reason = record.get("reason", "").lower()
                
                if "苍白" in reason:
                    if any("温度" in t for t in anomaly_types):
                        entry["correlation_assessment"] = "苍白可能与慢性热应激导致的贫血有关；温度持续高于目标，建议结合血液检查评估"
                    else:
                        entry["correlation_assessment"] = "苍白通常与慢性消耗性疾病或寄生虫有关，环境因素未见明显异常，建议临床排查"
                elif "胀气" in reason:
                    if any("温度" in t for t in anomaly_types):
                        entry["correlation_assessment"] = "胀气死亡可能与高温影响胃肠蠕动有关；建议关注饲喂后通风管理"
                    else:
                        entry["correlation_assessment"] = "胀气死亡建议排查饲料霉变、饲喂制度及饮水是否正常"
                else:
                    entry["correlation_assessment"] = "建议结合临床症状和病理检查综合判断"
            
            result["today_summary"].append(entry)
        
        # Risk factors summary
        env_issues_count = 0
        device_issues_count = 0
        sensor_issues_count = 0
        config_issues_count = 0
        
        for u in unit_reports:
            for a in u.get("anomalies", []):
                cat = a.get("category", "")
                if "环境" in cat:
                    env_issues_count += 1
                elif "设备" in cat:
                    device_issues_count += 1
                elif "传感器" in cat:
                    sensor_issues_count += 1
                elif "配置" in cat:
                    config_issues_count += 1
        
        result["risk_factors"] = [
            {"category": "环境参数异常", "count": env_issues_count, "level": "高" if env_issues_count > 3 else "中" if env_issues_count > 0 else "低"},
            {"category": "设备运行异常", "count": device_issues_count, "level": "高" if device_issues_count > 2 else "中" if device_issues_count > 0 else "低"},
            {"category": "传感器监测缺陷", "count": sensor_issues_count, "level": "高" if sensor_issues_count > 1 else "中" if sensor_issues_count > 0 else "低"},
            {"category": "配置问题", "count": config_issues_count, "level": "中" if config_issues_count > 0 else "低"},
        ]
        
        return result
    
    def _detect_device_logic_anomalies(self, unit_reports: List[Dict]) -> List[Dict]:
        """Detect anomalies in device operation logic across units"""
        anomalies = []
        
        # Check for cross-unit threshold inconsistency
        thresholds = {}
        for u in unit_reports:
            t = u.get("environment", {}).get("alarm_thresholds", {})
            if t:
                thresholds[u["unit_name"]] = t
        
        if len(thresholds) >= 2:
            co2_vals = {k: v.get("co2_high") for k, v in thresholds.items() if v.get("co2_high") is not None}
            if co2_vals:
                vals = list(co2_vals.values())
                if max(vals) != min(vals):
                    anomalies.append({
                        "type": "告警阈值不一致",
                        "category": "cross_unit",
                        "severity": "中",
                        "description": f'CO2告警阈值不一致: {", ".join([f"{k}={int(v)}ppm" for k, v in co2_vals.items()])}，同批次应统一标准',
                        "recommendation": "建议统一各单元CO2告警阈值为≤2000ppm"
                    })
        
        # Check for fan configuration consistency
        for u in unit_reports:
            var_fans = u.get("device_operation", {}).get("variable_fans", [])
            inactive = [f for f in var_fans if f.get("always_zero")]
            if inactive:
                for f in inactive:
                    anomalies.append({
                        "type": f'{f["name"]}始终停机',
                        "category": "device",
                        "severity": "中",
                        "unit": u["unit_name"],
                        "description": f'育肥舍{u["unit_name"]}的{f["name"]}({f["type"]})全天0%运行，需检查是否故障或为备用设备',
                        "recommendation": "如为备用设备请确认标注；如非备用，建议维修检查"
                    })
        
        # Check ventilation mode consistency
        vent_modes = {u["unit_name"]: u["basic_info"].get("vent_mode", "") for u in unit_reports}
        modes_set = set(vent_modes.values())
        if len(modes_set) > 1:
            anomalies.append({
                "type": "通风模式不一致",
                "category": "cross_unit",
                "severity": "低",
                "description": f'各单元通风模式不统一: {", ".join([f"{k}={v}" for k, v in vent_modes.items()])}',
                "recommendation": "同批次建议采用统一通风策略"
            })
        
        # ====== Combination Risk Analysis ======
        combination_risks = self._analyze_combination_risks(unit_reports)
        anomalies.extend(combination_risks)
        
        return anomalies
    
    def _analyze_combination_risks(self, unit_reports: List[Dict]) -> List[Dict]:
        """Analyze combined environmental risk factors"""
        risks = []
        
        for u in unit_reports:
            env = u.get("environment", {})
            unit = u["unit_name"]
            
            temp_avg = env.get("temperature_avg")
            humi_avg = env.get("humidity_avg")
            co2_avg = env.get("co2_avg")
            vent_level = env.get("ventilation_level_avg")
            
            risk_score = 0
            risk_factors = []
            
            # High temp + High humidity combination
            if temp_avg is not None and humi_avg is not None:
                if temp_avg > 25 and humi_avg > 75:
                    risk_score += 3
                    risk_factors.append(f"高温高湿(温度{temp_avg}℃+湿度{humi_avg}%)")
            
            # High temp + Low ventilation
            if temp_avg is not None and vent_level is not None:
                if temp_avg > 25 and vent_level < 3:
                    risk_score += 2
                    risk_factors.append(f"高温低通风(温度{temp_avg}℃+通风{vent_level}级)")
            
            # High humidity + Low ventilation
            if humi_avg is not None and vent_level is not None:
                if humi_avg > 80 and vent_level < 3:
                    risk_score += 2
                    risk_factors.append(f"高湿低通风(湿度{humi_avg}%+通风{vent_level}级)")
            
            # High CO2 + Low ventilation
            if co2_avg is not None and vent_level is not None:
                if co2_avg > 1500 and vent_level < 3:
                    risk_score += 2
                    risk_factors.append(f"高CO2低通风(CO2{int(co2_avg)}ppm+通风{vent_level}级)")
            
            # Multiple environmental parameters exceed threshold simultaneously
            exceed_count = 0
            if temp_avg is not None and temp_avg > 28:
                exceed_count += 1
            if humi_avg is not None and humi_avg > 85:
                exceed_count += 1
            if co2_avg is not None and co2_avg > 2000:
                exceed_count += 1
            
            if exceed_count >= 2:
                risk_score += exceed_count * 2
                risk_factors.append(f"多参数超标({exceed_count}项)")
            
            if risk_score >= 4:
                severity = "高" if risk_score >= 7 else "中"
                risks.append({
                    "type": "组合风险",
                    "category": "combination",
                    "severity": severity,
                    "unit": unit,
                    "description": f'育肥舍{unit}存在复合风险因素: {"; ".join(risk_factors)}',
                    "risk_score": risk_score,
                    "risk_factors": risk_factors,
                    "recommendation": f"综合评估风险等级{severity}，建议优先改善{self._get_primary_risk_factor(risk_factors)}"
                })
        
        # Cross-unit combination risk comparison
        if len(unit_reports) >= 2:
            risk_scores = [(u["unit_name"], sum([r.get("risk_score", 0) for r in risks if r.get("unit") == u["unit_name"]])) for u in unit_reports]
            max_unit = max(risk_scores, key=lambda x: x[1])
            if max_unit[1] > 0:
                risks.append({
                    "type": "批次组合风险对比",
                    "category": "cross_unit",
                    "severity": "中",
                    "description": f'批次内各单元组合风险对比: {", ".join([f"{u}:{s}分" for u, s in risk_scores])}，{max_unit[0]}风险最高',
                    "recommendation": f"重点关注{max_unit[0]}的环控策略优化"
                })
        
        return risks
    
    def _get_primary_risk_factor(self, risk_factors: List[str]) -> str:
        """Determine the primary risk factor to address"""
        priority = ["高温高湿", "多参数超标", "高湿低通风", "高温低通风", "高CO2低通风"]
        for p in priority:
            for rf in risk_factors:
                if p in rf:
                    return p
        return risk_factors[0] if risk_factors else "通风换气"
    
    def _build_hourly_analysis(self, files: Dict, date: str) -> Dict:
        """Build hourly aggregated analysis"""
        result = {"hours": [], "units": {}}
        
        for env_file in sorted(files.get("environment", []), key=lambda x: x["unit"]):
            unit = env_file["unit"]
            df = self._load_sheet(env_file["path"], '单元信息')
            
            if df.empty or '时间' not in df.columns:
                continue
            
            df['时间'] = pd.to_datetime(df['时间'], errors='coerce')
            df['hour'] = df['时间'].dt.hour
            
            hourly_data = []
            for hour in range(24):
                hour_df = df[df['hour'] == hour]
                if hour_df.empty:
                    continue
                
                entry = {"hour": hour}
                
                temp_col = '舍内温度(℃)'
                if temp_col in hour_df.columns:
                    vals = pd.to_numeric(hour_df[temp_col], errors='coerce').dropna()
                    if len(vals) > 0:
                        entry["temp_avg"] = round(float(vals.mean()), 1)

                humi_col = '舍内湿度(%)'
                if humi_col in hour_df.columns:
                    vals = pd.to_numeric(hour_df[humi_col], errors='coerce').dropna()
                    if len(vals) > 0:
                        entry["humidity_avg"] = round(float(vals.mean()), 1)

                co2_col = '二氧化碳均值(ppm)'
                if co2_col in hour_df.columns:
                    vals = pd.to_numeric(hour_df[co2_col], errors='coerce').dropna()
                    if len(vals) > 0:
                        entry["co2_avg"] = round(float(vals.mean()), 0)

                vent_col = '通风等级'
                if vent_col in hour_df.columns:
                    vals = pd.to_numeric(hour_df[vent_col], errors='coerce').dropna()
                    if len(vals) > 0:
                        entry["vent_level"] = round(float(vals.mean()), 1)
                
                hourly_data.append(entry)
            
            result["units"][unit] = hourly_data
        
        # Add lag effect analysis
        result["lag_effects"] = self._analyze_lag_effects(result["units"], date)
        
        result["hours"] = list(range(24))
        return result
    
    def _analyze_lag_effects(self, hourly_data: Dict[str, List[Dict]], date: str) -> Dict:
        """Analyze lag effects between environmental factors and death events"""
        lag_analysis = {}
        
        # Define lag periods to analyze (hours)
        lag_periods = [6, 12, 24, 48]
        
        for unit, hours in hourly_data.items():
            unit_lags = {}
            
            # Calculate average conditions for each lag period
            for lag in lag_periods:
                if len(hours) >= lag:
                    recent_hours = hours[-lag:]
                    temp_avg = sum(h.get("temp_avg", 0) for h in recent_hours if h.get("temp_avg")) / len([h for h in recent_hours if h.get("temp_avg")])
                    humi_avg = sum(h.get("humidity_avg", 0) for h in recent_hours if h.get("humidity_avg")) / len([h for h in recent_hours if h.get("humidity_avg")])
                    co2_avg = sum(h.get("co2_avg", 0) for h in recent_hours if h.get("co2_avg")) / len([h for h in recent_hours if h.get("co2_avg")])
                    
                    unit_lags[f"{lag}h"] = {
                        "temp_avg": round(temp_avg, 1) if temp_avg else None,
                        "humidity_avg": round(humi_avg, 1) if humi_avg else None,
                        "co2_avg": round(co2_avg, 0) if co2_avg else None,
                        "period_hours": lag
                    }
            
            lag_analysis[unit] = unit_lags
        
        return lag_analysis
    
    def _build_recommendations(self, unit_reports: List[Dict], device_anomalies: List[Dict], 
                                death_analysis: Dict) -> List[Dict]:
        """Build prioritized recommendations"""
        recs = []
        seen = set()
        
        # From unit anomalies
        for u in unit_reports:
            for a in u.get("anomalies", []):
                atype = a.get("type", "")
                if "温度持续高于目标" in atype and "temp_high" not in seen:
                    seen.add("temp_high")
                    recs.append({
                        "priority": "高",
                        "category": "环境调控",
                        "action": "优化降温策略",
                        "detail": "各单元舍温持续高于目标温度，建议检查通风策略设置，适当提高变频风机频率上限或开启更多通风设备",
                        "expected_effect": "舍温降低至目标范围，改善猪只舒适度"
                    })
                
                if "负压事件" in atype and "pressure" not in seen:
                    seen.add("pressure")
                    recs.append({
                        "priority": "高",
                        "category": "通风管理",
                        "action": "排查负压倒风问题",
                        "detail": "多个单元存在负压事件，冷空气可能倒灌进入舍内。建议检查进风口密封性和风机进出风配合逻辑",
                        "expected_effect": "减少局部温度骤降，降低应激发病风险"
                    })
        
        # From device anomalies
        for da in device_anomalies:
            if "阈值不一致" in da.get("type", "") and "threshold" not in seen:
                seen.add("threshold")
                recs.append({
                    "priority": "中",
                    "category": "配置管理",
                    "action": "统一各单元告警阈值",
                    "detail": da.get("description", ""),
                    "expected_effect": "统一监控标准，避免遗漏告警"
                })
        
        # Sensor issues
        for u in unit_reports:
            for issue in u.get("sensor_health", {}).get("issues", []):
                if "掉线" in issue.get("type", "") and "sensor_offline" not in seen:
                    seen.add("sensor_offline")
                    recs.append({
                        "priority": "中",
                        "category": "设备维护",
                        "action": "检修离线传感器",
                        "detail": issue.get("detail", ""),
                        "expected_effect": "恢复完整环境监测覆盖"
                    })
        
        # Death-related
        if death_analysis.get("today_summary"):
            if "death" not in seen:
                seen.add("death")
                recs.append({
                    "priority": "高",
                    "category": "生产管理",
                    "action": "加强巡栏和病死猪排查",
                    "detail": "当日存在死亡记录，建议加强巡栏频次，对病弱猪进行隔离观察，必要时进行病理检查",
                    "expected_effect": "及时发现异常猪只，降低传染风险"
                })
        
        # Sort by priority
        priority_order = {"高": 0, "中": 1, "低": 2}
        recs.sort(key=lambda x: priority_order.get(x["priority"], 3))
        
        return recs
    
    # ====== Legacy API Support ======
    def get_environment_data(self, batch_id: str, date: str) -> Dict[str, Any]:
        return self.get_batch_environment_summary(batch_id, date)
    
    def get_batch_environment_summary(self, batch_id: str, date: str) -> Dict[str, Any]:
        files = self.find_data_files(batch_id, date)
        unit_summaries = []
        for env_file in files.get("environment", []):
            env_df = self.load_environment_data(env_file["path"])
            summary = self._simple_env_summary(env_df, env_file["unit"])
            if summary:
                unit_summaries.append(summary)
        
        batch_summary = {"batch_id": batch_id, "date": date, "units": unit_summaries}
        if unit_summaries:
            temp_avgs = [u.get("temperature_avg", 0) for u in unit_summaries if u.get("temperature_avg")]
            humi_avgs = [u.get("humidity_avg", 0) for u in unit_summaries if u.get("humidity_avg")]
            batch_summary["batch_avg_temperature"] = round(sum(temp_avgs) / len(temp_avgs), 1) if temp_avgs else None
            batch_summary["batch_avg_humidity"] = round(sum(humi_avgs) / len(humi_avgs), 1) if humi_avgs else None
        return batch_summary
    
    def _simple_env_summary(self, env_df: pd.DataFrame, unit_name: str) -> Dict:
        if env_df.empty:
            return {}
        result = {"unit": unit_name}
        temp_col = '舍内温度(℃)'
        if temp_col in env_df.columns:
            data = pd.to_numeric(env_df[temp_col], errors='coerce').dropna()
            if len(data) > 0:
                result["temperature_avg"] = round(float(data.mean()), 1)
        humi_col = '舍内湿度(%)'
        if humi_col in env_df.columns:
            data = pd.to_numeric(env_df[humi_col], errors='coerce').dropna()
            if len(data) > 0:
                result["humidity_avg"] = round(float(data.mean()), 1)
        return result
    
    def get_trend_data(self, batch_id: str, date: str, page: int = 1, page_size: int = 7) -> Dict:
        files = self.find_data_files(batch_id, date)
        trend_data = self._build_trend_data(files, date)
        
        # Add pagination for historical data
        if 'historical' in trend_data:
            total_days = len(trend_data['historical'])
            start_idx = (page - 1) * page_size
            end_idx = start_idx + page_size
            trend_data['historical_paginated'] = {
                'data': trend_data['historical'][start_idx:end_idx],
                'pagination': {
                    'current_page': page,
                    'page_size': page_size,
                    'total_items': total_days,
                    'total_pages': (total_days + page_size - 1) // page_size
                }
            }
        
        return trend_data
    
    def deep_analysis(self, batch_id: str, date: str) -> Dict:
        return self.generate_batch_report(batch_id, date)
    
    # =============================================
    # HISTORICAL DATA ANALYSIS (NEW)
    # =============================================
    
    def generate_historical_report(self, batch_id: str, end_date: str, start_date: str = None, days: int = None) -> Dict[str, Any]:
        """生成历史周期报表
        Args:
            batch_id: 批次ID
            end_date: 结束日期 (YYYY-MM-DD)
            start_date: 开始日期，默认为批次入栏日期
            days: 如果指定，则从end_date往前推days天
        """
        from datetime import datetime, timedelta
        
        batch_info = self.get_batch_info(batch_id)
        if not batch_info:
            return {"error": "Batch not found"}
        
        # 确定结束日期
        if end_date:
            end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        else:
            # 全部历史模式：使用该批次的最晚日期
            all_dates = self.find_all_dates_for_batch(batch_id)
            if all_dates:
                end_dt = datetime.strptime(all_dates[-1], '%Y-%m-%d')
            else:
                return {"error": "No data found"}
        
        if days:
            start_dt = end_dt - timedelta(days=days-1)
        elif start_date:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        else:
            # 全部历史模式：使用该批次的最早日期
            all_dates = self.find_all_dates_for_batch(batch_id)
            if all_dates:
                start_dt = datetime.strptime(all_dates[0], '%Y-%m-%d')
            else:
                start_dt = end_dt - timedelta(days=30)
        
        start_date = start_dt.strftime('%Y-%m-%d')
        end_date = end_dt.strftime('%Y-%m-%d')
        
        date_range_files = self.get_date_range_files(batch_id, start_date, end_date)
        if not date_range_files:
            return {"error": "No data files found for the specified date range"}
        
        cache_key = f"{batch_id}:{start_date}:{end_date}"
        now = time.time()
        if cache_key in self._daily_summaries_cache:
            cached_time, cached_data = self._daily_summaries_cache[cache_key]
            if now - cached_time < self._daily_summaries_ttl:
                daily_summaries = cached_data
                period_stats = self._calculate_period_statistics(daily_summaries)
                death_analysis = self._analyze_historical_death(batch_id, start_date, end_date)
                trend_data = self._build_historical_trend(daily_summaries)
                unit_comparison = self._build_historical_unit_comparison(daily_summaries)
                unit_evaluation = self._evaluate_unit_performance(daily_summaries, batch_info)
                historical_anomalies = self._detect_historical_anomalies(daily_summaries, batch_info)
                return {
                    "batch_info": batch_info,
                    "date_range": {
                        "start_date": start_date,
                        "end_date": end_date,
                        "total_days": len(daily_summaries)
                    },
                    "period_statistics": period_stats,
                    "daily_summaries": daily_summaries,
                    "death_analysis": death_analysis,
                    "trend_data": trend_data,
                    "unit_comparison": unit_comparison,
                    "unit_evaluation": unit_evaluation,
                    "historical_anomalies": historical_anomalies
                }
        
        # 加载多日数据
        multi_day_data = self._load_multi_day_data(date_range_files)
        
        daily_summaries = self._calculate_daily_summaries(multi_day_data, batch_id)
        
        self._daily_summaries_cache[cache_key] = (now, daily_summaries)
        
        # 计算周期统计
        period_stats = self._calculate_period_statistics(daily_summaries)

        # 获取历史死亡数据
        death_analysis = self._analyze_historical_death(batch_id, start_date, end_date)

        # 生成趋势数据
        trend_data = self._build_historical_trend(daily_summaries)

        # 计算单元历史对比
        unit_comparison = self._build_historical_unit_comparison(daily_summaries)

        # 单元综合评价（新增）
        unit_evaluation = self._evaluate_unit_performance(daily_summaries, batch_info)

        # 历史异常检测
        historical_anomalies = self._detect_historical_anomalies(daily_summaries, batch_info)

        result = {
            "batch_info": batch_info,
            "date_range": {
                "start_date": start_date,
                "end_date": end_date,
                "total_days": len(date_range_files)
            },
            "period_statistics": period_stats,
            "daily_summaries": daily_summaries,
            "death_analysis": death_analysis,
            "trend_data": trend_data,
            "unit_comparison": unit_comparison,
            "unit_evaluation": unit_evaluation,
            "historical_anomalies": historical_anomalies
        }

        self._save_report_to_cache_file(batch_id, result)
        return result
    
    def _build_historical_unit_comparison(self, daily_summaries: List[Dict]) -> Dict:
        """构建历史周期内各单元的对比分析 - 重点关注异常情况"""
        if not daily_summaries:
            return {}
        
        unit_dates = {}
        for day in daily_summaries:
            date = day["date"]
            for unit in day.get("unit_details", {}).keys():
                if unit not in unit_dates:
                    unit_dates[unit] = []
                unit_dates[unit].append(date)
        
        unit_stats = {}
        for unit, dates in unit_dates.items():
            temps = []
            humis = []
            co2s = []
            pressures = []
            unit_type = ""
            target_temp = 0
            vent_mode = ""
            within_target_counts = {"temp": 0, "humi": 0, "co2": 0, "pressure": 0}
            total_records = {"temp": 0, "humi": 0, "co2": 0, "pressure": 0}
            
            anomaly_days = {
                "temp_high": [],
                "temp_low": [],
                "humi_high": [],
                "humi_low": [],
                "co2_high": [],
                "pressure_fail": []
            }
            daily_compliance = {"temp": [], "humi": [], "co2": [], "pressure": []}
            
            for day in daily_summaries:
                unit_detail = day.get("unit_details", {}).get(unit, {})
                date = day["date"]
                
                temp_data = unit_detail.get("temperature", {})
                humi_data = unit_detail.get("humidity", {})
                co2_data = unit_detail.get("co2", {})
                pressure_data = unit_detail.get("pressure", {})
                
                if temp_data.get("avg"):
                    temps.append(temp_data["avg"])
                    unit_type = unit_detail.get("unit_type", "")
                    target_temp = unit_detail.get("target_temp", 26)
                    temp_pct = temp_data.get("within_target_pct", 0)
                    within_target_counts["temp"] += temp_pct * 0.01
                    total_records["temp"] += 1
                    daily_compliance["temp"].append({"date": date, "pct": temp_pct})
                    
                    if temp_pct < 70:
                        if temp_data.get("avg", 0) > target_temp:
                            anomaly_days["temp_high"].append(date)
                        else:
                            anomaly_days["temp_low"].append(date)
                
                if humi_data.get("avg"):
                    humis.append(humi_data["avg"])
                    humi_pct = humi_data.get("within_target_pct", 0)
                    within_target_counts["humi"] += humi_pct * 0.01
                    total_records["humi"] += 1
                    daily_compliance["humi"].append({"date": date, "pct": humi_pct})
                    
                    if humi_pct < 60:
                        if humi_data.get("avg", 0) > 85:
                            anomaly_days["humi_high"].append(date)
                        else:
                            anomaly_days["humi_low"].append(date)
                
                if co2_data.get("avg"):
                    co2s.append(co2_data["avg"])
                    co2_pct = co2_data.get("within_target_pct", 0)
                    within_target_counts["co2"] += co2_pct * 0.01
                    total_records["co2"] += 1
                    daily_compliance["co2"].append({"date": date, "pct": co2_pct})
                    
                    if co2_pct < 70:
                        anomaly_days["co2_high"].append(date)
                
                if pressure_data.get("avg"):
                    pressures.append(pressure_data["avg"])
                    vent_mode = unit_detail.get("vent_mode", "")
                    pressure_pct = pressure_data.get("within_target_pct", 0)
                    within_target_counts["pressure"] += pressure_pct * 0.01
                    total_records["pressure"] += 1
                    daily_compliance["pressure"].append({"date": date, "pct": pressure_pct})
                    
                    if pressure_pct < 70:
                        anomaly_days["pressure_fail"].append(date)
            
            temp_within_pct = round(within_target_counts["temp"] / total_records["temp"] * 100, 1) if total_records["temp"] > 0 else 0
            humi_within_pct = round(within_target_counts["humi"] / total_records["humi"] * 100, 1) if total_records["humi"] > 0 else 0
            co2_within_pct = round(within_target_counts["co2"] / total_records["co2"] * 100, 1) if total_records["co2"] > 0 else 0
            pressure_within_pct = round(within_target_counts["pressure"] / total_records["pressure"] * 100, 1) if total_records["pressure"] > 0 else 0
            
            temp_cv = (np.std(temps) / np.mean(temps) * 100) if temps and np.mean(temps) != 0 else 0
            humi_cv = (np.std(humis) / np.mean(humis) * 100) if humis and np.mean(humis) != 0 else 0
            
            total_anomaly_days = len(set(
                anomaly_days["temp_high"] + anomaly_days["temp_low"] + 
                anomaly_days["humi_high"] + anomaly_days["humi_low"] + 
                anomaly_days["co2_high"] + anomaly_days["pressure_fail"]
            ))
            
            anomaly_score = 100 - (total_anomaly_days / len(dates) * 100) if dates else 100
            
            anomaly_breakdown = [
                {"type": "温度偏高", "count": len(anomaly_days["temp_high"]), "dates": anomaly_days["temp_high"][:5]},
                {"type": "温度偏低", "count": len(anomaly_days["temp_low"]), "dates": anomaly_days["temp_low"][:5]},
                {"type": "湿度过高", "count": len(anomaly_days["humi_high"]), "dates": anomaly_days["humi_high"][:5]},
                {"type": "湿度过低", "count": len(anomaly_days["humi_low"]), "dates": anomaly_days["humi_low"][:5]},
                {"type": "CO2超标", "count": len(anomaly_days["co2_high"]), "dates": anomaly_days["co2_high"][:5]},
                {"type": "压差异常", "count": len(anomaly_days["pressure_fail"]), "dates": anomaly_days["pressure_fail"][:5]},
            ]
            anomaly_breakdown = [a for a in anomaly_breakdown if a["count"] > 0]
            
            unit_stats[unit] = {
                "unit_type": unit_type,
                "target_temp": target_temp,
                "data_dates": sorted(dates),
                "date_range": {
                    "start": min(dates),
                    "end": max(dates),
                    "days": len(dates)
                },
                "temperature": {
                    "avg": round(np.mean(temps), 1) if temps else None,
                    "max": round(max(temps), 1) if temps else None,
                    "min": round(min(temps), 1) if temps else None,
                    "std": round(np.std(temps), 2) if temps else None,
                    "cv": round(temp_cv, 2),
                    "within_target_pct": temp_within_pct,
                    "target_range": f"{target_temp-3}~{target_temp+3}" if target_temp else "",
                    "stability": "稳定" if temp_cv < 5 else ("一般" if temp_cv < 10 else "波动大"),
                    "anomaly_days": len(anomaly_days["temp_high"]) + len(anomaly_days["temp_low"])
                },
                "humidity": {
                    "avg": round(np.mean(humis), 1) if humis else None,
                    "max": round(max(humis), 1) if humis else None,
                    "min": round(min(humis), 1) if humis else None,
                    "std": round(np.std(humis), 2) if humis else None,
                    "cv": round(humi_cv, 2),
                    "within_target_pct": humi_within_pct,
                    "stability": "稳定" if humi_cv < 10 else ("一般" if humi_cv < 20 else "波动大"),
                    "anomaly_days": len(anomaly_days["humi_high"]) + len(anomaly_days["humi_low"])
                },
                "co2": {
                    "avg": round(np.mean(co2s), 0) if co2s else None,
                    "max": round(max(co2s), 0) if co2s else None,
                    "within_target_pct": co2_within_pct,
                    "anomaly_days": len(anomaly_days["co2_high"])
                },
                "pressure": {
                    "avg": round(np.mean(pressures), 1) if pressures else None,
                    "within_target_pct": pressure_within_pct,
                    "vent_mode": vent_mode,
                    "target_pressure": "正压>0" if '正压' in vent_mode else "负压>0" if '负压' in vent_mode else "5-15Pa",
                    "anomaly_days": len(anomaly_days["pressure_fail"])
                },
                "anomaly": {
                    "total_days": total_anomaly_days,
                    "anomaly_rate": round((1 - anomaly_score/100) * 100, 1),
                    "breakdown": anomaly_breakdown,
                    "score": round(anomaly_score, 1)
                },
                "daily_compliance": daily_compliance,
                "data_days": len(dates)
            }
        
        sorted_by_anomaly = sorted(unit_stats.items(), 
                                   key=lambda x: x[1]["anomaly"]["total_days"])
        
        return {
            "units": unit_stats,
            "best_unit": sorted_by_anomaly[0][0] if sorted_by_anomaly else None,
            "worst_unit": sorted_by_anomaly[-1][0] if sorted_by_anomaly else None,
            "unit_count": len(unit_stats),
            "unit_dates": unit_dates
        }
    
    def _evaluate_unit_performance(self, daily_summaries: List[Dict], batch_info: Dict) -> Dict:
        """评价各单元的环境控制表现，返回各指标达标率"""
        if not daily_summaries:
            return {}

        unit_dates = {}
        for day in daily_summaries:
            date = day["date"]
            for unit in day.get("unit_details", {}).keys():
                if unit not in unit_dates:
                    unit_dates[unit] = []
                unit_dates[unit].append(date)

        unit_results = []

        for unit, dates in unit_dates.items():
            temps = []
            humis = []
            co2s = []
            pressures = []
            pig_counts = []
            compliant_temps = 0
            compliant_humis = 0
            compliant_co2s = 0
            compliant_pressures = 0
            total_records = 0
            unit_type = ""

            for day in daily_summaries:
                if day["date"] not in dates:
                    continue

                unit_detail = day.get("unit_details", {}).get(unit, {})
                unit_type = unit_detail.get("unit_type", "")

                temp_data = unit_detail.get("temperature", {})
                if temp_data.get("avg") is not None:
                    temps.append(temp_data["avg"])
                    total_records += 1
                    temp_within = temp_data.get("within_target_pct", 0)
                    compliant_temps += temp_within
                    # 收集存栏数据
                    pig_count = temp_data.get("pig_count", 0)
                    if pig_count > 0:
                        pig_counts.append(pig_count)

                humi_data = unit_detail.get("humidity", {})
                if humi_data.get("avg") is not None:
                    humis.append(humi_data["avg"])
                    humi_within = humi_data.get("within_target_pct", 0)
                    compliant_humis += humi_within

                co2_data = unit_detail.get("co2", {})
                if co2_data.get("avg") is not None:
                    co2s.append(co2_data["avg"])
                    co2_within = co2_data.get("within_target_pct", 0)
                    compliant_co2s += co2_within

                pressure_data = unit_detail.get("pressure", {})
                if pressure_data.get("avg") is not None:
                    pressures.append(pressure_data["avg"])
                    pressure_within = pressure_data.get("within_target_pct", 0)
                    compliant_pressures += pressure_within

            if not temps:
                continue

            temp_cv = round(np.std(temps) / np.mean(temps) * 100, 2) if np.mean(temps) != 0 else 0

            # 计算平均存栏，去掉第一天和最后一天的脏数据
            avg_pig_count = 0
            if len(pig_counts) > 2:
                # 去掉第一天和最后一天的数据
                cleaned_pig_counts = pig_counts[1:-1]
                if cleaned_pig_counts:
                    avg_pig_count = round(np.mean(cleaned_pig_counts), 0)
            elif len(pig_counts) > 0:
                # 如果数据不足3天，使用所有数据
                avg_pig_count = round(np.mean(pig_counts), 0)

            unit_results.append({
                "unit": unit,
                "unit_type": unit_type,
                "metrics": {
                    "temp_avg": round(np.mean(temps), 1),
                    "temp_stability": temp_cv,
                    "temp_compliance_rate": round(compliant_temps / len(temps), 1) if temps else 0,
                    "humi_avg": round(np.mean(humis), 1) if humis else None,
                    "humi_compliance_rate": round(compliant_humis / len(humis), 1) if humis else 0,
                    "co2_avg": round(np.mean(co2s), 0) if co2s else None,
                    "co2_compliance_rate": round(compliant_co2s / len(co2s), 1) if co2s else 0,
                    "pressure_avg": round(np.mean(pressures), 1) if pressures else None,
                    "pressure_compliance_rate": round(compliant_pressures / len(pressures), 1) if pressures else 0,
                    "avg_pig_count": avg_pig_count
                },
                "data_days": len(dates)
            })

        return {
            "units": unit_results
        }
    
    def _detect_historical_anomalies(self, daily_summaries: List[Dict], batch_info: Dict) -> List[Dict]:
        """检测历史周期内的异常"""
        anomalies = []
        
        if not daily_summaries:
            return anomalies
        
        target_temp = batch_info.get("target_temp") or 26
        
        # 1. 检测高温天数
        high_temp_days = [d for d in daily_summaries 
                         if (d.get("temperature", {}).get("avg") or 0) > target_temp + 3]
        if len(high_temp_days) >= 3:
            anomalies.append({
                "type": "持续高温",
                "category": "环境参数",
                "severity": "高" if len(high_temp_days) >= 7 else "中",
                "description": f"周期内有{len(high_temp_days)}天平均温度超过目标温度3℃以上",
                "affected_dates": [d["date"] for d in high_temp_days[:5]],
                "impact": "持续高温可能导致猪只热应激，影响生长性能"
            })
        
        # 2. 检测温度波动大的天数
        high_variation_days = []
        for d in daily_summaries:
            temp = d.get("temperature", {})
            temp_max = temp.get("max")
            temp_min = temp.get("min")
            if temp_max is not None and temp_min is not None and (temp_max - temp_min) > 8:
                high_variation_days.append(d)
        
        if len(high_variation_days) >= 3:
            anomalies.append({
                "type": "日内温差过大",
                "category": "环境参数",
                "severity": "中",
                "description": f"周期内有{len(high_variation_days)}天日内温差超过8℃",
                "affected_dates": [d["date"] for d in high_variation_days[:5]],
                "impact": "温差过大易导致猪只应激，增加发病风险"
            })
        
        # 3. 检测CO2超标天数
        high_co2_days = [d for d in daily_summaries 
                        if (d.get("co2", {}).get("avg") or 0) > 1500]
        if len(high_co2_days) >= 3:
            anomalies.append({
                "type": "CO2浓度偏高",
                "category": "环境参数",
                "severity": "高" if len(high_co2_days) >= 7 else "中",
                "description": f"周期内有{len(high_co2_days)}天CO2平均浓度超过1500ppm",
                "affected_dates": [d["date"] for d in high_co2_days[:5]],
                "impact": "CO2过高表明通风不足，影响猪只呼吸健康"
            })
        
        # 4. 检测单元间差异
        for day in daily_summaries:
            unit_details = day.get("unit_details", {})
            if len(unit_details) >= 2:
                temps = [u.get("temperature", {}).get("avg") for u in unit_details.values() 
                        if u.get("temperature", {}).get("avg")]
                if temps and max(temps) - min(temps) > 3:
                    anomalies.append({
                        "type": "单元间温差过大",
                        "category": "跨单元",
                        "severity": "中",
                        "description": f"{day['date']}各单元间温差达{max(temps) - min(temps):.1f}℃",
                        "date": day["date"],
                        "impact": "单元间环境差异大，可能导致生产性能不一致"
                    })
                    break  # 只报告一次
        
        # 5. 检测数据缺失
        total_units = len(batch_info.get("units", []))
        missing_data_days = [d for d in daily_summaries if d.get("unit_count", 0) < total_units]
        if len(missing_data_days) > 0:
            anomalies.append({
                "type": "数据缺失",
                "category": "数据质量",
                "severity": "低",
                "description": f"周期内有{len(missing_data_days)}天部分单元数据缺失",
                "affected_dates": [d["date"] for d in missing_data_days[:5]],
                "impact": "数据不完整可能影响分析准确性"
            })
        
        return anomalies
    
    def _load_multi_day_data(self, date_range_files: Dict) -> Dict[str, Dict[str, pd.DataFrame]]:
        """加载多日数据
        Returns:
            Dict[date, Dict[unit, Dict[data_type, DataFrame]]]
        """
        result = {}
        file_cache_keys_loaded = set()  # 记录已加载的文件缓存 key
            
        # 读取所有需要的列（不能减少，否则后续处理会失败）
        needed_columns = [
            '时间', '单元类型', '目标温度(℃)', '目标湿度(%)', '通风模式',
            '舍内温度(℃)', '舍内湿度(%)', '二氧化碳均值(ppm)', '压差均值(pa)',
            '栋舍', '单元', '装猪数量',
            # 以下列也在 CSV 中存在，需要包含
            '场区', '猪只体重(Kg)', '日龄', '通风季节', '工作模式', '通风等级'
        ]
            
        for date, files in date_range_files.items():
            result[date] = {}
                
            unit_env_files = {}
            for env_file in files.get("environment", []):
                unit = env_file["unit"]
                unit_env_files[unit] = env_file["path"]
                
            for unit, env_path in unit_env_files.items():
                # 使用文件路径作为缓存 key，而不是日期 + 路径
                cache_key = f"file_{env_path}"
                    
                if cache_key in self._sheet_cache:
                    # 从缓存中获取
                    result[date][unit] = self._sheet_cache[cache_key]
                else:
                    data = {
                        "unit_info": self._load_sheet(env_path, '单元信息', usecols=needed_columns),
                        "_env_path": env_path
                    }
                    self._sheet_cache[cache_key] = data
                    file_cache_keys_loaded.add(cache_key)
                    result[date][unit] = data
            
        return result
    
    def _calculate_daily_summaries(self, multi_day_data: Dict, batch_id: str) -> List[Dict]:
        """计算每日汇总指标（直接从单元信息 sheet 获取每分钟数据）"""
        from datetime import datetime
            
        daily_summaries = []
            
        for date in sorted(multi_day_data.keys()):
            date_data = multi_day_data[date]
                
            if not date_data:
                continue
                
            all_day_temps = []
            all_day_humis = []
            all_day_co2s = []
            all_day_pressures = []
            
            unit_details = {}
            
            # 记录是否已获取当日的日龄（每个日期只需要从当日有猪的一个单元获取日龄）
            day_age_for_date = None
            
            for unit, data in date_data.items():
                unit_info = data.get("unit_info", pd.DataFrame())
                
                unit_summary = {
                    "temperature": {},
                    "humidity": {},
                    "co2": {},
                    "pressure": {},
                    "unit_type": "",
                    "target_temp": 0,
                    "target_humidity": 0,
                    "vent_mode": ""
                }
                
                target_temp = 26
                target_humidity = 60
                vent_mode = ""
                unit_type = ""
                
                if not unit_info.empty:
                    row0 = unit_info.iloc[0]
                    unit_type = str(row0.get('单元类型', '')).strip().lower()
                    vent_mode = str(row0.get('通风模式', '')).strip().lower()
                    
                    # 计算当天的平均目标温度
                    if '时间' in unit_info.columns and '目标温度(℃)' in unit_info.columns:
                        unit_info['时间'] = pd.to_datetime(unit_info['时间'], errors='coerce')
                        unit_info['date'] = unit_info['时间'].dt.date
                        target_date = datetime.strptime(date, '%Y-%m-%d').date()
                        day_unit_info = unit_info[unit_info['date'] == target_date]
                        if not day_unit_info.empty:
                            target_temps = pd.to_numeric(day_unit_info['目标温度(℃)'], errors='coerce').dropna()
                            if len(target_temps) > 0:
                                target_temp = round(float(target_temps.mean()), 1)
                            else:
                                # 如果当天没有目标温度数据，使用第一行的目标温度
                                target_temp = float(row0.get('目标温度(℃)', 26))
                        else:
                            # 如果当天没有数据，使用第一行的目标温度
                            target_temp = float(row0.get('目标温度(℃)', 26))
                    else:
                        # 如果没有时间列或目标温度列，使用第一行的目标温度
                        target_temp = float(row0.get('目标温度(℃)', 26))
                    
                    target_humidity = float(row0.get('目标湿度(%)', 60))
                    
                    unit_summary["unit_type"] = unit_type
                    unit_summary["target_temp"] = target_temp
                    unit_summary["target_humidity"] = target_humidity
                    unit_summary["vent_mode"] = vent_mode
                
                temp_min = target_temp - 3
                temp_max = target_temp + 3
                
                day_df = pd.DataFrame()
                if not unit_info.empty and '时间' in unit_info.columns:
                    unit_info = unit_info.copy()
                    unit_info['时间'] = pd.to_datetime(unit_info['时间'], errors='coerce')
                    unit_info['date'] = unit_info['时间'].dt.date
                    day_df = unit_info[unit_info['date'] == datetime.strptime(date, '%Y-%m-%d').date()]
                    
                    # CSV文件已经在转换时进行了1分钟采样，无需再次采样
                    # 只对Excel文件进行采样
                    if not day_df.empty and len(day_df) > 0 and 'csv' not in str(data.get("_env_path", "")):
                        day_df = day_df.sort_values('时间')
                        day_df['minute'] = day_df['时间'].dt.minute
                        day_df['one_min_interval'] = day_df['minute']
                        day_df['sample_key'] = day_df['时间'].dt.strftime('%Y-%m-%d %H:') + day_df['one_min_interval'].astype(str).str.zfill(2)
                        day_df = day_df.drop_duplicates(subset=['sample_key'], keep='first')
                        day_df = day_df.drop(columns=['minute', 'one_min_interval', 'sample_key'])
                    
                    temp_col = '舍内温度(℃)'
                    humi_col = '舍内湿度(%)'
                    target_temp_col = '目标温度(℃)'
                    target_humi_col = '目标湿度(%)'
                    co2_col = '二氧化碳均值(ppm)'
                    pressure_col = '压差均值(pa)'

                    pig_count = 0
                    if '装猪数量' in day_df.columns and not day_df.empty:
                        day_df_sorted = day_df.sort_values('时间')
                        last_record = day_df_sorted.iloc[-1]
                        last_pig_count = last_record.get('装猪数量', 0)
                        if pd.notna(last_pig_count):
                            pig_count = int(last_pig_count)
                    if pig_count == 0 and '装猪数量' in unit_info.columns and not unit_info.empty:
                        unit_info_sorted = unit_info.sort_values('时间')
                        last_record = unit_info_sorted.iloc[-1]
                        last_pig_count = last_record.get('装猪数量', 0)
                        if pd.notna(last_pig_count):
                            pig_count = int(last_pig_count)

                    unit_summary["pig_count"] = pig_count

                    # 提取日龄字段（从当日有猪的任意一个单元获取，每个日期只获取一次）
                    # 注意：取第三条有效值，因为第一条可能涉及跨天上报，日龄未更新
                    day_age = None
                    if day_age_for_date is None and pig_count > 0 and '日龄' in day_df.columns and not day_df.empty:
                        day_age_vals = pd.to_numeric(day_df['日龄'], errors='coerce').dropna()
                        if len(day_age_vals) >= 3:
                            day_age = int(day_age_vals.iloc[2])
                            day_age_for_date = day_age
                        elif len(day_age_vals) > 0:
                            day_age = int(day_age_vals.iloc[0])
                            day_age_for_date = day_age
                    elif day_age_for_date is not None:
                        day_age = day_age_for_date
                    
                    unit_summary["day_age"] = day_age

                    if temp_col in day_df.columns and target_temp_col in day_df.columns:
                        temps = pd.to_numeric(day_df[temp_col], errors='coerce')
                        target_temps = pd.to_numeric(day_df[target_temp_col], errors='coerce')
                        if len(temps) > 0:
                            all_day_temps.extend(temps.dropna().tolist())
                            valid_mask = ~(temps.isna() | target_temps.isna())

                            target_temp_avg = round(float(target_temps[valid_mask].mean()), 1) if valid_mask.sum() > 0 else 26

                            if valid_mask.sum() > 0:
                                temps_valid = temps[valid_mask].values
                                target_temps_valid = target_temps[valid_mask].values

                                above_mask = temps_valid > (target_temps_valid + 3)
                                below_mask = temps_valid < (target_temps_valid - 3)

                                above_duration = int(np.sum(above_mask))
                                below_duration = int(np.sum(below_mask))

                                above_count = 0
                                below_count = 0

                                if len(temps_valid) > 0:
                                    above_transitions = np.diff(np.concatenate([[False], above_mask]))
                                    above_count = int(np.sum(above_transitions))

                                    below_transitions = np.diff(np.concatenate([[False], below_mask]))
                                    below_count = int(np.sum(below_transitions))

                                within_target = ~(above_mask | below_mask)
                                within_target_pct = round(float(within_target.mean()) * 100, 1)
                            else:
                                within_target_pct = 0
                                above_count = 0
                                below_count = 0
                                above_duration = 0
                                below_duration = 0

                            hourly_temps = []
                            if not day_df.empty and '时间' in day_df.columns:
                                day_df_temp = day_df.copy()
                                day_df_temp['hour'] = day_df_temp['时间'].dt.hour
                                for h in range(24):
                                    hour_temps = day_df_temp[day_df_temp['hour'] == h][temp_col]
                                    hour_temps = pd.to_numeric(hour_temps, errors='coerce').dropna()
                                    hourly_temps.append(round(float(hour_temps.mean()), 1) if len(hour_temps) > 0 else None)

                            temps_mean = float(temps.mean())
                            unit_summary["temperature"] = {
                                "avg": round(temps_mean, 1),
                                "max": round(float(temps.max()), 1),
                                "min": round(float(temps.min()), 1),
                                "std": round(float(temps.std()), 2),
                                "within_target_pct": within_target_pct,
                                "target_range": f"动态目标±3℃",
                                "above_target_count": above_count,
                                "below_target_count": below_count,
                                "above_target_duration": above_duration,
                                "below_target_duration": below_duration,
                                "pig_count": pig_count,
                                "hourly_curve": hourly_temps
                            }
                    
                    if humi_col in day_df.columns and target_humi_col in day_df.columns:
                        humis = pd.to_numeric(day_df[humi_col], errors='coerce')
                        target_humis = pd.to_numeric(day_df[target_humi_col], errors='coerce')
                        if len(humis) > 0:
                            all_day_humis.extend(humis.dropna().tolist())
                            within_humi = (humis >= 50) & (humis <= 85)
                            within_target_pct = round(within_humi.mean() * 100, 1)
                            hourly_humis = []
                            if not day_df.empty and '时间' in day_df.columns:
                                day_df_humi = day_df.copy()
                                day_df_humi['hour'] = day_df_humi['时间'].dt.hour
                                for h in range(24):
                                    hour_humis = day_df_humi[day_df_humi['hour'] == h][humi_col]
                                    hour_humis = pd.to_numeric(hour_humis, errors='coerce').dropna()
                                    hourly_humis.append(round(hour_humis.mean(), 1) if len(hour_humis) > 0 else None)
                            unit_summary["humidity"] = {
                                "avg": round(humis.mean(), 1),
                                "max": round(humis.max(), 1),
                                "min": round(humis.min(), 1),
                                "within_target_pct": within_target_pct,
                                "hourly_curve": hourly_humis
                            }
                    
                    if co2_col in day_df.columns:
                        co2s = pd.to_numeric(day_df[co2_col], errors='coerce').dropna()
                        if len(co2s) > 0:
                            all_day_co2s.extend(co2s.tolist())
                            hourly_co2s = []
                            if not day_df.empty and '时间' in day_df.columns:
                                day_df_co2 = day_df.copy()
                                day_df_co2['hour'] = day_df_co2['时间'].dt.hour
                                for h in range(24):
                                    hour_co2s = day_df_co2[day_df_co2['hour'] == h][co2_col]
                                    hour_co2s = pd.to_numeric(hour_co2s, errors='coerce').dropna()
                                    hourly_co2s.append(round(hour_co2s.mean(), 0) if len(hour_co2s) > 0 else None)
                            unit_summary["co2"] = {
                                "avg": round(co2s.mean(), 0),
                                "max": round(co2s.max(), 0),
                                "within_target_pct": round((co2s <= 3000).mean() * 100, 1),
                                "hourly_curve": hourly_co2s
                            }
                    
                    if pressure_col in day_df.columns:
                        pressures = pd.to_numeric(day_df[pressure_col], errors='coerce').dropna()
                        if len(pressures) > 0:
                            all_day_pressures.extend(pressures.tolist())

                            if '负压' in vent_mode:
                                within_target_pct = round((pressures < 0).mean() * 100, 1)
                            else:
                                within_target_pct = round((pressures > 0).mean() * 100, 1)

                            hourly_pressures = []
                            if not day_df.empty and '时间' in day_df.columns:
                                day_df_pressure = day_df.copy()
                                day_df_pressure['hour'] = day_df_pressure['时间'].dt.hour
                                for h in range(24):
                                    hour_pressures = day_df_pressure[day_df_pressure['hour'] == h][pressure_col]
                                    hour_pressures = pd.to_numeric(hour_pressures, errors='coerce').dropna()
                                    hourly_pressures.append(round(hour_pressures.mean(), 1) if len(hour_pressures) > 0 else None)

                            unit_summary["pressure"] = {
                                "avg": round(pressures.mean(), 1),
                                "max": round(pressures.max(), 1),
                                "min": round(pressures.min(), 1),
                                "within_target_pct": within_target_pct,
                                "vent_mode": vent_mode,
                                "hourly_curve": hourly_pressures
                            }
                
                unit_details[unit] = unit_summary

            outdoor_temp = None
            outdoor_temp_max = None
            outdoor_temp_min = None
            target_temp = None
            target_humidity = None
            # 计算所有单元的目标温度均值
            target_temps = []
            for unit, detail in unit_details.items():
                if detail.get("target_temp"):
                    target_temps.append(detail["target_temp"])
            if target_temps:
                target_temp = round(sum(target_temps) / len(target_temps), 1)
                target_humidity = 60

            env_path = None
            for unit_key, unit_data in date_data.items():
                if isinstance(unit_data, dict) and unit_data.get("_env_path"):
                    env_path = unit_data.get("_env_path")
                    break
            if env_path:
                cache_key = f"{env_path}_{date}"
                if cache_key in self._outdoor_temp_cache:
                    outdoor_data = self._outdoor_temp_cache[cache_key]
                    outdoor_temp = outdoor_data['avg']
                    outdoor_temp_max = outdoor_data['max']
                    outdoor_temp_min = outdoor_data['min']
                else:
                    try:
                        # 优先读取CSV文件（速度快5-10倍）
                        csv_path = Path(env_path).parent / (Path(env_path).stem + "_室外数据.csv")
                        if csv_path.exists():
                            outdoor_df = pd.read_csv(csv_path, encoding='utf-8-sig')
                        else:
                            outdoor_df = pd.read_excel(env_path, sheet_name='室外数据')
                        
                        if not outdoor_df.empty:
                            if '时间' in outdoor_df.columns:
                                outdoor_df['时间'] = pd.to_datetime(outdoor_df['时间'], errors='coerce')
                                outdoor_df['date'] = outdoor_df['时间'].dt.date
                                target_date = datetime.strptime(date, '%Y-%m-%d').date()
                                day_outdoor_df = outdoor_df[outdoor_df['date'] == target_date]
                                
                                # CSV文件已经进行了1分钟采样，无需再次采样
                                if not csv_path.exists() and not day_outdoor_df.empty and len(day_outdoor_df) > 0:
                                    day_outdoor_df = day_outdoor_df.sort_values('时间')
                                    day_outdoor_df['minute'] = day_outdoor_df['时间'].dt.minute
                                    day_outdoor_df['one_min_interval'] = day_outdoor_df['minute']
                                    day_outdoor_df['sample_key'] = day_outdoor_df['时间'].dt.strftime('%Y-%m-%d %H:') + day_outdoor_df['one_min_interval'].astype(str).str.zfill(2)
                                    day_outdoor_df = day_outdoor_df.drop_duplicates(subset=['sample_key'], keep='first')
                                
                                if not day_outdoor_df.empty and '温度' in day_outdoor_df.columns:
                                    outdoor_vals = pd.to_numeric(day_outdoor_df['温度'], errors='coerce')
                                    valid_count = len(outdoor_vals.dropna())
                                    if valid_count > 0:
                                        outdoor_temp = round(outdoor_vals.mean(), 1)
                                        outdoor_temp_max = round(outdoor_vals.max(), 1)
                                        outdoor_temp_min = round(outdoor_vals.min(), 1)
                                        self._outdoor_temp_cache[cache_key] = {
                                            'avg': outdoor_temp,
                                            'max': outdoor_temp_max,
                                            'min': outdoor_temp_min
                                        }
                            elif len(outdoor_df.columns) > 5:
                                outdoor_vals = pd.to_numeric(outdoor_df.iloc[:, 5], errors='coerce')
                                valid_count = len(outdoor_vals.dropna())
                                if valid_count > 0:
                                    outdoor_temp = round(outdoor_vals.mean(), 1)
                                    outdoor_temp_max = round(outdoor_vals.max(), 1)
                                    outdoor_temp_min = round(outdoor_vals.min(), 1)
                                    self._outdoor_temp_cache[cache_key] = {
                                        'avg': outdoor_temp,
                                        'max': outdoor_temp_max,
                                        'min': outdoor_temp_min
                                    }
                    except Exception as e:
                        print(f"Warning: Failed to read outdoor temp: {e}")

            day_summary = {
                "date": date,
                "temperature": {},
                "humidity": {},
                "co2": {},
                "pressure": {},
                "unit_details": unit_details,
                "unit_count": len(unit_details),
                "outdoor_temp": outdoor_temp,
                "outdoor_temp_max": outdoor_temp_max,
                "outdoor_temp_min": outdoor_temp_min,
                "target_temp": target_temp,
                "target_humidity": target_humidity,
                "day_age": day_age_for_date
            }
            
            if all_day_temps:
                day_summary["temperature"] = {
                    "avg": round(np.mean(all_day_temps), 1),
                    "max": round(np.max(all_day_temps), 1),
                    "min": round(np.min(all_day_temps), 1)
                }
            if all_day_humis:
                day_summary["humidity"] = {
                    "avg": round(np.mean(all_day_humis), 1),
                    "max": round(np.max(all_day_humis), 1),
                    "min": round(np.min(all_day_humis), 1)
                }
            if all_day_co2s:
                day_summary["co2"] = {
                    "avg": round(np.mean(all_day_co2s), 0),
                    "max": round(np.max(all_day_co2s), 0),
                    "min": round(np.min(all_day_co2s), 0)
                }
            if all_day_pressures:
                day_summary["pressure"] = {
                    "avg": round(np.mean(all_day_pressures), 1),
                    "max": round(np.max(all_day_pressures), 1),
                    "min": round(np.min(all_day_pressures), 1)
                }
            
            if all_day_temps or all_day_humis or all_day_co2s or all_day_pressures:
                daily_summaries.append(day_summary)
        
        return daily_summaries
    
    def _calculate_period_statistics(self, daily_summaries: List[Dict]) -> Dict:
        """计算周期统计（整个时间段的汇总）"""
        if not daily_summaries:
            return {}

        all_temps = []
        all_humis = []
        all_co2s = []
        all_pressures = []

        daily_temp_compliance_rates = []
        daily_humi_compliance_rates = []
        daily_co2_compliance_rates = []
        daily_pressure_compliance_rates = []

        for d in daily_summaries:
            temp_data = d.get("temperature", {})
            humi_data = d.get("humidity", {})
            co2_data = d.get("co2", {})
            pressure_data = d.get("pressure", {})
            unit_details = d.get("unit_details", {})

            if temp_data.get("avg") is not None:
                all_temps.append(temp_data["avg"])
            if humi_data.get("avg") is not None:
                all_humis.append(humi_data["avg"])
            if co2_data.get("avg") is not None:
                all_co2s.append(co2_data["avg"])
            if pressure_data.get("avg") is not None:
                all_pressures.append(pressure_data["avg"])

            unit_temp_rates = []
            unit_humi_rates = []
            unit_co2_rates = []
            unit_pressure_rates = []

            for unit_id, unit_data in unit_details.items():
                pig_count = unit_data.get("pig_count", 0)
                if pig_count <= 0:
                    continue

                temp_unit = unit_data.get("temperature", {})
                humi_unit = unit_data.get("humidity", {})
                co2_unit = unit_data.get("co2", {})
                pressure_unit = unit_data.get("pressure", {})

                if temp_unit.get("within_target_pct") is not None:
                    unit_temp_rates.append(temp_unit["within_target_pct"])
                if humi_unit.get("within_target_pct") is not None:
                    unit_humi_rates.append(humi_unit["within_target_pct"])
                if co2_unit.get("within_target_pct") is not None:
                    unit_co2_rates.append(co2_unit["within_target_pct"])
                if pressure_unit.get("within_target_pct") is not None:
                    unit_pressure_rates.append(pressure_unit["within_target_pct"])

            if unit_temp_rates:
                daily_temp_compliance_rates.append(np.mean(unit_temp_rates))
            if unit_humi_rates:
                daily_humi_compliance_rates.append(np.mean(unit_humi_rates))
            if unit_co2_rates:
                daily_co2_compliance_rates.append(np.mean(unit_co2_rates))
            if unit_pressure_rates:
                daily_pressure_compliance_rates.append(np.mean(unit_pressure_rates))

        temp_compliant = len([t for t in daily_temp_compliance_rates if t >= 50]) if daily_temp_compliance_rates else 0
        humi_compliant = len([h for h in daily_humi_compliance_rates if h >= 50]) if daily_humi_compliance_rates else 0
        co2_compliant = len([c for c in daily_co2_compliance_rates if c >= 50]) if daily_co2_compliance_rates else 0
        pressure_compliant = len([p for p in daily_pressure_compliance_rates if p >= 50]) if daily_pressure_compliance_rates else 0

        return {
            "temperature": {
                "avg": round(np.mean(all_temps), 1) if all_temps else None,
                "max": round(np.max(all_temps), 1) if all_temps else None,
                "min": round(np.min(all_temps), 1) if all_temps else None,
                "std": round(np.std(all_temps), 2) if all_temps else None,
                "compliant_days": temp_compliant,
                "compliant_rate": round(temp_compliant / len(daily_temp_compliance_rates) * 100, 1) if daily_temp_compliance_rates else 0,
            },
            "humidity": {
                "avg": round(np.mean(all_humis), 1) if all_humis else None,
                "max": round(np.max(all_humis), 1) if all_humis else None,
                "min": round(np.min(all_humis), 1) if all_humis else None,
                "std": round(np.std(all_humis), 2) if all_humis else None,
                "compliant_days": humi_compliant,
                "compliant_rate": round(humi_compliant / len(daily_humi_compliance_rates) * 100, 1) if daily_humi_compliance_rates else 0,
            },
            "co2": {
                "avg": round(np.mean(all_co2s), 0) if all_co2s else None,
                "max": round(np.max(all_co2s), 0) if all_co2s else None,
                "std": round(np.std(all_co2s), 0) if all_co2s else None,
                "compliant_days": co2_compliant,
                "compliant_rate": round(co2_compliant / len(daily_co2_compliance_rates) * 100, 1) if daily_co2_compliance_rates else 0,
            },
            "pressure": {
                "avg": round(np.mean(all_pressures), 1) if all_pressures else None,
                "std": round(np.std(all_pressures), 2) if all_pressures else None,
                "compliant_days": pressure_compliant,
                "compliant_rate": round(pressure_compliant / len(daily_pressure_compliance_rates) * 100, 1) if daily_pressure_compliance_rates else 0,
            },
            "total_days": len(daily_summaries)
        }
    
    def _analyze_historical_death(self, batch_id: str, start_date: str, end_date: str) -> Dict:
        """分析历史死亡数据"""
        from datetime import datetime, timedelta
        
        all_death_data = self.get_all_death_data(batch_id)
        
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        # 统计日期范围内的死亡
        period_deaths = 0
        daily_deaths = {}
        
        current = start_dt
        while current <= end_dt:
            date_str = current.strftime('%Y-%m-%d')
            daily_deaths[date_str] = 0
            
            if date_str in all_death_data:
                day_death_count = sum(d.get("death_count", 0) for d in all_death_data[date_str])
                period_deaths += day_death_count
                daily_deaths[date_str] = day_death_count
            
            current += timedelta(days=1)
        
        # 计算累计死亡趋势
        cumulative_deaths = []
        running_total = 0
        for date in sorted(daily_deaths.keys()):
            running_total += daily_deaths[date]
            cumulative_deaths.append({
                "date": date,
                "daily": daily_deaths[date],
                "cumulative": running_total
            })
        
        # 获取批次总猪数计算死亡率
        batch_info = self.get_batch_info(batch_id)
        total_pigs = batch_info.get("feeding_count", 0) if batch_info else 0
        mortality_rate = round(period_deaths / total_pigs * 100, 2) if total_pigs > 0 else 0
        
        return {
            "total_deaths": period_deaths,
            "mortality_rate": mortality_rate,
            "daily_deaths": daily_deaths,
            "cumulative_trend": cumulative_deaths,
            "peak_death_date": max(daily_deaths.items(), key=lambda x: x[1])[0] if daily_deaths else None,
            "peak_death_count": max(daily_deaths.values()) if daily_deaths else 0
        }
    
    def _build_historical_trend(self, daily_summaries: List[Dict]) -> Dict:
        """构建历史趋势数据（用于图表）"""
        dates = []
        temp_avgs = []
        temp_maxs = []
        temp_mins = []
        humi_avgs = []
        humi_maxs = []
        humi_mins = []
        co2_avgs = []
        co2_maxs = []
        pressure_avgs = []
        outdoor_temps = []
        target_temps = []
        target_humis = []
        all_units = set()
        
        for d in daily_summaries:
            dates.append(d["date"])
            temp_data = d.get("temperature", {})
            humi_data = d.get("humidity", {})
            co2_data = d.get("co2", {})
            pressure_data = d.get("pressure", {})

            temp_avgs.append(temp_data.get("avg"))
            temp_maxs.append(temp_data.get("max"))
            temp_mins.append(temp_data.get("min"))
            humi_avgs.append(humi_data.get("avg"))
            humi_maxs.append(humi_data.get("max"))
            humi_mins.append(humi_data.get("min"))
            co2_avgs.append(co2_data.get("avg"))
            co2_maxs.append(co2_data.get("max"))
            pressure_avgs.append(pressure_data.get("avg"))
            outdoor_temps.append(d.get("outdoor_temp"))
            target_temps.append(d.get("target_temp"))
            target_humis.append(d.get("target_humidity"))

            current_day_units = set(d.get("unit_details", {}).keys())
            all_units.update(current_day_units)

        unit_temp_data = {unit: [None] * len(dates) for unit in all_units}
        unit_temp_cv_data = {unit: [None] * len(dates) for unit in all_units}
        unit_humi_data = {unit: [None] * len(dates) for unit in all_units}
        unit_co2_data = {unit: [None] * len(dates) for unit in all_units}
        unit_pressure_data = {unit: [None] * len(dates) for unit in all_units}

        for idx, d in enumerate(daily_summaries):
            current_day_units = set(d.get("unit_details", {}).keys())
            for unit in current_day_units:
                detail = d["unit_details"][unit]
                temp_avg = detail.get("temperature", {}).get("avg")
                temp_std = detail.get("temperature", {}).get("std")
                unit_temp_data[unit][idx] = temp_avg
                # 计算温度变异系数 (CV = 标准差 / 平均值 * 100)
                if temp_avg and temp_std and temp_avg != 0:
                    unit_temp_cv_data[unit][idx] = round((temp_std / temp_avg) * 100, 2)
                else:
                    unit_temp_cv_data[unit][idx] = None
                unit_humi_data[unit][idx] = detail.get("humidity", {}).get("avg")
                unit_co2_data[unit][idx] = detail.get("co2", {}).get("avg")
                unit_pressure_data[unit][idx] = detail.get("pressure", {}).get("avg")

        return {
            "dates": dates,
            "temperature": {
                "avg": temp_avgs,
                "max": temp_maxs,
                "min": temp_mins,
                "outdoor": outdoor_temps,
                "target": target_temps,
                "units": unit_temp_data,
                "units_cv": unit_temp_cv_data
            },
            "humidity": {
                "avg": humi_avgs,
                "max": humi_maxs,
                "min": humi_mins,
                "target": target_humis,
                "units": unit_humi_data
            },
            "co2": {
                "avg": co2_avgs,
                "max": co2_maxs,
                "units": unit_co2_data
            },
            "pressure": {
                "avg": pressure_avgs,
                "units": unit_pressure_data
            }
        }
