#!/usr/bin/env python
# coding: utf-8
import pandas as pd

# 廣告活動類型
ad_network_type_mapping = {
    0: 'UNSPECIFIED',
    1: 'UNKNOWN',
    2: 'SEARCH',
    3: 'SEARCH_PARTNERS',
    4: 'CONTENT',
    5: 'YOUTUBE_SEARCH',
    6: 'YOUTUBE_WATCH',
    7: 'MIXED'
}


ad_type_mapping = {
    0: 'UNSPECIFIED',
    1: 'UNKNOWN',
    2: 'TEXT_AD',
    3: 'EXPANDED_TEXT_AD',
    7: 'EXPANDED_DYNAMIC_SEARCH_AD',
    8: 'HOTEL_AD',
    9: 'SHOPPING_SMART_AD',
    10: 'SHOPPING_PRODUCT_AD',
    12: 'VIDEO_AD',
    14: 'IMAGE_AD',
    15: 'RESPONSIVE_SEARCH_AD',
    16: 'LEGACY_RESPONSIVE_DISPLAY_AD',
    17: 'APP_AD',
    18: 'LEGACY_APP_INSTALL_AD',
    19: 'RESPONSIVE_DISPLAY_AD',
    20: 'LOCAL_AD',
    21: 'HTML5_UPLOAD_AD',
    22: 'DYNAMIC_HTML5_AD',
    23: 'APP_ENGAGEMENT_AD',
    24: 'SHOPPING_COMPARISON_LISTING_AD',
    25: 'VIDEO_BUMPER_AD',
    26: 'VIDEO_NON_SKIPPABLE_IN_STREAM_AD',
    27: 'VIDEO_OUTSTREAM_AD',
    29: 'VIDEO_TRUEVIEW_IN_STREAM_AD',
    30: 'VIDEO_RESPONSIVE_AD',
    31: 'SMART_CAMPAIGN_AD',
    32: 'CALL_AD',
    33: 'APP_PRE_REGISTRATION_AD',
    34: 'IN_FEED_VIDEO_AD',
    35: 'DEMAND_GEN_MULTI_ASSET_AD',
    36: 'DEMAND_GEN_CAROUSEL_AD'
}


click_type_mapping = {
    0: 'UNSPECIFIED',
    1: 'UNKNOWN',
    5: 'CALL_TRACKING',
    6: 'CALLS',
    7: 'CLICK_ON_ENGAGEMENT_AD',
    8: 'GET_DIRECTIONS',
    9: 'LOCATION_EXPANSION',
    19: 'OTHER',
    22: 'SITELINKS',
    25: 'URL_CLICKS',
    26: 'VIDEO_APP_STORE_CLICKS',
    27: 'VIDEO_CALL_TO_ACTION_CLICKS',
    28: 'VIDEO_CARD_ACTION_HEADLINE_CLICKS',
    29: 'VIDEO_END_CAP_CLICKS',
    30: 'VIDEO_WEBSITE_CLICKS',
    31: 'VISUAL_SITELINKS'
}


def query_base(start_date, end_date):
    query_base = f"""
        SELECT
            customer.id,
            campaign.id,
            campaign.name,
            ad_group.id, 
            ad_group.name,
            ad_group_ad.ad.id, 
            ad_group_ad.ad.name,
            ad_group_ad.labels,
            segments.ad_network_type,
            ad_group_ad.ad.type,
            segments.click_type,
            
            metrics.impressions, 
            metrics.clicks, 
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_micros,
            segments.date,
            
            ad_group_ad.ad.responsive_display_ad.marketing_images,
            ad_group_ad.ad.responsive_display_ad.square_marketing_images,  
            ad_group_ad.ad.image_ad.image_url,
            ad_group_ad.ad.image_ad.preview_image_url

        FROM ad_group_ad 
        WHERE 
            segments.date >= '{start_date}' 
            AND segments.date <= '{end_date}'
        """
    return query_base

query_asset = """
    SELECT 
      asset.image_asset.full_size.height_pixels,
      asset.image_asset.full_size.width_pixels,
      asset.image_asset.full_size.url,
      asset.image_asset.mime_type,
      asset.dynamic_custom_asset.image_url
    FROM asset 
    """


query_label = """
    SELECT 
      label.id, 
      label.name, 
      label.resource_name, 
      label.status
    FROM label 
    """


def query_video(start_date, end_date):
    query_video = """
        SELECT
          customer.id, 
          campaign.id, 
          campaign.name, 
          ad_group.id,
          ad_group.name,
          ad_group_ad.ad.id,
          ad_group_ad.ad.name,
          
          segments.ad_network_type,
          ad_group_ad.labels, 
          ad_group_ad.ad.type,
          segments.date,
          
          video.id,  
          video.title,
          metrics.video_views, 
          metrics.video_quartile_p25_rate, 
          metrics.video_quartile_p50_rate, 
          metrics.video_quartile_p75_rate, 
          metrics.video_quartile_p100_rate, 

          metrics.impressions, 
          metrics.clicks, 
          metrics.conversions, 
          metrics.conversions_value, 
          metrics.cost_micros
          

        FROM video 
        WHERE 
          segments.date >= '{}' 
          AND segments.date <= '{}'
        """.format(start_date, end_date)
    return query_video

def query_keyword(start_date, end_date):
    query_keyword = """
        SELECT
          customer.id,
          campaign.id,
          campaign.name,
          ad_group.id,
          ad_group.name,
          ad_group_criterion.criterion_id,
          ad_group_criterion.keyword.text,
          
          segments.ad_network_type, 
          segments.click_type,
        
          metrics.impressions,
          metrics.clicks, 
          metrics.conversions, 
          metrics.conversions_value, 
          metrics.cost_micros,
          segments.date
          
        FROM keyword_view
        WHERE 
          segments.date >= '{}' 
          AND segments.date <= '{}'
        """.format(start_date, end_date)
    return query_keyword


def query_dt(start_date, end_date):
    query_dt = """
        SELECT
            customer.id,
            campaign.id,
            campaign.name,
            ad_group.id, 
            ad_group.name,
            ad_group_ad.ad.id,
            segments.ad_network_type,
            ad_group_ad.ad.type,
            segments.click_type,
            
            ad_group_ad.ad.responsive_search_ad.headlines, 
            ad_group_ad.ad.responsive_search_ad.descriptions,
            
            metrics.impressions, 
            metrics.clicks, 
            metrics.conversions,
            metrics.conversions_value,
            metrics.cost_micros,
            segments.date
            
        FROM ad_group_ad
        WHERE
            segments.date >= '{}' 
            AND segments.date <= '{}'
            AND ad_group_ad.ad.type = 'RESPONSIVE_SEARCH_AD'
            """.format(start_date, end_date)
    return query_dt


def sql_google(account_name):
    sql_google = f"""
      SELECT  
        media,
        channel_type,
        customer_id,
        campaign_id,
        campaign_name,
        adgroup_id,
        adgroup_name,
        ad_id,
        ad_name,
        date,
        image_url,
        preview_image_url,
        CAST(impressions AS INT64) AS impressions,
        CAST(clicks AS INT64) AS clicks,
        CAST(cost AS FLOAT64) AS cost,
        CAST(conversions AS FLOAT64) AS conversions,
        CAST(conversion_value AS FLOAT64) AS conversion_value,
        CAST(video_thruplay AS FLOAT64) AS video_thruplay,
        CAST(video_views AS FLOAT64) AS video_views,
        CAST(video_p25 AS FLOAT64) AS video_p25,
        CAST(video_p50 AS FLOAT64) AS video_p50,
        CAST(video_p75 AS FLOAT64) AS video_p75,
        CAST(video_p100 AS FLOAT64) AS video_p100
      FROM `eco-carver-356809.api_ads_tables.googleAds_creative_{account_name}`
    """
    return sql_google


def sql_facebook(account_name):
    sql_facebook = f"""
      SELECT  
        ads.media,
        channel_type,
        ads.account_id AS customer_id,
        campaign_id,
        campaign_name,
        adset_id AS adgroup_id,
        adset_name AS adgroup_name,
        ads.ad_id,
        ads.ad_name,
        date_start AS date,
        img.permalink_url AS image_url,
        img.permalink_url as preview_image_url,
        CAST(impressions AS INT64) AS impressions,
        CAST(link_click AS INT64) AS clicks,
        CAST(spend AS FLOAT64) AS cost,
        CAST(purchase AS FLOAT64) AS conversions,
        CAST(purchase_value AS FLOAT64) AS conversion_value,
        CAST(video_thruplay AS FLOAT64) AS video_thruplay,
        CAST(view_view AS FLOAT64) AS video_views,
        CAST(video_25 AS FLOAT64) AS video_p25,
        CAST(video_50 AS FLOAT64) AS video_p50,
        CAST(video_75 AS FLOAT64) AS video_p75,
        CAST(video_100 AS FLOAT64) AS video_p100
      FROM `eco-carver-356809.api_ads_tables.facebook_report_{account_name}` ads
      LEFT JOIN `eco-carver-356809.api_ads_tables.facebook_image` img USING(account_id,ad_id)
    """
    return sql_facebook


def sql_yahooDSP(account_name):
    sql_yahooDSP = f"""
      SELECT  
        media,
        channel_type,
        account_id AS customer_id,
        campaign_id,
        campaign_name,
        adgroup_id,
        adgroup_name,
        ad_id,
        ad_name,
        date AS date,
        creative_url AS image_url,
        creative_url AS preview_image_url,
        CAST(impressions AS INT64) AS impressions,
        CAST(clicks AS INT64) AS clicks,
        CAST(spend AS FLOAT64) AS cost,
        CAST(conversions AS FLOAT64) AS conversions,
        CAST(conversions AS FLOAT64) AS conversion_value,
        CAST(video_thruplay AS FLOAT64) AS video_thruplay,
        CAST(view_view AS FLOAT64) AS video_views,
        CAST(video_25 AS FLOAT64) AS video_p25,
        CAST(video_50 AS FLOAT64) AS video_p50,
        CAST(video_75 AS FLOAT64) AS video_p75,
        CAST(video_100 AS FLOAT64) AS video_p100
      FROM `eco-carver-356809.api_ads_tables.yahooDsp_report_{account_name}`
    """
    return sql_yahooDSP


def sql_yahooNative(account_name):
    sql_yahooNative = f"""
      SELECT  
        media,
        channel_type,
        account_id AS customer_id,
        campaign_id,
        campaign_name,
        adgroup_id,
        adgroup_name,
        ad_id,
        ad_name,
        date AS date,
        creative_url AS image_url,
        creative_url AS preview_image_url,
        CAST(impressions AS INT64) AS impressions,
        CAST(clicks AS INT64) AS clicks,
        CAST(spend AS FLOAT64) AS cost,
        CAST(conversions AS FLOAT64) AS conversions,
        CAST(conversions AS FLOAT64) AS conversion_value,
        CAST(video_thruplay AS FLOAT64) AS video_thruplay,
        CAST(view_view AS FLOAT64) AS video_views,
        CAST(video_25 AS FLOAT64) AS video_p25,
        CAST(video_50 AS FLOAT64) AS video_p50,
        CAST(video_75 AS FLOAT64) AS video_p75,
        CAST(video_100 AS FLOAT64) AS video_p100
      FROM `eco-carver-356809.api_ads_tables.yahooNative_report_{account_name}`
    """
    return sql_yahooNative


def sql_line(account_name):
    sql_line = f"""
      SELECT  
        media,
        channel_type,
        adaccount_id AS customer_id,
        campaign_id,
        campaign_name,
        adgroup_id,
        adgroup_name,
        ad_id,
        ad_name,
        date,
        creative_url AS image_url,
        creative_url as preview_image_url,
        CAST(statistics_imp AS INT64) AS impressions,
        CAST(statistics_click AS INT64) AS clicks,
        CAST(statistics_cost AS FLOAT64) AS cost,
        CAST(statistics_cv AS FLOAT64) AS conversions,
        CAST(statistics_cv AS FLOAT64) AS conversion_value,
        CAST(video_thruplay AS FLOAT64) AS video_thruplay,
        CAST(view_view AS FLOAT64) AS video_views,
        CAST(video_25 AS FLOAT64) AS video_p25,
        CAST(video_50 AS FLOAT64) AS video_p50,
        CAST(video_75 AS FLOAT64) AS video_p75,
        CAST(video_100 AS FLOAT64) AS video_p100
      FROM `eco-carver-356809.api_ads_tables.line_report_{account_name}`
    """
    return sql_line
