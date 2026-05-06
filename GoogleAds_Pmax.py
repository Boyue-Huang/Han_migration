#!/usr/bin/env python
# coding: utf-8

# In[ ]:





# In[2]:


#install packages
import argparse
import sys
from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
import os
import pandas as pd
import numpy as np
import re
import json
from enum import Enum
from datetime import datetime, timedelta
import time
import pygsheets
import logging
import requests
from google.cloud import logging as log
from google.cloud.logging.handlers import CloudLoggingHandler
from google.cloud import bigquery as bq
from google.cloud import bigquery
import time
import warnings
warnings.filterwarnings('ignore')

# 導入

import GoogleAds_Parm_query as qr
import GoogleAds_api_token_Han as token
import GoogleAds_Parm_mapping as mp


# In[3]:


utc = datetime.utcnow()
today_dt = utc + timedelta(hours=8)
start_date_dt = today_dt - timedelta(days=14)
yesterday_date_dt = today_dt - timedelta(days=1)
# 將日期格式轉換為字符串
start_date = start_date_dt.strftime('%Y-%m-%d')
end_date = today_dt.strftime('%Y-%m-%d')

# 從今天起算，過去7天
start_date_dt_7d = today_dt - timedelta(days=7)
start_date_7d = start_date_dt_7d.strftime('%Y-%m-%d')

# 從今天起算，過去14天
start_date_dt_14d = today_dt - timedelta(days=14)
start_date_14d = start_date_dt_14d.strftime('%Y-%m-%d')


# In[4]:


def access_response(customer_id, query_input, page_token=None):
    googleads_client = GoogleAdsClient.load_from_dict(credentials)
    ga_service = googleads_client.get_service("GoogleAdsService")

    request = googleads_client.get_type("SearchGoogleAdsRequest")
    request.customer_id = customer_id
    request.query = query_input

    
    # 检查 page_token 是否存在，如果存在则设置
    if page_token:
        request.page_token = page_token

    response = ga_service.search(request=request)
    
    return response


# In[5]:


def process_response_basic(basic):

    df_basic = pd.DataFrame([
        {
            'customer_id': result.customer.id,
            'customer_name': result.customer.descriptive_name,
            
            'campaign_id': result.campaign.id,
            'campaign_name': result.campaign.name,
            'campaign_type': mp.campaign_type_mapping.get(result.campaign.advertising_channel_type, 'Unknown'),
            
            # segments
            'ad_network_type': mp.ad_network_type_mapping.get(result.segments.ad_network_type, 'Unknown'),
            # 'click_type': mp.click_type_mapping.get(result.segments.click_type, 'Unknown'),
            'date': result.segments.date,
            
            'impressions': result.metrics.impressions,
            'clicks': result.metrics.clicks,
            'cost': result.metrics.cost_micros / 1000000,
            'conversions': result.metrics.conversions,
            'conversion_value': result.metrics.conversions_value
        }
        for result in basic.results
    ])
    
    return df_basic


# In[6]:


def process_df_basic(customer_id, start_date, end_date):

    # 創建空 df
    df_basic_all = pd.DataFrame()

    # 透過 "access_response"取得指定 query 的 json
    query_pmax_basic = qr.query_pmax_basic(start_date, end_date)
    basic = access_response(customer_id, query_pmax_basic)

    # 透過 “process_response_OOO" 處理 json 轉換為 df
    df_basic = process_response_basic(basic)

    # 把 df 合併到特定 df_all
    df_basic_all = pd.concat([df_basic_all, df_basic], ignore_index=True)
    
    # 如果 basic json 有 next_page_token 就會繼續跑
    while basic.next_page_token:

        # 繼續透過 "access_response"取得指定 query 的 json
        basic = access_response(customer_id, query_pmax_basic, page_token=basic.next_page_token)

        df_basic = process_response_basic(basic)
        df_basic_all = pd.concat([df_basic_all, df_basic], ignore_index=True)

    return df_basic_all


# In[7]:


def get_df_basic(df_basic):

    # 先 Group By 起來，計算 metrics 量值
    df_basic = df_basic.groupby([
        'customer_id', 'customer_name', 'campaign_id', 'campaign_name', 'campaign_type',
        'ad_network_type', 'date'
    ]).agg({
        'impressions': 'sum',
        'clicks': 'sum',
        'cost': 'sum',
        'conversions': 'sum',
        'conversion_value': 'sum'
    }).reset_index()
    
    # 添加额外的列
    df_basic['media'] = 'Google Ads'
    df_basic['media_type'] = 'Performance Max'
    df_basic['media'] = 'Google'
    df_basic['channel_type'] = 'Google PMAX'
    df_basic['ad_id'] = '-'
    df_basic['ad_name'] = 'RESPONSIVE_SEARCH_AD'
    df_basic['image_url'] = 'https://topsceneassets.com/RESPONSIVE_SEARCH_AD.jpg'
    df_basic['preview_image_url'] = 'https://topsceneassets.com/RESPONSIVE_SEARCH_AD.jpg'
    
    # 轉換型態 (確保id欄位為str；所有數值都為 float)
    dtype_dict = {
        'media': str,
        'media_type': str,
        'channel_type' : str,
        'customer_id': str, 
        'customer_name': str, 
        'campaign_id': str, 
        'campaign_name': str, 
        'campaign_type': str,
        
        'ad_network_type': str,
        'ad_id': str,
        'ad_name': str,
        'image_url': str,
        'preview_image_url': str,
        'impressions': int,
        'clicks': int,
        'cost': float,
        'conversions': float,
        'conversion_value': float
    }
    
    df_basic = df_basic.astype(dtype_dict)
    
    # 調整日期欄位(重要!)
    df_basic['date'] = pd.to_datetime(df_basic['date']).dt.date

    # 保留需要的欄位 & 重新排順序
    new_columns = ['media', 'media_type', 'channel_type', 
                   'customer_id', 'customer_name', 'campaign_id', 'campaign_name', 'campaign_type', 
                   'ad_network_type', 'ad_id', 'ad_name', 'image_url', 'preview_image_url','date',
                   'impressions', 'clicks', 'cost', 'conversions', 'conversion_value']
    
    df_basic = df_basic[new_columns]

    return df_basic


# ### Pmax asset (each campaign has many assets)


# In[8]:


def get_df_asset(customer_id):

    # 創建空 df
    df_asset = pd.DataFrame()
    
    query_asset = """
            SELECT
                customer.id,
                customer.descriptive_name,
                campaign.id, 
                campaign.name, 
                campaign.advertising_channel_type,

                asset_group_asset.status,
                asset_group.status,
                
                asset.id, 
                asset.name,
                asset.image_asset.full_size.url,
                asset.youtube_video_asset.youtube_video_title, 
                asset.youtube_video_asset.youtube_video_id
            FROM asset_group_asset
            WHERE
                campaign.advertising_channel_type = 'PERFORMANCE_MAX'
        """
    
    asset = access_response(customer_id, query_asset)

    # 有些 Account 沒有設定 asset，則返回空的 df_asset
    if asset.results:
        
        df_asset = pd.DataFrame([
            {
                'customer_id': result.customer.id,
                'customer_name': result.customer.descriptive_name,
                'campaign_id': result.campaign.id,
                'campaign_name': result.campaign.name,
                'campaign_type': mp.campaign_type_mapping.get(result.campaign.advertising_channel_type, 'Unknown'),

                'asset_group_status': mp.asset_status.get(result.asset_group.status, 'Unknown'),
                'asset_status': mp.asset_status.get(result.asset_group_asset.status, 'Unknown'),
                
                'asset_id': result.asset.id,
                'asset_image_name': result.asset.name if result.asset.name else 'None',
                'asset_image_url': result.asset.image_asset.full_size.url if result.asset.image_asset.full_size.url else 'None',
                
                'asset_youtube_title': result.asset.youtube_video_asset.youtube_video_title if result.asset.youtube_video_asset.youtube_video_title else 'None',
                'asset_youtube_id': result.asset.youtube_video_asset.youtube_video_id if result.asset.youtube_video_asset.youtube_video_id else 'None',
                'asset_youtube_url': 'https://www.youtube.com/watch?v=' + result.asset.youtube_video_asset.youtube_video_id if result.asset.youtube_video_asset.youtube_video_id else 'None',
                'asset_youtube_screenshot': 'https://i.ytimg.com/vi/' + result.asset.youtube_video_asset.youtube_video_id + '/hqdefault.jpg' if result.asset.youtube_video_asset.youtube_video_id else 'None'
            }
            for result in asset.results
        ])
        
        # 轉換型態 (確保id欄位為str)
        df_asset['customer_id'] = df_asset['customer_id'].astype(str)
        df_asset['campaign_id'] = df_asset['campaign_id'].astype(str)
        df_asset['asset_id'] = df_asset['asset_id'].astype(str)
        df_asset['asset_youtube_id'] = df_asset['asset_youtube_id'].astype(str)
    
        df_asset['media'] = 'Google Ads'
        df_asset['media_type'] = 'Performance Max'
    
    return df_asset


# 
# 
# #google sheet enviornment
# gc = pygsheets.authorize(service_file='eco-carver-356809-a5ccbfde00b9.json')
# sht = gc.open_by_url('https://docs.google.com/spreadsheets/d/1oHP0Ec8LWjsFTLCaNEEh70Ks9YlraaVCjGfsuVXeWCQ/edit?usp=sharing')
# wks2 = sht.worksheet_by_title("漢瑞埬(勿動)")
# wks2.clear("A:X")

# In[9]:


# 連線到 G-sheet 讀取帳戶資訊
# 建立 python 與 bigquery 連線
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = 'eco-carver-356809-38c8914cd90f.json'
client = bq.Client()

project_name = 'eco-carver-356809'
dataset_name = 'ref_tables'
table_name = 'googleAds_account'

# Select table in BQ
sql = """
    select *
    from `{}.{}.{}`
    """.format(project_name,dataset_name,table_name)

# run query
query_job = client.query(sql, location="US")

# Store query result to df
accountlist  = query_job.to_dataframe()


# In[10]:


def upload_dataframe_to_bigquery(df, project_name, dataset_name, table_name):
    """
    Uploads a DataFrame to Google BigQuery and overwrites the existing table.

    Args:
        df (pd.DataFrame): The dataframe to upload.
        project_name (str): Google Cloud project ID.
        dataset_name (str): BigQuery dataset ID.
        table_name (str): BigQuery table name.
    """
    # Set up authentication (if needed)
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'eco-carver-356809-38c8914cd90f.json'
    
    client = bigquery.Client()

    table_ref = f"{project_name}.{dataset_name}.{table_name}"

    # 確保所有欄位都轉換為字串
    df = df.astype(str)

    # Configure the job to overwrite the table
    job_config = bigquery.LoadJobConfig(
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE  # Overwrite existing table
    )

    # Upload DataFrame
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()  # Wait for the job to complete

    print(f"Table {table_name} has been successfully replaced in {dataset_name} dataset.")


# In[11]:


accountlist[['customer_id']] = accountlist[['customer_id']].astype(str)
accountlist.reset_index(drop=True, inplace=True)


# In[12]:


# 初始化 logging
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = 'eco-carver-356809-38c8914cd90f.json'
client_log = log.Client()
handler = CloudLoggingHandler(client_log)

# 設定 logging (將 logging 記錄到 GCP Logging)
logging.basicConfig(level=logging.INFO)
logging.getLogger().setLevel(logging.INFO)
logging.getLogger().addHandler(handler)


# In[13]:


# 设置 googleads 库的日志级别为 WARNING
logging.getLogger('google.ads.googleads').setLevel(logging.WARNING)


# In[14]:


def create_dataset_if_not_exists(project_name, dataset_name):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'eco-carver-356809-38c8914cd90f.json'
    client = bq.Client()
    
    dataset_ref = f'{project_name}.{dataset_name}'

    try:
        client.get_dataset(dataset_ref)
        # print(f'Dataset: {dataset_name} already exists.')
        return True
        
    except Exception as e:
        if 'Not found' in str(e):
            dataset = bq.Dataset(dataset_ref)
            dataset.location = "US"
            client.create_dataset(dataset)
            print(f'Dataset {dataset_name} has been created.')
            return True
        else:
            print(f'An unexpected error occurred on dataset building.')
            print(f'Error: {e}')
            return False


# In[15]:


def upload_bigquery(df, project_name, dataset_name, table_name, start_date=None, end_date=None):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'eco-carver-356809-38c8914cd90f.json'
    client = bq.Client()

    # 檢查 table 是否存在，不存在的話創建它
    table_ref = f'{project_name}.{dataset_name}.{table_name}'

    try:
        client.get_table(table_ref)
        table_exists = True
    except:
        table_exists = False

    # 如果表存在，且有日期參數，則刪除 df 跑的日期的資料，再放上新資料
    if table_exists and start_date is not None:

        sql = """
            DELETE 
                FROM `{}`
            where 
                date >= DATE('{}')
                and date <= DATE('{}')
        """.format(table_ref, start_date, end_date)
    
        query_job = client.query(sql, location="US")
        query_job.result()
        
        query_job = client.load_table_from_dataframe(df, table_ref, location="US")
        query_job.result()
        print('Delete specific date and fill up.')
    
    # 如果表存在，但無日期參數，則直接覆蓋資料
    elif table_exists and start_date is None:

        job_config = bq.LoadJobConfig()
        job_config.write_disposition = bq.WriteDisposition.WRITE_TRUNCATE

        query_job = client.load_table_from_dataframe(df, table_ref, location="US", job_config=job_config)
        query_job.result()
        print('Write truncate.')

    # 如果表不存在，創立一個新的
    else:
        job_config = bq.LoadJobConfig()
        job_config.create_disposition = bq.CreateDisposition.CREATE_IF_NEEDED

        query_job = client.load_table_from_dataframe(df, table_ref, location="US", job_config=job_config)
        query_job.result()
        print('Create new table.')


# In[16]:


def create_dataset_if_not_exists(project_name, dataset_name):
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'eco-carver-356809-38c8914cd90f.json'
    client = bq.Client()
    
    dataset_ref = f'{project_name}.{dataset_name}'

    try:
        client.get_dataset(dataset_ref)
        # print(f'Dataset: {dataset_name} already exists.')
        return True
        
    except Exception as e:
        if 'Not found' in str(e):
            dataset = bq.Dataset(dataset_ref)
            dataset.location = "US"
            client.create_dataset(dataset)
            print(f'Dataset {dataset_name} has been created.')
            return True
        else:
            print(f'An unexpected error occurred on dataset building.')
            print(f'Error: {e}')
            return False


# In[17]:


def create_basic_table_if_not_exists(project_name, dataset_name, table_name):
    client = bq.Client.from_service_account_json('eco-carver-356809-38c8914cd90f.json')
    table_ref = f'{project_name}.{dataset_name}.{table_name}'

    try:
        client.get_table(table_ref)
        print(f'Table {table_name} already exists.')
    except:
        schema = [
            bq.SchemaField("customer_id", "STRING"),
            bq.SchemaField("customer_name", "STRING"),
            bq.SchemaField("campaign_id", "STRING"),
            bq.SchemaField("campaign_name", "STRING"),
            bq.SchemaField("campaign_type", "STRING"),
            bq.SchemaField("ad_network_type", "STRING"),
            bq.SchemaField("channel_type", "STRING"),
            bq.SchemaField("ad_id","STRING"),
            bq.SchemaField("ad_name","STRING"),
            bq.SchemaField("image_url","STRING"),
            bq.SchemaField("preview_image_url","STRING"),
            bq.SchemaField("media", "STRING"),
            bq.SchemaField("media_type", "STRING"),
            bq.SchemaField("date", "Date"),
            bq.SchemaField("impressions", "INTEGER"),
            bq.SchemaField("clicks", "INTEGER"),
            bq.SchemaField("cost", "FLOAT64"),
            bq.SchemaField("conversions", "FLOAT64"),
            bq.SchemaField("conversion_value", "FLOAT64"),
        ]

        table = bigquery.Table(table_ref, schema=schema)
        client.create_table(table)
        print(f'Table {table_name} has been created.')



# In[18]:


def create_asset_table_if_not_exists(project_name, dataset_name, table_name):
    client = bq.Client.from_service_account_json('eco-carver-356809-38c8914cd90f.json')
    table_ref = f'{project_name}.{dataset_name}.{table_name}'

    try:
        client.get_table(table_ref)
        print(f'Table {table_name} already exists.')
    except:
        schema = [
            bq.SchemaField("customer_id", "STRING"),
            bq.SchemaField("customer_name", "STRING"),
            bq.SchemaField("campaign_id", "STRING"),
            bq.SchemaField("campaign_name", "STRING"),
            bq.SchemaField("campaign_type", "STRING"),
            bq.SchemaField("asset_group_status","STRING"),
            bq.SchemaField("asset_status","STRING"),
            bq.SchemaField("asset_id","STRING"),
            bq.SchemaField("asset_image_name","STRING"),
            bq.SchemaField("assset_image_url", "STRING"),
            bq.SchemaField("asset_youtube_title", "STRING"),
            bq.SchemaField("asset_youtube_id", "STRING"),
            bq.SchemaField("asset_youtube_url", "FLOAT64"),
            bq.SchemaField("asset_youtube_screenshot", "FLOAT64"),
            bq.SchemaField("media", "FLOAT64"),
            bq.SchemaField("media_type", "FLOAT64"),
        ]

        table = bigquery.Table(table_ref, schema=schema)
        client.create_table(table)
        print(f'Table {table_name} has been created.')


# In[19]:


def upload_bigquery(df, project_name, dataset_name, table_name, start_date=None, end_date=None):
    # Set Google credentials
    os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'eco-carver-356809-38c8914cd90f.json'
    client = bq.Client()

    table_ref = f'{project_name}.{dataset_name}.{table_name}'

    # Ensure the 'date' column is properly formatted
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date'], errors='coerce')  # Coerce invalid dates to NaT
        df = df.dropna(subset=['date'])  # Drop rows where 'date' is NaT (if needed)
    
    # Check if table exists
    try:
        client.get_table(table_ref)  # Try to retrieve the table
        table_exists = True
    except:
        table_exists = False

    # If the table exists and date range is provided, delete existing data and upload new data
    if table_exists and start_date is not None:
        # Ensure start_date and end_date are in the correct format
        start_date = pd.to_datetime(start_date).date() if isinstance(start_date, str) else start_date
        end_date = pd.to_datetime(end_date).date() if isinstance(end_date, str) else end_date

        sql = f"""
            DELETE FROM `{table_ref}`
            WHERE date >= DATE('{start_date}')
            AND date <= DATE('{end_date}')
        """

        # Execute the delete query
        query_job = client.query(sql, location="US")
        query_job.result()

        # Upload new data
        job_config = bq.LoadJobConfig()
        job_config.write_disposition = bq.WriteDisposition.WRITE_APPEND  # Append data
        query_job = client.load_table_from_dataframe(df, table_ref, location="US", job_config=job_config)
        query_job.result()
        print('Deleted specific date range and uploaded new data.')

    # If the table exists and no date range is provided, replace the data
    elif table_exists and start_date is None:
        job_config = bq.LoadJobConfig()
        job_config.write_disposition = bq.WriteDisposition.WRITE_TRUNCATE  # Replace existing data

        query_job = client.load_table_from_dataframe(df, table_ref, location="US", job_config=job_config)
        query_job.result()
        print('Table data has been replaced.')

    # If the table does not exist, create a new table and upload data
    else:
        job_config = bq.LoadJobConfig()
        job_config.create_disposition = bq.CreateDisposition.CREATE_IF_NEEDED  # Create table if it does not exist

        query_job = client.load_table_from_dataframe(df, table_ref, location="US", job_config=job_config)
        query_job.result()
        print('Created new table and uploaded data.')


# def concatenate_with_creative_table(df_basic, project_name, dataset_final_name, table_creative):
#     required_columns = {
#         'adgroup_id': 0,
#         'adgroup_name': '',
#         'video_thruplay': 0.0,
#         'view_view': 0.0,
#         'video_25': 0.0,
#         'video_50': 0.0,
#         'video_75': 0.0,
#         'video_100': 0.0
#     }
# 
#     df_to_concat = df_basic.copy()
# 
#     for column, default_value in required_columns.items():
#         df_to_concat[column] = default_value
#    
#     df_to_concat['adgroup_id'] = df_to_concat['adgroup_id'].fillna(0).astype(int).astype(str)
#     df_to_concat['adgroup_name'] = df_to_concat['adgroup_name'].astype(str)
#     
#     float_columns = ['video_thruplay', 'view_view', 'video_25', 'video_50', 'video_75', 'video_100']
#     df_to_concat[float_columns] = df_to_concat[float_columns].astype(float)
# 
#     # 確保 'date' 欄位為字串
#     if 'date' in df_to_concat.columns:
#         df_to_concat['date'] = pd.to_datetime(df_to_concat['date'], errors='coerce')
# 
#     client = bigquery.Client.from_service_account_json('eco-carver-356809-38c8914cd90f.json')
#     table_ref = client.dataset(dataset_final_name).table(table_creative)
# 
#     creative_table_df = client.list_rows(table_ref).to_dataframe()
# 
#     if creative_table_df is None or creative_table_df.empty:
#         creative_table_df = pd.DataFrame(columns=df_to_concat.columns)
# 
#     # 確保 creative_table_df 的 'date' 欄位為字串
#     if 'date' in creative_table_df.columns:
#         creative_table_df['date'] = pd.to_datetime(creative_table_df['date'], errors='coerce')
# 
#     combined_df = pd.concat([creative_table_df, df_to_concat], ignore_index=True)
#     combined_df.drop(columns=['media_type','customer_name','campaign_type','ad_network_type'], inplace=True)
#     combined_df = combined_df.drop_duplicates(
#     subset=['channel_type', 'date', 'campaign_id', 'adgroup_id', 'ad_id'],
#     keep='last'
#     )
# 
#     upload_bigquery(combined_df, project_name, dataset_final_name, table_creative)
#     print(f"Successfully concatenated, deduplicated, and updated {table_creative}.")
# 

# def concatenate_with_creative_table(df_basic, project_name, dataset_name, table_creative_final):
#     client = bigquery.Client()
# 
#     # 確保 df_basic 不是空的
#     if df_basic.empty:
#         print(f'No data in df_basic, skipping concatenation.')
#         return
#     df_basic.drop(columns=['media_type','customer_name','campaign_type','ad_network_type'], inplace=True)
#     # 先刪除 `pmax` 相關的資料
#     delete_query = f"""
#     DELETE FROM `{project_name}.{dataset_name}.{table_creative_final}`
#     WHERE channel_type = 'Google PMAX'
#     """
#     try:
#         client.query(delete_query).result()
#         print(f'Successfully deleted existing pmax data from {table_creative_final}')
#     except Exception as e:
#         print(f'Error deleting pmax data: {e}')
#         return
# 
#     # 取得 `creative table` 目前的資料
#     query = f"SELECT * FROM `{project_name}.{dataset_name}.{table_creative_final}`"
#     try:
#         creative_table = client.query(query).to_dataframe()
#     except Exception as e:
#         print(f'Error fetching creative table: {e}')
#         creative_table = pd.DataFrame()
# 
#     # 合併資料
#     df_combined = pd.concat([creative_table, df_basic], ignore_index=True)
# 
#     # 上傳合併後的資料到 BigQuery
#     upload_bigquery(df_combined, project_name, dataset_name, table_creative_final)
# 
#     print(f'Successfully updated {table_creative_final} with new data.')


# In[20]:


accountlist


# In[21]:


def concatenate_with_creative_table(project_name, dataset_name, dataset_final_name, table_pmax_basic, table_creative_final):
    client = bigquery.Client()

    # 從 BigQuery 讀取 `table_pmax_basic`
    query_pmax = f"SELECT * FROM `{project_name}.{dataset_name}.{table_pmax_basic}`"
    try:
        df_basic = client.query(query_pmax).to_dataframe()
        if df_basic.empty:
            print(f'No data in {table_pmax_basic}, skipping concatenation.')
            return
    except Exception as e:
        print(f'Error fetching table_pmax_basic: {e}')
        return

    # 刪除 `pmax` 相關資料
    delete_query = f"""
    DELETE FROM `{project_name}.{dataset_final_name}.{table_creative_final}`
    WHERE channel_type = 'Google PMAX'
    """
    try:
        client.query(delete_query).result()
        print(f'Successfully deleted existing pmax data from {table_creative_final}')
    except Exception as e:
        print(f'Error deleting pmax data: {e}')
        return

    # 取得 `creative table` 目前的資料
    query_creative = f"SELECT * FROM `{project_name}.{dataset_final_name}.{table_creative_final}`"
    try:
        creative_table = client.query(query_creative).to_dataframe()
    except Exception as e:
        print(f'Error fetching creative table: {e}')
        creative_table = pd.DataFrame()

    if creative_table.empty and df_basic.empty:
        print(f'No data in both {table_pmax_basic} and {table_creative_final}, skipping concatenation.')
        return

    # 必要的欄位及預設值
    required_columns = {
        'adgroup_id': 0,
        'adgroup_name': '',
        'video_thruplay': 0.0,
        'view_view': 0.0,
        'video_25': 0.0,
        'video_50': 0.0,
        'video_75': 0.0,
        'video_100': 0.0
    }

    # 複製 df_basic
    df_to_concat = df_basic.copy()

    # 確保 df_basic 中有所有必要欄位，缺少的補充
    for column, default_value in required_columns.items():
        if column not in df_to_concat.columns:
            df_to_concat[column] = default_value

    # 填補和轉換欄位
    df_to_concat['adgroup_id'] = df_to_concat['adgroup_id'].fillna(0).astype(int).astype(str)
    df_to_concat['adgroup_name'] = df_to_concat['adgroup_name'].astype(str)
    
    float_columns = ['video_thruplay', 'view_view', 'video_25', 'video_50', 'video_75', 'video_100']
    df_to_concat[float_columns] = df_to_concat[float_columns].astype(float)

    # 確保 'date' 欄位為字串
    if 'date' in df_to_concat.columns:
        df_to_concat['date'] = pd.to_datetime(df_to_concat['date'], errors='coerce')
        df_to_concat['date'] = df_to_concat['date'].dt.tz_localize(None)  # 去除時區
        df_to_concat['date'] = df_to_concat['date'].astype(str)  # 轉換為字串格式

    # 確保兩個 DataFrame 的日期欄位都轉換為 tz-naive 格式
    def convert_to_tz_naive(df):
        for column in df.select_dtypes(include=['datetime', 'object']):
            if pd.api.types.is_datetime64_any_dtype(df[column]):
                df[column] = df[column].apply(lambda x: x.replace(tzinfo=None) if pd.notnull(x) else x)
        return df

    # 轉換 `df_basic` 和 `creative_table` 兩個 DataFrame 的日期欄位為 tz-naive
    df_to_concat = convert_to_tz_naive(df_to_concat)
    creative_table = convert_to_tz_naive(creative_table)

    # 如果 creative_table 中的 `date` 欄位是 tz-aware，則轉換為 tz-naive
    if 'date' in creative_table.columns and creative_table['date'].dtype == 'datetime64[ns, UTC]':
        creative_table['date'] = creative_table['date'].dt.tz_localize(None)

    # 合併 `table_pmax_basic` 和 `creative_table`
    df_combined = pd.concat([creative_table, df_to_concat], ignore_index=True)

    # **刪除指定欄位**
    columns_to_drop = ['media_type', 'customer_name', 'campaign_type', 'ad_network_type']
    df_combined.drop(columns=[col for col in columns_to_drop if col in df_combined.columns], inplace=True)

    # 上傳合併後的資料到 `table_creative_final`
    try:
        upload_bigquery(df_combined, project_name, dataset_final_name, table_creative_final)
        print(f'Successfully updated {table_creative_final} with new data.')
    except Exception as e:
        print(f'Error uploading to BigQuery: {e}')
        return







# In[22]:


def run(accountlist, start_date, end_date):
    # Start the timer to measure the processing time
    start_time = time.time()
    client = bigquery.Client.from_service_account_json('eco-carver-356809-38c8914cd90f.json')

    messages = []
    info_messages = ['【Info】']
    error_messages = ['【Error】']

    messages.append(f'\n【Google Ads, Pmax】 \nRange: {start_date} to {end_date}\n')

    for i in range(len(accountlist)):
        customer_id = accountlist.iloc[i]['customer_id']
        customer_name = accountlist.iloc[i]['account_name']
        project_name = accountlist.iloc[i]['project']
        dataset_name = accountlist.iloc[i]['dataset_tmp']
        dataset_final_name = accountlist.iloc[i]['dataset']
        table_pmax_basic = accountlist.iloc[i]['googleAds_pmax_basic']
        table_pmax_asset = accountlist.iloc[i]['googleAds_pmax_asset']
        table_creative_final = accountlist.iloc[i]['table_creative']

        print(f'{customer_id},{customer_name},{project_name},{dataset_name},{customer_name}')
        current_time = datetime.now().strftime("%H:%M")

        try:
            dataset_exists = create_dataset_if_not_exists(project_name, dataset_name)

            if dataset_exists:
                # 先處理 Basic
                df_basic = process_df_basic(customer_id, start_date, end_date)

                if not df_basic.empty:
                    df_basic = get_df_basic(df_basic)
                    # 確保 date 欄位為字串，避免 datetime.date 轉換錯誤
                    if 'date' in df_basic.columns:
                        df_basic['date'] = df_basic['date'].astype(str)
                        
                    # Concatenate df_basic with creative_table if necessary
                    #concatenate_with_creative_table(df_basic, project_name, dataset_final_name, table_creative_final)

                # 再處理 Asset
                df_asset = get_df_asset(customer_id)

                # **確認是否有資料才創建表**
                if not df_basic.empty or not df_asset.empty:
                    if not df_basic.empty:
                        create_basic_table_if_not_exists(project_name, dataset_name, table_pmax_basic)
                        upload_bigquery(df_basic, project_name, dataset_name, table_pmax_basic, str(start_date), str(end_date))
                        info_messages.append(f'{customer_name}, {current_time} Success Update!')
                        print(f'{customer_name}, Success Update!')
                    else:
                        print(f'{customer_name}, No Data for Basic!')

                    if not df_asset.empty:
                        create_asset_table_if_not_exists(project_name, dataset_name, table_pmax_asset)
                        upload_bigquery(df_asset, project_name, dataset_name, table_pmax_asset)
                        info_messages.append(f'{customer_name}, {current_time} Success Update Asset!')
                        print(f'{customer_name}, Success Update Asset!')
                    else:
                        print(f'{customer_name}, No Data for Asset!')
                else:
                    print(f'{customer_name}, No Data for Both Basic and Asset!')

            else:
                error_messages.append(f'{customer_name}, No dataset created.')
                print(f'{customer_name}, No dataset created.')

        except Exception as e:
            error_messages.append(f'{customer_name}, {current_time}, Error: {e}')
            print(f'{customer_name}, Error: {e}')
                    
        finally:
            concatenate_with_creative_table(project_name, dataset_name,dataset_final_name, table_pmax_basic, table_creative_final)
            print('---')

    # 當沒有 messages 顯示 None
    if len(info_messages) == 1:
        info_messages.append('None')
    if len(error_messages) == 1:
        error_messages.append('None')

    # 發送通知到 Line
    message_str = '\n'.join(messages + info_messages + error_messages)


    # End the timer and calculate the total time spent
    end_time = time.time()
    total_time = end_time - start_time
    print(f'Total time taken for the run function: {total_time:.2f} seconds')


# In[23]:


try:
    credentials = token.credentials
    run(accountlist,  start_date, end_date)
except Exception as e:
    error_message = f'\n【Han, Google Ads, Pmax】 \n有Bug請檢查!! \nError: {e}'
    print(error_message)


# In[ ]:





