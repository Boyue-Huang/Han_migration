#!/usr/bin/env python
# coding: utf-8

# advertising_channel_type
campaign_type_mapping = {
#       : UNSPECIFIED,
#       : UNKNOWN,
      2: 'SEARCH',
      3: 'DISPLAY',
#       : SHOPPING,
#       : HOTEL,
      6: 'VIDEO',
#       : MULTI_CHANNEL,
#       : LOCAL,
#       : SMART,
      10: 'PERFORMANCE_MAX',
#       : LOCAL_SERVICES,
      12: 'DEMAND_GEN',
#       : TRAVEL
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
    27: 'VIDEO_OUTSTREAM',
    29: 'VIDEO_TRUEVIEW_IN_STREAM_AD',
    30: 'VIDEO_RESPONSIVE_AD',
    31: 'SMART_CAMPAIGN_AD',
    32: 'CALL_AD',
    33: 'APP_PRE_REGISTRATION_AD',
    34: 'IN_FEED_VIDEO_AD',
    35: 'DEMAND_GEN_MULTI_ASSET_AD',     # 實際上 Demand Gen image ad
    36: 'DEMAND_GEN_CAROUSEL_AD'
}

keyword_match_type_mapping = {
    2: 'EXACT',
    3: 'PHRASE',
    4: 'BROAD',
    # 'UNKNOWN',
    # 'UNSPECIFIED'
}

search_term_status_mapping = {
    2: 'ADDED',
    3: 'EXCLUDED',
    5: 'NONE',
}

search_term_match_type_mapping = {
    2: 'BROAD',
    3: 'EXACT',
    4: 'PHRASE',
    5: 'NEAR_EXACT',
    6: 'NEAR_PHRASE'
}

placement_type_mapping = {
    # : 'GOOGLE_PRODUCTS',
    2: 'WEBSITE',
    4: 'MOBILE_APPLICATION',
    5: 'YOUTUBE_VIDEO',
    6: 'YOUTUBE_CHANNEL',
    # : 'MOBILE_APP_CATEGORY',
    # : 'UNKNOWN',
    # : 'UNSPECIFIED',
}

click_type_mapping = {
    0: 'UNSPECIFIED',
    1: 'UNKNOWN',
    2: 'APP_DEEPLINK',
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
    31: 'VISUAL_SITELINKS',
    57: 'CROSS_NETWORK'
    
}


# 幾乎可忽略，使用 campaign type 做區分
ad_network_type_mapping = {
    2: 'SEARCH',
    3: 'SEARCH_PARTNERS',
    4: 'CONTENT',
    7: 'MIXED',
    8: 'YOUTUBE'
}

# old
    # 0: 'UNSPECIFIED',
    # 1: 'UNKNOWN',
    # 2: 'SEARCH',
    # 3: 'SEARCH_PARTNERS',
    # 4: 'CONTENT',
    # 5: 'YOUTUBE_SEARCH',
    # 6: 'YOUTUBE_WATCH',
    # 7: 'MIXED',


# for pmax asset(image)
asset_status = {
    2: 'ENABLED',
    3: 'PAUSED',
    4: 'REMOVED'
}

