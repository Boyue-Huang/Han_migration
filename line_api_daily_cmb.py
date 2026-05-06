#!/usr/bin/env python
# coding: utf-8

# In[26]:


#!/usr/bin/env python
# coding: utf-8
"""
LINE Ads API v3 → pandas → BigQuery
- 時區安全：使用 datetime.now(UTC) + ZoneInfo("Asia/Taipei")
- 韌性欄位對齊：自動將多種別名對齊到統一 schema，缺欄補預設值
- BQ 刪除近 7 天 (含今日) 後重灌
"""

import os
import json
import base64
import hashlib
import hmac
import urllib.request
from datetime import datetime, timedelta

import pandas as pd
from google.cloud import bigquery as bq

# ======== 時區工具 ========
try:
    from datetime import UTC  # py3.11+
except ImportError:
    from datetime import timezone as _tz
    UTC = _tz.utc

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

TZ_TAIPEI = ZoneInfo("Asia/Taipei") if ZoneInfo else None


def now_utc() -> datetime:
    return datetime.now(UTC)


def now_tw() -> datetime:
    return now_utc().astimezone(TZ_TAIPEI) if TZ_TAIPEI else (now_utc() + timedelta(hours=8))


# ======== 認證設定（請自行保護金鑰）========
client_config = {
    "access_key": "7iOMeGhrpZCG50O4",
    "secret_key": "NgMRltpqqno0TVBE8OyIPLsdurEbRGJ9",
}

# ======== 欄位定義（統一 schema）========
STR_COLS = [
    "media", "channel_type",
    "adaccount_id", "adaccount_name", "campaign_id", "campaign_name",
    "adgroup_id", "adgroup_name", "adgroup_bidType", "ad_id", "ad_name",
]
INT_COLS = ["statistics_imp", "statistics_click", "statistics_reach"]
FLOAT_COLS = [
    "statistics_cost", "statistics_cv",
    "video_thruplay", "view_view", "video_25", "video_50", "video_75", "video_100",
]
REQUIRED = STR_COLS + ["date"] + INT_COLS + FLOAT_COLS

# 同義欄位（鍵一律用：正規化後的「全小寫」）
# 正規化規則：把 . - 空白 → _，再 .lower()
CANON_SYNONYMS = {
    # id/name 類
    "adaccount.id": "adaccount_id",
    "adaccount_id": "adaccount_id",
    "adaccount.name": "adaccount_name",
    "adaccount_name": "adaccount_name",
    "campaign.id": "campaign_id",
    "campaign_id": "campaign_id",
    "campaign.name": "campaign_name",
    "campaign_name": "campaign_name",
    "adgroup.id": "adgroup_id",
    "adgroup_id": "adgroup_id",
    "adgroup.name": "adgroup_name",
    "adgroup_name": "adgroup_name",
    "adgroupbidtype": "adgroup_bidType",
    "adgroup_bidtype": "adgroup_bidType",
    "ad.id": "ad_id",
    "ad_id": "ad_id",
    "ad.name": "ad_name",
    "ad_name": "ad_name",

    # 日期
    "date": "date",

    # metrics: impressions
    "statistics.impressions": "statistics_imp",
    "statistics_impressions": "statistics_imp",
    "impressions": "statistics_imp",
    "impression": "statistics_imp",

    # clicks
    "statistics.clicks": "statistics_click",
    "statistics_clicks": "statistics_click",
    "clicks": "statistics_click",
    "click": "statistics_click",

    # cost / spend
    "statistics.spend": "statistics_cost",
    "statistics_spend": "statistics_cost",
    "spend": "statistics_cost",
    "cost": "statistics_cost",
    "statistics.cost": "statistics_cost",
    "statistics_cost": "statistics_cost",

    # conversions
    "statistics.conversions": "statistics_cv",
    "statistics_conversions": "statistics_cv",
    "conversions": "statistics_cv",
    "cv": "statistics_cv",
    "statistics.cv": "statistics_cv",
    "statistics_cv": "statistics_cv",

    # reach
    "statistics.reach": "statistics_reach",
    "statistics_reach": "statistics_reach",
    "reach": "statistics_reach",

    # video metrics
    "statistics.videoview3s": "statistics_videoView3s",
    "statistics_videoview3s": "statistics_videoView3s",
    "statistics.videoview25r": "statistics_videoView25r",
    "statistics_videoview25r": "statistics_videoView25r",
    "statistics.videoview50r": "statistics_videoView50r",
    "statistics_videoview50r": "statistics_videoView50r",
    "statistics.videoview75r": "statistics_videoView75r",
    "statistics_videoview75r": "statistics_videoView75r",
    "statistics.videocompletions": "statistics_videoCompletions",
    "statistics_videocompletions": "statistics_videoCompletions",

    # 有些報表會直接給 video_view
    "video_view": "view_view",
}


# ======== 共用：欄名正規化 & 對齊 ========
def _norm_col(s: str) -> str:
    s = str(s or "")
    s = s.replace(".", "_").replace("-", "_").replace(" ", "_")
    while "__" in s:
        s = s.replace("__", "_")
    return s


def _rename_to_canonical(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    # 先把欄名做基本正規化
    orig_cols = list(df.columns)
    df.columns = [_norm_col(c) for c in df.columns]

    # 以 "全小寫" 做對照
    lower_to_actual = {c.lower(): c for c in df.columns}

    rename_map = {}
    for syn_key, canon in CANON_SYNONYMS.items():
        k = _norm_col(syn_key).lower()
        if k in lower_to_actual:
            src = lower_to_actual[k]
            rename_map[src] = canon

    if rename_map:
        df = df.rename(columns=rename_map)

    return df


def _ensure_required(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    # 補固定欄（若不存在）
    for c in STR_COLS:
        if c not in df:
            df[c] = ""
        df[c] = df[c].astype(str)

    if "date" not in df:
        df["date"] = pd.NaT
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    for c in INT_COLS:
        if c not in df:
            df[c] = 0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")

    for c in FLOAT_COLS:
        if c not in df:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype("float64")

    return df[REQUIRED]


# ======== LINE API 簽章與存取 ========
def _calc_sha256_digest(content: str) -> str:
    sha256 = hashlib.new("sha256")
    sha256.update(content.encode())
    return sha256.hexdigest()


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode()


def read_text(canonical_url: str, url_parameters: str, index: str) -> pd.DataFrame:
    """
    以 GET 取得 JSON → normalize → 回傳指定 index ('datas'/'paging') 對應的 DataFrame
    """
    access_key = client_config["access_key"]
    secret_key = client_config["secret_key"]

    endpoint = "https://ads.line.me" + canonical_url + url_parameters
    method = "GET"

    # GET 沒有 body（重要）
    request_body_json = ""
    content_type = ""

    jws_header = _b64url(json.dumps({
        "alg": "HS256",
        "kid": access_key,
        "typ": "text/plain",
    }).encode())

    hex_digest = _calc_sha256_digest(request_body_json)
    payload_date = now_utc().strftime("%Y%m%d")  # UTC
    payload = f"{hex_digest}\n{content_type}\n{payload_date}\n{canonical_url}"
    jws_payload = _b64url(payload.encode())

    signing_input = f"{jws_header}.{jws_payload}"
    signature = hmac.new(secret_key.encode(), signing_input.encode(), hashlib.sha256).digest()
    token = f"{signing_input}.{_b64url(signature)}"

    http_headers = {
        "Date": now_utc().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "Authorization": f"Bearer {token}",
    }

    req = urllib.request.Request(endpoint, headers=http_headers, method=method)

    with urllib.request.urlopen(req, timeout=60) as res:
        resp = res.read()

    info = json.loads(resp.decode())
    data = info.get(index, [])
    return pd.json_normalize(data)


# ======== 抓取 7 天內線上報表 ========
def get_table(account_id: str) -> pd.DataFrame:
    tw_now = now_tw()
    since_date = (tw_now - timedelta(days=7)).date().isoformat()
    until_date = tw_now.date().isoformat()

    daterange = pd.date_range(since_date, until_date)
    out = pd.DataFrame()

    for day in daterange:
        d = day.strftime("%Y-%m-%d")
        canonical_url = f"/api/v3/adaccounts/{account_id}/reports/online/ad"
        url_parameters = f"?since={d}&until={d}&size=100"

        page = 1
        while True:
            tmp = read_text(canonical_url, f"{url_parameters}&page={page}", "datas")
            if tmp.empty:
                break
            tmp["date"] = d
            out = pd.concat([out, tmp], ignore_index=True)
            page += 1

    print("Successed get report.")
    return out


# ======== 統一 schema ========
def build_table(account_id: str) -> pd.DataFrame:
    raw = get_table(account_id)
    if raw.empty:
        return pd.DataFrame(columns=REQUIRED)

    df = _rename_to_canonical(raw)

    # 固定值
    df["media"] = "Line lab"
    df["channel_type"] = "Line lab"

    # 視訊欄位（有就用；沒有補 0）
    if "statistics_videoView3s" in df:
        df["video_thruplay"] = df["statistics_videoView3s"]
        df["view_view"] = df["statistics_videoView3s"]
    else:
        df["video_thruplay"] = 0
        df["view_view"] = 0
    df["video_25"] = df["statistics_videoView25r"] if "statistics_videoView25r" in df else 0
    df["video_50"] = df["statistics_videoView50r"] if "statistics_videoView50r" in df else 0
    df["video_75"] = df["statistics_videoView75r"] if "statistics_videoView75r" in df else 0
    df["video_100"] = df["statistics_videoCompletions"] if "statistics_videoCompletions" in df else 0

    # 型別/缺欄補值 & 欄序
    df = _ensure_required(df)
    return df


# ======== 讀取 Ads（創意） ========
def read_ads(account_id: str) -> pd.DataFrame:
    canonical_url_ads = f"/api/v3/adaccounts/{account_id}/ads"
    ads = read_text(canonical_url_ads, "", "datas")
    if ads.empty:
        return pd.DataFrame(columns=["ad_id", "ad_name", "creative_id", "creative_url", "creative_title", "creative_description"])

    ads = _rename_to_canonical(ads)

    # 常見欄位對齊
    if "id" in ads.columns and "ad_id" not in ads.columns:
        ads = ads.rename(columns={"id": "ad_id"})
    if "name" in ads.columns and "ad_name" not in ads.columns:
        ads = ads.rename(columns={"name": "ad_name"})

    # 可能有 image 或 video 來源
    if "creative_image_object_sourceUrl" in ads.columns and "creative_url" not in ads.columns:
        ads = ads.rename(columns={"creative_image_object_sourceUrl": "creative_url"})
    if "creative_video_object_sourceUrl" in ads.columns:
        # 如果 image 沒有，則用 video 補
        if "creative_url" not in ads.columns or ads["creative_url"].isna().all():
            ads["creative_url"] = ads["creative_video_object_sourceUrl"]

    keep = ["ad_id", "ad_name", "creative_id", "creative_url", "creative_title", "creative_description"]
    for c in keep:
        if c not in ads.columns:
            ads[c] = ""
        ads[c] = ads[c].astype(str)

    return ads[keep]


# ======== 合併報表與創意 ========
def merge_table(account_id: str) -> pd.DataFrame:
    df = build_table(account_id)
    if df.empty:
        return df
    ads = read_ads(account_id)
    if ads.empty:
        return df
    fin = df.merge(ads, how="left", on=["ad_id", "ad_name"])
    return fin


# ======== 上傳 BigQuery ========
def upload_bigquery_table(project: str, dataset: str, table: str, account_id: str) -> None:
    df = merge_table(account_id)
    if df.empty:
        print(f"No data update to : {table}")
        return

    # 認證（請確認路徑正確）
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
    client = bq.Client()

    table_ref = f"{project}.{dataset}.{table}"

    # 檢查表是否存在
    try:
        client.get_table(table_ref)
        exists = True
    except Exception:
        exists = False

    if exists:
        # 以台北當地日曆日刪除過去 7 天 (含今日)
        sql = f"""
            DELETE FROM `{table_ref}`
            WHERE date BETWEEN DATE_SUB(CURRENT_DATE("Asia/Taipei"), INTERVAL 7 DAY)
                           AND CURRENT_DATE("Asia/Taipei")
        """
        client.query(sql, location="US").result()

        client.load_table_from_dataframe(df, table_ref, location="US").result()
    else:
        job_config = bq.LoadJobConfig()
        job_config.create_disposition = bq.CreateDisposition.CREATE_IF_NEEDED
        client.load_table_from_dataframe(df, table_ref, job_config=job_config, location="US").result()

    print(f"update df to table : {table}")


# ======== (選用) 對齊「從 Excel 匯出的 get_table 結果」 ========
def standardize_exported_excel(xlsx_path: str) -> pd.DataFrame:
    """
    若你手邊有 get_table 匯出的 Excel，丟進來就會回傳已對齊 REQUIRED schema 的 DataFrame。
    """
    df = pd.read_excel(xlsx_path)
    df = _rename_to_canonical(df)

    df["media"] = "Line lab"
    df["channel_type"] = "Line lab"

    # 影片欄位補齊
    if "statistics_videoView3s" in df:
        df["video_thruplay"] = df["statistics_videoView3s"]
        df["view_view"] = df["statistics_videoView3s"]
    else:
        df["video_thruplay"] = 0
        df["view_view"] = 0
    df["video_25"] = df["statistics_videoView25r"] if "statistics_videoView25r" in df else 0
    df["video_50"] = df["statistics_videoView50r"] if "statistics_videoView50r" in df else 0
    df["video_75"] = df["statistics_videoView75r"] if "statistics_videoView75r" in df else 0
    df["video_100"] = df["statistics_videoCompletions"] if "statistics_videoCompletions" in df else 0

    df = _ensure_required(df)
    return df


# ======== 執行入口 ========
if __name__ == "__main__":
    # 讀取上傳帳號清單
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
    client = bq.Client()

    project_name = "eco-carver-356809"
    dataset_name = "ref_tables"
    table_name = "line_account"

    sql = f"SELECT * FROM `{project_name}.{dataset_name}.{table_name}`"
    account_df = client.query(sql, location="US").to_dataframe()

    for i in range(len(account_df)):
        account_name = account_df.iat[i, 0]
        account_id   = account_df.iat[i, 1]
        up_project   = account_df.iat[i, 2]
        up_dataset   = account_df.iat[i, 3]
        up_table     = account_df.iat[i, 4]

        print(account_name)
        try:
            upload_bigquery_table(up_project, up_dataset, up_table, account_id)
        except Exception as e:
            print(f'There is some error in : {account_name}\n{e}\n')
        print()

