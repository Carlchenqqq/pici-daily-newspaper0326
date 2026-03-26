# -*- coding: utf-8 -*-
import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd

units = ['4-5', '4-6', '4-7']
for unit in units:
    print(f'\n=== Unit {unit} ===')
    env_file = f'20251218/临泉第一育肥场二分场育肥舍{unit} 2026-03-10 00_00_00 至 2026-03-10 23_59_59 环境数据.xlsx'
    dev_file = f'20251218/临泉第一育肥场二分场育肥舍{unit} 2026-03-10 00_00_00 至 2026-03-10 23_59_59 设备数据.xlsx'
    
    df = pd.read_excel(env_file, sheet_name='单元信息', engine='openpyxl')
    pig_count = df['装猪数量'].iloc[0]
    pig_weight = df.iloc[0]['猪只体重(Kg)']
    day_age = df['日龄'].iloc[0]
    
    temp_vals = df['舍内温度(℃)']
    humi_vals = df['舍内湿度(%)']
    co2_vals = df['二氧化碳均值(ppm)']
    pressure_vals = df['压差均值(pa)']
    vent_level = df['通风等级']
    vent_season = df['通风季节'].iloc[0]
    vent_mode = df['通风模式'].iloc[0]
    target_temp = df['目标温度(℃)'].iloc[0]
    target_humi = df['目标湿度(%)'].iloc[0]
    
    print(f'装猪: {pig_count}, 体重: {pig_weight}kg, 日龄: {day_age}')
    print(f'舍内温度 avg={temp_vals.mean():.1f} max={temp_vals.max():.1f} min={temp_vals.min():.1f}')
    print(f'舍内湿度 avg={humi_vals.mean():.1f} max={humi_vals.max():.1f} min={humi_vals.min():.1f}')
    print(f'目标温度={target_temp} 目标湿度={target_humi}')
    print(f'CO2 avg={co2_vals.mean():.0f} max={co2_vals.max():.0f} min={co2_vals.min():.0f}')
    print(f'压差 avg={pressure_vals.mean():.1f} max={pressure_vals.max():.1f} min={pressure_vals.min():.1f}')
    print(f'通风等级 min={vent_level.min()} max={vent_level.max()}')
    print(f'通风季节={vent_season} 通风模式={vent_mode}')
    
    # Variable fans
    fan_df = pd.read_excel(env_file, sheet_name='变频风机', engine='openpyxl')
    for col in fan_df.columns:
        if '风机组' in col:
            vals = fan_df[col].dropna()
            if len(vals) > 0:
                pcts = vals.apply(lambda x: int(str(x).split('%')[0]) if '%' in str(x) else 0)
                types = vals.apply(lambda x: str(x).split('|')[-1] if '|' in str(x) else '')
                fan_type = types.iloc[0]
                print(f'  变频{col}({fan_type}): avg={pcts.mean():.1f}% max={pcts.max()}% min={pcts.min()}%')
    
    # Fixed fans
    ffan_df = pd.read_excel(env_file, sheet_name='定速风机', engine='openpyxl')
    for col in ffan_df.columns:
        if '风机组' in col:
            vals = ffan_df[col].dropna()
            if len(vals) > 0:
                on_rate = vals.apply(lambda x: 1 if '开' in str(x) else 0).mean() * 100
                fan_type = vals.iloc[0].split('|')[-1] if '|' in str(vals.iloc[0]) else ''
                if on_rate > 0:
                    print(f'  定速{col}({fan_type}): 开启率={on_rate:.1f}%')
    
    # Device info
    dev_df = pd.read_excel(dev_file, sheet_name='设备信息', engine='openpyxl')
    print(f'设备IP: {dev_df["设备IP地址"].iloc[0]}')
    print(f'内存使用率: {dev_df["内存使用率"].mean():.0f}%')
    
    # 进风幕帘
    curtain_df = pd.read_excel(dev_file, sheet_name='进风幕帘配置', engine='openpyxl')
    if '当前开度' in curtain_df.columns:
        open_data = pd.to_numeric(curtain_df['当前开度'], errors='coerce').dropna()
        if len(open_data) > 0:
            print(f'进风幕帘开度 avg={open_data.mean():.1f} max={open_data.max():.1f}')
    
    # Temp detail
    temp_detail = pd.read_excel(env_file, sheet_name='温度明细', engine='openpyxl')
    active_sensors = []
    for c in temp_detail.columns:
        if '温度传感器' in c:
            non_null = temp_detail[c].dropna()
            if len(non_null) > 0:
                active_sensors.append(c)
    print(f'活跃温度传感器: {len(active_sensors)} 个 ({", ".join(active_sensors)})')
    
    # Humidity detail
    humi_detail = pd.read_excel(env_file, sheet_name='湿度明细', engine='openpyxl')
    active_h_sensors = []
    for c in humi_detail.columns:
        if '湿度传感器' in c:
            non_null = humi_detail[c].dropna()
            if len(non_null) > 0:
                active_h_sensors.append(c)
    print(f'活跃湿度传感器: {len(active_h_sensors)} 个')
    
    # CO2 detail 
    co2_detail = pd.read_excel(env_file, sheet_name='二氧化碳', engine='openpyxl')
    active_co2 = []
    for c in co2_detail.columns:
        if 'CO2' in c:
            non_null = co2_detail[c].dropna()
            if len(non_null) > 0:
                active_co2.append(c)
                print(f'  {c}: avg={non_null.mean():.0f} max={non_null.max():.0f} min={non_null.min():.0f}')
    
    # Alarm thresholds
    alarm_df = pd.read_excel(env_file, sheet_name='告警阈值', engine='openpyxl')
    print(f'告警阈值: 温度低限={alarm_df["温度低限阈值"].iloc[0]} 温度高限={alarm_df["温度高限阈值"].iloc[0]}')
    print(f'         湿度高限={alarm_df["湿度高限阈值"].iloc[0]} 氨气高限={alarm_df["氨气高限阈值"].iloc[0]}')
    print(f'         CO2高限={alarm_df["二氧化碳高限阈值"].iloc[0]}')
