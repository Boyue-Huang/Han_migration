#!/usr/bin/env python
# coding: utf-8

# In[1]:


#import packages
import base64
import requests
import pandas as pd
from datetime import datetime, timedelta
from google.cloud import bigquery as bq
import os
import db_dtypes
import urllib.request
import json
from pandas import json_normalize


# In[2]:


def get_access_token(api_token):
    # Encode api_token in base64
    encoded_api_token = base64.b64encode(api_token.encode('utf-8')).decode('utf-8')
    
    # Define the API URL and headers
    url = "https://s2s.popin.cc/data/v1/authentication"
    headers = {
        'Authorization': f'Basic {encoded_api_token}',
        'Content-Type': 'application/x-www-form-urlencoded;charset=utf-8'
    }
    
    # Make the POST request to get the access token
    response = requests.post(url, headers=headers)
    
    # Check for successful response
    if response.status_code == 200:
        response_data = response.json()
        access_token = response_data.get("access_token")
        expires_in = response_data.get("expires_in")
        return access_token
    else:
        print(f"Error {response.status_code}: {response.text}")
        return None

# Check api_token
##access_token = get_access_token(api_token)


# In[3]:


##3.1 CAMPAIGN LIST

# Campaign List API URL
def get_campaign_info(access_token):
    url = "https://s2s.popin.cc/discovery/api/v2/campaign/lists"  # Campaign List API URL
    headers = {"Authorization": f"Bearer {access_token}"}
    params = {"country_id": "tw"}  # Adjust as necessary

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print(f"Error: Unable to fetch data, status code {response.status_code}")
        return None

    data = response.json()
    campaign_list = data.get("data", [])

    if not campaign_list:
        print("No campaigns found.")
        return None

    df = pd.DataFrame(campaign_list)
    if {'mongo_id', 'name', 'account'}.issubset(df.columns):
        campaign = df.rename(columns={'mongo_id': 'campaign_id', 'name': 'campaign_name'})
        campaign = campaign[['campaign_id', 'campaign_name', 'account']]
        campaign_ids = campaign['campaign_id'].tolist()
        return campaign, campaign_ids
    else:
        print("Required columns are missing in the response data.")
        return None


# In[4]:


# API Base URL
def get_ad_list(access_token, campaign_ids):
    BASE_URL = "https://s2s.popin.cc/discovery/api/v2"
    all_ads = []  # 用來存儲所有campaign的Ad數據

    for campaign_id in campaign_ids:
        print(f"Fetching Ad list for Campaign ID: {campaign_id}")
        url = f"{BASE_URL}/ad/{campaign_id}/lists"
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            ad_list = response.json()
            creative_list = ad_list.get("data", [])  # 提取data部分，如果沒有則為空列表

            if creative_list:
                df = pd.DataFrame(creative_list)
                all_ads.append(df)  # 將該Campaign的DataFrame添加到all_ads列表中
        else:
            print(f"Error fetching ad list for campaign {campaign_id}: {response.status_code}")

    # 如果all_ads中有數據，將所有DataFrame合併
    if all_ads:
        creative_table = pd.concat(all_ads, ignore_index=True)
        creative_table = creative_table[['mongo_id','campaign','title','image']]
        creative_table.rename(columns = {'mongo_id':'ad_id','campaign':'campaign_id'},inplace = True)        
        key = creative_table[['campaign_id','ad_id']]
        return creative_table, key
    else:
        print("No data to combine.")
        return None
            


# In[15]:


##3.3Ad Daily Report
# 計算日期範圍
def fetch_data(access_token, key):
    BASE_URL = "https://s2s.popin.cc/discovery/api/v2"
    all_data = []
    
    # 計算開始和結束日期
    end_date = datetime.now()-timedelta(days= 1)
    start_date = end_date - timedelta(days=10)
    start_date_str = start_date.strftime('%Y%m%d')
    end_date_str = end_date.strftime('%Y%m%d')

    for _, row in key.iterrows():
        campaign_id = row['campaign_id']
        ad_id = row['ad_id']

        print(f"Fetching data for Campaign ID: {campaign_id}, Ad ID: {ad_id}")
        url = f"{BASE_URL}/ad/{campaign_id}/{ad_id}/{start_date_str}/{end_date_str}/date_reporting"
        headers = {"Authorization": f"Bearer {access_token}"}

        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            try:
                data = response.json()  # 嘗試將響應轉換為 JSON

                # 確保返回的是字典
                if isinstance(data, dict) and "data" in data:
                    if not data["data"]:  # 如果是空字典，跳過
                        print(f"Empty data for Campaign ID: {campaign_id}, Ad ID: {ad_id}")
                        continue

                    if isinstance(data["data"], dict):
                        for date, metrics in data["data"].items():
                            metrics['campaign_id'] = campaign_id
                            metrics['ad_id'] = ad_id
                            all_data.append(metrics)
                    else:
                        print(f"Unexpected data format for Campaign ID: {campaign_id}, Ad ID: {ad_id}")
                        continue
                else:
                    print(f"No valid data for Campaign ID: {campaign_id}, Ad ID: {ad_id}")
                    continue
            except ValueError:
                print(f"Invalid JSON response for Campaign ID: {campaign_id}, Ad ID: {ad_id}")
                continue
        else:
            print(f"Error fetching data for Campaign ID: {campaign_id}, Status Code: {response.status_code}")
            continue

    # 如果所有數據都成功返回，將結果存儲為 DataFrame
    if all_data:
        Ad_Daily_table = pd.DataFrame(all_data)
        return Ad_Daily_table
    else:
        print("No data retrieved.")
        return None



# In[6]:


def final_merge(Ad_Daily_table,campaign,creative_table):
    final = Ad_Daily_table.merge(campaign, left_on = ['campaign_id'], right_on = ['campaign_id'], how = 'left')
    final1 = final.merge(creative_table, left_on = ['campaign_id','ad_id'], right_on = ['campaign_id','ad_id'], how = 'left')
    final1 = final1[['date','account', 'campaign_id','campaign_name','ad_id','imp', 'click', 'ctr', 'cpc', 'cpm', 'charge', 'cv', 'cvr',
       'mcv', 'pc_imp', 'pc_click', 'pc_ctr', 'pc_charge', 'pc_cv', 'pc_cvr',
       'pc_cpm', 'mobile_imp', 'mobile_click', 'mobile_ctr', 'mobile_charge',
       'mobile_cv', 'mobile_cvr', 'mobile_cpm','title', 'image']]
    final1['date'] = pd.to_datetime(final1['date']).dt.date
    final1['account'] = final1['account'].astype(str)
    final1['campaign_id'] = final1['campaign_id'].astype(str)
    final1['campaign_name'] = final1['campaign_name'].astype(str)
    final1['ad_id'] = final1['ad_id'].astype(str)
    final1['imp'] = final1['imp'].astype(int)
    final1['click'] = final1['click'].astype(int)
    final1['ctr'] = final1['ctr'].astype(float)
    final1['cpc'] = final1['cpc'].astype(int)
    final1['cpm'] = final1['cpm'].astype(float)
    final1['charge'] = final1['charge'].astype(int)
    final1['cv'] = final1['cv'].astype(int)
    final1['cvr'] = final1['cvr'].astype(float)
    final1['mcv'] = final1['mcv'].astype(int)
    final1['pc_imp'] = final1['pc_imp'].astype(int)
    final1['pc_click'] = final1['pc_click'].astype(int)
    final1['pc_ctr'] = final1['pc_ctr'].astype(float)
    final1['pc_charge'] = final1['pc_charge'].astype(int)
    final1['pc_cv'] = final1['pc_cv'].astype(int)
    final1['pc_cvr'] = final1['pc_cvr'].astype(float)
    final1['pc_cpm'] = final1['pc_cpm'].astype(float)
    final1['mobile_imp'] = final1['mobile_imp'].astype(int)
    final1['mobile_click'] = final1['mobile_click'].astype(int)
    final1['mobile_ctr'] = final1['mobile_ctr'].astype(float)
    final1['mobile_charge'] = final1['mobile_charge'].astype(int)
    final1['mobile_cv'] = final1['mobile_cv'].astype(int)
    final1['mobile_cvr'] = final1['mobile_cvr'].astype(float)
    final1['mobile_cpm'] = final1['mobile_cpm'].astype(float)
    final1['title'] = final1['title'].astype(str)
    final1['image'] = final1['image'].astype(str)
    return final1


# In[7]:


# 抓取token
# 建立 python 與 bigquery 連線
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
client = bq.Client()

project_name = 'eco-carver-356809'
dataset_name = 'ref_tables'
table_name = 'popin_account'

# Select table in BQ
sql = """
    select *
    from `{}.{}.{}`
    """.format(project_name,dataset_name,table_name)

# run query
query_job = client.query(sql, location="US")

# Store query result to df
token = query_job.to_dataframe()


# In[16]:


for _, row in token.iterrows():
    name = row['account_name']
    account_token = row['account_id']
    upload_project = row['upload_project']
    upload_dataset = row['upload_dataset']
    upload_table = row['upload_table']

    try:
        access_token = get_access_token(account_token)
        campaign, campaign_ids = get_campaign_info(access_token)
        creative_table, key = get_ad_list(access_token, campaign_ids)
        Ad_Daily_table = fetch_data(access_token, key)

        final1 = final_merge(Ad_Daily_table, campaign, creative_table)
        
        # BigQuery 客戶端初始化
        client = bq.Client(project=upload_project)
        table_id = f"{upload_project}.{upload_dataset}.{upload_table}"

        # 檢查表是否存在
        try:
            table = client.get_table(table_id)  # 如果表存在，返回 Table 對象
            print(f"Table {table_id} exists.")

            # 查詢現有資料中的 date, campaign_id, ad_id
            query = f"""
                SELECT date, campaign_id, ad_id
                FROM `{table_id}`
            """
            existing_data = client.query(query).to_dataframe()

            # 過濾 final1 中不存在於現有表的資料
            final1_filtered = final1[~final1.set_index(['date', 'campaign_id', 'ad_id']).index.isin(
                existing_data.set_index(['date', 'campaign_id', 'ad_id']).index
            )]

            if final1_filtered.empty:
                print(f"No new data to insert for account: {name}")
            else:
                # 插入新資料
                job = client.load_table_from_dataframe(final1_filtered, table_id)
                job.result()  # 等待上傳完成
                print(f"New data inserted successfully for account: {name}")
        except Exception as e:
            # 如果表不存在，直接創建並上傳資料
            print(f"Table {table_id} does not exist. Creating table and uploading data.")
            job = client.load_table_from_dataframe(final1, table_id)  # 假設 final1 是 Pandas DataFrame
            job.result()  # 等待上傳完成
            print(f"Table created and data uploaded successfully for account: {name}")

    except Exception as e:
        print(f"Error processing data for account: {name} - {e}")
        

