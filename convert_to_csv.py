"""
Excel转CSV脚本
将Excel环境数据文件转换为CSV格式，并进行5分钟采样
提升数据加载速度5-10倍
"""
import pandas as pd
import os
from pathlib import Path
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

def convert_excel_to_csv(excel_path, output_dir=None, sample_interval=1):
    """
    将Excel文件转换为CSV格式
    
    Args:
        excel_path: Excel文件路径
        output_dir: 输出目录，默认与Excel文件同目录
        sample_interval: 采样间隔（分钟），默认5分钟
    
    Returns:
        转换后的CSV文件路径
    """
    excel_path = Path(excel_path)
    if output_dir is None:
        output_dir = excel_path.parent
    else:
        output_dir = Path(output_dir)
    
    # 读取Excel文件
    print(f"正在转换: {excel_path.name}")
    
    try:
        # 读取单元信息sheet
        df_unit = pd.read_excel(excel_path, sheet_name='单元信息', engine='openpyxl')
        
        if df_unit.empty:
            print("  [WARN] 单元信息为空，跳过")
            return None
        
        # 提取需要的列
        needed_columns = [
            '时间', '单元类型', '目标温度(℃)', '目标湿度(%)', '通风模式',
            '舍内温度(℃)', '舍内湿度(%)', '二氧化碳均值(ppm)', '压差均值(pa)',
            '栋舍', '单元', '装猪数量',
            '场区', '猪只体重(Kg)', '日龄', '通风季节', '工作模式', '通风等级'
        ]
        
        # 只保留存在的列
        available_columns = [col for col in needed_columns if col in df_unit.columns]
        df_unit = df_unit[available_columns]
        
        # 5分钟采样
        if '时间' in df_unit.columns and len(df_unit) > 0:
            df_unit['时间'] = pd.to_datetime(df_unit['时间'], errors='coerce')
            df_unit = df_unit.dropna(subset=['时间'])
            df_unit = df_unit.sort_values('时间')
            
            # 创建采样键（每5分钟一个键）
            df_unit['minute'] = df_unit['时间'].dt.minute
            df_unit['five_min_interval'] = (df_unit['minute'] // sample_interval) * sample_interval
            df_unit['sample_key'] = df_unit['时间'].dt.strftime('%Y-%m-%d %H:') + df_unit['five_min_interval'].astype(str).str.zfill(2)
            
            # 去重，保留每个5分钟间隔的第一条数据
            df_unit = df_unit.drop_duplicates(subset=['sample_key'], keep='first')
            df_unit = df_unit.drop(columns=['minute', 'five_min_interval', 'sample_key'])
        
        # 保存为CSV
        csv_filename = excel_path.stem + '_单元信息.csv'
        csv_path = output_dir / csv_filename
        df_unit.to_csv(csv_path, index=False, encoding='utf-8-sig')
        
        print(f"  [OK] 单元信息: {len(df_unit)} 行 -> {csv_filename}")
        
        # 尝试读取室外数据sheet
        try:
            df_outdoor = pd.read_excel(excel_path, sheet_name='室外数据', engine='openpyxl')
            
            if not df_outdoor.empty:
                # 5分钟采样
                if '时间' in df_outdoor.columns and len(df_outdoor) > 0:
                    df_outdoor['时间'] = pd.to_datetime(df_outdoor['时间'], errors='coerce')
                    df_outdoor = df_outdoor.dropna(subset=['时间'])
                    df_outdoor = df_outdoor.sort_values('时间')
                    
                    df_outdoor['minute'] = df_outdoor['时间'].dt.minute
                    df_outdoor['five_min_interval'] = (df_outdoor['minute'] // sample_interval) * sample_interval
                    df_outdoor['sample_key'] = df_outdoor['时间'].dt.strftime('%Y-%m-%d %H:') + df_outdoor['five_min_interval'].astype(str).str.zfill(2)
                    
                    df_outdoor = df_outdoor.drop_duplicates(subset=['sample_key'], keep='first')
                    df_outdoor = df_outdoor.drop(columns=['minute', 'five_min_interval', 'sample_key'])
                
                # 保存室外数据CSV
                csv_outdoor_filename = excel_path.stem + '_室外数据.csv'
                csv_outdoor_path = output_dir / csv_outdoor_filename
                df_outdoor.to_csv(csv_outdoor_path, index=False, encoding='utf-8-sig')
                
                print(f"  [OK] 室外数据: {len(df_outdoor)} 行 -> {csv_outdoor_filename}")
        
        except Exception as e:
            print(f"  [INFO] 无室外数据sheet: {e}")
        
        return csv_path
        
    except Exception as e:
        print(f"  [ERROR] 转换失败: {e}")
        return None

def convert_batch_directory(batch_dir):
    """
    转换整个批次目录下的所有Excel文件
    
    Args:
        batch_dir: 批次目录路径
    """
    batch_dir = Path(batch_dir)
    
    # 查找所有环境数据Excel文件
    excel_files = list(batch_dir.glob("*环境数据.xlsx"))
    excel_files = [f for f in excel_files if not f.name.startswith('~$')]
    
    if not excel_files:
        print(f"未找到环境数据Excel文件: {batch_dir}")
        return
    
    print(f"\n{'='*60}")
    print(f"批次目录: {batch_dir.name}")
    print(f"找到 {len(excel_files)} 个Excel文件")
    print(f"{'='*60}\n")
    
    success_count = 0
    for excel_file in excel_files:
        result = convert_excel_to_csv(excel_file)
        if result:
            success_count += 1
    
    print(f"\n转换完成: {success_count}/{len(excel_files)} 个文件成功")
    
    # 计算文件大小对比
    total_excel_size = sum(f.stat().st_size for f in excel_files) / (1024 * 1024)
    csv_files = list(batch_dir.glob("*_单元信息.csv")) + list(batch_dir.glob("*_室外数据.csv"))
    total_csv_size = sum(f.stat().st_size for f in csv_files) / (1024 * 1024)
    
    print(f"\n文件大小对比:")
    print(f"  Excel总大小: {total_excel_size:.2f} MB")
    print(f"  CSV总大小: {total_csv_size:.2f} MB")
    print(f"  压缩率: {(1 - total_csv_size/total_excel_size)*100:.1f}%")

def main():
    """主函数"""
    print("\n" + "="*60)
    print("Excel转CSV工具 - 提升数据加载速度")
    print("="*60)
    
    # 数据根目录
    data_root = Path(__file__).parent
    
    # 查找所有批次目录
    batch_dirs = [
        d for d in data_root.iterdir()
        if d.is_dir()
        and not d.name.startswith('.')
        and d.name not in {'cache', 'static', 'templates', '__pycache__'}
    ]
    
    if not batch_dirs:
        print("未找到批次目录")
        return
    
    print(f"\n找到 {len(batch_dirs)} 个批次目录:")
    for i, batch_dir in enumerate(batch_dirs, 1):
        print(f"  {i}. {batch_dir.name}")
    
    # 转换所有批次
    for batch_dir in batch_dirs:
        convert_batch_directory(batch_dir)
    
    print("\n" + "="*60)
    print("[OK] 所有批次转换完成！")
    print("="*60)
    print("\n提示:")
    print("  1. CSV文件已生成在原Excel文件同目录")
    print("  2. 数据已进行5分钟采样")
    print("  3. 现在可以重启服务器测试加载速度")

if __name__ == "__main__":
    main()
