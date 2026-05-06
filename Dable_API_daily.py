#!/usr/bin/env python
# coding: utf-8

# In[8]:


#import packages
import requests
import pandas as pd
import GoogleAds_api_token_Han as token
import Dable_Parm_token as d
from datetime import datetime, timedelta
import os
from google.cloud import bigquery as bq


# In[9]:


# 建立 python 與 bigquery 連線
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "eco-carver-356809-38c8914cd90f.json"
client = bq.Client()

project_name = 'eco-carver-356809'
dataset_name = 'ref_tables'
table_name = 'dable_account'

# Select table in BQ
sql = """
    select *
    from `{}.{}.{}`
    """.format(project_name,dataset_name,table_name)

# run query
query_job = client.query(sql, location="US")

# Store query result to df
account_df = query_job.to_dataframe()


# In[28]:


account_df


# In[1]:


#!/usr/bin/env python
# coding: utf-8

# ================================
#        🧩 載入必要套件
# ================================
import requests
import pandas as pd
from datetime import datetime, timedelta
import os
from google.cloud import bigquery as bq
from google.api_core.exceptions import NotFound, GoogleAPIError

# ✅ 自訂 module：API Token
import Dable_Parm_token as d  # 應包含 `name` 與 `token`

# ================================
#        🔧 認證與全域變數
# ================================
CREDENTIAL_PATH = "eco-carver-356809-38c8914cd90f.json"
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = CREDENTIAL_PATH

BQ_LOCATION = "US"

# ================================
#   🔁 Step 1. 擷取 Dable 資料
# ================================
def get_dable_campaign_data(client_name: str, api_key: str, start_date: datetime, end_date: datetime) -> pd.DataFrame:
    """
    從 Dable API 取得每日 Campaign 報表並轉為扁平化 DataFrame
    """
    url = f"https://marketing.dable.io/api/client/{client_name}/daily_report"
    params = {
        "api_key": api_key,
        "start_date": start_date.strftime('%Y-%m-%d'),
        "end_date": end_date.strftime('%Y-%m-%d'),
        "group_by_campaign": 1
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        raw_data = response.json()
    except requests.RequestException as e:
        print(f"[❌ API錯誤] 無法取得 Dable 資料: {e}")
        return pd.DataFrame()

    records = []

    for date, campaigns in raw_data.items():
        if not isinstance(campaigns, dict):
            continue
        for campaign_id, metrics in campaigns.items():
            if not isinstance(metrics, dict):
                continue
            record = {
                'date': date,
                'campaign_id': campaign_id,
                'exposes': metrics.get('exposes'),
                'impressions': metrics.get('impressions'),
                'clicks': metrics.get('clicks'),
                'ctr': metrics.get('ctr'),
                'cost_spent': metrics.get('cost_spent'),
                'avg_cpc': metrics.get('avg_cpc'),
                'convertion_cnt': metrics.get('convertion_cnt'),
                'convertion_rate': metrics.get('convertion_rate'),
                'cpa': metrics.get('cpa'),
                'campaign_name': metrics.get('campaign_name'),
                'lead_cnt': metrics.get('convertion', {}).get('lead', {}).get('cnt'),
                'lead_conversion_rate': metrics.get('convertion', {}).get('lead', {}).get('conversion_rate'),
                'lead_cpa': metrics.get('convertion', {}).get('lead', {}).get('cpa'),
            }
            records.append(record)

    df = pd.DataFrame(records)

    # ✅ 強制轉換 date 欄位為 datetime.date
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date']).dt.date

    return df


# ================================
#   ⬆️  Step 2. 上傳至 BigQuery
# ================================
def upload_bigquery_table(project: str, dataset: str, table: str, df: pd.DataFrame):
    """
    將 DataFrame 上傳至 BigQuery，並將 date 欄位設為 DATE 類型，且排序由遠到近。
    """
    if df.empty:
        print(f"[📭 無資料] ➜ {table}")
        return

    client = bq.Client()
    table_ref = f"{project}.{dataset}.{table}"

    # ✅ 強制轉換並排序 date 欄位
    if 'date' in df.columns:
        df['date'] = pd.to_datetime(df['date']).dt.date
        df = df.sort_values(by='date', ascending=True)  # 由遠到近排序

    # 檢查表是否存在
    try:
        table_obj = client.get_table(table_ref)
        table_exists = True
    except NotFound:
        table_exists = False

    # 刪除近 7 天資料
    now_tw = datetime.utcnow() + timedelta(hours=8)
    start_date = (now_tw - timedelta(days=7)).date()
    end_date = now_tw.date()

    if table_exists:
        delete_sql = f"""
            DELETE FROM `{table_ref}`
            WHERE DATE(date) BETWEEN DATE('{start_date}') AND DATE('{end_date}')
        """
        try:
            client.query(delete_sql, location=BQ_LOCATION).result()
            print(f"[🗑️ 清除] 已刪除 {start_date} ~ {end_date} 的資料")
        except Exception as e:
            print(f"[❗SQL錯誤] 刪除失敗: {e}")

    # 定義 schema
    schema = [
        bq.SchemaField("date", "DATE"),
        bq.SchemaField("campaign_id", "STRING"),
        bq.SchemaField("campaign_name", "STRING"),
        bq.SchemaField("exposes", "INTEGER"),
        bq.SchemaField("impressions", "INTEGER"),
        bq.SchemaField("clicks", "INTEGER"),
        bq.SchemaField("ctr", "FLOAT"),
        bq.SchemaField("cost_spent", "FLOAT"),
        bq.SchemaField("avg_cpc", "FLOAT"),
        bq.SchemaField("convertion_cnt", "INTEGER"),
        bq.SchemaField("convertion_rate", "FLOAT"),
        bq.SchemaField("cpa", "FLOAT"),
        bq.SchemaField("lead_cnt", "INTEGER"),
        bq.SchemaField("lead_conversion_rate", "FLOAT"),
        bq.SchemaField("lead_cpa", "FLOAT")
    ]

    job_config = bq.LoadJobConfig(
        write_disposition=bq.WriteDisposition.WRITE_APPEND,
        schema=schema
    )

    # 上傳
    try:
        job = client.load_table_from_dataframe(df, table_ref, job_config=job_config, location=BQ_LOCATION)
        job.result()
        print(f"[✅ 上傳成功] ➜ {table}（{len(df)} 筆，已排序）")
    except Exception as e:
        print(f"[❌ 上傳錯誤] {e}")


# ================================
#   📦 Step 3. 執行主流程（多帳戶）
# ================================
def main():
    client = bq.Client()
    project = 'eco-carver-356809'
    dataset = 'ref_tables'
    table = 'dable_account'

    query = f"SELECT * FROM `{project}.{dataset}.{table}`"
    try:
        account_df = client.query(query).to_dataframe()
    except Exception as e:
        print(f"[❌ 無法取得帳號資訊表]：{e}")
        return

    # 處理每個帳戶
    for i, row in account_df.iterrows():
        account_name = row['account_name']
        account_id = row['account_id']
        upload_project = row['upload_project']
        upload_dataset = row['upload_dataset']
        upload_table = row['upload_table']
        final_dataset = row['dataset']
        creative_final = row['table_creative']
        print(f"\n🚀 處理帳戶 【{account_name}】")

        try:
            end_date = datetime.today()
            start_date = end_date - timedelta(days=7)

            # 擷取 Dable 資料
            df = get_dable_campaign_data(
                client_name=account_id,
                api_key=d.token,
                start_date=start_date,
                end_date=end_date
            )

            # 上傳至 BigQuery
            upload_bigquery_table(
                project=upload_project,
                dataset=upload_dataset,
                table=upload_table,
                df=df
            )

            upload_bigquery_table(
                project = upload_project,
                dataset = final_dataset,
                table = creative_final,
                df = df
            )

        except Exception as e:
            print(f"[⚠️ 錯誤] 帳號「{account_name}」處理失敗：{e}")


# ================================
#                🚀 執行程式
# ================================
if __name__ == "__main__":
    main()


# In[ ]:




