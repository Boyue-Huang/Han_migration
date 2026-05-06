import pandas as pd
import numpy as np
import re
import json
import os
from google.cloud import bigquery as bq

from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.adaccountuser import AdAccountUser
from facebook_business.adobjects.adsinsights import AdsInsights
from facebook_business.adobjects.campaign import Campaign
import meta_token as token
import warnings
warnings.filterwarnings('ignore')

# ===== 時區安全：UTC→台北 =====  # <<< CHANGED
from datetime import datetime, timedelta
try:
    from datetime import UTC
except ImportError:
    from datetime import timezone as _tz
    UTC = _tz.utc
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None
TZ_TAIPEI = ZoneInfo("Asia/Taipei") if ZoneInfo else None

def now_utc() -> datetime:          # <<< CHANGED
    return datetime.now(UTC)

def now_tw() -> datetime:           # <<< CHANGED
    return now_utc().astimezone(TZ_TAIPEI) if TZ_TAIPEI else (now_utc() + timedelta(hours=8))


# Han Account info
my_app_id = token.my_app_id
my_app_secret = token.my_app_secret
my_access_token = token.my_access_token

FacebookAdsApi.init(my_app_id, my_app_secret, my_access_token)

# 建立 python 與 bigquery 連線
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
client = bq.Client()

project_name = 'eco-carver-356809'
dataset_name = 'ref_tables'
table_name = 'facebook_account'

sql = f"""
    select *
    from `{project_name}.{dataset_name}.{table_name}`
"""
account_df = client.query(sql, location="US").to_dataframe()

def get_insights(since_date, until_date, ad_account):
    fields = [
        'date_start','date_stop',
        'account_id','account_name',
        'campaign_id','campaign_name',
        'adset_id','adset_name',
        'ad_id','ad_name',
        'objective',
        'impressions','clicks','spend','reach',
        'actions',
        'video_p25_watched_actions','video_p50_watched_actions',
        'video_p75_watched_actions','video_p100_watched_actions'
    ]

    params = {
        'time_range': {'since': since_date, 'until': until_date},
        'time_increment': 1,
        'breakdowns': [],
        'level': 'ad',
        'limit': 100000,
        'use_unified_attribution_setting': True
    }

    resp = ad_account.get_insights(fields=fields, params=params)
    df_insights = pd.DataFrame(resp)

    if df_insights.empty:
        # 保持欄序
        return pd.DataFrame(columns=fields)

    # ---- 展開 actions：改為 list 累積 → DataFrame（取 value） ----  # <<< CHANGED
    action_rows = []
    for obj in df_insights.get('actions', []):
        if obj in (None, [], {}, np.nan):
            action_rows.append({})
            continue
        # obj 是 list[{'action_type': 'link_click', 'value': '123'} ...]
        row_map = {}
        for item in obj:
            try:
                at = item.get('action_type')
                val = pd.to_numeric(item.get('value'), errors='coerce')
                if pd.notna(val):
                    row_map[at] = float(val)
            except Exception:
                continue
        action_rows.append(row_map)
    df_actions = pd.DataFrame(action_rows)

    # ---- 展開各段影片觀看：同樣用 list 累積 ----  # <<< CHANGED
    def video_process(col_name, out_col):
        rows = []
        for obj in df_insights.get(col_name, []):
            if obj in (None, [], {}, np.nan):
                rows.append({})
                continue
            vm = {}
            for item in obj:
                # 通常 action_type = 'video_view'
                at = item.get('action_type')
                val = pd.to_numeric(item.get('value'), errors='coerce')
                if at and pd.notna(val):
                    vm[at] = float(val)
            rows.append(vm)
        vdf = pd.DataFrame(rows)
        # 取 'video_view' 欄位，沒有就 0
        if 'video_view' in vdf.columns:
            vdf = vdf[['video_view']].rename(columns={'video_view': out_col})
        else:
            vdf = pd.DataFrame({out_col: [0.0]*len(vdf)})
        return vdf

    df_video25  = video_process('video_p25_watched_actions',  'video_25')
    df_video50  = video_process('video_p50_watched_actions',  'video_50')
    df_video75  = video_process('video_p75_watched_actions',  'video_75')
    df_video100 = video_process('video_p100_watched_actions', 'video_100')

    # 合併
    df_insights = pd.concat([df_insights.drop(columns=['actions',
                                                       'video_p25_watched_actions',
                                                       'video_p50_watched_actions',
                                                       'video_p75_watched_actions',
                                                       'video_p100_watched_actions'],
                                              errors='ignore'),
                             df_actions.reset_index(drop=True),
                             df_video25.reset_index(drop=True),
                             df_video50.reset_index(drop=True),
                             df_video75.reset_index(drop=True),
                             df_video100.reset_index(drop=True)], axis=1)

    # 保持主要欄位順序在前（其餘 actions 動態欄在後）
    df_insights = df_insights.reindex(columns=fields + [c for c in df_insights.columns if c not in fields], fill_value=np.nan)
    return df_insights


def get_table(ad_account):
    # 以台北當地時間計算區間（相同邏輯、寫法更新）  # <<< CHANGED
    tw_today = now_tw()

    last_30d = (tw_today - timedelta(days=30)).strftime('%Y-%m-%d')
    last_21d = (tw_today - timedelta(days=21)).strftime('%Y-%m-%d')
    last_20d = (tw_today - timedelta(days=20)).strftime('%Y-%m-%d')
    last_11d = (tw_today - timedelta(days=11)).strftime('%Y-%m-%d')
    last_10d = (tw_today - timedelta(days=10)).strftime('%Y-%m-%d')
    today    = tw_today.strftime('%Y-%m-%d')

    # 拆三段抓（保留你原本策略）
    n1 = get_insights(last_10d, today, ad_account)
    n2 = get_insights(last_20d, last_11d, ad_account)
    n3 = get_insights(last_30d, last_21d, ad_account)

    df = pd.concat([n1, n2, n3], axis=0, ignore_index=True)

    return df


def build_table(account_name):
    df = get_table(account_name)
    if df.empty:
        return df

    # 先創建所有需要的 column（保留原邏輯）
    column_list = [
        'media', 'channel_type',
        'account_id', 'account_name', 'objective', 'campaign_id', 'campaign_name', 'adset_name', 'adset_id',
        'ad_name', 'ad_id',
        'date_start', 'date_stop',
        'impressions', 'clicks', 'spend', 'purchase', 'purchase_value',
        'video_thruplay', 'view_view', 'video_25', 'video_50', 'video_75', 'video_100',
        'reach', 'post_reaction', 'post_engagement', 'page_engagement', 'link_click', 'landing_page_view'
    ]
    null_df = pd.DataFrame(columns=column_list)

    # 用 concat 取代 append（pandas 2 相容）  # <<< CHANGED
    df = pd.concat([null_df, df], ignore_index=True)

    # 新增必要欄位（保留你的寫法）
    df['media'] = 'Facebook'
    df['channel_type'] = 'Facebook'

    # 從 actions 展開的欄位可能是字串，統一先轉數字  # <<< CHANGED
    for col in ['purchase','post_reaction','post_engagement','page_engagement','link_click','landing_page_view','video_view']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 你的原本邏輯：purchase_value = purchase（保留；若要真實金額可另外加 action_values）  # <<< CHANGED
    df['purchase_value'] = df['purchase']

    # 補 video_thruplay/view_view
    if 'video_view' in df.columns:
        df['video_thruplay'] = df['video_view']
        df['view_view'] = df['video_view']

    # 保留要的欄位（維持原順序）
    df = df[[
        'media', 'channel_type',
        'account_id', 'account_name', 'objective', 'campaign_id', 'campaign_name',
        'adset_name', 'adset_id', 'ad_name', 'ad_id',
        'date_start', 'date_stop',
        'impressions', 'clicks', 'spend', 'purchase', 'purchase_value',
        'video_thruplay', 'view_view', 'video_25', 'video_50', 'video_75', 'video_100',
        'reach', 'post_reaction', 'post_engagement', 'page_engagement', 'link_click', 'landing_page_view'
    ]]

    # 調整型態（保留你的型別轉換）
    for c in ['media','channel_type','account_id','account_name','objective','campaign_id','campaign_name',
              'adset_name','adset_id','ad_name','ad_id']:
        df[c] = df[c].astype(str)

    df['date_start'] = pd.to_datetime(df['date_start'], errors='coerce').dt.date
    df['date_stop']  = pd.to_datetime(df['date_stop'],  errors='coerce').dt.date

    for c in ['impressions','clicks']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype('int64')

    for c in ['spend','purchase','purchase_value','video_thruplay','view_view','video_25','video_50','video_75','video_100',
              'reach','link_click','post_reaction','landing_page_view','page_engagement','post_engagement']:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0).astype('float64')


    return df


def upload_bigquery_table(project_name, dataset_name, table_name, account_name):
    df = build_table(account_name)
    if df.empty:
        print("no data update to table : {}".format(table_name))
        return

    # 建立連線
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
    client = bq.Client()

    table_ref = f"{project_name}.{dataset_name}.{table_name}"

    # 檢查表是否存在
    try:
        client.get_table(table_ref)
        table_exists = True
    except Exception:
        table_exists = False

    if table_exists:
        # 用台北日曆日刪近 30 天（含今天）  # <<< CHANGED
        sql = f"""
            DELETE FROM `{table_ref}`
            WHERE date_start BETWEEN DATE_SUB(CURRENT_DATE("Asia/Taipei"), INTERVAL 30 DAY)
                                 AND CURRENT_DATE("Asia/Taipei")
        """
        client.query(sql, location="US").result()

        client.load_table_from_dataframe(df, table_ref, location="US").result()
    else:
        job_config = bq.LoadJobConfig()
        job_config.create_disposition = bq.CreateDisposition.CREATE_IF_NEEDED
        client.load_table_from_dataframe(df, table_ref, job_config=job_config, location="US").result()

    print("update df to table : {}".format(table_name))


# ===== 執行 =====
for i in range(0, len(account_df)):
    try:
        upload_bigquery_table(account_df.iat[i, 2],
                              account_df.iat[i, 3],
                              account_df.iat[i, 4],
                              AdAccount(account_df.iat[i, 1]))
    except Exception as e:
        # 保留你的提示，但補上實際錯誤訊息方便排查  # <<< CHANGED
        print('There is some error in :{}\n{}\n'.format(account_df.iat[i, 0], e))

