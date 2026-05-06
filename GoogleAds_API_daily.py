#!/usr/bin/env python
# coding: utf-8

# In[ ]:


#!/usr/bin/env python
# coding: utf-8

import argparse
import sys
import os
import re
import json
import datetime
import time
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import requests

from google.ads.googleads.client import GoogleAdsClient
from google.ads.googleads.errors import GoogleAdsException
from google.cloud import bigquery as bq

# 導入自己寫的函數
import GoogleAds_api_parm as p
import GoogleAds_api_token_Han as token


# =========================================================
# Helpers
# =========================================================
def _ensure_columns(df: pd.DataFrame, cols: list) -> pd.DataFrame:
    """
    確保 df 一定包含 cols 這些欄位（就算是空 df 也要有欄位），避免 merge/選欄位時 KeyError
    """
    if df is None or not isinstance(df, pd.DataFrame):
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = pd.Series(dtype="object")
    return df


def access_response(customer_id, query_input):
    googleads_client = GoogleAdsClient.load_from_dict(token.credentials)
    ga_service = googleads_client.get_service("GoogleAdsService")

    request = googleads_client.get_type("SearchGoogleAdsRequest")
    request.customer_id = str(customer_id)
    request.query = query_input
    response = ga_service.search(request=request)
    return response


# =========================================================
# Base / Asset / Label / Video base
# =========================================================
def access_base(parm_customer_id, query_base):
    base = access_response(parm_customer_id, query_base)

    # 定義要排除的 ad_type 數字（video 類型）
    exclude_ad_types = {12, 25, 26, 27, 29, 30}  # VIDEO_AD, VIDEO_BUMPER_AD, VIDEO_NON_SKIPPABLE..., OUTSTREAM, ...

    all_rows = []

    if base.results:
        for result in base.results:
            ad_type_enum = result.ad_group_ad.ad.type_

            # 過濾不支援的 video ad 類型
            if ad_type_enum in exclude_ad_types:
                continue

            ad_type_str = p.ad_type_mapping.get(ad_type_enum, 'Unknown')

            row = {
                'customer_id': result.customer.id,
                'campaign_id': result.campaign.id,
                'campaign_name': result.campaign.name,
                'adgroup_id': result.ad_group.id,
                'adgroup_name': result.ad_group.name,
                'ad_id': result.ad_group_ad.ad.id,

                'ad_network_type': p.ad_network_type_mapping.get(result.segments.ad_network_type, 'Unknown'),
                'ad_type': ad_type_str,
                'click_type': p.click_type_mapping.get(result.segments.click_type, 'Unknown'),

                'label_id': result.ad_group_ad.labels[0].split("/")[-1] if result.ad_group_ad.labels else 'None',
                'images_asset_id': str(result.ad_group_ad.ad.responsive_display_ad.marketing_images[0].asset).split("/")[-1]
                                   if ad_type_enum == 19 and result.ad_group_ad.ad.responsive_display_ad.marketing_images else 'None',
                'square_images_asset_id': str(result.ad_group_ad.ad.responsive_display_ad.square_marketing_images[0].asset).split("/")[-1]
                                          if ad_type_enum == 19 and result.ad_group_ad.ad.responsive_display_ad.square_marketing_images else 'None',

                'ad_name': result.ad_group_ad.ad.name if ad_type_enum == 14 else 'None',
                'image_url': result.ad_group_ad.ad.image_ad.image_url if ad_type_enum == 14 else 'None',

                'date': result.segments.date,
                'impressions': result.metrics.impressions,
                'clicks': result.metrics.clicks,
                'cost': result.metrics.cost_micros / 1_000_000,
                'conversions': result.metrics.conversions,
                'conversion_value': result.metrics.conversions_value,
            }

            all_rows.append(row)

        df_base = pd.DataFrame(all_rows)
    else:
        df_base = pd.DataFrame()

    return df_base


def access_asset(parm_customer_id, query_asset):
    asset = access_response(parm_customer_id, query_asset)

    if asset.results:
        df_asset = pd.DataFrame([
            {
                'asset_id': str(result.asset.resource_name).split("/")[-1],
                'asset_image_height': result.asset.image_asset.full_size.height_pixels,
                'asset_image_width': result.asset.image_asset.full_size.width_pixels,
                'asset_image_url': result.asset.image_asset.full_size.url
            }
            for result in asset.results
        ])

        # 去除前後空格 + 保留非空 url
        df_asset['asset_image_url'] = df_asset['asset_image_url'].astype(str).str.strip()
        df_asset = df_asset[df_asset['asset_image_url'] != '']

        df_asset['asset_id'] = df_asset['asset_id'].astype(str)
    else:
        # ✅ 關鍵：就算沒有資料也要回傳「有欄位」的空表，避免 KeyError
        df_asset = pd.DataFrame(columns=['asset_id', 'asset_image_height', 'asset_image_width', 'asset_image_url'])

    return df_asset


def access_label(parm_customer_id, query_label):
    label = access_response(parm_customer_id, query_label)

    if label.results:
        df_label = pd.DataFrame([
            {
                'label_id': result.label.id,
                'label_name': result.label.name
            }
            for result in label.results
        ])
        df_label['label_id'] = df_label['label_id'].astype(str)
    else:
        # ✅ 關鍵：就算沒有資料也要回傳「有欄位」的空表，避免 merge KeyError: 'label_id'
        df_label = pd.DataFrame(columns=['label_id', 'label_name'])

    return df_label


def access_video_base(parm_customer_id, query_video):
    video = access_response(parm_customer_id, query_video)

    if video.results:
        df_video = pd.DataFrame([
            {
                'customer_id': result.customer.id,
                'campaign_id': result.campaign.id,
                'campaign_name': result.campaign.name,
                'adgroup_id': result.ad_group.id,
                'adgroup_name': result.ad_group.name,
                'ad_id': result.ad_group_ad.ad.id,
                'ad_name': result.ad_group_ad.ad.name,

                'ad_network_type': p.ad_network_type_mapping.get(result.segments.ad_network_type, 'Unknown'),
                'ad_type': p.ad_type_mapping.get(result.ad_group_ad.ad.type_, 'Unknown'),
                'click_type': p.click_type_mapping.get(result.segments.click_type, 'Unknown'),

                'label_id': result.ad_group_ad.labels[0].split("/")[-1] if result.ad_group_ad.labels else 'None',

                'youtube_id': result.video.id if re.search('VIDEO', p.ad_type_mapping.get(result.ad_group_ad.ad.type_, 'Unknown')) else 'None',
                'video_name': result.video.title if re.search('VIDEO', p.ad_type_mapping.get(result.ad_group_ad.ad.type_, 'Unknown')) else 'None',

                'date': result.segments.date,
                'impressions': result.metrics.impressions,
                'clicks': result.metrics.clicks,
                'cost': result.metrics.cost_micros / 1_000_000,
                'conversions': result.metrics.conversions,
                'conversion_value': result.metrics.conversions_value,

                'video_views': result.metrics.video_views,
                'video_p25_rate': result.metrics.video_quartile_p25_rate,
                'video_p50_rate': result.metrics.video_quartile_p50_rate,
                'video_p75_rate': result.metrics.video_quartile_p75_rate,
                'video_p100_rate': result.metrics.video_quartile_p100_rate
            }
            for result in video.results
        ])

        df_video['video_p25'] = round(df_video['video_views'] * df_video['video_p25_rate'], 2)
        df_video['video_p50'] = round(df_video['video_views'] * df_video['video_p50_rate'], 2)
        df_video['video_p75'] = round(df_video['video_views'] * df_video['video_p75_rate'], 2)
        df_video['video_p100'] = round(df_video['video_views'] * df_video['video_p100_rate'], 2)

    else:
        df_video = pd.DataFrame()

    return df_video


# =========================================================
# SEARCH / DISPLAY / IMAGE / VIDEO
# =========================================================
def access_search(df_base):
    df_search_agg = pd.DataFrame()

    if df_base.empty:
        print("No data available for SEARCH AD.")
        return df_search_agg

    df_search = df_base[df_base['ad_network_type'].astype(str).str.startswith('SEARCH')]

    if df_search.empty:
        print("No data available for SEARCH AD.")
        return df_search_agg

    def sum_imp(series):
        return series.loc[df_search['click_type'] == 'URL_CLICKS'].sum()

    df_search_agg = df_search.groupby([
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name', 'date'
    ]).agg({
        'impressions': sum_imp,
        'clicks': 'sum',
        'cost': 'sum',
        'conversions': 'sum',
        'conversion_value': 'sum'
    }).reset_index()

    df_search_agg['media'] = 'Google'
    df_search_agg['channel_type'] = 'Google SEARCH'
    df_search_agg['ad_id'] = '-'
    df_search_agg['ad_name'] = 'RESPONSIVE_SEARCH_AD'
    df_search_agg['image_url'] = 'https://topsceneassets.com/RESPONSIVE_SEARCH_AD.jpg'
    df_search_agg['preview_image_url'] = 'https://topsceneassets.com/RESPONSIVE_SEARCH_AD.jpg'

    dtype_dict = {'customer_id': str, 'campaign_id': str, 'adgroup_id': str, 'ad_id': str}
    df_search_agg = df_search_agg.astype(dtype_dict)

    return df_search_agg


def access_display(df_base, df_asset, df_label):
    df_display_fin = pd.DataFrame()

    if df_base.empty:
        print("No data available for RESPONSIVE DISPLAY AD.")
        return df_display_fin

    df_display = df_base[df_base['ad_type'].astype(str).str.contains('RESPONSIVE_DISPLAY_AD', na=False)]
    if df_display.empty:
        print("No data available for RESPONSIVE DISPLAY AD.")
        return df_display_fin

    # ✅ 確保空表也有欄位
    df_label = _ensure_columns(df_label, ['label_id', 'label_name'])
    df_asset = _ensure_columns(df_asset, ['asset_id', 'asset_image_url'])

    def sum_imp(series):
        return series.loc[df_display['click_type'] == 'URL_CLICKS'].sum()

    def sum_others(series):
        return series.loc[(df_display['click_type'] == 'URL_CLICKS') | (df_display['click_type'] == 'CALLS')].sum()

    df_display_agg = df_display.groupby([
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name', 'ad_id', 'label_id', 'date',
        'images_asset_id', 'square_images_asset_id'
    ]).agg({
        'impressions': sum_imp,
        'clicks': sum_others,
        'cost': sum_others,
        'conversions': sum_others,
        'conversion_value': sum_others
    }).reset_index()

    df_display_agg['media'] = 'Google'
    df_display_agg['channel_type'] = 'Google CONTENT'

    dtype_dict = {
        'customer_id': str,
        'campaign_id': str,
        'adgroup_id': str,
        'ad_id': str,
        'label_id': str,
        'images_asset_id': str,
        'square_images_asset_id': str
    }
    df_display_agg = df_display_agg.astype(dtype_dict)

    # label merge（不會再 KeyError）
    df_display_agg = df_display_agg.merge(df_label, on='label_id', how='left')
    df_display_agg['label_name'] = df_display_agg['label_name'].fillna('None')
    df_display_agg['ad_name'] = df_display_agg['label_name']

    # asset merge：square
    df_display_fin = df_display_agg.merge(
        df_asset[['asset_id', 'asset_image_url']],
        how='left',
        left_on='square_images_asset_id',
        right_on='asset_id'
    ).drop(columns=['asset_id'], errors='ignore').rename(columns={'asset_image_url': 'asset_square_image_url'})

    # asset merge：rect
    df_display_fin = df_display_fin.merge(
        df_asset[['asset_id', 'asset_image_url']],
        how='left',
        left_on='images_asset_id',
        right_on='asset_id'
    ).drop(columns=['asset_id'], errors='ignore').rename(columns={'asset_image_url': 'asset_rect_image_url'})

    # ✅ 統一輸出欄位：asset_image_url（優先 square，沒有就用 rect）
    df_display_fin['asset_image_url'] = df_display_fin['asset_square_image_url']
    df_display_fin.loc[df_display_fin['asset_image_url'].isna(), 'asset_image_url'] = df_display_fin['asset_rect_image_url']

    return df_display_fin


def access_image(df_base, df_label):
    df_imageAd_agg = pd.DataFrame()

    if df_base.empty:
        print("No data available for IMAGE AD.")
        return df_imageAd_agg

    df_imageAd = df_base[df_base['ad_type'].astype(str).str.contains('IMAGE_AD', na=False)]
    if df_imageAd.empty:
        print("No data available for IMAGE AD.")
        return df_imageAd_agg

    # ✅ 確保空表也有欄位
    df_label = _ensure_columns(df_label, ['label_id', 'label_name'])

    def sum_imp(series):
        return series.loc[df_imageAd['click_type'] == 'URL_CLICKS'].sum()

    def sum_others(series):
        return series.loc[(df_imageAd['click_type'] == 'URL_CLICKS') | (df_imageAd['click_type'] == 'CALLS')].sum()

    df_imageAd_agg = df_imageAd.groupby([
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name', 'ad_id', 'ad_name', 'label_id', 'date',
        'image_url'
    ]).agg({
        'impressions': sum_imp,
        'clicks': sum_others,
        'cost': sum_others,
        'conversions': sum_others,
        'conversion_value': sum_others
    }).reset_index()

    df_imageAd_agg['media'] = 'Google'
    df_imageAd_agg['channel_type'] = 'Google CONTENT'

    dtype_dict = {
        'customer_id': str,
        'campaign_id': str,
        'adgroup_id': str,
        'ad_id': str,
        'label_id': str
    }
    df_imageAd_agg = df_imageAd_agg.astype(dtype_dict)

    df_imageAd_agg = df_imageAd_agg.merge(df_label, on='label_id', how='left')
    df_imageAd_agg['label_name'] = df_imageAd_agg['label_name'].fillna('None')
    df_imageAd_agg['ad_name'] = df_imageAd_agg['label_name']

    return df_imageAd_agg


def access_video(df_video, df_label):
    df_video_agg = pd.DataFrame()

    if df_video.empty:
        print("No data available for VIDEO AD.")
        return df_video_agg

    # ✅ 確保空表也有欄位
    df_label = _ensure_columns(df_label, ['label_id', 'label_name'])

    df_video_agg = df_video.groupby([
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name', 'ad_id', 'ad_name', 'label_id',
        'youtube_id', 'video_name', 'date'
    ]).agg({
        'impressions': 'sum',
        'clicks': 'sum',
        'cost': 'sum',
        'conversions': 'sum',
        'conversion_value': 'sum',
        'video_views': 'sum',
        'video_p25': 'sum',
        'video_p50': 'sum',
        'video_p75': 'sum',
        'video_p100': 'sum',
    }).reset_index()

    df_video_agg['media'] = 'Google'
    df_video_agg['channel_type'] = 'Google YOUTUBE_WATCH'

    dtype_dict = {
        'customer_id': str,
        'campaign_id': str,
        'adgroup_id': str,
        'ad_id': str,
        'label_id': str,
        'youtube_id': str
    }
    df_video_agg = df_video_agg.astype(dtype_dict)

    df_video_agg = df_video_agg.merge(df_label, on='label_id', how='left')
    df_video_agg['label_name'] = df_video_agg['label_name'].fillna('None')
    df_video_agg['ad_name'] = df_video_agg['label_name']

    return df_video_agg


# =========================================================
# Combine
# =========================================================
def combined(df_search, df_display, df_image, df_video):
    # 為避免缺少某個媒體資料造成欄位對不上，先創造一個空df
    all_columns = [
        'media', 'channel_type',
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name',
        'ad_id', 'ad_name',
        'label_name', 'date',
        'image_url', 'asset_image_url', 'youtube_id',
        'impressions', 'clicks', 'cost', 'conversions', 'conversion_value',
        'video_views', 'video_p25', 'video_p50', 'video_p75', 'video_p100'
    ]
    df_temp = pd.DataFrame(columns=all_columns)

    df_combined = pd.concat([df_temp, df_search, df_display, df_image, df_video], ignore_index=True)

    # 確保必要欄位存在（避免奇怪來源 df 缺欄）
    df_combined = _ensure_columns(df_combined, [
        'image_url', 'asset_image_url', 'youtube_id',
        'video_views', 'video_p25', 'video_p50', 'video_p75', 'video_p100'
    ])

    # image url：若 image_url 空，改用 asset_image_url
    df_combined.loc[df_combined['image_url'].isna() & df_combined['asset_image_url'].notna(), 'image_url'] = df_combined['asset_image_url']

    # 若是 YouTube 類型且 image_url 還是空，補 YouTube thumbnail
    if not df_video.empty:
        mask = df_combined['image_url'].isna() & df_combined['youtube_id'].notna() & (df_combined['youtube_id'].astype(str) != 'None')
        df_combined.loc[mask, 'image_url'] = df_combined.loc[mask, 'youtube_id'].apply(lambda y: f"https://i.ytimg.com/vi/{y}/hqdefault.jpg")

    df_combined['preview_image_url'] = df_combined['image_url']
    df_combined['video_thruplay'] = df_combined['video_views']

    new_columns = [
        'media', 'channel_type',
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name',
        'ad_id', 'ad_name',
        'date', 'image_url', 'preview_image_url',
        'impressions', 'clicks', 'cost', 'conversions', 'conversion_value',
        'video_thruplay', 'video_views', 'video_p25', 'video_p50', 'video_p75', 'video_p100'
    ]
    df_combined = _ensure_columns(df_combined, new_columns)
    df_combined = df_combined[new_columns].reindex(columns=new_columns)

    # 日期格式
    df_combined['date'] = pd.to_datetime(df_combined['date'], errors='coerce').dt.date

    print(df_combined.head())
    return df_combined


# =========================================================
# Keyword / Responsive Ad
# =========================================================
def access_keyword(parm_customer_id, query_keyword):
    keyword = access_response(parm_customer_id, query_keyword)

    if keyword.results:
        df_keyword = pd.DataFrame([
            {
                'customer_id': result.customer.id,
                'campaign_id': result.campaign.id,
                'campaign_name': result.campaign.name,
                'adgroup_id': result.ad_group.id,
                'adgroup_name': result.ad_group.name,
                'criterion_id': result.ad_group_criterion.criterion_id,
                'criteria': result.ad_group_criterion.keyword.text,

                'ad_network_type': p.ad_network_type_mapping.get(result.segments.ad_network_type, 'Unknown'),
                'click_type': p.click_type_mapping.get(result.segments.click_type, 'Unknown'),

                'date': result.segments.date,
                'impressions': result.metrics.impressions,
                'clicks': result.metrics.clicks,
                'cost': result.metrics.cost_micros / 1_000_000,
                'conversions': result.metrics.conversions,
                'conversion_value': result.metrics.conversions_value
            }
            for result in keyword.results
        ])
    else:
        df_keyword = pd.DataFrame()
        print("No data available for KEYWORD AD.")

    df_keyword_agg = pd.DataFrame()
    if df_keyword.empty:
        return df_keyword_agg

    def sum_imp(series):
        return series.loc[df_keyword['click_type'] == 'URL_CLICKS'].sum()

    df_keyword_agg = df_keyword.groupby([
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name',
        'criterion_id', 'criteria', 'date'
    ]).agg({
        'impressions': sum_imp,
        'clicks': 'sum',
        'cost': 'sum',
        'conversions': 'sum',
        'conversion_value': 'sum',
    }).reset_index()

    df_keyword_agg['media'] = 'Google'
    df_keyword_agg['channel_type'] = 'Google SEARCH'

    dtype_dict = {'customer_id': str, 'campaign_id': str, 'adgroup_id': str, 'criterion_id': str}
    df_keyword_agg = df_keyword_agg.astype(dtype_dict)

    new_columns = [
        'media', 'channel_type',
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name',
        'criterion_id', 'criteria',
        'date', 'impressions', 'clicks', 'cost', 'conversions', 'conversion_value'
    ]
    df_keyword_agg = _ensure_columns(df_keyword_agg, new_columns)[new_columns].reindex(columns=new_columns)
    df_keyword_agg['date'] = pd.to_datetime(df_keyword_agg['date'], errors='coerce')

    return df_keyword_agg


def access_keyword_responsive_ad(parm_customer_id, query_dt):
    dt = access_response(parm_customer_id, query_dt)

    if dt.results:
        df_dt = pd.DataFrame([
            {
                'customer_id': result.customer.id,
                'campaign_id': result.campaign.id,
                'campaign_name': result.campaign.name,
                'adgroup_id': result.ad_group.id,
                'adgroup_name': result.ad_group.name,
                'ad_id': result.ad_group_ad.ad.id,

                'ad_network_type': p.ad_network_type_mapping.get(result.segments.ad_network_type, 'Unknown'),
                'ad_type': p.ad_type_mapping.get(result.ad_group_ad.ad.type_, 'Unknown'),
                'click_type': p.click_type_mapping.get(result.segments.click_type, 'Unknown'),

                'headline': " || ".join(item.text for item in result.ad_group_ad.ad.responsive_search_ad.headlines),
                'description': " || ".join(item.text for item in result.ad_group_ad.ad.responsive_search_ad.descriptions),

                'date': result.segments.date,
                'impressions': result.metrics.impressions,
                'clicks': result.metrics.clicks,
                'cost': result.metrics.cost_micros / 1_000_000,
                'conversions': result.metrics.conversions,
                'conversion_value': result.metrics.conversions_value
            }
            for result in dt.results
        ])
    else:
        df_dt = pd.DataFrame()
        print("No data available for KEYWORD RESPONSIVE AD.")

    df_dt_agg = pd.DataFrame()
    if df_dt.empty:
        return df_dt_agg

    def sum_imp(series):
        return series.loc[df_dt['click_type'] == 'URL_CLICKS'].sum()

    df_dt_agg = df_dt.groupby([
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name',
        'ad_id', 'ad_type', 'headline', 'description', 'date'
    ]).agg({
        'impressions': sum_imp,
        'clicks': 'sum',
        'cost': 'sum',
        'conversions': 'sum',
        'conversion_value': 'sum',
    }).reset_index()

    df_dt_agg['media'] = 'Google'
    df_dt_agg['channel_type'] = 'Google SEARCH'

    dtype_dict = {'customer_id': str, 'campaign_id': str, 'adgroup_id': str, 'ad_id': str}
    df_dt_agg = df_dt_agg.astype(dtype_dict)

    new_columns = [
        'media', 'channel_type',
        'customer_id', 'campaign_id', 'campaign_name',
        'adgroup_id', 'adgroup_name', 'ad_id',
        'date', 'impressions', 'clicks', 'cost', 'conversions', 'conversion_value',
        'ad_type', 'headline', 'description'
    ]
    df_dt_agg = _ensure_columns(df_dt_agg, new_columns)[new_columns].reindex(columns=new_columns)

    df_dt_agg.loc[df_dt_agg['ad_type'] == 'RESPONSIVE_SEARCH_AD', 'ad_type'] = '回應式搜尋廣告'
    df_dt_agg['date'] = pd.to_datetime(df_dt_agg['date'], errors='coerce')

    return df_dt_agg


# =========================================================
# Process date range
# =========================================================
def process_date_range(parm_customer_id, start_date, end_date):
    df_combined = pd.DataFrame()
    df_keyword = pd.DataFrame()
    df_keyword_responsive_ad = pd.DataFrame()

    current_date = start_date

    while current_date <= end_date:
        next_date = current_date + datetime.timedelta(days=14)
        if next_date > end_date:
            next_date = end_date

        start_time = time.time()
        print('-- date --')
        print(current_date)
        print(next_date)

        query_base = p.query_base(current_date, next_date)
        query_asset = p.query_asset
        query_label = p.query_label
        query_video = p.query_video(current_date, next_date)
        query_keyword = p.query_keyword(current_date, next_date)
        query_dt = p.query_dt(current_date, next_date)

        df_base = access_base(parm_customer_id, query_base)
        df_asset = access_asset(parm_customer_id, query_asset)
        df_label = access_label(parm_customer_id, query_label)
        df_video_base = access_video_base(parm_customer_id, query_video)

        # ✅ 立即驗證（想關掉就註解）
        print("df_label columns:", df_label.columns.tolist(), "rows:", len(df_label))
        print("df_asset columns:", df_asset.columns.tolist(), "rows:", len(df_asset))

        df_search = access_search(df_base)
        df_display = access_display(df_base, df_asset, df_label)
        df_image = access_image(df_base, df_label)
        df_video = access_video(df_video_base, df_label)

        new_df_combined = combined(df_search, df_display, df_image, df_video)
        new_df_keyword = access_keyword(parm_customer_id, query_keyword)
        new_df_keyword_responsive_ad = access_keyword_responsive_ad(parm_customer_id, query_dt)

        if not new_df_combined.empty:
            df_combined = pd.concat([df_combined, new_df_combined], ignore_index=True)
        if not new_df_keyword.empty:
            df_keyword = pd.concat([df_keyword, new_df_keyword], ignore_index=True)
        if not new_df_keyword_responsive_ad.empty:
            df_keyword_responsive_ad = pd.concat([df_keyword_responsive_ad, new_df_keyword_responsive_ad], ignore_index=True)

        print('Done for this session.')
        print("This session 執行時間：", time.time() - start_time)

        current_date = next_date + datetime.timedelta(days=1)

    if not df_combined.empty:
        df_combined['date'] = pd.to_datetime(df_combined['date'], errors='coerce').dt.date
    if not df_keyword.empty:
        df_keyword['date'] = pd.to_datetime(df_keyword['date'], errors='coerce').dt.date
    if not df_keyword_responsive_ad.empty:
        df_keyword_responsive_ad['date'] = pd.to_datetime(df_keyword_responsive_ad['date'], errors='coerce').dt.date

    print("success")
    return df_combined, df_keyword, df_keyword_responsive_ad


# =========================================================
# BigQuery upload + Union
# =========================================================
schema = [
    bq.SchemaField("media", "STRING"),
    bq.SchemaField("channel_type", "STRING"),
    bq.SchemaField("customer_id", "STRING"),
    bq.SchemaField("campaign_id", "STRING"),
    bq.SchemaField("campaign_name", "STRING"),
    bq.SchemaField("adgroup_id", "STRING"),
    bq.SchemaField("adgroup_name", "STRING"),
    bq.SchemaField("ad_id", "STRING"),
    bq.SchemaField("ad_name", "STRING"),

    bq.SchemaField("date", "DATE"),
    bq.SchemaField("image_url", "STRING"),
    bq.SchemaField("preview_image_url", "STRING"),

    bq.SchemaField("impressions", "INTEGER"),
    bq.SchemaField("clicks", "INTEGER"),
    bq.SchemaField("cost", "FLOAT"),
    bq.SchemaField("conversions", "FLOAT"),
    bq.SchemaField("conversion_value", "FLOAT"),

    bq.SchemaField("video_thruplay", "FLOAT"),
    bq.SchemaField("video_views", "FLOAT"),
    bq.SchemaField("video_p25", "FLOAT"),
    bq.SchemaField("video_p50", "FLOAT"),
    bq.SchemaField("video_p75", "FLOAT"),
    bq.SchemaField("video_p100", "FLOAT")
]


# ✅ 新增：依照 BigQuery Table Schema 強制整理 df dtype（解你要的兩個錯誤）
def _sanitize_df_for_bq_by_table_schema(df: pd.DataFrame, table_obj: bq.Table) -> pd.DataFrame:
    """
    1) 解 pyarrow 轉換錯誤：欄位 dtype 混雜/物件型態，統一轉成 schema 對應的 pandas dtype
    2) 解 float -> int64 截斷錯誤：對 INT64 欄位先 round(0) 再轉整數
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # 確保 schema 欄位都存在；並且只保留 schema 欄位，避免多餘欄位造成 load error
    schema_fields = list(table_obj.schema)
    schema_names = [f.name for f in schema_fields]

    for name in schema_names:
        if name not in df.columns:
            df[name] = pd.NA

    df = df[schema_names]

    # 先把 inf/-inf 變成 NaN（避免 arrow/BigQuery 報錯）
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    for f in schema_fields:
        col = f.name
        typ = (f.field_type or "").upper()

        # STRING / BYTES
        if typ in ("STRING", "BYTES"):
            # 使用 pandas string dtype，並把 nan 保留為 <NA>
            df[col] = df[col].astype("string")

        # DATE
        elif typ == "DATE":
            # 轉成 python datetime.date 或 NaT
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

        # DATETIME / TIMESTAMP
        elif typ in ("DATETIME", "TIMESTAMP"):
            df[col] = pd.to_datetime(df[col], errors="coerce")

        # BOOL
        elif typ in ("BOOLEAN", "BOOL"):
            # 允許 NA
            df[col] = df[col].astype("boolean")

        # INT64 / INTEGER
        elif typ in ("INTEGER", "INT64"):
            # 關鍵：先 to_numeric，再 round(0)，再轉整數，避免 float 小數被 BigQuery 截斷報錯
            s = pd.to_numeric(df[col], errors="coerce")
            s = s.round(0)  # <--- 解 Float value truncated converting to int64
            # 用 Int64 可容許 NA，但你這邊通常要上傳，乾脆補 0 比較穩
            df[col] = s.fillna(0).astype("int64")

        # FLOAT64 / FLOAT / NUMERIC / BIGNUMERIC
        elif typ in ("FLOAT", "FLOAT64", "NUMERIC", "BIGNUMERIC"):
            # 關鍵：統一成 float64（不要 object），避免 pyarrow datatype error
            df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

        else:
            # 其他型別先保守轉 string，避免 object 混雜（你目前 schema 應該用不到）
            df[col] = df[col].astype("string")

    return df


def upload_to_bigquery(project_name, dataset_name, table_name, df):
    notification = []

    if df.empty:
        msg = f"No data update to : {table_name}"
        print(msg)
        notification.append("HRD 瀚睿埬 " + msg)
        return notification

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
    client = bq.Client()
    table_ref = f"{project_name}.{dataset_name}.{table_name}"

    table_exists = True
    table_obj = None
    try:
        table_obj = client.get_table(table_ref)
        print(f"Table {table_ref} exists.")
    except Exception as e:
        print(f"[ERROR] get_table: {e}")
        table_exists = False

    try:
        if table_exists:
            sql = f"""
                DELETE FROM `{table_ref}`
                WHERE date BETWEEN DATE_SUB(DATE(TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 8 HOUR)), INTERVAL 14 DAY)
                AND DATE(TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 8 HOUR))
            """
            query_job = client.query(sql, location="US")
            query_job.result()
            print(f"Deleted past 14 days from {table_ref}")

            # ✅ 核心修正：依照「既有 table schema」整理 df dtype，解 pyarrow & truncation 兩種錯誤
            df_upload = _sanitize_df_for_bq_by_table_schema(df, table_obj)

            job_config = bq.LoadJobConfig(
                schema=table_obj.schema,  # 明確帶 schema，避免型別推斷出錯
                write_disposition=bq.WriteDisposition.WRITE_APPEND,
            )
        else:
            # 若表不存在：維持原本行為（autodetect），但這情境你多數不會用到
            df_upload = df.copy()
            job_config = bq.LoadJobConfig(write_disposition=bq.WriteDisposition.WRITE_APPEND)

        query_job = client.load_table_from_dataframe(df_upload, table_ref, location="US", job_config=job_config)
        query_job.result()
        print(f"Uploaded data to {table_ref}")

        notification.append(f"HRD 瀚睿埬 Update data to : {table_name}")

    except Exception as e:
        err_msg = f"[ERROR uploading data to] {table_name}\n{str(e)}"
        print(err_msg)
        notification.append("HRD 瀚睿埬 上傳失敗 : " + table_name + f"\n\n錯誤：{str(e)}")

    return notification


def union_all_media_table(account_name, project_name, dataset_name, table_creative):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
    client = bq.Client()

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

    if not sql_queries:
        print(f"⚠️ union_all_media_table: 找不到任何符合 {account_name} 的資料表可 UNION")
        return

    union_query = f"SELECT DISTINCT * FROM ({' UNION ALL '.join(sql_queries)})"

    table_ref = f"{project_name}.{dataset_name}.{table_creative}"

    job_config = bq.QueryJobConfig()
    job_config.destination = table_ref
    job_config.write_disposition = bq.WriteDisposition.WRITE_TRUNCATE
    job_config.create_disposition = bq.CreateDisposition.CREATE_IF_NEEDED

    query_job = client.query(union_query, location="US", job_config=job_config)
    query_job.result()

    print("Update data to : {}".format(table_creative))


# =========================================================
# Main run
# =========================================================
if __name__ == "__main__":

    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
    client = bq.Client()

    project_name = 'eco-carver-356809'
    dataset_name = 'ref_tables'
    table_name = 'googleAds_account'

    sql = f"""
        SELECT *
        FROM `{project_name}.{dataset_name}.{table_name}`
    """
    df_account = client.query(sql, location="US").to_dataframe()

    # 只跑指定帳戶
    df_account

    for i in range(0, len(df_account)):

        # Step 1️⃣: 時區與日期設定 (台灣時間)
        utc = datetime.datetime.utcnow()
        tw_time = utc + datetime.timedelta(hours=8)

        # ✅ 修正：變數叫 last7days 就真的減 7 天
        tw_last7days = tw_time - datetime.timedelta(days=14)

        parm_start_date = tw_last7days.date()
        parm_end_date = tw_time.date()

        # Step 2️⃣: 抓取帳戶參數
        name = df_account.iat[i, 0]
        account_name = df_account.iat[i, 1]
        customer_id = df_account.iat[i, 2]
        project_name = df_account.iat[i, 3]
        dataset_tmp = df_account.iat[i, 4]
        table_googleAds_creative = df_account.iat[i, 5]

        dataset_name = df_account.iat[i, 6]
        table_creative = df_account.iat[i, 7]
        table_keyword = df_account.iat[i, 8]
        table_keyword_responsive_ad = df_account.iat[i, 9]

        print(f"\n====================\n【處理帳戶】{name} {account_name}")

        try:
            df_combined, df_keyword, df_keyword_responsive_ad = process_date_range(
                customer_id, parm_start_date, parm_end_date
            )
            print('✅ DataFrame 擷取成功')

            try:
                upload_to_bigquery(project_name, dataset_tmp, table_googleAds_creative, df_combined)
            except Exception as e:
                print(f"❌ [Creative] 上傳失敗 - {table_googleAds_creative} | 錯誤：{str(e)}")

            try:
                upload_to_bigquery(project_name, dataset_name, table_keyword, df_keyword)
            except Exception as e:
                print(f"❌ [Keyword] 上傳失敗 - {table_keyword} | 錯誤：{str(e)}")

            try:
                upload_to_bigquery(project_name, dataset_name, table_keyword_responsive_ad, df_keyword_responsive_ad)
            except Exception as e:
                print(f"❌ [Responsive Ad] 上傳失敗 - {table_keyword_responsive_ad} | 錯誤：{str(e)}")

        except Exception as e:
            print(f"🛑 ❗ 資料擷取或前面處理流程出現錯誤：{account_name}")
            print(f"[Exception]\n{str(e)}")

        print()

        try:
            union_all_media_table(account_name, project_name, dataset_name, table_creative)
        except Exception as e:
            print(f"❌ union_all_media_table union 錯誤：{account_name}")
            print(f"[Exception]\n{str(e)}")

        print("✅ 處理完成", name)
        print("=========================================")

