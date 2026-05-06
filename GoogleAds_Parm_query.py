#!/usr/bin/env python
# coding: utf-8

# In[ ]:


import os
import logging
from google.cloud import bigquery as bq


# In[ ]:


# Pmax Basic Query
# 2024/2/27 發現cost數值與後台對不上(imp,click無此問題)
# 後經查找，只要有click_type參數，就會讓cost數值減少，拿掉click_type即解決問題XD
# 應該是 api 的問題....
def query_pmax_basic(start_date, end_date):
    query_basic = """
        SELECT 
        customer.id,
        customer.descriptive_name,
        campaign.id,
        campaign.name,
        campaign.advertising_channel_type,
                
        segments.ad_network_type,
        segments.date,
    
        metrics.impressions, 
        metrics.clicks, 
        metrics.conversions,
        metrics.conversions_value,
        metrics.cost_micros

        FROM campaign
        WHERE 
            segments.date >= '{}' 
            AND segments.date <= '{}'
            AND campaign.advertising_channel_type = 'PERFORMANCE_MAX'
            AND metrics.impressions > 0
        """.format(start_date, end_date)
    return query_basic


# In[ ]:


def query_pmax_asset():
    query = """
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
    return query

