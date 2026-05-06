#!/usr/bin/env python
# coding: utf-8

# In[1]:


import pandas as pd
import numpy as np
import re
import json
import datetime
import os
from google.cloud import bigquery as bq

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adaccountuser import AdAccountUser
from facebook_business.adobjects.adsinsights import AdsInsights
from facebook_business.adobjects.campaign import Campaign
import requests

import warnings
import meta_token as token
warnings.filterwarnings('ignore')


# In[3]:


my_app_id = token.my_app_id
my_app_secret = token.my_app_secret
my_access_token = token.my_access_token


# In[4]:


FacebookAdsApi.init(my_app_id, my_app_secret, my_access_token)


# ## 連線至 Bigquery

# In[5]:


# 建立 python 與 bigquery 連線
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
client = bq.Client()
print(client)


# In[6]:


# 讀取 account table
project_name_account = 'eco-carver-356809'
dataset_name_account = 'ref_tables'
table_name_account = 'facebook_account'

# Select table in BQ
sql = """
    select *
    from `{}.{}.{}`
    """.format(project_name_account,dataset_name_account,table_name_account)

# run query
query_job = client.query(sql, location="US")

# Store query result to df
account_df = query_job.to_dataframe()


# In[7]:


account_df


# In[8]:


# account list
ad_accounts = []

for i in range(0,len(account_df)):
    ad_accounts.append(AdAccount(account_df.iloc[i,1]))


# ## AdAccount.get_ads (creative_id)
# https://developers.facebook.com/docs/marketing-api/reference/adgroup

# In[9]:


def get_creative(since_date, until_date, ad_accounts):
    
    ads_fields = [
        'account_id',
        'campaign_id',
        'adset_id',
        'id',          # The ID of this ad.
        'name',        # Name of the ad.
        'creative'
        ]

    ads_params = {        
        'time_range': {'since':since_date, 'until':until_date},
        'limit': 100000
        }

    df_creative = pd.DataFrame(columns=['account_id', 'ad_id', 'ad_name', 'creative_id'])

    for ad_account in ad_accounts:
        try:
            get_ads = ad_account.get_ads(fields=ads_fields, params=ads_params)
            for i in range(0, len(get_ads)):
                account_id = get_ads[i]['account_id']
                ad_id = get_ads[i]['id']
                ad_name = get_ads[i]['name']
                creative_id = get_ads[i]['creative']['id']
                new_row = pd.DataFrame([[account_id, ad_id, ad_name, creative_id]], columns=['account_id', 'ad_id', 'ad_name', 'creative_id'])
                df_creative = pd.concat([df_creative, new_row], ignore_index = True)
        except:
            print('Error ' + str(ad_account))
    return df_creative


# ## AdAccount.get_ad_images (permalink_url)
# https://developers.facebook.com/docs/marketing-api/reference/ad-image

# In[10]:


def get_ad_images(ad_accounts):
    
    image_fields = [
        'account_id',
        'creatives',   # creative IDs
        'id',          # The ID of the image.
        'hash',
        'name',
        'permalink_url',  # A permanent URL of the image to use in story creatives.
        'url',            # A temporary URL which the image can be retrieved at. Do not use this URL in ad creative creation.
        'url_128']

    df_image = pd.DataFrame()

    # 抓取各account資料
    for ad_account in ad_accounts:
        try:
            get_image = ad_account.get_ad_images(fields=image_fields)
            df = pd.DataFrame(get_image)
            df_image = pd.concat([df_image, df], axis=0, ignore_index=True)
        except:
            print('Error ' + str(ad_account))

    if 'creatives' not in df_image.columns:
        return pd.DataFrame(columns=image_fields).rename(columns={'creatives': 'creative_id'})

    # 把 creatives 展開
    df_image = df_image.explode('creatives')
    df_image.reset_index(drop=True, inplace=True)

    # 調整欄位順序
    df_image = df_image.reindex(columns=image_fields)
    df_image.rename(columns={'creatives': 'creative_id'}, inplace=True)
    
    return df_image


# ## AdAccount.get_ad_creatives (thumbnail_url)
# https://developers.facebook.com/docs/marketing-api/reference/ad-creative#Reading

# In[11]:


def get_ad_creatives(ad_accounts):
    
    fields = [
        'account_id',
        'id',          # creative_id
        'name',        # 素材名稱
        'title',       # 廣告標題
        'image_url',
        'thumbnail_url']

    params = {
        'thumbnail_width': 900,
        'thumbnail_height': 900,
    }

    df_creative = pd.DataFrame()

    for ad_account in ad_accounts:
        try:
            get_creative = list(
                ad_account.get_ad_creatives(fields=fields, params=params))
            df = pd.DataFrame(get_creative)
            df_creative = pd.concat([df_creative, df], axis=0, ignore_index=True)
        except:
            print('Error ' + str(ad_account))
    # 調整欄位順序
    df_creative = df_creative.reindex(columns=fields)
    df_creative.rename(columns={'id': 'creative_id'}, inplace=True)

    return df_creative


# In[12]:


# until_date (today)
utc = datetime.datetime.utcnow()
tw_today = utc + datetime.timedelta(hours=8)
tw_today = tw_today.strftime('%Y-%m-%d')

creative_id = get_creative('2022-07-14', tw_today, ad_accounts)
creative_id.head(2)


# In[13]:


permalink_url = get_ad_images(ad_accounts)
permalink_url.dropna(subset=['creative_id'], inplace=True)   # 刪掉 creative_id 為空值的row
permalink_url = permalink_url[['account_id', 'creative_id', 'permalink_url', 'url']]

permalink_url.head(2)


# In[ ]:


thumbnail_url = get_ad_creatives(ad_accounts)
thumbnail_url.dropna(subset=['creative_id'], inplace=True)   # 刪掉 creative_id 為空值的row
thumbnail_url = thumbnail_url[['account_id', 'creative_id', 'image_url', 'thumbnail_url']]

for frame in (creative_id, permalink_url, thumbnail_url):
    for key in ['account_id', 'creative_id']:
        if key in frame.columns:
            frame[key] = frame[key].astype(str)

thumbnail_url.head(2)


# In[ ]:


# merge df
df = creative_id.merge(permalink_url, on=['account_id', 'creative_id'], how='left')
df = df.merge(thumbnail_url, on=['account_id', 'creative_id'], how='left')


# In[ ]:


# 當 permalink_url 為空時，以 thumbnail_url 取代
df['permalink_url'].fillna(df['thumbnail_url'], inplace=True)


# In[ ]:


# 保留要的欄位
df = df[[
    'account_id','ad_id','ad_name', 'creative_id',
    'permalink_url', 'thumbnail_url']]

# 調整型態
df[['account_id']] = df[['account_id']].astype(str)
df[['ad_id']] = df[['ad_id']].astype(str)
df[['ad_name']] = df[['ad_name']].astype(str)
df[['creative_id']] = df[['creative_id']].astype(str)
df[['permalink_url']] = df[['permalink_url']].astype(str)
df[['thumbnail_url']] = df[['thumbnail_url']].astype(str)


# In[ ]:


df.drop_duplicates(subset=['account_id', 'ad_id', 'creative_id'], keep='last', inplace=True)
df.tail(2)


# # 上傳 df 到 bigquery

# In[ ]:


# 設定 Table 名稱
project_name = 'eco-carver-356809'
dataset_name = 'api_ads_tables'
table_name = 'facebook_image'
table_id = project_name + '.' + dataset_name + '.' + table_name


# In[ ]:


# # 設定 Table 資料結構

# schema = [
#     bq.SchemaField("account_id", "STRING"),
#     bq.SchemaField("ad_id", "STRING"),
#     bq.SchemaField("ad_name", "STRING"),
#     bq.SchemaField("creative_id", "STRING"),
#     bq.SchemaField("permalink_url", "STRING"),
#     bq.SchemaField("thumbnail_url", "STRING")
# ]

# # 建立 Table
# table = bq.Table(table_id, schema=schema)
# table = client.create_table(table)

# print("Created table {}".format(table_name))


# In[ ]:


# 清空table

sql = """
    DELETE 
        FROM `eco-carver-356809.api_ads_tables.facebook_image`
    WHERE permalink_url like '%https%' or permalink_url = 'nan'
"""

# run query
query_job = client.query(sql, location="US") 
query_job.result() 

print("Clear table in {}".format(table_name))


# In[ ]:


# 將 df 上傳到 Bigquery table

dataset_ref = client.dataset(dataset_name)
table_ref = dataset_ref.table(table_name)

job = client.load_table_from_dataframe(df, table_ref, location="US")
job.result()  # Waits for table load to complete.
assert job.state == "DONE"

print("Upload df to {}".format(table_name))

