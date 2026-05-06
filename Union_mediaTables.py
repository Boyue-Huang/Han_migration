#!/usr/bin/env python
# coding: utf-8

# In[1]:


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
import datetime
import time
from google.cloud import bigquery as bq

import warnings
warnings.filterwarnings('ignore')

# 導入自己寫的函數
import GoogleAds_api_parm as p
import GoogleAds_api_token_Han as token


# ### 查看所有帳戶List

# In[2]:


# 建立 python 與 bigquery 連線
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
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
df_account = query_job.to_dataframe()


# In[3]:


df_account


# In[9]:


# # 建立 python 與 bigquery 連線
# os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
# client = bq.Client()

# # 列出資料集中的所有表格
# dataset_tmp = 'api_ads_tables'
# tables = client.list_tables(dataset_tmp)


# In[10]:


def union_all_media_table(account_name, project_name, dataset_name, table_creative):

    # 建立 python 與 bigquery 連線
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
    client = bq.Client()

    # 列出資料集中的所有表格
    dataset_tmp = 'api_ads_tables'
    tables = client.list_tables(dataset_tmp)

    sql_facebook = p.sql_facebook(account_name)
    sql_google = p.sql_google(account_name)
    sql_line = p.sql_line(account_name)
    sql_yahooDSP = p.sql_yahooDSP(account_name)
    sql_yahooNative = p.sql_yahooNative(account_name)

    sql_queries = []

    for table in tables:
        if 'facebook_report_' + account_name in table.table_id:
            sql_queries.append(sql_facebook)

        if 'googleAds_creative_' + account_name in table.table_id:
            sql_queries.append(sql_google)

        if 'line_report_' + account_name in table.table_id:
            sql_queries.append(sql_line)

        if 'yahooDsp_report_' + account_name in table.table_id:
            sql_queries.append(sql_yahooDSP)
            
        if 'yahooNative_report_' + account_name in table.table_id:
            sql_queries.append(sql_yahooNative)

    # 組合 SQL 字串
    union_query = " UNION ALL ".join(sql_queries)

    # 直接將 join 結果上傳到 bigquery，無須額外的 df 儲存
    table_ref = f"{project_name}.{dataset_name}.{table_creative}"

    job_config  = bq.QueryJobConfig()
    job_config.destination = table_ref
    job_config.write_disposition = bq.WriteDisposition.WRITE_TRUNCATE
    job_config.create_disposition = bq.CreateDisposition.CREATE_IF_NEEDED

    query_job = client.query(union_query, location="US", job_config=job_config)
    query_job.result()

    print("Update data to : {}".format(table_creative))


# In[11]:


for i in range(0, len(df_account)):
    
    name = df_account.iat[i, 0]            # 漢寶幸福站
    account_name = df_account.iat[i, 1]    # happiness
    
    project_name = df_account.iat[i, 3]    # eco-carver-356809
    dataset_name = df_account.iat[i, 6]    # finish_tables
    table_creative = df_account.iat[i, 7]  # Creative_漢寶幸福站_FINAL

    print(name + ' ' + account_name)
    
    try:
        union_all_media_table(account_name, project_name, dataset_name, table_creative)
        
    except:
        print('There is some error in :{}'.format(account_name))
        
    print()


# In[ ]:




